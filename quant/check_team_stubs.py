"""Read the team's fetched stubs branch without editing any teammate's files.

Price-only diagnostic, not a substitute for complete Metric/Portfolio output.
Run from repo root after git fetch origin: python -m quant.check_team_stubs
"""
import io
import json
from pathlib import Path
import subprocess
import pandas as pd
from quant.stats import calculate_price_metrics
from quant.contracts import shared_model

def main():
    root=Path(__file__).resolve().parents[1]
    def git(*args):return subprocess.check_output(["git",*args],cwd=root,text=True)
    revision=git("rev-parse","origin/stubs").strip()
    wide=pd.read_csv(io.StringIO(git("show","origin/stubs:stubs/prices.csv")),parse_dates=["date"])
    frame=wide.melt(id_vars="date",var_name="ticker",value_name="close")
    calculated={}
    for ticker in sorted(frame.ticker.unique()):
        as_of,values=calculate_price_metrics(frame,ticker)
        calculated[ticker]=dict(as_of=as_of,price_metrics=values,dividend_yield_status="unavailable: stub contains no cash dividend history")
    missing=[]
    for name in ("Metric","Portfolio"):
        try:shared_model(name)
        except ImportError:missing.append(name)
    result=dict(label="SYNTHETIC team stubs; past performance, not a forecast",stub_revision=revision,
        price_layout="wide daily closes; no cash dividends",missing_shared_models=missing,tickers=calculated,
        integration_status="blocked: cash dividend observations, compatible shared models, source registry and API still required")
    destination=root/"quant/examples/team-stub-validation.json"
    destination.write_text(json.dumps(result,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps(result,indent=2))

if __name__=="__main__":main()
