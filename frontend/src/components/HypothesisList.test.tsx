import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { makeAnalysis } from "../test/fixtures";
import HypothesisList from "./HypothesisList";

describe("HypothesisList", () => {
  it("ranks hypotheses and labels scores as heuristic", () => {
    render(<HypothesisList analysis={makeAnalysis()} />);
    const headers = screen.getAllByRole("button");
    expect(headers).toHaveLength(2);
    expect(headers[0]).toHaveTextContent("Database connection pool exhaustion");
    expect(headers[0]).toHaveTextContent("84.2");
    expect(screen.getByText(/not statistical probabilities/)).toBeInTheDocument();
    expect(screen.getAllByRole("meter")[0]).toHaveAttribute("aria-valuenow", "84.2");
  });

  it("expands the top hypothesis by default, showing evidence, score breakdown and actions", () => {
    render(<HypothesisList analysis={makeAnalysis()} />);
    expect(screen.getByText("Supporting evidence")).toBeInTheDocument();
    expect(screen.getByText("How the score was computed")).toBeInTheDocument();
    expect(screen.getByText("Compare pool size, in-use and waiting counts.")).toBeInTheDocument();
    expect(screen.getByText("Matching volume")).toBeInTheDocument();
  });

  it("toggles lower-ranked hypotheses", async () => {
    render(<HypothesisList analysis={makeAnalysis()} />);
    const second = screen.getByRole("button", { name: /Elevated HTTP 5xx/ });
    expect(second).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(second);
    expect(second).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("Treat 5xx as a symptom.")).toBeInTheDocument();
  });

  it("states insufficient evidence instead of inventing a cause", () => {
    render(<HypothesisList analysis={makeAnalysis({ hypotheses: [], verdict: "insufficient_evidence", verdict_reason: "No known failure pattern had enough evidence." })} />);
    expect(screen.getByRole("status")).toHaveTextContent("Insufficient evidence");
    expect(screen.getByRole("status")).toHaveTextContent("No known failure pattern");
    expect(screen.queryByRole("meter")).toBeNull();
  });

  it("states no incident for healthy systems", () => {
    render(<HypothesisList analysis={makeAnalysis({ hypotheses: [], verdict: "no_incident", verdict_reason: "within routine noise" })} />);
    expect(screen.getByRole("status")).toHaveTextContent("No incident");
  });
});
