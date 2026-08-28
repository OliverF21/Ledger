"use client";

import { useEffect } from "react";
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

gsap.registerPlugin(ScrollTrigger);

/** Re-measure pinned sections after hydration, fonts, and resize. */
export function ScrollRefresh() {
  useEffect(() => {
    const refresh = () => ScrollTrigger.refresh();

    refresh();
    window.addEventListener("load", refresh);
    window.addEventListener("resize", refresh);

    const id = window.setTimeout(refresh, 120);

    return () => {
      window.removeEventListener("load", refresh);
      window.removeEventListener("resize", refresh);
      window.clearTimeout(id);
    };
  }, []);

  return null;
}
