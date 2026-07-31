/**
 * The element vocabulary, matching `forgecast/motion/compose.py`.
 *
 * Text, Band and ImageCard exist in both backends and take the same fields. What
 * differs is everything the browser gives away for free and ffmpeg cannot do at all:
 * text wraps on word boundaries with real font metrics, shadows are actually blurred
 * rather than a displaced dark copy, and a card can be scaled and rotated in one
 * transform instead of a chain of filters that each fix the frame size.
 */

import React from "react";
import { AbsoluteFill, Img, staticFile, useCurrentFrame, useVideoConfig } from "remotion";

import { between, envelope } from "./easing";
import type { BandElement, CardElement, TextElement } from "./types";

/** Horizontal travel for an entry, as a fraction of the frame. */
const TRAVEL: Record<string, number> = { slide: 0.16, wipe: 0.3, pop: 0, rise: 0 };

export const Text: React.FC<{ element: TextElement; fontFamily: string }> = ({
  element,
  fontFamily,
}) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const local = frame / fps - element.start;
  if (local < 0 || local > element.duration) return null;

  const opacity = envelope(
    local,
    element.duration,
    element.entryDuration,
    element.exitDuration,
  );

  // Entry moves. `pop` scales rather than travels, which is why it is the family a
  // fast preset picks: it reads as complete in a fraction of the time a slide needs.
  const travel = TRAVEL[element.entry] ?? 0;
  const x =
    element.entry === "slide" || element.entry === "wipe"
      ? between(local, 0, element.entryDuration, element.x - travel, element.x, element.easing)
      : element.x;
  const y =
    element.entry === "rise"
      ? between(local, 0, element.entryDuration, element.y + 0.06, element.y, element.easing)
      : element.y;
  const scale =
    element.entry === "pop"
      ? between(local, 0, element.entryDuration, 0.82, 1, element.easing)
      : 1;

  const fontSize = Math.max(14, element.sizeRatio * height);
  const outlined = element.style === "outline";

  return (
    <AbsoluteFill>
      {element.style === "band" ? (
        <div
          style={{
            position: "absolute",
            left: 0,
            top: (y - 0.07) * height,
            width,
            height: height * 0.15,
            background: `rgba(0,0,0,${element.bandOpacity})`,
            opacity,
          }}
        />
      ) : null}
      <div
        style={{
          position: "absolute",
          left: 0,
          top: y * height,
          width,
          display: "flex",
          justifyContent: "center",
          opacity,
          transform: `translateX(${(x - 0.5) * width}px) scale(${scale})`,
        }}
      >
        <span
          style={{
            fontFamily,
            fontSize,
            fontWeight: 700,
            lineHeight: 1.15,
            color: element.colour,
            textAlign: "center",
            // The reason a browser compositor is worth the dependency: drawtext has
            // no concept of a line break, so long copy either overflows the frame or
            // has to be split by hand in Python.
            maxWidth: width * 0.86,
            padding: element.style === "box" ? `${fontSize * 0.3}px ${fontSize * 0.5}px` : 0,
            background:
              element.style === "box" ? `rgba(0,0,0,${element.bandOpacity})` : "transparent",
            borderRadius: element.style === "box" ? fontSize * 0.18 : 0,
            WebkitTextStroke: outlined ? `${Math.max(2, fontSize * 0.045)}px #000` : undefined,
            paintOrder: "stroke fill",
            textShadow: outlined ? undefined : "0 2px 12px rgba(0,0,0,0.55)",
          }}
        >
          {element.text}
        </span>
      </div>
    </AbsoluteFill>
  );
};

export const Band: React.FC<{ element: BandElement }> = ({ element }) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const local = frame / fps - element.start;
  if (local < 0 || local > element.duration) return null;

  return (
    <div
      style={{
        position: "absolute",
        left: 0,
        top: element.y * height,
        width: width * element.widthFraction,
        height: height * element.heightFraction,
        background: element.colour,
        opacity: element.opacity * envelope(local, element.duration, 0.2, 0.2),
      }}
    />
  );
};

export const Card: React.FC<{ element: CardElement }> = ({ element }) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const local = frame / fps - element.start;
  if (local < 0 || local > element.duration) return null;

  const opacity = envelope(local, element.duration, element.fadeIn, element.fadeOut);
  // Grow *through* the resting scale, so the card is never smaller than intended at
  // the moment it becomes readable — same rule as the Python preset.
  const zoom = between(
    local,
    0,
    element.duration,
    1 / element.zoom,
    element.zoom,
    element.easing,
  );
  const tilt = between(
    local,
    0,
    Math.min(element.duration, element.fadeIn * 2.2 + 0.2),
    element.tilt,
    0,
    element.easing,
  );

  return (
    <div
      style={{
        position: "absolute",
        left: element.x * width,
        top: element.y * height,
        width: element.scale * width,
        transform: `translate(-50%, -50%) scale(${zoom}) rotate(${tilt}rad)`,
        opacity,
        // A real blurred shadow. The ffmpeg backend approximates this with a
        // displaced dark copy because blurring an alpha matte there is too slow.
        filter: element.shadow ? "drop-shadow(0 18px 34px rgba(0,0,0,0.45))" : undefined,
      }}
    >
      <Img src={staticFile(element.src)} style={{ width: "100%", display: "block" }} />
    </div>
  );
};
