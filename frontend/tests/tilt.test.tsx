import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Tilt3D } from "../src/components/Tilt3D";

const rect = { left: 0, top: 0, width: 200, height: 100, right: 200, bottom: 100, x: 0, y: 0, toJSON: () => ({}) };

describe("Tilt3D", () => {
  it("tilts toward the pointer and resets on leave", async () => {
    render(
      <Tilt3D aria-label="tile">
        <dd>₹10</dd>
      </Tilt3D>,
    );
    const el = screen.getByLabelText("tile");
    vi.spyOn(el, "getBoundingClientRect").mockReturnValue(rect as DOMRect);
    fireEvent.pointerMove(el, { clientX: 200, clientY: 0 }); // top-right corner
    await waitFor(() => expect(el.style.transform).toMatch(/rotateX\(10deg\).*rotateY\(10deg\)/));
    fireEvent.pointerLeave(el);
    await waitFor(() => expect(el.style.transform).not.toMatch(/rotate[XY]\(10deg\)/));
    expect(screen.getByText("₹10")).toBeInTheDocument();
  });
});
