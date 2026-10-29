import { animate, motion, useMotionValue, useTransform } from "motion/react";
import { useEffect } from "react";

interface Props {
  value: number;
  format: (v: number) => string;
  /** Starting value on first mount (e.g. 0 for a count-up). Defaults to `value`: no animation on load. */
  from?: number;
}

/** Counts from the previous value to the new one. Text updates through a motion value, so React does not re-render. */
export function AnimatedNumber({ value, format, from = value }: Props) {
  const v = useMotionValue(from);
  const text = useTransform(v, format);
  useEffect(() => animate(v, value, { duration: 0.8, ease: [0.16, 1, 0.3, 1] }).stop, [v, value]);
  return <motion.span>{text}</motion.span>;
}
