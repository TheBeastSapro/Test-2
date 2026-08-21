import { sodiumReady } from './sodium.js';

/**
 * A worker's X25519 key pair.
 *
 * The private key lives in this process's memory as an ordinary Uint8Array.
 * It is not hardware-backed, not OS-protected, and not "non-exportable" - any
 * code running in this process can read it, and so can anything that can read
 * the process's memory. Persistent OS-level protection (DPAPI / Windows
 * Credential Manager) is Milestone 2B. Until then, a worker restart means a
 * new identity and a new fingerprint confirmation, which is the intended
 * behaviour for a development milestone.
 */
export interface WorkerKeyPair {
  publicKey: Uint8Array;
  privateKey: Uint8Array;
}

export async function generateWorkerKeyPair(): Promise<WorkerKeyPair> {
  const sodium = await sodiumReady();
  const pair = sodium.crypto_box_keypair();
  return { publicKey: pair.publicKey, privateKey: pair.privateKey };
}

/**
 * A human-comparable fingerprint of the canonical public-key bytes.
 *
 * BLAKE2b-256 over the raw 32-byte key, truncated to 128 bits and grouped for
 * reading aloud. Truncation is safe here: an attacker must find a second key
 * matching a specific fingerprint, which is a 2^128 problem, not a birthday
 * problem.
 */
export async function fingerprintPublicKey(publicKey: Uint8Array): Promise<string> {
  const sodium = await sodiumReady();
  // Unkeyed BLAKE2b-256 over the raw public key bytes.
  const digest = sodium.crypto_generichash(32, publicKey, null);
  const hex = sodium.to_hex(digest.subarray(0, 16)).toUpperCase();
  return (hex.match(/.{4}/g) ?? []).join('-');
}

export async function encodePublicKey(publicKey: Uint8Array): Promise<string> {
  const sodium = await sodiumReady();
  return sodium.to_base64(publicKey, sodium.base64_variants.ORIGINAL);
}

export async function decodePublicKey(encoded: string): Promise<Uint8Array> {
  const sodium = await sodiumReady();
  return sodium.from_base64(encoded, sodium.base64_variants.ORIGINAL);
}
