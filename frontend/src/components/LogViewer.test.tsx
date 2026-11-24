import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { EVENTS, makeEvent } from "../test/fixtures";
import LogViewer from "./LogViewer";

const base = { events: EVENTS, total: EVENTS.length, truncated: false, window: null, onClearWindow: () => undefined };
const rows = () => screen.queryAllByTestId("log-row");

describe("LogViewer", () => {
  it("renders every event with severity and service", () => {
    render(<LogViewer {...base} />);
    expect(rows()).toHaveLength(6);
    expect(within(rows()[2]).getByText("ERROR")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("6 matching");
  });

  it("filters by search text", async () => {
    render(<LogViewer {...base} />);
    await userEvent.type(screen.getByLabelText("Search logs"), "pool");
    expect(rows()).toHaveLength(2);
    expect(screen.getByRole("status")).toHaveTextContent("2 matching");
  });

  it("filters by severity toggle", async () => {
    render(<LogViewer {...base} />);
    const group = screen.getByRole("group", { name: "Filter by severity" });
    await userEvent.click(within(group).getByRole("button", { name: "INFO" }));
    expect(within(group).getByRole("button", { name: "INFO" })).toHaveAttribute("aria-pressed", "false");
    expect(rows()).toHaveLength(4);
  });

  it("filters by service and resets", async () => {
    render(<LogViewer {...base} />);
    await userEvent.selectOptions(screen.getByLabelText("Filter by service"), "orders-api");
    expect(rows()).toHaveLength(2);
    await userEvent.click(screen.getByRole("button", { name: "Reset" }));
    expect(rows()).toHaveLength(6);
    expect(screen.getByRole("button", { name: "Reset" })).toBeDisabled();
  });

  it("shows an empty state when nothing matches", async () => {
    render(<LogViewer {...base} />);
    await userEvent.type(screen.getByLabelText("Search logs"), "zzz-no-match");
    expect(rows()).toHaveLength(0);
    expect(screen.getByText("No events match the current filters.")).toBeInTheDocument();
  });

  it("restricts to a selected time window and can clear it", async () => {
    const onClear = vi.fn();
    const t0 = Date.parse(EVENTS[0].timestamp as string);
    render(<LogViewer {...base} window={{ start: t0 + 10_000, end: t0 + 30_000 }} onClearWindow={onClear} />);
    expect(rows()).toHaveLength(2);
    await userEvent.click(screen.getByRole("button", { name: "Clear" }));
    expect(onClear).toHaveBeenCalled();
  });

  it("pages large result sets and explains truncation", async () => {
    const many = Array.from({ length: 450 }, (_, i) => makeEvent(i, i, "INFO", "svc", `line ${i}`));
    render(<LogViewer {...base} events={many} total={9000} truncated />);
    expect(rows()).toHaveLength(200);
    expect(screen.getByText(/Showing 450 of 9,000 events/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Show 200 more/ }));
    expect(rows()).toHaveLength(400);
    await userEvent.click(screen.getByRole("button", { name: /Show 50 more/ }));
    expect(rows()).toHaveLength(450);
  });

  it("renders log text as text, never as HTML", () => {
    const hostile = [makeEvent(0, 0, "ERROR", "a", "<img src=x onerror=alert(1)> <b>bold</b>")];
    const { container } = render(<LogViewer {...base} events={hostile} total={1} />);
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("b")).toBeNull();
    expect(screen.getByText(/<img src=x/)).toBeInTheDocument();
  });
});
