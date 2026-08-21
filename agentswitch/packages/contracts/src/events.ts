import { z } from 'zod';
import {
  CheckpointSchema,
  FailoverStateSchema,
  RoutingDecisionSchema,
  TransitionEventDetailSchema,
} from './domain.js';

/* ------------------------------------------------------------------ *
 * Agent events: emitted by an adapter, normalised from whatever the
 * underlying CLI produces. Every adapter maps its native output onto
 * exactly these shapes, which is what makes one timeline possible.
 * ------------------------------------------------------------------ */

const SessionStarted = z.object({
  type: z.literal('session_started'),
  sessionId: z.string(),
  adapterId: z.string(),
  modelId: z.string(),
  displayName: z.string(),
  /** 'initial' | 'handoff' — a handoff session starts read-only. */
  mode: z.enum(['initial', 'handoff']),
});

const TextDelta = z.object({
  type: z.literal('text_delta'),
  text: z.string(),
});

/** That the agent reasoned, never what it reasoned. Not portable, not stored. */
const ThinkingMarker = z.object({
  type: z.literal('thinking_marker'),
});

const ToolCall = z.object({
  type: z.literal('tool_call'),
  callId: z.string(),
  name: z.string(),
  summary: z.string(),
});

const ToolResult = z.object({
  type: z.literal('tool_result'),
  callId: z.string(),
  ok: z.boolean(),
  summary: z.string(),
});

const FileChange = z.object({
  type: z.literal('file_change'),
  path: z.string(),
  kind: z.enum(['create', 'edit', 'delete', 'rename']),
  added: z.number().int().nonnegative(),
  removed: z.number().int().nonnegative(),
});

const CommandRun = z.object({
  type: z.literal('command_run'),
  command: z.string(),
  exitCode: z.number().int(),
});

const TestResult = z.object({
  type: z.literal('test_result'),
  passed: z.number().int().nonnegative(),
  failed: z.number().int().nonnegative(),
  failing: z.array(z.string()),
});

/**
 * The failover trigger. 'approaching' moves the machine to limit_suspected;
 * only a second, confirming 'reached' signal moves it to limit_confirmed.
 * A single ambiguous signal never causes a switch.
 */
const LimitSignal = z.object({
  type: z.literal('limit_signal'),
  kind: z.enum(['approaching', 'reached']),
  /** Verbatim provider evidence. Never paraphrased into a false certainty. */
  evidence: z.string(),
  resetAt: z.string().nullable(),
});

/** Result of the mandatory read-only handoff verification pass. */
const VerificationResult = z.object({
  type: z.literal('verification_result'),
  agrees: z.boolean(),
  filesInspected: z.number().int().nonnegative(),
  notes: z.string(),
});

const SessionEnded = z.object({
  type: z.literal('session_ended'),
  reason: z.enum(['completed', 'usage_limit', 'cancelled', 'error']),
});

export const AgentEventSchema = z.discriminatedUnion('type', [
  SessionStarted,
  TextDelta,
  ThinkingMarker,
  ToolCall,
  ToolResult,
  FileChange,
  CommandRun,
  TestResult,
  LimitSignal,
  VerificationResult,
  SessionEnded,
]);
export type AgentEvent = z.infer<typeof AgentEventSchema>;

/* ------------------------------------------------------------------ *
 * Orchestrator events: emitted by AgentSwitch itself. They share the
 * timeline with agent events so the user sees one stream, not two.
 * ------------------------------------------------------------------ */

const FailoverStateChanged = z.object({
  type: z.literal('failover_state_changed'),
  from: FailoverStateSchema.nullable(),
  to: FailoverStateSchema,
  note: z.string(),
});

const CheckpointCreated = z.object({
  type: z.literal('checkpoint_created'),
  checkpoint: CheckpointSchema,
});

const RoutingCompleted = z.object({
  type: z.literal('routing_completed'),
  decision: RoutingDecisionSchema,
});

const Transition = z.object({
  type: z.literal('transition'),
  detail: TransitionEventDetailSchema,
});

const Paused = z.object({
  type: z.literal('paused'),
  reason: z.string(),
  resetAt: z.string().nullable(),
  /** What the user can do about it, in plain language. */
  options: z.array(z.string()),
});

export const OrchestratorEventSchema = z.discriminatedUnion('type', [
  FailoverStateChanged,
  CheckpointCreated,
  RoutingCompleted,
  Transition,
  Paused,
]);
export type OrchestratorEvent = z.infer<typeof OrchestratorEventSchema>;

/* ------------------------------------------------------------------ *
 * The timeline: one continuous, contiguously numbered stream per task.
 * A provider change does NOT reset seq and does NOT start a new task id.
 * That property is what "one continuous conversation" actually means.
 * ------------------------------------------------------------------ */

export const TimelinePayloadSchema = z.discriminatedUnion('type', [
  SessionStarted,
  TextDelta,
  ThinkingMarker,
  ToolCall,
  ToolResult,
  FileChange,
  CommandRun,
  TestResult,
  LimitSignal,
  VerificationResult,
  SessionEnded,
  FailoverStateChanged,
  CheckpointCreated,
  RoutingCompleted,
  Transition,
  Paused,
]);
export type TimelinePayload = z.infer<typeof TimelinePayloadSchema>;

export const TimelineEventSchema = z.object({
  /** 1-based, contiguous, never reset for the lifetime of the task. */
  seq: z.number().int().positive(),
  taskId: z.string().min(1),
  source: z.object({
    kind: z.enum(['agent', 'orchestrator']),
    adapterId: z.string().nullable(),
  }),
  payload: TimelinePayloadSchema,
});
export type TimelineEvent = z.infer<typeof TimelineEventSchema>;
