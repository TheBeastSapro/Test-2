import React from 'react';
import {interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import * as S from '../style';
import type {Icon as IconT, IconKind} from '../sheet';
import {clamp} from '../lib/rand';

/**
 * Icon language: black/white vector only, plus the single red accent.
 * `onDark` swaps the black strokes for white so a glyph stays legible on a
 * full-frame cinematic scene as well as on a white-canvas info frame.
 */
export const Glyph: React.FC<{kind: IconKind; s: number; draw: number; onDark: boolean}> = ({
  kind, s, draw, onDark,
}) => {
  const half = s / 2;
  const ink = onDark ? S.WHITE : S.BLACK;
  const shadow = onDark
    ? 'drop-shadow(0 0 10px rgba(0,0,0,0.9)) drop-shadow(0 2px 4px rgba(0,0,0,0.9))'
    : 'none';

  if (kind === 'redx') {
    const w = Math.max(6, s * 0.14);
    const L = Math.hypot(s, s);
    return (
      <svg width={s} height={s} viewBox={`0 0 ${s} ${s}`} style={{filter: shadow, overflow: 'visible'}}>
        {[
          [0, 0, s, s],
          [0, s, s, 0],
        ].map(([x1, y1, x2, y2], i) => (
          <line
            key={i}
            x1={x1} y1={y1} x2={x2} y2={y2}
            stroke={S.RED}
            strokeWidth={w}
            strokeLinecap="round"
            strokeDasharray={L}
            strokeDashoffset={L * (1 - interpolate(draw, [i * 0.28, 0.72 + i * 0.28], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'}))}
          />
        ))}
      </svg>
    );
  }

  if (kind === 'arrow') {
    const w = Math.max(5, s * 0.1);
    return (
      <svg width={s} height={s} viewBox={`0 0 ${s} ${s}`} style={{filter: shadow, overflow: 'visible'}}>
        <line
          x1={0} y1={half} x2={s * 0.84} y2={half}
          stroke={S.RED} strokeWidth={w} strokeLinecap="round"
          strokeDasharray={s} strokeDashoffset={s * (1 - draw)}
        />
        <polygon
          points={`${s},${half} ${s * 0.66},${half - s * 0.25} ${s * 0.66},${half + s * 0.25}`}
          fill={S.RED}
          opacity={interpolate(draw, [0.55, 0.9], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'})}
        />
      </svg>
    );
  }

  if (kind === 'warn') {
    const w = Math.max(5, s * 0.1);
    return (
      <svg width={s} height={s} viewBox={`0 0 ${s} ${s}`} style={{filter: shadow, overflow: 'visible'}}>
        <polygon
          points={`${half},${s * 0.03} ${s * 0.97},${s * 0.95} ${s * 0.03},${s * 0.95}`}
          fill="none" stroke={S.RED} strokeWidth={w} strokeLinejoin="round"
        />
        <line x1={half} y1={s * 0.34} x2={half} y2={s * 0.68} stroke={S.RED} strokeWidth={w} strokeLinecap="round" />
        <circle cx={half} cy={s * 0.82} r={w * 0.62} fill={S.RED} />
      </svg>
    );
  }

  const w = Math.max(5, s * 0.09);
  return (
    <svg width={s} height={s} viewBox={`0 0 ${s} ${s}`} style={{filter: shadow, overflow: 'visible'}}>
      <circle cx={half} cy={s * 0.16} r={s * 0.15} fill="none" stroke={ink} strokeWidth={w} />
      <line x1={half} y1={s * 0.31} x2={half} y2={s * 0.62} stroke={ink} strokeWidth={w} strokeLinecap="round" />
      <line x1={half - s * 0.28} y1={s * 0.42} x2={half + s * 0.28} y2={s * 0.42} stroke={ink} strokeWidth={w} strokeLinecap="round" />
      <line x1={half} y1={s * 0.62} x2={half - s * 0.22} y2={s * 0.98} stroke={ink} strokeWidth={w} strokeLinecap="round" />
      <line x1={half} y1={s * 0.62} x2={half + s * 0.22} y2={s * 0.98} stroke={ink} strokeWidth={w} strokeLinecap="round" />
    </svg>
  );
};

/** Free-standing icon over a cinematic frame. Clamped into the legal type rect,
 *  which by construction keeps it out of the four corners. */
export const Icon: React.FC<{icon: IconT; onDark: boolean}> = ({icon, onDark}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const t = frame / fps;

  const local = frame - Math.round(icon.t0 * fps);
  const sIn = spring({frame: local, fps, config: {damping: 10, stiffness: 170, mass: 0.6}, durationInFrames: 26});
  const draw = interpolate(local, [0, 14], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const out = interpolate(t, [icon.t1 - 0.18, icon.t1], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const opacity = Math.min(interpolate(local, [0, 4], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'}), out);
  if (opacity <= 0) return null;

  const half = icon.size / 2;
  const cx = clamp(icon.x, S.TYPE_L + half, S.TYPE_R - half);
  const cy = clamp(icon.y, S.TYPE_T + half, S.TYPE_B - half);

  const scale = interpolate(sIn, [0, 1], [0.62, 1]);
  const rot = interpolate(sIn, [0, 1], [icon.kind === 'person' ? 0 : -7, 0]);
  const idle = Math.sin((t - icon.t0) * 3.4);
  const nudge = icon.kind === 'arrow' ? idle * 9 : 0;
  const breathe = 1 + (icon.kind === 'warn' ? Math.abs(idle) * 0.035 : idle * 0.012);

  return (
    <div
      style={{
        position: 'absolute',
        left: cx - half,
        top: cy - half,
        width: icon.size,
        height: icon.size,
        opacity,
        transform: `translateX(${nudge}px) scale(${scale * breathe}) rotate(${rot}deg)`,
      }}
    >
      <Glyph kind={icon.kind} s={icon.size} draw={draw} onDark={onDark} />
    </div>
  );
};
