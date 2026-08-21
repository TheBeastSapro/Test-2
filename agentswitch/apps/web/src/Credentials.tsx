import { useCallback, useEffect, useRef, useState } from 'react';
import type {
  CredentialTypeId,
  DeliveryReceipt,
  ProviderId,
  WorkerIdentity,
} from '@agentswitch/contracts';
import { decodePublicKey, sealCredential, wipe } from '@agentswitch/crypto';
import { workerPin } from './workerPin';

/**
 * Encrypted credential delivery (Milestone 2A).
 *
 * The plaintext exists in exactly two places: this browser, and the worker the
 * user confirmed. It is read from an uncontrolled input only at the moment the
 * button is pressed, encrypted immediately, and the input is cleared. It never
 * enters React state, storage, a URL, a log, or an error message.
 */

interface CredentialTypeOption {
  id: CredentialTypeId | 'local-login';
  label: string;
  supported: boolean;
  note?: string;
}

const PROVIDERS: Array<{ id: ProviderId; label: string; types: CredentialTypeOption[] }> = [
  {
    id: 'claude',
    label: 'Claude',
    types: [
      {
        id: 'local-login',
        label: 'Existing sign-in on the worker',
        supported: false,
        note: 'AgentSwitch uses the sign-in already present on that computer and never brokers the credential. Nothing to send from here.',
      },
      {
        id: 'access-token',
        label: 'Raw token',
        supported: false,
        note: 'Not supported by AgentSwitch policy: Claude authentication stays with the local sign-in on the worker. No raw-token workaround will be offered.',
      },
    ],
  },
  {
    id: 'codex',
    label: 'Codex',
    types: [
      { id: 'test-value', label: 'Test value (security test mode)', supported: true },
      { id: 'api-key', label: 'API key', supported: true },
      { id: 'access-token', label: 'Access token', supported: true },
    ],
  },
  {
    id: 'gemini',
    label: 'Gemini',
    types: [
      { id: 'test-value', label: 'Test value (security test mode)', supported: true },
      { id: 'api-key', label: 'API key', supported: true },
    ],
  },
];

type Status =
  | { kind: 'idle' }
  | { kind: 'sending' }
  | { kind: 'success'; receipt: DeliveryReceipt }
  | { kind: 'error'; message: string };

const POLL_INTERVAL_MS = 300;
const POLL_TIMEOUT_MS = 15_000;

async function waitForReceipt(envelopeId: string): Promise<DeliveryReceipt | null> {
  const deadline = Date.now() + POLL_TIMEOUT_MS;
  while (Date.now() < deadline) {
    const response = await fetch(`/api/receipt?envelopeId=${encodeURIComponent(envelopeId)}`);
    if (response.ok) {
      const { receipt } = (await response.json()) as { receipt: DeliveryReceipt | null };
      if (receipt) return receipt;
    }
    await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
  }
  return null;
}

