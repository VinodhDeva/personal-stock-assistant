import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { MotionGlobalConfig } from "motion/react";
import { afterEach, vi } from "vitest";

MotionGlobalConfig.skipAnimations = true;

// jsdom has no PointerEvent, so fireEvent.pointerMove would drop clientX/clientY.
if (!("PointerEvent" in window)) {
  Object.assign(window, { PointerEvent: class PointerEvent extends MouseEvent {} });
}

// Canvas charts cannot render in jsdom; the chart library is replaced with no-op stubs.
vi.mock("lightweight-charts", () => {
  const series = { setData: vi.fn(), createPriceLine: vi.fn(), priceScale: () => ({ applyOptions: vi.fn() }) };
  return {
    createChart: () => ({ addSeries: () => series, timeScale: () => ({ fitContent: vi.fn() }), remove: vi.fn() }),
    CandlestickSeries: {},
    HistogramSeries: {},
    LineSeries: {},
    ColorType: { Solid: "solid" },
  };
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
