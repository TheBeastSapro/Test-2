import type { AgentEvent } from './events.js';
import type { CapabilityProfile, Checkpoint, Task } from './domain.js';

/**
 * What a replacement agent is handed at a cross-provider switch.
 *
 * Layered deliberately: layer 1 is never truncated, later layers are dropped
 * first under a token budget. It carries PATHS and COUNTS, never file
 * contents - the replacement is already standing in the same worktree and can
 * read what it needs with its own tools. That single decision is what keeps a
 * handoff cheap.
 *
 * It never carries hidden reasoning. No provider can consume another's.
 */
export interface ContinuityPackage {
  /** Layer 1 - mission. Verbatim user intent. Never truncated. */
  objective: string;
  constraints: string[];
  /** Layer 2 - ground truth. Paths and counts only. */
  workspacePath: string;
  filesChanged: Array<{ path: string; added: number; removed: number }>;
  /** Layer 3 - progress. */
  completedWork: string[];
  remainingWork: string[];
  /** Layer 4 - decisions and dead ends, so work is not repeated. */
  decisions: string[];
  rejectedApproaches: string[];
  /** Layer 5 - test status. */
  lastTestResult: { passed: number; failed: number } | null;
  /** Layer 6 - references to detailed logs, not the logs themselves. */
  logReferences: Array<{ path: string; lines: number; summary: string }>;
}

/** How an adapter run was started. */
export type AdapterRunMode =
  /** Fresh work on a new task. */
  | { kind: 'initial'; task: Task }
  /** Read-only verification of existing work, before any write is permitted. */
  | { kind: 'verify'; task: Task; handoff: ContinuityPackage }
  /** Continuing after verification passed. */
  | { kind: 'continue'; task: Task; handoff: ContinuityPackage };

/**
 * The universal adapter contract.
 *
 * Milestone 1 implements the subset needed to prove failover. The wider
 * contract (auth status, model discovery, cancellation, permissions,
 * native session resume, health checks) is deliberately deferred rather
 * than stubbed, so nothing here implies support that does not exist.
 */
export interface AgentAdapter {
  readonly id: string;
  readonly profile: CapabilityProfile;

  /**
   * Run one phase, emitting normalised events. Adapters normalise; they never
   * make routing decisions and never interpret their own failures.
   */
  run(mode: AdapterRunMode): AsyncGenerator<AgentEvent, void, void>;
}

/** Builds the handoff package from observable state only. */
export type ContinuityPackageBuilder = (
  task: Task,
  checkpoint: Checkpoint,
) => ContinuityPackage;
