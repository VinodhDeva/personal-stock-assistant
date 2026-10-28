import {
  motion,
  useMotionTemplate,
  useMotionValue,
  useReducedMotion,
  useSpring,
  useTransform,
} from "motion/react";
import type { PointerEvent, ReactNode } from "react";

const SPRING = { stiffness: 260, damping: 22, mass: 0.6 };

interface Props {
  children: ReactNode;
  className?: string;
  as?: "div" | "article" | "section";
  /** Max tilt in degrees at the card edge. Keep small on large cards. */
  maxTilt?: number;
  glare?: boolean;
  "aria-label"?: string;
}

/**
 * Card that tilts toward the pointer in 3D. Direct children marked `.tilt-pop` float above the surface (translateZ).
 * Pointer position is stored in motion values, so moving never re-renders React.
 */
export function Tilt3D({ children, className = "", as = "div", maxTilt = 10, glare = true, ...rest }: Props) {
  const reduce = useReducedMotion();
  const px = useMotionValue(0.5);
  const py = useMotionValue(0.5);
  const rotateX = useSpring(useTransform(py, [0, 1], [maxTilt, -maxTilt]), SPRING);
  const rotateY = useSpring(useTransform(px, [0, 1], [-maxTilt, maxTilt]), SPRING);
  const gx = useTransform(px, [0, 1], ["0%", "100%"]);
  const gy = useTransform(py, [0, 1], ["0%", "100%"]);
  const glareBg = useMotionTemplate`radial-gradient(circle at ${gx} ${gy}, var(--glare), transparent 60%)`;
  const Tag = motion[as];

  if (reduce) {
    const Plain = as;
    return (
      <Plain className={`tilt ${className}`} {...rest}>
        {children}
      </Plain>
    );
  }

  const move = (e: PointerEvent<HTMLElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    px.set((e.clientX - r.left) / r.width);
    py.set((e.clientY - r.top) / r.height);
  };
  const reset = () => {
    px.set(0.5);
    py.set(0.5);
  };

  return (
    <Tag
      className={`tilt ${className}`}
      onPointerMove={move}
      onPointerLeave={reset}
      style={{ rotateX, rotateY, transformPerspective: 900, transformStyle: "preserve-3d" }}
      initial={{ opacity: 0, y: 14, scale: 0.97 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      whileHover={{ scale: 1.03, transition: { type: "spring", bounce: 0.3, duration: 0.4, out: true } }}
      transition={{ type: "spring", bounce: 0.25, duration: 0.5 }}
      {...rest}
    >
      {children}
      {glare && <motion.span className="tilt-glare" aria-hidden="true" style={{ background: glareBg }} />}
    </Tag>
  );
}
