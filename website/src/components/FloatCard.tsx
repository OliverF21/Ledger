"use client";

import { useRef, type ReactNode } from "react";
import {
  motion,
  useMotionValue,
  useSpring,
  useReducedMotion,
} from "motion/react";

type FloatCardProps = {
  children: ReactNode;
  className?: string;
  delay?: number;
};

export function FloatCard({ children, className, delay = 0 }: FloatCardProps) {
  const reduce = useReducedMotion();
  const ref = useRef<HTMLDivElement>(null);
  const rx = useMotionValue(0);
  const ry = useMotionValue(0);
  const rotateX = useSpring(rx, { stiffness: 220, damping: 18, mass: 0.35 });
  const rotateY = useSpring(ry, { stiffness: 220, damping: 18, mass: 0.35 });

  return (
    <motion.div
      ref={ref}
      className={className}
      style={
        reduce ? undefined : { rotateX, rotateY, transformPerspective: 920 }
      }
      animate={reduce ? undefined : { y: [0, -9, 0] }}
      transition={
        reduce
          ? undefined
          : {
              y: {
                duration: 5.4 + delay * 3.2,
                repeat: Infinity,
                ease: "easeInOut",
                delay,
              },
            }
      }
      whileHover={
        reduce
          ? undefined
          : {
              scale: 1.025,
              zIndex: 4,
              transition: { type: "spring", stiffness: 280, damping: 18 },
            }
      }
      onMouseMove={(e) => {
        if (reduce || !ref.current) return;
        const r = ref.current.getBoundingClientRect();
        const px = (e.clientX - r.left) / r.width;
        const py = (e.clientY - r.top) / r.height;
        ry.set((px - 0.5) * 9);
        rx.set((0.5 - py) * 9);
      }}
      onMouseLeave={() => {
        rx.set(0);
        ry.set(0);
      }}
    >
      {children}
    </motion.div>
  );
}
