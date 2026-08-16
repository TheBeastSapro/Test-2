import React from 'react';
import {AbsoluteFill, Audio, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import * as S from './style';
import {GLITCHES, ROSTER, SHAKES, SHOTS} from './sheet';
import {Scene} from './components/Scene';
import {Glitch, GlitchDefs} from './components/Glitch';
import {ensureFonts} from './fonts';

export const SewerSpider: React.FC<{withAudio?: boolean}> = ({withAudio = true}) => {
  ensureFonts();
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const t = frame / fps;

  // --- screen shake on impact beats (decaying) --------------------------
  // The layer is overscanned by exactly enough to cover its own displacement,
  // so the shake can never slide the frame edge into view.
  let dx = 0;
  let dy = 0;
  let rot = 0;
  let amp = 0;
  for (const sk of SHAKES) {
    if (t >= sk.t0 && t < sk.t0 + sk.dur) {
      const k = (t - sk.t0) / sk.dur;
      const a = sk.amp * (1 - k) ** 2;
      amp = Math.max(amp, a);
      dx += a * Math.sin(t * 92);
      dy += a * Math.cos(t * 77);
      rot += a * 0.02 * Math.sin(t * 61);
    }
  }
  const overscan = 1 + (2.2 * amp) / S.H;

  const shot = SHOTS.find((s) => t >= s.t0 && t < s.t1);
  const bg = t < ROSTER.t1 || !shot?.whiteCanvas ? S.SCENE_BG : S.CANVAS;

  const burst = GLITCHES.find((g) => t >= g.t0 && t < g.t0 + g.dur);
  const scene = <Scene />;

  return (
    <AbsoluteFill style={{backgroundColor: bg}}>
      <GlitchDefs />
      {withAudio ? <Audio src={staticFile('audio/mix.wav')} /> : null}
      <AbsoluteFill
        style={{
          transform: `translate(${dx}px, ${dy}px) rotate(${rot}deg) scale(${overscan})`,
          backgroundColor: bg,
        }}
      >
        {burst ? <Glitch burst={burst}>{scene}</Glitch> : scene}
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
