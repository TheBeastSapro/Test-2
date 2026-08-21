import type {
  AgentEvent,
  Checkpoint,
  ContinuityPackage,
  Task,
} from '@agentswitch/contracts';

/**
 * Accumulates observable state as events stream past. Only what actually
 * happened on disk and in the test runner - never hidden reasoning, which is
 * not portable across providers and must not be implied to be.
 */
export class ObservedState {
  readonly #files = new Map<string, { added: number; removed: number }>();
  readonly #commands: string[] = [];
  #lastTest: { passed: number; failed: number; failing: string[] } | null = null;

  record(event: AgentEvent): void {
    switch (event.type) {
      case 'file_change': {
        const current = this.#files.get(event.path) ?? { added: 0, removed: 0 };
        this.#files.set(event.path, {
          added: current.added + event.added,
          removed: current.removed + event.removed,
        });
        break;
      }
      case 'command_run':
        this.#commands.push(event.command);
        break;
      case 'test_result':
        this.#lastTest = {
          passed: event.passed,
          failed: event.failed,
          failing: [...event.failing],
        };
        break;
      default:
        break;
    }
  }

  get lastTest(): { passed: number; failed: number; failing: string[] } | null {
    return this.#lastTest;
  }

  /** Sorted by path so a checkpoint is byte-identical for identical work. */
  filesChanged(): Array<{ path: string; added: number; removed: number }> {
    return [...this.#files.entries()]
      .map(([path, counts]) => ({ path, ...counts }))
      .sort((a, b) => a.path.localeCompare(b.path));
  }

  commandsRun(): string[] {
    return [...this.#commands];
  }
}

export function buildCheckpoint(
  task: Task,
  observed: ObservedState,
  sequence: number,
  createdAfterEventSeq: number,
): Checkpoint {
  const lastTest = observed.lastTest;
  const remainingWork: string[] = [];

  if (lastTest && lastTest.failed > 0) {
    for (const name of lastTest.failing) {
      remainingWork.push(`Fix failing test: ${name}`);
    }
  }
  remainingWork.push(`Complete the objective: ${task.objective}`);

  return {
    taskId: task.id,
    sequence,
    objective: task.objective,
    createdAfterEventSeq,
    filesChanged: observed.filesChanged(),
    commandsRun: observed.commandsRun(),
    lastTestResult: lastTest ? { passed: lastTest.passed, failed: lastTest.failed } : null,
    remainingWork,
  };
}

/**
 * The layered handoff package. Note what it does NOT contain: file contents.
 * The replacement is already in the same worktree and reads what it needs with
 * its own tools, which is what keeps a cross-provider handoff cheap.
 */
export function buildContinuityPackage(task: Task, checkpoint: Checkpoint): ContinuityPackage {
  return {
    // Layer 1 - mission, never truncated.
    objective: task.objective,
    constraints: [],
    // Layer 2 - ground truth: paths and counts only.
    workspacePath: task.workspacePath,
    filesChanged: checkpoint.filesChanged.map((f) => ({ ...f })),
    // Layer 3 - progress.
    completedWork: checkpoint.filesChanged.map(
      (f) => `Edited ${f.path} (+${f.added}/-${f.removed})`,
    ),
    remainingWork: [...checkpoint.remainingWork],
    // Layer 4 - decisions and dead ends. Extracting these from a transcript is
    // Milestone 3 work; leaving them empty is honest, inventing them is not.
    decisions: [],
    rejectedApproaches: [],
    // Layer 5 - test status.
    lastTestResult: checkpoint.lastTestResult,
    // Layer 6 - references, not content.
    logReferences: [],
  };
}
