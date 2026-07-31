/**
 * Composition registry.
 *
 * The composition's size and duration come from the props rather than being declared
 * here, via `calculateMetadata`. That matters: the plan is produced by a preset
 * measured from a reference video, so its duration and aspect ratio are data, and
 * hard-coding them here would mean every render silently conformed to whatever was
 * typed in this file.
 */

import React from "react";
import { Composition } from "remotion";

import { MotionScene } from "./MotionScene";
import { DEFAULT_PLAN, type ScenePlan } from "./types";

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="MotionScene"
      component={MotionScene}
      defaultProps={{ plan: DEFAULT_PLAN }}
      // Placeholders; calculateMetadata replaces all four from the incoming plan.
      durationInFrames={150}
      fps={30}
      width={1280}
      height={720}
      calculateMetadata={({ props }: { props: { plan?: ScenePlan } }) => {
        const plan = props.plan ?? DEFAULT_PLAN;
        return {
          // At least one frame: a zero-length composition is a hard render error,
          // and a scene rounding to zero should produce a blip, not a crash.
          durationInFrames: Math.max(1, Math.round(plan.duration * plan.fps)),
          fps: plan.fps,
          width: plan.width,
          height: plan.height,
        };
      }}
    />
  );
};
