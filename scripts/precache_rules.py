"""Pre-run the likely live rules so they come back from cache on stage: python scripts/precache_rules.py [run.json]"""
import json
import sys
import time
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mandate import config as C  # noqa: E402
from mandate.live_rule import add_rule  # noqa: E402

RULES = ["No alcohol producers.", "No gambling companies.", "No companies that test cosmetics on animals.",
         "No companies fined for data privacy breaches in the last 3 years."]


def main() -> None:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else C.RESULTS_DIR / "run.json"
    run = json.loads(src.read_text(encoding="utf-8"))
    for text in RULES:
        t = time.time()
        new = add_rule(run, text)       # each rule is applied to the original run, not stacked
        gone = [r["ticker"] for r in new["what_changed"]["removed"]]
        print(f"{time.time() - t:5.1f}s  {text!r:70s} removed: {gone or 'none'}")


if __name__ == "__main__":
    main()
