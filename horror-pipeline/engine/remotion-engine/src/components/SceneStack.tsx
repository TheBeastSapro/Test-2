import React from 'react';
import {AbsoluteFill} from 'remotion';
import * as S from '../style';
import type {Shot} from '../sheet';
import {Plate} from './Plate';
import {CutoutLayer} from './CutoutLayer';
import {Atmosphere} from './Atmosphere';

/**
 * A cinematic scene: ONE background plate + an ordered stack of cutout layers,
 * filling the whole frame. This is the DEFAULT treatment now.
 *
 * z slots, back to front:  back -> mid -> creature -> front
 * `front` is the foreground slot that makes the signature move work: a creature
 * in the `creature` slot rises from BEHIND a treeline / manhole rim sitting in
 * `front`, instead of sliding on top of the picture.
 */
export const SceneStack: React.FC<{shot: Shot}> = ({shot}) => (
  <AbsoluteFill style={{backgroundColor: S.SCENE_BG, filter: 'contrast(1.10) saturate(0.92)'}}>
    <Plate shot={shot} />
    {shot.layers.map((layer, i) => (
      <AbsoluteFill key={`ly-${i}`} style={{zIndex: S.Z[layer.z] * 10 + i}}>
        <CutoutLayer layer={layer} />
      </AbsoluteFill>
    ))}
    <AbsoluteFill style={{zIndex: 900}}>
      <Atmosphere shot={shot} />
    </AbsoluteFill>
  </AbsoluteFill>
);
