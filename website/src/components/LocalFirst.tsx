import { Reveal } from "@/components/Reveal";
import { site } from "@/content/site";

export function LocalFirst() {
  return (
    <section className="relative z-[1] pt-8 lg:pt-28">
      <div className="mx-auto max-w-[1400px] px-5 py-20 sm:px-8 sm:py-32">
        <Reveal>
          <h2 className="max-w-[12ch] text-[clamp(2.6rem,7vw,5.4rem)] font-bold leading-[0.96] tracking-[-0.055em]">
            {site.localFirst.headline}
          </h2>
        </Reveal>
        <div className="mt-16 grid grid-cols-1 gap-12 md:grid-cols-3 md:gap-0">
          {site.localFirst.facts.map((fact, i) => (
            <Reveal
              key={fact.title}
              delay={0.08 * i}
              className="md:pr-10 md:pl-10 first:md:pl-0 md:border-l md:border-[var(--hairline-soft)] first:md:border-l-0"
            >
              <p className="text-[1.35rem] font-semibold tracking-[-0.03em]">
                {fact.title}
              </p>
              <p className="mt-3 max-w-[28ch] text-[15px] leading-relaxed text-[var(--ink-muted)]">
                {fact.body}
              </p>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}
