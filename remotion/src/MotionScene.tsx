/**
 * One scene: a background bed with the plan's elements composited over it.
 *
 * Deliberately the same shape as `motion.Scene` on the Python side — a background
 * plus a flat list of timed elements — so a plan renders identically through either
 * backend and neither becomes the one that "really" defines the look.
 */

import React from "react";
import { AbsoluteFill, Img, OffthreadVideo, staticFile } from "remotion";

import { Band, Text } from "./elements";
import { DEFAULT_PLAN, type ScenePlan } from "./types";

export const MotionScene: React.FC<{ plan?: ScenePlan }> = ({ plan }) => {
  const scene = plan ?? DEFAULT_PLAN;
  const { background } = scene;

  return (
    <AbsoluteFill style={{ backgroundColor: background.colour }}>
      {background.kind === "video" && background.src ? (
        // OffthreadVideo, not <Video>: it extracts frames with ffmpeg rather than
        // playing back in the page, which is both faster and frame-accurate. A
        // <Video> in a headless render drifts against the timeline.
        <OffthreadVideo
          src={staticFile(background.src)}
          style={{ width: "100%", height: "100%", objectFit: "cover" }}
        />
      ) : null}
      {background.kind === "image" && background.src ? (
        <Img
          src={staticFile(background.src)}
          style={{ width: "100%", height: "100%", objectFit: "cover" }}
        />
      ) : null}

      {scene.elements.map((element, index) => {
        const key = `${element.kind}-${index}`;
        if (element.kind === "text") {
          return <Text key={key} element={element} fontFamily={scene.fontFamily} />;
        }
        return <Band key={key} element={element} />;
      })}
    </AbsoluteFill>
  );
};
