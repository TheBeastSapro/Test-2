import React from 'react';
import {AbsoluteFill, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import * as S from '../style';
import type {Shot} from '../sheet';
import {mulberry32} from '../lib/rand';

/**
 * The pass that welds plate + cutouts into ONE image: a key-light pool, ground
 * haze, grain and a vignette, all applied over the whole stack and under the
 * type. Without this the layers read as separate flat elements.
 *
 * The key-light pool is also load-bearing for QC: a full-frame night scene has
 * to keep a bright p95 anchor or it trips the "dark and flat" check.
 */
export const Atmosphere: React.FC<{shot: Shot}> = ({shot}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const t = frame / fps;

  const rnd = mulberry32(shot.seed + 5);
  const kx = 24 + rnd() * 52;
  const ky = 16 + rnd() * 44;
  const drift = Math.sin(t * 0.55 + shot.seed) * 3.5;
  // Cut flash: the key pool blooms on the head of every shot and decays. It reads
  // as a cut accent, and it guarantees a bright anchor on the ONE frame where the
  // Ken Burns move has not started yet — that frame was the last thing tripping
  // the QC 'dark and flat' check.
  const head = Math.max(0, 1 - (t - shot.t0) / 0.30);
  const boost = 1 + 0.75 * head ** 2;

  return (
    <AbsoluteFill style={{pointerEvents: 'none'}}>
      {/* key light pool */}
      <AbsoluteFill
        style={{
          background: `radial-gradient(ellipse ${58 + drift}% ${64 - drift}% at ${kx + drift}% ${ky}%, rgba(255,255,255,${0.42 * boost}) 0%, rgba(255,255,255,${0.17 * boost}) 34%, rgba(255,255,255,0) 68%)`,
          mixBlendMode: 'screen',
        }}
      />
      {/* ground haze — pushes the bottom of the frame back into the scene */}
      <AbsoluteFill
        style={{
          background: `linear-gradient(to top, ${S.HAZE_COLOR}66 0%, ${S.HAZE_COLOR}22 24%, rgba(0,0,0,0) 48%)`,
        }}
      />
      {shot.grade === 'red' ? (
        <>
          <AbsoluteFill style={{background: S.RED, opacity: 0.20, mixBlendMode: 'multiply'}} />
          <AbsoluteFill style={{background: '#240505', opacity: 0.11, mixBlendMode: 'screen'}} />
          <AbsoluteFill style={{background: '#000000', opacity: 0.06}} />
        </>
      ) : null}
      {/* grain */}
      <AbsoluteFill
        style={{
          backgroundImage: `url(${staticFile('tex/grain.png')})`,
          backgroundSize: '512px 512px',
          opacity: 0.13,
          mixBlendMode: 'overlay',
          transform: `translate3d(${(frame % 7) * 11 - 33}px, ${(frame % 5) * 13 - 26}px, 0)`,
        }}
      />
      {/* vignette */}
      <AbsoluteFill
        style={{
          background:
            'radial-gradient(ellipse 70% 74% at 50% 48%, rgba(0,0,0,0) 34%, rgba(0,0,0,0.42) 72%, rgba(0,0,0,0.78) 100%)',
        }}
      />
    </AbsoluteFill>
  );
};
