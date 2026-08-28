import { Reveal } from "@/components/Reveal";
import { site } from "@/content/site";

export function LocalFirst() {
  return (
    <section className="relative z-[var(--z-content)] border-y border-[var(--hairline-soft)]">
      <div className="mx-auto max-w-[1400px] px-5 py-20 sm:px-8 sm:py-28">
        <Reveal>
          <h2 className="max-w-[16ch] text-4xl font-bold leading-[1.08] tracking-[-0.04em] sm:text-5xl lg:text-[3.4rem]">
            {site.localFirst.headline}
          </h2>
        </Reveal>
        <div className="mt-14 grid grid-cols-1 gap-10 md:grid-cols-3 md:gap-0">
          {site.localFirst.facts.map((fact, i) => (
            <Reveal
              key={fact.title}
              delay={0.08 * i}
              className="md:border-l md:border-[var(--hairline-soft)] md:px-8 first:md:border-l-0 first:md:pl-0"
            >
              <p className="text-[17px] font-semibold tracking-tight">{fact.title}</p>
              <p className="mt-2 max-w-[34ch] text-[14.5px] leading-relaxed text-[var(--ink-muted)]">
                {fact.body}
              </p>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}
