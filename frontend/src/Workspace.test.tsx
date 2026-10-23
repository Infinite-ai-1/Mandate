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
import InvestmentPanel from "./InvestmentPanel";
import PolicyEditor from "./PolicyEditor";
import raw from "../dev/fixtures.json";
import workspace from "../dev/workspace-fixtures.json";
import research from "../dev/research-fixtures.json";
import purchase from "../dev/purchase-fixture.json";
const cid = "cancer_research_wales";
let data: Record<string, unknown>;
let loseResponse = false;
vi.mock("recharts", () => ({
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
  PieChart: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
  Pie: ({ data }: { data: unknown }) => (
    <pre aria-label="Allocation chart data">{JSON.stringify(data)}</pre>
  ),
  Cell: () => null,
  Tooltip: () => null,
  Legend: () => null,
}));
beforeEach(() => {
  localStorage.clear();
  data = structuredClone({ ...raw, ...workspace });
  loseResponse = false;
  Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
    configurable: true,
    value: vi.fn(),
  });
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path: string, init?: RequestInit) => {
      if (init?.method === "POST" && path.endsWith("/investments")) {
        data[`/api/charities/${cid}/account`] = purchase.account;
        if (loseResponse) {
          loseResponse = false;
          throw new TypeError("Response lost");
        }
        return new Response(JSON.stringify(purchase));
      }
      if (init?.method === "POST")
        return new Response(JSON.stringify({ job_id: "workspace-job" }));
      if (path === "/api/jobs/workspace-job")
        return new Response(
          JSON.stringify({
            status: "done",
            progress: [
              "[melchior:done] Ready",
              "[balthasar:done] Ready",
              "[casper:done] Ready",
            ],
            result: null,
            error: null,
          }),
        );
      const summary = (research as Record<string, unknown>)[path];
      return new Response(
        JSON.stringify(data[path] || { error: "Not available" }),
        {
          status: data[path] ? 200 : 404,
          headers: summary
            ? { "X-Mandate-Research": JSON.stringify(summary) }
            : {},
        },
      );
    }),
  );
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
it("buys after research, returns Home and updates the pot, holdings and pie from the API", async () => {
  render(<App />);
  await screen.findByRole("heading", { name: "Your $100,000 investment pot" });
  expect(screen.getByRole("button", { name: "Home" })).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Research a stock →" }));
  fireEvent.click(screen.getByRole("button", { name: "Research stock →" }));
  await screen.findByRole("heading", { name: "How much should we invest?" });
  await screen.findByRole("button", { name: "Buy · simulated investment" });
  fireEvent.change(screen.getByLabelText("Amount to invest in TEST (USD)"), {
    target: { value: "5000" },
  });
  fireEvent.click(
    screen.getByRole("button", { name: "Buy · simulated investment" }),
  );
  await screen.findByText(/allocated to TEST/);
  await waitFor(() =>
    expect(
      JSON.parse(screen.getByLabelText("Allocation chart data").textContent!),
    ).toEqual(purchase.account.chart),
  );
  expect(screen.getByRole("button", { name: "TEST ↗" })).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Stats" }));
  await screen.findByRole("heading", { name: "Portfolio stats" });
  fireEvent.click(screen.getByRole("button", { name: "Rejections" }));
  await screen.findByRole("heading", { name: "Rejections" });
  fireEvent.click(screen.getByRole("button", { name: "To verify" }));
  await screen.findByRole("heading", { name: "To verify" });
});
it("reuses the allocation request after a lost response instead of buying twice", async () => {
  loseResponse = true;
  const onPurchased = vi.fn();
  render(
    <InvestmentPanel charity={cid} ticker="TEST" onPurchased={onPurchased} />,
  );
  await screen.findByRole("button", { name: "Buy · simulated investment" });
  fireEvent.change(screen.getByLabelText("Amount to invest in TEST (USD)"), {
    target: { value: "5000" },
  });
  fireEvent.click(
    screen.getByRole("button", { name: "Buy · simulated investment" }),
  );
  await screen.findByRole("button", { name: "Check this allocation" });
  fireEvent.click(
    screen.getByRole("button", { name: "Check this allocation" }),
  );
  await waitFor(() => expect(onPurchased).toHaveBeenCalledOnce());
  const calls = (fetch as ReturnType<typeof vi.fn>).mock.calls.filter(
    ([path]) => path.endsWith("/investments"),
  );
  expect(calls).toHaveLength(2);
  expect(calls[0][1].body).toBe(calls[1][1].body);
});
it("submits revised policy text with its original revision for reassessment", () => {
  const onSave = vi.fn();
  render(
    <PolicyEditor
      policy={{ text: "No tobacco", policy_revision: 1 }}
      busy={false}
      onSave={onSave}
    />,
  );
  fireEvent.change(screen.getByLabelText("Investment and ethics policy"), {
    target: { value: "No tobacco. Exclude TEST." },
  });
  fireEvent.click(
    screen.getByRole("button", { name: "Save policy and reassess" }),
  );
  expect(onSave).toHaveBeenCalledWith("No tobacco. Exclude TEST.", 1);
});
