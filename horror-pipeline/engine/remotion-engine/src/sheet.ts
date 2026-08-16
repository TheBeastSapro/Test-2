/**
 * EDIT SHEET — Sewer Spider, section 1.
 *
 * REBUILT 2026-08-08 for the corrected house style. Every time anchor from the
 * previous cut is preserved (the audio at assets/work/mix.wav is FIXED at
 * 62.60s and is not rebuilt); shots are SPLIT at internal times that were
 * snapped to detected transients in that mix, so the new hard cuts still land
 * on something you can hear.
 *
 * Structure per shot:
 *   plate     which background plate slot this shot composites over. Consecutive
 *             beats REUSE a plate — the background persists, the SHOT does not.
 *   framing   wide | close | insert. "Cut closer" = a hard cut to a different
 *             CROP of the same plate. Never a zoom.
 *   layers[]  ordered cutout layers, each with its own entry time, entry
 *             animation, z slot, transform track and tint.
 *   whiteCanvas  the infographic EXCEPTION: numbers, size comparisons, icon
 *             lists. Everything else fills the frame.
 */
import * as S from './style';

export const VO_OFFSET = 0.7;
export const DURATION = 62.6;
export const TITLE = 'The Sewer Spider';

// ---------------------------------------------------------------------------
// Background plates — mirrors PLATES in engine/sheets/sewer_spider.py
// ---------------------------------------------------------------------------
export const PLATES: Record<number, string> = {
  1: 'sewer access ladder, torchlight down a service shaft',
  2: 'flooded storm tunnel, standing water, distant light',
  3: 'tunnel mouth at street level, two workers in hi-vis',
  4: "supervisor's face half lit, the laugh stopping",
  5: 'dark water surface, something long underneath',
  6: 'black tunnel throat, the pipe going deep',
  7: 'scanned forum post, monospaced text block',
  8: 'city works ID badge and a paper shift log',
  9: 'tunnel branch, three dark mouths',
  10: 'HERO: open manhole at night, wet asphalt',
  11: 'archive record with the name field left blank',
  12: 'forum thread, replies naming the creature',
  13: 'the original post, one word highlighted',
  14: 'macro on the word: spiders',
  15: 'wide: three manholes on one street, all open',
  16: 'empty street at night, POV crossing away',
  17: 'municipal ROAD CLOSED sign, routine maintenance',
};

// ---------------------------------------------------------------------------
// Cutouts — mirrors engine/cutouts.py SLOTS (slot number is the tag)
// ---------------------------------------------------------------------------
export const CUTOUTS = {
  creature_tall: 1,
  creature_small: 2,
  car: 3,
  treeline: 4,
  manhole_rim: 5,
  figure: 6,
} as const;
export type CutName = keyof typeof CUTOUTS;
export const cutFile = (c: CutName) =>
  `cutouts/cut${String(CUTOUTS[c]).padStart(2, '0')}_${c}.png`;

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
export type Framing = S.FramingName;
export type ZSlot = keyof typeof S.Z;
export type Entry = 'rise' | 'slideL' | 'slideR' | 'push' | 'drop' | 'fade';

export type Layer = {
  cut: CutName;
  /** ABSOLUTE entry start. May precede this shot's t0 — a layer that entered in
   *  the wide sub-shot is already in when we hard-cut to the close one. */
  t0: number;
  entry: Entry;
  dur?: number;
  /** rest position, frame px. x = centre, y = BASE (bottom) line. */
  x: number;
  y: number;
  /** rendered height, frame px */
  h: number;
  z: ZSlot;
  flip?: boolean;
  /** 0..1 colour tint pushed into the cutout to match the plate/sky */
  tint?: number;
  tintColor?: string;
  /** depth-of-field blur, px */
  blur?: number;
  opacity?: number;
  /** independent per-layer drift, px/s */
  dx?: number;
  dy?: number;
  /** vertical bob amplitude, px */
  bob?: number;
  /** contact shadow under the base line */
  shadow?: boolean;
};

