import React from 'react';
import {AbsoluteFill, Easing, interpolate, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import * as S from '../style';
import type {Roster} from '../sheet';

/**
 * Cold open, kept from the previous cut: a roster grid of the channel's
 * creatures, then a punch-in into THIS creature's cell so the section starts
 * inside the grid rather than cutting to it.
 *
 * The punch is a compositor transform on a fixed-size grid — never a resize.
 * The whole move is deliberately fast; by the time it lands, the target cell
 * covers the frame and the hard cut into shot 1 is invisible.
 */
const CELL_W = 440;
const CELL_H = 262;
const GAP = 26;

export const RosterGrid: React.FC<{roster: Roster}> = ({roster}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const t = frame / fps;

  const u = interpolate(t, [roster.t0, roster.t1], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: Easing.bezier(0.36, 0, 0.22, 1),
  });

  const gw = roster.cols * CELL_W + (roster.cols - 1) * GAP;
  const gh = roster.rows * CELL_H + (roster.rows - 1) * GAP;
  const col = roster.cell % roster.cols;
  const row = Math.floor(roster.cell / roster.cols);
  const cellCx = col * (CELL_W + GAP) + CELL_W / 2;
  const cellCy = row * (CELL_H + GAP) + CELL_H / 2;

  const sc = 1 + 3.55 * u;
  // translate so the target cell centre walks to the frame centre as we scale
  const ox = (gw / 2 - cellCx) * u;
  const oy = (gh / 2 - cellCy) * u;

  return (
    <AbsoluteFill style={{backgroundColor: S.SCENE_BG, overflow: 'hidden'}}>
      <AbsoluteFill
        style={{
          background:
            'radial-gradient(ellipse 62% 66% at 44% 34%, rgba(255,255,255,0.22) 0%, rgba(255,255,255,0) 70%)',
          mixBlendMode: 'screen',
          zIndex: 5,
        }}
      />
      <div
        style={{
          position: 'absolute',
          left: (S.W - gw) / 2,
          top: (S.H - gh) / 2,
          width: gw,
          height: gh,
          transformOrigin: '50% 50%',
          transform: `translate3d(${ox * sc}px, ${oy * sc}px, 0) scale(${sc})`,
          willChange: 'transform',
        }}
      >
        {roster.names.map((name, i) => {
          const c = i % roster.cols;
          const r = Math.floor(i / roster.cols);
          const hero = i === roster.cell;
          return (
            <div
              key={name}
              style={{
                position: 'absolute',
                left: c * (CELL_W + GAP),
                top: r * (CELL_H + GAP),
                width: CELL_W,
                height: CELL_H,
                border: `4px solid ${hero ? S.RED : S.WHITE}`,
                borderColor: hero
                  ? `rgba(214,32,32,${interpolate(u, [0.3, 0.62], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'})})`
                  : `rgba(255,255,255,${interpolate(u, [0.2, 0.5], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'})})`,
                boxSizing: 'border-box',
                overflow: 'hidden',
                background: S.SCENE_BG,
                opacity: hero ? 1 : interpolate(u, [0, 0.5], [0.8, 0.32], {extrapolateRight: 'clamp'}),
              }}
            >
              <img
                src={staticFile(hero ? 'plates/card.png' : `plates/slot${String((i % 17) + 1).padStart(2, '0')}.png`)}
                style={{
                  position: 'absolute',
                  left: '50%',
                  top: '50%',
                  width: CELL_W * 1.5,
                  height: (CELL_W * 1.5 * S.PLATE_H) / S.PLATE_W,
                  transform: `translate(-50%, -50%) scale(${hero ? 1 + 0.12 * u : 1})`,
                  filter: hero ? 'brightness(1.15)' : 'grayscale(1) brightness(0.9)',
                }}
              />
              <div
                style={{
                  position: 'absolute',
                  left: 0,
                  right: 0,
                  bottom: 0,
                  padding: '38px 14px 12px',
                  background: 'linear-gradient(to top, rgba(0,0,0,0.88), rgba(0,0,0,0))',
                  textAlign: 'center',
                  fontFamily: S.FONT.card,
                  fontSize: 40,
                  letterSpacing: 1.5,
                  color: hero ? S.WHITE : S.GREY,
                  opacity: interpolate(u, [0.28, 0.55], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'}),
                }}
              >
                {name}
              </div>
              {hero ? (
                <div
                  style={{
                    position: 'absolute',
                    inset: 0,
                    boxShadow: `inset 0 0 0 6px ${S.RED}`,
                    opacity:
                      interpolate(Math.sin(t * 9), [-1, 1], [0.45, 1]) *
                      interpolate(u, [0.25, 0.55], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'}),
                  }}
                />
              ) : null}
            </div>
          );
        })}
      </div>
      {/* the punch lands on black, so the grid can never show its own edge */}
      <AbsoluteFill
        style={{
          background: S.SCENE_BG,
          opacity: interpolate(u, [0.9, 1], [0, 0.22], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'}),
        }}
      />
    </AbsoluteFill>
  );
};
