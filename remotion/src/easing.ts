/**
 * The same five easing curves the Python keyframe compiler emits.
 *
 * They are duplicated here rather than imported from Remotion's `Easing` because the
 * two backends must agree: a preset learned from a reference and rendered through
 * ffmpeg should look the same rendered through Remotion. Remotion's bezier easings are
 * nicer, but "nicer" that differs between backends is a bug, not a feature.
 *
 * Matches `forgecast/motion/keyframe.py::_EASINGS` exactly.
 */

import type { Easing } from "./types";

export const ease = (curve: Easing, progress: number): number => {
  const p = Math.max(0, Math.min(1, progress));
  switch (curve) {
    case "linear":
      return p;
    case "ease_in":
      return p * p;
    case "ease_out":
      return 1 - (1 - p) ** 2;
    case "ease_in_out":
      // Smoothstep, matching the Python side.
      return p * p * (3 - 2 * p);
    case "hold":
      return 0;
    default:
      return p;
  }
};

/** Interpolate between two values across a window, with easing. */
export const between = (
  time: number,
  from: number,
  to: number,
  fromValue: number,
  toValue: number,
  curve: Easing = "ease_out",
): number => {
  if (to <= from) return toValue;
  const progress = (time - from) / (to - from);
  if (progress <= 0) return fromValue;
  if (progress >= 1) return toValue;
  return fromValue + (toValue - fromValue) * ease(curve, progress);
};

/**
 * Fade in, hold, fade out — the alpha envelope every timed element shares.
 *
 * Clamps the rise and fall to the element's own window. An element whose fades do not
 * fit would otherwise still be rising when it disappears, which reads as a flicker.
 */
export const envelope = (
  local: number,
  duration: number,
  rise: number,
  fall: number,
): number => {
  const up = Math.min(rise, duration * 0.45);
  const down = Math.min(fall, duration * 0.35);
  if (local < 0 || local > duration) return 0;
  if (local < up) return ease("ease_out", local / Math.max(up, 1e-6));
  if (local > duration - down) {
    return 1 - ease("ease_in", (local - (duration - down)) / Math.max(down, 1e-6));
  }
  return 1;
};
