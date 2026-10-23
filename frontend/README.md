# React workspace

From this directory: `npm ci`, `npm run build`, `npm test`.
From the repository root: `python api.py` serves React through Flask at
http://127.0.0.1:5000. `npm run dev` proxies /api to Flask for development.

All application data comes from /api. Missing measurements render as unavailable.
Paper accounts are recorded purchase costs and remain separate from optimiser
recommendations. Only the backend calculates shares, cash, caps and statistics.
Policies and accounts persist in the ignored results/workspace directory.

Research requests include the selected charity. Policy-only saves finish cleanly
when credentials are absent. Legacy preview caches are ignored using a new cache
namespace. There is no fixture server or runtime sample data. See the repository
README for configuration, limitations and verification.
