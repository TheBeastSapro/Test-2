import { createServer } from 'node:http';
import { demoConfig, runTask } from '@agentswitch/worker-core';
import type { QualityMode } from '@agentswitch/contracts';

/**
 * Milestone 1 control plane.
 *
 * Deliberately tiny, and deliberately dumb. Its whole job here is to prove the
 * boundary: the orchestration in worker-core is transport-agnostic and knows
 * nothing about HTTP, so the same timeline streams identically in a browser
 * and over the wire. It holds no credentials and never will - in the target
 * architecture it relays events and opaque ciphertext, nothing more.
 *
 * The browser demo does NOT depend on this server; it runs worker-core
 * in-process so the demo needs no backend at all.
 */

const PORT = Number(process.env.PORT ?? 8787);
const QUALITY_MODES = new Set<string>(['strict', 'balanced', 'continue_at_any_cost', 'ask_me']);

const server = createServer(async (req, res) => {
  const url = new URL(req.url ?? '/', `http://${req.headers.host ?? 'localhost'}`);

  if (url.pathname === '/health') {
    res.writeHead(200, { 'content-type': 'application/json' });
    res.end(JSON.stringify({ ok: true, milestone: 1 }));
    return;
  }

  if (url.pathname === '/api/demo/stream') {
    const modeParam = url.searchParams.get('mode') ?? 'balanced';
    if (!QUALITY_MODES.has(modeParam)) {
      res.writeHead(400, { 'content-type': 'application/json' });
      res.end(JSON.stringify({ error: `Unknown quality mode: ${modeParam}` }));
      return;
    }

    const pool = (url.searchParams.get('pool') ?? 'sim-alpha,sim-beta,sim-gamma')
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean);

    res.writeHead(200, {
      'content-type': 'application/x-ndjson',
      'cache-control': 'no-store',
    });

    try {
      for await (const event of runTask(
        demoConfig({ qualityMode: modeParam as QualityMode, failoverPool: pool }),
      )) {
        res.write(`${JSON.stringify(event)}\n`);
      }
    } catch (error) {
      res.write(
        `${JSON.stringify({ error: error instanceof Error ? error.message : 'unknown' })}\n`,
      );
    }
    res.end();
    return;
  }

  res.writeHead(404, { 'content-type': 'application/json' });
  res.end(JSON.stringify({ error: 'not found' }));
});

server.listen(PORT, () => {
  console.log(`AgentSwitch control plane (Milestone 1) listening on :${PORT}`);
  console.log(`  GET /health`);
  console.log(`  GET /api/demo/stream?mode=balanced&pool=sim-alpha,sim-beta,sim-gamma`);
});
