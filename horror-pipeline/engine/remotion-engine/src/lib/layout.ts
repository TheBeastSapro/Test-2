/**
 * Geometry for the composited-scene layout.
 *
 * The frame is FULL-BLEED by default: the background plate covers 1920x1080 and
 * cutout layers sit on top of it in z slots. A "cut closer" is a hard cut to a
 * different CROP of the same plate (different framing scale + different anchor),
 * never a zoom.
 *
 * The white-canvas boxed treatment survives only for infographic beats and gets
 * its geometry from the INFO_* constants.
 */
import * as S from '../style';
import type {CutName, Layer, Shot, PopAnchorX, PopAnchorY} from '../sheet';
import {clamp, mulberry32} from './rand';

export type Rect = {l: number; t: number; w: number; h: number};

export const smooth = (u: number) => {
  const x = clamp(u, 0, 1);
  return x * x * (3 - 2 * x);
};
export const easeOut = (u: number) => 1 - (1 - clamp(u, 0, 1)) ** 3;
export const lerp = (a: number, b: number, k: number) => a + (b - a) * clamp(k, 0, 1);

const HEX = (c: string) => [
  parseInt(c.slice(1, 3), 16),
  parseInt(c.slice(3, 5), 16),
  parseInt(c.slice(5, 7), 16),
];
export const mix = (a: string, b: string, k: number) => {
  const A = HEX(a);
  const B = HEX(b);
  const u = clamp(k, 0, 1);
  return `rgb(${A.map((v, i) => Math.round(v + (B[i] - v) * u)).join(',')})`;
};

// ---------------------------------------------------------------------------
// Background plate
// ---------------------------------------------------------------------------
/** Base <img> size. Every size change is a scale on top of this — nothing ever
 *  animates width/left (Chrome snaps layout to device px and emits dupe frames). */
export const BASE_W = S.W;
export const BASE_H = (S.W * S.PLATE_H) / S.PLATE_W;

const COVER_W = S.W;
const COVER_H = S.W / (S.PLATE_W / S.PLATE_H);

/** Where the plate <img> goes this frame: translate3d + scale, nothing else. */
export const plateXform = (shot: Shot, t: number) => {
  const len = Math.max(1e-6, shot.t1 - shot.t0);
  const u = clamp((t - shot.t0) / len, 0, 1);
  const f = S.FRAMING[shot.framing];

  const cp = Math.max(0, (t - shot.t0) / S.PUNCH_DUR);
  const punch = cp < 1 ? 1 + S.PUNCH_AMT * (1 - easeOut(cp)) : 1;
  // CONSTANT velocity for the whole sub-shot. Easing makes a shot visually
  // stall at both ends and drops the head/tail motion samples into dead zone.
  const scale = f.scale * (1 + f.travel * u) * punch;

  const rnd = mulberry32(shot.seed);
  const r1 = rnd();
  const [cx0, cy0] = shot.crop;
  // always drift toward the middle so the crop can never run off the plate
  const dirX = cx0 < 0.5 ? 1 : -1;
  const dirY = cy0 < 0.5 ? 1 : -1;
  const cx = clamp(cx0 + dirX * f.lateral * u, 0, 1);
  const cy = clamp(cy0 + dirY * f.lateral * 0.55 * u * (0.6 + 0.8 * r1), 0, 1);

  const dispW = COVER_W * scale;
  const dispH = COVER_H * scale;
  const ovX = Math.max(0, dispW - S.W);
  const ovY = Math.max(0, dispH - S.H);
  return {x: -ovX * cx, y: -ovY * cy, k: dispW / BASE_W};
};

// ---------------------------------------------------------------------------
// Cutout layers
// ---------------------------------------------------------------------------
/** intrinsic sizes from engine/cutouts.py SLOTS */
export const CUT_AR: Record<CutName, number> = {
  creature_tall: 1180 / 1500,
  creature_small: 980 / 620,
  car: 1280 / 560,
  treeline: 1920 / 460,
  manhole_rim: 1500 / 480,
  figure: 400 / 940,
};

export type LayerXform = {
  l: number; t: number; w: number; h: number;
  dx: number; dy: number; scale: number; opacity: number;
};

