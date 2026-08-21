import _sodium from 'libsodium-wrappers';

/**
 * libsodium is a WASM module that must finish initialising before use. Every
 * entry point in this package awaits this once; callers never touch the raw
 * module.
 *
 * Everything here uses libsodium's own primitives. There is no custom
 * cryptography in this codebase, and there must never be.
 */
export type Sodium = typeof _sodium;

let ready: Promise<Sodium> | null = null;

export function sodiumReady(): Promise<Sodium> {
  ready ??= _sodium.ready.then(() => _sodium);
  return ready;
}

/**
 * Best-effort zeroing of a mutable byte array.
 *
 * This works because Uint8Array contents are mutable. It does NOT extend to
 * JavaScript strings, which are immutable and garbage-collected: a secret that
 * has been a string cannot be wiped by any means available to us. Where a
 * string is unavoidable (a DOM input value), the honest mitigation is to
 * shorten its lifetime, not to claim it was erased.
 */
export async function wipe(...arrays: Array<Uint8Array | null | undefined>): Promise<void> {
  const sodium = await sodiumReady();
  for (const array of arrays) {
    if (array && array.length > 0) sodium.memzero(array);
  }
}

/** Synchronous variant for paths that already hold an initialised module. */
export function wipeWith(sodium: Sodium, ...arrays: Array<Uint8Array | null | undefined>): void {
  for (const array of arrays) {
    if (array && array.length > 0) sodium.memzero(array);
  }
}
