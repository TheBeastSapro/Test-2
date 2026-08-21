import type {
  AdapterRunMode,
  AgentAdapter,
  AgentEvent,
  CapabilityProfile,
} from '@agentswitch/contracts';

/**
 * Simulated adapters for Milestone 1.
 *
 * These are NOT stand-ins for any real provider. Model ids, messages and
 * limit evidence are deliberately synthetic and prefixed so nothing here can
 * be mistaken for documented behaviour of a real CLI. Real adapters land in
 * Milestone 2, built strictly against official documentation.
 *
 * What is real: the event shapes, the ordering, and the fact that the work
 * they describe is what the checkpoint and handoff package are derived from.
 */

const FULL_CAPABILITIES = {
  images: true,
  webAccess: true,
  mcp: true,
  multiFileEditing: true,
  structuredOutput: true,
  sandboxControls: true,
} as const;

export const SIM_ALPHA_PROFILE: CapabilityProfile = {
  adapterId: 'sim-alpha',
  modelId: 'sim-model-a1',
  displayName: 'Sim Alpha',
  status: 'stable',
  capabilities: { ...FULL_CAPABILITIES },
  contextTokens: 200_000,
  scores: {
    multi_file_implementation: 88,
    debugging: 86,
    test_repair: 84,
    refactoring: 85,
    planning: 87,
  },
  availability: { state: 'ok', resetAt: null },
  authenticated: true,
  scoreSource: 'simulated',
};

export const SIM_BETA_PROFILE: CapabilityProfile = {
  adapterId: 'sim-beta',
  modelId: 'sim-model-b1',
  displayName: 'Sim Beta',
  status: 'stable',
  capabilities: { ...FULL_CAPABILITIES },
  contextTokens: 200_000,
  scores: {
    multi_file_implementation: 85,
    debugging: 82,
    test_repair: 83,
    refactoring: 80,
    planning: 79,
  },
  availability: { state: 'ok', resetAt: null },
  authenticated: true,
  scoreSource: 'simulated',
};

/**
 * Deliberately weak. It passes every hard gate - installed, signed in,
 * selectable adapter status, has multi-file editing, enough context - so that
 * when it is rejected, it is rejected by the QUALITY FLOOR and nothing else.
 */
export const SIM_GAMMA_PROFILE: CapabilityProfile = {
  adapterId: 'sim-gamma',
  modelId: 'sim-model-g1',
  displayName: 'Sim Gamma',
  status: 'beta',
  capabilities: {
    ...FULL_CAPABILITIES,
    images: false,
    webAccess: false,
  },
  contextTokens: 64_000,
  scores: {
    multi_file_implementation: 55,
    debugging: 51,
    test_repair: 49,
    refactoring: 50,
    planning: 48,
  },
  availability: { state: 'ok', resetAt: null },
  authenticated: true,
  scoreSource: 'simulated',
};

/** Synthetic reset time. Never a real provider's wording or schedule. */
const SIM_RESET_AT = '[simulated] 45 minutes from the start of this task';

type Script = readonly AgentEvent[];

function sessionStart(
  profile: CapabilityProfile,
  mode: 'initial' | 'handoff',
): AgentEvent {
  return {
    type: 'session_started',
    sessionId: `${profile.adapterId}-session-1`,
    adapterId: profile.adapterId,
    modelId: profile.modelId,
    displayName: profile.displayName,
    mode,
  };
}

/** Strong starting agent: does real-looking work, then hits a simulated limit. */
function alphaInitial(): Script {
  return [
    sessionStart(SIM_ALPHA_PROFILE, 'initial'),
    { type: 'text_delta', text: 'Reading the API client to see how requests are issued.' },
    { type: 'thinking_marker' },
    { type: 'tool_call', callId: 'a1', name: 'Read', summary: 'src/api/client.ts' },
    { type: 'tool_result', callId: 'a1', ok: true, summary: '96 lines' },
    { type: 'text_delta', text: 'Adding a retry helper and wiring it into the client.' },
    { type: 'file_change', path: 'src/api/retry.ts', kind: 'create', added: 42, removed: 0 },
    { type: 'file_change', path: 'src/api/client.ts', kind: 'edit', added: 18, removed: 4 },
    { type: 'command_run', command: 'npm test', exitCode: 1 },
    {
      type: 'test_result',
      passed: 11,
      failed: 2,
      failing: ['retry > backs off exponentially', 'retry > gives up after max attempts'],
    },
    { type: 'text_delta', text: 'Two tests fail. The backoff calculation is wrong; fixing it.' },
    { type: 'file_change', path: 'src/api/retry.ts', kind: 'edit', added: 6, removed: 3 },
    {
      type: 'limit_signal',
      kind: 'approaching',
      evidence: '[simulated] sim-alpha reported repeated rate-limited retries',
      resetAt: null,
    },
    { type: 'text_delta', text: 'Continuing while the provider still accepts requests.' },
    {
      type: 'limit_signal',
      kind: 'reached',
      evidence: '[simulated] sim-alpha usage limit reached',
      resetAt: SIM_RESET_AT,
    },
    { type: 'session_ended', reason: 'usage_limit' },
  ];
}

