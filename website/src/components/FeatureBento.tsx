import Image from "next/image";
import { Reveal } from "@/components/Reveal";
import { site } from "@/content/site";

export function FeatureBento() {
  const cells = site.features.cells;

  return (
    <section
      id={site.features.id}
      className="relative z-[var(--z-content)] scroll-mt-24"
    >
      <div className="mx-auto max-w-[1400px] px-5 py-16 sm:px-8 sm:py-24">
        <Reveal>
          <h2 className="max-w-[18ch] text-3xl font-bold leading-[1.1] tracking-[-0.04em] sm:text-4xl lg:text-[2.6rem]">
            {site.features.headline}
          </h2>
        </Reveal>

        <div className="mt-12 grid grid-cols-1 gap-4 md:grid-cols-6 md:grid-rows-[minmax(280px,auto)_minmax(220px,auto)_minmax(200px,auto)]">
          {cells.map((cell, i) => {
            const span =
              cell.key === "netWorth"
                ? "md:col-span-4 md:row-span-2 min-h-[280px]"
                : cell.key === "budgets"
                  ? "md:col-span-2 min-h-[220px]"
                  : cell.key === "subscriptions"
                    ? "md:col-span-2 min-h-[220px]"
                    : "md:col-span-3 min-h-[200px]";

            return (
              <Reveal key={cell.key} delay={0.05 * i} className={span}>
                <article className="glass-frame relative h-full min-h-[220px] overflow-hidden p-5 sm:p-6">
                  {cell.key === "netWorth" ||
                  cell.key === "budgets" ||
                  cell.key === "activity" ? (
                    <>
                      <Image
                        src={site.shots[cell.shot]}
                        alt=""
                        fill
                        sizes="(min-width: 768px) 50vw, 100vw"
                        className="object-cover opacity-45"
                        style={{ objectPosition: cell.objectPosition }}
                      />
                      <div
                        className="pointer-events-none absolute inset-0"
                        style={{
                          background:
                            "linear-gradient(180deg, transparent 20%, color-mix(in srgb, var(--canvas) 78%, transparent) 100%)",
                        }}
                      />
                    </>
                  ) : (
                    <div
                      className="pointer-events-none absolute inset-0"
                      style={{
                        background:
                          cell.key === "investments"
                            ? "radial-gradient(80% 70% at 80% 20%, rgba(116,216,168,0.18), transparent 70%)"
                            : "radial-gradient(80% 70% at 20% 80%, rgba(149,200,255,0.16), transparent 70%)",
                      }}
                    />
                  )}
                  <div className="relative z-[1] flex h-full flex-col justify-end">
                    <h3 className="text-xl font-semibold tracking-tight">
                      {cell.title}
                    </h3>
                    <p className="mt-2 max-w-[42ch] text-[14.5px] leading-relaxed text-[var(--ink-soft)]">
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
