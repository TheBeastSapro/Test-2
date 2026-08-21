/**
 * Per-worker record of consumed replay nonces.
 *
 * Bounded in two directions: entries age out once no live envelope could still
 * carry them, and the total is capped so a flood of junk deliveries cannot
 * grow it without limit.
 */
export class ReplayGuard {
  readonly #seen = new Map<string, number>();

  constructor(
    private readonly retentionMs: number,
    private readonly maxEntries = 10_000,
  ) {}

  has(nonce: string, now: Date = new Date()): boolean {
    this.#prune(now);
    return this.#seen.has(nonce);
  }

  consume(nonce: string, now: Date = new Date()): void {
    this.#prune(now);
    this.#seen.set(nonce, now.getTime());
    // Map preserves insertion order, so the oldest entry is always first.
    while (this.#seen.size > this.maxEntries) {
      const oldest = this.#seen.keys().next();
      if (oldest.done) break;
      this.#seen.delete(oldest.value);
    }
  }

  get size(): number {
    return this.#seen.size;
  }

  #prune(now: Date): void {
    const cutoff = now.getTime() - this.retentionMs;
    for (const [nonce, seenAt] of this.#seen) {
      if (seenAt < cutoff) this.#seen.delete(nonce);
      else break; // insertion-ordered, so the rest are newer
    }
  }
}