export type InfoItem = {
  t0: number;
  label: string;
  big?: string;
  cut?: CutName;
  icon?: IconKind;
  /** [cx, cy, zoom] crop into the cutout, so panels can show different parts */
  crop?: [number, number, number];
  accent?: boolean;
};
export type Info = {
  kind: 'grid' | 'rules';
  heading?: string;
  items: InfoItem[];
  footer?: {text: string; t0: number};
};

export type Shot = {
  t0: number;
  t1: number;
  desc: string;
  plate: number;
  framing: Framing;
  /** normalised crop anchor into the plate — the "different crop" of a cut */
  crop: [number, number];
  seed: number;
  layers: Layer[];
  whiteCanvas?: boolean;
  info?: Info;
  grade?: 'red' | 'cold';
};

export type PopAnchorX = 'l' | 'c' | 'r';
export type PopAnchorY = 'head' | 'high' | 'mid' | 'low';
export type Pop = {
  text: string;
  t0: number;
  t1: number;
  ax: PopAnchorX;
  ay: PopAnchorY;
  accent: boolean;
  size: number;
};

export type Caption = {text: string; t0: number; t1: number; ax: PopAnchorX; accent?: boolean};

export type IconKind = 'redx' | 'person' | 'arrow' | 'warn';
export type Icon = {kind: IconKind; t0: number; t1: number; x: number; y: number; size: number};
export type Burst = {t0: number; dur: number; amp: number};

/** Roster-grid cold open, kept from the previous cut, plus the punch-in into
 *  the creature's own cell. */
export type Roster = {
  t0: number;
  t1: number;
  cols: number;
  rows: number;
  cell: number;             // index of the sewer spider's cell
  names: string[];
};
export const ROSTER: Roster = {
  t0: 0.0,
  t1: 2.3,
  cols: 4,
  rows: 2,
  cell: 2,
  names: [
    'THE GRINNER', 'HOLLOW MAN', 'SEWER SPIDER', 'THE PALE ELK',
    'NIGHT NURSE', 'THE LONG DOG', 'ROOM 9', 'THE QUIET ONE',
  ],
};

// ---------------------------------------------------------------------------
// SHOTS
// ---------------------------------------------------------------------------
const L = (
  cut: CutName, t0: number, entry: Entry, x: number, y: number, h: number, z: ZSlot,
  extra: Partial<Layer> = {},
): Layer => ({cut, t0, entry, x, y, h, z, shadow: z !== 'front', ...extra});

