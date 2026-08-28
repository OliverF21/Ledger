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
const HERO_END = 0.16;

function sceneIndex(progress: number) {
  if (progress <= HERO_END) return 0;
  const sceneP = (progress - HERO_END) / (1 - HERO_END);
  return Math.min(scenes.length - 1, Math.floor(sceneP * scenes.length));
}

export function ProductWalk({ release }: { release: LatestRelease }) {
  const reduce = useReducedMotion();
  const sectionRef = useRef<HTMLElement>(null);
  const stageRef = useRef<HTMLDivElement>(null);
  const laptopRef = useRef<HTMLDivElement>(null);
  const [active, setActive] = useState(0);
  const [cardsOn, setCardsOn] = useState(false);

  useEffect(() => {
    if (reduce || !sectionRef.current || !laptopRef.current) return;

    const ctx = gsap.context(() => {
      const section = sectionRef.current!;
      const laptop = laptopRef.current!;

      gsap.set(laptop, {
        rotateY: -18,
        rotateX: 10,
        xPercent: 6,
        yPercent: 4,
        scale: 1.04,
      });

      gsap.to(laptop, {
        rotateY: -11,
        rotateX: 6,
        xPercent: 6,
        yPercent: 2,
        scale: 1,
        ease: "none",
        scrollTrigger: {
          trigger: section,
          start: "top top",
          end: "bottom bottom",
          scrub: 1,
          onUpdate: (self) => {
            const next = sceneIndex(self.progress);
            setActive((i) => (i === next ? i : next));
            setCardsOn(self.progress > HERO_END * 0.55);
          },
        },
      });
    }, stageRef);

    return () => ctx.revert();
  }, [reduce]);

  const scrollVh = reduce ? undefined : 100 + scenes.length * 80;
  const showCards = reduce || cardsOn;

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
        <div className="mx-auto grid w-full max-w-[1400px] grid-cols-1 content-center items-center gap-8 px-5 pt-20 sm:px-8 lg:grid-cols-[minmax(0,0.86fr)_minmax(0,1.14fr)] lg:gap-10 lg:pt-10">
          <div className="relative z-10 max-w-[36rem] lg:min-h-[26rem]">
            <div
              className={
                reduce || !showCards
                  ? "relative"
                  : "pointer-events-none invisible absolute inset-0"
              }
            >
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

            <div
              className={
                reduce
                  ? "mt-10 flex flex-col gap-4"
                  : showCards
                    ? "relative"
                    : "pointer-events-none invisible absolute inset-0"
              }
              aria-live="polite"
            >
              {reduce
                ? scenes.map((scene) => (
                    <article key={scene.key} className="liquid-glass p-6 sm:p-7">
                      <SceneCopy scene={scene} />
                    </article>
                  ))
                : scenes.map((scene, i) => (
                    <div
                      key={scene.key}
                      className={`walk-card ${
                        showCards && i === active
                          ? "walk-card-active relative"
                          : "absolute inset-0"
                      }`}
                    >
                      <article className="liquid-glass walk-card-panel w-full p-7 sm:p-8">
                        <SceneCopy scene={scene} index={i} />
                      </article>
                    </div>
                  ))}
            </div>
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
                        transition: reduce ? "none" : "opacity 0.45s var(--ease-out)",
                      }}
                    >
                      <Image
                        src={site.shots[item.shot]}
                        alt={i === active ? item.title : ""}
                        fill
                        priority={i === 0}
                        sizes="(min-width: 1024px) 54vw, 92vw"
                        className="object-cover object-left-top"
                      />
                    </div>
                  ))
                )}
                <span className="macbook-glare" aria-hidden="true" />
              </div>
            </MacBook>
          </div>
        </div>
      </div>
    </section>
  );
}

function SceneCopy({
  scene,
  index,
}: {
  scene: (typeof scenes)[number];
  index?: number;
}) {
  return (
    <div className="relative z-[1]">
      {index !== undefined && (
        <p className="text-[13px] font-medium text-[var(--ink-muted)]">
          {String(index + 1).padStart(2, "0")} /{" "}
          {String(scenes.length).padStart(2, "0")}
        </p>
      )}
      <h2
        className={
          index !== undefined
            ? "mt-3 text-[clamp(1.8rem,3.4vw,2.55rem)] font-bold leading-[1.05] tracking-[-0.045em]"
            : "text-[1.45rem] font-bold tracking-[-0.04em]"
        }
      >
        {scene.title}
      </h2>
      <p className="mt-3 text-[15px] leading-relaxed text-[var(--ink-soft)] sm:text-[15.5px]">
        {scene.body}
      </p>
      <ul className="mt-5 space-y-2.5">
        {scene.points.map((point) => (
          <li
            key={point}
            className="flex gap-2.5 text-[13.5px] leading-snug text-[var(--ink)]"
          >
            <span
              className="mt-[0.45em] h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--positive)]"
              aria-hidden="true"
            />
            <span>{point}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
