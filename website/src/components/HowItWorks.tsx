"use client";

import { useEffect, useRef } from "react";
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { useReducedMotion } from "motion/react";
import { Atmosphere } from "@/components/Atmosphere";
import { site } from "@/content/site";

gsap.registerPlugin(ScrollTrigger);

const tints = [
  "radial-gradient(900px 500px at 80% 20%, color-mix(in srgb, var(--glow-cool) 40%, transparent), transparent 70%)",
  "radial-gradient(900px 500px at 20% 80%, color-mix(in srgb, var(--positive) 18%, transparent), transparent 70%)",
  "radial-gradient(900px 500px at 90% 80%, color-mix(in srgb, var(--glow-blue) 28%, transparent), transparent 70%)",
];

export function HowItWorks() {
  const ref = useRef<HTMLDivElement>(null);
  const reduce = useReducedMotion();

  useEffect(() => {
    if (reduce || !ref.current) return;

    const ctx = gsap.context(() => {
      const mm = gsap.matchMedia();
      mm.add("(min-width: 768px)", () => {
        const cards = gsap.utils.toArray<HTMLElement>(".stack-card");
        cards.forEach((card, i) => {
          if (i === cards.length - 1) return;
          ScrollTrigger.create({
            trigger: card,
            start: "top top",
            endTrigger: cards[cards.length - 1],
            end: "top top",
            pin: true,
            pinSpacing: false,
          });
          gsap.to(card, {
            scale: 0.92,
            opacity: 0.55,
            ease: "none",
            scrollTrigger: {
              trigger: cards[i + 1],
              start: "top bottom",
              end: "top top",
              scrub: true,
            },
          });
        });
      });
    }, ref);

    return () => ctx.revert();
  }, [reduce]);

  return (
    <section className="relative z-[1]">
      <div ref={ref} className="relative">
        {site.how.steps.map((step, i) => (
          <div
            key={step.title}
            className="stack-card relative sticky top-0 flex min-h-[100dvh] items-end overflow-hidden md:items-center"
          >
            <Atmosphere mode="fill" />
            <div
              className="pointer-events-none absolute inset-0"
              style={{ background: tints[i] }}
            />
            <div className="relative mx-auto flex min-h-[100dvh] w-full max-w-[1400px] flex-col justify-end px-5 py-16 sm:px-8 md:justify-center md:py-24">
              {i === 0 && (
                <p className="mb-10 max-w-[16ch] text-[clamp(1.6rem,3vw,2.2rem)] font-semibold tracking-[-0.04em] text-[var(--ink-muted)]">
                  {site.how.headline}
                </p>
              )}
              <h2 className="max-w-[12ch] text-[clamp(3.2rem,10vw,8.5rem)] font-bold leading-[0.9] tracking-[-0.06em]">
                {step.title}
              </h2>
              <p className="mt-6 max-w-[36ch] text-[17px] leading-relaxed text-[var(--ink-soft)] md:text-[19px]">
                {step.body}
              </p>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
