"use client";

import { useState } from "react";
import { List, X } from "@phosphor-icons/react";
import { Logo } from "@/components/Logo";
import { site } from "@/content/site";

export function Nav() {
  const [open, setOpen] = useState(false);

  return (
    <>
      <header
        className="fixed top-3 left-1/2 z-[var(--z-nav)] w-[min(1120px,calc(100%-1.5rem))] -translate-x-1/2"
      >
        <nav
          className="glass-frame flex h-14 items-center justify-between px-3 sm:px-4"
          style={{ borderRadius: 18 }}
        >
          <Logo />
          <ul className="hidden items-center gap-7 md:flex">
            {site.nav.map((item) => (
              <li key={item.label}>
                <a
                  href={item.href}
                  {...("external" in item && item.external
                    ? { target: "_blank", rel: "noreferrer" }
                    : {})}
                  className="text-[13.5px] font-medium text-[var(--ink-soft)] transition-colors hover:text-[var(--ink)]"
                >
                  {item.label}
                </a>
              </li>
            ))}
          </ul>
          <button
            type="button"
            className="flex h-9 w-9 items-center justify-center rounded-[var(--radius-btn)] text-[var(--ink)] md:hidden"
            aria-expanded={open}
            aria-label={open ? "Close menu" : "Open menu"}
            onClick={() => setOpen((v) => !v)}
          >
            {open ? <X size={20} /> : <List size={20} />}
          </button>
        </nav>
      </header>

      {open && (
        <div
          className="fixed inset-0 z-[var(--z-overlay)] flex flex-col bg-[var(--canvas)]/92 px-6 pt-24 backdrop-blur-xl md:hidden"
        >
          <ul className="flex flex-col gap-6">
            {site.nav.map((item) => (
              <li key={item.label}>
                <a
                  href={item.href}
                  {...("external" in item && item.external
                    ? { target: "_blank", rel: "noreferrer" }
                    : {})}
                  className="text-3xl font-semibold tracking-tight"
                  onClick={() => setOpen(false)}
                >
                  {item.label}
                </a>
              </li>
            ))}
          </ul>
        </div>
      )}
    </>
  );
}
