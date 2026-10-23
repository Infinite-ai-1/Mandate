"""Package observed caches and completed runs; exclude keys and paper transactions.

Usage: python scripts/package_demo.py [--output results/mandate-keyless-demo.zip]
Extract the ZIP into the repository root and set DEMO_MODE=1 before starting Flask.
"""
import argparse
import hashlib
import json
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def package(output):
    from mandate import config as C
    from mandate.web import Workspace
    from dotenv import dotenv_values
    ws = Workspace(C.RESULTS_DIR / "workspace")
    files = {}
    completed = []
    try:
        from mandate.web import CHARITIES
        for cid in CHARITIES:
            try:
                run = ws.run(cid)
            except Exception:
                continue
            # Do not export personal policy edits, receipts, jobs or transaction ledgers.
            policy_file = next((p for p in (C.POLICIES_DIR / f"{cid}.txt", C.POLICIES_DIR / f"{cid}.md") if p.exists()), None)
            if not policy_file or run["policy_hash"] != hashlib.sha256(policy_file.read_text(encoding="utf-8").encode()).hexdigest():
                continue
            state = dict(revision=0, policy=None, run=run, cash=C.BUDGET_USD, positions={}, receipts={})
            files[f"results/workspace/{cid}.json"] = json.dumps(state, indent=2, allow_nan=False).encode()
            completed.append(cid)
    finally:
        ws.executor.shutdown()
    if not completed:
        raise RuntimeError("No completed run matches a supplied published policy. Complete a live run first.")
    # Whitelist data directories; never include .env, logs, local state or source credentials.
    for directory in ("cache/llm", "cache/edgar", "cache/emb", "cache/news", "data/processed", "policies"):
        for path in (ROOT / directory).rglob("*"):
            if path.is_file() and path.suffix in (".json", ".npy", ".parquet", ".txt", ".md"):
                files[path.relative_to(ROOT).as_posix()] = path.read_bytes()
    for name in ("prices.csv", "fundamentals.json", "risk_stats.json", "yields.json"):
        path = C.CACHE_DIR / name
        if path.exists():
            files[f"cache/{name}"] = path.read_bytes()
    # Match known local secrets and common credential field names before creating an archive.
    secrets = [v.encode() for k, v in dotenv_values(ROOT / ".env").items() if v and ("KEY" in k or "TOKEN" in k or "SECRET" in k) and len(v) > 10]
    for name, data in files.items():
        if any(secret in data for secret in secrets):
            raise RuntimeError(f"Credential scan failed for {name}; archive was not created.")
    manifest = dict(created_at=datetime.now(timezone.utc).isoformat(), charities=completed,
                    models=C.MODELS, mode="completed-assessment replay", files={name: hashlib.sha256(data).hexdigest() for name, data in files.items()})
    files["demo-manifest.json"] = json.dumps(manifest, indent=2).encode()
    files["DEMO-BUNDLE-README.txt"] = ("Extract into the Mandate repository root. Set DEMO_MODE=1 in the environment, then run python api.py.\n"
        "Install dependencies and build React before disconnecting. No API keys are required for saved-run replay.\n"
        "See demo-manifest.json for included charities. New policies and uncached research require an online run.\n"
        "Quotes retain original dates; stale real-price allocations stay blocked. Starred demos use simulated prices.\n").encode()
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            archive.writestr(name, data)
    print(f"Packaged {len(completed)} completed charities and {len(files)} files: {output}")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=str(ROOT / "results/mandate-keyless-demo.zip"))
    package(parser.parse_args().output)
