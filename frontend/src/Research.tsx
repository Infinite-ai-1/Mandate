import { useEffect, useRef, useState } from "react";
import {
  api,
  paths,
  request,
  researchSummary,
  type CompanyReport,
  type Portfolio,
  type Selection,
  type ResearchAgent,
  type ResearchSummary,
  type Job,
} from "./api";
import type { Purchase } from "./api";
import InvestmentPanel from "./InvestmentPanel";

const agents: ResearchAgent[] = ["melchior", "balthasar", "casper"];
const names = {
  melchior: "Melchior",
  balthasar: "Balthasar",
  casper: "Casper",
};
const roles = {
  melchior: "Ethics & the charity’s mandate",
  balthasar: "Financial health & the investment case",
  casper: "Risk & resilience",
};
const voteLabel = {
  INVEST: "Invest",
  DO_NOT_INVEST: "Do not invest",
  REVIEW: "Needs review",
};
const ratingLabel = {
  STRONG_BUY: "Strong buy",
  BUY: "Buy",
  REJECT: "Reject",
  REVIEW: "Trustee review",
};
const format = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 1 });
function wait(signal: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    const cancel = () => {
      clearTimeout(timer);
      reject(new DOMException("Aborted", "AbortError"));
    };
    const timer = setTimeout(() => {
      signal.removeEventListener("abort", cancel);
      resolve();
    }, 1000);
    signal.addEventListener("abort", cancel, { once: true });
    if (signal.aborted) cancel();
  });
}
export function parseAgentProgress(progress: string[], agent: ResearchAgent) {
  const pattern = new RegExp(`^\\[${agent}(:done)?\\]\\s*(.*)$`, "i");
  return progress.flatMap((message) => {
    const match = pattern.exec(message);
    return match ? [{ done: !!match[1], text: match[2] }] : [];
  });
}

