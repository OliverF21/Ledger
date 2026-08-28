import { DownloadButton } from "@/components/DownloadButton";
import { Reveal } from "@/components/Reveal";
import { site } from "@/content/site";
import type { LatestRelease } from "@/release/github";

export function DownloadHonest({ release }: { release: LatestRelease }) {
  const d = site.download;

  return (
    <section id={d.id} className="relative z-[1] scroll-mt-24">
      <div className="mx-auto max-w-[1400px] px-5 py-24 sm:px-8 sm:py-36">
        <Reveal>
          <h2 className="max-w-[12ch] text-[clamp(2.8rem,7.5vw,6rem)] font-bold leading-[0.94] tracking-[-0.055em]">
            {d.headline}
          </h2>
          <p className="mt-6 max-w-[46ch] text-[16px] leading-relaxed text-[var(--ink-soft)]">
            {d.body}
          </p>
          <div className="mt-10 flex flex-wrap items-center gap-3">
            <DownloadButton release={release} />
            <a href={release.htmlUrl} className="btn-ghost">
              {d.otherPlatformsLabel}
            </a>
          </div>
          <p className="mt-5 text-[13px] text-[var(--ink-muted)]">
            macOS Apple Silicon{" "}
            <span aria-hidden="true" className="mx-2 text-[var(--hairline)]">
              /
            </span>{" "}
            Windows x64{" "}
            <span aria-hidden="true" className="mx-2 text-[var(--hairline)]">
              /
            </span>{" "}
            <a
              href={site.sourceInstall}
              className="text-[var(--link)] hover:text-[var(--link-hover)]"
            >
              {d.linuxNote.title} from source
            </a>
          </p>
        </Reveal>

        <div className="mt-20 grid grid-cols-1 gap-12 border-t border-[var(--hairline-soft)] pt-12 md:grid-cols-2 md:gap-16">
          <Reveal>
            <p className="text-[1.15rem] font-semibold tracking-tight">
              {d.macNote.title}
            </p>
            <p className="mt-3 max-w-[46ch] text-[15px] leading-relaxed text-[var(--ink-soft)]">
              {d.macNote.body}
            </p>
            <pre className="mt-4 overflow-x-auto rounded-[var(--radius-btn)] border border-[var(--hairline-soft)] bg-black/25 px-4 py-3 text-[13px] text-[var(--positive-text)]">
              <code>{d.macNote.code}</code>
            </pre>
          </Reveal>
          <Reveal delay={0.08}>
            <p className="text-[1.15rem] font-semibold tracking-tight">
              {d.winNote.title}
            </p>
            <p className="mt-3 max-w-[46ch] text-[15px] leading-relaxed text-[var(--ink-soft)]">
              {d.winNote.body}
            </p>
          </Reveal>
        </div>
      </div>
    </section>
  );
}
