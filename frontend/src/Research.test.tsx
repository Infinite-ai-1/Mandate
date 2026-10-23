// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import Research, { parseAgentProgress } from "./Research";
import raw from "../dev/fixtures.json";
import research from "../dev/research-fixtures.json";
import type { Portfolio, Selection } from "./api";
const fixtures = raw as Record<string, unknown>;
const summaries = research as Record<string, unknown>;
const cid = "cancer_research_wales";
let polls = 0;
let selected = "TEST";
let omitHeader = false;
let failJob = false;
const scroll = vi.fn();
const complete = vi.fn();
const busy = vi.fn();
beforeEach(() => {
  polls = 0;
  selected = "TEST";
  omitHeader = false;
  failJob = false;
  scroll.mockClear();
  complete.mockClear();
  busy.mockClear();
  Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
    configurable: true,
    value: scroll,
  });
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path: string, init?: RequestInit) => {
      if (init?.method === "POST") {
        selected = decodeURIComponent(path.split("/")[3]);
        return new Response(JSON.stringify({ job_id: "research-job" }));
      }
      if (path === "/api/jobs/research-job") {
        if (failJob)
          return new Response(
            JSON.stringify({ error: "Connection interrupted" }),
            { status: 503 },
          );
        polls++;
        const progress = [
          "[melchior] Checking cached policy evidence.",
          "[balthasar] Reviewing cash flow evidence.",
          "[casper] Reviewing historical risk.",
          "[melchior:done] Ethics findings ready.",
        ];
        if (polls > 1)
          progress.push("[balthasar:done] Financial findings ready.");
        if (polls > 2) progress.push("[casper:done] Risk findings ready.");
        return new Response(
          JSON.stringify({
            status: polls > 2 ? "done" : "running",
            progress,
            result: null,
            error: null,
          }),
        );
      }
      return new Response(JSON.stringify(fixtures[path]), {
        headers: omitHeader
          ? {}
          : { "X-Mandate-Research": JSON.stringify(summaries[path]) },
      });
    }),
  );
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
function mount() {
  render(
    <Research
      charity={cid}
      name="Cancer Research Wales"
      selection={fixtures[`/api/charities/${cid}/selection`] as Selection}
      portfolio={fixtures[`/api/charities/${cid}/portfolio`] as Portfolio}
      externalBusy={false}
      onBusy={busy}
      onComplete={complete}
      openSource={() => {}}
    />,
  );
}
it("opens three live cards, flashes completion and scrolls to the Chair after all agents finish", async () => {
  mount();
  fireEvent.change(
    screen.getByLabelText("Which stock would you like to research?"),
    { target: { value: "CAPPED" } },
  );
  fireEvent.click(screen.getByRole("button", { name: "Research stock →" }));
  await screen.findByText("Checking cached policy evidence.");
  expect(screen.getAllByRole("article")).toHaveLength(3);
  const ethics = screen.getByRole("article", {
    name: "Melchior research card",
  });
  expect(within(ethics).getByText("✓ Complete")).toBeTruthy();
  expect(screen.queryByRole("region", { name: "Chair findings" })).toBeNull();
  await screen.findByText(
    "Buy",
    { selector: ".verdict-label", exact: true },
    { timeout: 5000 },
  );
  expect(
    screen.getByText("2 of three agents favour investing.", { exact: false }),
  ).toBeTruthy();
  expect(screen.getByText("Verified ethics score")).toBeTruthy();
  await waitFor(
    () =>
      expect(
        (scroll.mock.contexts.at(-1) as HTMLElement | undefined)?.getAttribute(
          "aria-label",
        ),
      ).toBe("Chair findings"),
    { timeout: 2000 },
  );
  expect(complete).toHaveBeenCalledOnce();
});
it("keeps a verified ethics rejection despite two invest votes", async () => {
  mount();
  fireEvent.change(
    screen.getByLabelText("Which stock would you like to research?"),
    { target: { value: "VETO" } },
  );
  fireEvent.click(screen.getByRole("button", { name: "Research stock →" }));
  await screen.findByText(
    "Reject",
    { selector: ".verdict-label", exact: true },
    { timeout: 5000 },
  );
  expect(screen.getByText(/Ethics veto: verified evidence fails/)).toBeTruthy();
});
it("shows a financial/risk majority rejection even when ethics passes", async () => {
  mount();
  fireEvent.change(
    screen.getByLabelText("Which stock would you like to research?"),
    { target: { value: "DECLINE" } },
  );
  fireEvent.click(screen.getByRole("button", { name: "Research stock →" }));
  await screen.findByText(
    "Reject",
    { selector: ".verdict-label", exact: true },
    { timeout: 5000 },
  );
  expect(screen.queryByText(/Ethics veto: verified evidence fails/)).toBeNull();
  expect(
    screen.getByRole("heading", {
      name: /Ethics checks pass, but the investment case does not/,
    }),
  ).toBeTruthy();
});
it("does not invent a majority rating when backend votes are unavailable", async () => {
  omitHeader = true;
  mount();
  fireEvent.click(screen.getByRole("button", { name: "Research stock →" }));
  await screen.findByText("Decision received", {}, { timeout: 5000 });
  expect(screen.getByText(/No majority rating has been invented/)).toBeTruthy();
  expect(screen.queryByText("Strong buy", { exact: true })).toBeNull();
});
it("preserves the research workspace on polling error and reconnects to the same job", async () => {
  failJob = true;
  mount();
  fireEvent.click(screen.getByRole("button", { name: "Research stock →" }));
  await screen.findByRole("alert");
  expect(screen.getAllByRole("article")).toHaveLength(3);
  fireEvent.click(screen.getByRole("button", { name: "Check the same job" }));
  await screen.findByRole("alert");
  expect(
    (fetch as ReturnType<typeof vi.fn>).mock.calls.filter(
      ([, init]) => init?.method === "POST",
    ),
  ).toHaveLength(1);
});
it("accepts only explicit agent-tagged progress, not unrelated log text", () => {
  expect(
    parseAgentProgress(
      ["Some general work", "[melchior] Reading sources", "[casper:done] Done"],
      "melchior",
    ),
  ).toEqual([{ done: false, text: "Reading sources" }]);
});
