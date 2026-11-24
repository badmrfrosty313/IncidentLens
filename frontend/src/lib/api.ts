import type {
  AnalysisResponse,
  AnalysisSource,
  DemoResponse,
  FormatHint,
  ReportFormat,
  ScenarioInfo,
} from "../types/api";
import { demoDataUrl, isStaticDemo } from "./mode";

const API_BASE: string = (import.meta.env?.VITE_API_BASE as string | undefined) ?? "";

/** Mirrors the backend default (INCIDENTLENS_MAX_INPUT_BYTES). The server is authoritative. */
export const MAX_UPLOAD_BYTES = 20 * 1024 * 1024;

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  constructor(message: string, status: number, code = "error") {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

async function toError(res: Response): Promise<ApiError> {
  let message = `Request failed (${res.status})`;
  let code = "error";
  try {
    const body: unknown = await res.json();
    if (body && typeof body === "object") {
      const b = body as { detail?: unknown; code?: unknown };
      if (typeof b.code === "string") code = b.code;
      if (typeof b.detail === "string") message = b.detail;
      else if (Array.isArray(b.detail) && b.detail.length > 0) {
        const first = b.detail[0] as { msg?: unknown };
        if (typeof first?.msg === "string") message = `Invalid request: ${first.msg}`;
      }
    }
  } catch {
    /* non-JSON error body: keep the generic message */
  }
  return new ApiError(message, res.status, code);
}

async function request(path: string, init?: RequestInit): Promise<Response> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, init);
  } catch {
    throw new ApiError("Cannot reach the IncidentLens API. Is the backend running?", 0, "network");
  }
  if (!res.ok) throw await toError(res);
  return res;
}

const json = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

const SCENARIO_ID = /^[a-z0-9-]{1,64}$/;

async function staticFixture(file: string): Promise<Response> {
  let res: Response;
  try {
    res = await fetch(demoDataUrl(file));
  } catch {
    throw new ApiError("Could not load the demonstration data.", 0, "network");
  }
  if (!res.ok) throw new ApiError(`Demonstration data not found (${res.status}).`, res.status, "not_found");
  return res;
}

const STATIC_DISABLED = new ApiError(
  "Static demonstration mode: analyzing your own logs is disabled. Run the full application locally (see the README).",
  403,
  "static_demo",
);

export async function getHealth(): Promise<{ status: string; version: string }> {
  if (isStaticDemo()) {
    const m = (await (await staticFixture("manifest.json")).json()) as { version: string };
    return { status: "static", version: m.version };
  }
  return (await request("/api/health")).json();
}

export async function listScenarios(): Promise<ScenarioInfo[]> {
  if (isStaticDemo()) return (await staticFixture("scenarios.json")).json();
  return (await request("/api/demo")).json();
}

export async function runScenario(id: string): Promise<DemoResponse> {
  if (isStaticDemo()) {
    if (!SCENARIO_ID.test(id)) throw new ApiError("Unknown scenario.", 404, "unknown_scenario");
    return (await staticFixture(`${id}.json`)).json();
  }
  return (await request(`/api/demo/${encodeURIComponent(id)}`)).json();
}

export async function analyze(content: string, format: FormatHint = "auto"): Promise<AnalysisResponse> {
  if (isStaticDemo()) throw STATIC_DISABLED;
  return (await request("/api/analyze", json({ content, format }))).json();
}

/** Fetch a Markdown or JSON incident report for whatever produced the current analysis. */
export async function fetchReport(source: AnalysisSource, format: ReportFormat): Promise<string> {
  if (isStaticDemo()) {
    if (source.kind !== "demo" || !SCENARIO_ID.test(source.scenarioId)) throw STATIC_DISABLED;
    return (await staticFixture(`${source.scenarioId}.report.${format === "markdown" ? "md" : "json"}`)).text();
  }
  const res =
    source.kind === "demo"
      ? await request(`/api/demo/${encodeURIComponent(source.scenarioId)}/report?format=${format}`)
      : await request(`/api/report?format=${format}`, json({ content: source.content, format: source.format }));
  return res.text();
}
