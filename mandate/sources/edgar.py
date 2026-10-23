"""SEC EDGAR: latest 10-K / 20-F for a ticker, split into sections (best effort)."""
import json
import re
import time

import requests
from bs4 import BeautifulSoup

from .. import config as C

EDGAR_DIR = C.CACHE_DIR / "edgar"
FULL_CHARS = 400_000        # fallback: first 400k chars of the whole document
SECTION_MAX = 150_000
MIN_TOTAL = 30_000          # less than this across all sections means extraction failed
MIN_SECTION = 200           # shorter than this is a table-of-contents hit, not the section
# (item label, section name) per form. 20-F Item 3 holds 3.D Risk Factors; Item 8 holds 8.A.7 legal.
WANTED = {
    "10-K": [("1", "Business"), ("1A", "Risk Factors"), ("3", "Legal Proceedings")],
    "20-F": [("3", "Risk Factors"), ("4", "Information on the Company"), ("8", "Legal Proceedings")],
}
ITEM = re.compile(r"\bItem\s+(\d{1,2}[A-C]?)\s*[\.:\-–—]", re.I)
# "see Item 1A." inside a sentence is a cross-reference, not a heading
XREF_BEFORE = {"see", "in", "under", "to", "and", "of", "this", "our", "the", "with", "by", "also", "or", "at"}
_last = 0.0


def _get(url: str) -> requests.Response:
    """GET with the SEC User-Agent, at most ~6 requests/s (SEC limit is 10/s)."""
    global _last
    time.sleep(max(0.0, 0.15 - (time.time() - _last)))
    r = requests.get(url, headers={"User-Agent": C.EDGAR_USER_AGENT}, timeout=60)
    _last = time.time()
    r.raise_for_status()
    return r


def _cik(ticker: str) -> int:
    path = EDGAR_DIR / "_company_tickers.json"
    if not path.exists():
        EDGAR_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(_get("https://www.sec.gov/files/company_tickers.json").text, encoding="utf-8")
    for row in json.loads(path.read_text(encoding="utf-8")).values():
        if row["ticker"].upper() == ticker.upper():
            return int(row["cik_str"])
    raise KeyError(f"{ticker} not in SEC company_tickers.json")


def latest_filing(ticker: str, form: str) -> dict:
    cik = _cik(ticker)
    recent = _get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json").json()["filings"]["recent"]
    for i, f in enumerate(recent["form"]):
        if f == form:
            acc = recent["accessionNumber"][i].replace("-", "")
            return {"form": form, "filing_date": recent["filingDate"][i],
                    "url": f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{recent['primaryDocument'][i]}"}
    raise LookupError(f"no {form} found for {ticker}")


def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for t in soup.find_all(["script", "style", "ix:header"]):   # ix:header = hidden XBRL block
        t.decompose()
    return re.sub(r"\s+", " ", soup.get_text(" ")).strip()


def extract_sections(text: str, form: str) -> dict[str, str]:
    """Cut the wanted Items out of the text. Of each Item's heading hits, keep the longest span."""
    marks = []
    for m in ITEM.finditer(text):
        prev = text[max(0, m.start() - 12):m.start()].split()
        if prev and prev[-1].lower().strip(",;()") in XREF_BEFORE:
            continue
        marks.append((m.start(), m.group(1).upper()))
    out = {}
    for label, name in WANTED[form]:
        best = ""
        for i, (pos, lab) in enumerate(marks):
            if lab != label:
                continue
            end = next((p for p, other in marks[i + 1:] if other != label), len(text))
            if end - pos > len(best):
                best = text[pos:end]
        if len(best) >= MIN_SECTION:
            out[name] = best[:SECTION_MAX]
    return out


def fetch_filing(ticker: str, form: str, force: bool = False) -> dict | None:
    """Cached {"form","filing_date","url","sections"}. Falls back to sections={"full": ...}."""
    path = EDGAR_DIR / f"{ticker}.json"
    if path.exists() and not force:
        return json.loads(path.read_text(encoding="utf-8"))
    if C.DEMO_MODE:
        return None
    meta = latest_filing(ticker, form)
    text = html_to_text(_get(meta["url"]).text)
    sections = extract_sections(text, form)
    if sum(map(len, sections.values())) < MIN_TOTAL:     # extraction clearly missed: use the whole document
        sections = {"full": text[:FULL_CHARS]}
    rec = {**meta, "sections": sections}
    EDGAR_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rec), encoding="utf-8")
    return rec
