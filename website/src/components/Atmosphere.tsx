type AtmosphereProps = {
  mode?: "fixed" | "fill";
};

export function Atmosphere({ mode = "fixed" }: AtmosphereProps) {
  const wrap =
    mode === "fixed"
      ? "pointer-events-none fixed inset-0 z-[var(--z-glow)] overflow-hidden"
      : "pointer-events-none absolute inset-0 overflow-hidden";

  return (
    <div aria-hidden="true" className={wrap}>
      <div className="absolute inset-0 atmosphere-wash" />
      <div
        className="absolute left-[30%] top-[40%] h-[460px] w-[700px] rounded-full blur-[100px]"
        style={{
          background: "radial-gradient(circle, var(--glow-blue), transparent 68%)",
        }}
      />
      <div
        className="absolute right-[4%] top-[2%] h-[420px] w-[520px] rounded-full blur-[90px]"
        style={{
          background: "radial-gradient(circle, var(--glow-teal), transparent 66%)",
        }}
      />
      <div
        className="absolute bottom-[-8%] left-[6%] h-[360px] w-[560px] rounded-full blur-[110px]"
        style={{
          background: "radial-gradient(circle, var(--glow-warm), transparent 68%)",
        }}
      />
    </div>
  );
}
