import { z } from 'zod';

/**
 * A task is classified before any routing happens. The class selects which
 * capability score the router compares candidates on.
 */
export const TaskClassSchema = z.enum([
  'architecture',
  'planning',
  'repository_exploration',
  'multi_file_implementation',
  'focused_coding',
  'debugging',
  'test_repair',
  'refactoring',
  'migration',
  'code_review',
  'security_review',
  'frontend_ui',
  'research',
  'large_context',
  'multimodal',
  'documentation',
]);
export type TaskClass = z.infer<typeof TaskClassSchema>;

/** Quality modes set how far below the departing agent we will accept. */
export const QualityModeSchema = z.enum([
  'strict',
  'balanced',
  'continue_at_any_cost',
  'ask_me',
]);
export type QualityMode = z.infer<typeof QualityModeSchema>;

/**
 * How much of the departing agent's task-relevant score a replacement must
 * retain. Expressed as a multiplier so the floor is always relative to what
 * we are replacing, never an absolute number baked into the product.
 */
export const QUALITY_FLOOR_MULTIPLIER: Readonly<Record<QualityMode, number>> = Object.freeze({
  strict: 0.95,
  balanced: 0.85,
  continue_at_any_cost: 0.6,
  // ask_me uses the balanced floor to shortlist, then always defers to the user.
  ask_me: 0.85,
});

/** Hard capability requirements are pass/fail gates, never scored. */
export const CapabilityFlagsSchema = z.object({
  images: z.boolean(),
  webAccess: z.boolean(),
  mcp: z.boolean(),
  multiFileEditing: z.boolean(),
  structuredOutput: z.boolean(),
  sandboxControls: z.boolean(),
});
export type CapabilityFlags = z.infer<typeof CapabilityFlagsSchema>;

export const TaskSchema = z.object({
  id: z.string().min(1),
  objective: z.string().min(1),
  taskClass: TaskClassSchema,
  qualityMode: QualityModeSchema,
  /** Capabilities the task cannot proceed without. */
  requiredCapabilities: z.array(CapabilityFlagsSchema.keyof()),
  /** Rough context need, used by the context-sufficiency gate. */
  estimatedContextTokens: z.number().int().nonnegative(),
  /** Repository/worktree the task runs in. Not exercised in Milestone 1. */
  workspacePath: z.string(),
});
export type Task = z.infer<typeof TaskSchema>;

/**
 * Adapter maturity. Only stable/beta adapters may be selected automatically;
 * experimental requires explicit opt-in, unsupported is never selectable.
 */
export const AdapterStatusSchema = z.enum(['stable', 'beta', 'experimental', 'unsupported']);
export type AdapterStatus = z.infer<typeof AdapterStatusSchema>;

/**
 * One CLI x model combination. Scores are DATA, not code: in production this
 * record is loaded from a versioned registry fed by documented capabilities,
 * local qualification runs and real task outcomes. Nothing here is hard-coded
 * as "the best model".
 */
export const CapabilityProfileSchema = z.object({
  adapterId: z.string().min(1),
  modelId: z.string().min(1),
  displayName: z.string().min(1),
  status: AdapterStatusSchema,
  capabilities: CapabilityFlagsSchema,
  contextTokens: z.number().int().positive(),
  /** 0-100 per task class. Absent class means "no evidence" and scores 0. */
  scores: z.record(TaskClassSchema, z.number().min(0).max(100)),
  availability: z.object({
    state: z.enum(['ok', 'rate_limited', 'unavailable']),
    /** Populated only when the provider documents a reset time. */
    resetAt: z.string().nullable(),
  }),
  authenticated: z.boolean(),
  /** Provenance of the scores above, surfaced in the routing explanation. */
  scoreSource: z.enum(['simulated', 'local_eval', 'task_outcomes', 'documented']),
});
export type CapabilityProfile = z.infer<typeof CapabilityProfileSchema>;

/** Why a candidate failed a pass/fail gate, before any scoring happened. */
export const GateFailureSchema = z.enum([
  'is_departing_agent',
  'not_available',
  'not_authenticated',
  'adapter_status_not_selectable',
  'missing_required_capability',
  'insufficient_context',
]);
export type GateFailure = z.infer<typeof GateFailureSchema>;

export const CandidateEvaluationSchema = z.object({
  adapterId: z.string(),
  modelId: z.string(),
  displayName: z.string(),
  eligible: z.boolean(),
  gateFailures: z.array(GateFailureSchema),
  /** Task-relevant capability score; null when gates were never passed. */
  score: z.number().nullable(),
  aboveFloor: z.boolean(),
});
export type CandidateEvaluation = z.infer<typeof CandidateEvaluationSchema>;

export const RoutingOutcomeSchema = z.enum([
  'selected',
  'paused_no_candidate_clears_floor',
  'paused_user_confirmation_required',
]);
export type RoutingOutcome = z.infer<typeof RoutingOutcomeSchema>;

export const RoutingDecisionSchema = z.object({
  taskId: z.string(),
  taskClass: TaskClassSchema,
  qualityMode: QualityModeSchema,
  departingAdapterId: z.string().nullable(),
  departingScore: z.number().nullable(),
  floorMultiplier: z.number(),
  /** The score a candidate must reach. departingScore * floorMultiplier. */
  requiredScore: z.number(),
  candidates: z.array(CandidateEvaluationSchema),
  selectedAdapterId: z.string().nullable(),
  outcome: RoutingOutcomeSchema,
  /** Plain-English rationale shown behind "Why this agent?". */
  explanation: z.string(),
});
export type RoutingDecision = z.infer<typeof RoutingDecisionSchema>;

/** The failover state machine's states, in the order they normally occur. */
export const FailoverStateSchema = z.enum([
  'running',
  'limit_suspected',
  'limit_confirmed',
  'checkpoint_requested',
  'routing',
  'handoff_verification',
  'paused',
]);
export type FailoverState = z.infer<typeof FailoverStateSchema>;

/**
 * A checkpoint records OBSERVABLE state only: what changed on disk, what the
 * tests said, what remains. Hidden reasoning is never captured, because it is
 * not portable across providers and storing it would imply otherwise.
 */
export const CheckpointSchema = z.object({
  taskId: z.string(),
  sequence: z.number().int().nonnegative(),
  objective: z.string(),
  createdAfterEventSeq: z.number().int().nonnegative(),
  filesChanged: z.array(
    z.object({
      path: z.string(),
      added: z.number().int().nonnegative(),
      removed: z.number().int().nonnegative(),
    }),
  ),
  commandsRun: z.array(z.string()),
  lastTestResult: z
    .object({ passed: z.number().int(), failed: z.number().int() })
    .nullable(),
  remainingWork: z.array(z.string()),
});
export type Checkpoint = z.infer<typeof CheckpointSchema>;

/** The small timeline marker a provider change produces in the UI. */
export const TransitionEventDetailSchema = z.object({
  reason: z.enum(['usage_limit', 'provider_outage', 'auth_failure', 'crash', 'context_exhausted']),
  fromAdapterId: z.string(),
  fromDisplayName: z.string(),
  toAdapterId: z.string(),
  toDisplayName: z.string(),
  /** Documented reset time when the provider gave one, otherwise null. */
  resetAt: z.string().nullable(),
  checkpointSequence: z.number().int().nonnegative(),
  summary: z.string(),
});
export type TransitionEventDetail = z.infer<typeof TransitionEventDetailSchema>;
