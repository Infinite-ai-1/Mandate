# Mandate: shared project contract

## What we're building
An AI analyst for UK charities (Microsoft x LSEG Hackathon 2026). A charity pastes its
ethics policy; the tool recommends how to invest $100,000 and explains every decision
with verified citations. Educational hackathon project. Not financial advice.

Demo charities (policy text in policies/*.txt):
- cancer_research_wales (lead story: no tobacco, non-negotiable)
- british_thoracic_society (no tobacco, fracking or arms trade; lung health mission)
- british_red_cross (humanitarian; Fundamental Principles incl. neutrality)
- nuffield_oxford_hospitals_fund (no published ethics policy: rules proposed from purpose)

## Pipeline
1. Policy compiler (LLM) -> rules JSON
2. Evidence: filings, news, regulator records, prices -> chunks with source IDs
3. Melchior (ethics), Balthasar (financial health), Casper (risk): three different models
4. Code: verify every quote/citation, then ethics veto (verified FAIL = reject, FLAG = trustee review)
5. Chair (LLM): weighs financial + risk for ethics-clean companies using policy weights
6. Optimiser (code, no LLM): $100k -> exact dollars and share counts
7. Streamlit app shows results; judge can add a rule live

## Hard rules
- No number shown to the user may come from an LLM. Numbers come from data or code.
- Every claim an agent makes cites source_ids. Code verifies them. Unverified = flagged.
- An LLM can never approve a company that has a verified ethics FAIL. This is an `if` in code.
- All LLM calls: JSON output, validated with pydantic, cached to disk by hash of (model, prompt).
- All API responses cached to data/cache/. DEMO_MODE=1 means read cache only, no network.
- Secrets only in .env (gitignored). Never hardcode keys. Never commit .env.
- Only edit files in your own area unless the team agrees. Shared files: config.py, schemas.py, llm.py.

## Repo layout
config.py            env vars, model deployment names, DEMO_MODE, paths
schemas.py           pydantic models for everything below (single source of truth)
llm.py               AzureOpenAI client: chat_json(), embed(), disk cache, retries
universe.py          ticker list + bond ETFs
policies/*.txt       charity policies, verbatim
ingest/              Person 1: edgar.py finnhub.py guardian.py gdelt.py epa.py fda.py prices.py fred.py fx.py
evidence.py          Person 1: chunking, embeddings, rank_evidence()
sources.py           Person 1: source registry read/write
agents/              Person 2: compiler.py melchior.py balthasar.py casper.py chair.py memo.py
verify.py            Person 2: quote + citation verification, ethics veto
pipeline.py          Person 2: run_charity(charity_id) end to end
quant/               Person 3: stats.py optimiser.py backtest.py
app.py               Person 3: Streamlit UI
data/cache/          raw API + LLM cache (gitignored)
data/processed/      outputs the app reads (committed for demo)
stubs/               fake data in schema format so everyone can work in parallel

## Schemas (implement in schemas.py)

Source (registry entry, data/processed/sources.json keyed by source_id):
{"source_id": "S-XOM-0012", "ticker": "XOM", "kind": "filing|news|regulator|market|computed",
 "origin": "edgar_10k|edgar_8k|edgar_20f|edgar_6k|finnhub|guardian|gdelt|epa|fda|yfinance|twelvedata|fred|quant",
 "title": "...", "date": "YYYY-MM-DD", "url": "...", "section": "Item 3 Legal Proceedings"}

Chunk (data/processed/chunks/{ticker}.json is a list of these):
{"source_id": "...", "ticker": "...", "text": "...", "date": "YYYY-MM-DD"}

Metric (fundamentals and risk stats both use this):
{"name": "debt_to_equity", "value": 0.42, "unit": "ratio", "as_of": "YYYY-MM-DD", "source_id": "..."}
data/processed/fundamentals/{ticker}.json -> {"ticker": "...", "metrics": [Metric, ...]}
data/processed/risk/{ticker}.json         -> {"ticker": "...", "metrics": [Metric, ...]}

Rules (data/processed/rules/{charity_id}.json):
{"charity_id": "...", "purpose": "...",
 "rules": [{"id": "R1", "clause": "2", "text": "...", "test": "...", "threshold": "...",
            "keywords": ["..."], "origin": "policy|proposed|assumed", "approved": true}],
 "constraints": {"max_weight": 0.10, "min_bonds": 0.30, "min_yield": 0.03, "max_drawdown": -0.15},
 "constraint_origin": {"max_weight": "policy|assumed", "...": "..."},
 "weights": {"financial": 0.4, "risk": 0.6}, "weights_reason": "...",
 "questions": ["vague wording the trustees should clarify"]}

EthicsOutput (Melchior):
{"ticker": "...", "agent": "melchior", "model": "...",
 "verdicts": [{"rule_id": "R1", "verdict": "PASS|FAIL|FLAG", "confidence": 0.0,
               "quote": "verbatim from a chunk", "source_id": "...", "reason": "one plain sentence",
               "verified": null}]}

ScoreOutput (Balthasar and Casper):
{"ticker": "...", "agent": "balthasar|casper", "model": "...", "score": 0,
 "reasons": [{"claim": "...", "source_ids": ["..."], "verified": null}], "summary": "..."}

Decision:
{"ticker": "...", "decision": "APPROVE|APPROVE_CAPPED|REJECT|TRUSTEE_REVIEW",
 "cap": 0.10, "decided_by": "code_veto|chair", "reason": "...", "source_ids": ["..."]}

Portfolio (data/processed/portfolio/{charity_id}.json):
{"charity_id": "...", "total_usd": 100000, "gbpusd": 0.0, "as_of": "YYYY-MM-DD",
 "holdings": [{"ticker": "...", "name": "...", "is_bond": false, "usd": 0.0, "shares": 0,
               "price": 0.0, "weight": 0.0, "cap": 0.10, "reason": "...", "source_ids": ["..."]}],
 "cash_usd": 0.0,
 "risk": {"worst_12m": 0.0, "yield": 0.0, "volatility": 0.0, "vs_6040_return": 0.0},
 "checks": {"max_drawdown_ok": true, "yield_ok": true, "bonds_ok": true},
 "rejected": [Decision], "trustee_review": [Decision],
 "run_stats": {"seconds": 0.0, "llm_calls": 0, "tokens": 0}}

## Models (deployment names from .env, confirm in the hackathon portal)
MODEL_MELCHIOR (GPT 6.1 Sol: gpt-6.1-sol), MODEL_BALTHASAR (MAI Thinking 1),
MODEL_CASPER (GPT 6 Terra), MODEL_CHAIR (GPT 6.1 Sol), MODEL_EMBED (text-embedding-3-large)
Client: AzureOpenAI, api_version 2024-12-01-preview, endpoint and key from .env.
Reasoning models may reject temperature or JSON mode: llm.py must handle per-model params.
