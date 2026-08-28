import { DownloadButton } from "@/components/DownloadButton";
import { Reveal } from "@/components/Reveal";
import { site } from "@/content/site";
import type { LatestRelease } from "@/release/github";

export function DownloadHonest({ release }: { release: LatestRelease }) {
  const d = site.download;

  return (
    <section
      id={d.id}
      className="relative z-[var(--z-content)] scroll-mt-24"
    >
      <div className="mx-auto max-w-[1400px] px-5 py-16 sm:px-8 sm:py-24">
        <Reveal>
          <div className="glass-frame grid grid-cols-1 gap-12 p-7 sm:p-10 lg:grid-cols-[1.05fr_1fr] lg:gap-16 lg:p-12">
            <div>
              <h2 className="text-4xl font-bold tracking-[-0.04em] sm:text-5xl">
                {d.headline}
              </h2>
              <p className="mt-4 max-w-[42ch] text-[15.5px] leading-relaxed text-[var(--ink-soft)]">
                {d.body}
              </p>
              <div className="mt-8 flex flex-wrap items-center gap-3">
                <DownloadButton release={release} />
                <a href={release.htmlUrl} className="btn-ghost">
                  {d.otherPlatformsLabel}
                </a>
              </div>
              <div className="mt-4 flex flex-wrap gap-3 text-[13px] text-[var(--ink-muted)]">
                <span>macOS Apple Silicon</span>
                <span aria-hidden="true">/</span>
                <span>Windows x64</span>
                <span aria-hidden="true">/</span>
                <a
                  href={site.sourceInstall}
                  className="text-[var(--link)] hover:text-[var(--link-hover)]"
                >
                  {d.linuxNote.title} from source
                </a>
              </div>
            </div>

            <div className="flex flex-col justify-center gap-8 lg:border-l lg:border-[var(--hairline-soft)] lg:pl-12">
              <div>
                <p className="text-[15px] font-semibold">{d.macNote.title}</p>
                <p className="mt-2 text-[14px] leading-relaxed text-[var(--ink-soft)]">
                  {d.macNote.body}
                </p>
                <pre className="mt-3 overflow-x-auto rounded-[var(--radius-btn)] bg-black/35 px-3 py-2.5 text-[12.5px] text-[var(--positive-text)]">
                  <code>{d.macNote.code}</code>
                </pre>
              </div>
              <div>
                <p className="text-[15px] font-semibold">{d.winNote.title}</p>
                <p className="mt-2 text-[14px] leading-relaxed text-[var(--ink-soft)]">
                  {d.winNote.body}
                </p>
              </div>
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  );
}
