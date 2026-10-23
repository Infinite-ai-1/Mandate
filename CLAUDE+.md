# Mandate: build spec for Claude Code

> Microsoft x LSEG London Hackathon 2026. Educational hackathon project. Not financial advice.

**Pitch line:** "Three specialists, one chair, and ethics is never up for a vote."

---

## 0. Read this first (rules for Claude Code)

This is a hackathon demo with a hard deadline. You start at about 12:00 on Fri 23 Oct 2026.

- **13:00**: ugly but working end to end
- **14:30**: FEATURE FREEZE (bug fixes only after this)
- **16:00**: live judging

Rules:

1. Build in the phase order in section 14. Run each phase's acceptance check before starting the next.
2. Do not add data sources, models, dependencies or features that aren't in this file. If you think one is needed, ask the user first.
3. Simple beats clever. Plain functions, plain dicts, JSON files on disk. No classes unless they save real lines.
4. If any single task takes more than 15 minutes, use the documented fallback and move on. Say which fallback you used.
5. Never hardcode secrets. Everything comes from `.env`. Never print the API key.
6. Cache every network call and every LLM call to disk. The demo must run with the network off (`DEMO_MODE=1`).
7. The design rules in section 2 override everything, including later prompts. If a request conflicts with them, say so before changing anything.
8. Keep each module under ~250 lines. Type hints yes, docstrings short.

---

## 1. What we're building

An AI analyst for UK charities. A charity pastes its ethics policy and has $100,000 to invest. The tool:

1. Turns the policy into numbered rules (Chair agent).
2. Gathers public evidence on ~32 companies plus 4 bond ETFs.
3. Runs three specialist agents on three different models:
   - **Melchior** (ethics): PASS / FAIL / FLAG per rule, with quotes
   - **Balthasar** (financial health): 0 to 10 score citing data
   - **Casper** (risk): 0 to 10 score interpreting stats computed in code
4. Applies the ethics veto **in code**.
5. The **Chair** decides full / reduced / reject for ethically clean companies.
6. A deterministic optimiser allocates the $100k with exact dollars and share counts.
7. Every accept and reject comes with a cited, code-verified reason.
8. Live moment: a judge adds a rule out loud and the portfolio rebuilds.

---

## 2. Non-negotiable design rules

1. **No number used in allocation comes from an LLM.** LLMs output verdicts, categories and cited reasons. Code computes every statistic, cap, weight, dollar amount and share count.
2. **Ethics is never up for a vote.** A *verified* Melchior FAIL on any rule rejects the company in code. It never reaches the Chair.
3. **Every claim is verified in code.**
   - Quotes must appear in the cited source chunk (case- and whitespace-normalised substring match).
   - Cited metrics must exist in the computed data with a matching value (within 2%).
   - Cited source IDs must exist.
   - An unverified FAIL is downgraded to FLAG. Other unverified reasons are kept but shown greyed out as "unverified" and are not passed to the Chair.
4. **FLAG means trustee review.** Flagged companies are excluded from the portfolio by default and shown on the trustee review list.
5. **The Chair outputs a category, not a number.** Code maps `full -> 0.10`, `reduced -> 0.05`, `reject -> 0.0` max weight.
6. **Assumptions are labelled.** Any limit not stated in the policy uses the config default and shows an "assumed" badge in the UI. The financial health vs risk weighting is fixed at 50/50 in config and labelled as assumed.

---

## 3. Hackathon constraints

- **Models:** only the ones provided through Azure OpenAI: GPT 6.1 Sol, GPT 6 Astra, GPT 6 Terra, GPT 5.6 Terra, MAI Thinking 1, Text Embedding 3 Large. Deployment names come from `.env`.
- **Data:** public sources only.
- **Budget:** $100,000 (USD).
- **Pitch:** 8 minutes plus 2 minutes Q&A, with a live demo.
- **The endpoint is shared with every team.** Expect 429s. Max 8 concurrent LLM calls, exponential backoff, cache everything.
- **UI footer must show:** "Educational hackathon project. Not financial advice. Not affiliated with any charity named."

---

## 4. Scope

### MVP (must work by 14:30)