export default function Research({
  charity,
  name,
  selection,
  portfolio,
  externalBusy,
  onBusy,
  onComplete,
  openSource,
  onPurchased,
}: {
  charity: string;
  name: string;
  selection?: Selection;
  portfolio?: Portfolio;
  externalBusy: boolean;
  onBusy: (busy: boolean) => void;
  onComplete: () => void;
  openSource: (id: string) => void;
  onPurchased?: (purchase: Purchase) => void;
}) {
  const tickers = [
    ...new Set([
      ...(selection?.selected.map((s) => s.ticker) || []),
      ...(portfolio?.holdings.filter((h) => !h.is_bond).map((h) => h.ticker) ||
        []),
      ...(portfolio?.rejected.map((d) => d.ticker) || []),
      ...(portfolio?.trustee_review.map((d) => d.ticker) || []),
    ]),
  ];
  const [chosen, setChosen] = useState("");
  const ticker = tickers.includes(chosen) ? chosen : tickers[0] || "";
  const [active, setActive] = useState("");
  const [phase, setPhase] = useState<"choose" | "running" | "done" | "error">(
    "choose",
  );
  const [progress, setProgress] = useState<string[]>([]);
  const [error, setError] = useState("");
  const [jobId, setJobId] = useState("");
  const [result, setResult] = useState<{
    report: CompanyReport;
    summary?: ResearchSummary;
  } | null>(null);
  const [history, setHistory] = useState<
    { report: CompanyReport; summary?: ResearchSummary }[]
  >([]);
  const [run, setRun] = useState(0);
  const controller = useRef<AbortController | null>(null);
  const chair = useRef<HTMLElement | null>(null);
  const stage = useRef<HTMLElement | null>(null);
  const running = phase === "running";
  useEffect(() => {
    onBusy(running);
    return () => onBusy(false);
  }, [running, onBusy]);
  useEffect(() => () => controller.current?.abort(), []);
  useEffect(() => {
    if (phase === "running") {
      stage.current?.scrollIntoView?.({
        behavior: window.matchMedia?.("(prefers-reduced-motion: reduce)")
          .matches
          ? "instant"
          : "smooth",
        block: "start",
      });
      return;
    }
    if (phase !== "done") return;
    const timer = setTimeout(
      () =>
        chair.current?.scrollIntoView?.({
          behavior: window.matchMedia?.("(prefers-reduced-motion: reduce)")
            .matches
            ? "instant"
            : "smooth",
          block: "start",
        }),
      850,
    );
    return () => clearTimeout(timer);
  }, [phase]);
  async function follow(id: string, stock: string, signal: AbortSignal) {
    const started = Date.now();
    while (!signal.aborted) {
      const job: Job = await api.job(id, signal);
      if (signal.aborted) return;
      setProgress(job.progress);
      if (job.status === "error")
        throw new Error(job.error || "Research could not be completed.");
      if (job.status === "done") {
        const path = paths.company(charity, stock);
        const report = await request<CompanyReport>(path, undefined, signal);
        if (signal.aborted) return;
        if (report.decision.ticker !== stock)
          throw new Error("The API returned a different stock.");
        const completed = { report, summary: researchSummary(path) };
        setResult(completed);
        setHistory((previous) => [
          ...previous.filter((item) => item.report.decision.ticker !== stock),
          completed,
        ]);
        setPhase("done");
        onComplete();
        return;
      }
      if (Date.now() - started > 600000)
        throw new Error(
          "Research is taking longer than expected. Check the same job again to reconnect.",
        );
      await wait(signal);
    }
  }
  async function begin(resume = false) {
    if (running || externalBusy || !ticker) return;
    controller.current?.abort();
    const next = new AbortController();
    controller.current = next;
    setError("");
    setPhase("running");
    setRun((r) => r + 1);
    const stock = resume ? active : ticker;
    setActive(stock);
    if (!resume) {
      setProgress([]);
      setJobId("");
    }
    try {
      const id = resume
        ? jobId
        : (await api.refresh(stock, charity, next.signal)).job_id;
      if (!id) throw new Error("The API did not return a research job.");
      setJobId(id);
      await follow(id, stock, next.signal);
    } catch (cause) {
      if (!next.signal.aborted) {
        setError(
          cause instanceof Error
            ? cause.message
            : "Research connection interrupted.",
        );
        setPhase("error");
      }
    }
  }
  function sources(ids: string[]) {
    return (
      <span className="research-sources">
        {ids.map((id) => (
          <a
            key={id}
            href={paths.source(id)}
            onClick={(event) => {
              event.preventDefault();
              openSource(id);
            }}
          >
            {id} ↗
          </a>
        ))}
      </span>
    );
  }
  const summary = result?.summary;
  const showResult =
    (phase === "done" || phase === "error") &&
    result?.report.decision.ticker === active;
  return (
    <div className="research-page">
      <section className="research-intro">
        <p className="research-kicker">Stock research</p>
        <h2>
          Before you invest,
          <br />
          <em>hear the whole case.</em>
        </h2>
        <p>
          One company, considered from three perspectives.
          <br />
          Research for <strong>{name}</strong>.
        </p>
        <form
          className="research-form"
          onSubmit={(event) => {
            event.preventDefault();
            void begin();
          }}
        >
          <div>
            <label htmlFor="research-ticker">
              Which stock would you like to research?
            </label>
            <select
              id="research-ticker"
              value={ticker}
              onChange={(event) => setChosen(event.target.value)}
              disabled={running || !ticker}
            >
              {!ticker && <option>Waiting for selected companies</option>}
              {tickers.map((t) => (
                <option key={t} value={t}>
                  {t}
                  {portfolio?.holdings.find((h) => h.ticker === t)?.name &&
                  portfolio.holdings.find((h) => h.ticker === t)?.name !== t
                    ? ` · ${portfolio.holdings.find((h) => h.ticker === t)?.name}`
                    : ""}
                </option>
              ))}
            </select>
          </div>
          <button
            className="primary"
            disabled={running || externalBusy || !ticker}
          >
            {running ? "Researching…" : "Research stock →"}
          </button>
        </form>
        <p className="research-caption">
          The agents read stored evidence. Their activity appears below as the
          API reports it.
        </p>
      </section>
      {phase !== "choose" && (
        <>
          <section
            ref={stage}
            className="research-stage"
            aria-label="Live agent assessments"
          >
            <div className="research-section-title">
              <h3>
                {active} <span>— the three perspectives</span>
              </h3>
              <p role="status">
                {running
                  ? "Research in progress"
                  : phase === "done"
                    ? "Assessments received"
                    : "Research interrupted"}
              </p>
            </div>
            <div className="research-agents">
              {agents.map((agent) => {
                const messages = parseAgentProgress(progress, agent);
                const finished =
                  phase === "done" || messages.some((m) => m.done);
                const report = showResult ? result.report[agent] : null;
                const vote = showResult ? summary?.votes[agent] : null;
                return (
                  <article
                    key={agent + run}
                    className={`research-agent ${finished ? "is-complete" : ""}`}
                    aria-label={`${names[agent]} research card`}
                  >
                    <header>
                      <div>
                        <h3>{names[agent]}</h3>
                        <p>{roles[agent]}</p>
                      </div>
                      <span
                        className={`agent-indicator ${finished ? "complete" : running ? "working" : "interrupted"}`}
                      >
                        {finished
                          ? "✓ Complete"
                          : running
                            ? "Working"
                            : "Interrupted"}
                      </span>
                    </header>
                    <div
                      className="research-activity"
                      role="log"
                      aria-live="polite"
                      aria-label={`${names[agent]} activity`}
                    >
                      {messages.length ? (
                        messages.map((message, i) => (
                          <p key={i}>{message.text}</p>
                        ))
                      ) : (
                        <p className="muted">
                          {running
                            ? "Waiting for an agent update from the API."
                            : "No individual progress messages were supplied."}
                        </p>
                      )}
                    </div>
                    {report && result && (
                      <div className="agent-finding">
                        <p className="model-label">{report.model}</p>
                        <h4>
                          {vote ? voteLabel[vote] : "Assessment received"}
                        </h4>
                        {agent === "melchior" ? (
                          result.report.melchior.verdicts.map((v, i) => (
                            <div key={i}>
                              <p>
                                <strong>
                                  {v.rule_id} · {v.verdict}
                                </strong>{" "}
                                — {v.reason}
                              </p>
                              <blockquote>{v.quote}</blockquote>
                              <p className="verification-note">
                                {v.verified === true
                                  ? "✓ Quote verified"
                                  : v.verified === false
                                    ? "Quote not verified"
                                    : "Verification pending"}
                              </p>
                              {sources([v.source_id])}
                            </div>
                          ))
                        ) : (
                          <>
                            <p>
                              {
                                result.report[agent as "balthasar" | "casper"]
                                  .summary
                              }
                            </p>
                            {result.report[
                              agent as "balthasar" | "casper"
                            ].reasons.map((reason, i) => (
                              <div key={i}>
                                <p>{reason.claim}</p>
                                {sources(reason.source_ids)}
                              </div>
                            ))}
                          </>
                        )}
                      </div>
                    )}
                  </article>
                );
              })}
            </div>
            <details className="research-run-log">
              <summary>View the full progress log</summary>
              <div role="log" aria-label="Research progress">
                {progress.map((message, i) => (
                  <p key={i}>{message}</p>
                ))}
              </div>
            </details>
          </section>
          {error && (
            <div className="notice" role="alert">
              <p>
                {error} Your previous completed assessment, if available, is
                retained below.
              </p>
              <button
                disabled={externalBusy}
                onClick={() => void begin(!!jobId)}
              >
                {jobId ? "Check the same job" : "Try again"}
              </button>
            </div>
          )}
          {showResult && (
            <section
              ref={chair}
              className="research-chair"
              aria-label="Chair findings"
            >
              <div className="chair-byline">
                <span className="chair-seal">M</span>
                <div>
                  <p className="research-kicker">The Chair’s findings</p>
                  <p>
                    {name} · {active}
                    {phase === "error" ? " · Previous assessment" : ""}
                  </p>
                </div>
              </div>
              <div className="chair-verdict">
                <div>
                  <p className="verdict-label">
                    {summary?.recommendation
                      ? ratingLabel[summary.recommendation]
                      : "Decision received"}
                  </p>
                  <h2>
                    {summary?.chair_reason || result.report.decision.reason}
                  </h2>
                  {sources(result.report.decision.source_ids)}
                </div>
                <div className="ethics-measure">
                  <span>Verified ethics score</span>
                  <strong>
                    {summary?.ethics_score === null ||
                    summary?.ethics_score === undefined
                      ? "Unavailable"
                      : format.format(summary.ethics_score)}
                    {summary?.ethics_score !== null &&
                      summary?.ethics_score !== undefined && (
                        <small> / 100</small>
                      )}
                  </strong>
                  <p>
                    {summary?.ethics_definition ||
                      "The API has not supplied a verified ethics measure."}
                  </p>
                </div>
              </div>
              <div className="research-voting">
                <h3>Where the committee stands</h3>
                {summary ? (
                  <>
                    <div className="vote-list">
                      {agents.map((agent) => (
                        <p key={agent}>
                          <strong>{names[agent]}</strong>
                          <span>
                            {summary.votes[agent]
                              ? voteLabel[summary.votes[agent]!]
                              : "Vote not supplied"}
                          </span>
                        </p>
                      ))}
                    </div>
                    {summary.invest_votes !== null && (
                      <p>
                        {format.format(summary.invest_votes)} of three agents
                        favour investing.
                        {summary.consensus && (
                          <>
                            {" "}
                            Committee consensus:{" "}
                            <strong>{ratingLabel[summary.consensus]}</strong>.
                          </>
                        )}
                      </p>
                    )}
                    {summary.ethics_blocked && (
                      <p className="ethics-override">
                        Ethics veto: verified evidence fails the mandate. A
                        majority in favour cannot override this exclusion.
                      </p>
                    )}
                    {summary.consensus === null && (
                      <p className="muted">
                        A consensus label needs explicit financial and risk
                        votes from the API. Scores are not converted into votes.
                      </p>
                    )}
                  </>
                ) : (
                  <p>
                    The API has not supplied explicit votes. No majority rating
                    has been invented.
                  </p>
                )}
                <p className="research-caption">
                  Three invest votes: strong buy. Two: buy. Two votes against:
                  reject. Unresolved evidence goes to trustees. Ethics
                  exclusions take priority.
                </p>
              </div>
              <div className="research-reasons">
                {(["ethics", "financial", "risk"] as const).map((area) => (
                  <section key={area}>
                    <p className="research-kicker">
                      {area === "financial"
                        ? "Financial case"
                        : area === "ethics"
                          ? "Ethics case"
                          : "Risk case"}
                    </p>
                    <p>
                      {summary?.rationale[area] ||
                        (area === "ethics"
                          ? result.report.melchior.verdicts
                              .map((v) => v.reason)
                              .join(" ")
                          : result.report[
                              area === "financial" ? "balthasar" : "casper"
                            ].summary)}
                    </p>
                  </section>
                ))}
              </div>
              {onPurchased && (
                <InvestmentPanel
                  key={active + run}
                  charity={charity}
                  ticker={active}
                  onPurchased={onPurchased}
                />
              )}
              <p className="research-caption">
                These findings describe the research assessment. Exact holdings
                still come from the constrained portfolio optimiser. Past
                performance, not a forecast.
              </p>
            </section>
          )}
          {history.length > 0 && (
            <section className="research-history">
              <p className="research-kicker">This research session · {name}</p>
              <h3>The stocks you’ve considered</h3>
              <div className="research-history-list">
                {history.map((item) => (
                  <article key={item.report.decision.ticker}>
                    <div className="history-heading">
                      <strong>{item.report.decision.ticker}</strong>
                      <span>
                        {item.summary?.recommendation
                          ? ratingLabel[item.summary.recommendation]
                          : "Assessment received"}
                      </span>
                    </div>
                    <p>{item.report.decision.reason}</p>
                    {item.summary && (
                      <div className="history-reasons">
                        <p>
                          <strong>Ethics</strong>{" "}
                          {item.summary.rationale.ethics}
                        </p>
                        <p>
                          <strong>Financial</strong>{" "}
                          {item.summary.rationale.financial}
                        </p>
                        <p>
                          <strong>Risk</strong> {item.summary.rationale.risk}
                        </p>
                      </div>
                    )}
                    {sources(item.report.decision.source_ids)}
                  </article>
                ))}
              </div>
            </section>
          )}
        </>
      )}
    </div>
  );
}
