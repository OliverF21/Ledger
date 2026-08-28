import Link from "next/link";
import { BookOpen } from "@phosphor-icons/react/dist/ssr";
import { site } from "@/content/site";

export function Logo({ compact = false }: { compact?: boolean }) {
  return (
    <Link href="/" className="flex items-center gap-2.5 min-w-0">
      <span
        className="flex h-[27px] w-[27px] shrink-0 items-center justify-center"
        style={{
          borderRadius: "var(--radius-logo)",
          background: "linear-gradient(150deg, var(--logo-top), var(--logo-bottom))",
          boxShadow:
            "0 6px 18px -6px var(--logo-shadow), inset 0 1px 0 rgba(255,255,255,0.95)",
        }}
      >
        <BookOpen size={14} weight="bold" color="var(--cta-ink)" />
      </span>
      {!compact && (
        <span className="text-[15.5px] font-bold tracking-tight">{site.name}</span>
      )}
    </Link>
  );
}