- One client: **Cancer Research Wales** (policy text in `policies/cancer_research_wales.md`)
- Data: EDGAR (10-K and 20-F only), Finnhub company news, yfinance (prices, fundamentals, dividends), embeddings
- Universe: the 32 equities and 4 bond ETFs in section 8.1
- All five agents (compiler/Chair, Melchior, Balthasar, Casper, memo)
- Ethics veto, caps, optimiser, backtest stats
- Streamlit app (section 13)
- Live rule change (section 12)

### Stretch (only after the MVP runs end to end, in this order)

1. Extra client policies: British Thoracic Society, British Red Cross, Nuffield Oxford Hospitals Fund (the no-policy case). These are new files in `policies/` only. No new code paths.
2. Memo number check (every number in the memo must appear in the portfolio JSON).
3. Model bake-off table shown in the app's "About" expander.

### Out of scope (do NOT build)

Guardian news, EPA records, FDA records, 8-K filings, Twelve Data, FRED, databases, user accounts, auth, cloud deployment, PDF export, a React frontend.

---

## 5. Stack

Python 3.11+. `requirements.txt`:

```
openai
python-dotenv
streamlit
plotly
pandas
numpy
yfinance
requests
beautifulsoup4
lxml
pyportfolioopt
tenacity
```

No other dependencies without asking.

---

## 6. Repo layout

```
mandate/                  # repo root
  CLAUDE.md
  .env.example
  .gitignore              # must include .env and cache/
  requirements.txt
  app.py                  # Streamlit entry point
  mandate/
    __init__.py
    config.py             # models, limits, paths, flags
    universe.py           # tickers, groups, bond flags
    llm.py                # Azure client, JSON calls, cache, retry, semaphore
    sources/
      market.py           # yfinance prices, fundamentals, dividends, risk stats
      edgar.py            # 10-K / 20-F fetch + section extraction
      news.py             # Finnhub company news
    evidence.py           # chunking, embeddings, retrieval, source IDs
    agents/
      compiler.py         # Chair: policy -> rules
      melchior.py         # ethics
      balthasar.py        # financial health
      casper.py           # risk
      chair.py            # final decision for clean companies
      memo.py             # trustee memo
    verify.py             # quote / metric / source checks
    decide.py             # veto, FLAG handling, caps
    optimise.py           # PyPortfolioOpt + backtest
    pipeline.py           # runs everything, writes results/run.json
    live_rule.py          # add-a-rule path
  policies/
    cancer_research_wales.md
    demo_fallback.md
  scripts/
    test_models.py
    fetch_data.py         # pulls and caches all data
    precache_rules.py     # pre-runs likely live rules
  cache/                  # gitignored: raw data, embeddings, LLM responses
  results/                # run.json and live-rule runs
```

---

## 7. Config and environment

### `.env.example`

```
AZURE_OPENAI_ENDPOINT=
AZURE_OPENAI_API_KEY=
AZURE_OPENAI_API_VERSION=

# Exact deployment names from the portal dropdown
DEPLOY_SOL=
DEPLOY_ASTRA=
DEPLOY_TERRA_6=
DEPLOY_TERRA_56=
DEPLOY_MAI=
DEPLOY_EMBED=

FINNHUB_API_KEY=
EDGAR_USER_AGENT=Mandate Hackathon your.email@example.com

DEMO_MODE=0
```

If the organisers gave a base URL ending in `/openai/v1/`, use `OpenAI(base_url=..., api_key=...)` instead of `AzureOpenAI` and ignore the API version. Support both in `llm.py` with a simple check.

### `config.py`

```python
MODELS = {
    "chair":     DEPLOY_SOL,       # policy compiler + final decision
    "melchior":  DEPLOY_SOL,       # ethics
    "balthasar": DEPLOY_MAI,       # financial health (reasoning model)
    "casper":    DEPLOY_TERRA_6,   # risk
    "memo":      DEPLOY_SOL,
    "fast":      DEPLOY_TERRA_56,  # live rule re-screen
    "backup":    DEPLOY_ASTRA,     # swap in if any model is down
    "embed":     DEPLOY_EMBED,
}
REASONING_MODELS = {DEPLOY_MAI}    # no temperature, use max_completion_tokens

BUDGET_USD = 100_000
CAP_BY_DECISION = {"full": 0.10, "reduced": 0.05, "reject": 0.0}
BOND_MAX_WEIGHT = 0.25             # per bond ETF, bonds skip the ethics screen

DEFAULT_LIMITS = {                 # used when the policy doesn't say; shown as "assumed"
    "min_bonds": 0.30,
    "income_target": 0.025,        # portfolio trailing dividend yield
    "worst_year_limit": -0.15,     # worst rolling 12-month return
}
SCORE_WEIGHTS = {"financial_health": 0.5, "risk": 0.5}   # assumed, trustees to confirm

PRICE_YEARS = 3
NEWS_DAYS = 180
TOP_K_PER_RULE = 4
MAX_CONCURRENCY = 8
LIVE_RULE_TIMEOUT_S = 25
```

