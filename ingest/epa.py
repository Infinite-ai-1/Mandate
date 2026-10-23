"""EPA ECHO: enforcement/violations by company name. Best effort, as asked for in
STEP 3 -- ECHO's REST API only supports facility-name search (no ticker lookup),
so a tobacco holding company's listed brand name may not match its plants'
registered facility names at all. Every match this module makes is logged with a
fuzzy match score so a human (or verify.py) can sanity-check it; low-confidence
matches are kept but clearly flagged rather than silently dropped.

Two-step flow, reverse-engineered against the live API (ECHO's REST docs describe
the summary-count behaviour but not this row-retrieval path):
  1. cwa_rest_services.get_facilities (name [+ state] search) -> a QueryID, plus
     aggregate counts (significant violations, total penalties) across all
     programs -- but NOT the facility rows themselves.
  2. echo_rest_services.get_download(qid=..., output=CSV) -> the actual facility
     rows (name, SourceID/NPDES permit, address, NAICS) for that QueryID.
  3. dfr_rest_services.get_dfr(p_id=<SourceID>) -> the full Detailed Facility
     Report for one facility: current compliance status per statute (CAA/CWA/
     RCRA/SDWA), inspection counts, formal enforcement actions and penalties.

Keyless public API, no .env entry. Best-effort/log-match-quality per STEP 3: a
facility search that returns nothing, or a DFR call that fails, logs and the
company is simply skipped -- this is expected for most of the universe (most
companies have no EPA enforcement history at all).
"""
import csv
import io
import os

import requests

import evidence
from ingest._cache import RateLimiter, cached_fetch

BASE_URL = "https://echodata.epa.gov/echo"
MATCH_THRESHOLD = 70  # rapidfuzz score (0-100) below which a facility match is logged as weak
MATCH_FLOOR = 25      # below this, ECHO's own name search is returning noise -- skip, don't even log
MAX_FACILITIES = 5    # cap DFR calls per company -- a conglomerate can have hundreds of sites

# CWPName, SourceID, CWPStreet, CWPCity, CWPState, CWPStateDistrict, CWPNAICSCodes,
# CWPNAICSDescs, FacLat -- column numbers found by trial against the live API,
# not documented anywhere findable; if ECHO ever reshuffles its column numbering
# this mapping (and only this mapping) would need re-verifying against a live call.
FACILITY_QCOLUMNS = "1,2,3,4,5,6,24,25,26"

_limiter = RateLimiter(0.5)


def _get(path, params, timeout=20):
    _limiter.wait()
    resp = requests.get(f"{BASE_URL}/{path}", params=params, timeout=timeout)
    resp.raise_for_status()
    return resp


def _facility_query_id(company_name, state=None):
    params = {"output": "JSON", "p_fn": company_name}
    if state:
        params["p_st"] = state
    data = cached_fetch("epa_facility_search", params,
                         lambda: _get("cwa_rest_services.get_facilities", params).json())
    results = (data or {}).get("Results", {})
    if "Error" in results:
        print(f"[epa] {company_name}: search too broad even with filters "
              f"({results['Error'].get('ErrorMessage')}), skipping")
        return None
    return results.get("QueryID")


def _facility_rows(qid):
    params = {"qid": qid, "qcolumns": FACILITY_QCOLUMNS, "output": "CSV"}
    text = cached_fetch("epa_facility_download", params,
                         lambda: _get("echo_rest_services.get_download", params).text)
    if not text:
        return []
    return list(csv.DictReader(io.StringIO(text)))


def _dfr(source_id):
    params = {"p_id": source_id, "output": "JSON"}
    data = cached_fetch("epa_dfr", params, lambda: _get("dfr_rest_services.get_dfr", params).json())
    return (data or {}).get("Results")


def _summarize_dfr(facility_name, source_id, dfr):
    summaries = ((dfr.get("EnforcementComplianceSummaries") or {}).get("Summaries")) or []
    lines = [f"EPA ECHO detailed facility report for {facility_name} (ID {source_id})."]
    any_data = False
    for s in summaries:
        statute = s.get("Statute")
        status = s.get("CurrentStatus")
        if not statute or not status:
            continue
        any_data = True
        bits = [f"{statute} compliance status: {status}"]
        if s.get("Inspections"):
            bits.append(f"{s['Inspections']} inspections (last {s.get('LastInspection') or 'unknown date'})")
        if s.get("FormalActions") and s["FormalActions"] != "0":
            bits.append(f"{s['FormalActions']} formal enforcement actions")
        if s.get("TotalPenalties") and s["TotalPenalties"] not in (None, "$0"):
            bits.append(f"total penalties {s['TotalPenalties']}")
        lines.append(". ".join(bits) + ".")

    formal = (dfr.get("FormalActions") or {}).get("Action") or []
    priced = [a for a in formal if a.get("PenaltyAmount") and a["PenaltyAmount"] not in ("$0", None)]
    if priced:
        any_data = True
        lines.append("Formal enforcement actions with a penalty: " + "; ".join(
            f"{a.get('Statute')} {a.get('ActionType')} on {a.get('ActionDate')} for {a.get('PenaltyAmount')}"
            for a in priced[:5]
        ) + ".")

    return " ".join(lines) if any_data else None


def fetch_violations(ticker, company_name, state=None):
    """Searches EPA ECHO for facilities matching `company_name`, fetches a
    Detailed Facility Report for the best-matching ones, and ingests a compliance
    summary as a Chunk for each. -> number of new chunks added.
    """
    qid = _facility_query_id(company_name, state=state)
    if not qid:
        print(f"[epa] {company_name}: no facility match")
        return 0

    rows = _facility_rows(qid)
    if not rows:
        print(f"[epa] {company_name}: query matched but download returned no rows")
        return 0

    try:
        from rapidfuzz import fuzz
        scored = [(fuzz.token_set_ratio(company_name.upper(), r.get("CWPName", "")), r) for r in rows]
    except ImportError:
        scored = [(100 if company_name.upper() in r.get("CWPName", "").upper() else 0, r) for r in rows]
    scored.sort(key=lambda x: -x[0])

    total_new = 0
    for score, row in scored[:MAX_FACILITIES]:
        name, source_id = row.get("CWPName"), row.get("SourceID")
        if not source_id or score < MATCH_FLOOR:
            continue
        quality = "exact/strong" if score >= MATCH_THRESHOLD else "weak"
        print(f"[epa] {ticker}: matched facility '{name}' ({source_id}) to '{company_name}' "
              f"score={score} match_quality={quality}")

        dfr = _dfr(source_id)
        if not dfr:
            continue
        text = _summarize_dfr(name, source_id, dfr)
        if not text:
            continue
        total_new += len(evidence.ingest_document(
            ticker,
            {"kind": "regulator", "origin": "epa", "title": f"EPA ECHO facility report: {name}",
             "date": None, "url": f"https://echo.epa.gov/detailed-facility-report?fid={source_id}",
             "section": f"match_quality={quality} score={score}"},
            text,
        ))
    return total_new
