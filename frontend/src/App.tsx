import { useEffect, useRef, useState, type ReactNode } from "react";
import {
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
} from "recharts";
import {
  api,
  paths,
  presentation,
  remember,
  request,
  safeLink,
  type Charity,
  type CompanyReport,
  type CompareRow,
  type Decision,
  type Job,
  type Portfolio,
  type Rules,
  type Selection,
  type Source,
  type Account,
  type PolicyDocument,
  type Purchase,
} from "./api";
import { useResource } from "./hooks";
import Research from "./Research";
import PolicyEditor from "./PolicyEditor";

const money = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});
const percent = new Intl.NumberFormat("en-GB", {
  style: "percent",
  maximumFractionDigits: 1,
});
const number = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 2 });
const colours = [
  "#123c35",
  "#318576",
  "#8c4b20",
  "#5375a3",
  "#8b5a94",
  "#687e35",
  "#c78d26",
  "#3a7e8b",
];
const decisionLabel = {
  APPROVE: "Approved",
  APPROVE_CAPPED: "Approved · capped",
  REJECT: "Rejected",
  TRUSTEE_REVIEW: "Trustee review",
};
const chairLabel = {
  code_veto: "code veto",
  prefilter: "pre-filter",
  chair: "chair",
};
type Resource = {
  loading: boolean;
  error?: string;
  data?: unknown;
  retry: () => void;
};
function Status({ resource }: { resource: Resource }) {
  if (resource.error)
    return (
      <div className="notice" role="status">
        {resource.data ? "Showing the last good data. " : ""}
        {resource.error}{" "}
        <button className="text-button" onClick={resource.retry}>
          Try again
        </button>
      </div>
    );
  return resource.loading ? (
    <p className="loading" role="status">
      Loading evidence…
    </p>
  ) : null;
}
function Badge({
  children,
  kind = "neutral",
}: {
  children: ReactNode;
  kind?: string;
}) {
  return <span className={`badge ${kind}`}>{children}</span>;
}
function DecisionBadge({ decision }: { decision: Decision }) {
  return (
    <Badge kind={decision.decision}>{decisionLabel[decision.decision]}</Badge>
  );
}
function Chips({ ids, open }: { ids: string[]; open: (id: string) => void }) {
  return (
    <span className="chips">
      {ids.map((id) => (
        <a
          key={id}
          href={paths.source(id)}
          onClick={(e) => {
            e.preventDefault();
            open(id);
          }}
        >
          {id} ↗
        </a>
      ))}
    </span>
  );
}
function RegisteredLink({ id }: { id: string }) {
  const source = useResource<Source>(paths.source(id));
  const url = source.data ? safeLink(source.data.url) : undefined;
  return (
    <>
      <Status resource={source} />
      {url && (
        <a href={url} target="_blank" rel="noreferrer">
          Open filing evidence ↗
        </a>
      )}
    </>
  );
}
function Modal({
  title,
  close,
  children,
}: {
  title: string;
  close: () => void;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    dialog?.showModal();
    return () => dialog?.close();
  }, []);
  return (
    <dialog
      ref={ref}
      onCancel={(e) => {
        e.preventDefault();
        close();
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) close();
      }}
      aria-label={title}
    >
      <div className="drawer">
        <div className="drawer-heading">
          <h2>{title}</h2>
          <button onClick={close} aria-label={`Close ${title}`}>
            Close ×
          </button>
        </div>
        {children}
      </div>
    </dialog>
  );
}
function SourceDrawer({ id, close }: { id: string; close: () => void }) {
  const source = useResource<Source>(paths.source(id));
  const s = source.data;
  return (
    <Modal title="Evidence source" close={close}>
      <Status resource={source} />
      {s && (
        <>
          <Badge>
            {s.kind} · {s.origin}
          </Badge>
          <h3>{s.title}</h3>
          <p className="muted">{s.source_id}</p>
          <dl>
            <dt>Date</dt>
            <dd>{s.date}</dd>
            <dt>Section</dt>
            <dd>{s.section || "No section supplied"}</dd>
          </dl>
          {safeLink(s.url) ? (
            <a
              className="primary link-button"
              href={safeLink(s.url)}
              target="_blank"
              rel="noreferrer"
            >
              Open registered source ↗
            </a>
          ) : (
            <p className="notice">The registry has no usable source link.</p>
          )}
        </>
      )}
    </Modal>
  );
}
function ScoreCard({
  report,
  open,
}: {
  report: CompanyReport["casper"];
  open: (id: string) => void;
}) {
  return (
    <article className="agent-card">
      <p className="eyebrow">{report.agent}</p>
      <h3>{report.model}</h3>
      <p className="score">
        {report.score === null ? "Unavailable" : number.format(report.score)} <span>verified evidence coverage (%)</span>
      </p>
      <p>{report.summary}</p>
      {report.reasons.map((r, i) => (
        <div className="claim" key={i}>
          <p>{r.claim}</p>
          <Badge kind={r.verified === true ? "verified" : "neutral"}>
            {r.verified === true
              ? "✓ Verified"
              : r.verified === false
                ? "Unverified"
                : "Verification pending"}
          </Badge>
          <Chips ids={r.source_ids} open={open} />
        </div>
      ))}
    </article>
  );
}
function CompanyDrawer({
  charity,
  ticker,
  version,
  close,
  openSource,
  refresh,
  busy,
}: {
  charity: string;
  ticker: string;
  version: number;
  close: () => void;
  openSource: (id: string) => void;
  refresh: (ticker: string) => void;
  busy: boolean;
}) {
  const report = useResource<CompanyReport>(
    paths.company(charity, ticker),
    version,
  );
  const r = report.data;
  return (
    <Modal title={ticker + " · analyst evidence"} close={close}>
      <Status resource={report} />
      <button disabled={busy} onClick={() => refresh(ticker)}>
        Refresh company evidence
      </button>
      {r && (
        <>
          <div className="agent-grid">
            <article className="agent-card">
              <p className="eyebrow">Melchior · ethics</p>
              <h3>{r.melchior.model}</h3>
              {r.melchior.verdicts.map((v, i) => (
                <div className="claim" key={i}>
                  <Badge
                    kind={
                      v.verdict === "PASS"
                        ? "verified"
                        : v.verdict === "FAIL"
                          ? "REJECT"
                          : "TRUSTEE_REVIEW"
                    }
                  >
                    {v.rule_id} · {v.verdict}
                  </Badge>
                  <p>{v.reason}</p>
                  <blockquote>{v.quote}</blockquote>
                  <p
                    className={v.verified === true ? "verified-text" : "muted"}
                  >
                    {v.verified === true
                      ? "✓ Quote verified"
                      : v.verified === false
                        ? "Quote not verified"
                        : "Quote verification pending"}
                  </p>
                  <Chips ids={[v.source_id]} open={openSource} />
                </div>
              ))}
            </article>
            <ScoreCard report={r.balthasar} open={openSource} />
            <ScoreCard report={r.casper} open={openSource} />
          </div>
          <section className="chair-card">
            <p className="eyebrow">Chair’s decision</p>
            <DecisionBadge decision={r.decision} />
            <p>{r.decision.reason}</p>
            <p>
              Weighted score:{" "}
              {r.decision.weighted_score === null
                ? "Not supplied"
                : number.format(r.decision.weighted_score)}
            </p>
            <p className="muted">
              Decided by {chairLabel[r.decision.decided_by]}
            </p>
            <Chips ids={r.decision.source_ids} open={openSource} />
          </section>
        </>
      )}
    </Modal>
  );
}
function Rejected({
  decision,
  charity,
  version,
  open,
  company,
}: {
  decision: Decision;
  charity: string;
  version: number;
  open: (id: string) => void;
  company: (ticker: string) => void;
}) {
  const report = useResource<CompanyReport>(
    decision.decided_by === "prefilter"
      ? null
      : paths.company(charity, decision.ticker),
    version,
  );
  const failures = report.data?.melchior.verdicts.filter(
    (v) => v.verdict === "FAIL",
  );
  return (
    <article className="rejection">
      <div className="row between">
        <button className="ticker" onClick={() => company(decision.ticker)}>
          {decision.ticker} · {decision.name} ↗
        </button>
        <Badge>{chairLabel[decision.decided_by]}</Badge>
      </div>
      <p>{decision.reason}</p>
      <Chips ids={decision.source_ids} open={open} />
      <Status resource={report} />
      {failures?.map((v, i) => (
        <div className="quote" key={i}>
          <p className="eyebrow">Rule {v.rule_id}</p>
          <blockquote>{v.quote}</blockquote>
          <p className={v.verified === true ? "verified-text" : "muted"}>
            {v.verified === true ? "✓ Verified quote" : "Quote not verified"}
          </p>
          <Chips ids={[v.source_id]} open={open} />
          <RegisteredLink id={v.source_id} />
        </div>
      ))}
    </article>
  );
}
function DecisionProcess({ explore }: { explore?: () => void }) {
  return (
    <section
      className="decision-process panel"
      aria-label="How decisions are made"
    >
      <div className="section-heading">
        <div>
          <p className="eyebrow">The investment committee</p>
          <h2>A decision you can trace.</h2>
        </div>
        {explore && (
          <button className="primary" onClick={explore}>
            Explore agent decisions →
          </button>
        )}
      </div>
      <div className="process-track">
        <div>
          <span className="process-symbol">M</span>
          <h3>Melchior</h3>
          <p>Checks the ethics of every company against each rule.</p>
          <Badge>Ethics gate</Badge>
        </div>
        <div>
          <span className="process-symbol">B</span>
          <h3>Balthasar</h3>
          <p>Assesses financial health and cites the supporting evidence.</p>
          <Badge>Financial assessment</Badge>
        </div>
        <div>
          <span className="process-symbol">C</span>
          <h3>Casper</h3>
          <p>Assesses historical risk and cites the supporting evidence.</p>
          <Badge>Risk assessment</Badge>
        </div>
        <div className="process-chair">
          <span className="process-symbol">↳</span>
          <h3>The Chair</h3>
          <p>
            Weighs the assessments for companies that clear the ethics checks.
          </p>
          <Badge>Final decision</Badge>
        </div>
      </div>
      <p className="process-rule">
        A verified ethics failure blocks approval. An ethics flag goes to
        trustees. Financial scores cannot override the ethics gate.
      </p>
    </section>
  );
}
function AgentDecisions({
  charity,
  selection,
  portfolio,
  rules,
  version,
  open,
  refresh,
  busy,
}: {
  charity: string;
  selection?: Selection;
  portfolio?: Portfolio;
  rules?: Rules;
  version: number;
  open: (id: string) => void;
  refresh: (ticker: string) => void;
  busy: boolean;
}) {
  const [picked, setPicked] = useState("");
  const tickers = [
    ...new Set([
      ...(selection?.selected.map((s) => s.ticker) || []),
      ...(portfolio?.holdings.filter((h) => !h.is_bond).map((h) => h.ticker) ||
        []),
      ...(portfolio?.rejected.map((d) => d.ticker) || []),
      ...(portfolio?.trustee_review.map((d) => d.ticker) || []),
    ]),
  ];
  const ticker = tickers.includes(picked) ? picked : tickers[0] || "";
  const report = useResource<CompanyReport>(
    ticker ? paths.company(charity, ticker) : null,
    version,
  );
  const data = report.data;
  const holding = portfolio?.holdings.find((h) => h.ticker === ticker);
  return (
    <div className="decisions-workspace">
      <DecisionProcess />
      <section className="panel decision-selector">
        <div>
          <p className="eyebrow">Open the evidence behind a company</p>
          <h2>Agent decisions</h2>
          <p className="muted">
            Read the submitted assessments, verified quotes and the final
            decision together.
          </p>
        </div>
        <div>
          <label htmlFor="decision-company">Company under review</label>
          <select
            id="decision-company"
            value={ticker}
            disabled={!ticker}
            onChange={(e) => setPicked(e.target.value)}
          >
            {!ticker && <option>No company data available</option>}
            {tickers.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
          <button disabled={!ticker || busy} onClick={() => refresh(ticker)}>
            Refresh this evidence ↻
          </button>
        </div>
      </section>
      <Status resource={report} />
      {!ticker && (
        <section className="panel">
          <p>
            Company assessments will appear when the selection or portfolio API
            supplies company tickers.
          </p>
        </section>
      )}
      {data && (
        <>
          <section className={`decision-outcome ${data.decision.decision}`}>
            <div>
              <p className="eyebrow">{ticker} · recorded outcome</p>
              <DecisionBadge decision={data.decision} />
              <h2>{data.decision.reason}</h2>
              <Chips ids={data.decision.source_ids} open={open} />
            </div>
            <dl>
              <dt>Decision made by</dt>
              <dd>{chairLabel[data.decision.decided_by]}</dd>
              <dt>Position cap</dt>
              <dd>{percent.format(data.decision.cap)}</dd>
              <dt>Weighted score</dt>
              <dd>
                {data.decision.weighted_score === null
                  ? "Not supplied by API"
                  : number.format(data.decision.weighted_score)}
              </dd>
            </dl>
          </section>
          <div className="committee-grid">
            <article className="agent-card ethics-card">
              <p className="eyebrow">Melchior · ethics</p>
              <h2>Does it meet the mandate?</h2>
              <p className="model-label">{data.melchior.model}</p>
              <p className="muted">
                Rule-by-rule verdicts, with the exact evidence used.
              </p>
              {data.melchior.verdicts.map((v, i) => {
                const rule = rules?.rules.find((rule) => rule.id === v.rule_id);
                return (
                  <section className="claim" key={v.rule_id + String(i)}>
                    <div className="row between">
                      <Badge
                        kind={
                          v.verdict === "PASS"
                            ? "APPROVE"
                            : v.verdict === "FAIL"
                              ? "REJECT"
                              : "TRUSTEE_REVIEW"
                        }
                      >
                        {v.verdict}
                      </Badge>
                      <span className="muted">{v.rule_id}</span>
                    </div>
                    {rule && <h3 className="matched-rule">{rule.text}</h3>}
                    <p>{v.reason}</p>
                    <blockquote>{v.quote}</blockquote>
                    <div className="evidence-verification">
                      <Badge
                        kind={v.verified === true ? "verified" : "neutral"}
                      >
                        {v.verified === true
                          ? "✓ Quote verified"
                          : v.verified === false
                            ? "Quote not verified"
                            : "Verification pending"}
                      </Badge>
                      <p className="muted">
                        Evidence verified: {v.verified ? "Yes" : "No"}
                      </p>
                    </div>
                    <Chips ids={[v.source_id]} open={open} />
                  </section>
                );
              })}
              {!data.melchior.verdicts.length && (
                <p>No ethics verdicts supplied.</p>
              )}
            </article>
            <div className="assessment-column">
              <div className="assessment-intro">
                <p className="eyebrow">Balthasar · financial health</p>
                <h2>Is the business financially sound?</h2>
                <p>The API’s score and supporting assessment.</p>
              </div>
              <ScoreCard report={data.balthasar} open={open} />
            </div>
            <div className="assessment-column">
              <div className="assessment-intro">
                <p className="eyebrow">Casper · risk</p>
                <h2>How much risk does it carry?</h2>
                <p>The API’s score and supporting assessment.</p>
              </div>
              <ScoreCard report={data.casper} open={open} />
            </div>
          </div>
          <section className="chair-explanation panel">
            <div>
              <p className="eyebrow">How the assessments reach the Chair</p>
              <h2>The charity sets the balance.</h2>
              <p>
                Ethics is a gate. The financial and risk weights guide the
                Chair’s assessment after the company clears that gate.
              </p>
              {rules ? (
                <>
                  <div className="weights">
                    <p>
                      Financial health
                      <strong>{percent.format(rules.weights.financial)}</strong>
                    </p>
                    <p>
                      Risk<strong>{percent.format(rules.weights.risk)}</strong>
                    </p>
                  </div>
                  <p className="weights-reason">{rules.weights_reason}</p>
                </>
              ) : (
                <p className="muted">
                  Waiting for the charity’s weights from the rules API.
                </p>
              )}
            </div>
            <div className="allocation-result">
              <p className="eyebrow">From decision to allocation</p>
              <h3>
                {holding
                  ? "Included in the current portfolio"
                  : "No holding in the current portfolio"}
              </h3>
              {holding ? (
                <>
                  <p className="allocation-value">
                    {money.format(holding.usd)}
                  </p>
                  <p>
                    {number.format(holding.shares)} shares ·{" "}
                    {percent.format(holding.weight)} portfolio weight
                  </p>
                  <p>{holding.reason}</p>
                  <Chips ids={holding.source_ids} open={open} />
                </>
              ) : (
                <p>
                  The portfolio API has no current allocation for this company.
                  The recorded decision above explains its assessment.
                </p>
              )}
              <p className="muted small">
                The optimiser calculates share counts using prices and portfolio
                constraints. Agent scores are assessment outputs, not measured
                financial statistics.
              </p>
            </div>
          </section>
        </>
      )}
    </div>
  );
}
function Compare({
  charities,
  open,
}: {
  charities: Charity[];
  open: (id: string) => void;
}) {
  const [input, setInput] = useState("");
  const [ticker, setTicker] = useState("");
  const resource = useResource<CompareRow[]>(
    ticker ? paths.compare(ticker) : null,
  );
  return (
    <section className="panel">
      <p className="eyebrow">Same company. Different mandates.</p>
      <h2>Compare across charities</h2>
      <form
        className="row"
        onSubmit={(e) => {
          e.preventDefault();
          if (input.trim()) setTicker(input.trim().toUpperCase());
        }}
      >
        <label htmlFor="compare-ticker">Company ticker</label>
        <input
          id="compare-ticker"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="e.g. XOM"
          required
        />
        <button className="primary">Compare</button>
      </form>
      <Status resource={resource} />
      {resource.data && (
        <div className="compare-grid">
          {resource.data.map((row) => (
            <article className="rule-card" key={row.charity_id}>
              <h3>
                {charities.find((c) => c.charity_id === row.charity_id)?.name ||
                  row.charity_id}
              </h3>
              <DecisionBadge decision={row.decision} />
              <p>{row.decision.reason}</p>
              <p>Cap: {percent.format(row.decision.cap)}</p>
              <p>
                Weighted score:{" "}
                {row.decision.weighted_score === null
                  ? "Not supplied"
                  : number.format(row.decision.weighted_score)}
              </p>
              <Chips ids={row.decision.source_ids} open={open} />
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

function StatsDetails({
  p,
  r,
  rules,
}: {
  p: Portfolio;
  r?: Rules;
  rules: Resource;
}) {
  return (
    <>
      <section className="panel">
        <p className="eyebrow">Historical evidence, not a promise</p>
        <h2>Risk & the trustees’ limits</h2>
        <Status resource={rules} />
        <div className="risk-grid">
          <RiskCard
            title="Trailing dividend yield"
            value={p.risk.yield === null ? "Unavailable" : percent.format(p.risk.yield)}
            ok={p.checks.yield_ok ?? undefined}
            limit={
              r
                ? `Minimum ${percent.format(r.constraints.min_yield)}`
                : "Limit loading"
            }
          />
          <RiskCard
            title="Worst twelve-month return check"
            value={p.checks.max_drawdown_ok === null ? "Not assessed" : p.checks.max_drawdown_ok ? "Within limit" : "Outside limit"}
            ok={p.checks.max_drawdown_ok ?? undefined}
            limit={
              r
                ? `Twelve-month return floor ${percent.format(r.constraints.max_drawdown)}`
                : "Limit loading"
            }
          />
          <RiskCard
            title="Bond allocation check"
            value={p.checks.bonds_ok === null ? "Not assessed" : p.checks.bonds_ok ? "Within limit" : "Outside limit"}
            ok={p.checks.bonds_ok ?? undefined}
            limit={
              r
                ? `Minimum ${percent.format(r.constraints.min_bonds)}`
                : "Limit loading"
            }
          />
          <RiskCard
            title="Annualised volatility"
            value={p.risk.volatility === null ? "Unavailable" : percent.format(p.risk.volatility)}
          />
          <RiskCard
            title="Worst rolling twelve months"
            value={p.risk.worst_12m === null ? "Unavailable" : percent.format(p.risk.worst_12m)}
          />
          <RiskCard
            title="Return vs SPY / BND benchmark"
            value={p.risk.vs_6040_return === null ? "Unavailable" : percent.format(p.risk.vs_6040_return)}
          />
        </div>
        <p className="muted">
          Past performance, not a forecast. Final weights replayed over history.
          Checks use the original trustee limits.
        </p>
        {p.relaxed.length > 0 && (
          <div className="notice">
            <h3>Constraints relaxed</h3>
            <ul>
              {p.relaxed.map((x, i) => (
                <li key={i}>{x}</li>
              ))}
            </ul>
          </div>
        )}
      </section>
      <section className="two-columns">
        <article className="panel memo">
          <p className="eyebrow">For the board</p>
          <h2>Trustee memo</h2>
          <p>{p.memo || "Memo not yet supplied."}</p>
        </article>
        <article className="panel devil">
          <p className="eyebrow">Challenge the recommendation</p>
          <h2>Devil’s advocate</h2>
          {p.devils_advocate.length ? (
            <ul>
              {p.devils_advocate.map((x, i) => (
                <li key={i}>{x}</li>
              ))}
            </ul>
          ) : (
            <p>No counterarguments supplied.</p>
          )}
        </article>
      </section>
      <section className="panel">
        <h2>Run transparency</h2>
        <div className="run-stats">
          <p>
            <strong>{number.format(p.run_stats.seconds)}</strong> seconds
          </p>
          <p>
            <strong>{number.format(p.run_stats.llm_calls)}</strong> LLM calls
          </p>
          <p>
            <strong>{number.format(p.run_stats.tokens)}</strong> tokens
          </p>
        </div>
        <div className="agent-stats">
          {Object.entries(p.run_stats.by_agent).map(([agent, stats]) => (
            <div key={agent}>
              <h3>{agent}</h3>
              {typeof stats === "object" && stats ? (
                Object.entries(stats)
                  .filter(
                    ([, v]) => typeof v === "number" || typeof v === "string",
                  )
                  .map(([key, value]) => (
                    <p key={key}>
                      {key.replaceAll("_", " ")}:{" "}
                      {typeof value === "number"
                        ? number.format(value)
                        : String(value)}
                    </p>
                  ))
              ) : (
                <p>{String(stats)}</p>
              )}
            </div>
          ))}
        </div>
      </section>
    </>
  );
}
export default function App() {
  const charities = useResource<Charity[]>(paths.charities);
  const [selected, setSelected] = useState(() => {
    try {
      return localStorage.getItem("mandate:selected") || "";
    } catch {
      return "";
    }
  });
  const id = charities.data?.some((c) => c.charity_id === selected)
    ? selected
    : charities.data?.[0]?.charity_id || "";
  const [version, setVersion] = useState(0);
  const [researchBusy, setResearchBusy] = useState(false);
  const [tab, setTab] = useState("portfolio");
  const account = useResource<Account>(id ? paths.account(id) : null, version);
  const [purchaseNotice, setPurchaseNotice] = useState<{
    charity: string;
    receipt: Purchase["receipt"];
  } | null>(null);
  const portfolio = useResource<Portfolio>(
    id ? paths.portfolio(id) : null,
    version,
  );
  const rules = useResource<Rules>(id ? paths.rules(id) : null, version);
  const selection = useResource<Selection>(
    id ? paths.selection(id) : null,
    version,
  );
  const policy = useResource<PolicyDocument>(
    id ? paths.policy(id) : null,
    version,
  );
  const [source, setSource] = useState<string | null>(null);
  const [company, setCompany] = useState<string | null>(null);
  const [ruleText, setRuleText] = useState("");
  const [pending, setPending] = useState(false);
  const [job, setJob] = useState<Job | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [jobCharity, setJobCharity] = useState("");
  const [actionError, setActionError] = useState("");
  const [changes, setChanges] = useState<{
    charity: string;
    added: string[];
    removed: string[];
    ruleIds: string[];
  } | null>(null);
  const before = useRef<Portfolio | undefined>(undefined);
  const oldRules = useRef<string[]>([]);
  const jobController = useRef<AbortController | null>(null);
  const baseBusy =
    pending || !!jobId || job?.status === "queued" || job?.status === "running";
  const busy = baseBusy || researchBusy;
  const p = account.data?.portfolio ?? portfolio.data;
  const r = rules.data;
  const current = charities.data?.find((c) => c.charity_id === id);
  useEffect(() => () => jobController.current?.abort(), []);
  useEffect(() => {
    if (id)
      try {
        localStorage.setItem("mandate:selected", id);
      } catch {
        /* optional */
      }
  }, [id]);
  async function start(action: () => Promise<{ job_id: string }>) {
    if (busy) return;
    setPending(true);
    setActionError("");
    setJob(null);
    setChanges(null);
    setJobCharity(id);
    before.current = p;
    oldRules.current = r?.rules.map((x) => x.id) || [];
    try {
      const result = await action();
      if (!result.job_id) throw new Error("The API did not return a job ID.");
      setJobId(result.job_id);
      setJob({
        status: "queued",
        progress: ["Job queued."],
        result: null,
        error: null,
      });
    } catch (error) {
      setActionError(
        error instanceof Error ? error.message : "Unable to start job.",
      );
    } finally {
      setPending(false);
    }
  }
  useEffect(() => {
    if (!jobId) return;
    const controller = new AbortController();
    jobController.current = controller;
    let timer: ReturnType<typeof setTimeout>;
    let started = Date.now();
    async function poll() {
      try {
        const next = await api.job(jobId!, controller.signal);
        if (controller.signal.aborted) return;
        setJob(next);
        setActionError("");
        if (next.status === "done") {
          if (next.result === null) {
            setVersion((v) => v + 1);
            setJobId(null);
            setRuleText("");
            return;
          }
          {
            const result =
              next.result?.charity_id === jobCharity
                ? next.result
                : await request<Portfolio>(
                    paths.portfolio(jobCharity),
                    undefined,
                    controller.signal,
                  );
            if (result.charity_id !== jobCharity)
              throw new Error("API returned a different charity.");
            remember(paths.portfolio(jobCharity), result);
            const prior = new Set(
              before.current?.holdings.map((h) => h.ticker) || [],
            );
            const currentResult = account.data
              ? (
                  await request<Account>(
                    paths.account(jobCharity),
                    undefined,
                    controller.signal,
                  )
                ).portfolio
              : result;
            const after = new Set(currentResult.holdings.map((h) => h.ticker));
            setChanges({
              charity: jobCharity,
              added: [...after].filter((t) => !prior.has(t)),
              removed: [...prior].filter((t) => !after.has(t)),
              ruleIds: oldRules.current,
            });
          }
          setVersion((v) => v + 1);
          setJobId(null);
          setRuleText("");
          return;
        }
        if (next.status === "error") {
          setActionError(
            next.error || "The job failed. Last good portfolio retained.",
          );
          setJobId(null);
          return;
        }
      } catch (error) {
        if (controller.signal.aborted) return;
        setActionError(
          (error instanceof Error
            ? error.message
            : "Job connection interrupted.") +
            " The last good portfolio is retained.",
        );
      }
      if (Date.now() - started > 600000) {
        setActionError(
          "Stopped polling after a long wait. Use Check job to reconnect.",
        );
        setJobId(null);
        setJob((j) => (j ? { ...j, status: "error" } : j));
        return;
      }
      timer = setTimeout(poll, 1000);
    }
    void poll();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [jobId, jobCharity]);
  const logRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [job?.progress]);
  const [lastJobId, setLastJobId] = useState<string | null>(null);
  useEffect(() => {
    if (jobId) setLastJobId(jobId);
  }, [jobId]);
  const changed = changes?.charity === id ? changes : null;
  const totals =
    account.data?.presentation ??
    (id ? presentation(paths.portfolio(id)) : undefined);
  const chart = account.data?.chart ?? p?.holdings ?? [];
  const funnel = id ? presentation(paths.selection(id)) : undefined;
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a className="brand" href="#main" onClick={() => setTab("portfolio")}>
          <span className="brand-mark">M</span>mandate
          <span className="brand-dot">.</span>
        </a>
        <p className="sidebar-note">Investment with evidence.</p>
        <label className="eyebrow" htmlFor="charity">
          Charity mandate
        </label>
        <Status resource={charities} />
        <select
          id="charity"
          value={id}
          disabled={!charities.data}
          onChange={(e) => {
            setSelected(e.target.value);
            setCompany(null);
          }}
        >
          {!charities.data && <option>Waiting for charity API</option>}
          {charities.data?.map((c) => (
            <option key={c.charity_id} value={c.charity_id}>
              {c.name}
            </option>
          ))}
        </select>
        <nav aria-label="Workspace">
          {[
            ["portfolio", "Home"],
            ["research", "Research stock"],
            ["stats", "Stats"],
            ["rejections", "Rejections"],
            ["verify", "To verify"],
            ["decisions", "Agent decisions"],
            ["policy", "Policy & rules"],
            ["compare", "Compare mandates"],
          ].map(([key, label]) => (
            <button
              className={tab === key ? "active" : ""}
              key={key}
              onClick={() => setTab(key)}
            >
              {label}
              <span aria-hidden="true">↗</span>
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <span className="status-dot" /> Evidence-led decisions
          <p>
            Policy first. Sources attached.
            <br />
            Trustees stay in control.
          </p>
        </div>
      </aside>
      <div className="workspace">
        <div className="paper-banner" role="status">Paper portfolio · Recorded purchase costs, not live valuations · No real-money trades</div>
        <header className="topbar">
          <span>Mandate / Research & investment</span>
          <div className="row">
            <button
              className="primary"
              disabled={!id}
              onClick={() => setTab("research")}
            >
              Research stock
            </button>
            <span className="muted">{p?.as_of && `As of ${p.as_of}`}</span>
            <button
              onClick={() => {
                charities.retry();
                setVersion((v) => v + 1);
              }}
            >
              Reload data
            </button>
            <button
              disabled={!id || busy}
              onClick={() => void start(() => api.run(id))}
            >
              Re-run mandate
            </button>
          </div>
        </header>
        <main id="main">
          {purchaseNotice?.charity === id && tab === "portfolio" && (
            <div className="change-strip" role="status">
              {money.format(purchaseNotice.receipt.spent_usd)} allocated to{" "}
              {purchaseNotice.receipt.ticker} ·{" "}
              {number.format(purchaseNotice.receipt.shares)} whole shares. Your
              pot, holdings and pie chart have been updated. Simulated
              investment.
            </div>
          )}
          <div className="page-heading">
            <div>
              <p className="eyebrow">
                Your purpose, reflected in your portfolio
              </p>
              <h1>{current?.name || "Your trustee workspace"}</h1>
              <p className="muted">
                {current?.purpose ||
                  "Connect the charity API to load policies, portfolios and evidence."}
              </p>
            </div>
            <Badge kind="verified">Policy → evidence → decision</Badge>
          </div>
          {!id && (
            <section className="panel">
              <h2>Ready for your charity data</h2>
              <p>
                The workspace will populate when the API is available. Select
                Try again to reconnect.
              </p>
              <p>No investment data has been invented.</p>
            </section>
          )}
          {tab === "compare" ? (
            <Compare charities={charities.data || []} open={setSource} />
          ) : (
            <>
              {tab === "research" && id && (
                <>
                  <Status resource={selection} />
                  <Status resource={portfolio} />
                  <Research
                    key={id}
                    charity={id}
                    name={current?.name || id}
                    selection={selection.data}
                    portfolio={p}
                    externalBusy={!!baseBusy}
                    onBusy={setResearchBusy}
                    onComplete={() => setVersion((v) => v + 1)}
                    onPurchased={(purchase) => {
                      setPurchaseNotice({
                        charity: id,
                        receipt: purchase.receipt,
                      });
                      setVersion((v) => v + 1);
                      setTab("portfolio");
                    }}
                    openSource={setSource}
                  />
                </>
              )}
              {tab === "decisions" && id && (
                <>
                  <Status resource={selection} />
                  <Status resource={portfolio} />
                  <Status resource={rules} />
                  <AgentDecisions
                    key={id}
                    charity={id}
                    selection={selection.data}
                    portfolio={p}
                    rules={r}
                    version={version}
                    open={setSource}
                    refresh={(ticker) => void start(() => api.refresh(ticker, id))}
                    busy={!!busy}
                  />
                </>
              )}
              {tab === "policy" && (
                <>
                  <section className="panel">
                    <p className="eyebrow">The source mandate</p>
                    <h2>Policy text</h2>
                    <Status resource={policy} />
                    {policy.data && (
                      <PolicyEditor
                        key={id}
                        policy={policy.data}
                        revision={account.data?.policy_revision}
                        busy={!!busy}
                        onSave={(text, revision) =>
                          void start(() => api.updatePolicy(id, text, revision))
                        }
                      />
                    )}
                  </section>
                  <section className="panel">
                    <h2>Rules & trustee questions</h2>
                    <Status resource={rules} />
                    {r && (
                      <>
                        <div className="rule-grid">
                          {r.rules.map((rule) => (
                            <article
                              key={rule.id}
                              className={`rule-card ${changed && !changed.ruleIds.includes(rule.id) ? "added" : ""}`}
                            >
                              <div className="row between">
                                <Badge kind={rule.origin}>{rule.origin}</Badge>
                                <span className="muted">
                                  {rule.id} · clause {rule.clause}
                                </span>
                              </div>
                              <h3>{rule.text}</h3>
                              <p>{rule.test}</p>
                              <p className="muted">
                                Threshold: {rule.threshold}
                              </p>
                              {rule.origin === "proposed" && (
                                <label className="toggle">
                                  <input
                                    type="checkbox"
                                    role="switch"
                                    checked={rule.approved}
                                    disabled
                                  />{" "}
                                  {rule.approved
                                    ? "Approved"
                                    : "Awaiting trustee approval"}
                                  <span className="muted">
                                    Approval updates require an API endpoint.
                                  </span>
                                </label>
                              )}
                            </article>
                          ))}
                        </div>
                        <h3>Questions for trustees</h3>
                        <ul>
                          {r.questions.map((q, i) => (
                            <li key={i}>{q}</li>
                          ))}
                        </ul>
                        <div className="weights">
                          <p>
                            Financial weight{" "}
                            <strong>
                              {percent.format(r.weights.financial)}
                            </strong>
                          </p>
                          <p>
                            Risk weight{" "}
                            <strong>{percent.format(r.weights.risk)}</strong>
                          </p>
                        </div>
                        <p>{r.weights_reason}</p>
                      </>
                    )}
                  </section>
                </>
              )}
              {tab === "portfolio" && (
                <>
                  <Status resource={account} />
                  {account.error && !account.data && (
                    <p className="notice">
                      The managed pot is unavailable. The portfolio below is the
                      API’s suggested allocation, not a record of purchases.
                    </p>
                  )}
                  <section className="research-entry">
                    <div>
                      <p className="research-kicker">
                        A considered investment starts here
                      </p>
                      <h2>
                        Get to know the company
                        <br />
                        before it joins your portfolio.
                      </h2>
                      <p>
                        Hear the ethics, financial and risk assessments
                        together, then read the Chair’s conclusion.
                      </p>
                    </div>
                    <div>
                      <button
                        className="primary"
                        onClick={() => setTab("research")}
                      >
                        Research a stock →
                      </button>
                      <button
                        className="text-button"
                        onClick={() => setTab("decisions")}
                      >
                        Explore agent decisions →
                      </button>
                    </div>
                  </section>
                  <Status resource={selection} />
                  {selection.data && (
                    <div className="funnel">
                      <span>
                        <strong>
                          {number.format(selection.data.universe_size)}
                        </strong>{" "}
                        companies
                      </span>
                      <span aria-hidden>→</span>
                      <span>
                        <strong>
                          {number.format(selection.data.after_prefilter)}
                        </strong>{" "}
                        in scope
                      </span>
                      <span aria-hidden>→</span>
                      <span>
                        {funnel?.analysed_count !== undefined ? (
                          <>
                            <strong>
                              {number.format(funnel.analysed_count)}
                            </strong>{" "}
                            analysed
                          </>
                        ) : (
                          "Selected companies analysed"
                        )}
                      </span>
                      <details>
                        <summary>View selection</summary>
                        <div className="chips">
                          {selection.data.selected.map((s) => (
                            <button
                              key={s.ticker}
                              onClick={() => setCompany(s.ticker)}
                              title={s.why}
                            >
                              {s.ticker} · {s.name}
                            </button>
                          ))}
                        </div>
                      </details>
                    </div>
                  )}
                  <Status resource={portfolio} />
                  {p && (
                    <>
                      <section className="hero panel">
                        <div>
                          <p className="eyebrow">
                            A portfolio built around your mandate
                          </p>
                          <h2>
                            {account.data ? (
                              <>
                                Your {money.format(p.total_usd)} investment pot
                              </>
                            ) : (
                              <>
                                Invest {money.format(p.total_usd)}
                                {totals?.total_gbp !== undefined && (
                                  <>
                                    {" "}
                                    (about{" "}
                                    {new Intl.NumberFormat("en-GB", {
                                      style: "currency",
                                      currency: "GBP",
                                      maximumFractionDigits: 0,
                                    }).format(totals.total_gbp)}
                                    )
                                  </>
                                )}
                                {totals?.holdings_count !== undefined ? (
                                  <>
                                    {" "}
                                    across{" "}
                                    {number.format(totals.holdings_count)}{" "}
                                    holdings:
                                  </>
                                ) : (
                                  <>
                                    <br />
                                    <span>
                                      with a reason for every holding.
                                    </span>
                                  </>
                                )}
                              </>
                            )}
                          </h2>
                          {account.data && (
                            <div className="pot-balances">
                              <p>
                                Available to invest
                                <strong>{money.format(p.cash_usd)}</strong>
                              </p>
                              <p>
                                Allocated
                                <strong>
                                  {money.format(account.data.invested_usd)}
                                </strong>
                              </p>
                              <p>
                                Holdings
                                <strong>
                                  {number.format(
                                    account.data.presentation.holdings_count!,
                                  )}
                                </strong>
                              </p>
                            </div>
                          )}
                          {totals?.shares_weight !== undefined &&
                            totals?.bonds_weight !== undefined &&
                            totals?.cash_weight !== undefined && (
                              <p className="allocation-line">
                                {percent.format(totals.shares_weight)} shares,{" "}
                                {percent.format(totals.bonds_weight)} bonds,{" "}
                                {percent.format(totals.cash_weight)} cash.
                              </p>
                            )}
                          <p>
                            Exact shares, visible limits, traceable evidence.
                          </p>
                          <div className="row">
                            <Badge>Cash {money.format(p.cash_usd)}</Badge>
                            <Badge>GBP/USD {p.gbpusd === null ? "Unavailable" : number.format(p.gbpusd)}</Badge>
                          </div>
                          {!totals && (
                            <p className="muted small">
                              Allocation totals and GBP conversion await
                              API-supplied summary fields.
                            </p>
                          )}
                        </div>
                        <div
                          className="donut"
                          role="img"
                          aria-label="Portfolio allocation by holding; weights are from the API"
                        >
                          {chart.length > 0 ? (
                            <ResponsiveContainer width="100%" height={300}>
                              <PieChart>
                                <Pie
                                  data={chart}
                                  dataKey="weight"
                                  nameKey="ticker"
                                  innerRadius="58%"
                                  outerRadius="82%"
                                  paddingAngle={2}
                                  stroke="none"
                                >
                                  {chart.map((h, i) => (
                                    <Cell
                                      key={h.ticker}
                                      fill={colours[i % colours.length]}
                                    />
                                  ))}
                                </Pie>
                                <Tooltip
                                  formatter={(v) =>
                                    typeof v === "number"
                                      ? percent.format(v)
                                      : String(v)
                                  }
                                />
                                <Legend />
                              </PieChart>
                            </ResponsiveContainer>
                          ) : (
                            <p className="empty">Funds are held as cash.</p>
                          )}
                        </div>
                      </section>
                      {changed && (
                        <div className="change-strip" role="status">
                          <strong>Portfolio updated</strong>
                          <p>
                            Added: {changed.added.join(", ") || "No additions"}
                          </p>
                          <p>
                            Removed:{" "}
                            {changed.removed.join(", ") || "No removals"}
                          </p>
                          <button
                            className="text-button"
                            onClick={() => setTab("policy")}
                          >
                            Review updated rules →
                          </button>
                        </div>
                      )}
                      <section className="panel">
                        <div className="section-heading">
                          <div>
                            <p className="eyebrow">
                              {account.data
                                ? "Your current allocation"
                                : "The proposed allocation"}
                            </p>
                            <h2>Holdings & their reasons</h2>
                          </div>
                          <p className="muted">
                            Click a ticker to open its analyst review.
                          </p>
                        </div>
                        <div className="table-scroll">
                          <table>
                            <thead>
                              <tr>
                                {[
                                  "Company",
                                  "Allocation",
                                  "Shares",
                                  "Weight / cap",
                                  "Decision",
                                  "Reason & evidence",
                                  "",
                                ].map((x, i) => (
                                  <th key={i}>{x}</th>
                                ))}
                              </tr>
                            </thead>
                            <tbody>
                              {p.holdings.map((h) => {
                                return (
                                  <tr
                                    key={h.ticker}
                                    className={
                                      changed?.added.includes(h.ticker)
                                        ? "added"
                                        : ""
                                    }
                                  >
                                    <td>
                                      <button
                                        className="ticker"
                                        onClick={() => setCompany(h.ticker)}
                                      >
                                        {h.ticker} ↗
                                      </button>
                                      <span className="company-name">
                                        {h.name}
                                      </span>
                                      <Badge>
                                        {h.is_bond ? "Bond ETF" : "Shares"}
                                      </Badge>
                                    </td>
                                    <td className="numeric">
                                      {money.format(h.usd)}
                                    </td>
                                    <td className="numeric">
                                      {number.format(h.shares)}
                                    </td>
                                    <td className="numeric">
                                      {percent.format(h.weight)}
                                      <br />
                                      <span className="muted">
                                        cap {percent.format(h.cap)}
                                      </span>
                                    </td>
                                    <td>
                                      <HoldingDecision
                                        charity={id}
                                        ticker={h.ticker}
                                        bond={h.is_bond}
                                        version={version}
                                      />
                                    </td>
                                    <td className="reason-cell">
                                      <p>{h.reason}</p>
                                      <Chips
                                        ids={h.source_ids}
                                        open={setSource}
                                      />
                                    </td>
                                    <td>
                                      <button
                                        disabled={busy}
                                        onClick={() =>
                                          void start(() =>
                                            api.refresh(h.ticker, id),
                                          )
                                        }
                                        aria-label={`Refresh ${h.ticker}`}
                                      >
                                        Refresh ↻
                                      </button>
                                    </td>
                                  </tr>
                                );
                              })}
                            </tbody>
                          </table>
                          {!p.holdings.length && (
                            <p className="empty">
                              No stocks purchased yet. Research a stock, then
                              choose how much to allocate from your pot.
                            </p>
                          )}
                        </div>
                      </section>
                    </>
                  )}
                </>
              )}
              {tab === "stats" && p && (
                <>
              <h2>Suggested portfolio stats</h2>
                  <Status resource={account} />
                  <StatsDetails p={portfolio.data ?? p} r={r} rules={rules} />
                </>
              )}
              {tab === "rejections" && p && (
                <section className="panel">
                  <h2>Rejections</h2>
                  <p>
                    Companies excluded by the current policy or investment
                    assessment.
                  </p>
                  <Status resource={account} />
                  {p.rejected.map((d) => (
                    <Rejected
                      key={d.ticker}
                      decision={d}
                      charity={id}
                      version={version}
                      open={setSource}
                      company={setCompany}
                    />
                  ))}
                  {!p.rejected.length && <p>No rejections returned.</p>}
                </section>
              )}
              {tab === "verify" && p && (
                <section className="panel">
                  <h2>To verify</h2>
                  <Status resource={account} />
                  {account.data?.to_verify.map((item) => (
                    <article className="rejection" key={"held-" + item.ticker}>
                      <button
                        className="ticker"
                        onClick={() => setCompany(item.ticker)}
                      >
                        {item.ticker} · {item.name} · Held stock needs review ↗
                      </button>
                      <p>{item.reason}</p>
                      <p>
                        The position stays visible on Home. Additional purchases
                        are blocked.
                      </p>
                    </article>
                  ))}
                  {p.trustee_review.map((d) => (
                    <article className="rejection" key={d.ticker}>
                      <button
                        className="ticker"
                        onClick={() => setCompany(d.ticker)}
                      >
                        {d.ticker} · {d.name} ↗
                      </button>
                      <p>{d.reason}</p>
                      <Chips ids={d.source_ids} open={setSource} />
                    </article>
                  ))}
                  <h3>Trustee questions</h3>
                  <ul>
                    {r?.questions.map((question, i) => (
                      <li key={i}>{question}</li>
                    ))}
                  </ul>
                  {!p.trustee_review.length &&
                    !account.data?.to_verify.length && (
                      <p>No companies awaiting verification.</p>
                    )}
                </section>
              )}
              {tab !== "research" && (
                <section className="panel live-rule">
                  <div>
                    <p className="eyebrow">Put the mandate to the test</p>
                    <h2>Add the judge’s rule</h2>
                    <p>
                      The agents reassess the evidence and rebuild the
                      portfolio.
                    </p>
                  </div>
                  <form
                    onSubmit={(e) => {
                      e.preventDefault();
                      if (ruleText.trim())
                        void start(() => api.addRule(id, ruleText.trim()));
                    }}
                  >
                    <label htmlFor="judge-rule">New rule</label>
                    <textarea
                      id="judge-rule"
                      value={ruleText}
                      onChange={(e) => setRuleText(e.target.value)}
                      placeholder="Type the judge’s sentence…"
                      required
                      disabled={busy || !id}
                    />
                    <button
                      className="primary"
                      disabled={busy || !id || !ruleText.trim()}
                    >
                      {pending
                        ? "Starting…"
                        : busy
                          ? "Working…"
                          : "Apply rule →"}
                    </button>
                  </form>
                  {actionError && (
                    <div className="notice" role="alert">
                      {actionError}
                      {!jobId && lastJobId && (
                        <button
                          onClick={() => {
                            setJobId(lastJobId);
                            setJob((j) =>
                              j ? { ...j, status: "running" } : j,
                            );
                          }}
                        >
                          Check job
                        </button>
                      )}
                    </div>
                  )}
                  {job && (
                    <div className="job-panel">
                      <Badge>{job.status}</Badge>
                      <p>
                        {charities.data?.find(
                          (c) => c.charity_id === jobCharity,
                        )?.name || jobCharity}
                      </p>
                      <div
                        className="live-log"
                        ref={logRef}
                        role="log"
                        aria-live="polite"
                        aria-label="Job progress"
                      >
                        {job.progress.map((message, i) => (
                          <p key={i}>› {message}</p>
                        ))}
                      </div>
                    </div>
                  )}
                </section>
              )}
            </>
          )}
        </main>
        <footer>Educational hackathon project. Not financial advice.</footer>
      </div>
      {company && id && (
        <CompanyDrawer
          key={id + company}
          charity={id}
          ticker={company}
          version={version}
          close={() => setCompany(null)}
          openSource={setSource}
          refresh={(ticker) => void start(() => api.refresh(ticker, id))}
          busy={!!busy}
        />
      )}
      {source && (
        <SourceDrawer key={source} id={source} close={() => setSource(null)} />
      )}
    </div>
  );
}
function RiskCard({
  title,
  value,
  ok,
  limit,
}: {
  title: string;
  value: string;
  ok?: boolean;
  limit?: string;
}) {
  return (
    <article
      className={`risk-card ${ok === undefined ? "" : ok ? "pass" : "fail"}`}
    >
      <p>{title}</p>
      <strong>{value}</strong>
      {limit && (
        <small>
          {ok ? "✓" : "!"} {limit}
        </small>
      )}
    </article>
  );
}
function HoldingDecision({
  charity,
  ticker,
  bond,
  version,
}: {
  charity: string;
  ticker: string;
  bond: boolean;
  version: number;
}) {
  const report = useResource<CompanyReport>(
    bond ? null : paths.company(charity, ticker),
    version,
  );
  if (bond) return <Badge>Bond constraint</Badge>;
  return report.data ? (
    <DecisionBadge decision={report.data.decision} />
  ) : (
    <>
      <span className="muted">
        {report.error ? "Decision unavailable" : "Loading decision…"}
      </span>
      {report.error && (
        <button className="text-button" onClick={report.retry}>
          Retry
        </button>
      )}
    </>
  );
}
