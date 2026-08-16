import React from 'react';
import {AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import * as S from '../style';

/**
 * Persistent creature-name title, top-centre, ALL CAPS, Anton, with a short red
 * rule under it. HARD RULE: it is on EVERY SINGLE FRAME, including the cinematic
 * ones and the cold open.
 *
 * On a full-frame dark scene it takes a WHITE fill with a heavy BLACK stroke and
 * sits over a subtle top scrim, so it holds on any plate value. On a
 * white-canvas info frame it flips to a black fill and drops the scrim.
 */
export const TitleBar: React.FC<{title: string; onDark: boolean}> = ({title, onDark}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();

  const s = spring({frame, fps, config: {damping: 15, stiffness: 130, mass: 0.8}, durationInFrames: 24});
  const rule = spring({frame: frame - 5, fps, config: {damping: 18, stiffness: 150, mass: 0.7}, durationInFrames: 22});
  // NO fade-in: the title is on every single frame, including frame 0.
  const opacity = 1;
  const dy = interpolate(s, [0, 1], [-26, 0]);

  const txt = title.toUpperCase();
  const type: React.CSSProperties = {
    fontFamily: S.FONT.title,
    fontSize: S.TITLE_SIZE,
    lineHeight: 1.0,
    letterSpacing: S.TITLE_TRACK,
    whiteSpace: 'nowrap',
    paddingRight: S.TITLE_TRACK,
  };

  return (
    <>
      {onDark ? (
        <AbsoluteFill
          style={{
            height: S.TITLE_SCRIM_H,
            background: 'linear-gradient(to bottom, rgba(0,0,0,0.62) 0%, rgba(0,0,0,0.34) 46%, rgba(0,0,0,0) 100%)',
            pointerEvents: 'none',
          }}
        />
      ) : null}
      <div
        style={{
          position: 'absolute',
          left: 0,
          right: 0,
          top: S.TITLE_Y,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          opacity,
          transform: `translateY(${dy}px)`,
        }}
      >
        <div style={{...type, position: 'relative', color: 'transparent'}}>
          {txt}
          {onDark ? (
            <>
              <div style={{...type, position: 'absolute', inset: 0, color: S.BLACK, WebkitTextStroke: `${S.TITLE_STROKE}px ${S.BLACK}`}}>
                {txt}
              </div>
              <div style={{...type, position: 'absolute', inset: 0, color: S.WHITE}}>{txt}</div>
            </>
          ) : (
            <div style={{...type, position: 'absolute', inset: 0, color: S.BLACK}}>{txt}</div>
          )}
          <div
            style={{
              position: 'absolute',
              left: '50%',
              top: S.TITLE_RULE_Y - S.TITLE_Y,
              width: `${34 * Math.min(1, rule)}%`,
              height: S.TITLE_RULE_H,
              background: S.RED,
              transform: 'translateX(-50%)',
              borderRadius: 2,
              boxShadow: onDark ? `0 0 0 3px ${S.BLACK}` : undefined,
            }}
          />
        </div>
      </div>
    </>
  );
};
