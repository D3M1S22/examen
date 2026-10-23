import data from "./voiceover-v2.json";

// Single source of truth for the v2 pitch timing.
// The same JSON feeds the placeholder audio script (scripts/make-vo-placeholders.mjs),
// the subtitles, the teleprompter overlay and docs/19_video_pitch_v2_script_live_demo.md.

export type VoKind = "vo" | "live";

export interface VoLine {
  id: string;
  scene: string;
  kind: VoKind;
  /** Seconds from the start of its scene. */
  start: number;
  /** Planned speaking time in seconds. */
  duration: number;
  words: number;
  text: string;
  /** Path inside public/. */
  file: string;
}

export interface SceneSlot {
  key: string;
  title: string;
  seconds: number;
  /** Absolute start in the master timeline, transitions included. */
  startsAt: number;
}

export const V2_FPS: number = data.fps;
export const V2_TRANSITION_FRAMES = Math.round(data.transitionSeconds * data.fps);
export const V2_SCENES: SceneSlot[] = data.scenes;
export const V2_LINES: VoLine[] = data.lines as VoLine[];

export const sceneFrames = (key: string): number => {
  const scene = V2_SCENES.find((s) => s.key === key);
  if (!scene) {
    throw new Error(`Unknown v2 scene: ${key}`);
  }
  return Math.round(scene.seconds * V2_FPS);
};

/** Absolute start frame of a scene inside the TransitionSeries. */
export const sceneStartFrame = (key: string): number => {
  let frame = 0;
  for (const scene of V2_SCENES) {
    if (scene.key === key) {
      return frame;
    }
    frame += Math.round(scene.seconds * V2_FPS) - V2_TRANSITION_FRAMES;
  }
  throw new Error(`Unknown v2 scene: ${key}`);
};

export const V2_TOTAL_FRAMES: number =
  V2_SCENES.reduce((sum, s) => sum + Math.round(s.seconds * V2_FPS), 0) -
  (V2_SCENES.length - 1) * V2_TRANSITION_FRAMES;

export interface PlacedLine extends VoLine {
  fromFrame: number;
  plannedFrames: number;
  /** Frames available before the next line (or the end of the video). */
  slotFrames: number;
}

export const PLACED_LINES: PlacedLine[] = V2_LINES.map((line) => ({
  ...line,
  fromFrame: sceneStartFrame(line.scene) + Math.round(line.start * V2_FPS),
  plannedFrames: Math.round(line.duration * V2_FPS),
  slotFrames: 0,
})).map((line, i, all) => {
  const nextStart = i + 1 < all.length ? all[i + 1].fromFrame : V2_TOTAL_FRAMES;
  return { ...line, slotFrames: Math.max(line.plannedFrames, nextStart - line.fromFrame) };
});

export const formatTime = (frames: number): string => {
  const total = frames / V2_FPS;
  const m = Math.floor(total / 60);
  const s = total - m * 60;
  return `${m}:${s.toFixed(1).padStart(4, "0")}`;
};
