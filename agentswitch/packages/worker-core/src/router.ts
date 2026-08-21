import {
  QUALITY_FLOOR_MULTIPLIER,
  type CandidateEvaluation,
  type CapabilityProfile,
  type GateFailure,
  type RoutingDecision,
  type Task,
  type TaskClass,
} from '@agentswitch/contracts';

export interface RouteInput {
  task: Task;
  /** The agent being replaced. null when routing a brand new task. */
  departing: CapabilityProfile | null;
  /** Every profile currently known to be installed on some worker. */
  candidates: CapabilityProfile[];
}

const SELECTABLE_STATUSES = new Set(['stable', 'beta']);

/** Two decimals, so floating-point noise can never move a floor comparison. */
const round2 = (n: number): number => Math.round(n * 100) / 100;

/** Task-relevant score. An unscored task class means no evidence, so zero. */
export function scoreFor(profile: CapabilityProfile, task: Task): number {
  // Widened to a partial record: an unscored class is "no evidence", not zero
  // confidence in a score we never measured.
  const scores: Partial<Record<TaskClass, number>> = profile.scores;
  return scores[task.taskClass] ?? 0;
}

/**
 * Pass/fail gates, evaluated before any ranking. All failures are collected
 * rather than short-circuited so the explanation can be complete.
 */
function evaluateGates(
  profile: CapabilityProfile,
  input: RouteInput,
): GateFailure[] {
  const failures: GateFailure[] = [];

  if (input.departing && profile.adapterId === input.departing.adapterId) {
    failures.push('is_departing_agent');
  }
  if (profile.availability.state !== 'ok') {
    failures.push('not_available');
  }
  if (!profile.authenticated) {
    failures.push('not_authenticated');
  }
  if (!SELECTABLE_STATUSES.has(profile.status)) {
    failures.push('adapter_status_not_selectable');
  }
  const missing = input.task.requiredCapabilities.filter(
    (cap) => !profile.capabilities[cap],
  );
  if (missing.length > 0) {
    failures.push('missing_required_capability');
  }
  if (profile.contextTokens < input.task.estimatedContextTokens) {
    failures.push('insufficient_context');
  }

  return failures;
}

/**
 * Deterministic ordering: highest task-relevant score first, adapter id
 * ascending as the tie-break. Given the same inputs in any order, the same
 * agent is always chosen.
 */
function compareCandidates(a: CandidateEvaluation, b: CandidateEvaluation): number {
  const scoreDelta = (b.score ?? -1) - (a.score ?? -1);
  if (scoreDelta !== 0) return scoreDelta;
  return a.adapterId.localeCompare(b.adapterId);
}

export function route(input: RouteInput): RoutingDecision {
  const { task, departing } = input;
  const floorMultiplier = QUALITY_FLOOR_MULTIPLIER[task.qualityMode];
  const departingScore = departing ? scoreFor(departing, task) : null;
  const requiredScore =
    departingScore === null ? 0 : round2(departingScore * floorMultiplier);

  const candidates: CandidateEvaluation[] = input.candidates
    .map((profile) => {
      const gateFailures = evaluateGates(profile, input);
      const eligible = gateFailures.length === 0;
      const score = eligible ? round2(scoreFor(profile, task)) : null;
      return {
        adapterId: profile.adapterId,
        modelId: profile.modelId,
        displayName: profile.displayName,
        eligible,
        gateFailures,
        score,
        aboveFloor: score !== null && score >= requiredScore,
      };
    })
    // Stable output shape regardless of input order.
    .sort((a, b) => a.adapterId.localeCompare(b.adapterId));

  const qualified = candidates
    .filter((c) => c.eligible && c.aboveFloor)
    .sort(compareCandidates);

  const best = qualified[0] ?? null;

  // 'ask_me' shortlists with the balanced floor but never auto-selects.
  if (task.qualityMode === 'ask_me') {
    return {
      taskId: task.id,
      taskClass: task.taskClass,
      qualityMode: task.qualityMode,
      departingAdapterId: departing?.adapterId ?? null,
      departingScore,
      floorMultiplier,
      requiredScore,
      candidates,
      selectedAdapterId: null,
      outcome: 'paused_user_confirmation_required',
      explanation: explain(task, departing, requiredScore, candidates, null, true),
    };
  }

  return {
    taskId: task.id,
    taskClass: task.taskClass,
    qualityMode: task.qualityMode,
    departingAdapterId: departing?.adapterId ?? null,
    departingScore,
    floorMultiplier,
    requiredScore,
    candidates,
    selectedAdapterId: best?.adapterId ?? null,
    outcome: best ? 'selected' : 'paused_no_candidate_clears_floor',
    explanation: explain(task, departing, requiredScore, candidates, best, false),
  };
}

const GATE_TEXT: Readonly<Record<GateFailure, string>> = Object.freeze({
  is_departing_agent: 'it is the agent being replaced',
  not_available: 'it is not currently available',
  not_authenticated: 'it is not signed in',
  adapter_status_not_selectable: 'its adapter is not mature enough to pick automatically',
  missing_required_capability: 'it lacks a capability this task needs',
  insufficient_context: 'its context window is too small for this task',
});

/** Plain-English rationale, shown behind "Why this agent?". */
function explain(
  task: Task,
  departing: CapabilityProfile | null,
  requiredScore: number,
  candidates: CandidateEvaluation[],
  selected: CandidateEvaluation | null,
  awaitingUser: boolean,
): string {
  const lines: string[] = [];

  lines.push(`Task type: ${task.taskClass.replace(/_/g, ' ')}.`);
  lines.push(`Quality mode: ${task.qualityMode.replace(/_/g, ' ')}.`);

  if (departing) {
    const departingScore = round2(scoreFor(departing, task));
    lines.push(
      `${departing.displayName} scored ${departingScore}/100 on this kind of work, ` +
        `so a replacement must reach at least ${requiredScore}/100 to be accepted.`,
    );
  } else {
    lines.push('No agent is being replaced, so there is no quality floor to clear.');
  }

  lines.push('');
  lines.push('Candidates considered:');
  for (const c of candidates) {
    if (!c.eligible) {
      const reasons = c.gateFailures.map((f) => GATE_TEXT[f]).join('; ');
      lines.push(`  - ${c.displayName}: ruled out because ${reasons}.`);
      continue;
    }
    const verdict = c.aboveFloor
      ? `meets the floor (${c.score} >= ${requiredScore})`
      : `below the floor (${c.score} < ${requiredScore})`;
    const chosen = selected && selected.adapterId === c.adapterId ? ' — selected' : '';
    lines.push(`  - ${c.displayName}: scored ${c.score}/100, ${verdict}${chosen}.`);
  }

  lines.push('');
  if (awaitingUser) {
    lines.push('Quality mode is "ask me", so AgentSwitch is waiting for you to choose.');
  } else if (selected) {
    lines.push(
      `Continuing with ${selected.displayName} because it was the highest-scoring ` +
        'available agent that met the quality floor.',
    );
  } else {
    lines.push(
      'No available agent met the quality floor, so AgentSwitch paused instead of ' +
        'continuing with a weaker agent. Your work is checkpointed and unchanged.',
    );
  }

  return lines.join('\n');
}
