import { DownloadButton } from "@/components/DownloadButton";
import { Logo } from "@/components/Logo";
import { Reveal } from "@/components/Reveal";
import { site } from "@/content/site";
import type { LatestRelease } from "@/release/github";

export function CloseFooter({ release }: { release: LatestRelease }) {
  return (
    <footer className="relative z-[var(--z-content)]">
      <div className="mx-auto max-w-[1400px] px-5 pb-10 pt-10 sm:px-8 sm:pt-16">
        <Reveal>
          <div className="pb-20">
            <h2 className="text-5xl font-bold tracking-[-0.05em] sm:text-6xl">
              {site.close.headline}
            </h2>
            <div className="mt-8">
              <DownloadButton release={release} />
            </div>
          </div>
        </Reveal>
        <div className="flex flex-col gap-5 border-t border-[var(--hairline-soft)] py-6 sm:flex-row sm:items-center sm:justify-between">
          <Logo />
          <ul className="flex flex-wrap items-center gap-x-6 gap-y-2 text-[13px] text-[var(--ink-muted)]">
            <li>{site.footer.license}</li>
            {site.footer.links.map((link) => (
              <li key={link.label}>
                <a
                  href={link.href}
                  target="_blank"
                  rel="noreferrer"
                  className="hover:text-[var(--ink)]"
                >
                  {link.label}
                </a>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </footer>
  );
}
