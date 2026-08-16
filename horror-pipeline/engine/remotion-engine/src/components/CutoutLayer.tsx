import React from 'react';
import {staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import * as S from '../style';
import {cutFile, type Layer} from '../sheet';
import {layerXform} from '../lib/layout';
import {clamp} from '../lib/rand';

/**
 * One cutout layer of a composited scene.
 *
 * Three things stop a cutout reading as "pasted on":
 *   tint   a colour pushed into the silhouette to match the plate / the sky
 *          (the reference cut tints the creature red for the climax)
 *   haze   atmospheric perspective by z slot — a `back` layer sits further into
 *          the scene than a `creature` layer and gets more of the scene colour
 *   shadow a contact shadow pinned to the layer's REST base line (it does not
 *          ride up with a rising creature, which would look like a sticker)
 */
export const CutoutLayer: React.FC<{layer: Layer}> = ({layer}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const t = frame / fps;

  const x = layerXform(layer, t);
  if (x.opacity <= 0.001) return null;

  const src = staticFile(cutFile(layer.cut));
  const haze = S.HAZE[layer.z];
  const maskCommon: React.CSSProperties = {
    position: 'absolute',
    inset: 0,
    WebkitMaskImage: `url(${src})`,
    maskImage: `url(${src})`,
    WebkitMaskSize: '100% 100%',
    maskSize: '100% 100%',
    WebkitMaskRepeat: 'no-repeat',
    maskRepeat: 'no-repeat',
  };

  const entered = clamp((t - layer.t0) / (layer.dur ?? S.LAYER_ENTRY_DUR), 0, 1);
  const shW = x.w * 0.58;
  const shH = Math.max(10, x.h * 0.045);

  return (
    <>
      {layer.shadow ? (
        <div
          style={{
            position: 'absolute',
            left: layer.x - shW / 2,
            top: layer.y - shH * 0.55,
            width: shW,
            height: shH,
            opacity: 0.34 * entered * x.opacity,
            background: 'radial-gradient(ellipse at 50% 50%, rgba(0,0,0,0.85) 0%, rgba(0,0,0,0) 70%)',
          }}
        />
      ) : null}
      <div
        style={{
          position: 'absolute',
          left: x.l,
          top: x.t,
          width: x.w,
          height: x.h,
          opacity: x.opacity,
          transformOrigin: '50% 100%',
          transform: `translate3d(${x.dx}px, ${x.dy}px, 0) scale(${x.scale})${layer.flip ? ' scaleX(-1)' : ''}`,
          filter: layer.blur ? `blur(${layer.blur}px)` : undefined,
          willChange: 'transform',
        }}
      >
        <img src={src} style={{width: '100%', height: '100%', display: 'block'}} />
        {layer.tint ? (
          <div style={{...maskCommon, background: layer.tintColor ?? S.HAZE_COLOR, opacity: layer.tint}} />
        ) : null}
        {haze ? <div style={{...maskCommon, background: S.HAZE_COLOR, opacity: haze}} /> : null}
        {S.DARKEN[layer.z] ? (
          <div style={{...maskCommon, background: '#000000', opacity: S.DARKEN[layer.z]}} />
        ) : null}
      </div>
    </>
  );
};
