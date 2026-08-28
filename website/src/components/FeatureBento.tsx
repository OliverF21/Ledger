import Image from "next/image";
import { Reveal } from "@/components/Reveal";
import { site } from "@/content/site";

const span: Record<string, string> = {
  netWorth: "md:col-span-7 md:row-span-2 min-h-[420px]",
  budgets: "md:col-span-5 min-h-[240px]",
  activity: "md:col-span-5 min-h-[240px]",
  investments: "md:col-span-6 min-h-[220px]",
  subscriptions: "md:col-span-6 min-h-[220px]",
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

        <div className="mt-14 grid grid-cols-1 gap-4 md:grid-cols-12">
          {site.features.cells.map((cell, i) => {
            const pictured =
              cell.key === "netWorth" ||
              cell.key === "budgets" ||
              cell.key === "activity";

            return (
              <Reveal
                key={cell.key}
                delay={0.05 * i}
                className={span[cell.key] ?? "md:col-span-6"}
              >
                <article className="glass-frame relative h-full min-h-[220px] overflow-hidden">
                  {pictured ? (
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
                      style={{
                        background:
                          cell.key === "investments"
                            ? "radial-gradient(90% 80% at 92% 8%, color-mix(in srgb, var(--positive) 22%, transparent), transparent 62%)"
                            : "radial-gradient(90% 80% at 8% 100%, color-mix(in srgb, var(--glow-cool) 55%, transparent), transparent 62%)",
                      }}
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
              </Reveal>
            );
          })}
        </div>
      </div>
    </section>
  );
}