const RAW: Omit<Shot, 'seed'>[] = [
  // --- 2.3 ladder shaft ---------------------------------------------------
  {t0: 2.30, t1: 3.63, desc: 'service shaft, torch down the ladder', plate: 1, framing: 'wide', crop: [0.44, 0.46],
   layers: [L('figure', 2.50, 'drop', 1330, 980, 430, 'mid', {tint: 0.22, dy: -3})]},
  {t0: 3.63, t1: 5.20, desc: 'closer: the worker on the rungs', plate: 1, framing: 'close', crop: [0.66, 0.60],
   layers: [L('figure', 2.50, 'drop', 1180, 1030, 640, 'mid', {tint: 0.22, dy: -5})]},

  // --- 5.2 flooded tunnel -------------------------------------------------
  {t0: 5.20, t1: 6.44, desc: 'flooded storm tunnel, standing water', plate: 2, framing: 'wide', crop: [0.50, 0.52],
   layers: [L('creature_small', 5.60, 'rise', 1250, 762, 170, 'back', {tint: 0.34, blur: 2.5, dx: -6})]},
  {t0: 6.44, t1: 8.00, desc: 'closer: the far end of the water', plate: 2, framing: 'close', crop: [0.64, 0.44],
   layers: [L('creature_small', 5.60, 'rise', 1150, 806, 280, 'back', {tint: 0.30, blur: 2, dx: -9})]},

  // --- 8.0 the two workers ------------------------------------------------
  {t0: 8.00, t1: 9.06, desc: 'tunnel mouth, two workers, a parked car', plate: 3, framing: 'wide', crop: [0.46, 0.54],
   layers: [
     L('figure', 8.15, 'slideR', 640, 936, 330, 'mid', {tint: 0.20}),
     L('figure', 8.45, 'slideR', 862, 946, 352, 'mid', {tint: 0.20, flip: true}),
     L('car', 8.60, 'slideL', 1520, 1014, 300, 'front', {tint: 0.10}),
   ]},
  {t0: 9.06, t1: 10.60, desc: 'closer: the supervisor turning', plate: 3, framing: 'close', crop: [0.36, 0.62],
   layers: [
     L('figure', 8.15, 'slideR', 700, 1024, 520, 'mid', {tint: 0.18}),
     L('figure', 8.45, 'slideR', 1040, 1042, 548, 'mid', {tint: 0.18, flip: true}),
     L('car', 8.60, 'slideL', 1740, 1120, 430, 'front', {tint: 0.10}),
   ]},

  // --- 10.6 the face ------------------------------------------------------
  {t0: 10.60, t1: 12.00, desc: "supervisor's face half lit, the laugh stopping", plate: 4, framing: 'close', crop: [0.52, 0.42],
   layers: []},

  // --- 12.0 not alligators ------------------------------------------------
  {t0: 12.00, t1: 13.21, desc: 'dark water, something long underneath', plate: 5, framing: 'wide', crop: [0.48, 0.50],
   layers: [
     L('creature_small', 12.20, 'rise', 900, 700, 260, 'creature', {tint: 0.26, dx: 8}),
     L('treeline', 12.00, 'fade', 960, 1170, 300, 'front', {tint: 0.12, flip: true}),
   ]},
  {t0: 13.21, t1: 14.20, desc: 'closer: the shape does not move like a gator', plate: 5, framing: 'close', crop: [0.40, 0.58],
   layers: [
     L('creature_small', 12.20, 'rise', 840, 786, 430, 'creature', {tint: 0.22, dx: 12}),
     L('treeline', 12.00, 'fade', 960, 1216, 340, 'front', {tint: 0.12, flip: true}),
   ]},

  // --- 14.2 THE REVEAL — it rises from behind the foreground ---------------
  {t0: 14.20, t1: 15.28, desc: 'REVEAL: it comes up from behind the ridge', plate: 6, framing: 'wide', crop: [0.50, 0.44],
   layers: [
     L('treeline', 14.20, 'fade', 960, 1152, 330, 'front', {tint: 0.10}),
     L('creature_tall', 14.25, 'rise', 980, 986, 760, 'creature', {tint: 0.30, dur: 0.42, bob: 5}),
   ]},
  {t0: 15.28, t1: 17.00, desc: 'HARD CUT closer: it turns toward us', plate: 6, framing: 'close', crop: [0.56, 0.36],
   layers: [
     L('treeline', 14.20, 'fade', 960, 1268, 420, 'front', {tint: 0.10}),
     L('creature_tall', 14.25, 'rise', 1010, 1128, 1150, 'creature', {tint: 0.26, dur: 0.42, bob: 7, dx: -10}),
   ]},

  // --- 17.0 the post ------------------------------------------------------
  {t0: 17.00, t1: 18.41, desc: 'scanned forum post, monospaced block', plate: 7, framing: 'wide', crop: [0.50, 0.48], layers: []},
  {t0: 18.41, t1: 19.30, desc: 'INSERT: one paragraph of the post', plate: 7, framing: 'insert', crop: [0.38, 0.62], layers: []},

  // --- 19.3 the badge -----------------------------------------------------
  {t0: 19.30, t1: 20.47, desc: 'city works ID badge and a shift log', plate: 8, framing: 'wide', crop: [0.52, 0.50],
   layers: [L('figure', 19.50, 'fade', 1560, 1000, 340, 'back', {tint: 0.35, blur: 3})]},
  {t0: 20.47, t1: 21.80, desc: 'closer: the name field on the badge', plate: 8, framing: 'close', crop: [0.62, 0.42], layers: []},

  // --- 21.8 three mouths --------------------------------------------------
  {t0: 21.80, t1: 23.49, desc: 'tunnel branch, three dark mouths', plate: 9, framing: 'wide', crop: [0.48, 0.52],
   layers: [L('creature_small', 22.30, 'rise', 1420, 706, 200, 'back', {tint: 0.36, blur: 2.5, dx: -5})]},
  {t0: 23.49, t1: 24.60, desc: 'closer: the right-hand mouth', plate: 9, framing: 'close', crop: [0.70, 0.48],
   layers: [L('creature_small', 22.30, 'rise', 1450, 774, 330, 'back', {tint: 0.30, blur: 2, dx: -8})]},

  // --- 24.6 HERO: legs rise out of the manhole ----------------------------
  {t0: 24.60, t1: 25.91, desc: 'HERO wide: open manhole, wet asphalt', plate: 10, framing: 'wide', crop: [0.50, 0.56],
   layers: [
     L('manhole_rim', 24.60, 'fade', 980, 1092, 430, 'front', {tint: 0.06}),
     L('creature_tall', 25.30, 'rise', 980, 1006, 700, 'creature', {tint: 0.26, dur: 0.50, bob: 4}),
   ]},
  {t0: 25.91, t1: 26.93, desc: 'HARD CUT closer: four glossy white legs', plate: 10, framing: 'close', crop: [0.50, 0.66],
   layers: [
     L('manhole_rim', 24.60, 'fade', 980, 1252, 560, 'front', {tint: 0.06}),
     L('creature_tall', 25.30, 'rise', 980, 1092, 1180, 'creature', {tint: 0.22, dur: 0.50, bob: 6, dx: 9}),
   ]},
  {t0: 26.93, t1: 28.50, desc: 'INSERT: one leg against the rim', plate: 10, framing: 'insert', crop: [0.42, 0.70],
   layers: [
     L('manhole_rim', 24.60, 'fade', 900, 1520, 760, 'front', {tint: 0.06}),
     L('creature_tall', 25.30, 'rise', 880, 1300, 1900, 'creature', {tint: 0.18, dur: 0.50, bob: 8, dx: -14}),
   ]},

  // --- 28.5 WHITE CANVAS: scale comparison (the exception) ----------------
  {t0: 28.50, t1: 31.20, desc: 'INFOGRAPHIC: one leg vs one man', plate: 10, framing: 'wide', crop: [0.5, 0.5],
   whiteCanvas: true, layers: [],
   info: {kind: 'grid', heading: 'EACH LEG', items: [
     {t0: 28.50, label: 'ONE LEG', big: '1', cut: 'creature_tall', crop: [0.18, 0.30, 2.1], accent: true},
     {t0: 29.61, label: 'ONE MAN', big: '1', cut: 'figure', crop: [0.5, 0.5, 1.0]},
   ], footer: {text: 'AND THERE ARE FOUR', t0: 30.15}}},

  // --- 31.2 WHITE CANVAS: three joints ------------------------------------
  {t0: 31.20, t1: 34.40, desc: 'INFOGRAPHIC: three separate joints', plate: 10, framing: 'wide', crop: [0.5, 0.5],
   whiteCanvas: true, layers: [],
   info: {kind: 'grid', items: [
     {t0: 31.20, label: 'SHOULDER', big: '1', cut: 'creature_tall', crop: [0.28, 0.34, 2.6]},
     {t0: 32.12, label: 'MID BEND', big: '2', cut: 'creature_tall', crop: [0.15, 0.52, 2.6]},
     {t0: 33.34, label: 'FOOT', big: '3', cut: 'creature_tall', crop: [0.09, 0.76, 2.6], accent: true},
   ]}},

  // --- 34.4 back to the manhole (SAME PLATE 10 reused) --------------------
  {t0: 34.40, t1: 35.73, desc: 'the manhole again, nothing above the rim', plate: 10, framing: 'wide', crop: [0.58, 0.48],
   layers: [L('manhole_rim', 34.40, 'fade', 900, 1060, 400, 'front', {tint: 0.06})]},
  {t0: 35.73, t1: 37.20, desc: 'closer: everything below the rim is black', plate: 10, framing: 'close', crop: [0.42, 0.62],
   layers: [L('manhole_rim', 34.40, 'fade', 940, 1230, 540, 'front', {tint: 0.06})]},

  // --- 37.2 the archive record --------------------------------------------
  {t0: 37.20, t1: 38.84, desc: 'archive record, name field blank', plate: 11, framing: 'wide', crop: [0.50, 0.46], layers: []},
  {t0: 38.84, t1: 40.30, desc: 'INSERT: the empty name field', plate: 11, framing: 'insert', crop: [0.56, 0.40], layers: []},

  // --- 40.3 the fans named it ---------------------------------------------
  {t0: 40.30, t1: 41.47, desc: 'forum thread, replies naming it', plate: 12, framing: 'wide', crop: [0.48, 0.50], layers: []},
  {t0: 41.47, t1: 42.70, desc: 'INSERT: one reply', plate: 12, framing: 'insert', crop: [0.75, 0.80], layers: []},

  // --- 42.7 read it closely -----------------------------------------------
  {t0: 42.70, t1: 43.94, desc: 'the original post', plate: 13, framing: 'wide', crop: [0.52, 0.48], layers: []},
  {t0: 43.94, t1: 45.10, desc: 'INSERT: one line of it', plate: 13, framing: 'insert', crop: [0.16, 0.40], layers: []},

  // --- 45.1 the word ------------------------------------------------------
  {t0: 45.10, t1: 46.54, desc: 'macro on the word', plate: 14, framing: 'wide', crop: [0.50, 0.50], layers: []},
  {t0: 46.54, t1: 47.60, desc: 'INSERT: spiders, plural', plate: 14, framing: 'insert', crop: [0.44, 0.52], layers: []},

  // --- 47.6 PLURAL — three of them rise, one at a time --------------------
  {t0: 47.60, t1: 48.22, desc: 'wide: three manholes, three risings', plate: 15, framing: 'wide', crop: [0.50, 0.54],
   layers: [
     L('manhole_rim', 47.60, 'fade', 400, 1010, 210, 'front', {tint: 0.06}),
     L('manhole_rim', 47.60, 'fade', 960, 1040, 250, 'front', {tint: 0.06}),
     L('manhole_rim', 47.60, 'fade', 1520, 1010, 210, 'front', {tint: 0.06}),
     L('creature_tall', 47.62, 'rise', 400, 960, 430, 'creature', {tint: 0.30, dur: 0.30}),
     L('creature_tall', 47.72, 'rise', 960, 990, 510, 'creature', {tint: 0.28, dur: 0.30}),
     L('creature_tall', 47.82, 'rise', 1520, 960, 450, 'creature', {tint: 0.30, dur: 0.30}),
   ]},
  {t0: 48.22, t1: 49.20, desc: 'HARD CUT closer: two of them', plate: 15, framing: 'close', crop: [0.38, 0.58],
   layers: [
     L('manhole_rim', 47.60, 'fade', 560, 1120, 400, 'front', {tint: 0.06}),
     L('manhole_rim', 47.60, 'fade', 1440, 1090, 360, 'front', {tint: 0.06}),
     L('creature_tall', 47.62, 'rise', 560, 1030, 820, 'creature', {tint: 0.26, dur: 0.30, bob: 6}),
     L('creature_tall', 47.82, 'rise', 1440, 1000, 700, 'creature', {tint: 0.28, dur: 0.30, bob: 5}),
   ]},

  // --- 49.2 WHITE CANVAS: the survival rules (the exception) --------------
  {t0: 49.20, t1: 52.60, desc: 'INFOGRAPHIC: survival rules, one at a time', plate: 16, framing: 'wide', crop: [0.5, 0.5],
   whiteCanvas: true, layers: [],
   info: {kind: 'rules', heading: 'HOW TO SURVIVE', items: [
     {t0: 49.20, label: 'STAY OUT OF STORM DRAINS', icon: 'redx'},
     {t0: 50.95, label: 'KEEP AWAY FROM MANHOLES', icon: 'redx'},
     {t0: 52.06, label: 'ASSUME IT IS NOT ALONE', icon: 'warn', accent: true},
   ]}},

  // --- 52.6 WHITE CANVAS: the cover-off rule ------------------------------
  {t0: 52.60, t1: 55.40, desc: 'INFOGRAPHIC: cover off + no crew', plate: 16, framing: 'wide', crop: [0.5, 0.5],
   whiteCanvas: true, layers: [],
   info: {kind: 'grid', items: [
     {t0: 52.60, label: 'COVER OFF', cut: 'manhole_rim', crop: [0.5, 0.55, 1.1]},
     {t0: 53.87, label: 'NO CREW', cut: 'figure', crop: [0.5, 0.5, 1.0]},
   ], footer: {text: 'CROSS THE STREET', t0: 54.80}}},

  // --- 55.4 the empty street ----------------------------------------------
  {t0: 55.40, t1: 56.74, desc: 'empty street, crossing away from the drain', plate: 16, framing: 'wide', crop: [0.46, 0.54],
   layers: [
     L('figure', 55.60, 'slideL', 760, 1006, 360, 'mid', {tint: 0.22, dx: 26}),
     L('car', 55.40, 'fade', 1560, 1064, 340, 'front', {tint: 0.10}),
   ]},
  {t0: 56.74, t1: 57.90, desc: 'closer: not looking back', plate: 16, framing: 'close', crop: [0.60, 0.60],
   layers: [L('figure', 55.60, 'slideL', 700, 1084, 560, 'mid', {tint: 0.20, dx: 34})]},

  // --- 57.9 road closed ---------------------------------------------------
  {t0: 57.90, t1: 59.03, desc: 'municipal ROAD CLOSED sign, daylight routine', plate: 17, framing: 'wide', crop: [0.46, 0.48],
   layers: [L('car', 58.10, 'slideR', 1430, 1020, 320, 'mid', {tint: 0.14})]},
  {t0: 59.03, t1: 60.30, desc: 'closer: MAINTENANCE, no detail', plate: 17, framing: 'close', crop: [0.58, 0.42], layers: []},

  // --- 60.3 the same sign at night (SAME PLATE 17, red grade) -------------
  {t0: 60.30, t1: 61.28, desc: 'the same sign at night, the cover already off', plate: 17, framing: 'wide', crop: [0.54, 0.56],
   grade: 'red',
   layers: [
     L('manhole_rim', 60.30, 'fade', 760, 1076, 360, 'front', {tint: 0.08}),
     L('creature_tall', 60.60, 'rise', 740, 1010, 560, 'creature', {tint: 0.17, tintColor: S.RED, dur: 0.44, bob: 5}),
   ]},
  {t0: 61.28, t1: 62.60, desc: 'HARD CUT closer: it is already out', plate: 17, framing: 'close', crop: [0.40, 0.64],
   grade: 'red',
   layers: [
     L('manhole_rim', 60.30, 'fade', 700, 1230, 520, 'front', {tint: 0.08}),
     L('creature_tall', 60.60, 'rise', 800, 1100, 900, 'creature', {tint: 0.15, tintColor: S.RED, dur: 0.44, bob: 8, dx: -8}),
   ]},
];

