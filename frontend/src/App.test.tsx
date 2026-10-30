import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { App } from "./App";

describe("App", () => {
  it("renders the foundation heading and non-authoritative status text", () => {
    render(<App />);
    expect(screen.getByRole("heading", { name: /finpilot ai/i })).toBeInTheDocument();
    expect(screen.getByText(/no trading features are implemented yet/i)).toBeInTheDocument();
  });
});
