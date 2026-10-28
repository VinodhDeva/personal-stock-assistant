import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Tilt3D } from "../src/components/Tilt3D";

vi.mock("motion/react", async (orig) => ({ ...(await orig<typeof import("motion/react")>()), useReducedMotion: () => true }));

describe("Tilt3D with reduced motion", () => {
  it("renders a static element with no transform or glare", () => {
    render(
      <Tilt3D as="article" aria-label="card">
        x
      </Tilt3D>,
    );
    const el = screen.getByRole("article", { name: "card" });
    expect(el.style.transform).toBe("");
    expect(el.querySelector(".tilt-glare")).toBeNull();
  });
});
