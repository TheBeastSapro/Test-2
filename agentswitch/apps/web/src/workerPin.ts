import { WorkerKeyPin } from '@agentswitch/crypto';

/**
 * One pin store for the tab.
 *
 * Module-level and in memory on purpose: a refresh drops every confirmation
 * and the user must compare the fingerprint again. Persisting confirmations
 * would mean trusting a key nobody re-checked.
 */
export const workerPin = new WorkerKeyPin();
