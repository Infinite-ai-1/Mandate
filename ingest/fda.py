"""openFDA: enforcement reports (recalls) by firm name, across drug/device/food.

Searches all three openFDA enforcement endpoints (a company like 3M shows up
under "device", a food/beverage company under "food", a pharma company under
"drug") since there's no single cross-category search. The field is
recalling_firm, matched with a quoted phrase search; openFDA has no fuzzy
matching, so a firm name that doesn't exactly match a substring of the real
recalling_firm value (e.g. a subsidiary name) finds nothing -- best effort, same
spirit as STEP 3 asks of epa.py.

Keyless public API, no .env entry needed. openFDA returns HTTP 404 (not an empty
list) when a search matches nothing, which is the normal "no recalls" case, not
a failure -- handled explicitly rather than as an error.
"""
import os

import requests

import evidence
from ingest._cache import RateLimiter, cached_fetch

BASE_URL = "https://api.fda.gov"
CATEGORIES = ["drug", "device", "food"]
LIMIT = 20       # recalls per category per company; most companies have far fewer
RECENT_YEARS = 5  # openFDA's recall history goes back decades; keep this recent

_limiter = RateLimiter(0.3)  # openFDA's unauthenticated rate limit is 40 req/min


def _search(category, firm_name):
    _limiter.wait()
    query = f'recalling_firm:"{firm_name}"'
    resp = requests.get(f"{BASE_URL}/{category}/enforcement.json",
                         params={"search": query, "limit": LIMIT, "sort": "report_date:desc"},
                         timeout=15)
    if resp.status_code == 404:
        return []  # openFDA's normal "no matches" response, not an error
    resp.raise_for_status()
    return resp.json().get("results", [])


def fetch_recalls(ticker, company_name):
    """Searches drug/device/food enforcement reports for `company_name` as the
    recalling firm, ingesting each hit as a Chunk. -> number of new chunks added.
    """
    total_new = 0
    for category in CATEGORIES:
        params = {"ticker": ticker, "category": category, "firm": company_name}
        results = cached_fetch("fda_enforcement", params, lambda c=category: _search(c, company_name))
        if not results:
            continue

        for r in results:
            reason = r.get("reason_for_recall") or ""
            product = r.get("product_description") or ""
            classification = r.get("classification") or ""
            text = (
                f"openFDA {category} enforcement report for {r.get('recalling_firm', company_name)}: "
                f"{classification} recall of {product}. Reason: {reason}. "
                f"Status: {r.get('status', 'unknown')}. Distribution: {r.get('distribution_pattern', 'unknown')}."
            ).strip()
            if not reason and not product:
                continue
            date = r.get("report_date")  # "YYYYMMDD"
            date = f"{date[0:4]}-{date[4:6]}-{date[6:8]}" if date and len(date) == 8 else None
            total_new += len(evidence.ingest_document(
                ticker,
                {"kind": "regulator", "origin": "fda", "title": f"openFDA {category} recall {r.get('recall_number', '')}",
                 "date": date, "url": "https://www.accessdata.fda.gov/scripts/ires/index.cfm",
                 "section": f"{category} enforcement, classification {classification}"},
                text,
            ))
    return total_new
