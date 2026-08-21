import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath } from 'node:url';

const r = (p: string) => fileURLToPath(new URL(p, import.meta.url));

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      // Resolve workspace packages to source so `npm run dev` works without a
      // prior library build. The typecheck step uses the emitted d.ts files.
      '@agentswitch/contracts': r('../../packages/contracts/src/index.ts'),
      '@agentswitch/worker-core': r('../../packages/worker-core/src/index.ts'),
      '@agentswitch/crypto': r('../../packages/crypto/src/index.ts'),
    },
  },
  // The control plane is same-origin through this proxy, so there is no CORS
  // preflight and no opportunity to widen origins later by accident.
  server: { proxy: { '/api': 'http://127.0.0.1:8787' } },
  preview: { proxy: { '/api': 'http://127.0.0.1:8787' } },
});
