import { defineConfig } from 'vitest/config';
import { fileURLToPath } from 'node:url';

const r = (p: string) => fileURLToPath(new URL(p, import.meta.url));

export default defineConfig({
  resolve: {
    alias: {
      // Run tests directly against TypeScript sources so `npm test` works
      // without a prior build. The production build uses the emitted dist/.
      '@agentswitch/contracts': r('./packages/contracts/src/index.ts'),
      '@agentswitch/worker-core': r('./packages/worker-core/src/index.ts'),
      '@agentswitch/crypto': r('./packages/crypto/src/index.ts'),
      '@agentswitch/relay-core': r('./packages/relay-core/src/index.ts'),
    },
  },
  test: {
    include: ['packages/*/test/**/*.test.ts'],
    environment: 'node',
  },
});
