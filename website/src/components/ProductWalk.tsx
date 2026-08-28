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
const COPY_END = 0.16;

function sceneIndex(progress: number) {
  if (progress <= COPY_END) return 0;
  const sceneP = (progress - COPY_END) / (1 - COPY_END);
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
          xPercent: 8,
          yPercent: 4,
          scale: 1.03,
        });
        gsap.set(caption, { opacity: 0, y: 18 });

        const tl = gsap.timeline({
          scrollTrigger: {
            trigger: section,
            start: "top top",
            end: "bottom bottom",
            scrub: 1,
            onUpdate: (self) => {
              const next = sceneIndex(self.progress);
              setActive((i) => (i === next ? i : next));
            },
          },
        });

        tl.to(
          laptop,
          {
            xPercent: 6,
            yPercent: 1,
            scale: 1,
            ease: "none",
            duration: COPY_END,
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
              duration: COPY_END * 0.7,
            },
            0,
          );
        }
        if (caption) {
          tl.to(
            caption,
            { opacity: 1, y: 0, ease: "none", duration: COPY_END * 0.35 },
            COPY_END * 0.45,
          );
        }
        tl.to({}, { duration: 1 - COPY_END }, COPY_END);
      });

      mm.add("(max-width: 1023px)", () => {
        gsap.set(laptop, { xPercent: 0, yPercent: 0, scale: 1 });

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
        tl.to({}, { duration: 0.82 }, 0.18);
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

            {reduce ? (
              <div className="mt-10 flex flex-col gap-8">
                {scenes.map((item, i) => (
                  <SceneCaption key={item.key} scene={item} index={i} />
                ))}
              </div>
            ) : (
              <div
                ref={captionRef}
                className="walk-caption pointer-events-none absolute inset-0 hidden lg:block"
                aria-live="polite"
              >
                <SceneCaption scene={scene} index={active} />
              </div>
            )}
          </div>

          <div
            ref={laptopRef}
            className="walk-laptop relative z-20 w-full origin-[80%_40%]"
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
                        transition: reduce
                          ? "none"
                          : "opacity 0.45s var(--ease-out)",
                      }}
                    >
                      <Image
                        src={site.shots[item.shot]}
                        alt={i === active ? item.title : ""}
                        fill
                        priority={i === 0}
                        sizes="(min-width: 1024px) 48vw, 78vw"
                        className="object-cover object-left-top"
                      />
                    </div>
                  ))
                )}
              </div>
            </MacBook>
          </div>

          {!reduce && (
            <div className="relative z-10 max-w-[34rem] lg:hidden">
              <SceneCaption scene={scene} index={active} compact />
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

function SceneCaption({
  scene,
  index,
  compact,
}: {
  scene: (typeof scenes)[number];
  index: number;
  compact?: boolean;
}) {
  return (
    <>
      <p className="text-[13px] font-medium text-[var(--ink-muted)]">
        {String(index + 1).padStart(2, "0")} /{" "}
        {String(scenes.length).padStart(2, "0")}
      </p>
      <h2
        className={
          compact
            ? "mt-2 text-[1.65rem] font-bold tracking-[-0.04em]"
            : "mt-3 text-[clamp(2rem,4.4vw,3.4rem)] font-bold leading-[1.02] tracking-[-0.05em]"
        }
      >
        {scene.title}
      </h2>
      <p
        className={
          compact
            ? "mt-2 text-[14.5px] leading-relaxed text-[var(--ink-soft)]"
            : "mt-4 max-w-[34ch] text-[15.5px] leading-relaxed text-[var(--ink-soft)]"
        }
      >
        {scene.body}
      </p>
    </>
  );
}
