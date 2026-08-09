/**
 * BUILD-TIME VALIDATOR. Runs on import (Root.tsx pulls it in), so a sheet that
 * breaks a house rule FAILS THE RENDER — it does not warn.
 *
 * Rules encoded here, all of them hard failures:
 *   1. shots are contiguous and every referenced plate slot exists
 *   2. HARD CAP 4.0s on one unchanged frame (the old 8s figure is dead)
 *   3. no frame is ever text-free: every frame carries the title PLUS at least
 *      a caption or a pop
 *   4. no blank text-only cards — a frame is never type on empty canvas
 *   5. pops are KEYWORDS: <=3 words, <=22 chars. Captions too.
 *   6. icon lists pop ONE AT A TIME, never pre-assembled
 *   7. multi-image layouts are a 2-up or 3-up grid, equal size, equal border
 *   8. the corners stay EMPTY (the grey animatic slot tag is the only exempt
 *      element and it is not routed through here)
 *   9. the white-canvas treatment is the EXCEPTION, not half the section
 */
import * as S from '../style';
import {
  CAPTIONS, DURATION, ICONS, PLATES, POPS, ROSTER, SHAKES, SHOTS,
} from '../sheet';
import {capBox, inCorner, popBox} from './layout';

const MAX_STATIC = 4.0;
const MAX_POP_WORDS = 3;
const MAX_POP_CHARS = 22;
const WHITE_CANVAS_MAX_FRACTION = 0.45;

