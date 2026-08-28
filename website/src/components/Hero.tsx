import Image from "next/image";
import { DownloadButton } from "@/components/DownloadButton";
import { site } from "@/content/site";
import type { LatestRelease } from "@/release/github";

export function Hero({ release }: { release: LatestRelease }) {
  return (
    <section className="relative min-h-[100dvh]">
      <div className="absolute inset-0">
        <Image
          src={site.shots.hero}
          alt="Ledger Overview showing net worth, spending, and budgets"
          fill
          priority
          sizes="100vw"
          className="object-cover object-[center_18%] opacity-[0.92]"
        />
        <div
          className="absolute inset-0"
          style={{
            background:
              "linear-gradient(180deg, rgba(7,8,10,0.28) 0%, rgba(7,8,10,0.12) 38%, rgba(7,8,10,0.72) 72%, var(--canvas) 100%), linear-gradient(90deg, rgba(7,8,10,0.72) 0%, rgba(7,8,10,0.18) 42%, transparent 68%)",
          }}
        />
      </div>

      <div className="relative z-[var(--z-content)] mx-auto flex min-h-[100dvh] w-full max-w-[1400px] items-end px-5 pb-10 pt-24 sm:px-8 sm:pb-14 lg:pb-16">
        <div className="max-w-[34rem]">
          <h1 className="text-[2.15rem] font-bold leading-[1.05] tracking-[-0.045em] sm:text-5xl lg:text-[3.35rem]">
            {site.hero.headline}
          </h1>
          <p className="mt-4 max-w-[36ch] text-[15.5px] leading-relaxed text-[var(--ink-soft)] sm:text-base">
            {site.hero.subtext}
          </p>
          <div className="mt-7 flex flex-wrap items-center gap-3">
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
      </div>
    </section>
  );
}
