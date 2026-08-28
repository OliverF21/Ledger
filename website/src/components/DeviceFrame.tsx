import type { ReactNode } from "react";

export function DeviceFrame({
  children,
  softClip = false,
}: {
  children: ReactNode;
  softClip?: boolean;
}) {
  return (
    <div className="glass-frame p-1.5 sm:p-2">
      <div
        className={softClip ? "device-frame-soft" : "overflow-hidden"}
        style={{ borderRadius: "calc(var(--radius-frame) - 7px)" }}
      >
        {children}
      </div>
    </div>
  );
}
