"""Mandate: Streamlit front end. Reads results/run.json; only the live rule calls the API."""
import json
import os
import warnings
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

warnings.filterwarnings("ignore")

from mandate import config as C  # noqa: E402
from mandate import view  # noqa: E402
from mandate.live_rule import add_rule  # noqa: E402

DISCLAIMER = "Educational hackathon project. Not financial advice. Not affiliated with any charity named."
PALETTE = ["#2a6fdb", "#e08a1e", "#2e9e6b", "#b84ec9", "#d9534f", "#17a2b8", "#8c6d1f", "#6c757d", "#e83e8c"]
BADGE = {"PASS": ":green-badge[PASS]", "FAIL": ":red-badge[FAIL]", "FLAG": ":orange-badge[FLAG]"}

st.set_page_config(page_title="Mandate", layout="wide")
st.markdown("<style>.stApp{font-size:1.08rem} h1,h2,h3{margin-top:.6rem}</style>", unsafe_allow_html=True)


@st.cache_data
def load_run(path: str, mtime: float) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def run_path(charity: str | None) -> Path:
    """results/run_{charity}.json if present, else results/run.json (or $MANDATE_RUN_JSON)."""
    if os.getenv("MANDATE_RUN_JSON"):
        return Path(os.environ["MANDATE_RUN_JSON"])
    return next((p for p in (C.RESULTS_DIR / f"run_{charity}.json", C.RESULTS_DIR / "run.json") if p.exists()), C.RESULTS_DIR / "run.json")


# ---------------- sidebar ----------------
policies = sorted(p.stem for p in C.POLICIES_DIR.glob("*.md") if p.stem != "demo_fallback") if C.POLICIES_DIR.exists() else []
with st.sidebar:
    st.title("Mandate")
    st.caption("Three specialists, one chair, and ethics is never up for a vote.")
    charity = st.selectbox("Charity", policies or ["(no files in policies/)"],
                           index=policies.index("cancer_research_wales") if "cancer_research_wales" in policies else 0,
                           format_func=lambda s: s.replace("_", " ").title())
    pol_file = C.POLICIES_DIR / f"{charity}.md"
    with st.expander("Policy text"):
        st.text(pol_file.read_text(encoding="utf-8") if pol_file.exists() else "No policy file found.")
    st.divider()
    st.subheader("Add a rule")
    new_rule = st.text_input("In plain English", placeholder="No alcohol producers.", key="new_rule")
    go_btn = st.button("Rebuild portfolio", type="primary", disabled=not new_rule.strip())
    reset_btn = st.button("Reset to original run")
    st.divider()
    st.caption(DISCLAIMER)

path = run_path(charity)
if not path.exists():
    st.error(f"No results found at {path}. Run `python scripts/run_pipeline.py {charity}` first.")
    st.caption(DISCLAIMER)
    st.stop()
base = load_run(str(path), path.stat().st_mtime)
if base["charity_id"] != charity and not os.getenv("MANDATE_RUN_JSON") and policies:
    st.warning(f"The results file is for {base['charity_id']}, not {charity}. Run `python scripts/run_pipeline.py {charity}`.")

if st.session_state.get("base_key") != str(path) or reset_btn:
    st.session_state.update(base_key=str(path), run=base)
if go_btn:
    with st.spinner(f"Checking approved companies against: {new_rule}"):
        try:
            st.session_state.run = add_rule(st.session_state.run, new_rule)
        except Exception as e:
            st.sidebar.error(f"Could not add the rule ({type(e).__name__}: {str(e)[:150]}). The pre-cached rules work offline.")
run = st.session_state.run
fund = view.fund_cache()
dec = {d["ticker"]: d for d in run["decisions"]}

# ---------------- what changed (live rule) ----------------
wc = run.get("what_changed")
if wc:
    with st.container(border=True):
        st.subheader(f"What changed: new rule {wc['rule']['id']}, \"{wc['rule']['text']}\"  ({wc['seconds']}s)")
        if not wc["removed"]:
            st.success("Every approved company passed the new rule. The portfolio is unchanged.")
        for r in wc["removed"]:
            what = "Not checked in time, sent to trustees" if r["timed_out"] else ("Removed" if r["status"] == "REJECTED_ETHICS" else "Flagged, removed")
            st.markdown(f"**{r['ticker']}**: {what}. {r['reason']}")
            if r["quote"]:
                url = view.source_url(r["source_id"])
                st.caption(f"\"{r['quote']}\" [{r['source_id']}]({url})" if url else f"\"{r['quote']}\" [{r['source_id']}]")
        old = {h["ticker"]: h["dollars"] for h in wc["old_holdings"]}
        new = {h["ticker"]: h["dollars"] for h in wc["new_holdings"]}
        tbl = pd.DataFrame([{"Ticker": t, "Before ($)": old.get(t, 0.0), "After ($)": new.get(t, 0.0), "Change ($)": new.get(t, 0.0) - old.get(t, 0.0)}
                            for t in sorted(set(old) | set(new), key=lambda t: -max(old.get(t, 0), new.get(t, 0)))])
        st.dataframe(tbl, hide_index=True, width="stretch", column_config={c: st.column_config.NumberColumn(format="$%.0f") for c in tbl.columns[1:]})
        if wc.get("new_error"):
            st.error(f"No portfolio could be built: {wc['new_error']}")

