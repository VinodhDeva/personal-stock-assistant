import {
  CandlestickSeries,
  ColorType,
  HistogramSeries,
  LineSeries,
  createChart,
  type IChartApi,
  type UTCTimestamp,
} from "lightweight-charts";
import { useEffect, useRef } from "react";

import type { Candle, IndicatorPoint } from "../types/api";

const css = (name: string) => getComputedStyle(document.documentElement).getPropertyValue(name).trim() || "#888";

function useChart(height: number, build: (chart: IChartApi) => void, deps: unknown[]) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!ref.current) return;
    const chart = createChart(ref.current, {
      height,
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: "transparent" }, textColor: css("--muted") },
      grid: { vertLines: { color: css("--grid") }, horzLines: { color: css("--grid") } },
      timeScale: { borderColor: css("--border") },
      rightPriceScale: { borderColor: css("--border") },
    });
    build(chart);
    chart.timeScale().fitContent();
    return () => chart.remove();
  }, deps);
  return ref;
}

const t = (s: number) => s as UTCTimestamp;
const line = (pts: IndicatorPoint[], key: keyof IndicatorPoint) =>
  pts.filter((p) => p[key] != null).map((p) => ({ time: t(p.time), value: p[key] as number }));

export function PriceChart({ candles, indicators }: { candles: Candle[]; indicators: IndicatorPoint[] }) {
  const ref = useChart(
    380,
    (chart) => {
      const up = css("--up");
      const down = css("--down");
      chart
        .addSeries(CandlestickSeries, { upColor: up, downColor: down, wickUpColor: up, wickDownColor: down, borderVisible: false })
        .setData(candles.map((c) => ({ time: t(c.time), open: c.open, high: c.high, low: c.low, close: c.close })));
      chart.addSeries(LineSeries, { color: css("--series-1"), lineWidth: 1, title: "SMA20" }).setData(line(indicators, "sma_20"));
      chart.addSeries(LineSeries, { color: css("--series-2"), lineWidth: 1, title: "SMA50" }).setData(line(indicators, "sma_50"));
      const vol = chart.addSeries(HistogramSeries, { priceScaleId: "vol", priceFormat: { type: "volume" } });
      vol.priceScale().applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });
      vol.setData(
        candles.map((c) => ({ time: t(c.time), value: c.volume, color: c.close >= c.open ? css("--up-soft") : css("--down-soft") })),
      );
    },
    [candles, indicators],
  );
  return <div ref={ref} className="chart" role="img" aria-label="Candlestick price chart with SMA20, SMA50 and volume" />;
}

export function RsiChart({ indicators }: { indicators: IndicatorPoint[] }) {
  const ref = useChart(
    160,
    (chart) => {
      const s = chart.addSeries(LineSeries, { color: css("--series-1"), lineWidth: 2, title: "RSI14" });
      s.setData(line(indicators, "rsi_14"));
      s.createPriceLine({ price: 70, color: css("--down"), lineStyle: 2, lineWidth: 1, axisLabelVisible: true, title: "70" });
      s.createPriceLine({ price: 30, color: css("--up"), lineStyle: 2, lineWidth: 1, axisLabelVisible: true, title: "30" });
    },
    [indicators],
  );
  return <div ref={ref} className="chart" role="img" aria-label="RSI 14 chart with 30 and 70 levels" />;
}

export function MacdChart({ indicators }: { indicators: IndicatorPoint[] }) {
  const ref = useChart(
    160,
    (chart) => {
      chart
        .addSeries(HistogramSeries, { title: "Hist" })
        .setData(
          indicators
            .filter((p) => p.macd_hist != null)
            .map((p) => ({ time: t(p.time), value: p.macd_hist!, color: p.macd_hist! >= 0 ? css("--up-soft") : css("--down-soft") })),
        );
      chart.addSeries(LineSeries, { color: css("--series-1"), lineWidth: 2, title: "MACD" }).setData(line(indicators, "macd"));
      chart.addSeries(LineSeries, { color: css("--series-2"), lineWidth: 1, title: "Signal" }).setData(line(indicators, "macd_signal"));
    },
    [indicators],
  );
  return <div ref={ref} className="chart" role="img" aria-label="MACD 12 26 9 chart" />;
}
