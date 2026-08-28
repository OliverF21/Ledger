export function Glow() {
  return (
    <div
      aria-hidden="true"
      className="pointer-events-none fixed inset-0 z-[var(--z-glow)] overflow-hidden"
    >
      <div
        className="absolute inset-0"
        style={{
          background:
            "radial-gradient(1200px 860px at 90% -14%, var(--glow-cool), transparent 66%), linear-gradient(166deg, var(--canvas-hi) 0%, var(--canvas-mid) 48%, var(--canvas) 100%)",
        }}
      />
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
