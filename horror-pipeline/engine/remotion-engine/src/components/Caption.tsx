import React from 'react';
import {interpolate, useCurrentFrame, useVideoConfig} from 'remotion';
import * as S from '../style';
import type {Caption as CaptionT} from '../sheet';
import {capBox, estWidth} from '../lib/layout';

/**
 * The always-on keyword caption layer. HARD RULE: no frame is ever text-free —
 * the title plus either a caption or a pop is on screen at all times, and the
 * build-time validator fails the render if that is not true.
 *
 * Captions live in the dead space along the bottom of the frame. There is no box
 * to sit under any more, so the anchor moves left/centre/right shot to shot and
 * the whole layer is deliberately smaller and quieter than a pop.
 */
export const Caption: React.FC<{cap: CaptionT; onDark: boolean}> = ({cap, onDark}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const t = frame / fps;

  const fadeIn =
    cap.t0 <= 0
      ? 1
      : interpolate(t, [cap.t0, cap.t0 + S.CAP_IN_DUR], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const fadeOut = interpolate(t, [cap.t1 - S.CAP_OUT_DUR, cap.t1], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const opacity = Math.min(fadeIn, fadeOut);
  if (opacity <= 0) return null;

  const txt = cap.text.toUpperCase();
  const track = 1.5;
  const box = capBox(cap.ax, cap.text);
  const shrink = Math.min(1, (S.TYPE_R - S.TYPE_L) / estWidth(txt, S.CAP_SIZE, track));
  const dy = interpolate(fadeIn, [0, 1], [22, 0]) - interpolate(fadeOut, [0, 1], [10, 0]);
  const drift = Math.sin((t - cap.t0) * 1.4) * 2;
  const stroke = Math.round(S.CAP_SIZE * 0.135) * 2;

  const type: React.CSSProperties = {
    fontFamily: S.FONT.pop,
    fontSize: S.CAP_SIZE,
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
        transform: `translateY(${dy + drift}px)`,
      }}
    >
      <div style={{display: 'flex', alignItems: 'center', gap: 16, transform: `scale(${shrink})`, transformOrigin: 'left top'}}>
        <div
          style={{
            width: 10,
            height: S.CAP_SIZE * 0.86,
            background: S.RED,
            borderRadius: 2,
            boxShadow: onDark ? `0 0 0 3px ${S.BLACK}` : undefined,
          }}
        />
        <div style={{...type, position: 'relative'}}>
          {onDark ? (
            <div style={{...type, position: 'absolute', inset: 0, color: S.BLACK, WebkitTextStroke: `${stroke}px ${S.BLACK}`}}>
              {txt}
            </div>
          ) : null}
          <div style={{...type, position: 'relative', color: onDark ? S.WHITE : cap.accent ? S.RED : S.BLACK}}>
            {txt}
          </div>
        </div>
      </div>
    </div>
  );
};
