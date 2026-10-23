"""SEC EDGAR: 10-K/20-F item text, recent 8-K/6-K, and XBRL company facts.

Uses edgartools (imports as `edgar`) with SEC_USER_AGENT from .env. All item text
goes through evidence.ingest_document(), which registers one Source per document
and chunks it; raw extraction output is cached in data/cache/ via ingest/_cache.py
so re-running a ticker doesn't refetch unless its cache is cleared.

Fails soft throughout: a company with no 10-K (an ETF), a missing XBRL tag, or an
item edgartools can't parse logs a line and moves on -- see STEP 3's "if item
extraction fails, split the full text into paragraphs instead" for the item-text
fallback, and _best_annual_fact() for the XBRL-tag fallback.
"""
import os
import re
import warnings

import edgar as edgartools

# edgartools warns on every XBRL tag that isn't tagged for a given company/year --
# expected and handled by _best_annual_fact()'s multi-tag search, not worth the noise.
warnings.filterwarnings("ignore", category=UserWarning)

import evidence
from ingest._cache import cached_fetch

SEC_USER_AGENT = os.environ.get("SEC_USER_AGENT") or "Mandate Hackathon (no contact set in .env)"
edgartools.set_identity(SEC_USER_AGENT)

RECENT_MONTHS = 12

# Item labels per STEP 3: "Latest 10-K: Item 1, 1A, 3. 20-F: Item 3.D, 4, 8.A.7."
# edgartools exposes top-level items (Item 3, not Item 3.D), so the sub-item labels
# below describe what that block actually covers, not an edgartools section name.
TEN_K_ITEMS = [("Item 1", "Item 1 Business"), ("Item 1A", "Item 1A Risk Factors"),
               ("Item 3", "Item 3 Legal Proceedings")]
TWENTY_F_ITEMS = [("Item 3", "Item 3.D Risk Factors"), ("Item 4", "Item 4 Information on the Company"),
                   ("Item 8", "Item 8.A.7 Legal Proceedings")]

# Revenue/net income/etc. are tagged inconsistently across companies and years as
# GAAP taxonomies evolved (ASC 606 in ~2018 retagged revenue, for instance). For
# each concept we try every known tag and keep whichever has data for the most
# recent fiscal year -- not just the first one that returns anything.
# US-GAAP tags for domestic 10-K filers, plus IFRS tags (ifrs-full:*) for 20-F
# filers that report under IFRS -- BTI, DEO, GSK, UL and the other foreign filers
# in universe.py's FOREIGN_FILERS list all use IFRS, not US-GAAP.
XBRL_TAGS = {
    "revenue": ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet",
                "ifrs-full:Revenue"],
    "net_income": ["NetIncomeLoss", "ProfitLoss", "ifrs-full:ProfitLoss"],
    "total_liabilities": ["Liabilities", "ifrs-full:Liabilities"],
    "stockholders_equity": ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
                             "ifrs-full:Equity"],
    "operating_cash_flow": ["NetCashProvidedByUsedInOperatingActivities",
                             "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
                             "ifrs-full:CashFlowsFromUsedInOperatingActivities"],
    "dividends_per_share": ["CommonStockDividendsPerShareDeclared", "CommonStockDividendsPerShareCashPaid",
                             "ifrs-full:DividendsRecognisedAsDistributionsToOwnersPerShare",
                             "ifrs-full:DividendsPaidOrdinarySharesPerShare"],
}


def _sane(fact):
    """False if a fact's own fiscal_year label and period_end disagree by more than
    a year -- seen on a handful of older/inconsistently-tagged IFRS facts (a BTI
    dividend-per-share fact labelled fiscal_year=2019 with period_end 2018-02-28),
    which otherwise get treated as "most recent" and silently misreported.
    """
    try:
        return abs(fact.fiscal_year - fact.period_end.year) <= 1
    except Exception:
        return True  # missing data to check -- let it through rather than over-filter


def _best_annual_fact(facts, tag_candidates):
    """-> edgar FinancialFact for whichever tag in tag_candidates has the most
    recent fiscal year of (self-consistent) annual data, or None if none do."""
    best = None
    for tag in tag_candidates:
        try:
            fact = facts.get_annual_fact(tag)
        except Exception:
            fact = None
        if fact is not None and _sane(fact) and (best is None or fact.fiscal_year > best[0].fiscal_year):
            best = (fact, tag)
    return best


