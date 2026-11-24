import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import * as api from "./lib/api";
import { SCENARIO, makeAnalysis } from "./test/fixtures";

vi.mock("./lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./lib/api")>();
  return {
    ...actual,
    getHealth: vi.fn(),
    listScenarios: vi.fn(),
    runScenario: vi.fn(),
    analyze: vi.fn(),
    fetchReport: vi.fn(),
  };
});

// Recharts cannot lay out inside jsdom; the dashboard logic is what these tests cover.
vi.mock("recharts", () => {
  const Box = ({ children }: { children?: React.ReactNode }) => <div>{children}</div>;
  return {
    ResponsiveContainer: Box, BarChart: Box, PieChart: Box, Pie: Box, Bar: Box, Cell: Box,
    CartesianGrid: Box, XAxis: Box, YAxis: Box, Tooltip: Box, ReferenceArea: Box,
  };
});

const mocked = vi.mocked(api);

beforeEach(() => {
  vi.resetAllMocks();
  mocked.getHealth.mockResolvedValue({ status: "ok", version: "0.1.0" });
  mocked.listScenarios.mockResolvedValue([SCENARIO]);
});

describe("App", () => {
  it("shows API status and demo scenarios on load", async () => {
    render(<App />);
    expect(await screen.findByText(/API online · v0.1.0/)).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: /Database connection pool exhaustion/ })).toBeInTheDocument();
    expect(screen.getByText("Turn raw logs into an incident report")).toBeInTheDocument();
  });

  it("warns when the backend is unreachable", async () => {
    mocked.getHealth.mockRejectedValue(new Error("down"));
    render(<App />);
    expect(await screen.findByText(/API is not reachable/)).toBeInTheDocument();
  });

  it("runs a demo scenario and renders the dashboard", async () => {
    mocked.runScenario.mockResolvedValue({ scenario: SCENARIO, analysis: makeAnalysis() });
    render(<App />);
    await userEvent.click(await screen.findByRole("button", { name: /Database connection pool exhaustion/ }));

    expect(await screen.findByText("Ranked root-cause hypotheses")).toBeInTheDocument();
    expect(mocked.runScenario).toHaveBeenCalledWith("db-pool-exhaustion");
    expect(screen.getByText("Events analyzed")).toBeInTheDocument();
    expect(screen.getByText("Recommended investigation steps")).toBeInTheDocument();
    expect(screen.getByText(/The engine's output matches this expectation/)).toBeInTheDocument();
    expect(screen.getAllByTestId("log-row").length).toBe(6);
    expect(screen.getByRole("button", { name: "Export Markdown" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Export JSON" })).toBeEnabled();
  });

  it("surfaces API errors from manual analysis", async () => {
    mocked.analyze.mockRejectedValue(new api.ApiError("Input is 30 MiB; the limit is 20 MiB.", 413, "input_too_large"));
    render(<App />);
    await userEvent.click(screen.getByRole("tab", { name: "Manual entry" }));
    await userEvent.type(screen.getByLabelText("Log content"), "something");
    await userEvent.click(screen.getByRole("button", { name: "Analyze" }));
    expect(await screen.findByText(/the limit is 20 MiB/)).toBeInTheDocument();
    expect(screen.queryByText("Ranked root-cause hypotheses")).toBeNull();
  });

  it("analyzes pasted content and hides the expected-outcome card for non-demo input", async () => {
    mocked.analyze.mockResolvedValue(makeAnalysis());
    render(<App />);
    await userEvent.click(screen.getByRole("tab", { name: "Manual entry" }));
    await userEvent.type(screen.getByLabelText("Log content"), "2025-03-14T09:00:00Z ERROR [[a] boom");  // "[[" types a literal "[" (user-event key syntax)
    await userEvent.click(screen.getByRole("button", { name: "Analyze" }));
    await waitFor(() => expect(mocked.analyze).toHaveBeenCalledWith("2025-03-14T09:00:00Z ERROR [a] boom", "auto"));
    expect(await screen.findByText("Ranked root-cause hypotheses")).toBeInTheDocument();
    expect(screen.queryByText("Documented expected outcome")).toBeNull();
  });

  it("exports a Markdown report for the current analysis", async () => {
    mocked.runScenario.mockResolvedValue({ scenario: SCENARIO, analysis: makeAnalysis() });
    mocked.fetchReport.mockResolvedValue("# IncidentLens incident report");
    const createUrl = vi.fn(() => "blob:fake");
    Object.assign(URL, { createObjectURL: createUrl, revokeObjectURL: vi.fn() });
    render(<App />);
    await userEvent.click(await screen.findByRole("button", { name: /Database connection pool exhaustion/ }));
    await userEvent.click(await screen.findByRole("button", { name: "Export Markdown" }));
    await waitFor(() => expect(mocked.fetchReport).toHaveBeenCalledWith({ kind: "demo", scenarioId: "db-pool-exhaustion" }, "markdown"));
    await waitFor(() => expect(createUrl).toHaveBeenCalled());
  });
});

describe("App in static demonstration mode", () => {
  it("identifies itself, disables ad-hoc analysis and explains how to run locally", async () => {
    vi.stubEnv("VITE_STATIC_DEMO", "true");
    mocked.getHealth.mockResolvedValue({ status: "static", version: "0.1.0" });
    render(<App />);
    expect(await screen.findByTestId("static-demo-banner")).toHaveTextContent(/Static demonstration/);
    expect(await screen.findByText(/Static demo · v0.1.0/)).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Upload" })).toBeDisabled();
    expect(screen.getByTestId("static-demo-help")).toBeInTheDocument();
    expect(screen.queryByText(/API is not reachable/)).not.toBeInTheDocument();
    vi.unstubAllEnvs();
  });

  it("shows no static banner in full-stack mode", async () => {
    render(<App />);
    await screen.findByText(/API online/);
    expect(screen.queryByTestId("static-demo-banner")).not.toBeInTheDocument();
  });
});
