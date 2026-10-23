import { useEffect, useState } from "react";
import type { DecisionKind } from "./api";

export const demoStocks: {
  ticker: string; name: string; decision: DecisionKind; label: string; cap: number;
  notes: string[]; reason: string; challenges: string[];
}[] = [
  { ticker: "XYL", name: "Xylem", decision: "APPROVE", label: "Approved", cap: 10,
    notes: [
      "Assume the supplied evidence supports every adopted ethics rule. Melchior records a pass in this scenario.",
      "Assume verified financial records show a sustainable business and adequate liquidity. Balthasar supports investment.",
      "Assume the measured risk fits the trustee limits. Casper supports the standard position limit.",
      "The simulated ethics gate is clear and both specialist assessments support investment. Chair approves the standard cap.",
    ], reason: "All simulated rule checks pass and the financial and risk cases support approval.",
    challenges: ["A clean screen depends on the completeness of the evidence. What adverse evidence might be missing?", "Would the allocation still be suitable if liquidity or sector concentration deteriorated?", "Before any real allocation, replace these assumptions with current verified sources." ] },
  { ticker: "MSFT", name: "Microsoft", decision: "APPROVE_CAPPED", label: "Approved with a cap", cap: 5,
    notes: [
      "Assume the available evidence passes the adopted ethics rules. Melchior finds no blocking issue in this scenario.",
      "Assume verified financial records support the investment case. Balthasar supports a position.",
      "Assume the charity already has material exposure to the same sector. Casper requests a smaller position to limit concentration.",
      "The ethics gate passes, but the simulated concentration concern remains. Chair approves a reduced cap rather than a full position.",
    ], reason: "The simulated investment case is acceptable, with a reduced cap to address concentration risk.",
    challenges: ["A smaller position reduces exposure but does not remove the concentration risk.", "Check overlapping exposure inside funds as well as direct holdings.", "Would a different eligible company provide better diversification?" ] },
  { ticker: "PM", name: "Philip Morris", decision: "REJECT", label: "Rejected", cap: 0,
    notes: [
      "Assume trustees have explicitly adopted a tobacco exclusion and the scenario evidence confirms prohibited exposure. Melchior records an ethics failure.",
      "Assume the business has a positive financial case. Balthasar's financial support cannot override the ethics gate.",
      "Casper notes that a manageable financial risk would not resolve the simulated policy breach.",
      "The code veto blocks approval because this scenario has a confirmed ethics failure. Chair records rejection regardless of financial support.",
    ], reason: "A simulated verified breach of an explicitly adopted tobacco exclusion triggers the ethics veto.",
    challenges: ["Confirm the exclusion is an adopted trustee rule rather than an inferred mission preference.", "Check the evidence identifies the right issuer and the activity covered by the rule.", "A strong financial case is not a reason to bypass a confirmed policy exclusion." ] },
  { ticker: "MMM", name: "3M", decision: "TRUSTEE_REVIEW", label: "Trustee review", cap: 0,
    notes: [
      "Assume relevant evidence is incomplete or ambiguous. Melchior flags the unresolved rule instead of inventing a pass.",
      "Assume some financial evidence supports investment. Balthasar records the case subject to the unresolved ethics check.",
      "Casper identifies uncertainty that cannot be resolved from the supplied scenario evidence.",
      "Missing verification prevents approval. Chair refers the case to trustees and requests targeted evidence before another assessment.",
    ], reason: "The simulated evidence is insufficient to approve or establish a confirmed breach. Trustees must resolve the gap.",
    challenges: ["A flag is not proof of wrongdoing; specify exactly which evidence would resolve it.", "Set an owner and review date so the case does not remain unresolved indefinitely.", "Would clarification from trustees settle the scope of the rule before more research is commissioned?" ] },
];
const agents = ["Melchior · Ethics", "Balthasar · Financial health", "Casper · Risk", "Chair · Final decision"];

export default function DemoResearch({ disabled = false }: { disabled?: boolean }) {
  const [selected, setSelected] = useState<number | null>(null);
  const [step, setStep] = useState(0);
  const [replay, setReplay] = useState(0);
  const stock = selected === null ? null : demoStocks[selected];
  const done = step >= agents.length;
  useEffect(() => {
    if (selected === null || step >= agents.length) return;
    const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    const timer = setTimeout(() => setStep((value) => value + 1), reduced ? 0 : 900);
    return () => clearTimeout(timer);
  }, [selected, step, replay]);
  return <section className="demo-research panel" aria-label="Starred demo stocks">
    <p className="research-kicker">★ Demo stocks · Four decision paths</p>
    <h3>Try a complete committee review</h3>
    <p>Scripted simulation using illustrative assumptions about these companies. These are demo outcomes, not their actual assessments. Review notes are a narrated walkthrough, not private model reasoning.</p>
    <div className="demo-stock-grid">
      {demoStocks.map((item, index) => <button key={item.ticker} className={selected === index ? "demo-stock selected" : "demo-stock"}
        disabled={disabled} aria-pressed={selected === index}
        onClick={() => { setSelected(index); setStep(0); setReplay((value) => value + 1); }}>
        <strong>★ {item.ticker}</strong><span>{item.name}</span><span>{item.label} · demo</span>
      </button>)}
    </div>
    {stock && <div className="demo-walkthrough">
      <div className="row between"><h4>{stock.ticker} · Simulated review</h4><button onClick={() => setSelected(null)}>Close demo</button></div>
      <p role="status">{done ? "Simulation complete" : `Simulating ${agents[step]}`}</p>
      <div className="demo-agent-grid">{agents.map((agent, index) => <article key={agent} className={step > index ? "complete" : ""}>
        <h4>{agent}</h4><p>{step > index ? stock.notes[index] : step === index ? "Reviewing this scenario's assumptions…" : "Waiting for the preceding review"}</p>
      </article>)}</div>
      {done && <>
        <section className="demo-decision" aria-label="Simulated final decision"><h4>{stock.label} · simulated</h4><p>{stock.reason}</p>
          <p>{stock.cap ? `Illustrative position cap: ${stock.cap}% of the demo budget.` : "No allocation permitted in this scenario."}</p>
        </section>
        <section aria-label="Demo devil’s advocate"><h4>Devil’s advocate</h4><ul>{stock.challenges.map((challenge) => <li key={challenge}>{challenge}</li>)}</ul></section>
        <p className="research-caption">Demo results do not change your charity's real assessments, suggested portfolio or paper account. Select a starred stock to replay.</p>
      </>}
    </div>}
  </section>;
}
