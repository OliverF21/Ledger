"use client";

import Image from "next/image";
import { motion, useReducedMotion } from "motion/react";
import { DeviceFrame } from "@/components/DeviceFrame";
import { site } from "@/content/site";

export function HeroProduct() {
  const reduce = useReducedMotion();

  return (
    <motion.div
      className="origin-top-right"
      initial={reduce ? false : { opacity: 0, y: 36, rotateX: 8 }}
      animate={{ opacity: 1, y: 0, rotateX: 0 }}
      transition={{ duration: 0.9, delay: 0.12, ease: [0.22, 0.8, 0.2, 1] }}
    >
      <div className="hero-product-tilt">
        <DeviceFrame>
          <Image
            src={site.shots.hero}
            alt={site.hero.shotAlt}
            width={1600}
            height={1000}
            priority
            sizes="(min-width: 1024px) 62vw, 100vw"
            className="h-auto w-full"
          />
        </DeviceFrame>
      </div>
    </motion.div>
  );
}
