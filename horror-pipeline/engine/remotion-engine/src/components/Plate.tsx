import React from 'react';
import {AbsoluteFill, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import * as S from '../style';
import type {Shot} from '../sheet';
import {BASE_H, BASE_W, plateXform} from '../lib/layout';

/**
 * The background plate, covering the whole 1920x1080 frame.
 *
 * A shot's `framing` picks the CROP (wide / close / insert). Cutting closer is a
 * hard cut to a different crop of the SAME plate — consecutive shots reuse the
 * plate deliberately, which is the whole point of the layered-cutout language.
 * Within a sub-shot the crop moves at constant velocity so no 0.5s motion sample
 * ever lands in a dead zone.
 */
export const Plate: React.FC<{shot: Shot}> = ({shot}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const {x, y, k} = plateXform(shot, frame / fps);

  return (
    <AbsoluteFill style={{backgroundColor: S.SCENE_BG, overflow: 'hidden'}}>
      <img
        src={staticFile(`plates/slot${String(shot.plate).padStart(2, '0')}.png`)}
        style={{
          position: 'absolute',
          left: 0,
          top: 0,
          width: BASE_W,
          height: BASE_H,
          display: 'block',
          transformOrigin: '0 0',
          transform: `translate3d(${x}px, ${y}px, 0) scale(${k})`,
          willChange: 'transform',
        }}
      />
    </AbsoluteFill>
  );
};