export const validateSheet = (): string[] => {
  const errs: string[] = [];
  const F = 1 / S.FPS;

  // -- 1. structure -------------------------------------------------------
  if (Math.abs(SHOTS[0].t0 - ROSTER.t1) > 1e-6) {
    errs.push(`cold open ends at ${ROSTER.t1} but first shot starts at ${SHOTS[0].t0}`);
  }
  SHOTS.forEach((s, i) => {
    if (s.t1 <= s.t0) errs.push(`shot ${i} has non-positive length`);
    if (i > 0 && Math.abs(SHOTS[i - 1].t1 - s.t0) > 1e-6) {
      errs.push(`gap/overlap between shot ${i - 1} (${SHOTS[i - 1].t1}) and ${i} (${s.t0})`);
    }
    if (!s.whiteCanvas && !PLATES[s.plate]) errs.push(`shot ${i} references unknown plate slot ${s.plate}`);
  });
  if (Math.abs(SHOTS[SHOTS.length - 1].t1 - DURATION) > 1e-6) {
    errs.push(`last shot ends at ${SHOTS[SHOTS.length - 1].t1}, section is ${DURATION}`);
  }

  // -- 2. hard 4.0s cap on one unchanged frame ----------------------------
  SHOTS.forEach((s, i) => {
    const len = s.t1 - s.t0;
    if (len > MAX_STATIC + 1e-6) errs.push(`shot ${i} is ${len.toFixed(2)}s (>${MAX_STATIC}s hard cap)`);
  });
  const events = new Set<number>([ROSTER.t0, DURATION]);
  SHOTS.forEach((s) => {
    events.add(s.t0);
    s.layers.forEach((l) => events.add(Math.max(l.t0, s.t0)));
    s.info?.items.forEach((it) => events.add(it.t0));
    if (s.info?.footer) events.add(s.info.footer.t0);
  });
  POPS.forEach((p) => events.add(p.t0));
  CAPTIONS.forEach((c) => events.add(c.t0));
  ICONS.forEach((i) => events.add(i.t0));
  SHAKES.forEach((k) => events.add(k.t0));
  const ev = [...events].sort((a, b) => a - b);
  for (let i = 1; i < ev.length; i++) {
    const gap = ev[i] - ev[i - 1];
    if (gap > MAX_STATIC + 1e-6) {
      errs.push(`${gap.toFixed(2)}s with nothing changing on screen, t=${ev[i - 1].toFixed(2)}-${ev[i].toFixed(2)} (>${MAX_STATIC}s hard cap)`);
    }
  }

  // -- 3. always-on text layer -------------------------------------------
  const bare: number[] = [];
  for (let f = 0; f < Math.round(DURATION * S.FPS); f++) {
    const t = f * F;
    const hasCap = CAPTIONS.some((c) => t >= c.t0 && t < c.t1);
    const hasPop = POPS.some((p) => t >= p.t0 && t < p.t1);
    if (!hasCap && !hasPop) bare.push(t);
  }
  if (bare.length) {
    const a = bare[0];
    const b = bare[bare.length - 1];
    errs.push(`${bare.length} frames carry neither a caption nor a pop alongside the title (first ${a.toFixed(2)}s, last ${b.toFixed(2)}s)`);
  }

  // -- 4. no blank text-only cards ---------------------------------------
  SHOTS.forEach((s, i) => {
    if (s.whiteCanvas) {
      if (!s.info || s.info.items.length === 0) {
        errs.push(`shot ${i} is a white-canvas frame with no infographic content — that is a blank text-only card`);
      } else if (s.info.items[0].t0 > s.t0 + 1e-6) {
        errs.push(
          `shot ${i} shows an empty white canvas from ${s.t0.toFixed(2)}s to ${s.info.items[0].t0.toFixed(2)}s ` +
            '— a heading over nothing is still a blank text-only card',
        );
      }
    } else if (!PLATES[s.plate]) {
      errs.push(`shot ${i} has no background image`);
    }
  });

  // -- 5. pops and captions are keywords ---------------------------------
  const keyword = (label: string, txt: string, maxWords: number) => {
    const words = txt.trim().split(/\s+/).length;
    if (words > maxWords) errs.push(`${label} ${JSON.stringify(txt)} is ${words} words (max ${maxWords}) — pops are keywords, not sentences`);
    if (txt.length > MAX_POP_CHARS) errs.push(`${label} ${JSON.stringify(txt)} is ${txt.length} chars (max ${MAX_POP_CHARS})`);
  };
  POPS.forEach((p) => keyword('pop', p.text, MAX_POP_WORDS));
  CAPTIONS.forEach((c) => keyword('caption', c.text, 4));
  POPS.forEach((p, i) => {
    if (p.t1 <= p.t0) errs.push(`pop ${i} has non-positive duration`);
  });

  // -- 6. icon lists pop one at a time -----------------------------------
  SHOTS.forEach((s, i) => {
    const ts = (s.info?.items ?? []).map((it) => it.t0);
    for (let k = 1; k < ts.length; k++) {
      if (ts[k] - ts[k - 1] < 0.25) {
        errs.push(`shot ${i} info items ${k - 1}/${k} appear together (${ts[k - 1]}, ${ts[k]}) — lists pop ONE AT A TIME`);
      }
    }
    if (ts.length && ts[0] < s.t0 - 1e-6) errs.push(`shot ${i} info item starts before the shot`);
  });
  for (let k = 1; k < ICONS.length; k++) {
    if (Math.abs(ICONS[k].t0 - ICONS[k - 1].t0) < 0.25 && ICONS[k].t1 > ICONS[k - 1].t0) {
      errs.push(`icons ${k - 1}/${k} appear pre-assembled at ${ICONS[k].t0}`);
    }
  }

  // -- 7. multi-image layouts are 2-up or 3-up ---------------------------
  SHOTS.forEach((s, i) => {
    if (s.info?.kind === 'grid' && ![2, 3].includes(s.info.items.length)) {
      errs.push(`shot ${i} grid is ${s.info.items.length}-up (must be 2-up or 3-up, equal size, equal border)`);
    }
  });

  // -- 8. corners stay empty ---------------------------------------------
  POPS.forEach((p) => {
    if (inCorner(popBox(p.ax, p.ay, p.text, p.size))) errs.push(`pop ${JSON.stringify(p.text)} lands in a frame corner`);
  });
  CAPTIONS.forEach((c) => {
    if (inCorner(capBox(c.ax, c.text))) errs.push(`caption ${JSON.stringify(c.text)} lands in a frame corner`);
  });
  ICONS.forEach((ic, i) => {
    const r = {l: ic.x - ic.size / 2, t: ic.y - ic.size / 2, w: ic.size, h: ic.size};
    if (inCorner(r)) errs.push(`icon ${i} (${ic.kind}) lands in a frame corner`);
  });

  // -- 9. white canvas is the exception ----------------------------------
  const wc = SHOTS.filter((s) => s.whiteCanvas).reduce((a, s) => a + (s.t1 - s.t0), 0);
  const frac = wc / DURATION;
  if (frac > WHITE_CANVAS_MAX_FRACTION) {
    errs.push(`white-canvas frames are ${(frac * 100).toFixed(0)}% of the section — they are the exception, not half of it`);
  }

  return errs;
};

export const assertSheet = () => {
  const errs = validateSheet();
  if (errs.length) {
    throw new Error(
      `EDIT SHEET FAILED VALIDATION (${errs.length} error${errs.length > 1 ? 's' : ''}):\n  - ` +
        errs.join('\n  - '),
    );
  }
};
