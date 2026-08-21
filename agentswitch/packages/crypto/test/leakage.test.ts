import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { join } from 'node:path';
import { EnvelopeRelay } from '@agentswitch/relay-core';
import {
  WorkerKeyPin,
  createWorkerContext,
  encodePublicKey,
  fingerprintPublicKey,
  generateWorkerKeyPair,
  receiveEnvelope,
  sealCredential,
  sodiumReady,
  type WorkerKeyPair,
} from '@agentswitch/crypto';

/**
 * The canary is defined here, in a test file, and injected into the worker at
 * runtime. It therefore cannot legitimately appear in any shipped source file
 * or build artifact, which is what makes the scans below meaningful.
 */
const CANARY = 'AGENTSWITCH-CANARY-7b2e19f4c6a80d35-NEVER-IN-OUTPUT';
const WORKER_ID = 'worker-leak-1';
const T0 = new Date('2026-08-21T12:00:00.000Z');
const REPO_ROOT = fileURLToPath(new URL('../../../', import.meta.url));

let keyPair: WorkerKeyPair;
let fingerprint: string;
let publicKeyB64: string;

beforeAll(async () => {
  await sodiumReady();
  keyPair = await generateWorkerKeyPair();
  fingerprint = await fingerprintPublicKey(keyPair.publicKey);
  publicKeyB64 = await encodePublicKey(keyPair.publicKey);
});

afterEach(() => vi.restoreAllMocks());

function newRelay() {
  const relay = new EnvelopeRelay({ now: () => T0 });
  relay.registerWorker({
    workerId: WORKER_ID,
    displayName: 'Leak Test Worker',
    publicKey: publicKeyB64,
    fingerprint,
  });
  return relay;
}

async function sealCanary() {
  const secret = new TextEncoder().encode(CANARY);
  return sealCredential({
    secret,
    recipientPublicKey: keyPair.publicKey,
    destinationWorkerId: WORKER_ID,
    workerKeyFingerprint: fingerprint,
    provider: 'codex',
    credentialType: 'test-value',
    now: T0,
  });
}

describe('end-to-end: browser -> relay -> worker', () => {
  it('delivers, verifies, and deletes the ciphertext on acknowledgement', async () => {
    const relay = newRelay();
    const context = createWorkerContext(WORKER_ID, fingerprint, keyPair, CANARY);

    const envelope = await sealCanary();
    expect(relay.submit(envelope).ok).toBe(true);

    // Everything the relay is holding, at the moment it holds it.
    const held = JSON.stringify(relay.storedEnvelopes());
    expect(held).not.toContain(CANARY);
    expect(held).toContain(envelope.ciphertext);

    const [fetched] = relay.fetchFor(WORKER_ID);
    expect(fetched).toBeDefined();

    const receipt = await receiveEnvelope(context, fetched, new Date(T0.getTime() + 500));
    expect(receipt.ok).toBe(true);
    expect(receipt.canaryMatched).toBe(true);

    expect(relay.acknowledge(receipt.envelopeId, WORKER_ID, receipt)).toBe(true);
    expect(relay.pendingCount).toBe(0);
    expect(relay.storedEnvelopes()).toEqual([]);
    expect(JSON.stringify(relay.receipt(receipt.envelopeId))).not.toContain(CANARY);
  });

  it('never writes the canary to any console channel during the whole flow', async () => {
    const captured: string[] = [];
    for (const channel of ['log', 'info', 'warn', 'error', 'debug'] as const) {
      vi.spyOn(console, channel).mockImplementation((...args: unknown[]) => {
        captured.push(args.map((a) => String(a)).join(' '));
      });
    }

    const relay = newRelay();
    const context = createWorkerContext(WORKER_ID, fingerprint, keyPair, CANARY);
    const envelope = await sealCanary();
    relay.submit(envelope);
    const receipt = await receiveEnvelope(
      context,
      relay.fetchFor(WORKER_ID)[0],
      new Date(T0.getTime() + 500),
    );
    relay.acknowledge(receipt.envelopeId, WORKER_ID, receipt);

    expect(captured.join('\n')).not.toContain(CANARY);
  });

  it('surfaces the canary in no error thrown along the way', async () => {
    const relay = newRelay();
    const context = createWorkerContext(WORKER_ID, fingerprint, keyPair, CANARY);
    const envelope = await sealCanary();

    // Force every failure branch and inspect what comes back out.
    const results = [
      relay.submit({ ...envelope, ciphertext: 'not-base64!!' }),
      relay.submit({ ...envelope, destinationWorkerId: 'nope' }),
      relay.submit(envelope),
      relay.submit(envelope),
    ];
    const receipts = [
      await receiveEnvelope(context, { ...envelope, v: 99 }, T0),
      await receiveEnvelope(context, { ...envelope, credentialType: 'api-key' }, T0),
      await receiveEnvelope(context, envelope, new Date(T0.getTime() + 10 * 60_000)),
    ];

    const everything = JSON.stringify({ results, receipts });
    expect(everything).not.toContain(CANARY);
  });
});

