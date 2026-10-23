"""Code-level checks on every agent claim: quotes, metrics (within 2%), source IDs."""
from .evidence import get_chunk
from .schemas import (BalthasarOutput, CasperOutput, ChairOutput, ChairResult, FinResult, MelchiorOutput,
                      MelchiorResult, RiskResult, Verdict)

TOLERANCE = 0.02
UNVERIFIED_FAIL = "Evidence quote could not be verified."
_QUOTES = {"‘": "'", "’": "'", "“": '"', "”": '"', " ": " ", "–": "-", "—": "-"}


def norm(s: str) -> str:
    """Lowercase, collapse whitespace, straighten quotes and dashes."""
    for a, b in _QUOTES.items():
        s = s.replace(a, b)
    return " ".join(s.lower().split())


def quote_in(quote: str | None, text: str) -> bool:
    q = norm(quote or "")
    return bool(q) and q in norm(text)


def metric_matches(metric: str | None, value, data: dict) -> bool:
    """The metric must exist in the computed data and the cited value be within 2% of it."""
    actual = data.get(metric) if metric else None
    if isinstance(actual, bool) or not isinstance(actual, (int, float)):
        return False
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return abs(value - actual) <= TOLERANCE * abs(actual) if actual else abs(value) < 1e-9


def _quote_ok(v: Verdict, ticker: str) -> bool:
    chunk = get_chunk(v.source_id) if v.source_id else None
    return bool(chunk and chunk.ticker == ticker and quote_in(v.quote, chunk.text))


def verify_verdicts(ticker: str, rule_ids: list[str], out: MelchiorOutput) -> MelchiorResult:
    """One verdict per rule. Unknown rule IDs are dropped, missing ones become FLAG, unverified FAIL becomes FLAG."""
    first: dict[str, Verdict] = {}
    for v in out.verdicts:
        if v.rule_id in rule_ids:
            first.setdefault(v.rule_id, v)
    result = []
    for rid in rule_ids:
        v = first.get(rid)
        if v is None:
            result.append(Verdict(rule_id=rid, verdict="FLAG", verified=False, reason="No verdict was returned for this rule."))
        elif v.verdict == "FAIL":
            if _quote_ok(v, ticker):
                result.append(v.model_copy(update={"verified": True}))
            else:
                result.append(v.model_copy(update={"verdict": "FLAG", "verified": False, "downgraded": True,
                                                   "reason": f"{UNVERIFIED_FAIL} Model said: {v.reason}"}))
        else:   # PASS / FLAG: a quote is optional, but if given it is checked
            result.append(v.model_copy(update={"verified": _quote_ok(v, ticker) if v.quote else True}))
    return MelchiorResult(ticker=ticker, verdicts=result)


def verify_fin(out: BalthasarOutput, data: dict) -> FinResult:
    """Keep reasons whose metric exists with a matching value. No verified reason -> score None."""
    ok, bad = [], []
    for r in out.reasons:
        # "missing" is only honest if some metric really is missing
        is_missing = r.metric == "missing" and any(v is None for v in data.values())
        (ok if is_missing or metric_matches(r.metric, r.value, data) else bad).append(r)
    if not ok:
        return FinResult(ticker=out.ticker, score=None, unverified=bad, note="Financial data missing or unverifiable.")
    return FinResult(ticker=out.ticker, score=out.score, reasons=ok, unverified=bad)


def verify_risk(out: CasperOutput, stats: dict) -> RiskResult:
    """A reason passes if every thing it cites (stat value and/or source ID) checks out, and it cites something."""
    ok, bad = [], []
    for r in out.reasons:
        checks = []
        if r.metric is not None:
            checks.append(metric_matches(r.metric, r.value, stats))
        if r.source_id is not None:
            checks.append(get_chunk(r.source_id) is not None)
        (ok if checks and all(checks) else bad).append(r)
    if not ok:
        return RiskResult(ticker=out.ticker, score=None, unverified=bad, note="Risk data missing or unverifiable.")
    return RiskResult(ticker=out.ticker, score=out.score, reasons=ok, unverified=bad)


def verify_chair(out: ChairOutput, allowed: set[str]) -> ChairResult:
    """Every cited ID must come from the specialists' verified reasons. IDs that are chunks become links."""
    ok, bad = [], []
    for r in out.reasons:
        (ok if r.source_ids and all(i in allowed for i in r.source_ids) else bad).append(r)
    links = {}
    for r in ok:
        for i in r.source_ids:
            c = get_chunk(i)
            if c and c.url:
                links[i] = c.url
    return ChairResult(ticker=out.ticker, decision=out.decision, reasons=ok, unverified=bad, links=links)
