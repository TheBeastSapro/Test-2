import React from 'react';
import {AbsoluteFill, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import * as S from '../style';
import {cutFile, type InfoItem, type Shot} from '../sheet';
import {CUT_AR, infoPanels} from '../lib/layout';
import {Glyph} from './Icons';

/**
 * THE EXCEPTION: the white-canvas explainer frame.
 *
 * Reserved for infographic beats — numbers, size comparisons, icon lists. Two
 * layouts, both governed by the house rules:
 *   grid   a 2-up or 3-up grid, EQUAL size, EQUAL border
 *   rules  an icon list that pops ONE AT A TIME on the spoken noun, never
 *          pre-assembled
 * Nothing here is ever a blank text-only card: an info frame without content
 * fails the build-time validator.
 */

const Panel: React.FC<{item: InfoItem; rect: {l: number; t: number; w: number; h: number}; t: number; u: number}> = ({
  item, rect, t, u,
}) => {
  const {fps} = useVideoConfig();
  const frame = useCurrentFrame();
  const local = frame - Math.round(item.t0 * fps);
  if (local < 0) return null;
  const sIn = spring({frame: local, fps, config: {damping: 13, stiffness: 175, mass: 0.7}, durationInFrames: 22});
  const op = interpolate(local, [0, 4], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const dy = interpolate(sIn, [0, 1], [40, 0]);
  const sc = interpolate(sIn, [0, 1], [0.94, 1]);

  const age = t - item.t0;
  const inner = {w: rect.w - S.INFO_BORDER * 2, h: rect.h - S.INFO_BORDER * 2 - 62};

  let img: React.ReactNode = null;
  if (item.cut) {
    const [cx, cy, zoom] = item.crop ?? [0.5, 0.5, 1];
    const ar = CUT_AR[item.cut];
    // A white-canvas frame is still a FRAME: the crop pushes in and pans across
    // the whole beat at constant velocity, or the 0.5s motion samples here fall
    // through the floor and the beat reads as a still.
    const fitH = Math.min(inner.w / ar, inner.h) * 0.86;
    const h0 = fitH * zoom * (1 + 0.10 * u);
    const w0 = h0 * ar;
    img = (
      <img
        src={staticFile(cutFile(item.cut))}
        style={{
          position: 'absolute',
          left: inner.w / 2 - w0 * cx,
          top: inner.h / 2 - h0 * cy,
          width: w0,
          height: h0,
          display: 'block',
          transform: `translate3d(${-26 + 52 * u}px, ${8 - 16 * u}px, 0)`,
        }}
      />
    );
  }

  return (
    <div
      style={{
        position: 'absolute',
        left: rect.l,
        top: rect.t,
        width: rect.w,
        height: rect.h,
        opacity: op,
        transform: `translateY(${dy}px) scale(${sc})`,
        transformOrigin: '50% 100%',
        border: `${S.INFO_BORDER}px solid ${S.BLACK}`,
        borderRadius: S.INFO_RADIUS,
        background: S.WHITE,
        boxSizing: 'border-box',
        overflow: 'hidden',
      }}
    >
      <div style={{position: 'absolute', left: 0, top: 0, width: inner.w, height: inner.h, overflow: 'hidden'}}>
        {img}
        {item.icon ? (
          <div style={{position: 'absolute', left: inner.w / 2 - 90, top: inner.h / 2 - 90}}>
            <Glyph kind={item.icon} s={180} draw={1} onDark={false} />
          </div>
        ) : null}
      </div>
      {item.big ? (
        <div
          style={{
            position: 'absolute',
            left: 18,
            top: 8,
            fontFamily: S.FONT.pop,
            fontSize: 84,
            lineHeight: 1,
            color: item.accent ? S.RED : S.BLACK,
          }}
        >
          {item.big}
        </div>
      ) : null}
      <div
        style={{
          position: 'absolute',
          left: 0,
          right: 0,
          bottom: 14,
          textAlign: 'center',
          fontFamily: S.FONT.pop,
          fontSize: S.INFO_LABEL_SIZE,
          letterSpacing: 1.5,
          color: item.accent ? S.RED : S.BLACK,
        }}
      >
        {item.label.toUpperCase()}
      </div>
    </div>
  );
};

const RuleRow: React.FC<{item: InfoItem; y: number; t: number; u: number}> = ({item, y, t, u}) => {
  const {fps} = useVideoConfig();
  const frame = useCurrentFrame();
  const local = frame - Math.round(item.t0 * fps);
  if (local < 0) return null;
  const sIn = spring({frame: local, fps, config: {damping: 12, stiffness: 180, mass: 0.7}, durationInFrames: 22});
  const op = interpolate(local, [0, 4], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const dx = interpolate(sIn, [0, 1], [-70, 0]);
  const age = t - item.t0;

  return (
    <div
      style={{
        position: 'absolute',
        left: 336,
        top: y,
        display: 'flex',
        alignItems: 'center',
        gap: 34,
        transformOrigin: 'left center',
        opacity: op,
        transform: `translate3d(${dx + 34 * u}px, ${-6 + 12 * u}px, 0) scale(${1 + 0.05 * u})`,
      }}
    >
      <div style={{width: 96, height: 96, display: 'flex', alignItems: 'center'}}>
        <Glyph kind={item.icon ?? 'redx'} s={92} draw={Math.min(1, local / 12)} onDark={false} />
      </div>
      <div
        style={{
          fontFamily: S.FONT.pop,
          fontSize: 54,
          letterSpacing: 1.5,
          color: item.accent ? S.RED : S.BLACK,
          whiteSpace: 'nowrap',
        }}
      >
        {item.label.toUpperCase()}
      </div>
    </div>
  );
};

export const InfoFrame: React.FC<{shot: Shot; headingHidden: boolean}> = ({shot, headingHidden}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const t = frame / fps;
  const info = shot.info!;
  const rects = infoPanels(info.items.length);

  const u = Math.max(0, Math.min(1, (t - shot.t0) / Math.max(1e-6, shot.t1 - shot.t0)));
  const footer = info.footer;
  const fLocal = footer ? frame - Math.round(footer.t0 * fps) : -1;
  const fIn = footer
    ? spring({frame: fLocal, fps, config: {damping: 14, stiffness: 170, mass: 0.7}, durationInFrames: 20})
    : 0;

  return (
    <AbsoluteFill style={{backgroundColor: S.CANVAS}}>
      {info.heading && !headingHidden ? (
        <div
          style={{
            position: 'absolute',
            left: 0,
            right: 0,
            top: S.INFO_HEAD_Y,
            textAlign: 'center',
            fontFamily: S.FONT.pop,
            fontSize: S.INFO_HEAD_SIZE,
            letterSpacing: 3,
            color: S.BLACK,
            transform: `translate3d(${-10 + 20 * u}px, ${Math.sin(t * 1.3) * 2}px, 0)`,
          }}
        >
          {info.heading.toUpperCase()}
          <div
            style={{
              width: 120,
              height: 8,
              background: S.RED,
              borderRadius: 2,
              margin: '18px auto 0',
            }}
          />
        </div>
      ) : null}

      <div
        style={{
          position: 'absolute',
          inset: 0,
          transformOrigin: '50% 52%',
          transform: `translate3d(${14 - 28 * u}px, 0, 0) scale(${1 + 0.035 * u})`,
          willChange: 'transform',
        }}
      >
        {info.kind === 'grid'
          ? info.items.map((it, i) => <Panel key={`p-${i}`} item={it} rect={rects[i]} t={t} u={u} />)
          : info.items.map((it, i) => (
              <RuleRow key={`r-${i}`} item={it} y={S.INFO_GRID_T + 24 + i * 132} t={t} u={u} />
            ))}
      </div>

      {footer && fLocal >= 0 ? (
        <div
          style={{
            position: 'absolute',
            left: 0,
            right: 0,
            top: 782,
            display: 'flex',
            justifyContent: 'center',
            alignItems: 'center',
            gap: 20,
            opacity: interpolate(fLocal, [0, 4], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'}),
            transform: `translateY(${interpolate(fIn, [0, 1], [22, 0])}px)`,
          }}
        >
          <div style={{width: 68 * Math.min(1, fIn), height: 9, background: S.RED, borderRadius: 2}} />
          <div style={{fontFamily: S.FONT.pop, fontSize: 46, letterSpacing: 2, color: S.BLACK}}>
            {footer.text.toUpperCase()}
          </div>
        </div>
      ) : null}
    </AbsoluteFill>
  );
};
