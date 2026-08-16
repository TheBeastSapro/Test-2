/**
 * House style constants.
 *
 * REBUILD 2026-08-08 — the default treatment changed. The scene now FILLS the
 * 1920x1080 frame and is composited from layers (background plate + cutouts).
 * The white-canvas boxed treatment is the EXCEPTION, reserved for infographic
 * beats (numbers, size comparisons, icon lists). Client: "cinematic-integrated,
 * M Simplified-leaning, not busy-white-canvas Ficknime".
 *
 * Palette is strictly black / white / ONE red. Nothing else.
 */
export const W = 1920;
export const H = 1080;
export const FPS = 30;

export const WHITE = '#FFFFFF';
export const BLACK = '#111111';
export const RED = '#D62020';
export const GREY = '#969696';

/** Backing colour behind a full-frame composited scene. */
export const SCENE_BG = '#0A0A0C';
/** Canvas colour for the white-canvas infographic exception. */
export const CANVAS = WHITE;

// ---------------------------------------------------------------------------
// Frame geometry
// ---------------------------------------------------------------------------
export const SAFE = 96;                 // keep type this far off the frame edge
/** Corners stay EMPTY. Nothing but the grey animatic slot tag may enter these. */
export const CORNER_W = 220;
export const CORNER_H = 170;

/** Type may only live inside this rect. Enforced by clamp AND by the validator. */
export const TYPE_L = 250;
export const TYPE_R = W - 250;
export const TYPE_T = 190;
export const TYPE_B = H - 118;

// ---------------------------------------------------------------------------
// Shot framing — a "cut closer" is a HARD CUT to a different crop of the same
// plate, never a zoom. Each framing is a different scale + anchor on the plate.
// `travel` is the Ken Burns scale travel across the sub-shot (constant velocity).
// ---------------------------------------------------------------------------
export const FRAMING = {
  wide: {scale: 1.06, travel: 0.19, lateral: 0.16},
  close: {scale: 1.70, travel: 0.13, lateral: 0.12},
  insert: {scale: 2.25, travel: 0.10, lateral: 0.09},
} as const;
export type FramingName = keyof typeof FRAMING;

/** cut punch — a fast scale overshoot on the head of every shot so a cut reads
 *  as a CUT, not a dissolve. */
export const PUNCH_AMT = 0.055;
export const PUNCH_DUR = 0.28;

// source plate dimensions (engine/plates.py, bumped for the close/insert crops)
export const PLATE_W = 2600;
export const PLATE_H = 1600;

// ---------------------------------------------------------------------------
// Layer language
// ---------------------------------------------------------------------------
export const LAYER_ENTRY_DUR = 0.46;    // fast. "I should SEE it move."
export const Z = {back: 10, mid: 20, creature: 30, front: 40} as const;
/** Atmospheric perspective: how much scene haze is mixed into a layer by depth. */
export const HAZE = {back: 0.26, mid: 0.12, creature: 0.06, front: 0.0} as const;
/** Foreground elements are the darkest thing in a real composite — without this
 *  a `front` occluder sits at the same value as the plate and stops reading. */
export const DARKEN = {back: 0.0, mid: 0.0, creature: 0.06, front: 0.42} as const;
export const HAZE_COLOR = '#20262F';

// ---------------------------------------------------------------------------
// Persistent title — on EVERY frame, top-centre.
// ---------------------------------------------------------------------------
export const TITLE_SIZE = 72;
export const TITLE_Y = 40;
export const TITLE_TRACK = 4;
export const TITLE_RULE_Y = 134;
export const TITLE_RULE_H = 8;
export const TITLE_STROKE = 12;         // black stroke behind the white fill
export const TITLE_SCRIM_H = 260;       // subtle top scrim on cinematic frames

// ---------------------------------------------------------------------------
// Text layers
// ---------------------------------------------------------------------------
export const POP_IN_DUR = 0.20;
export const POP_OUT_DUR = 0.16;

export const CAP_SIZE = 46;
export const CAP_IN_DUR = 0.16;
export const CAP_OUT_DUR = 0.14;
/** Caption band: the dead space along the bottom of the frame. NOT a band under
 *  a box — there is no box any more. */
export const CAP_Y = 916;
export const CAP_X = {l: 620, c: 960, r: 1300} as const;

/** Pop anchors live in mid-frame dead space, well clear of the caption band. */
export const POP_Y = {head: 194, high: 330, mid: 505, low: 660} as const;
export const POP_X = {l: 640, c: 960, r: 1280} as const;

// ---------------------------------------------------------------------------
// White-canvas infographic exception
// ---------------------------------------------------------------------------
export const INFO_HEAD_Y = 214;
export const INFO_HEAD_SIZE = 62;
export const INFO_GRID_T = 326;
export const INFO_GRID_H = 396;
export const INFO_GRID_W = 1480;        // total width of the 2-up / 3-up grid
export const INFO_GAP = 40;
export const INFO_BORDER = 6;           // EQUAL border on every panel
export const INFO_RADIUS = 14;
export const INFO_LABEL_SIZE = 34;

export const FONT = {
  title: 'Anton',
  pop: 'ArchivoBlack',
  card: 'Bangers',
  body: 'Inter',
} as const;

// legacy names kept so nothing downstream silently reads undefined
export const POP_SIZE = 58;
