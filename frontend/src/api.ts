/** Single API boundary. Types follow AGENTS.md; no market or portfolio calculations here. */
export type Origin = "policy" | "proposed" | "assumed" | "judge";
export type DecisionKind =
  "APPROVE" | "APPROVE_CAPPED" | "REJECT" | "TRUSTEE_REVIEW";
export interface Charity {
  charity_id: string;
  name: string;
  purpose: string;
}
export interface Rule {
  id: string;
  clause: string;
  text: string;
  test: string;
  threshold: string;
  keywords: string[];
  origin: Origin;
  approved: boolean;
}
export interface Rules extends Charity {
  rules: Rule[];
  constraints: {
    max_weight: number;
    min_bonds: number;
    min_yield: number;
    max_drawdown: number;
  };
  constraint_origin: Record<string, Origin>;
  weights: { financial: number; risk: number };
  weights_reason: string;
  questions: string[];
  screening_hints: { exclude_sic: string[]; prefer_sic: string[] };
}
export interface Selection {
  charity_id: string;
  universe_size: number;
  after_prefilter: number;
  excluded_by_sic: { ticker: string; sic: string; rule_id: string }[];
  selected: { ticker: string; why: string }[];
}
export interface Decision {
  ticker: string;
  decision: DecisionKind;
  cap: number;
  decided_by: "code_veto" | "prefilter" | "chair";
  reason: string;
  source_ids: string[];
  weighted_score: number | null;
}
export interface Holding {
  ticker: string;
  name: string;
  is_bond: boolean;
  usd: number;
  shares: number;
  price: number;
  weight: number;
  cap: number;
  reason: string;
  source_ids: string[];
}
export interface Source {
  source_id: string;
  ticker: string;
  kind: string;
  origin: string;
  title: string;
  date: string;
  url: string;
  section: string;
}
export interface Verdict {
  rule_id: string;
  verdict: "PASS" | "FAIL" | "FLAG";
  confidence: number;
  quote: string;
  source_id: string;
  reason: string;
  verified: boolean | null;
}
export interface EthicsOutput {
  ticker: string;
  agent: "melchior";
  model: string;
  verdicts: Verdict[];
}
export interface ScoreOutput {
  ticker: string;
  agent: "balthasar" | "casper";
  model: string;
  score: number;
  reasons: { claim: string; source_ids: string[]; verified: boolean | null }[];
  summary: string;
}
export interface CompanyReport {
  melchior: EthicsOutput;
  balthasar: ScoreOutput;
  casper: ScoreOutput;
  decision: Decision;
}
export interface Portfolio {
  charity_id: string;
  total_usd: number;
  gbpusd: number;
  as_of: string;
  holdings: Holding[];
  cash_usd: number;
  risk: {
    worst_12m: number;
    yield: number;
    volatility: number;
    vs_6040_return: number;
  };
  checks: { max_drawdown_ok: boolean; yield_ok: boolean; bonds_ok: boolean };
  relaxed: string[];
  rejected: Decision[];
  trustee_review: Decision[];
  memo: string;
  devils_advocate: string[];
  run_stats: {
    seconds: number;
    llm_calls: number;
    tokens: number;
    by_agent: Record<string, unknown>;
  };
}
export interface Job {
  status: "queued" | "running" | "done" | "error";
  progress: string[];
  result: Portfolio | null;
  error: string | null;
}
export interface CompareRow {
  charity_id: string;
  decision: Decision;
}
export interface Presentation {
  holdings_count?: number;
  total_gbp?: number;
  shares_weight?: number;
  bonds_weight?: number;
  cash_weight?: number;
  analysed_count?: number;
}

export const paths = {
  charities: "/api/charities",
  policy: (id: string) => `/api/charities/${encodeURIComponent(id)}/policy`,
  rules: (id: string) => `/api/charities/${encodeURIComponent(id)}/rules`,
  selection: (id: string) =>
    `/api/charities/${encodeURIComponent(id)}/selection`,
  portfolio: (id: string) =>
    `/api/charities/${encodeURIComponent(id)}/portfolio`,
  company: (id: string, ticker: string) =>
    `/api/charities/${encodeURIComponent(id)}/companies/${encodeURIComponent(ticker)}`,
  source: (id: string) => `/api/sources/${encodeURIComponent(id)}`,
  compare: (ticker: string) => `/api/compare/${encodeURIComponent(ticker)}`,
  run: (id: string) => `/api/charities/${encodeURIComponent(id)}/run`,
  refresh: (ticker: string) =>
    `/api/companies/${encodeURIComponent(ticker)}/refresh`,
  job: (id: string) => `/api/jobs/${encodeURIComponent(id)}`,
};
const memory = new Map<string, unknown>();
type Obj = Record<string, unknown>;
const obj = (x: unknown): x is Obj =>
  !!x && typeof x === "object" && !Array.isArray(x);
