// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import App from "./App";
import raw from "../dev/fixtures.json";
import summaryFixtures from "../dev/presentation-fixtures.json";
import type { Portfolio, Rules } from "./api";

const cid = "cancer_research_wales";
let fixtures: Record<string, unknown>;
let polls = 0;
let action = "";
vi.mock("recharts", () => ({
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
  PieChart: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
  Pie: () => null,
  Cell: () => null,
  Tooltip: () => null,
  Legend: () => null,
}));
beforeEach(() => {
  fixtures = structuredClone(raw);
  polls = 0;
  action = "";
  localStorage.clear();
  Object.defineProperty(HTMLDialogElement.prototype, "showModal", {
    configurable: true,
    value: function () {
      this.setAttribute("open", "");
    },
  });
  Object.defineProperty(HTMLDialogElement.prototype, "close", {
    configurable: true,
    value: function () {
      this.removeAttribute("open");
    },
  });
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path: string, init?: RequestInit) => {
      if (init?.method === "POST") {
        action = path;
        polls = 0;
        return new Response(JSON.stringify({ job_id: "test-job" }));
      }
      if (path === "/api/jobs/test-job") {
        polls++;
        const result = structuredClone(
          fixtures[`/api/charities/${cid}/portfolio`],
        ) as Portfolio;
        if (polls > 1) {
          if (action.endsWith("/rules")) {
            result.holdings = result.holdings.filter(
              (h) => h.ticker !== "TEST",
            );
            const rules = fixtures[`/api/charities/${cid}/rules`] as Rules;
            rules.rules.push({
              ...rules.rules[0],
              id: "J-TEST",
              text: "No synthetic TEST",
              origin: "judge",
            });
          }
          fixtures[`/api/charities/${cid}/portfolio`] = result;
        }
        return new Response(
          JSON.stringify({
            status: polls > 1 ? "done" : "running",
            progress:
              polls > 1
                ? ["Reading evidence", "Portfolio ready"]
                : ["Reading evidence"],
            result: polls > 1 ? result : null,
            error: null,
          }),
        );
      }
      const data = fixtures[path];
      return new Response(
        JSON.stringify(data || { error: "Unavailable test endpoint" }),
        {
          status: data ? 200 : 404,
          headers: {
            "X-Mandate-Presentation": JSON.stringify(
              (summaryFixtures as Record<string, unknown>)[path] || {},
            ),
          },
        },
      );
    }),
  );
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
it("renders server-supplied headline and funnel totals", async () => {
  render(<App />);
  await screen.findByRole("heading", {
    name: "Invest $100,000 (about £76,923) across 3 holdings:",
  });
  expect(screen.getByText("analysed", { exact: false })).toBeTruthy();
  await screen.findByRole("link", { name: "Open filing evidence ↗" });
});
it("renders all charities, source drawer, analyst cards and comparison", async () => {
  render(<App />);
  await screen.findByRole("heading", { name: "Cancer Research Wales" });
  for (const [name, id] of [
    ["British Thoracic Society", "british_thoracic_society"],
    ["British Red Cross", "british_red_cross"],
    ["Nuffield Oxford Hospitals Fund", "nuffield_oxford_hospitals_fund"],
    ["Cancer Research Wales", cid],
  ]) {
    fireEvent.change(screen.getByLabelText("Charity mandate"), {
      target: { value: id },
    });
    await screen.findByRole("heading", { name });
  }
  await screen.findByRole("heading", { name: "Holdings & their reasons" });
  fireEvent.click(screen.getAllByRole("link", { name: /S-TEST-TEST/ })[0]);
  await screen.findByRole("heading", {
    name: "SYNTHETIC TEST filing for interface tests",
  });
  expect(
    screen
      .getByRole("link", { name: "Open registered source ↗" })
      .getAttribute("href"),
  ).toBe("/api/fixture-evidence/TEST");
  fireEvent.click(
    screen.getByRole("button", { name: "Close Evidence source" }),
  );
  fireEvent.click(screen.getAllByRole("button", { name: "TEST ↗" })[0]);
  await screen.findByText("Claude Sonnet 5.5 (fixture)");
  await screen.findByText("MAI Thinking 1 (fixture)");
  fireEvent.click(
    screen.getByRole("button", { name: "Close TEST · analyst evidence" }),
  );
  fireEvent.click(screen.getByRole("button", { name: /Compare mandates/ }));
  fireEvent.change(screen.getByLabelText("Company ticker"), {
    target: { value: "TEST" },
  });
  fireEvent.click(screen.getByRole("button", { name: /^Compare$/ }));
  await screen.findByRole("heading", { name: "British Red Cross" });
  expect(
    screen.getByText("Educational hackathon project. Not financial advice."),
  ).toBeTruthy();
});
it("polls a live rule, shows progress and highlights the removed holding and new rule", async () => {
  render(<App />);
  await screen.findByRole("heading", { name: "Holdings & their reasons" });
  fireEvent.change(screen.getByLabelText("New rule"), {
    target: { value: "No synthetic TEST" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Apply rule →" }));
  await screen.findByText(/Reading evidence/);
  await screen.findByText("Portfolio updated", {}, { timeout: 5000 });
  expect(screen.getByText("Removed: TEST")).toBeTruthy();
  fireEvent.click(
    screen.getByRole("button", { name: "Review updated rules →" }),
  );
  await screen.findByRole("heading", { name: "No synthetic TEST" });
  expect(screen.getByText("judge")).toBeTruthy();
});
it("refreshes a company through the job flow", async () => {
  render(<App />);
  await screen.findByRole("button", { name: "Refresh TEST" });
  fireEvent.click(screen.getByRole("button", { name: "Refresh TEST" }));
  await screen.findByText("Portfolio updated", {}, { timeout: 5000 });
  expect(action).toBe("/api/companies/TEST/refresh");
  expect(polls).toBeGreaterThan(1);
});
it("keeps the last good portfolio visible when API reads fail", async () => {
  render(<App />);
  await screen.findByRole("heading", { name: "Holdings & their reasons" });
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ error: "Offline for test" }), {
        status: 503,
      }),
    ),
  );
  fireEvent.click(screen.getByRole("button", { name: "Reload data" }));
  await waitFor(() =>
    expect(
      screen.getAllByText(/Showing the last good data/).length,
    ).toBeGreaterThan(0),
  );
  expect(
    screen.getByRole("heading", { name: "Holdings & their reasons" }),
  ).toBeTruthy();
});
it("opens a complete agent decision trail and switches between company outcomes", async () => {
  render(<App />);
  await screen.findByRole("heading", { name: "Holdings & their reasons" });
  fireEvent.click(
    screen.getByRole("button", { name: "Explore agent decisions →" }),
  );
  await screen.findByRole("heading", { name: "Agent decisions" });
  await screen.findByRole("heading", { name: "Does it meet the mandate?" });
  expect(
    screen.getByRole("heading", { name: "Is the business financially sound?" }),
  ).toBeTruthy();
  expect(
    screen.getByRole("heading", { name: "How much risk does it carry?" }),
  ).toBeTruthy();
  await screen.findByText("Reported confidence: 90%");
  expect(screen.getByText("Synthetic conservative weighting")).toBeTruthy();
  expect(
    screen.getByRole("heading", { name: "Included in the current portfolio" }),
  ).toBeTruthy();
  fireEvent.change(screen.getByLabelText("Company under review"), {
    target: { value: "VETO" },
  });
  await screen.findByText("Synthetic test quote: this company sells tobacco.");
  expect(screen.getByText("Rejected", { exact: true })).toBeTruthy();
  expect(
    screen.getByRole("heading", {
      name: "No holding in the current portfolio",
    }),
  ).toBeTruthy();
  expect(screen.getByText("✓ Quote verified")).toBeTruthy();
  fireEvent.click(screen.getAllByRole("link", { name: /S-VETO-TEST/ })[0]);
  await screen.findByRole("heading", {
    name: "SYNTHETIC VETO filing for interface tests",
  });
});
