import type { ReactNode } from "react";

type MacBookProps = {
  children: ReactNode;
  className?: string;
};

export function MacBook({ children, className }: MacBookProps) {
  return (
    <div className={`macbook-scene ${className ?? ""}`}>
      <div className="macbook">
        <div className="macbook-lid">
          <div className="macbook-bezel">
            <span className="macbook-camera" aria-hidden="true" />
            <div className="macbook-screen">{children}</div>
          </div>
        </div>
        <div className="macbook-base" aria-hidden="true">
          <div className="macbook-hinge" />
          <div className="macbook-deck">
            <div className="macbook-keys" />
            <div className="macbook-trackpad" />
          </div>
          <div className="macbook-front" />
        </div>
      </div>
    </div>
  );
}