# ---------------- 1. headline ----------------
st.title("Mandate")
h = view.headline(run)
if h:
    st.header(f"Invest ${h['budget']:,.0f} across {h['n']} holdings: {h['shares_pct']:.0%} shares, {h['bonds_pct']:.0%} bonds, ${h['cash']:,.2f} cash left over.")
else:
    st.error(f"No portfolio could be built. {run['optimiser'].get('error') or ''}")

# ---------------- 2. policy as rules ----------------
st.subheader("1. The policy as rules")
pol = run["policy"]
st.caption(f"{pol['charity']}: {pol['purpose_summary']}")
cols = st.columns(2)
for i, r in enumerate(pol["rules"]):
    with cols[i % 2].container(border=True):
        kind = r["type"].replace("_", " ")
        st.markdown(f"**{r['id']}**  {r['text']}")
        st.markdown(f":blue-badge[{kind}] :gray-badge[clause {r['clause_ref'] or '-'}] "
                    + (":green-badge[✓ quote verified]" if r["source_quote"] and not r["id"].startswith(("M", "L")) else
                       ":orange-badge[proposed from purpose]" if r["id"].startswith("M") else ":violet-badge[live rule]"))
        if r.get("threshold"):
            st.caption(f"Threshold: {r['threshold']}")
        if r["source_quote"]:
            st.caption(f"\"{r['source_quote']}\"")
for r in pol["unverified_rules"]:
    st.warning(f"Unverified rule, not used ({r['id']}): the quote \"{r['source_quote'][:80]}\" is not in the policy.")
for v in pol["vague_wording"]:
    st.warning(f"Vague wording: \"{v['quote']}\". {v['issue']} Assumption used: {v['assumption_used']}")
if pol["proposed_mission_conflicts"]:
    with st.expander("Proposed mission conflicts (from the charity's purpose, pre-approved for the demo)"):
        for p in pol["proposed_mission_conflicts"]:
            st.checkbox(f"{p['id']}: {p['text']}", value=p["approved"], disabled=True, key=f"mc_{p['id']}", help=p["reasoning"])
        st.caption("Changing approvals needs a pipeline re-run.")
st.markdown("**Limits** " + "  ".join(
    f"{view.LIMIT_LABELS[k]}: **{v['value']:.1%}** " + (":orange-badge[assumed]" if v["origin"] == "assumed" else ":green-badge[stated]")
    for k, v in pol["limits"].items() if v))
w = pol["weights"]
st.markdown(f"**Weighting** financial health {w['financial']:.0%} / risk {w['risk']:.0%} " + (":orange-badge[assumed]" if w["origin"] == "assumed" else ":green-badge[stated]"))

# ---------------- 3. MAGI board ----------------
st.subheader("2. The MAGI board")
st.caption("Melchior (ethics), Balthasar (financial health), Casper (risk), then the Chair. A verified ethics FAIL is a veto: it never reaches the Chair.")
st.dataframe(pd.DataFrame(view.board_rows(run)), hide_index=True, width="stretch")
for d in sorted(run["decisions"], key=lambda d: (view.ORDER[d["status"]], d["ticker"])):
    if not d.get("melchior"):
        continue
    with st.expander(f"{d['ticker']}  ·  {d['status'].replace('_', ' ').title()}  ·  cap {d['cap']:.0%}"):
        st.markdown("**Melchior (ethics)**")
        rules = {r["id"]: r["text"] for r in pol["rules"]}
        for v in d["melchior"]["verdicts"]:
            line = f"{BADGE[v['verdict']]} **{v['rule_id']}** {rules.get(v['rule_id'], '')}: {v['reason']}"
            st.markdown(line if v["verified"] else f":gray[{line}  (unverified)]")
            if v["quote"]:
                url = view.source_url(v["source_id"])
                st.caption(f"{'✓' if v['verified'] else '✗ not found in source'} \"{v['quote']}\" " + (f"[{v['source_id']}]({url})" if url else f"[{v['source_id']}]"))
        for title, key in (("Balthasar (financial health)", "balthasar"), ("Casper (risk)", "casper")):
            r = d.get(key)
            if r:
                st.markdown(f"**{title}**: {'data missing' if r['score'] is None else str(r['score']) + '/10'}")
                for x in r["reasons"]:
                    cite = x.get("metric") or ""
                    if x.get("source_id"):
                        url = view.source_url(x["source_id"])
                        cite += f" [{x['source_id']}]({url})" if url else f" {x['source_id']}"
                    st.markdown(f"✓ {x['text']} `{cite.strip()}`")
                for x in r["unverified"]:
                    st.markdown(f":gray[✗ {x['text']} (unverified)]")
        ch = d.get("chair")
        if ch:
            st.markdown(f"**Chair**: {ch['decision']}" + (" :orange-badge[defaulted: Chair unavailable]" if ch["defaulted"] else ""))
            for x in ch["reasons"]:
                links = ", ".join(f"[{i}]({ch['links'][i]})" if i in ch["links"] else f"`{i}`" for i in x["source_ids"])
                st.markdown(f"✓ {x['text']} {links}")
            for x in ch["unverified"]:
                st.markdown(f":gray[✗ {x['text']} (unverified)]")

