"use client";

import { useEffect, useRef, useState } from "react";
import Image from "next/image";
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { useReducedMotion } from "motion/react";
import { DownloadButton } from "@/components/DownloadButton";
import { MacBook } from "@/components/MacBook";
import { site } from "@/content/site";
import type { LatestRelease } from "@/release/github";

gsap.registerPlugin(ScrollTrigger);

const scenes = site.features.scenes;
const ROTATE_END = 0.28;

function sceneIndex(progress: number, rotateEnd: number) {
  if (progress <= rotateEnd) return 0;
  const sceneP = (progress - rotateEnd) / (1 - rotateEnd);
  return Math.min(scenes.length - 1, Math.floor(sceneP * scenes.length));
}

export function ProductWalk({ release }: { release: LatestRelease }) {
  const reduce = useReducedMotion();
  const sectionRef = useRef<HTMLElement>(null);
  const stageRef = useRef<HTMLDivElement>(null);
  const copyRef = useRef<HTMLDivElement>(null);
  const captionRef = useRef<HTMLDivElement>(null);
  const laptopRef = useRef<HTMLDivElement>(null);
  const [active, setActive] = useState(0);

  useEffect(() => {
    if (reduce || !sectionRef.current || !laptopRef.current) return;

    const ctx = gsap.context(() => {
      const section = sectionRef.current!;
      const laptop = laptopRef.current!;
      const copy = copyRef.current;
      const caption = captionRef.current;
      const mm = gsap.matchMedia();

      mm.add("(min-width: 1024px)", () => {
        gsap.set(laptop, {
          rotateY: -22,
          rotateX: 14,
          xPercent: 14,
          yPercent: 8,
          scale: 1.12,
        });
        gsap.set(caption, { opacity: 0, y: 18 });

        const tl = gsap.timeline({
          scrollTrigger: {
            trigger: section,
            start: "top top",
            end: "bottom bottom",
            scrub: 1,
            onUpdate: (self) => {
              const next = sceneIndex(self.progress, ROTATE_END);
              setActive((i) => (i === next ? i : next));
            },
          },
        });

        tl.to(
          laptop,
          {
            rotateY: 0,
            rotateX: 7,
            xPercent: 0,
            yPercent: 6,
            scale: 1,
            ease: "none",
            duration: ROTATE_END,
          },
          0,
        );
        if (copy) {
          tl.to(
            copy,
            {
              opacity: 0,
              y: -36,
              pointerEvents: "none",
              ease: "none",
              duration: ROTATE_END * 0.85,
            },
            0,
          );
        }
        if (caption) {
          tl.to(
            caption,
            { opacity: 1, y: 0, ease: "none", duration: ROTATE_END * 0.5 },
            ROTATE_END * 0.55,
          );
        }
      });

      mm.add("(max-width: 1023px)", () => {
        gsap.set(laptop, {
          rotateY: 0,
          rotateX: 4,
          xPercent: 0,
          yPercent: 0,
          scale: 1,
        });

        const tl = gsap.timeline({
          scrollTrigger: {
            trigger: section,
            start: "top top",
            end: "bottom bottom",
            scrub: 1,
            onUpdate: (self) => {
              const next = Math.min(
                scenes.length - 1,
                Math.floor(self.progress * scenes.length),
              );
              setActive((i) => (i === next ? i : next));
            },
          },
        });

        if (copy) {
          tl.to(
            copy,
            {
              opacity: 0,
              height: 0,
              margin: 0,
              overflow: "hidden",
              pointerEvents: "none",
              ease: "none",
              duration: 0.18,
            },
            0,
          );
        }
      });
    }, stageRef);

    return () => ctx.revert();
  }, [reduce]);

  const scene = scenes[active];
  const scrollVh = reduce ? undefined : 100 + scenes.length * 85;

  return (
    <section
      ref={sectionRef}
      id={site.features.id}
      className="relative z-[1]"
      style={scrollVh ? { height: `${scrollVh}vh` } : undefined}
    >
      <div
        ref={stageRef}
        className="sticky top-0 flex min-h-[100dvh] items-stretch overflow-x-clip"
      >
        <div className="mx-auto grid w-full max-w-[1400px] grid-cols-1 content-center items-center gap-8 px-5 pt-20 sm:px-8 lg:grid-cols-[minmax(0,0.78fr)_minmax(0,1.22fr)] lg:gap-6 lg:pt-10">
          <div className="relative z-10 min-h-[11rem] max-w-[34rem] lg:min-h-[22rem]">
            <div ref={copyRef}>
              <h1 className="text-[clamp(2.4rem,6.2vw,4.35rem)] font-bold leading-[0.98] tracking-[-0.055em]">
                {site.hero.lines.map((line) => (
                  <span key={line} className="block">
                    {line}
                  </span>
                ))}
              </h1>
              <p className="mt-5 max-w-[34ch] text-[15.5px] leading-relaxed text-[var(--ink-soft)] sm:text-base">
                {site.hero.subtext}
              </p>
              <div className="mt-8 flex flex-wrap items-center gap-3">
                <DownloadButton release={release} />
                <a
                  href={site.github}
                  target="_blank"
                  rel="noreferrer"
                  className="btn-ghost"
                >
                  {site.hero.githubLabel}
                </a>
              </div>
            </div>

            {!reduce && (
              <div
                ref={captionRef}
                className="pointer-events-none absolute inset-0 hidden lg:block"
                aria-live="polite"
              >
                <p className="text-[13px] font-medium text-[var(--ink-muted)]">
                  {String(active + 1).padStart(2, "0")} /{" "}
                  {String(scenes.length).padStart(2, "0")}
                </p>
                <h2 className="mt-3 text-[clamp(2rem,4.4vw,3.4rem)] font-bold leading-[1.02] tracking-[-0.05em]">
                  {scene.title}
                </h2>
                <p className="mt-4 max-w-[34ch] text-[15.5px] leading-relaxed text-[var(--ink-soft)]">
                  {scene.body}
                </p>
              </div>
            )}
          </div>

          <div
            ref={laptopRef}
            className="walk-laptop relative z-20 w-full origin-center lg:origin-[70%_40%]"
          >
            <MacBook>
              <div className="relative h-full w-full bg-[var(--canvas)]">
                {site.features.video ? (
                  <video
                    className="absolute inset-0 h-full w-full object-cover"
                    muted
                    playsInline
                    preload="metadata"
                    poster={site.shots.overview}
                    src={site.features.video}
                  />
                ) : (
                  scenes.map((item, i) => (
                    <div
                      key={item.key}
                      className="absolute inset-0"
                      style={{
                        opacity: i === active ? 1 : 0,
                        transition: reduce ? "none" : "opacity 0.45s var(--ease-out)",
                      }}
                    >
                      <Image
                        src={site.shots[item.shot]}
                        alt={i === active ? item.title : ""}
                        fill
                        priority={i === 0}
                        sizes="(min-width: 1024px) 56vw, 92vw"
                        className="object-cover object-left-top"
                      />
                    </div>
                  ))
                )}
                <span className="macbook-glare" aria-hidden="true" />
              </div>
            </MacBook>
          </div>

          {!reduce && (
            <div className="relative z-10 max-w-[34rem] lg:hidden">
              <p className="text-[13px] font-medium text-[var(--ink-muted)]">
                {String(active + 1).padStart(2, "0")} /{" "}
                {String(scenes.length).padStart(2, "0")}
              </p>
              <h2 className="mt-2 text-[1.65rem] font-bold tracking-[-0.04em]">
                {scene.title}
              </h2>
              <p className="mt-2 text-[14.5px] leading-relaxed text-[var(--ink-soft)]">
                {scene.body}
              </p>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
