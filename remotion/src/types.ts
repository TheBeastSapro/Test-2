/**
 * The scene contract shared with Python.
 *
 * These types mirror `forgecast/render/scene_plan.py` field for field. The Python
 * side is the source of truth: it owns the motion presets that are *learned from
 * reference videos*, and this project is only a renderer for the plan they produce.
 * Keeping the contract dumb — plain JSON, no behaviour — is what lets the same plan
 * render through either backend and lets the ffmpeg one stay the default.
 *
 * Times are in seconds, not frames. Frames are a rendering detail; a preset measured
 * from a 24fps reference has to drive a 30fps render without rewriting its numbers.
 * Positions are fractions of the frame (0..1) for the same reason.
 */

export type Easing =
  | "linear"
  | "ease_in"
  | "ease_out"
  | "ease_in_out"
  | "hold";

export type EntryFamily = "pop" | "slide" | "rise" | "wipe";

export type CaptionStyle = "band" | "box" | "outline" | "plain";

export interface TextElement {
  kind: "text";
  start: number;
  duration: number;
  text: string;
  /** Cap height as a fraction of frame height. */
  sizeRatio: number;
  colour: string;
  x: number;
  y: number;
  entry: EntryFamily;
  entryDuration: number;
  exitDuration: number;
  easing: Easing;
  style: CaptionStyle;
  bandOpacity: number;
}

export interface BandElement {
  kind: "band";
  start: number;
  duration: number;
  colour: string;
  opacity: number;
  y: number;
  widthFraction: number;
  heightFraction: number;
}

export interface CardElement {
  kind: "card";
  start: number;
  duration: number;
  /** Filename relative to the public directory the CLI was pointed at. */
  src: string;
  /** Resting width as a fraction of frame width. */
  scale: number;
  x: number;
  y: number;
  /** End scale divided by start scale over the card's life. 1 = no move. */
  zoom: number;
  /** Radians the card settles through. */
  tilt: number;
  shadow: boolean;
  fadeIn: number;
  fadeOut: number;
  easing: Easing;
}

export type SceneElement = TextElement | BandElement | CardElement;

export interface Background {
  kind: "video" | "image" | "colour";
  /** Relative to the public directory. Absent for a colour background. */
  src?: string;
  colour: string;
}

export interface ScenePlan {
  width: number;
  height: number;
  fps: number;
  duration: number;
  background: Background;
  elements: SceneElement[];
  /** Recorded for provenance, so a render can be traced to the preset behind it. */
  presetName: string;
  fontFamily: string;
}

export const DEFAULT_PLAN: ScenePlan = {
  width: 1280,
  height: 720,
  fps: 30,
  duration: 5,
  background: { kind: "colour", colour: "#101418" },
  elements: [],
  presetName: "none",
  fontFamily:
    'system-ui, -apple-system, "Segoe UI", Roboto, "DejaVu Sans", sans-serif',
};