---

## 8. Data layer

### 8.1 Universe (`universe.py`)

Groups exist for the demo story only. The pipeline treats all equities identically.

| Group | Tickers | Purpose in the demo |
| --- | --- | --- |
| Likely fails | XOM, CVX, BP*, SHEL*, MO, PM, BTI*, LMT, RTX | Prove the basics work |
| Alcohol (live-rule bait) | BUD*, DEO*, STZ | Fail when the judge adds "no alcohol" |
| Grey zone | MMM, DD, CC, DOW, KO, PEP, DUK, JNJ | Where the evidence and the agents shine |
| Likely passes | XYL, ECL, AWK, ABT, TMO, DHR, MSFT, AAPL, COST, PG, ISRG, V | Fill the portfolio |
| Bond ETFs (no ethics screen) | SHY, IEF, BND, TIP | Bond sleeve, max 25% each |
| Benchmarks (not investable) | SPY, BND | 60/40 comparison and beta |

`*` = files a 20-F instead of a 10-K.

Feasibility: equity caps + bond caps must sum to at least 1.0. With 4 bonds at 25% this always holds, but check it anyway before optimising (section 11).

### 8.2 `sources/market.py` (yfinance)

- `fetch_prices(tickers) -> DataFrame`: 3 years of daily close prices (auto-adjusted). Save to `cache/prices.csv`.
- `trailing_yield(ticker) -> float`: sum of dividends over the last 365 days divided by the last price. Compute it from `Ticker.dividends`. Do NOT trust `info["dividendYield"]` (its units have changed between versions).
- `fundamentals(ticker) -> dict`: from `Ticker.info`, keep only these keys (None if missing): `profitMargins`, `operatingMargins`, `returnOnEquity`, `debtToEquity`, `currentRatio`, `revenueGrowth`, `freeCashflow`, `marketCap`, `sector`, `longBusinessSummary`. Save to `cache/fundamentals.json`.
- `risk_stats(prices) -> dict per ticker`, computed in code:
  - `annual_vol`: std of daily returns × sqrt(252)
  - `max_drawdown`
  - `worst_12m_return`: minimum rolling 252-day return
  - `beta_vs_spy`
  
  Save to `cache/risk_stats.json`.

### 8.3 `sources/edgar.py`

- Every request sends the header `User-Agent: {EDGAR_USER_AGENT}`. Sleep 0.15 s between requests (SEC limit is 10/s).
- Ticker to CIK: `https://www.sec.gov/files/company_tickers.json`
- Filing list: `https://data.sec.gov/submissions/CIK{cik:010d}.json`. In `filings.recent`, take the latest `form` of `10-K` or `20-F`.
- Document URL: `https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession_without_dashes}/{primaryDocument}`
- Parse with BeautifulSoup (`lxml`), `get_text(" ")`, collapse whitespace.
- Section extraction (best effort):
  - 10-K: Item 1 (Business), Item 1A (Risk Factors), Item 3 (Legal Proceedings)
  - 20-F: Item 3.D (Risk Factors), Item 4 (Information on the Company), Item 8.A.7 (Legal Proceedings)
  - The table of contents repeats these headings, so take the match followed by the most text before the next "Item" heading.
