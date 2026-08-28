"use client";

import { useEffect, useRef, useState } from "react";
import {
  motion,
  useMotionValue,
  useSpring,
  useReducedMotion,
} from "motion/react";
import { AppleLogo, ArrowDown, WindowsLogo } from "@phosphor-icons/react";
import type { LatestRelease } from "@/release/github";

type Platform = "mac" | "win" | "other";

function detectPlatform(): Platform {
  const ua = navigator.userAgent;
  const platform =
    (navigator as Navigator & { userAgentData?: { platform?: string } })
      .userAgentData?.platform ??
    navigator.platform ??
    "";
  const hay = `${ua} ${platform}`;
  if (/Mac|iPhone|iPad|Macintosh/i.test(hay)) return "mac";
  if (/Win/i.test(hay)) return "win";
  return "other";
}

type Props = {
  release: LatestRelease;
  force?: Platform;
  className?: string;
};

export function DownloadButton({ release, force, className }: Props) {
  const reduce = useReducedMotion();
  const [platform, setPlatform] = useState<Platform | null>(force ?? null);
  const ref = useRef<HTMLAnchorElement>(null);
  const mx = useMotionValue(0);
  const my = useMotionValue(0);
  const x = useSpring(mx, { stiffness: 160, damping: 18, mass: 0.4 });
  const y = useSpring(my, { stiffness: 160, damping: 18, mass: 0.4 });

  useEffect(() => {
    if (force) {
      setPlatform(force);
      return;
    }
    setPlatform(detectPlatform());
  }, [force]);

  if (platform === null) {
    return (
      <span className={`btn-skeleton ${className ?? ""}`} aria-hidden="true" />
    );
  }

  const href =
    platform === "mac" && release.macDmg
      ? release.macDmg
      : platform === "win" && release.winExe
        ? release.winExe
        : release.htmlUrl;

  const label =
    platform === "mac"
      ? "Download for macOS"
      : platform === "win"
        ? "Download for Windows"
        : "Download";

  const Icon = platform === "win" ? WindowsLogo : platform === "mac" ? AppleLogo : ArrowDown;

  return (
    <motion.a
      ref={ref}
      href={href}
      className={`btn-primary ${className ?? ""}`}
      style={reduce ? undefined : { x, y }}
      onMouseMove={(e) => {
        if (reduce || !ref.current) return;
        const r = ref.current.getBoundingClientRect();
        mx.set((e.clientX - r.left - r.width / 2) * 0.28);
        my.set((e.clientY - r.top - r.height / 2) * 0.28);
      }}
      onMouseLeave={() => {
        mx.set(0);
        my.set(0);
      }}
    >
      <span>{label}</span>
      <span className="btn-primary-icon">
        <Icon size={14} weight="bold" />
      </span>
    </motion.a>
  );
}
