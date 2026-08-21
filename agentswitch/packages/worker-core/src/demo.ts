import type { Task } from '@agentswitch/contracts';
import { createAllSimAdapters } from './sim-adapters.js';
import type { RunTaskConfig } from './orchestrator.js';

/**
 * The Milestone 1 demo scenario, shared by the browser demo, the control
 * plane and the tests so all three exercise exactly the same path.
 */
export const DEMO_TASK: Task = {
  id: 'task-demo-1',
  objective: 'Add retry handling with exponential backoff to the API client',
  taskClass: 'multi_file_implementation',
  qualityMode: 'balanced',
  // Only a capability gate that every sim adapter passes, so that when
  // sim-gamma is rejected it is rejected by the quality floor and nothing else.
  requiredCapabilities: ['multiFileEditing'],
  estimatedContextTokens: 32_000,
  workspacePath: '/workspace/demo',
};

export interface DemoScenario {
  qualityMode: Task['qualityMode'];
  /** Which adapters the router may consider as replacements. */
  failoverPool: string[];
}

export function demoConfig(scenario: DemoScenario): RunTaskConfig {
  return {
    task: { ...DEMO_TASK, qualityMode: scenario.qualityMode },
    adapters: createAllSimAdapters(),
    startingAdapterId: 'sim-alpha',
    failoverPool: [...scenario.failoverPool],
  };
}
