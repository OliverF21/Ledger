"use client";

import dynamic from "next/dynamic";
import type { MutableRefObject } from "react";

const MacBookCanvas = dynamic(
  () => import("./MacBookCanvas").then((mod) => mod.MacBookCanvas),
  { ssr: false, loading: () => <div className="macbook-3d-fallback" aria-hidden="true" /> },
);

type MacBookProps = {
  progressRef: MutableRefObject<number>;
  freeze?: boolean;
  variant?: "desktop" | "mobile";
  className?: string;
};

export function MacBook({
  progressRef,
  freeze = false,
  variant = "desktop",
  className,
}: MacBookProps) {
  return (
    <div className={`macbook-3d ${variant === "mobile" ? "macbook-3d-mobile" : ""} ${className ?? ""}`}>
      <MacBookCanvas progressRef={progressRef} freeze={freeze} variant={variant} />
    </div>
  );
}
