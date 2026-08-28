import { DownloadButton } from "@/components/DownloadButton";
import { Logo } from "@/components/Logo";
import { Reveal } from "@/components/Reveal";
import { site } from "@/content/site";
import type { LatestRelease } from "@/release/github";

export function CloseFooter({ release }: { release: LatestRelease }) {
  return (
    <footer className="relative z-[1]">
      <div className="mx-auto max-w-[1400px] px-5 pb-10 pt-10 sm:px-8 sm:pt-8">
        <Reveal>
          <div className="border-t border-[var(--hairline-soft)] pb-24 pt-16">
            <h2 className="text-[clamp(3.4rem,12vw,9rem)] font-bold leading-[0.88] tracking-[-0.07em]">
              {site.close.headline}
            </h2>
            <div className="mt-10">
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
