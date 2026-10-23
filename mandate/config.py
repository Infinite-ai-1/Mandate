"""Settings from .env, model routing, limits and paths."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


# Azure OpenAI. If the endpoint ends in /openai/v1/ the plain OpenAI client is used.
ENDPOINT = _env("AZURE_OPENAI_ENDPOINT")
API_KEY = _env("AZURE_OPENAI_API_KEY")
API_VERSION = _env("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")

DEPLOY_SOL = _env("DEPLOY_SOL")
DEPLOY_ASTRA = _env("DEPLOY_ASTRA")
DEPLOY_TERRA_6 = _env("DEPLOY_TERRA_6")
DEPLOY_TERRA_56 = _env("DEPLOY_TERRA_56")
DEPLOY_MAI = _env("DEPLOY_MAI")
DEPLOY_EMBED = _env("DEPLOY_EMBED")

FINNHUB_API_KEY = _env("FINNHUB_API_KEY")
EDGAR_USER_AGENT = _env("EDGAR_USER_AGENT", "Mandate Hackathon your.email@example.com")

DEMO_MODE = _env("DEMO_MODE", "0") == "1"

MODELS = {
    "chair": DEPLOY_SOL,        # policy compiler + final decision
    "melchior": DEPLOY_SOL,     # ethics
    "balthasar": DEPLOY_MAI,    # financial health (reasoning model)
    "casper": DEPLOY_TERRA_6,   # risk
    "memo": DEPLOY_SOL,
    "fast": DEPLOY_TERRA_56,    # live rule re-screen
    "backup": DEPLOY_ASTRA,     # used if a deployment fails 4 times
    "embed": DEPLOY_EMBED,
}
REASONING_MODELS = {d for d in (DEPLOY_MAI,) if d}   # no temperature, max_completion_tokens

BUDGET_USD = 100_000
CAP_BY_DECISION = {"full": 0.10, "reduced": 0.05, "reject": 0.0}
BOND_MAX_WEIGHT = 0.25      # per bond ETF, bonds skip the ethics screen

DEFAULT_LIMITS = {          # used when the policy doesn't say; shown as "assumed"
    "min_bonds": 0.30,
    "min_yield": 0.025,     # portfolio trailing dividend yield
    "worst_year_limit": -0.15,  # worst rolling 12-month return
}
DEFAULT_WEIGHTS = {"financial": 0.5, "risk": 0.5}   # origin="assumed" unless the policy states weights

PRICE_YEARS = 3
NEWS_DAYS = 180
TOP_K_PER_RULE = 4
MAX_CONCURRENCY = 8
LIVE_RULE_TIMEOUT_S = 25
EMBED_BATCH = 64

# Paths
CACHE_DIR = ROOT / "cache"
LLM_CACHE_DIR = CACHE_DIR / "llm"
LLM_LOG = CACHE_DIR / "llm_log.jsonl"
RESULTS_DIR = ROOT / "results"
POLICIES_DIR = ROOT / "policies"
