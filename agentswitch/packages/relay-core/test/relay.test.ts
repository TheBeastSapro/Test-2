import { describe, expect, it } from 'vitest';
import { MAX_ENVELOPE_JSON_BYTES, type DeliveryReceipt } from '@agentswitch/contracts';
import { EnvelopeRelay } from '@agentswitch/relay-core';

const T0 = new Date('2026-08-21T12:00:00.000Z');

function makeRelay(clock = { now: T0 }) {
  const relay = new EnvelopeRelay({ now: () => clock.now });
  relay.registerWorker({
    workerId: 'worker-1',
    displayName: 'Worker One',
    publicKey: 'cHVibGljLWtleS1ieXRlcw==',
    fingerprint: 'AAAA-BBBB-CCCC-DDDD',
  });
  return { relay, clock };
}

const envelope = (overrides: Record<string, unknown> = {}) => ({
  v: 1,
  envelopeId: 'envelope-0000000001',
  destinationWorkerId: 'worker-1',
  workerKeyFingerprint: 'AAAA-BBBB-CCCC-DDDD',
  provider: 'codex',
  credentialType: 'test-value',
  replayNonce: 'nonce-0123456789abcdef',
  createdAt: T0.toISOString(),
  expiresAt: new Date(T0.getTime() + 60_000).toISOString(),
  ciphertext: 'c2VhbGVkLWNpcGhlcnRleHQ=',
  ...overrides,
});

const receipt = (envelopeId: string): DeliveryReceipt => ({
  envelopeId,
  ok: true,
  workerId: 'worker-1',
  provider: 'codex',
  credentialType: 'test-value',
  canaryMatched: true,
  failure: null,
  receivedAt: T0.toISOString(),
});

describe('relay: what it stores', () => {
  it('stores only routing metadata and opaque ciphertext', () => {
    const { relay } = makeRelay();
    relay.submit(envelope());

    const stored = relay.storedEnvelopes();
    expect(stored).toHaveLength(1);
    expect(Object.keys(stored[0]!).sort()).toEqual([
      'ciphertext',
      'createdAt',
      'credentialType',
      'destinationWorkerId',
      'envelopeId',
      'expiresAt',
      'provider',
      'replayNonce',
      'v',
      'workerKeyFingerprint',
    ]);
  });

  it('has no decrypt capability on its public surface', () => {
    const { relay } = makeRelay();
    const surface = [
      ...Object.getOwnPropertyNames(Object.getPrototypeOf(relay)),
      ...Object.keys(relay),
    ].join(' ');

    for (const forbidden of ['decrypt', 'open', 'seal', 'privateKey', 'unseal']) {
      expect(surface.toLowerCase()).not.toContain(forbidden);
    }
  });

  it('only hands an envelope to the worker it is addressed to', () => {
    const { relay } = makeRelay();
    relay.registerWorker({
      workerId: 'worker-2',
      displayName: 'Worker Two',
      publicKey: 'b3RoZXIta2V5',
      fingerprint: 'EEEE-FFFF-0000-1111',
    });
    relay.submit(envelope());

    expect(relay.fetchFor('worker-1')).toHaveLength(1);
    expect(relay.fetchFor('worker-2')).toHaveLength(0);
  });
});

describe('relay: lifecycle', () => {
  it('deletes the ciphertext on acknowledgement', () => {
    const { relay } = makeRelay();
    relay.submit(envelope());
    expect(relay.pendingCount).toBe(1);

    expect(relay.acknowledge('envelope-0000000001', 'worker-1', receipt('envelope-0000000001')))
      .toBe(true);

    expect(relay.pendingCount).toBe(0);
    expect(relay.storedEnvelopes()).toEqual([]);
    expect(relay.fetchFor('worker-1')).toEqual([]);
    // What remains is non-secret metadata only.
    expect(relay.receipt('envelope-0000000001')?.ok).toBe(true);
  });

  it('will not let another worker acknowledge someone else\'s envelope', () => {
    const { relay } = makeRelay();
    relay.submit(envelope());
    expect(relay.acknowledge('envelope-0000000001', 'worker-2', receipt('envelope-0000000001')))
      .toBe(false);
    expect(relay.pendingCount).toBe(1);
  });

  it('deletes expired ciphertext even if nobody collected it', () => {
    const { relay, clock } = makeRelay();
    relay.submit(envelope());
    expect(relay.pendingCount).toBe(1);

    clock.now = new Date(T0.getTime() + 61_000);
    expect(relay.sweep()).toBe(1);
    expect(relay.pendingCount).toBe(0);
    expect(relay.storedEnvelopes()).toEqual([]);
  });

  it('refuses an envelope id that has already been delivered', () => {
    const { relay } = makeRelay();
    relay.submit(envelope());
    relay.acknowledge('envelope-0000000001', 'worker-1', receipt('envelope-0000000001'));

    expect(relay.submit(envelope())).toEqual({ ok: false, rejection: 'duplicate' });
  });
});

describe('relay: rejections', () => {
  const cases: Array<[string, unknown, string]> = [
    ['oversized', envelope({ ciphertext: 'A'.repeat(MAX_ENVELOPE_JSON_BYTES) }), 'too_large'],
    ['unsupported version', envelope({ v: 2 }), 'unsupported_version'],
    ['unknown worker', envelope({ destinationWorkerId: 'nope' }), 'unknown_worker'],
    ['malformed', { hello: 'world' }, 'malformed'],
    [
      'lifetime beyond the cap',
      envelope({ expiresAt: new Date(T0.getTime() + 20 * 60_000).toISOString() }),
      'malformed',
    ],
    [
      'already expired',
      envelope({
        createdAt: new Date(T0.getTime() - 120_000).toISOString(),
        expiresAt: new Date(T0.getTime() - 60_000).toISOString(),
      }),
      'expired',
    ],
  ];

  for (const [name, input, rejection] of cases) {
    it(`rejects ${name}`, () => {
      const { relay } = makeRelay();
      expect(relay.submit(input)).toEqual({ ok: false, rejection });
      expect(relay.pendingCount).toBe(0);
    });
  }
});
