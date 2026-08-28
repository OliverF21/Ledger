import { site } from "@/content/site";

export const scenes = site.features.scenes;

/** Scroll budget (vh) for the hero intro before scene 1 locks in. */
export const INTRO_SCROLL_VH = 100;

/** Scroll budget (vh) spent holding each screenshot — one section per scene. */
export const SCENE_SCROLL_VH = 260;

/** Scroll budget (vh) for the crossfade into the next screenshot. */
export const SCENE_BLEND_VH = 45;

export type WalkFrame = {
  progress: number;
  scene: number;
  blend: number;
  inIntro: boolean;
};

function smoothstep(t: number) {
  const x = Math.min(1, Math.max(0, t));
  return x * x * (3 - 2 * t);
}

/** Scroll distance for the pinned product walk (viewport heights). */
export function walkScrollDistance() {
  const transitions = Math.max(0, scenes.length - 1);
  return INTRO_SCROLL_VH + scenes.length * SCENE_SCROLL_VH + transitions * SCENE_BLEND_VH;
}

/** Share of total scroll spent in the hero intro (for GSAP timeline sync). */
export function introRatio() {
  return INTRO_SCROLL_VH / walkScrollDistance();
}

export function walkFrame(progress: number): WalkFrame {
  const clamped = Math.min(1, Math.max(0, progress));
  const total = walkScrollDistance();
  const pos = clamped * total;

  if (pos <= INTRO_SCROLL_VH) {
    return { progress: clamped, scene: 0, blend: 0, inIntro: true };
  }

  let cursor = INTRO_SCROLL_VH;

  for (let i = 0; i < scenes.length; i += 1) {
    const holdEnd = cursor + SCENE_SCROLL_VH;

    if (i === scenes.length - 1 || pos < holdEnd) {
      return { progress: clamped, scene: i, blend: 0, inIntro: false };
    }

    cursor = holdEnd;
    const blendEnd = cursor + SCENE_BLEND_VH;

    if (pos < blendEnd) {
      const blend = smoothstep((pos - cursor) / SCENE_BLEND_VH);
      return { progress: clamped, scene: i, blend, inIntro: false };
    }

    cursor = blendEnd;
  }

  return { progress: clamped, scene: scenes.length - 1, blend: 0, inIntro: false };
}