describe('worker key pinning', () => {
  const worker = (publicKey: string) => ({
    workerId: WORKER_ID,
    publicKey,
    fingerprint,
  });

  it('starts unconfirmed and blocks until a human confirms', () => {
    const pin = new WorkerKeyPin();
    expect(pin.status(worker(publicKeyB64))).toBe('unconfirmed');
    pin.confirm(worker(publicKeyB64));
    expect(pin.status(worker(publicKeyB64))).toBe('confirmed');
  });

  it('does not silently accept a changed key', () => {
    const pin = new WorkerKeyPin();
    pin.confirm(worker(publicKeyB64));

    // Same worker id, different key: a substituted key must not inherit trust.
    expect(pin.status(worker('c29tZS1vdGhlci1rZXk='))).toBe('key_changed');
  });

  it('requires fresh confirmation after a key change', () => {
    const pin = new WorkerKeyPin();
    pin.confirm(worker(publicKeyB64));
    const rotated = 'cm90YXRlZC1rZXktYnl0ZXM=';

    expect(pin.status(worker(rotated))).toBe('key_changed');
    pin.confirm(worker(rotated));
    expect(pin.status(worker(rotated))).toBe('confirmed');
    // And the old key is no longer trusted.
    expect(pin.status(worker(publicKeyB64))).toBe('key_changed');
  });
});

/* ------------------------------------------------------------------ *
 * Static guarantees about the control plane.
 * ------------------------------------------------------------------ */

function walk(dir: string): string[] {
  let out: string[] = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) out = out.concat(walk(full));
    else out.push(full);
  }
  return out;
}

function exists(path: string): boolean {
  try {
    statSync(path);
    return true;
  } catch {
    return false;
  }
}

describe('control plane has no ability to decrypt', () => {
  const source = readFileSync(join(REPO_ROOT, 'apps/control-plane/src/server.ts'), 'utf8');

  it('imports no cryptography and references no private key', () => {
    for (const forbidden of [
      'libsodium',
      '@agentswitch/crypto',
      'crypto_box_seal_open',
      'privateKey',
      'openEnvelope',
      'node:crypto',
    ]) {
      expect(source).not.toContain(forbidden);
    }
  });

  it('depends on no package that can decrypt', () => {
    const pkg = JSON.parse(
      readFileSync(join(REPO_ROOT, 'apps/control-plane/package.json'), 'utf8'),
    ) as { dependencies?: Record<string, string> };

    expect(Object.keys(pkg.dependencies ?? {})).not.toContain('@agentswitch/crypto');
    expect(Object.keys(pkg.dependencies ?? {})).not.toContain('libsodium-wrappers');
  });

  it('never passes a request or response body to a console call', () => {
    // Static text in a log line cannot leak anything; only the *expressions*
    // a log call evaluates can. So strip every string literal, keep the
    // template interpolations, and check what is actually being printed.
    const calls = source.match(/console\.(?:log|info|warn|error|debug)\([\s\S]*?\);/g) ?? [];
    expect(calls.length).toBeGreaterThan(0);

    for (const call of calls) {
      const interpolations = (call.match(/\$\{[^}]*\}/g) ?? []).join(' ');
      const bareArguments = call
        .replace(/`[\s\S]*?`/g, '')
        .replace(/'(?:[^'\\]|\\.)*'/g, '')
        .replace(/"(?:[^"\\]|\\.)*"/g, '');
      const evaluated = `${interpolations} ${bareArguments}`;

      expect(evaluated, `leaky console call: ${call}`).not.toMatch(
        /body|ciphertext|receipt|envelope|payload|\bvalue\b|secret|token/i,
      );
    }
  });

  it('logs only method, path, status and byte count in the request path', () => {
    expect(source).toContain('`${method} ${path} -> ${res.statusCode} (${bytes}b out)`');
  });
});

describe('build artifacts', () => {
  it('contain no canary value', () => {
    const dists = ['apps/web/dist', 'apps/control-plane/dist', 'packages/crypto/dist']
      .map((d) => join(REPO_ROOT, d))
      .filter(exists);

    // Not a silent pass: if nothing has been built, say so rather than
    // reporting a clean scan of zero files.
    expect(dists.length, 'run `npm run build` before this test to scan artifacts')
      .toBeGreaterThan(0);

    for (const dist of dists) {
      for (const file of walk(dist)) {
        expect(readFileSync(file, 'utf8').includes(CANARY), `canary found in ${file}`).toBe(false);
      }
    }
  });
});
