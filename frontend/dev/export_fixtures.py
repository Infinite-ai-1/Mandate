"""Rebuild SYNTHETIC snapshots used by frontend component tests."""
import json
from pathlib import Path
from frontend.dev.stub_api import create_app
from quant.contract_fixtures import CHARITIES

def main():
    app=create_app()
    client=app.test_client()
    paths=["/api/charities"]
    for cid,_,_ in CHARITIES:
        paths.extend(f"/api/charities/{cid}/{r}" for r in ("rules","policy","portfolio","selection"))
        paths.extend(f"/api/charities/{cid}/companies/{t}" for t in ("TEST","CAPPED","VETO","REVIEW"))
    paths.extend(f"/api/sources/{s}" for s in app.config["FIXTURE_STORE"].sources)
    paths.append("/api/compare/TEST")
    responses={path:client.get(path) for path in paths}
    snapshot={path:response.get_json() for path,response in responses.items()}
    summaries={path:json.loads(response.headers["X-Mandate-Presentation"]) for path,response in responses.items() if "X-Mandate-Presentation" in response.headers}
    (Path(__file__).parent/"fixtures.json").write_text(json.dumps(snapshot,indent=2)+"\n",encoding="utf-8")
    (Path(__file__).parent/"presentation-fixtures.json").write_text(json.dumps(summaries,indent=2)+"\n",encoding="utf-8")
    print("Exported synthetic API snapshots for all four charities.")

if __name__=="__main__":main()
