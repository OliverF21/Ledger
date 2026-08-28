import { DownloadButton } from "@/components/DownloadButton";
import { HeroProduct } from "@/components/HeroProduct";
import { site } from "@/content/site";
import type { LatestRelease } from "@/release/github";

export function Hero({ release }: { release: LatestRelease }) {
  return (
    <section className="relative min-h-[100dvh] overflow-visible">
      <div className="mx-auto grid min-h-[100dvh] max-w-[1400px] grid-cols-1 items-start px-5 pt-20 sm:px-8 lg:grid-cols-[minmax(0,0.92fr)_minmax(0,1.15fr)] lg:items-center lg:gap-6 lg:pt-16">
        <div className="relative z-10 max-w-[38rem] pb-8 lg:pb-24">
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

        <div className="relative z-20 w-[min(100%,52rem)] justify-self-end lg:w-[118%] lg:translate-x-[8%] lg:translate-y-[8%]">
          <HeroProduct />
        </div>
      </div>
    </section>
  );
}
