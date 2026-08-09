import React from 'react';
import {AbsoluteFill, useCurrentFrame, useVideoConfig} from 'remotion';
import * as S from '../style';
import {CAPTIONS, CUTOUTS, ICONS, PLATES, POPS, ROSTER, SHOTS, TITLE} from '../sheet';
import {SceneStack} from './SceneStack';
import {InfoFrame} from './InfoFrame';
import {RosterGrid} from './RosterGrid';
import {TitleBar} from './TitleBar';
import {SlotTag} from './SlotTag';
import {Pop} from './Pop';
import {Caption} from './Caption';
import {Icon} from './Icons';

/**
 * Frame assembly. Default = a full-frame composited scene; white canvas only
 * when the shot is flagged as an infographic beat. The title and the caption
 * layer sit above BOTH, always.
 */
export const Scene: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const t = frame / fps;

  const inRoster = t < ROSTER.t1;
  const shot = SHOTS.find((s) => t >= s.t0 && t < s.t1) ?? SHOTS[SHOTS.length - 1];
  const onDark = inRoster || !shot.whiteCanvas;

  const pops = POPS.filter((p) => t >= p.t0 && t < p.t1);
  const caps = CAPTIONS.filter((c) => t >= c.t0 && t < c.t1);
  const headPop = pops.some((p) => p.ay === 'head');

  const tag = inRoster
    ? 'ROSTER GRID · PLACEHOLDER · COLD OPEN'
    : shot.whiteCanvas
      ? `INFOGRAPHIC · PLACEHOLDER · ${shot.desc.toUpperCase()}`
      : `PLATE ${String(shot.plate).padStart(2, '0')}${
          shot.layers.length
            ? ' · CUT ' + [...new Set(shot.layers.map((l) => String(CUTOUTS[l.cut]).padStart(2, '0')))].sort().join('/')
            : ''
        } · ${shot.framing.toUpperCase()} · PLACEHOLDER · ${(PLATES[shot.plate] ?? shot.desc).toUpperCase()}`;

  return (
    <AbsoluteFill style={{backgroundColor: onDark ? S.SCENE_BG : S.CANVAS}}>
      {inRoster ? (
        <RosterGrid roster={ROSTER} />
      ) : shot.whiteCanvas ? (
        <InfoFrame shot={shot} headingHidden={headPop} />
      ) : (
        <SceneStack shot={shot} />
      )}

      <AbsoluteFill style={{zIndex: 1000}}>
        {ICONS.filter((i) => t >= i.t0 && t < i.t1).map((i, n) => (
          <Icon key={`ic-${n}`} icon={i} onDark={onDark} />
        ))}
        <TitleBar title={TITLE} onDark={onDark} />
        {pops.map((p, n) => (
          <Pop key={`pop-${n}`} pop={p} onDark={onDark} />
        ))}
        {caps.map((c, n) => (
          <Caption key={`cap-${n}`} cap={c} onDark={onDark} />
        ))}
        <SlotTag text={tag} onDark={onDark} />
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
