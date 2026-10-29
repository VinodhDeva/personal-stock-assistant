import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AnimatedNumber } from "../src/components/AnimatedNumber";
import { money } from "../src/services/format";

describe("AnimatedNumber", () => {
  it("counts up from `from` and settles on each new value", async () => {
    const { rerender } = render(<AnimatedNumber from={0} value={1500} format={money} />);
    await waitFor(() => expect(screen.getByText("₹1,500.00")).toBeInTheDocument());
    rerender(<AnimatedNumber from={0} value={1234.5} format={money} />);
    await waitFor(() => expect(screen.getByText("₹1,234.50")).toBeInTheDocument());
  });

  it("starts at the value itself when no `from` is given", () => {
    render(<AnimatedNumber value={42} format={(v) => String(Math.round(v))} />);
    expect(screen.getByText("42")).toBeInTheDocument();
  });
});