export function Credentials() {
  const [providerId, setProviderId] = useState<ProviderId>('codex');
  const provider = PROVIDERS.find((p) => p.id === providerId) ?? PROVIDERS[1]!;

  const [typeId, setTypeId] = useState<CredentialTypeOption['id']>('test-value');
  const credentialType = provider.types.find((t) => t.id === typeId) ?? provider.types[0]!;

  const [workers, setWorkers] = useState<WorkerIdentity[]>([]);
  const [workerId, setWorkerId] = useState<string>('');
  const [pinVersion, setPinVersion] = useState(0);
  const [revealed, setRevealed] = useState(false);
  const [status, setStatus] = useState<Status>({ kind: 'idle' });

  // Uncontrolled on purpose: the secret is never a React state value, so it
  // cannot reach a render tree, a devtools snapshot or a state serialisation.
  const tokenRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const response = await fetch('/api/workers');
        if (!response.ok) return;
        const { workers: list } = (await response.json()) as { workers: WorkerIdentity[] };
        if (cancelled) return;
        setWorkers(list);
        setWorkerId((current) => current || (list[0]?.workerId ?? ''));
      } catch {
        /* control plane not running; the UI shows "no computer connected" */
      }
    };
    void poll();
    const timer = setInterval(poll, 2000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);

  const worker = workers.find((w) => w.workerId === workerId) ?? null;
  const pinStatus = worker ? workerPin.status(worker) : 'unconfirmed';
  const canSend = Boolean(worker?.online) && pinStatus === 'confirmed' && credentialType.supported;

  const confirmFingerprint = () => {
    if (!worker) return;
    workerPin.confirm(worker);
    setPinVersion((v) => v + 1);
    setStatus({ kind: 'idle' });
  };

  const send = useCallback(async () => {
    const input = tokenRef.current;
    if (!input || !worker) return;

    // Read at the last possible moment, and only here.
    const value = input.value;
    if (value.length === 0) {
      setStatus({ kind: 'error', message: 'Enter a test value first.' });
      return;
    }

    setStatus({ kind: 'sending' });
    let secret: Uint8Array | null = null;

    try {
      secret = new TextEncoder().encode(value);
      const envelope = await sealCredential({
        secret,
        recipientPublicKey: await decodePublicKey(worker.publicKey),
        destinationWorkerId: worker.workerId,
        workerKeyFingerprint: worker.fingerprint,
        provider: providerId,
        credentialType: credentialType.id as CredentialTypeId,
      });

      // Cleared the instant encryption is done, before any network call.
      input.value = '';
      setRevealed(false);
      await wipe(secret);
      secret = null;

      const response = await fetch('/api/envelopes', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(envelope),
      });
      if (!response.ok) {
        setStatus({ kind: 'error', message: 'The relay rejected the envelope.' });
        return;
      }

      const receipt = await waitForReceipt(envelope.envelopeId);
      if (!receipt) {
        setStatus({ kind: 'error', message: 'No response from the worker in time.' });
        return;
      }
      setStatus(
        receipt.ok
          ? { kind: 'success', receipt }
          : { kind: 'error', message: `Worker rejected the delivery (${receipt.failure}).` },
      );
    } catch {
      // Never surface the exception: it can echo input.
      setStatus({ kind: 'error', message: 'Encryption or delivery failed.' });
    } finally {
      if (input.value !== '') input.value = '';
      if (secret) await wipe(secret);
    }
  }, [worker, providerId, credentialType.id]);

  return (
    <div className="credentials-view">
      <section className="panel form">
        <h1>Encrypted credential delivery</h1>

        <p className="warning-banner" role="status">
          Security test mode — use a test value only. Real provider credentials are not
          supported yet.
        </p>

        <label className="field-row">
          <span>Provider</span>
          <select
            value={providerId}
            onChange={(e) => {
              const next = PROVIDERS.find((p) => p.id === e.target.value) ?? PROVIDERS[1]!;
              setProviderId(next.id);
              setTypeId(next.types[0]!.id);
              if (tokenRef.current) tokenRef.current.value = '';
              setStatus({ kind: 'idle' });
            }}
          >
            {PROVIDERS.map((p) => (
              <option key={p.id} value={p.id}>
                {p.label}
              </option>
            ))}
          </select>
        </label>

        <label className="field-row">
          <span>Credential type</span>
          <select
            value={typeId}
            onChange={(e) => {
              setTypeId(e.target.value as CredentialTypeOption['id']);
              if (tokenRef.current) tokenRef.current.value = '';
              setStatus({ kind: 'idle' });
            }}
          >
            {provider.types.map((t) => (
              <option key={t.id} value={t.id}>
                {t.label}
                {t.supported ? '' : ' — Not Supported'}
              </option>
            ))}
          </select>
        </label>

        {credentialType.note && <p className="hint hint-blocked">{credentialType.note}</p>}

        <label className="field-row">
          <span>Destination computer</span>
          <select value={workerId} onChange={(e) => setWorkerId(e.target.value)}>
            {workers.length === 0 && <option value="">No computer connected</option>}
            {workers.map((w) => (
              <option key={w.workerId} value={w.workerId}>
                {w.displayName} ({w.online ? 'online' : 'offline'})
              </option>
            ))}
          </select>
        </label>

        <div className="worker-identity" data-pin-version={pinVersion}>
          <div className="worker-status-row">
            <span>Worker status</span>
            <span className={worker?.online ? 'chip chip-ok' : 'chip chip-warn'}>
              {worker ? (worker.online ? 'online' : 'offline') : 'not connected'}
            </span>
          </div>

          <div className="worker-status-row">
            <span>Fingerprint</span>
            <code data-testid="fingerprint">{worker?.fingerprint ?? '—'}</code>
          </div>

          {worker && pinStatus === 'key_changed' && (
            <p className="hint hint-blocked">
              This computer is presenting a different key than the one you confirmed. Delivery is
              blocked until you check the new fingerprint against what the worker prints.
            </p>
          )}

          {worker && pinStatus !== 'confirmed' && (
            <>
              <p className="hint">
                Check this fingerprint matches the one the worker printed in its own terminal,
                then confirm. This comparison is what stops a substituted key.
              </p>
              <button type="button" className="ghost" onClick={confirmFingerprint}>
                Confirm fingerprint
              </button>
            </>
          )}

          {pinStatus === 'confirmed' && (
            <p className="confirmed-note">
              Fingerprint confirmed for this browser session. A refresh clears it.
            </p>
          )}
        </div>

        <label className="field-row">
          <span>Test value</span>
          <span className="token-input">
            <input
              ref={tokenRef}
              type={revealed ? 'text' : 'password'}
              disabled={!canSend}
              placeholder={canSend ? 'Paste a test value' : 'Confirm the fingerprint first'}
              autoComplete="off"
              autoCorrect="off"
              autoCapitalize="off"
              spellCheck={false}
              data-testid="token-input"
              aria-describedby="token-help"
            />
            <button
              type="button"
              className="ghost"
              disabled={!canSend}
              onClick={() => setRevealed((v) => !v)}
              aria-pressed={revealed}
            >
              {revealed ? 'Hide' : 'Show'}
            </button>
          </span>
        </label>

        <p id="token-help" className="fineprint">
          Encrypted in this browser to the confirmed worker key before anything is sent. The box
          is cleared the moment encryption completes.
        </p>

        <div className="save-row">
          <button
            type="button"
            className="primary"
            disabled={!canSend || status.kind === 'sending'}
            onClick={() => void send()}
          >
            {status.kind === 'sending' ? 'Delivering…' : 'Test Encrypted Delivery'}
          </button>

          {status.kind === 'success' && (
            <p className="status-ok" role="status" data-testid="delivery-status">
              Worker decrypted the envelope. provider={status.receipt.provider} · type=
              {status.receipt.credentialType} · worker={status.receipt.workerId}
              {status.receipt.canaryMatched === null
                ? ''
                : ` · canary ${status.receipt.canaryMatched ? 'matched' : 'did not match'}`}
            </p>
          )}
          {status.kind === 'error' && (
            <p className="status-error" role="status" data-testid="delivery-status">
              {status.message}
            </p>
          )}
        </div>
      </section>

      <aside className="panel notice">
        <h2>What happens when you press the button</h2>
        <ol className="steps">
          <li>The value is read from the box only at that moment.</li>
          <li>It is encrypted in this browser to the confirmed worker key.</li>
          <li>The box is cleared before any network request is made.</li>
          <li>The control plane relays ciphertext it has no key to open.</li>
          <li>The worker decrypts locally and reports success — never the value.</li>
          <li>The relay deletes the ciphertext on acknowledgement.</li>
        </ol>
        <p className="fineprint">
          Nothing is stored. The worker holds its key in memory only and forgets it on exit, so a
          worker restart requires confirming a new fingerprint. Persistent OS-protected storage is
          Milestone 2B.
        </p>
      </aside>
    </div>
  );
}