def _currency_unit(fact, default="usd"):
    """-> lowercase currency code from a fact's unit ("GBP", "USD per share" -> "gbp",
    "usd"), so foreign filers reporting in their home currency (BTI/DEO/GSK report
    in GBP, not USD) aren't mislabelled. Falls back to `default` if edgartools
    didn't resolve a unit.
    """
    unit = (getattr(fact, "unit", None) or "").strip()
    if not unit:
        return default
    # "GBP" -> "gbp", "USD per share" -> "usd", "GBP/shares" -> "gbp"
    head = re.split(r"[\s/]", unit)[0]
    code = head.lower()
    return code if len(code) == 3 else default


def _annual_fact_for_year(facts, tag, fiscal_year):
    try:
        return facts.get_annual_fact(tag, fiscal_year=fiscal_year)
    except Exception:
        return None


# ------------------------------------------------------------------------- filings
def fetch_filing_items(ticker):
    """Ingests the latest annual filing's item text (10-K: Item 1/1A/3, 20-F: Item
    3/4/8). -> number of new chunks added across all items."""
    try:
        company = edgartools.Company(ticker)
    except Exception as exc:
        print(f"[edgar] {ticker}: could not open Company ({exc})")
        return 0

    form, items = None, None
    for candidate_form, candidate_items in (("10-K", TEN_K_ITEMS), ("20-F", TWENTY_F_ITEMS)):
        filings = company.get_filings(form=candidate_form)
        if filings and len(filings) > 0:
            form, items = candidate_form, candidate_items
            break
    if form is None:
        print(f"[edgar] {ticker}: no 10-K or 20-F found (likely an ETF/fund)")
        return 0

    filing = company.get_filings(form=form).latest(1)

    def _extract():
        obj = filing.obj()
        out = {}
        for item_key, _ in items:
            try:
                out[item_key] = obj.get(item_key)
            except Exception as exc:
                print(f"[edgar] {ticker} {form} {item_key}: extraction failed ({exc}), "
                      f"falling back to full text")
                out[item_key] = None
        if all(v is None for v in out.values()):
            # Whole-document fallback per STEP 3: split the full text into
            # paragraphs instead of giving up on this filing.
            out["__fulltext__"] = filing.text()
        return out

    params = {"ticker": ticker, "form": form, "accession_no": filing.accession_no}
    extracted = cached_fetch(f"edgar_{form.lower().replace('-', '')}_items", params, _extract)
    if not extracted:
        return 0

    origin = "edgar_10k" if form == "10-K" else "edgar_20f"
    total_new = 0
    if "__fulltext__" in extracted:
        total_new += len(evidence.ingest_document(
            ticker,
            {"kind": "filing", "origin": origin, "title": f"{company.name} Form {form}",
             "date": str(filing.filing_date), "url": filing.filing_url,
             "section": f"{form} (full text, item extraction failed)"},
            extracted["__fulltext__"],
        ))
    else:
        for item_key, section_label in items:
            text = extracted.get(item_key)
            if not text:
                continue
            total_new += len(evidence.ingest_document(
                ticker,
                {"kind": "filing", "origin": origin, "title": f"{company.name} Form {form}",
                 "date": str(filing.filing_date), "url": filing.filing_url, "section": section_label},
                text,
            ))
    return total_new


def fetch_recent_events(ticker):
    """Ingests every 8-K (domestic) or 6-K (foreign) filed in the last RECENT_MONTHS
    months. -> number of new chunks added."""
    import datetime

    try:
        company = edgartools.Company(ticker)
    except Exception as exc:
        print(f"[edgar] {ticker}: could not open Company ({exc})")
        return 0

    cutoff = (datetime.date.today() - datetime.timedelta(days=RECENT_MONTHS * 31)).isoformat()
    total_new = 0
    for form, origin in (("8-K", "edgar_8k"), ("6-K", "edgar_6k")):
        try:
            filings = company.get_filings(form=form, date=f"{cutoff}:")
        except Exception as exc:
            print(f"[edgar] {ticker} {form}: filings lookup failed ({exc})")
            continue
        if not filings or len(filings) == 0:
            continue
        for filing in filings:
            params = {"ticker": ticker, "form": form, "accession_no": filing.accession_no}
            text = cached_fetch(f"edgar_{form.lower().replace('-', '')}_text", params,
                                 lambda f=filing: f.text())
            if not text:
                continue
            items_label = getattr(filing, "items", "") or form
            section = f"{form} Item {items_label}" if items_label and items_label != form else form
            total_new += len(evidence.ingest_document(
                ticker,
                {"kind": "filing", "origin": origin, "title": f"{company.name} Form {form}",
                 "date": str(filing.filing_date), "url": filing.filing_url, "section": section},
                text,
            ))
    return total_new


