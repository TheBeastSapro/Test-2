import {
  createWorkerContext,
  encodePublicKey,
  fingerprintPublicKey,
  generateWorkerKeyPair,
  receiveEnvelope,
} from '@agentswitch/crypto';

/**
 * AgentSwitch worker (Milestone 2A).
 *
 * Generates an in-memory X25519 key pair, registers ONLY the public half with
 * the control plane, prints its own fingerprint, then polls for envelopes
 * addressed to it, decrypts them locally and acknowledges so the relay can
 * delete the ciphertext.
 *
 * The private key is an ordinary Uint8Array in this process's heap. It is not
 * OS-protected and does not survive a restart; a restart produces a new
 * identity and requires fresh fingerprint confirmation in the browser. That is
 * the intended behaviour until Milestone 2B adds persistent OS-level
 * protection on Windows.
 */

const CONTROL_PLANE = process.env.AGENTSWITCH_CONTROL_PLANE ?? 'http://127.0.0.1:8787';
const WORKER_ID = process.env.AGENTSWITCH_WORKER_ID ?? 'worker-dev-1';
const DISPLAY_NAME = process.env.AGENTSWITCH_WORKER_NAME ?? 'This computer (dev)';
const POLL_MS = Number(process.env.AGENTSWITCH_POLL_MS ?? 300);
const HEARTBEAT_MS = 5_000;

/**
 * Test-path canary. When set, the worker reports whether decrypted bytes
 * matched it. It is supplied by the environment precisely so it never appears
 * in any committed source file or shipped build artifact.
 */
const EXPECTED_CANARY = process.env.AGENTSWITCH_TEST_CANARY;

async function post(path: string, body: unknown): Promise<Response> {
  return fetch(`${CONTROL_PLANE}${path}`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  });
}

async function main(): Promise<void> {
  const keyPair = await generateWorkerKeyPair();
  const publicKey = await encodePublicKey(keyPair.publicKey);
  const fingerprint = await fingerprintPublicKey(keyPair.publicKey);
  const context = createWorkerContext(WORKER_ID, fingerprint, keyPair, EXPECTED_CANARY);

  // Printed independently of the control plane and of the browser. This is the
  // value a person compares against what the website shows - the one check
  // that stands between "zero-knowledge" and "trust the server".
  console.log('');
  console.log('  AgentSwitch worker');
  console.log(`  worker id    ${WORKER_ID}`);
  console.log(`  fingerprint  ${fingerprint}`);
  console.log('');
  console.log('  Confirm this fingerprint in the browser before sending anything.');
  console.log('  The private key is in this process\'s memory only and is lost on exit.');
  console.log('');

  const registration = await post('/api/workers/register', {
    workerId: WORKER_ID,
    displayName: DISPLAY_NAME,
    publicKey,
    fingerprint,
  });
  if (!registration.ok) {
    console.error(`  registration failed (${registration.status})`);
    process.exit(1);
  }
  console.log(`  registered with ${CONTROL_PLANE}`);

  setInterval(() => {
    void post('/api/workers/heartbeat', { workerId: WORKER_ID }).catch(() => {});
  }, HEARTBEAT_MS).unref();

  for (;;) {
    try {
      const response = await fetch(
        `${CONTROL_PLANE}/api/envelopes?workerId=${encodeURIComponent(WORKER_ID)}`,
      );
      if (response.ok) {
        const { envelopes } = (await response.json()) as { envelopes: unknown[] };
        for (const envelope of envelopes) {
          const receipt = await receiveEnvelope(context, envelope);
          await post('/api/envelopes/ack', { receipt });
          // Non-secret only: never the credential, never a derivative of it.
          console.log(
            `  envelope ${receipt.envelopeId.slice(0, 8)}… ` +
              `${receipt.ok ? 'accepted' : `rejected (${receipt.failure})`}` +
              (receipt.canaryMatched === null ? '' : ` canary=${receipt.canaryMatched}`),
          );
        }
      }
    } catch {
      // Control plane unreachable; keep polling rather than exiting.
    }
    await new Promise((resolve) => setTimeout(resolve, POLL_MS));
  }
}

void main();
