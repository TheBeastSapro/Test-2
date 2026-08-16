import React from 'react';
import * as S from '../style';

/** Animatic annotation for the client — which asset slots this frame still needs
 *  real canon art for. Small, grey, bottom-left. This is the ONLY element
 *  allowed to sit in a frame corner. */
export const SlotTag: React.FC<{text: string; onDark: boolean}> = ({text, onDark}) => (
  <div
    style={{
      position: 'absolute',
      left: 34,
      bottom: 26,
      fontFamily: S.FONT.body,
      fontWeight: 700,
      fontSize: 21,
      letterSpacing: 0.6,
      opacity: 0.85,
      color: onDark ? '#C8CCD4' : S.GREY,
      textShadow: onDark ? '0 0 8px rgba(0,0,0,0.9), 0 1px 2px rgba(0,0,0,0.9)' : undefined,
      whiteSpace: 'nowrap',
    }}
  >
    {text}
  </div>
);
