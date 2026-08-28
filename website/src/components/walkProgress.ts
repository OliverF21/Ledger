import { site } from "@/content/site";

export const scenes = site.features.scenes;

/** Share of total scroll spent fading hero copy before the walk begins. */
export const INTRO_RATIO = 0.14;

/** Fraction of each scene segment spent holding before crossfade begins. */
export const SCENE_HOLD = 0.86;

export type WalkFrame = {
  progress: number;
  scene: number;
  blend: number;
  inIntro: boolean;
};

export function walkFrame(progress: number): WalkFrame {
  const clamped = Math.min(1, Math.max(0, progress));

  if (clamped <= INTRO_RATIO) {
    return { progress: clamped, scene: 0, blend: 0, inIntro: true };
  }

  const walk = (clamped - INTRO_RATIO) / (1 - INTRO_RATIO);
  const scaled = walk * scenes.length;
  const scene = Math.min(scenes.length - 1, Math.floor(scaled));
  const within = scaled - scene;
  const blend =
    scene >= scenes.length - 1
      ? 0
      : Math.min(1, Math.max(0, (within - SCENE_HOLD) / (1 - SCENE_HOLD)));

  return { progress: clamped, scene, blend, inIntro: false };
}

/** Scroll distance for the pinned product walk (viewport heights). */
export function walkScrollDistance() {
  return 140 + scenes.length * 200;
}
