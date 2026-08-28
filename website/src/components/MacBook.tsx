"use client";

import type { MutableRefObject } from "react";
import { MacBookMockup } from "@/components/MacBookMockup";

type MacBookProps = {
  progressRef: MutableRefObject<number>;
  freeze?: boolean;
  className?: string;
};

export function MacBook({ progressRef, freeze = false, className }: MacBookProps) {
  return (
    <div className={`macbook-mockup-wrap ${className ?? ""}`}>
      <MacBookMockup progressRef={progressRef} freeze={freeze} />
    </div>
  );
}
