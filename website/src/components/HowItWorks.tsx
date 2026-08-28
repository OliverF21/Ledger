import { Reveal } from "@/components/Reveal";
import { site } from "@/content/site";

export function HowItWorks() {
  return (
    <section className="relative z-[var(--z-content)]">
      <div className="mx-auto max-w-[1400px] px-5 py-16 sm:px-8 sm:py-28">
        <Reveal>
          <h2 className="max-w-[16ch] text-3xl font-bold leading-[1.1] tracking-[-0.04em] sm:text-4xl">
            {site.how.headline}
          </h2>
        </Reveal>
        <ol className="mt-14 flex flex-col">
          {site.how.steps.map((step, i) => (
            <Reveal key={step.title} delay={0.06 * i}>
              <li className="grid grid-cols-1 gap-3 border-t border-[var(--hairline-soft)] py-10 md:grid-cols-[minmax(0,0.42fr)_minmax(0,1fr)] md:items-baseline md:gap-10">
                <p className="text-4xl font-bold tracking-[-0.04em] sm:text-5xl">
                  {step.title}
                </p>
                <p className="max-w-[48ch] text-[16px] leading-relaxed text-[var(--ink-soft)]">
                  {step.body}
                </p>
              </li>
            </Reveal>
          ))}
        </ol>
      </div>
    </section>
  );
}