export const SHOTS: Shot[] = RAW.map((s, i) => ({...s, seed: i * 977 + 13}));

// ---------------------------------------------------------------------------
// KEYWORD POPS — keywords, never sentences (<=3 words, <=22 chars).
// Texts and times are unchanged from the previous cut; only placement moved.
// ---------------------------------------------------------------------------
const RAW_POPS: [string, number, number, PopAnchorX, PopAnchorY, boolean, number][] = [
  ['Not alligators',    12.05, 1.95, 'l', 'mid',  false, 74],
  ['Spiders',           14.20, 2.40, 'c', 'high', true,  116],
  ['Former city worker',19.60, 2.10, 'r', 'mid',  false, 60],
  ['4 legs',            25.95, 2.00, 'l', 'head', true,  96],
  ['3 joints',          31.65, 2.10, 'c', 'head', true,  84],
  ['Body never seen',   35.90, 2.00, 'r', 'mid',  false, 64],
  ['Name: fan-coined',  40.80, 2.00, 'l', 'mid',  false, 60],
  ['Plural',            47.90, 1.30, 'c', 'high', true,  116],
  ['No open manholes',  52.10, 2.20, 'c', 'head', true,  60],
];
export const POPS: Pop[] = RAW_POPS.map(([text, t0, dur, ax, ay, accent, size]) => ({
  text, t0, t1: t0 + dur, ax, ay, accent, size,
}));