/**
 * Entry animations. All of them are FAST — the client's note is "the creature
 * visibly rises above the trees (fast, I should SEE it move)". `rise` slides the
 * layer up from below its rest position; because it sits in the `creature` z
 * slot and a `front` layer covers the base line, it reads as coming out from
 * BEHIND the foreground element rather than sliding on top of it.
 */
export const layerXform = (layer: Layer, t: number): LayerXform => {
  const h = layer.h;
  const w = h * CUT_AR[layer.cut];
  const dur = layer.dur ?? S.LAYER_ENTRY_DUR;
  const p = clamp((t - layer.t0) / dur, 0, 1);
  const e = easeOut(p);
  const age = Math.max(0, t - layer.t0);

  let dx = 0;
  let dy = 0;
  let scale = 1;
  let opacity = layer.opacity ?? 1;

  switch (layer.entry) {
    case 'rise':
      dy = (1 - e) * h * 0.98;
      break;
    case 'drop':
      dy = -(1 - e) * h * 0.75;
      opacity *= clamp(p * 4, 0, 1);
      break;
    case 'slideL':
      dx = -(1 - e) * (S.W * 0.55 + w / 2);
      break;
    case 'slideR':
      dx = (1 - e) * (S.W * 0.55 + w / 2);
      break;
    case 'push':
      scale = 0.52 + 0.48 * e;
      opacity *= clamp(p * 3, 0, 1);
      break;
    case 'fade':
    default:
      opacity *= e;
      break;
  }

  // independent transform track — nothing on screen is ever fully static
  dx += (layer.dx ?? 0) * age;
  dy += (layer.dy ?? 0) * age;
  if (layer.bob) dy += Math.sin(age * 1.9) * layer.bob;

  return {l: layer.x - w / 2, t: layer.y - h, w, h, dx, dy, scale, opacity};
};

// ---------------------------------------------------------------------------
// Type anchors (shared by the components AND the build-time validator)
// ---------------------------------------------------------------------------
/** conservative advance-width estimate for Archivo Black caps */
export const estWidth = (txt: string, size: number, track = 2) =>
  txt.length * size * 0.66 + Math.max(0, txt.length - 1) * track;

/** Resolve an anchor to a clamped bounding box inside the legal type rect. */
export const textBox = (cx: number, top: number, txt: string, size: number): Rect => {
  const w = Math.min(estWidth(txt, size), S.TYPE_R - S.TYPE_L);
  const h = size * 1.18;
  let l = cx - w / 2;
  l = clamp(l, S.TYPE_L, S.TYPE_R - w);
  const t = clamp(top, S.TYPE_T, S.TYPE_B - h);
  return {l, t, w, h};
};

export const capBox = (ax: PopAnchorX, txt: string, size = S.CAP_SIZE) =>
  textBox(S.CAP_X[ax], S.CAP_Y, txt.toUpperCase(), size);

export const popBox = (ax: PopAnchorX, ay: PopAnchorY, txt: string, size: number) =>
  textBox(S.POP_X[ax], S.POP_Y[ay], txt.toUpperCase(), size);

/** The corners stay EMPTY. Only the grey animatic slot tag is exempt. */
export const inCorner = (r: Rect) => {
  const right = r.l + r.w;
  const bottom = r.t + r.h;
  const xL = r.l < S.CORNER_W;
  const xR = right > S.W - S.CORNER_W;
  const yT = r.t < S.CORNER_H;
  const yB = bottom > S.H - S.CORNER_H;
  return (xL || xR) && (yT || yB);
};

// ---------------------------------------------------------------------------
// White-canvas infographic grid — equal size, equal border, 2-up or 3-up
// ---------------------------------------------------------------------------
export const infoPanels = (n: number): Rect[] => {
  const total = S.INFO_GRID_W;
  const w = (total - S.INFO_GAP * (n - 1)) / n;
  const l0 = (S.W - total) / 2;
  return Array.from({length: n}, (_, i) => ({
    l: l0 + i * (w + S.INFO_GAP),
    t: S.INFO_GRID_T,
    w,
    h: S.INFO_GRID_H,
  }));
};

export const insetFor = (rect: Rect, grow = 0, radius = 0) =>
  `inset(${rect.t - grow}px ${S.W - (rect.l + rect.w + grow)}px ${
    S.H - (rect.t + rect.h + grow)
  }px ${rect.l - grow}px round ${radius}px)`;
