"use client";

import { useEffect, useState } from "react";
import { AppleLogo, WindowsLogo } from "@phosphor-icons/react";
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
  const [platform, setPlatform] = useState<Platform | null>(force ?? null);

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

  const Icon = platform === "win" ? WindowsLogo : AppleLogo;

  return (
    <a href={href} className={`btn-primary ${className ?? ""}`}>
      {platform === "other" ? null : <Icon size={16} weight="fill" />}
      {label}
    </a>
  );
}
