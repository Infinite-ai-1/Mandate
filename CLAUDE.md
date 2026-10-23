# Mandate: shared project contract

## What we're building
An AI analyst for UK charities (Microsoft x LSEG Hackathon 2026). A charity pastes its ethics
policy; the tool recommends how to invest $100,000 and explains every accept and reject with
verified citations. Educational hackathon project. Not financial advice.

Demo charities (text in policies/*.txt):
- cancer_research_wales: lead story, no tobacco (non-negotiable)
- british_thoracic_society: no tobacco, fracking or arms trade; lung health mission
- british_red_cross: humanitarian; Fundamental Principles incl. neutrality
- nuffield_oxford_hospitals_fund: no published ethics policy, rules proposed from its purpose

## Pipeline
1. Compiler (LLM): policy -> Rules (numbered rules, proposed mission conflicts, assumed limits,
   trustee questions, weights, screening hints)
2. Universe funnel (code): ~550 companies -> SIC pre-filter -> selector picks ~40 per charity
3. Data (code): live fetch from EDGAR, Finnhub, Guardian, GDELT, EPA ECHO, openFDA, yfinance,
   Twelve Data, FRED; cached with source IDs
4. Melchior (ethics, GPT 6.1 Sol), Balthasar (financial health, MAI Thinking 1),
   Casper (risk, Claude Sonnet 5.5)
5. Code: verify every quote and citation, then ethics veto (verified FAIL = reject, FLAG = trustee review)
6. Chair (LLM, GPT 6.1 Sol): weighs financial + risk for ethics-clean companies using policy weights
7. Optimiser (code, no LLM): $100k -> exact dollars and share counts
8. Flask API + React frontend; judge can add a rule live; per-company evidence refresh

The app's LLM agents never browse the web. They only read evidence our data code fetched,
so every quote can be verified against stored text.

## Hard rules
- No number shown to the user may come from an LLM. Numbers come from data or code.
- Every agent claim cites source_ids. Code verifies them. Unverified = flagged, never trusted.
- An LLM can never approve a company with a verified ethics FAIL. This is an `if` in code.
- LLM calls: JSON output validated with pydantic, cached on disk by hash(provider, model, prompt).
- API responses cached in data/cache/. DEMO_MODE=1 = cache only, zero network.
- Secrets only in .env (gitignored). Never hardcode keys. Never commit .env. Check `git status`.
- Only edit your own area. Shared files (config.py, schemas.py, llm.py) change only by agreement.
- Merge to main at least hourly. Never leave main broken for more than 15 minutes.

## Stack
Python 3.11, Flask + flask-cors, openai SDK (AzureOpenAI), anthropic SDK, pydantic, edgartools,
yfinance, PyPortfolioOpt, rapidfuzz, pandas. Frontend: React + Vite + TypeScript, Tailwind, Recharts.
Dev: Flask :5000, Vite :5173 proxying /api to :5000. Demo: Flask serves the built frontend.

## Repo layout
config.py              env vars, model names, DEMO_MODE, paths            (Person 2)
schemas.py             pydantic models, single source of truth            (Person 2)
llm.py                 chat_json() for Azure + Anthropic, embed(), cache  (Person 2)
policies/*.txt         charity policies verbatim
universe.py            full universe with SIC codes, always_include list (Person 1)
ingest/                edgar finnhub guardian gdelt epa fda prices fx fred run_all refresh (Person 1)
evidence.py            chunking, embeddings, rank_evidence()              (Person 1)
sources.py             source registry                                    (Person 1)
agents/                compiler selector melchior balthasar casper chair memo devils_advocate, prompts/ (Person 2)
verify.py              quote + citation checks, ethics veto               (Person 2)
pipeline.py            run_charity()                                      (Person 2)
api.py                 Flask API                                          (Person 2)
quant/                 stats optimiser backtest                           (Person 3)
frontend/              React app                                          (Person 3)
stubs/                 fake data in schema format for parallel work
data/cache/            raw API + LLM cache (gitignored)
data/processed/        outputs the API reads (committed for the demo)

## Schemas (implement in schemas.py)

Source (data/processed/sources.json, keyed by source_id):
{"source_id": "S-XOM-0012", "ticker": "XOM", "kind": "filing|news|regulator|market|computed",
 "origin": "edgar_10k|edgar_8k|edgar_20f|edgar_6k|edgar_xbrl|finnhub|guardian|gdelt|epa|fda|yfinance|twelvedata|fred|quant",
 "title": "...", "date": "YYYY-MM-DD", "url": "...", "section": "Item 3 Legal Proceedings"}

Company (universe): {"ticker": "...", "name": "...", "cik": "...", "sic": "2111",
 "sic_description": "...", "form": "10-K|20-F", "is_bond": false}

Chunk (data/processed/chunks/{ticker}.json = list): {"source_id": "...", "ticker": "...", "text": "...", "date": "YYYY-MM-DD"}

Metric: {"name": "debt_to_equity", "value": 0.42, "unit": "ratio", "as_of": "YYYY-MM-DD", "source_id": "..."}
data/processed/fundamentals/{ticker}.json and data/processed/risk/{ticker}.json -> {"ticker": "...", "metrics": [Metric]}

Rules (data/processed/rules/{charity_id}.json):
{"charity_id": "...", "name": "...", "purpose": "...",
 "rules": [{"id": "R1", "clause": "2", "text": "...", "test": "...", "threshold": "...",
            "keywords": ["..."], "origin": "policy|proposed|assumed|judge", "approved": true}],
 "constraints": {"max_weight": 0.10, "min_bonds": 0.30, "min_yield": 0.03, "max_drawdown": -0.15},
 "constraint_origin": {"max_weight": "policy|assumed", "min_bonds": "...", "min_yield": "...", "max_drawdown": "..."},
 "weights": {"financial": 0.4, "risk": 0.6}, "weights_reason": "...",
 "questions": ["..."],
 "screening_hints": {"exclude_sic": ["2111"], "prefer_sic": ["3561"]}}

Selection (data/processed/selection/{charity_id}.json):
{"charity_id": "...", "universe_size": 0, "after_prefilter": 0,
 "excluded_by_sic": [{"ticker": "...", "sic": "...", "rule_id": "..."}],
 "selected": [{"ticker": "...", "why": "preferred_sector|diversification|grey_zone|always_include"}]}

EthicsOutput: {"ticker": "...", "agent": "melchior", "model": "...",
 "verdicts": [{"rule_id": "R1", "verdict": "PASS|FAIL|FLAG", "confidence": 0.0,
               "quote": "verbatim from a chunk", "source_id": "...", "reason": "one plain sentence", "verified": null}]}

ScoreOutput: {"ticker": "...", "agent": "balthasar|casper", "model": "...", "score": 0,
 "reasons": [{"claim": "...", "source_ids": ["..."], "verified": null}], "summary": "..."}

Decision: {"ticker": "...", "decision": "APPROVE|APPROVE_CAPPED|REJECT|TRUSTEE_REVIEW",
 "cap": 0.10, "decided_by": "code_veto|prefilter|chair", "reason": "...", "source_ids": ["..."],
 "weighted_score": null}

Portfolio (data/processed/portfolio/{charity_id}.json):
{"charity_id": "...", "total_usd": 100000, "gbpusd": 0.0, "as_of": "YYYY-MM-DD",
 "holdings": [{"ticker": "...", "name": "...", "is_bond": false, "usd": 0.0, "shares": 0, "price": 0.0,
               "weight": 0.0, "cap": 0.10, "reason": "...", "source_ids": ["..."]}],
 "cash_usd": 0.0,
 "risk": {"worst_12m": 0.0, "yield": 0.0, "volatility": 0.0, "vs_6040_return": 0.0},
 "checks": {"max_drawdown_ok": true, "yield_ok": true, "bonds_ok": true},
 "relaxed": ["what the optimiser had to relax, if anything"],
 "rejected": [Decision], "trustee_review": [Decision],
 "memo": "...", "devils_advocate": ["...", "...", "..."],
 "run_stats": {"seconds": 0.0, "llm_calls": 0, "tokens": 0, "by_agent": {}}}

## API contract (JSON under /api)
GET  /api/health
GET  /api/charities                               -> [{charity_id, name, purpose}]
GET  /api/charities/<id>/policy                   -> {text}
GET  /api/charities/<id>/rules                    -> Rules
GET  /api/charities/<id>/selection                -> Selection
GET  /api/charities/<id>/portfolio                -> Portfolio
GET  /api/charities/<id>/companies/<ticker>       -> {melchior, balthasar, casper, decision}
GET  /api/sources/<source_id>                     -> Source
GET  /api/compare/<ticker>                        -> [{charity_id, decision}]
POST /api/charities/<id>/rules  body {rule_text}  -> {job_id}
POST /api/charities/<id>/run                      -> {job_id}   (full re-run)
POST /api/companies/<ticker>/refresh              -> {job_id}   (re-fetch news, re-run agents)
GET  /api/jobs/<job_id> -> {status: queued|running|done|error, progress: ["..."], result: Portfolio|null, error: null}
Errors: {"error": "message"} with a proper HTTP status.

## Models (.env)
Azure (AzureOpenAI client, api_version 2024-12-01-preview):
  MODEL_MELCHIOR=gpt-6.1-sol, MODEL_BALTHASAR=<MAI Thinking 1 deployment name from portal>,
  MODEL_CHAIR=gpt-6.1-sol, MODEL_EMBED=text-embedding-3-large
Anthropic (anthropic SDK): MODEL_CASPER=claude-sonnet-5-5
Reasoning models may reject temperature or JSON mode; llm.py handles per-model params.

## .env keys
AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY, AZURE_OPENAI_API_VERSION, ANTHROPIC_API_KEY,
MODEL_MELCHIOR, MODEL_BALTHASAR, MODEL_CASPER, MODEL_CHAIR, MODEL_EMBED,
FINNHUB_API_KEY, TWELVE_DATA_API_KEY, GUARDIAN_API_KEY, FRED_API_KEY, SEC_USER_AGENT, DEMO_MODE