/**
 * The mandatory read-only verification pass. No file_change events appear
 * here: the replacement is not permitted to write until it has confirmed the
 * work it inherited actually matches the checkpoint.
 */
function verifyScript(profile: CapabilityProfile): Script {
  return [
    sessionStart(profile, 'handoff'),
    { type: 'text_delta', text: 'Checking the inherited work before changing anything.' },
    { type: 'tool_call', callId: 'v1', name: 'Read', summary: 'diff of 2 changed files' },
    { type: 'tool_result', callId: 'v1', ok: true, summary: '2 files, +66/-7' },
    { type: 'command_run', command: 'npm test', exitCode: 1 },
    {
      type: 'test_result',
      passed: 11,
      failed: 2,
      failing: ['retry > backs off exponentially', 'retry > gives up after max attempts'],
    },
    {
      type: 'verification_result',
      agrees: true,
      filesInspected: 2,
      notes: 'Diff and test results match the checkpoint. Safe to continue.',
    },
  ];
}

/** Continuation after verification passed. Same worktree, same objective. */
function continueScript(): Script {
  return [
    { type: 'text_delta', text: 'Confirmed. Picking up at the backoff calculation.' },
    { type: 'file_change', path: 'src/api/retry.ts', kind: 'edit', added: 9, removed: 5 },
    { type: 'command_run', command: 'npm test', exitCode: 0 },
    { type: 'test_result', passed: 13, failed: 0, failing: [] },
    { type: 'text_delta', text: 'All 13 tests pass. Retry handling is complete.' },
    { type: 'session_ended', reason: 'completed' },
  ];
}

/** Minimal script so gamma is a usable adapter, not a hollow object. */
function gammaInitial(): Script {
  return [
    sessionStart(SIM_GAMMA_PROFILE, 'initial'),
    { type: 'text_delta', text: 'Starting work.' },
    { type: 'file_change', path: 'src/api/retry.ts', kind: 'create', added: 12, removed: 0 },
    { type: 'session_ended', reason: 'completed' },
  ];
}

class SimAdapter implements AgentAdapter {
  constructor(
    readonly id: string,
    readonly profile: CapabilityProfile,
    private readonly scripts: {
      initial: () => Script;
      verify: () => Script;
      continue: () => Script;
    },
  ) {}

  async *run(mode: AdapterRunMode): AsyncGenerator<AgentEvent, void, void> {
    const script =
      mode.kind === 'initial'
        ? this.scripts.initial()
        : mode.kind === 'verify'
          ? this.scripts.verify()
          : this.scripts.continue();

    for (const event of script) {
      yield event;
    }
  }
}

export function createSimAlpha(): AgentAdapter {
  return new SimAdapter('sim-alpha', SIM_ALPHA_PROFILE, {
    initial: alphaInitial,
    verify: () => verifyScript(SIM_ALPHA_PROFILE),
    continue: continueScript,
  });
}

export function createSimBeta(): AgentAdapter {
  return new SimAdapter('sim-beta', SIM_BETA_PROFILE, {
    initial: () => verifyScript(SIM_BETA_PROFILE),
    verify: () => verifyScript(SIM_BETA_PROFILE),
    continue: continueScript,
  });
}

export function createSimGamma(): AgentAdapter {
  return new SimAdapter('sim-gamma', SIM_GAMMA_PROFILE, {
    initial: gammaInitial,
    verify: () => verifyScript(SIM_GAMMA_PROFILE),
    continue: continueScript,
  });
}

export function createAllSimAdapters(): AgentAdapter[] {
  return [createSimAlpha(), createSimBeta(), createSimGamma()];
}
