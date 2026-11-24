import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, analyze, fetchReport, getHealth, runScenario } from "./api";

function mockFetch(response: { status?: number; body?: unknown; text?: string } | Error) {
  const fn = vi.fn(async () => {
    if (response instanceof Error) throw response;
    const status = response.status ?? 200;
    return {
      ok: status >= 200 && status < 300,
      status,
      json: async () => {
        if (response.body === undefined) throw new Error("no json");
        return response.body;
      },
      text: async () => response.text ?? "",
    } as unknown as Response;
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

afterEach(() => vi.unstubAllGlobals());

describe("api client", () => {
  it("POSTs analyze requests as JSON", async () => {
    const fetchMock = mockFetch({ body: { ok: true } });
    await analyze("hello", "jsonl");
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/analyze");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({ content: "hello", format: "jsonl" });
    expect((init.headers as Record<string, string>)["Content-Type"]).toBe("application/json");
  });

  it("maps 413 responses to an ApiError with the server message", async () => {
    mockFetch({ status: 413, body: { code: "input_too_large", detail: "Input is too big." } });
    await expect(analyze("x")).rejects.toMatchObject({ name: "ApiError", status: 413, code: "input_too_large", message: "Input is too big." });
  });

  it("surfaces FastAPI validation errors readably", async () => {
    mockFetch({ status: 422, body: { detail: [{ msg: "String should have at least 1 character" }] } });
    await expect(analyze("")).rejects.toThrow("Invalid request: String should have at least 1 character");
  });

  it("falls back to a generic message for non-JSON errors", async () => {
    mockFetch({ status: 502 });
    await expect(getHealth()).rejects.toThrow("Request failed (502)");
  });

  it("reports an unreachable backend clearly", async () => {
    mockFetch(new TypeError("Failed to fetch"));
    const err = await getHealth().catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).code).toBe("network");
    expect((err as ApiError).message).toMatch(/Cannot reach/);
  });

  it("url-encodes scenario ids", async () => {
    const fetchMock = mockFetch({ body: {} });
    await runScenario("a/b c");
    expect((fetchMock.mock.calls[0] as unknown as [string])[0]).toBe("/api/demo/a%2Fb%20c");
  });

  it("requests demo and content reports from the right endpoints", async () => {
    const fetchMock = mockFetch({ text: "# report" });
    expect(await fetchReport({ kind: "demo", scenarioId: "healthy-system" }, "markdown")).toBe("# report");
    expect((fetchMock.mock.calls[0] as unknown as [string])[0]).toBe("/api/demo/healthy-system/report?format=markdown");

    await fetchReport({ kind: "content", content: "abc", format: "auto", label: "x" }, "json");
    const [url, init] = fetchMock.mock.calls[1] as unknown as [string, RequestInit];
    expect(url).toBe("/api/report?format=json");
    expect(JSON.parse(init.body as string)).toEqual({ content: "abc", format: "auto" });
  });
});

describe("static demonstration mode", () => {
  const fixtures: Record<string, { body?: unknown; text?: string }> = {
    "/IncidentLens/demo-data/manifest.json": { body: { version: "0.1.0" } },
    "/IncidentLens/demo-data/scenarios.json": { body: [{ id: "db-pool-exhaustion" }] },
    "/IncidentLens/demo-data/db-pool-exhaustion.json": { body: { scenario: { id: "db-pool-exhaustion" }, analysis: {} } },
    "/IncidentLens/demo-data/db-pool-exhaustion.report.md": { text: "# IncidentLens incident report" },
    "/IncidentLens/demo-data/db-pool-exhaustion.report.json": { text: "{}" },
  };

  function staticFetch() {
    vi.stubEnv("VITE_STATIC_DEMO", "true");
    vi.stubEnv("BASE_URL", "/IncidentLens/");
    const fn = vi.fn(async (url: string) => {
      const hit = fixtures[url];
      return {
        ok: Boolean(hit),
        status: hit ? 200 : 404,
        json: async () => hit?.body,
        text: async () => hit?.text ?? "",
      } as unknown as Response;
    });
    vi.stubGlobal("fetch", fn);
    return fn;
  }

  afterEach(() => vi.unstubAllEnvs());

  it("serves everything from generated fixtures and never touches /api", async () => {
    const fn = staticFetch();
    expect(await getHealth()).toEqual({ status: "static", version: "0.1.0" });
    await listScenarios();
    await runScenario("db-pool-exhaustion");
    expect(await fetchReport({ kind: "demo", scenarioId: "db-pool-exhaustion" }, "markdown")).toContain("# IncidentLens");
    expect(await fetchReport({ kind: "demo", scenarioId: "db-pool-exhaustion" }, "json")).toBe("{}");
    const urls = fn.mock.calls.map((c) => c[0] as string);
    expect(urls).toHaveLength(5);
    expect(urls.every((u) => u.startsWith("/IncidentLens/demo-data/") && !u.includes("/api/"))).toBe(true);
  });

  it("refuses to analyze arbitrary content and makes no request", async () => {
    const fn = staticFetch();
    await expect(analyze("anything")).rejects.toMatchObject({ code: "static_demo" });
    await expect(fetchReport({ kind: "content", content: "x", format: "auto", label: "l" }, "markdown")).rejects.toMatchObject({ code: "static_demo" });
    expect(fn).not.toHaveBeenCalled();
  });

  it("rejects scenario ids that could escape the fixture directory", async () => {
    const fn = staticFetch();
    await expect(runScenario("../../etc/passwd")).rejects.toMatchObject({ code: "unknown_scenario" });
    expect(fn).not.toHaveBeenCalled();
  });

  it("reports a missing fixture as a readable error", async () => {
    staticFetch();
    await expect(runScenario("nope")).rejects.toMatchObject({ status: 404, code: "not_found" });
  });
});
