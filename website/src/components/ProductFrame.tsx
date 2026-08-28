import Image from "next/image";
import { Reveal } from "@/components/Reveal";
import { site } from "@/content/site";

export function ProductFrame() {
  return (
    <section className="relative z-[var(--z-content)]">
      <div className="mx-auto max-w-[1400px] px-5 py-16 sm:px-8 sm:py-24">
        <Reveal>
          <div className="glass-frame p-1.5 sm:p-2">
            <div
              className="relative overflow-hidden"
              style={{ borderRadius: "calc(var(--radius-frame) - 6px)" }}
            >
              <Image
                src={site.shots.product}
                alt={site.product.caption}
                width={1600}
                height={1000}
                sizes="(min-width: 1400px) 1360px, 100vw"
                className="h-auto w-full"
              />
            </div>
          </div>
          <p className="mt-5 text-[13.5px] text-[var(--ink-muted)]">
            {site.product.caption}
          </p>
        </Reveal>
      </div>
    </section>
  );
}
