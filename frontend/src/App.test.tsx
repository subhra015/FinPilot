import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { App } from "./App";

describe("App", () => {
  it("renders the dashboard brand and initial research view", async () => {
    render(<App />);
    expect(screen.getByText("FinPilot AI")).toBeInTheDocument();
    expect(await screen.findByText(/Research Status & Specification/i)).toBeInTheDocument();
    expect(screen.getByText(/Evaluation Benchmark Hurdle/i)).toBeInTheDocument();
    expect(screen.getByText(/No live broker trading features are implemented yet/i)).toBeInTheDocument();
  });
});