const str = (x: unknown) => typeof x === "string";
const num = (x: unknown) => typeof x === "number" && Number.isFinite(x);
const array = (x: unknown, test: (x: unknown) => boolean): boolean =>
  Array.isArray(x) && x.every(test);
const strings = (x: unknown) => array(x, str);
const fields = (x: unknown, keys: string[], test: (x: unknown) => boolean) =>
  obj(x) && keys.every((k) => test(x[k]));
const decision = (x: unknown) =>
  fields(x, ["ticker", "decision", "decided_by", "reason"], str) &&
  fields(x, ["cap"], num) &&
  obj(x) &&
  strings(x.source_ids) &&
  (x.weighted_score === null || num(x.weighted_score)) &&
  ["APPROVE", "APPROVE_CAPPED", "REJECT", "TRUSTEE_REVIEW"].includes(
    String(x.decision),
  ) &&
  ["code_veto", "prefilter", "chair"].includes(String(x.decided_by));
const holding = (x: unknown) =>
  fields(x, ["ticker", "name", "reason"], str) &&
  fields(x, ["usd", "shares", "price", "weight", "cap"], num) &&
  obj(x) &&
  typeof x.is_bond === "boolean" &&
  strings(x.source_ids);
const score = (x: unknown) =>
  fields(x, ["ticker", "agent", "model", "summary"], str) &&
  fields(x, ["score"], num) &&
  obj(x) &&
  array(
    x.reasons,
    (r) =>
      obj(r) &&
      str(r.claim) &&
      strings(r.source_ids) &&
      (r.verified === null || typeof r.verified === "boolean"),
  );
const verdict = (x: unknown) =>
  fields(x, ["rule_id", "verdict", "quote", "source_id", "reason"], str) &&
  fields(x, ["confidence"], num) &&
  obj(x) &&
  ["PASS", "FAIL", "FLAG"].includes(String(x.verdict)) &&
  (x.verified === null || typeof x.verified === "boolean");
const portfolio = (x: unknown) =>
  obj(x) &&
  fields(x, ["charity_id", "as_of", "memo"], str) &&
  fields(x, ["total_usd", "gbpusd", "cash_usd"], num) &&
  array(x.holdings, holding) &&
  array(x.rejected, decision) &&
  array(x.trustee_review, decision) &&
  strings(x.relaxed) &&
  strings(x.devils_advocate) &&
  fields(x.risk, ["worst_12m", "yield", "volatility", "vs_6040_return"], num) &&
  fields(
    x.checks,
    ["max_drawdown_ok", "yield_ok", "bonds_ok"],
    (v) => typeof v === "boolean",
  ) &&
  fields(x.run_stats, ["seconds", "llm_calls", "tokens"], num) &&
  obj(x.run_stats) &&
  obj(x.run_stats.by_agent);
