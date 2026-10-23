import { afterEach, describe, expect, it, vi } from "vitest";
import {
  api,
  cached,
  paths,
  presentation,
  remember,
  request,
  safeLink,
  validatePayload,
} from "./api";
import fixtures from "../dev/fixtures.json";

afterEach(() => vi.unstubAllGlobals());
describe("API boundary", () => {
  it("validates every synthetic snapshot against the typed contract", () => {
    for (const [path, data] of Object.entries(fixtures))
      expect(validatePayload(path, data), path).toBe(true);
  });
  it("preserves last good data on HTTP errors and malformed responses", async () => {
    const path = paths.portfolio("cancer_research_wales");
    const good = fixtures[path as keyof typeof fixtures];
    remember(path, good);
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          new Response(JSON.stringify({ error: "Temporarily unavailable" }), {
            status: 503,
          }),
        ),
    );
    await expect(request(path)).rejects.toThrow("Temporarily unavailable");
    expect(cached(path)).toEqual(good);
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(new Response(JSON.stringify({ holdings: null }))),
    );
    await expect(request(path)).rejects.toThrow("contract");
    expect(cached(path)).toEqual(good);
  });
  it("posts only the agreed rule body", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValue(
        new Response(JSON.stringify({ job_id: "fixture-job" })),
      );
    vi.stubGlobal("fetch", fetch);
    await api.addRule("british_red_cross", "No tobacco");
    expect(fetch.mock.calls[0][0]).toBe(
      "/api/charities/british_red_cross/rules",
    );
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({
      rule_text: "No tobacco",
    });
  });
  it("reads server-computed presentation headers without changing the JSON contract", async () => {
    const path = paths.portfolio("cancer_research_wales");
    const data = fixtures[path as keyof typeof fixtures];
    const summary = {
      holdings_count: 3,
      total_gbp: 76923.076923,
      shares_weight: 0.12,
      bonds_weight: 0.87,
      cash_weight: 0.01,
    };
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          new Response(JSON.stringify(data), {
            headers: { "X-Mandate-Presentation": JSON.stringify(summary) },
          }),
        ),
    );
    expect(await request(path)).toEqual(data);
    expect(presentation(path)).toEqual(summary);
  });
  it("permits registered web/API links and blocks executable URLs", () => {
    expect(safeLink("https://example.org/filing")).toBe(
      "https://example.org/filing",
    );
    expect(safeLink("/api/sources/Q-TEST-beta")).toBe(
      "/api/sources/Q-TEST-beta",
    );
    expect(safeLink("javascript:alert(1)")).toBeUndefined();
    expect(safeLink("//example.org")).toBeUndefined();
  });
});
