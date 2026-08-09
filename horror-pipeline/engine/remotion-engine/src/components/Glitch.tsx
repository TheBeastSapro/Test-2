import React from 'react';
import {AbsoluteFill, useCurrentFrame, useVideoConfig} from 'remotion';
import * as S from '../style';
import type {Burst} from '../sheet';
import {mulberry32} from '../lib/rand';

/** SVG channel-isolation filters, mounted once. */
export const GlitchDefs: React.FC = () => (
  <svg width={0} height={0} style={{position: 'absolute'}} aria-hidden>
    <defs>
      <filter id="ch-r" colorInterpolationFilters="sRGB">
        <feColorMatrix type="matrix" values="1 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 1 0" />
      </filter>
      <filter id="ch-g" colorInterpolationFilters="sRGB">
        <feColorMatrix type="matrix" values="0 0 0 0 0  0 1 0 0 0  0 0 0 0 0  0 0 0 1 0" />
      </filter>
      <filter id="ch-b" colorInterpolationFilters="sRGB">
        <feColorMatrix type="matrix" values="0 0 0 0 0  0 0 0 0 0  0 0 1 0 0  0 0 0 1 0" />
      </filter>
    </defs>
  </svg>
);

/**
 * RGB-split + scanline glitch. Three channel-isolated copies of the scene are
 * screen-blended over black with opposing horizontal offsets, plus tear slices
 * and scanlines. Much cleaner than v1's numpy channel roll (no wrap-around
 * artefacts at the frame edges).
 */
export const Glitch: React.FC<{burst: Burst; children: React.ReactNode}> = ({burst, children}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const t = frame / fps;
  const k = Math.max(0, 1 - (t - burst.t0) / burst.dur);
  const shift = burst.amp * k;

  const rnd = mulberry32(frame * 2654435761);
  const slices = [0, 1].map(() => {
    const top = rnd() * 88;
    const h = 3 + rnd() * 9;
    const dx = (rnd() - 0.5) * burst.amp * 3.2 * k;
    return {top, h, dx};
  });

  return (
    <AbsoluteFill style={{backgroundColor: '#000000', isolation: 'isolate'}}>
      <AbsoluteFill style={{filter: 'url(#ch-r)', mixBlendMode: 'screen', transform: `translateX(${shift}px) scale(1.05)`}}>
        {children}
      </AbsoluteFill>
      <AbsoluteFill style={{filter: 'url(#ch-g)', mixBlendMode: 'screen', transform: `translateY(${-shift * 0.18}px) scale(1.05)`}}>
        {children}
      </AbsoluteFill>
      <AbsoluteFill style={{filter: 'url(#ch-b)', mixBlendMode: 'screen', transform: `translateX(${-shift}px) scale(1.05)`}}>
        {children}
      </AbsoluteFill>

      {slices.map((sl, i) => (
        <AbsoluteFill
          key={i}
          style={{
            clipPath: `inset(${sl.top}% 0 ${Math.max(0, 100 - sl.top - sl.h)}% 0)`,
            transform: `translateX(${sl.dx}px) scale(1.02)`,
          }}
        >
          {children}
        </AbsoluteFill>
      ))}

      {/* scanlines */}
      <AbsoluteFill
        style={{
          background: `repeating-linear-gradient(to bottom, rgba(0,0,0,${0.13 * k + 0.03}) 0px, rgba(0,0,0,${
            0.13 * k + 0.03
          }) 2px, rgba(0,0,0,0) 2px, rgba(0,0,0,0) 6px)`,
        }}
      />
      {/* red accent flash, palette-safe */}
      <AbsoluteFill style={{backgroundColor: S.RED, opacity: 0.06 * k, mixBlendMode: 'multiply'}} />
    </AbsoluteFill>
  );
};