# ---------------- 4. portfolio ----------------
st.subheader("3. The portfolio")
if h:
    hs = run["optimiser"]["holdings"]
    sectors = [view.sector_of(x["ticker"], x["is_bond"], fund) for x in hs]
    colour = {s: PALETTE[i % len(PALETTE)] for i, s in enumerate(sorted(set(sectors)))}
    left, right = st.columns([2, 3])
    fig = go.Figure(go.Pie(labels=[x["ticker"] for x in hs], values=[x["dollars"] for x in hs], hole=0.55, sort=False,
                           marker=dict(colors=[colour[s] for s in sectors]), textinfo="label+percent",
                           hovertext=sectors, hovertemplate="%{label} (%{hovertext}): $%{value:,.0f}<extra></extra>"))
    fig.update_layout(height=430, margin=dict(t=10, b=10, l=10, r=10), showlegend=False, font=dict(size=15))
    left.plotly_chart(fig, width="stretch")
    left.caption("Colour = sector: " + ", ".join(f":gray[{s}]" for s in colour))
    right.dataframe(pd.DataFrame(view.holdings_rows(run)), hide_index=True, width="stretch",
                    column_config={"Dollars": st.column_config.NumberColumn(format="$%.2f"), "Cap": st.column_config.NumberColumn(format="percent"),
                                   "Reason": st.column_config.TextColumn(width="large")})

# ---------------- 5. rejections ----------------
st.subheader("4. Why we rejected or flagged")
rej = view.rejection_rows(run)
if rej:
    st.dataframe(pd.DataFrame(rej), hide_index=True, width="stretch",
                 column_config={"Source": st.column_config.LinkColumn("Source", display_text=r"https?://.*/([^/]+)$"),
                                "Why": st.column_config.TextColumn(width="large"), "Quote": st.column_config.TextColumn(width="large")})
else:
    st.write("Nothing rejected or flagged.")

# ---------------- 6. review list and risk cards ----------------
st.subheader("5. For the trustees")
for item in view.review_items(run):
    st.markdown(f"- {item}")
cards = view.risk_cards(run)
if cards:
    st.caption("Past performance, not a forecast.")
    for col, c in zip(st.columns(len(cards)), cards):
        with col.container(border=True):
            st.metric(c["label"], c["value"])
            tone = "gray" if c["ok"] is None else ("green" if c["ok"] else "orange")
            col.markdown(f":{tone}[{c['note']}" + ("" if c["ok"] is None else (" · inside" if c["ok"] else " · outside")) + "]")

# ---------------- 7. memo ----------------
st.subheader("6. Trustee memo")
if run.get("memo_stale"):
    st.warning("This memo was written before the live rule and is out of date. Re-run the pipeline to refresh it.")
st.markdown(run["memo"] or "_No memo was generated for this run._")

# ---------------- 8. about ----------------
with st.expander("About this run"):
    s = run["stats"]
    a, b, c, d_ = st.columns(4)
    a.metric("Wall time", f"{s['wall_seconds']}s")
    b.metric("LLM calls", s["llm_calls"])
    c.metric("Tokens", f"{s['tokens']:,}")
    d_.metric("Cache hits", s["cache_hits"])
    st.caption(f"Generated {run['generated_at']}" + (" · DEMO_MODE (cache only)" if run.get("demo_mode") else ""))
    st.dataframe(pd.DataFrame([{"Agent": k, "Deployment": s["models"].get(k, "-"), "Calls": v["calls"], "Cache hits": v["cache_hits"],
                                "Tokens": v["prompt_tokens"] + v["completion_tokens"]} for k, v in s["by_agent"].items()]),
                 hide_index=True, width="stretch")

st.divider()
st.caption(DISCLAIMER)
