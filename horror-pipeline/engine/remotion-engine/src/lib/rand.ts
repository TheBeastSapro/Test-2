/** Deterministic PRNG so Ken Burns anchors are identical on every render/machine. */
export const mulberry32 = (a: number) => {
  let t = a >>> 0;
  return () => {
    t = (t + 0x6d2b79f5) >>> 0;
    let x = Math.imul(t ^ (t >>> 15), 1 | t);
    x = (x + Math.imul(x ^ (x >>> 7), 61 | x)) ^ x;
    return ((x ^ (x >>> 14)) >>> 0) / 4294967296;
  };
};

export const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v));