/** Validate before caching: malformed responses must never replace last good data. */
export function validatePayload(
  path: string,
  data: unknown,
  post = false,
): boolean {
  if (post) return obj(data) && str(data.job_id);
  if (path === paths.charities)
    return array(data, (x) =>
      fields(x, ["charity_id", "name", "purpose"], str),
    );
  if (path.startsWith("/api/jobs/"))
    return (
      obj(data) &&
      ["queued", "running", "done", "error"].includes(String(data.status)) &&
      strings(data.progress) &&
      (data.result === null || portfolio(data.result)) &&
      (data.error === null || str(data.error))
    );
  if (path.startsWith("/api/sources/"))
    return fields(
      data,
      [
        "source_id",
        "ticker",
        "kind",
        "origin",
        "title",
        "date",
        "url",
        "section",
      ],
      str,
    );
  if (path.startsWith("/api/compare/"))
    return array(
      data,
      (x) => obj(x) && str(x.charity_id) && decision(x.decision),
    );
  if (path.includes("/companies/"))
    return (
      obj(data) &&
      obj(data.melchior) &&
      fields(data.melchior, ["ticker", "agent", "model"], str) &&
      array(data.melchior.verdicts, verdict) &&
      score(data.balthasar) &&
      score(data.casper) &&
      decision(data.decision)
    );
  if (path.endsWith("/portfolio")) return portfolio(data);
  if (path.endsWith("/policy")) return fields(data, ["text"], str);
  if (path.endsWith("/selection"))
    return (
      obj(data) &&
      str(data.charity_id) &&
      fields(data, ["universe_size", "after_prefilter"], num) &&
      array(data.selected, (x) => fields(x, ["ticker", "why"], str)) &&
      array(data.excluded_by_sic, (x) =>
        fields(x, ["ticker", "sic", "rule_id"], str),
      )
    );
  if (path.endsWith("/rules"))
    return (
      obj(data) &&
      fields(data, ["charity_id", "name", "purpose", "weights_reason"], str) &&
      strings(data.questions) &&
      obj(data.constraint_origin) &&
      obj(data.screening_hints) &&
      strings(data.screening_hints.exclude_sic) &&
      strings(data.screening_hints.prefer_sic) &&
      fields(data.weights, ["financial", "risk"], num) &&
      fields(
        data.constraints,
        ["max_weight", "min_bonds", "min_yield", "max_drawdown"],
        num,
      ) &&
      array(
        data.rules,
        (x) =>
          fields(
            x,
            ["id", "clause", "text", "test", "threshold", "origin"],
            str,
          ) &&
          obj(x) &&
          strings(x.keywords) &&
          typeof x.approved === "boolean" &&
          ["policy", "proposed", "assumed", "judge"].includes(String(x.origin)),
      )
    );
  return obj(data) || Array.isArray(data);
}
export function cached<T>(path: string): T | undefined {
  if (memory.has(path)) return memory.get(path) as T;
  try {
    const item = localStorage.getItem(`mandate:${path}`);
    const data = item ? JSON.parse(item) : undefined;
    return validatePayload(path, data) ? (data as T) : undefined;
  } catch {
    return undefined;
  }
}
export function remember<T>(path: string, data: T) {
  memory.set(path, data);
  memory.delete("presentation:" + path);
  try {
    localStorage.setItem(`mandate:${path}`, JSON.stringify(data));
    localStorage.removeItem(`mandate:presentation:${path}`);
  } catch {
    /* memory cache still works */
  }
}
export function presentation(path: string): Presentation | undefined {
  if (memory.has("presentation:" + path))
    return memory.get("presentation:" + path) as Presentation;
  try {
    const value = localStorage.getItem(`mandate:presentation:${path}`);
    if (value) return JSON.parse(value);
  } catch {
    /* optional */
  }
  return undefined;
}
export async function request<T>(
  path: string,
  body?: unknown,
  signal?: AbortSignal,
): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15000);
  const abort = () => controller.abort();
  signal?.addEventListener("abort", abort, { once: true });
  if (signal?.aborted) controller.abort();
  try {
    const response = await fetch(path, {
      method: body === undefined ? "GET" : "POST",
      headers: {
        Accept: "application/json",
        ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
      },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
    });
    if (response.headers.get("X-Mandate-Data") === "synthetic")
      document.documentElement.dataset.demo = "synthetic";
    let data: unknown;
    try {
      data = await response.json();
    } catch {
      throw new Error("The API returned an unreadable response.");
    }
    if (!response.ok)
      throw new Error(
        typeof data === "object" && data && "error" in data
          ? String(data.error)
          : `Request failed (${response.status}).`,
      );
    if (!validatePayload(path, data, body !== undefined))
      throw new Error(
        "The API returned data that does not match the project contract.",
      );
    if (body === undefined) {
      remember(path, data);
      try {
        const header = response.headers.get("X-Mandate-Presentation");
        const summary = header ? JSON.parse(header) : null;
        if (obj(summary) && Object.values(summary).every(num)) {
          memory.set("presentation:" + path, summary);
          try {
            localStorage.setItem(
              `mandate:presentation:${path}`,
              JSON.stringify(summary),
            );
          } catch {
            /* memory retained */
          }
        }
      } catch {
        /* Display API data without optional presentation totals. */
      }
    }
    return data as T;
  } finally {
    clearTimeout(timeout);
    signal?.removeEventListener("abort", abort);
  }
}
export const api = {
  charities: (signal?: AbortSignal) =>
    request<Charity[]>(paths.charities, undefined, signal),
  addRule: (id: string, text: string) =>
    request<{ job_id: string }>(paths.rules(id), { rule_text: text }),
  run: (id: string) => request<{ job_id: string }>(paths.run(id), {}),
  refresh: (ticker: string) =>
    request<{ job_id: string }>(paths.refresh(ticker), {}),
  job: (id: string, signal?: AbortSignal) =>
    request<Job>(paths.job(id), undefined, signal),
};
export function safeLink(url: string): string | undefined {
  if (url.startsWith("/api/") && !url.startsWith("//")) return url;
  try {
    const parsed = new URL(url);
    if (["https:", "http:"].includes(parsed.protocol)) return parsed.href;
  } catch {
    /* invalid */
  }
  return undefined;
}
