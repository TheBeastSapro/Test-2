import React from 'react';
import {Composition} from 'remotion';
import {SewerSpider} from './SewerSpider';
import {DURATION} from './sheet';
import {assertSheet} from './lib/validate';
import * as S from './style';

// HARD build-time gate. A sheet that breaks a house rule throws here, which
// fails `remotion render` before a single frame is drawn.
assertSheet();

export const RemotionRoot: React.FC = () => (
  <>
    <Composition
      id="SewerSpider"
      component={SewerSpider}
      durationInFrames={Math.round(DURATION * S.FPS)}
      fps={S.FPS}
      width={S.W}
      height={S.H}
      defaultProps={{withAudio: true}}
    />
  </>
);
