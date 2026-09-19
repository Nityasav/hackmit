"use client";

import { motion, useInView, useReducedMotion } from "framer-motion";
import type { ReactNode, RefObject } from "react";

/**
 * Reveals a grid cell once the section scrolls into view. `animationNum` is the
 * cell's place in the stagger, so the grid fills in reading order rather than
 * every card animating at once.
 */
export function TimelineAnimation({
  children,
  className,
  animationNum,
  timelineRef,
}: {
  children: ReactNode;
  className?: string;
  animationNum: number;
  timelineRef: RefObject<HTMLDivElement | null>;
}) {
  const inView = useInView(timelineRef, { once: true, margin: "-12% 0px" });
  const reduceMotion = useReducedMotion();

  if (reduceMotion) {
    return <div className={className}>{children}</div>;
  }

  return (
    <motion.div
      className={className}
      initial={{ opacity: 0, y: 12 }}
      animate={inView ? { opacity: 1, y: 0 } : { opacity: 0, y: 12 }}
      transition={{
        duration: 0.32,
        delay: animationNum * 0.06,
        ease: [0.22, 1, 0.36, 1],
      }}
    >
      {children}
    </motion.div>
  );
}
