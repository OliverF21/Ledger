"use client";

import dynamic from "next/dynamic";
import type { MutableRefObject } from "react";

const MacBookCanvas = dynamic(
  () => import("./MacBookCanvas").then((mod) => mod.MacBookCanvas),
  { ssr: false, loading: () => <div className="macbook-3d-fallback" aria-hidden="true" /> },
);

type MacBookProps = {
  active: number;
  progressRef: MutableRefObject<number>;
  freeze?: boolean;
  className?: string;
};

export function MacBook({ active, progressRef, freeze = false, className }: MacBookProps) {
  return (
    <div className={`macbook-3d ${className ?? ""}`}>
      <MacBookCanvas active={active} progressRef={progressRef} freeze={freeze} />
    </div>
  );
}
