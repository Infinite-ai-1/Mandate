// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { api, cached, paths, remember, request, safeLink, validatePayload } from "./api";
import PolicyEditor from "./PolicyEditor";
import App from "./App";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); localStorage.clear(); });

const cid = "british_thoracic_society";
// Honest initial paper ledger; no market observations or investment recommendations.
const portfolio = { charity_id: cid, total_usd: 100000, gbpusd: null, as_of: "", holdings: [], cash_usd: 100000,
  risk: { worst_12m: null, yield: null, volatility: null, vs_6040_return: null },
  checks: { max_drawdown_ok: null, yield_ok: null, bonds_ok: null }, relaxed: [], rejected: [], trustee_review: [],
  memo: "", devils_advocate: [], run_stats: { seconds: 0, llm_calls: 0, tokens: 0, by_agent: {} } };
const account = { charity_id: cid, simulated: true, policy_revision: 0, portfolio, invested_usd: 0,
  presentation: { holdings_count: 0, shares_weight: 0, bonds_weight: 0, cash_weight: 1 },
  chart: [{ ticker: "Cash", usd: 100000, weight: 1 }], to_verify: [] };

it("accepts unavailable measurements and rejects malformed market values", () => {
  expect(validatePayload(paths.account(cid), account)).toBe(true);
  expect(validatePayload(paths.portfolio(cid), portfolio)).toBe(true);
  expect(validatePayload(paths.portfolio(cid), { ...portfolio, gbpusd: "unknown" })).toBe(false);
  expect(validatePayload(paths.portfolio(cid), { ...portfolio, cash_usd: NaN })).toBe(false);
});

it("does not reuse legacy synthetic browser data", () => {
  localStorage.setItem("mandate:" + paths.policy("old-preview"), JSON.stringify({text: "old preview"}));
  expect(cached(paths.policy("old-preview"))).toBeUndefined();
});

it("refresh requests include the selected charity", async () => {
  const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({job_id: "abc"}), {status: 202}));
  vi.stubGlobal("fetch", fetch);
  await api.refresh("XYL", cid);
  expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({charity_id: cid});
});

it("rejects responses from a legacy synthetic server", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(portfolio), {
    status: 200, headers: {"X-Mandate-Data": "synthetic"},
  })));
  await expect(request(paths.portfolio(cid))).rejects.toThrow("Legacy preview server");
});

it("policy-save jobs may finish without an assessment", () => {
  expect(validatePayload(paths.job("abc"), {status: "done", progress: ["Policy saved; configure credentials"], result: null, error: null})).toBe(true);
});

it("policy editor submits actual text and the current revision", () => {
  const save = vi.fn();
  render(<PolicyEditor policy={{text: "", policy_revision: 2}} busy={false} onSave={save} />);
  fireEvent.change(screen.getByLabelText("Investment and ethics policy"), {target: {value: "Trustee-entered restriction"}});
  fireEvent.click(screen.getByRole("button", {name: "Save policy and reassess"}));
  expect(save).toHaveBeenCalledWith("Trustee-entered restriction", 2);
});

it("renders the empty real-data workspace and completes a policy-only job", async () => {
  let saved = false;
  vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
  vi.stubGlobal("fetch", vi.fn(async (path: string, options?: RequestInit) => {
    let payload: unknown;
    let status = 200;
    if (path === paths.charities) payload = [{charity_id: cid, name: "British Thoracic Society", purpose: "Policy document required"}];
    else if (path === paths.account(cid)) payload = account;
    else if (path === paths.policy(cid) && options?.method === "POST") { saved = true; payload = {job_id: "saved"}; }
    else if (path === paths.policy(cid)) payload = {text: saved ? "Trustee-entered policy" : "", policy_revision: saved ? 1 : 0};
    else if (path === paths.job("saved")) payload = {status: "done", progress: ["Policy saved. Configure credentials."], result: null, error: null};
    else if (path === paths.selection(cid)) payload = {charity_id: cid, universe_size: 0, after_prefilter: 0, selected: [], excluded_by_sic: []};
    else { payload = {error: "No current assessment"}; status = 409; }
    return new Response(JSON.stringify(payload), {status});
  }));
  render(<App />);
  expect(await screen.findByRole("heading", {name: "British Thoracic Society"})).toBeTruthy();
  expect(screen.getByText(/No real-money trades/)).toBeTruthy();
  fireEvent.click(screen.getByRole("button", {name: /Policy/}));
  const input = await screen.findByLabelText("Investment and ethics policy");
  fireEvent.change(input, {target: {value: "Trustee-entered policy"}});
  fireEvent.click(screen.getByRole("button", {name: "Save policy and reassess"}));
  await waitFor(() => expect(saved).toBe(true));
  await waitFor(() => expect(screen.queryByRole("button", {name: "Reassessing…"})).toBeNull());
  expect(screen.queryByText(/SYNTHETIC FIXTURE/)).toBeNull();
});

it("blocks unsafe evidence links", () => {
  expect(safeLink("javascript:alert(1)")).toBeUndefined();
  expect(safeLink("https://www.sec.gov/")).toBe("https://www.sec.gov/");
});

it("full reset clears Mandate browser caches only after a successful server reset", async () => {
  localStorage.setItem('mandate:selected', 'test');
  sessionStorage.setItem('mandate:job', 'old');
  localStorage.setItem('unrelated', 'keep');
  const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({reset:true}), {status:200}));
  vi.stubGlobal('fetch', fetch);
  await api.reset();
  expect(fetch.mock.calls[0][0]).toBe('/api/reset');
  expect(localStorage.getItem('mandate:selected')).toBeNull();
  expect(sessionStorage.getItem('mandate:job')).toBeNull();
  expect(localStorage.getItem('unrelated')).toBe('keep');
  localStorage.setItem('mandate:selected','retained');
  fetch.mockResolvedValue(new Response(JSON.stringify({error:'failed'}), {status:500}));
  await expect(api.reset()).rejects.toThrow('failed');
  expect(localStorage.getItem('mandate:selected')).toBe('retained');
});
