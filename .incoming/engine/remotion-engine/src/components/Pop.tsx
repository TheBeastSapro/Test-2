import React from 'react';
import {interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import * as S from '../style';
import type {Pop as PopT} from '../sheet';
import {estWidth, popBox} from '../lib/layout';

/**
 * Keyword pops. KEYWORDS, never sentences — the build-time validator fails any
 * pop over 3 words / 22 characters.
 *
 * There is no box and therefore no band under a box any more: a pop is anchored
 * into mid-frame dead space, clear of the caption layer along the bottom and
 * clear of the four corners. On a cinematic frame it is WHITE with a heavy black
 * stroke; on a white-canvas info frame it flips to black (or red when accent)
 * and can take over as the infographic headline.
 */
export const Pop: React.FC<{pop: PopT; onDark: boolean}> = ({pop, onDark}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const t = frame / fps;

  const local = frame - Math.round(pop.t0 * fps);
  const sIn = spring({frame: local, fps, config: {damping: 11, stiffness: 190, mass: 0.7}, durationInFrames: 26});
  const fadeIn = interpolate(t, [pop.t0, pop.t0 + S.POP_IN_DUR], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const fadeOut = interpolate(t, [pop.t1 - S.POP_OUT_DUR, pop.t1], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const opacity = Math.min(fadeIn, fadeOut);
  if (opacity <= 0) return null;

  const txt = pop.text.toUpperCase();
  // wider tracking + a lighter stroke: at track 2 the heavy black stroke welded
  // adjacent glyphs together and the QC OCR pass read '4 LEGS' as '4ILEGS'.
  const track = 3;
  const box = popBox(pop.ax, pop.ay, pop.text, pop.size);
  const shrink = Math.min(1, (S.TYPE_R - S.TYPE_L) / estWidth(txt, pop.size, track));
  const dx = interpolate(sIn, [0, 1], [-52, 0]);
  const scale = interpolate(sIn, [0, 1], [0.9, 1]);
  const stroke = Math.round(pop.size * 0.095) * 2;

  // On a full-frame picture the accent lives in the RULE, not the fill: red type
  // on a night plate is the lowest-contrast thing in the palette (D62020 is only
  // ~86 in luma) and it stops reading — and stops OCR-ing — over a dark plate.
  // On the white-canvas exception the polarity flips and red is the strong choice.
  const fill = onDark ? S.WHITE : pop.accent ? S.RED : S.BLACK;

  const type: React.CSSProperties = {
    fontFamily: S.FONT.pop,
    fontSize: pop.size,
    lineHeight: 1.0,
    letterSpacing: track,
    whiteSpace: 'nowrap',
    paddingRight: track,
  };

  return (
    <div
      style={{
        position: 'absolute',
        left: box.l,
        top: box.t,
        opacity,
        transform: `translateX(${dx}px) scale(${scale})`,
        transformOrigin: 'left top',
      }}
    >
      <div style={{display: 'inline-block', transform: `scale(${shrink})`, transformOrigin: 'left top'}}>
        <div style={{...type, position: 'relative'}}>
          {onDark ? (
            <div style={{...type, position: 'absolute', inset: 0, color: S.BLACK, WebkitTextStroke: `${stroke}px ${S.BLACK}`}}>
              {txt}
            </div>
          ) : null}
          <div style={{...type, position: 'relative', color: fill}}>{txt}</div>
        </div>
        {pop.accent ? (
          <div
            style={{
              marginTop: 12,
              height: 9,
              width: `${100 * Math.min(1, Math.max(0, sIn))}%`,
              background: S.RED,
              borderRadius: 2,
              boxShadow: onDark ? `0 0 0 3px ${S.BLACK}` : undefined,
            }}
          />
        ) : null}
      </div>
    </div>
  );
};
