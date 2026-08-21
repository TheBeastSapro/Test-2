import { useEffect, useRef, useState } from 'react';

/**
 * Credentials page SHELL for Milestone 1.
 *
 * Nothing here transmits, stores or validates anything. "Test and Save" is
 * disabled on purpose: the encrypted worker delivery it depends on does not
 * exist yet, and a button that appears to work would be worse than no button.
 *
 * The typed value lives only in this component's state for as long as the page
 * is open. It is never written to localStorage, never put in a URL, never
 * logged, and never sent anywhere.
 */

interface CredentialType {
  id: string;
  label: string;
  supported: boolean;
  note?: string;
}

interface Provider {
  id: string;
  label: string;
  credentialTypes: CredentialType[];
}

const PROVIDERS: Provider[] = [
  {
    id: 'claude',
    label: 'Claude',
    credentialTypes: [
      {
        id: 'local-login',
        label: 'Existing sign-in on the worker',
        supported: true,
        note: 'AgentSwitch uses the sign-in already present on that computer. It never sees or brokers the credential.',
      },
      {
        id: 'raw-token',
        label: 'Raw token',
        supported: false,
        note: 'Not supported by AgentSwitch policy: Claude authentication stays with the local sign-in on the worker. No raw-token workaround will be offered.',
      },
    ],
  },
  {
    id: 'codex',
    label: 'Codex',
    credentialTypes: [
      {
        id: 'official-login',
        label: 'Official login on the worker',
        supported: true,
        note: 'Preferred. Performed by the CLI itself on that computer.',
      },
      { id: 'api-key', label: 'API key', supported: true },
      { id: 'access-token', label: 'Access token', supported: true },
    ],
  },
  {
    id: 'gemini',
    label: 'Gemini',
    credentialTypes: [
      { id: 'official-login', label: 'Official login on the worker', supported: true },
      { id: 'api-key', label: 'API key', supported: true },
    ],
  },
];

const WORKERS = [{ id: 'none', label: 'No computer connected yet' }];

export function Credentials() {
  const [providerId, setProviderId] = useState<string>(PROVIDERS[0]!.id);
  const provider = PROVIDERS.find((p) => p.id === providerId) ?? PROVIDERS[0]!;

  const [typeId, setTypeId] = useState<string>(provider.credentialTypes[0]!.id);
  const credentialType =
    provider.credentialTypes.find((t) => t.id === typeId) ?? provider.credentialTypes[0]!;

  const [token, setToken] = useState('');
  const [revealed, setRevealed] = useState(false);

  // Best-effort scrub on unmount. JavaScript strings are immutable and
  // garbage-collected, so this drops our reference rather than wiping memory.
  // Saying so plainly is better than implying a guarantee we cannot make.
  const tokenRef = useRef('');
  tokenRef.current = token;
  useEffect(
    () => () => {
      tokenRef.current = '';
    },
    [],
  );

  const selectProvider = (id: string) => {
    const next = PROVIDERS.find((p) => p.id === id) ?? PROVIDERS[0]!;
    setProviderId(next.id);
    setTypeId(next.credentialTypes[0]!.id);
    setToken('');
    setRevealed(false);
  };

  const entryAllowed =
    credentialType.supported &&
    credentialType.id !== 'local-login' &&
    credentialType.id !== 'official-login';

  return (
    <div className="credentials-view">
      <section className="panel form">
        <h1>Credentials</h1>
        <p className="objective">
          Credentials belong to one person and one computer. AgentSwitch is designed so the
          central server never holds a key that could read them.
        </p>

        <label className="field-row">
          <span>Provider</span>
          <select value={providerId} onChange={(e) => selectProvider(e.target.value)}>
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
              setTypeId(e.target.value);
              setToken('');
            }}
          >
            {provider.credentialTypes.map((t) => (
              <option key={t.id} value={t.id}>
                {t.label}
                {t.supported ? '' : ' — Not Supported'}
              </option>
            ))}
          </select>
        </label>

        {credentialType.note && (
          <p className={credentialType.supported ? 'hint' : 'hint hint-blocked'}>
            {credentialType.note}
          </p>
        )}

        <label className="field-row">
          <span>Destination computer</span>
          <select disabled>
            {WORKERS.map((w) => (
              <option key={w.id} value={w.id}>
                {w.label}
              </option>
            ))}
          </select>
        </label>

        <label className="field-row">
          <span>Token</span>
          <span className="token-input">
            <input
              type={revealed ? 'text' : 'password'}
              value={token}
              disabled={!entryAllowed}
              placeholder={entryAllowed ? 'Paste your token' : 'Not applicable for this type'}
              onChange={(e) => setToken(e.target.value)}
              autoComplete="off"
              autoCorrect="off"
              autoCapitalize="off"
              spellCheck={false}
              aria-describedby="token-help"
            />
            <button
              type="button"
              className="ghost"
              disabled={!entryAllowed}
              onClick={() => setRevealed((v) => !v)}
              aria-pressed={revealed}
            >
              {revealed ? 'Hide' : 'Show'}
            </button>
          </span>
        </label>

        <p id="token-help" className="fineprint">
          Only credential types a provider officially documents as user-supplied are accepted.
          Browser cookies, extracted session tokens and internal OAuth credentials are never
          accepted.
        </p>

        <div className="save-row">
          <button type="button" className="primary" disabled aria-describedby="save-disabled">
            Test and Save
          </button>
          <p id="save-disabled" className="disabled-note">
            Encrypted worker delivery will be enabled in Milestone 2.
          </p>
        </div>
      </section>

      <aside className="panel notice">
        <h2>What this page will do</h2>
        <ol className="steps">
          <li>Your browser fetches the destination computer&apos;s public key.</li>
          <li>You confirm its fingerprint matches the one that computer displays.</li>
          <li>The browser encrypts the token to that key before anything is sent.</li>
          <li>The server relays ciphertext it has no key to open.</li>
          <li>That computer decrypts it locally and stores it in the OS secret store.</li>
          <li>The relayed copy is one-time-use and deleted on acknowledgement.</li>
        </ol>
        <p className="fineprint">
          None of this is implemented yet, which is exactly why the button above is disabled.
        </p>
      </aside>
    </div>
  );
}
