import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MAX_UPLOAD_BYTES } from "../lib/api";
import { SCENARIO } from "../test/fixtures";
import IngestPanel from "./IngestPanel";

function setup(overrides: Partial<React.ComponentProps<typeof IngestPanel>> = {}) {
  const props = {
    scenarios: [SCENARIO],
    busy: false,
    activeScenarioId: null,
    onAnalyze: vi.fn(),
    onSelectScenario: vi.fn(),
    ...overrides,
  };
  render(<IngestPanel {...props} />);
  return props;
}

describe("IngestPanel", () => {
  it("starts on demo scenarios and selects one on click", async () => {
    const props = setup();
    await userEvent.click(screen.getByRole("button", { name: /Database connection pool exhaustion/ }));
    expect(props.onSelectScenario).toHaveBeenCalledWith("db-pool-exhaustion");
  });

  it("submits manual entry with the chosen format", async () => {
    const props = setup();
    await userEvent.click(screen.getByRole("tab", { name: "Manual entry" }));
    const analyze = screen.getByRole("button", { name: "Analyze" });
    expect(analyze).toBeDisabled();

    await userEvent.type(screen.getByLabelText("Log content"), "2025-03-14T09:00:00Z ERROR [[a] boom");  // "[[" types a literal "[" (user-event key syntax)
    await userEvent.selectOptions(screen.getByLabelText("Log format"), "plaintext");
    expect(analyze).toBeEnabled();
    await userEvent.click(analyze);
    expect(props.onAnalyze).toHaveBeenCalledWith("2025-03-14T09:00:00Z ERROR [a] boom", "plaintext", "manual entry");
  });

  it("disables Analyze while busy", async () => {
    setup({ busy: true });
    await userEvent.click(screen.getByRole("tab", { name: "Manual entry" }));
    await userEvent.type(screen.getByLabelText("Log content"), "x");
    expect(screen.getByRole("button", { name: "Analyzing…" })).toBeDisabled();
  });

  it("analyzes an uploaded file", async () => {
    const props = setup();
    await userEvent.click(screen.getByRole("tab", { name: "Upload" }));
    const file = new File(["2025-03-14T09:00:00Z INFO [a] hi"], "app.log", { type: "text/plain" });
    await userEvent.upload(screen.getByTestId("file-input"), file);
    await waitFor(() => expect(props.onAnalyze).toHaveBeenCalledWith("2025-03-14T09:00:00Z INFO [a] hi", "auto", "app.log"));
  });

  it("rejects oversized files client-side without reading them", async () => {
    const props = setup();
    await userEvent.click(screen.getByRole("tab", { name: "Upload" }));
    const big = new File(["x"], "huge.log");
    Object.defineProperty(big, "size", { value: MAX_UPLOAD_BYTES + 1 });
    await userEvent.upload(screen.getByTestId("file-input"), big);
    expect(await screen.findByRole("alert")).toHaveTextContent(/huge\.log.*limit/);
    expect(props.onAnalyze).not.toHaveBeenCalled();
  });

  it("rejects empty files", async () => {
    const props = setup();
    await userEvent.click(screen.getByRole("tab", { name: "Upload" }));
    await userEvent.upload(screen.getByTestId("file-input"), new File(["   "], "empty.log"));
    expect(await screen.findByRole("alert")).toHaveTextContent(/empty/);
    expect(props.onAnalyze).not.toHaveBeenCalled();
  });
});

describe("IngestPanel in static demonstration mode", () => {
  afterEach(() => vi.unstubAllEnvs());

  it("disables upload and manual entry, explains why, and still lists scenarios", async () => {
    vi.stubEnv("VITE_STATIC_DEMO", "true");
    const props = { scenarios: [SCENARIO], busy: false, activeScenarioId: null, onAnalyze: vi.fn(), onSelectScenario: vi.fn() };
    render(<IngestPanel {...props} />);
    expect(screen.getByRole("tab", { name: "Upload" })).toBeDisabled();
    expect(screen.getByRole("tab", { name: "Manual entry" })).toBeDisabled();
    expect(screen.getByTestId("static-demo-help")).toHaveTextContent(/docker compose up/);
    await userEvent.click(screen.getByRole("button", { name: /Database connection pool exhaustion/ }));
    expect(props.onSelectScenario).toHaveBeenCalledWith("db-pool-exhaustion");
  });
});
