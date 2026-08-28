import type { ReactNode } from "react";
import Image from "next/image";
import { site } from "@/content/site";

type MacBookProps = {
  children: ReactNode;
  className?: string;
};

export function MacBook({ children, className }: MacBookProps) {
  return (
    <div className={`macbook-photo ${className ?? ""}`}>
      <Image
        src={site.shots.macbook}
        alt=""
        width={1536}
        height={1024}
        priority
        sizes="(min-width: 1024px) 58vw, 94vw"
        className="macbook-photo-body"
      />
      <div className="macbook-photo-screen">{children}</div>
      <span className="macbook-photo-glass" aria-hidden="true" />
    </div>
  );
}
