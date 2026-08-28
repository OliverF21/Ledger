import Image from "next/image";
import { FloatCard } from "@/components/FloatCard";
import { Reveal } from "@/components/Reveal";
import { site } from "@/content/site";

const span: Record<string, string> = {
  netWorth: "md:col-span-7 md:row-span-2 min-h-[420px]",
  budgets: "md:col-span-5 min-h-[240px]",
  sync: "md:col-span-5 min-h-[240px]",
  risk: "md:col-span-4 min-h-[240px]",
  mcp: "md:col-span-4 min-h-[240px]",
  activity: "md:col-span-4 min-h-[240px]",
};

const tints: Record<string, string> = {
  cool: "radial-gradient(90% 80% at 8% 100%, color-mix(in srgb, var(--glow-cool) 55%, transparent), transparent 62%)",
  mint: "radial-gradient(90% 80% at 92% 8%, color-mix(in srgb, var(--positive) 22%, transparent), transparent 62%)",
  teal: "radial-gradient(90% 80% at 88% 100%, color-mix(in srgb, var(--glow-teal) 42%, transparent), transparent 62%)",
};

export function FeatureBento() {
  return (
    <section
      id={site.features.id}
      className="relative z-[1] scroll-mt-24"
    >
      <div className="mx-auto max-w-[1400px] px-5 py-16 sm:px-8 sm:py-28">
        <Reveal>
          <h2 className="max-w-[14ch] text-[clamp(2rem,4.6vw,3.4rem)] font-bold leading-[1.05] tracking-[-0.045em]">
            {site.features.headline}
          </h2>
        </Reveal>

        <div className="mt-14 grid grid-cols-1 gap-4 md:grid-cols-12 md:[perspective:1200px]">
          {site.features.cells.map((cell, i) => (
            <Reveal
              key={cell.key}
              delay={0.05 * i}
              className={span[cell.key] ?? "md:col-span-6"}
            >
              <FloatCard delay={0.12 * i} className="h-full">
                <article className="glass-frame relative h-full min-h-[220px] overflow-hidden">
                  {cell.pictured ? (
                    <>
                      <Image
                        src={site.shots[cell.shot]}
                        alt=""
                        fill
                        sizes="(min-width: 768px) 58vw, 100vw"
                        className="object-cover"
                        style={{ objectPosition: cell.objectPosition }}
                      />
                      <div
                        className="pointer-events-none absolute inset-0"
                        style={{
                          background:
                            "linear-gradient(180deg, transparent 42%, color-mix(in srgb, var(--canvas) 82%, transparent) 100%)",
                        }}
                      />
                    </>
                  ) : (
                    <div
                      className="pointer-events-none absolute inset-0"
                      style={{ background: tints[cell.tint] }}
                    />
                  )}
                  <div className="relative z-[1] flex h-full min-h-[220px] flex-col justify-end p-6 sm:p-7">
                    <h3 className="text-[1.45rem] font-semibold tracking-[-0.03em]">
                      {cell.title}
                    </h3>
                    <p className="mt-2 max-w-[36ch] text-[14.5px] leading-relaxed text-[var(--ink-soft)]">
                      {cell.body}
                    </p>
                  </div>
                </article>
              </FloatCard>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}
