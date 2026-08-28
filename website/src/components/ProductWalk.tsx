"use client";

import { useEffect, useRef, useState } from "react";
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { useReducedMotion } from "motion/react";
import { DownloadButton } from "@/components/DownloadButton";
import { MacBook } from "@/components/MacBook";
import { site } from "@/content/site";
import type { LatestRelease } from "@/release/github";
import {
  INTRO_RATIO,
  scenes,
  walkFrame,
  walkScrollDistance,
} from "@/components/walkProgress";
import { useMobileWalk } from "@/components/useMobileWalk";

gsap.registerPlugin(ScrollTrigger);

export function ProductWalk({ release }: { release: LatestRelease }) {
  const reduce = useReducedMotion();
  const sectionRef = useRef<HTMLElement>(null);
  const stageRef = useRef<HTMLDivElement>(null);
  const copyRef = useRef<HTMLDivElement>(null);
  const captionRef = useRef<HTMLDivElement>(null);
  const captionTitleRef = useRef<HTMLHeadingElement>(null);
  const captionBodyRef = useRef<HTMLParagraphElement>(null);
  const mobileTitleRef = useRef<HTMLHeadingElement>(null);
  const mobileBodyRef = useRef<HTMLParagraphElement>(null);
  const progressRef = useRef(0);
  const [mobileScene, setMobileScene] = useState(0);
  const isMobile = useMobileWalk();
  const freeze = reduce === true;

  useEffect(() => {
    if (freeze || !sectionRef.current || !stageRef.current) return;

    const section = sectionRef.current;
    const stage = stageRef.current;
    const copy = copyRef.current;
    const caption = captionRef.current;

    const syncCaptions = (progress: number) => {
      progressRef.current = progress;
      const { scene, inIntro } = walkFrame(progress);
      const item = scenes[scene];

      if (captionTitleRef.current) captionTitleRef.current.textContent = item.title;
      if (captionBodyRef.current) captionBodyRef.current.textContent = item.body;
      if (mobileTitleRef.current) mobileTitleRef.current.textContent = item.title;
      if (mobileBodyRef.current) mobileBodyRef.current.textContent = item.body;

      if (!inIntro) setMobileScene(scene);
    };

    const ctx = gsap.context(() => {
      const distance = walkScrollDistance();
      const mm = gsap.matchMedia();

      mm.add("(min-width: 1024px)", () => {
        gsap.set(caption, { autoAlpha: 0, y: 22 });

        const tl = gsap.timeline({
          scrollTrigger: {
            trigger: section,
            start: "top top",
            end: () => `+=${distance}vh`,
            pin: stage,
            scrub: 1,
            anticipatePin: 1,
            invalidateOnRefresh: true,
            onUpdate: (self) => syncCaptions(self.progress),
          },
        });

        if (copy) {
          tl.to(
            copy,
            {
              autoAlpha: 0,
              y: -28,
              pointerEvents: "none",
              ease: "none",
              duration: INTRO_RATIO,
            },
            0,
          );
        }

        if (caption) {
          tl.to(
            caption,
            { autoAlpha: 1, y: 0, ease: "none", duration: INTRO_RATIO * 0.35 },
            INTRO_RATIO,
          );
        }

        tl.to({}, { duration: 1 - INTRO_RATIO }, INTRO_RATIO);
      });

      mm.add("(max-width: 1023px)", () => {
        gsap.set(caption, { autoAlpha: 1, y: 0 });
        if (copy) {
          gsap.set(copy, { autoAlpha: 0, height: 0, marginTop: 0, marginBottom: 0, overflow: "hidden" });
        }

        const tl = gsap.timeline({
          scrollTrigger: {
            trigger: section,
            start: "top top",
            end: () => `+=${Math.round(distance * 0.72)}vh`,
            pin: stage,
            scrub: 1,
            anticipatePin: 1,
            invalidateOnRefresh: true,
            onUpdate: (self) => syncCaptions(self.progress),
          },
        });

        if (copy) {
          tl.to(
            copy,
            {
              autoAlpha: 0,
              height: 0,
              marginTop: 0,
              marginBottom: 0,
              overflow: "hidden",
              pointerEvents: "none",
              ease: "none",
              duration: 0.01,
            },
            0,
          );
        }

        tl.to({}, { duration: 1 - INTRO_RATIO }, INTRO_RATIO);
      });

      syncCaptions(0);
      ScrollTrigger.refresh();
    }, section);

    return () => ctx.revert();
  }, [freeze]);

  const fallbackScene = scenes[mobileScene];

  return (
    <section
      ref={sectionRef}
      id={site.features.id}
      className="relative z-[1] scroll-mt-20"
    >
      <div
        ref={stageRef}
        className="walk-stage flex min-h-[100dvh] items-stretch overflow-x-clip"
      >
        <div className="mx-auto grid w-full max-w-[1400px] grid-cols-1 content-start items-center gap-5 px-4 pt-[calc(var(--nav-h)+0.35rem)] sm:px-8 lg:content-center lg:gap-6 lg:px-8 lg:pt-[calc(var(--nav-h)+0.5rem)] lg:grid-cols-[minmax(0,0.78fr)_minmax(0,1.22fr)]">
          <div className="walk-laptop relative z-20 order-1 w-full lg:order-2">
            <MacBook
              key={isMobile ? "mobile" : "desktop"}
              progressRef={progressRef}
              freeze={freeze}
              variant={isMobile ? "mobile" : "desktop"}
            />
          </div>

          <div className="relative z-10 order-2 hidden min-h-0 max-w-[34rem] lg:order-1 lg:block lg:min-h-[22rem]">
            <div ref={copyRef}>
              <h1 className="text-[clamp(1.85rem,8.5vw,4.35rem)] font-bold leading-[0.98] tracking-[-0.055em] lg:text-[clamp(2.4rem,6.2vw,4.35rem)]">
                {site.hero.lines.map((line) => (
                  <span key={line} className="block lg:inline lg:after:content-['_'] last:lg:after:content-none">
                    {line}
                  </span>
                ))}
              </h1>
              <p className="mt-3 max-w-[34ch] text-[14.5px] leading-relaxed text-[var(--ink-soft)] sm:text-base lg:mt-5">
                {site.hero.subtext}
              </p>
              <div className="mt-5 flex flex-wrap items-center gap-3 lg:mt-8">
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

            {freeze ? (
              <div className="mt-10 flex flex-col gap-8">
                {scenes.map((item) => (
                  <SceneCaption key={item.key} scene={item} />
                ))}
              </div>
            ) : (
              <div
                ref={captionRef}
                className="walk-caption pointer-events-none absolute inset-0 hidden lg:block"
                aria-live="polite"
              >
                <h2
                  ref={captionTitleRef}
                  className="text-[clamp(2rem,4.4vw,3.4rem)] font-bold leading-[1.02] tracking-[-0.05em]"
                >
                  {scenes[0].title}
                </h2>
                <p
                  ref={captionBodyRef}
                  className="mt-4 max-w-[34ch] text-[15.5px] leading-relaxed text-[var(--ink-soft)]"
                >
                  {scenes[0].body}
                </p>
              </div>
            )}
          </div>

          {!freeze && (
            <div className="relative z-10 order-2 max-w-[34rem] lg:order-3 lg:hidden">
              <h2
                ref={mobileTitleRef}
                className="text-[1.65rem] font-bold tracking-[-0.04em]"
              >
                {fallbackScene.title}
              </h2>
              <p
                ref={mobileBodyRef}
                className="mt-2 text-[14.5px] leading-relaxed text-[var(--ink-soft)]"
              >
                {fallbackScene.body}
              </p>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

function SceneCaption({ scene }: { scene: (typeof scenes)[number] }) {
  return (
    <>
      <h2 className="text-[clamp(2rem,4.4vw,3.4rem)] font-bold leading-[1.02] tracking-[-0.05em]">
        {scene.title}
      </h2>
      <p className="mt-4 max-w-[34ch] text-[15.5px] leading-relaxed text-[var(--ink-soft)]">
        {scene.body}
      </p>
    </>
  );
}