# --------------------------------------------------------------------------- xbrl
def fetch_fundamentals(ticker):
    """Computes the 5 contract metrics from XBRL company facts and writes
    data/processed/fundamentals/{ticker}.json. -> the Metric list, or [] on failure.
    """
    import json

    import sources as source_registry

    try:
        company = edgartools.Company(ticker)
        facts = company.get_facts()
    except Exception as exc:
        print(f"[edgar] {ticker}: XBRL company facts unavailable ({exc})")
        return []

    cik = int(company.cik)
    source_id = source_registry.register({
        "ticker": ticker, "kind": "filing", "origin": "edgar_xbrl",
        "title": f"{company.name} XBRL company facts", "date": None,
        "url": f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json", "section": None,
    })

    metrics = []

    def add(name, value, unit, as_of):
        if value is None:
            print(f"[edgar] {ticker}: no XBRL data for {name}, skipping")
            return
        metrics.append({"name": name, "value": value, "unit": unit,
                         "as_of": as_of, "source_id": source_id})

    revenue = _best_annual_fact(facts, XBRL_TAGS["revenue"])
    net_income = _best_annual_fact(facts, XBRL_TAGS["net_income"])
    liabilities = _best_annual_fact(facts, XBRL_TAGS["total_liabilities"])
    equity = _best_annual_fact(facts, XBRL_TAGS["stockholders_equity"])
    ocf = _best_annual_fact(facts, XBRL_TAGS["operating_cash_flow"])
    dps = _best_annual_fact(facts, XBRL_TAGS["dividends_per_share"])

    if revenue:
        fact, tag = revenue
        # SEC's XBRL coverage for a given tag sometimes runs short of a full 3
        # years (a recently-adopted tag, a newly-public company); search a small
        # window around fiscal_year-3 and take the oldest match, rather than
        # requiring exactly 3 years back.
        prior = None
        for years_back in (3, 4, 5, 2):
            prior = _annual_fact_for_year(facts, tag, fact.fiscal_year - years_back)
            if prior and prior.numeric_value:
                break
        if prior and prior.numeric_value:
            growth = (fact.numeric_value / prior.numeric_value) - 1
            add("revenue_3y_growth", round(growth, 4), "ratio", str(fact.period_end))
        else:
            print(f"[edgar] {ticker}: no revenue history for {tag}, skipping revenue_3y_growth")

    if revenue and net_income:
        rev_fact, _ = revenue
        ni_fact, _ = net_income
        if rev_fact.numeric_value:
            add("net_margin", round(ni_fact.numeric_value / rev_fact.numeric_value, 4),
                "ratio", str(ni_fact.period_end))

    if not liabilities and equity:
        # IFRS filers (BTI, DEO, ...) often tag CurrentLiabilities and
        # NoncurrentLiabilities but not a single combined "Liabilities" total.
        eq_fact, _ = equity
        current = _annual_fact_for_year(facts, "ifrs-full:CurrentLiabilities", eq_fact.fiscal_year)
        noncurrent = _annual_fact_for_year(facts, "ifrs-full:NoncurrentLiabilities", eq_fact.fiscal_year)
        if current and noncurrent:
            total = current.numeric_value + noncurrent.numeric_value

            class _Sum:  # minimal stand-in with just the fields used below
                numeric_value = total
                period_end = current.period_end

            liabilities = (_Sum(), "ifrs-full:CurrentLiabilities+NoncurrentLiabilities")

    if liabilities and equity:
        liab_fact, _ = liabilities
        eq_fact, _ = equity
        if eq_fact.numeric_value:
            add("debt_to_equity", round(liab_fact.numeric_value / eq_fact.numeric_value, 4),
                "ratio", str(liab_fact.period_end))

    if ocf:
        fact, _ = ocf
        add("operating_cash_flow", fact.numeric_value, _currency_unit(fact), str(fact.period_end))

    if dps:
        fact, _ = dps
        add("dividends_per_share", fact.numeric_value, _currency_unit(fact), str(fact.period_end))

    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out_dir = os.path.join(here, "data", "processed", "fundamentals")
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, f"{ticker.upper()}.json"), "w") as f:
        json.dump({"ticker": ticker, "metrics": metrics}, f, indent=2)
        f.write("\n")

    return metrics


def fetch_company(ticker):
    """Runs all three EDGAR fetches for one ticker. -> dict of what happened, for
    run_all.py's coverage table."""
    new_item_chunks = fetch_filing_items(ticker)
    new_event_chunks = fetch_recent_events(ticker)
    metrics = fetch_fundamentals(ticker)
    return {"filing_chunks": new_item_chunks, "event_chunks": new_event_chunks,
            "metrics": len(metrics)}