- **Fallback (use it if extraction isn't working within 15 minutes):** skip sections, take the first 400,000 characters of the whole document, and tag `section = "full"`. Embeddings will find the relevant parts anyway.
- Save raw text to `cache/edgar/{ticker}.json` as `{"form", "filing_date", "url", "sections": {name: text}}`.

### 8.4 `sources/news.py` (Finnhub)

- `GET https://finnhub.io/api/v1/company-news?symbol={T}&from={YYYY-MM-DD}&to={YYYY-MM-DD}&token={KEY}` for the last 180 days.
- Keep `headline`, `summary`, `url`, `datetime`, `source`. Maximum 40 articles per ticker, newest first.
- Free tier allows 60 calls per minute, so sleep 1.1 s between tickers.
- Save to `cache/news/{ticker}.json`.

### 8.5 `evidence.py`

- Chunk filing sections into ~1,500 characters with 200 overlap. Each news item (headline + summary) is one chunk. Cap at 250 filing chunks per ticker.
- Chunk schema:
  ```json
  {"source_id": "MMM-10K-c0042", "ticker": "MMM", "kind": "filing|news",
   "section": "Legal Proceedings", "url": "...", "date": "2026-02-10", "text": "..."}
  ```
  Source ID format: `{TICKER}-{10K|20F}-c{0000}` for filings and `{TICKER}-NEWS-{000}` for news.
- Embed chunks in batches of 64 with the embedding deployment. Save vectors as `cache/emb/{ticker}.npy` and metadata as `cache/emb/{ticker}.json`.
- `retrieve(ticker, rule) -> list[chunk]`: embed `rule.text + " " + " ".join(rule.keywords)` (cache it), take the cosine top-4, plus up to 2 chunks with keyword hits not already included. Deduplicate.
- `get_chunk(source_id) -> chunk`: used by `verify.py`.

---

## 9. Agents

### 9.1 `llm.py`

`call_json(role: str, system: str, user: str, max_tokens=2000) -> dict`

- Model = `MODELS[role]`.
- Cache key = sha256 of (deployment, system, user). The cache lives in `cache/llm/{key}.json`. On a hit, return it with no call.
- In `DEMO_MODE`, a cache miss raises an error (except on the live-rule path, which may call live).
- Request `response_format={"type": "json_object"}`. If the model rejects it, retry without and extract the first `{...}` block from the text.
- For `REASONING_MODELS`: no `temperature`, use `max_completion_tokens`. Others: `temperature=0`, `max_tokens`.
- Use `tenacity` retry: 4 attempts, exponential backoff starting at 2 s, on 429 / 5xx / timeout.
- A global `asyncio.Semaphore(MAX_CONCURRENCY)` wraps an async version `acall_json`. Use `asyncio.gather` for per-company fan-out.
- Log every call to `cache/llm_log.jsonl` with role, deployment, latency, prompt and completion tokens, and cache hit or miss. The pitch needs real numbers for run time and cost.
- If a deployment fails 4 times, retry once with `MODELS["backup"]` and record that in the log.

### 9.2 Policy compiler (Chair, `agents/compiler.py`)

**Input:** policy text and the charity's stated purpose (first lines of the policy file).

**System prompt:**

```
You turn a UK charity's investment policy into machine-checkable rules.
Return ONLY JSON with this shape:
{
 "charity": str,
 "purpose_summary": str,
 "rules": [{"id": "R1", "clause_ref": str, "type": "hard_exclusion|mission_conflict|preference",
            "text": str, "threshold": str|null, "keywords": [str], "source_quote": str}],
 "proposed_mission_conflicts": [{"id": "M1", "text": str, "keywords": [str], "reasoning": str}],
 "vague_wording": [{"quote": str, "issue": str, "assumption_used": str}],
 "stated_limits": {"min_bonds": float|null, "income_target": float|null,
                   "worst_year_limit": float|null, "max_single_holding": float|null}
}
Rules:
- Every rule must include source_quote copied word for word from the policy.
- Never invent a rule the policy does not state. Ideas from the charity's purpose go in
  proposed_mission_conflicts, never in rules.
- A limit the policy does not state is null. Do not guess numbers.
- If the policy is empty or missing, return no rules and propose mission conflicts from the purpose only.
```

**Code after the call:**
- Verify every `source_quote` against the policy text. Drop rules that fail and show them as "unverified rule".
- Merge limits: a stated value wins, otherwise use `DEFAULT_LIMITS` and mark it `assumed=True`.
- Proposed mission conflicts are pre-approved for the demo (`approved=True`) but shown with an approve checkbox in the UI. Approved ones become rules with `type = mission_conflict` and IDs `M1`, `M2` and so on.

### 9.3 Melchior: ethics (`agents/melchior.py`, model: Sol)

One call per company covering all rules. Evidence = `retrieve(ticker, rule)` for each rule, grouped by rule.

**System prompt:**

```
You are Melchior, the ethics specialist on a charity's investment committee.
Check ONE company against EACH rule using ONLY the evidence given.
Return ONLY JSON:
{"ticker": str,
 "verdicts": [{"rule_id": str, "verdict": "PASS|FAIL|FLAG", "confidence": float,
               "quote": str|null, "source_id": str|null, "reason": str}]}
Rules:
- FAIL requires a quote copied word for word from one evidence chunk, plus its source_id.
- If the evidence is ambiguous or insufficient to decide, answer FLAG and explain what is missing.
- PASS means nothing in the evidence breaches the rule. quote may be null.
- reason: one plain sentence a volunteer trustee would understand.
- Do not use outside knowledge.
```

**User message:** the company name, ticker and business summary, then for each rule: `[R1] rule text`, followed by its chunks formatted as `<chunk id="MMM-10K-c0042">text</chunk>`.

### 9.4 Balthasar: financial health (`agents/balthasar.py`, model: MAI Thinking 1)

Runs only for companies with no verified FAIL.

**System prompt:**

```
You are Balthasar, the financial health specialist on a charity's investment committee.
Judge the company's financial health from the metrics given. Use no outside knowledge.
Return ONLY JSON:
{"ticker": str, "score": int (0-10, 10 = strongest),
 "reasons": [{"text": str, "metric": str, "value": number}]}
Every reason must cite exactly one metric key from the data and its value as given.
Give 2 to 4 reasons. If key metrics are missing, say so in a reason with metric "missing" and value 0,
and keep the score near 5.
```

**User message:** the fundamentals dict as JSON (`longBusinessSummary` removed).

**Verify:** each `metric` exists and `value` matches within 2%. Drop unverified reasons. If every reason fails verification, set score = None and tell the Chair the data is missing.

### 9.5 Casper: risk (`agents/casper.py`, model: GPT 6 Terra)

Runs only for companies with no verified FAIL.

**System prompt:**

```
You are Casper, the risk specialist on a charity's investment committee.
You are given risk statistics computed by code and a few risk-related evidence chunks.
Interpret them. Do not compute new numbers.
Return ONLY JSON:
{"ticker": str, "score": int (0-10, 10 = lowest risk),
 "reasons": [{"text": str, "metric": str|null, "value": number|null, "source_id": str|null}]}
Each reason cites either one stat key and its exact value, or one source_id. Give 2 to 4 reasons.
```

**User message:** `risk_stats[ticker]` as JSON plus the top 4 chunks retrieved for the query "legal, regulatory and litigation risk".

**Verify:** stat values must match within 2%, and source_ids must exist. Drop the reasons that fail.

### 9.6 Chair: final decision (`agents/chair.py`, model: Sol)

Runs only for ethically clean companies (all verdicts PASS after verification).

**System prompt:**

```
You are the Chair of a charity's investment committee. This company has already passed the ethics
screen; ethics is not your decision. Weigh financial health and risk equally (trustees' assumed 50/50 weighting).
Return ONLY JSON:
{"ticker": str, "decision": "full|reduced|reject",
 "reasons": [{"text": str, "source_ids": [str]}]}
- full: sound on both. reduced: acceptable but one notable weakness. reject: serious weakness.
- Cite source_ids or metric keys from the specialists' verified reasons only.
- 2 or 3 reasons, each one sentence for a volunteer trustee.
```

**User message:** Balthasar's and Casper's verified outputs (scores and reasons) plus the company name.

**Verify:** every cited ID exists among the verified reasons or chunks. Turn source IDs into links using the chunk URL. If the Chair call fails twice, the decision defaults to `reduced` with the reason "Chair unavailable, defaulted to reduced cap", flagged in the UI.

### 9.7 Memo (`agents/memo.py`, model: Sol)

**System prompt:**

```
Write a one-page memo for the volunteer trustees of {charity}. They are not finance experts.
Use ONLY numbers that appear in this JSON. Cite the policy as [Clause X] and evidence as [source_id].
Order: the recommendation in one sentence; three reasons; what we rejected and why (top 5);
items needing trustee review; assumptions we made; the main risks; what would change our mind.
Under 450 words. Plain English. No hype.
```

**User message:** a portfolio JSON with holdings, rejections, flags, limits (with assumed flags) and risk cards.

---

## 10. Decision logic (`decide.py`, pure code)

```
for each equity:
    v = melchior verdicts after verify()
    if any(verdict == FAIL and verified):        status = REJECTED_ETHICS   # veto, never reaches Chair
    elif any(verdict == FLAG):                   status = TRUSTEE_REVIEW    # excluded by default
    else:
        run balthasar + casper + chair
        cap = CAP_BY_DECISION[chair.decision]
        status = APPROVED if cap > 0 else REJECTED_CHAIR
bonds: status = APPROVED, cap = BOND_MAX_WEIGHT, no agents run
```

`verify()` turns an unverified FAIL into a FLAG with reason "evidence quote could not be verified".

The output per company: `status`, `cap`, every agent output (verified and unverified reasons kept separately), source links.

---

## 11. Optimiser (`optimise.py`)

```python
from pypfopt import EfficientFrontier, risk_models, DiscreteAllocation

tickers = approved equities + bond ETFs
S = risk_models.CovarianceShrinkage(prices[tickers]).ledoit_wolf()
bounds = [(0, cap[t]) for t in tickers]
assert sum(cap.values()) >= 1.0          # else: show "not enough approved holdings" in the UI
ef = EfficientFrontier(None, S, weight_bounds=bounds)
ef.add_constraint(lambda w: w @ is_bond >= limits["min_bonds"])
ef.add_constraint(lambda w: w @ yields >= limits["income_target"])
weights = ef.min_volatility()
weights = ef.clean_weights()
alloc, leftover = DiscreteAllocation(weights, latest_prices, total_portfolio_value=BUDGET_USD).greedy_portfolio()
```

**Relaxation chain if infeasible** (record each step and show it in the UI as "constraint relaxed"):

1. Drop the income constraint.
2. Raise `BOND_MAX_WEIGHT` to 0.35.
3. Give up: show the error clearly. Never silently ignore min_bonds or the caps.

**Backtest** (code only): daily portfolio returns from the final weights. Report:
- `worst_12m_return` vs `worst_year_limit`
- `max_drawdown`
- `annual_vol`
- `trailing_yield` vs `income_target`
- total return vs 60/40 SPY/BND over the same window

Label it "past performance, not a forecast".

---

## 12. Live rule (`live_rule.py`)

Goal: under ~25 seconds from typing to the rebuilt portfolio.

1. The user types a rule in plain English.
2. Turn it into ONE rule with the compiler prompt run on that sentence only (`fast` model). Give it a new ID, `L1`, `L2` and so on.
3. Re-run Melchior on **that one rule only** across currently APPROVED equities, using the `fast` model. Use the same verification.
4. Newly FAILed companies drop out. Nothing else re-runs: the Chair decisions and caps of the others are reused.
5. Re-run the optimiser and backtest.
6. Show a "What changed" panel: removed tickers with their quotes, and the old vs new allocation.

Cache key = (normalised rule text, ticker). `scripts/precache_rules.py` pre-runs these:
- "No alcohol producers."
- "No gambling companies."
- "No companies that test cosmetics on animals."
- "No companies fined for data privacy breaches in the last 3 years."

Timeout: any company not finished by `LIVE_RULE_TIMEOUT_S` becomes FLAG ("not checked in time") and drops out. The demo never hangs.

---

## 13. Streamlit app (`app.py`)

`st.set_page_config(layout="wide")`. Load `results/run.json`. The app never runs the full pipeline itself; only the live rule calls the API.

**Sidebar**
- Client selector: lists files in `policies/`, defaulting to Cancer Research Wales.
- Policy text (read-only expander).
- "Add a rule" text input and button.
- Footer disclaimer.

**Main page, top to bottom**

1. **Headline:** "Invest $100,000 across N holdings: X% shares, Y% bonds, $Z cash left over." The numbers come from the optimiser output.
2. **Policy as rules:** a card per rule with the clause ref, type badge and verified tick. Vague-wording warnings. Proposed mission conflicts with approve checkboxes. Every limit with an "assumed" badge where applicable.
3. **MAGI board:** one row per company with the columns Melchior verdict badge, Balthasar score, Casper score, Chair decision, cap and status. Click a row (expander) to see each agent's reasons: green tick if verified, grey if unverified, and source links.
4. **Portfolio:** Plotly donut by holding, coloured by sector or bond. Holdings table: ticker, dollars, shares, cap, Chair decision, one-line reason with sources.
5. **Why we rejected:** ticker, rule or Chair, quote, link. Sort ethics vetoes first.
6. **Trustee review list:** FLAGs, 2-model disagreements, relaxed constraints, assumed limits.
7. **Risk cards:** worst 12-month return vs limit, yield vs target, vs 60/40. Green inside the limit, amber outside.
8. **Trustee memo** (markdown).
9. **"About this run" expander:** wall time, LLM calls, tokens, cache hits, which model ran each agent.

The live rule result shows the "What changed" panel above the headline, highlighted.

Browser zoom will be 125 to 150% on the projector, so keep it readable: no tiny fonts, no more than 6 table columns.

---

## 14. Build phases (do them in order)

Times are targets. If a phase overruns by 15 minutes, use its fallback.

### Phase 0: setup (12:00 to 12:15)
- Repo skeleton, `requirements.txt`, `.env.example`, `.gitignore`, `config.py`, `llm.py`.
- `scripts/test_models.py`: one "Reply with just: OK" call per deployment and one embedding call. Print PASS/FAIL with the error.
- **Check:** all 6 deployments PASS. Fallback: map a failing role to `backup` in config.

### Phase 1: data (12:15 to 12:50)
- `market.py`, `news.py`, `edgar.py`, `evidence.py`, and `scripts/fetch_data.py` to run them all.
- **Check:** `cache/` holds prices for all tickers, fundamentals, risk stats, news for most tickers, and filings plus embeddings for at least 28 of 32 equities. Print a coverage table.
- **Fallback:** EDGAR sections to whole-doc mode (8.3). A ticker with no filing still runs on news alone.

### Phase 2: agents + decisions (12:15 to 12:50, in parallel with Phase 1 using 3 cached tickers: MO, MMM, XYL)
- `compiler.py`, `melchior.py`, `balthasar.py`, `casper.py`, `chair.py`, `verify.py`, `decide.py`.
- **Check:** MO is REJECTED_ETHICS with a verified quote. XYL reaches the Chair. A deliberately fake quote gets downgraded to FLAG.

### Phase 3: optimiser (12:30 to 12:50)
- `optimise.py` with the relaxation chain and backtest.
- **Check:** with a dummy approved list of 10 equities, it returns share counts summing to under $100,000 and every constraint holds.

### Phase 4: end to end (12:50 to 13:15)
- `pipeline.py` runs everything and writes `results/run.json`.
- A bare Streamlit page shows the headline, holdings table and rejections.
- **Check:** the full run completes, a second run is fully cached and finishes in under 10 seconds, and `DEMO_MODE=1` works.

### Phase 5: demo quality (13:15 to 14:30)
In priority order. Stop wherever 14:30 lands.
1. Live rule (section 12) and `precache_rules.py`.
2. Full app layout (section 13): MAGI board, verified ticks, rejection table, risk cards.
3. Memo.
4. "About this run" metrics.
5. Stretch items from section 4.

### 14:30: FREEZE
After this, bug fixes only. No new features, no refactors, no dependency changes.

---

## 15. Pre-demo checklist (14:30 to 16:00)

- [ ] `DEMO_MODE=1` full app run with the Wi-Fi off
- [ ] All 4 pre-cached live rules return in under 5 seconds
- [ ] An unexpected live rule still finishes inside the timeout
- [ ] Footer disclaimer visible
- [ ] `results/run.json` committed as a known-good snapshot (copy it to `results/run_backup.json`)
- [ ] Screen recording of the full demo saved locally
- [ ] Real numbers noted from "About this run": wall time, LLM calls, tokens
- [ ] Tested on the presenting laptop with the room's screen

---

## 16. If things break during the demo

- The API is down or slow: the app still runs entirely from cache. Only the live rule needs the network, and it falls back to the pre-cached rules.
- A live rule hangs: the timeout turns unchecked companies into FLAGs. Say: "Anything the committee can't verify in time goes to the trustees rather than into the portfolio." That's a feature.
- The app crashes: switch to the screen recording and keep talking.
