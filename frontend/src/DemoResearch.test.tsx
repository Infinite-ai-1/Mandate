// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import DemoResearch, { demoStocks } from "./DemoResearch";

afterEach(() => { cleanup(); vi.useRealTimers(); vi.unstubAllGlobals(); });

it.each(demoStocks)("walks $ticker through its distinct simulated decision", async (stock) => {
  vi.useFakeTimers();
  const fetch = vi.fn();
  vi.stubGlobal("fetch", fetch);
  render(<DemoResearch />);
  fireEvent.click(screen.getByRole("button", {name: new RegExp(`★ ${stock.ticker}`)}));
  expect(screen.getByRole("status").textContent).toContain("Simulating Melchior");
  expect(screen.queryByLabelText("Simulated final decision")).toBeNull();
  for (let stage = 0; stage < 4; stage++) {
    await act(async () => { await vi.advanceTimersByTimeAsync(900); });
  }
  expect(screen.getByRole("status").textContent).toBe("Simulation complete");
  const decision = screen.getByLabelText("Simulated final decision");
  expect(within(decision).getByText(`${stock.label} · simulated`)).toBeTruthy();
  expect(within(decision).getByText(stock.reason)).toBeTruthy();
  expect(within(screen.getByLabelText("Demo devil’s advocate")).getAllByRole("listitem")).toHaveLength(3);
  expect(fetch).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", {name: /Close demo/}));
  expect(screen.queryByLabelText("Simulated final decision")).toBeNull();
});

it("offers all four distinct outcomes and disables demo starts during live research", () => {
  expect(new Set(demoStocks.map((stock) => stock.decision)).size).toBe(4);
  render(<DemoResearch disabled />);
  screen.getAllByRole("button").forEach((button) => expect((button as HTMLButtonElement).disabled).toBe(true));
});

it("replaying another stock clears the previous verdict immediately", async () => {
  vi.useFakeTimers();
  render(<DemoResearch />);
  fireEvent.click(screen.getByRole("button", {name: /★ XYL/}));
  for (let i = 0; i < 4; i++) await act(async () => { await vi.advanceTimersByTimeAsync(900); });
  expect(screen.getByLabelText("Simulated final decision")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", {name: /★ PM/}));
  expect(screen.queryByLabelText("Simulated final decision")).toBeNull();
  expect(screen.getByRole("status").textContent).toContain("Simulating Melchior");
});