// ---------------------------------------------------------------------------
// CAPTION LAYER — always on. Back-to-back, so no frame is ever text-free.
// Sits in the dead space along the bottom of the frame; pops sit above it.
// ---------------------------------------------------------------------------
const RAW_CAPS: [string, number, number, PopAnchorX, boolean?][] = [
  ['Unverified',            0.00,  2.30, 'c'],
  ['First week under',      2.30,  4.20, 'l'],
  ['New city worker',       4.20,  6.20, 'l'],
  ['Alligators?',           6.20,  8.00, 'c'],
  ['He joked',              8.00, 10.00, 'r'],
  ['The laugh stopped',    10.00, 12.02, 'c'],
  ['His answer',           12.02, 14.20, 'r'],
  ['He meant it',          14.20, 15.80, 'r'],
  ['Word for word',        15.80, 17.60, 'l'],
  ['A forum post',         17.60, 19.60, 'c'],
  ['Testimony',            19.60, 21.80, 'l'],
  ['He knew',              21.80, 24.64, 'c'],
  ['One photo',            24.64, 26.60, 'r'],
  ['Glossy white legs',    26.60, 28.50, 'r'],
  ['Longer than a man',    28.50, 31.20, 'c'],
  ['Fine spikes',          31.20, 34.40, 'c'],
  ['No body',              34.40, 37.20, 'l'],
  ['No official name',     37.20, 40.30, 'c'],
  ['Fans named it',        40.30, 42.70, 'r'],
  ['Read it closely',      42.70, 45.10, 'l'],
  ['Never one',            45.10, 47.60, 'c'],
  ['He says spiders',      47.60, 49.20, 'r', true],
  ['Rules',                49.20, 52.60, 'c'],
  ['A cover is off',     52.60, 55.40, 'c'],
  ['Cross the street',     55.40, 57.90, 'l'],
  ['Road closed',          57.90, 60.30, 'r'],
  ["Don't ask what kind",  60.30, 62.60, 'c'],
];
export const CAPTIONS: Caption[] = RAW_CAPS.map(([text, t0, t1, ax, accent]) => ({
  text, t0, t1, ax, accent: Boolean(accent),
}));

// ---------------------------------------------------------------------------
// Free-standing icons over cinematic frames (the infographic icon lists live
// inside their own shot's info.items and pop ONE AT A TIME).
// ---------------------------------------------------------------------------
const RAW_ICONS: [IconKind, number, number, number, number, number][] = [
  ['redx',  12.30, 14.10, 1430, 430, 260],
  ['arrow', 27.05, 28.40, 1420, 560, 220],
];
export const ICONS: Icon[] = RAW_ICONS.map(([kind, t0, t1, x, y, size]) => ({kind, t0, t1, x, y, size}));

export const SHAKES: Burst[] = [
  {t0: 14.25, dur: 0.34, amp: 18},
  {t0: 25.95, dur: 0.38, amp: 22},
  {t0: 47.95, dur: 0.32, amp: 20},
  {t0: 60.62, dur: 0.26, amp: 14},
];

export const GLITCHES: Burst[] = [
  {t0: 14.20, dur: 0.28, amp: 18},
  {t0: 47.90, dur: 0.22, amp: 14},
  {t0: 60.50, dur: 0.20, amp: 10},
];
