# stubs/ — fake data in the real schemas

Everything in here is **synthetic**: hand-written for this repo so `agents/`, `quant/` and
`frontend/` can be built before the real ingest lands. The numbers are plausible, not true. The
filing and news text is written for this repo — it is **not** a real filing or a real article, and
the `url` fields are illustrative. Nothing in `stubs/` is read by the real pipeline.

Shapes follow CLAUDE.md exactly, so swapping in the real loaders is an import change:

| stub call | real call |
|---|---|
| `stubs.load_universe()` | `universe.load_universe()` |
| `stubs.load_all()` / `stubs.get(sid)` | `sources.load_all()` / `sources.get(sid)` |
| `stubs.load_chunks(t)` | reads `data/processed/chunks/{t}.json` |
| `stubs.load_fundamentals(t)` / `load_risk(t)` | `data/processed/{fundamentals,risk}/{t}.json` |
| `stubs.load_prices()` | `data/processed/prices.parquet` |
| `stubs.rank_evidence(rules, t, k)` | `evidence.rank_evidence(rules, t, k)` |

`stubs/__init__.py` is stdlib-only, so it imports with no venv. `load_prices()` returns a pandas
DataFrame when pandas is installed and a plain dict of lists otherwise.

## Coverage

| ticker | company | chunks | fundamentals | risk | prices | the point |
|---|---|---|---|---|---|---|
| PM | Philip Morris International, SIC 2111 | 6 | yes | yes | yes | clear ethics **FAIL** on any tobacco rule; financially strong |
| MMM | 3M, SIC 3841 | 7 | yes | yes | yes | **grey zone**: PFAS/water litigation, an EPA violation, real settlements |
| XYL | Xylem, SIC 3561 | 5 | yes | yes | yes | clean **PASS**, mission-aligned on water |
| AGG | iShares Core US Aggregate Bond ETF | — | — | yes | yes | `is_bond: true`, for the `min_bonds` constraint |
| SPY | — | — | — | — | yes | benchmark column for the 60/40 comparison |

`prices.csv` is a seeded random walk (1,260 weekdays to 2026-10-22) whose drift and vol match
`risk/*.json`. The real file is `prices.parquet`; CSV is used here so the stubs need no pyarrow.

## Notes for whoever consumes these

- Every `Chunk` and every `Metric` carries a `source_id` that resolves in `sources.json`. That
  invariant is what `verify.py` depends on, so test against it: an agent quote must appear verbatim
  in some chunk's `text`.
- Chunks are 70–160 words. The real chunker targets 150–300, but a short news item is legitimately
  one short chunk, so handle both.
- Good things to test a verifier against: PM `S-PM-0001` says combustible cigarettes were "61.4% of
  our net revenues in 2025" (tobacco FAIL); MMM `S-MMM-0003` and `S-MMM-0006` are the grey-zone
  pollution evidence; XYL `S-XYL-0003` is an explicit "no material proceeding" statement.
- `rank_evidence()` here scores keyword overlap, not embeddings. Rankings will shift when the real
  one lands; don't hard-code an expected order in a test.

## Regenerating

The JSON and CSV are checked in; `_generate.py` and `_generate_prices.py` are what produced them,
kept so the text and the ids stay consistent if a stub needs editing:

```bash
python3 stubs/_generate.py .          # universe, sources, chunks, fundamentals, risk
python3 stubs/_generate_prices.py .   # prices.csv
```
