# Mandate

React + TypeScript frontend and Flask backend for UK charity investment research.
Published policy excerpts, real market data and verified evidence feed the analyst
pipeline. Allocations are **paper transactions**, never brokerage orders.
Educational hackathon project; not financial advice.

## Run

Use Python 3.11 or 3.12 and Node 20 or later.

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
Copy-Item .env.example .env
npm --prefix frontend ci
npm --prefix frontend run build
.venv\Scripts\python api.py
```

Open http://127.0.0.1:5000. On macOS/Linux use `.venv/bin/python`.
Waitress binds to loopback. This is a local, single-process workspace without
user authentication; do not expose it to the public internet.
For development run `npm --prefix frontend run dev` alongside Flask.

Fill `.env` with actual credentials; it is ignored by Git. Restart after changes.
Azure uses AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY and the API version.
MODEL_CHAIR and MODEL_MELCHIOR select Azure deployments. Balthasar uses
MODEL_BALTHASAR=mai-thinking-1. Casper uses Anthropic for a `claude-*` MODEL_CASPER
and requires ANTHROPIC_API_KEY; otherwise it uses Azure. DEPLOY_* aliases remain
supported. `/api/health` reports missing setting names, never values.

Prices use yfinance; news uses FINNHUB_API_KEY; SEC filings need a real contact in
SEC_USER_AGENT; GBP conversion uses TWELVE_DATA_API_KEY. Optional collectors
under ingest/ support the other keys in .env.example.

## Workflow

Choose a charity and review the supplied policy excerpts. Saving a policy
immediately invalidates its previous assessment. When credentials are missing,
the document still saves and the job explains what is needed. Re-run the mandate
or research a stock to start real analysis; jobs can take several minutes.

Verified ethics failures always veto an investment. Missing evidence, failed
Chair calls and unverified approvals require trustee review. Proposed mission
restrictions are not automatically adopted. Cancer Research Wales has no published
tobacco-exclusion clause in the supplied excerpts; the invented demo clause was
removed. Trustees may add restrictions explicitly in the Policy page.

Paper accounts start with an explicitly simulated $100,000 cash budget. Buy
requests enforce whole shares, available cash, position caps and current policy
revision. Retrying a request ID cannot allocate twice. Quotes require an observed
price no more than seven calendar days old. Existing positions remain visible
and are flagged when the policy changes. Holdings are recorded purchase costs,
not live brokerage valuations. The Stats page shows the optimiser's suggested
portfolio separately from the paper ledger.

## Integration and data

- mandate/: compiler, specialists, evidence verifier, decision gate and pipeline.
  mandate/web.py adapts internal models to the React API contract.
- ingest/, universe.py, sources.py: broader data collectors and the source registry.
  Committed data/processed files contain observed data. IDs and provenance are
  preserved by the evidence adapter.
- quant/: shared risk calculations and integer share-allocation repair used by
  the pipeline; schemas.py supplies its public contracts.
- frontend/: React app, served with JSON endpoints by Flask.
- policies/: published excerpts and source provenance, not fabricated policies.

The active research universe is the explicit 32-equity list in mandate/universe.py
plus four bond ETFs. The UI reports actual counts; it does not claim the planned
550-to-40 screening funnel ran. The broader ingestion universe is retained for
future selector work. Bond ETFs follow the inherited policy of skipping company
ethics checks, labelled in their decisions.

Raw responses and model caches live in cache/ and data/cache/. Accounts, saved
policy revisions and completed assessments live in results/workspace/. These
folders are ignored by Git. Jobs are process-local: restart an interrupted job
after a server restart; completed accounts and assessments remain on disk.
DEMO_MODE=1 permits cache reads only, including LLM calls. There is no fake data
server or synthetic fallback. Missing measurements are null or explicit errors.

The displayed specialist score is code-calculated verified-claim coverage, not
an LLM rating or probability of success. Verification checks cited quotations and
metric values, not the truth of every natural-language inference. Optimiser
constraint relaxations remain visible.

## Verify

```powershell
npm --prefix frontend run build
npm --prefix frontend test
.venv\Scripts\python -m unittest tests.test_integration quant.test_stats quant.test_portfolio -v
```

Tests use temporary accounts and controlled doubles only inside the test suite.
They cover policy persistence, stale revisions, idempotent paper transactions,
missing data, source resolution, ethics vetoes, cache-only mode, portfolio math,
React policy saving and Flask asset serving. Test recommendations are never
loaded by the application. Live checks require valid credentials and provider
access; offline tests alone do not establish external-service availability.

## Starred demo scenarios

Research stock includes four starred, scripted walkthroughs: XYL (Approved),
MSFT (Approved with a cap), PM (Rejected), MMM (Trustee review). The company names
are illustrative; scenario assumptions and outcomes are simulated, independent
of the selected charity's actual policy or current research. Each walks through
three specialists, a Chair decision and specific Devil's advocate challenges.
They make no model calls and never overwrite live issuer assessments. Choose them
in the normal research selector; they use the same agent cards, Chair results and
allocation form. Approved and capped scenarios can allocate from the paper pot
at explicitly simulated prices; their DEMO-* holdings appear in the allocation
table and pie. Rejected and review cases remain blocked. Policy edits invalidate
demo approvals just like live assessments.

The real portfolio's Devil's advocate is calculated from the actual assessment,
including evidence gaps, bond-screening exemptions, assumed limits, relaxations,
concentration and historical benchmark shortfall. It works for saved runs too.
