import { createServer, type IncomingMessage, type ServerResponse } from 'node:http';
import { demoConfig, runTask } from '@agentswitch/worker-core';
import { EnvelopeRelay } from '@agentswitch/relay-core';
import {
  DeliveryReceiptSchema,
  MAX_ENVELOPE_JSON_BYTES,
  type QualityMode,
} from '@agentswitch/contracts';

/**
 * AgentSwitch control plane (Milestone 2A).
 *
 * Two hard rules this file exists to enforce:
 *
 *  1. It has no private key and imports no crypto library. There is no code
 *     path here that could decrypt a credential, by construction rather than
 *     by policy.
 *  2. It never logs a request or response body. The logger below records
 *     method, path, status and byte counts only - so an encrypted or (through
 *     some future bug) unencrypted credential field cannot reach a log line.
 */

const PORT = Number(process.env.PORT ?? 8787);
const QUALITY_MODES = new Set(['strict', 'balanced', 'continue_at_any_cost', 'ask_me']);
const MAX_BODY_BYTES = MAX_ENVELOPE_JSON_BYTES;

const relay = new EnvelopeRelay();

/** Coarse by design: a precise error is an oracle. */
function fail(res: ServerResponse, status: number, reason: string): void {
  res.writeHead(status, { 'content-type': 'application/json' });
  res.end(JSON.stringify({ ok: false, reason }));
}

function ok(res: ServerResponse, body: unknown, status = 200): void {
  res.writeHead(status, { 'content-type': 'application/json' });
  res.end(JSON.stringify(body));
}

/**
 * Reads a JSON body with a hard byte ceiling, aborting the moment the limit is
 * crossed rather than buffering an oversized payload first.
 */
async function readJson(
  req: IncomingMessage,
): Promise<{ ok: true; value: unknown; bytes: number } | { ok: false; reason: string }> {
  return new Promise((resolve) => {
    let bytes = 0;
    const chunks: Buffer[] = [];
    let settled = false;

    const finish = (result: Awaited<ReturnType<typeof readJson>>) => {
      if (settled) return;
      settled = true;
      resolve(result);
    };

    req.on('data', (chunk: Buffer) => {
      bytes += chunk.length;
      if (bytes > MAX_BODY_BYTES) {
        req.destroy();
        finish({ ok: false, reason: 'too_large' });
        return;
      }
      chunks.push(chunk);
    });
    req.on('error', () => finish({ ok: false, reason: 'malformed' }));
    req.on('end', () => {
      try {
        finish({ ok: true, value: JSON.parse(Buffer.concat(chunks).toString('utf8')), bytes });
      } catch {
        finish({ ok: false, reason: 'malformed' });
      }
    });
  });
}

const server = createServer(async (req, res) => {
  const url = new URL(req.url ?? '/', `http://${req.headers.host ?? 'localhost'}`);
  const path = url.pathname;
  const method = req.method ?? 'GET';

  // Bodies are never touched here. Path, method, status and size only.
  res.on('finish', () => {
    const bytes = Number(res.getHeader('content-length') ?? 0);
    console.log(`${method} ${path} -> ${res.statusCode} (${bytes}b out)`);
  });

  try {
    if (path === '/health') return ok(res, { ok: true, milestone: '2A' });

    /* ---- worker identity: public keys only ---- */

    if (path === '/api/workers' && method === 'GET') {
      return ok(res, { workers: relay.listWorkers() });
    }

    if (path === '/api/workers/register' && method === 'POST') {
      const body = await readJson(req);
      if (!body.ok) return fail(res, 400, body.reason);
      const identity = relay.registerWorker(body.value);
      if (!identity) return fail(res, 400, 'malformed');
      return ok(res, { worker: identity });
    }

    if (path === '/api/workers/heartbeat' && method === 'POST') {
      const body = await readJson(req);
      if (!body.ok) return fail(res, 400, body.reason);
      const workerId = (body.value as { workerId?: unknown })?.workerId;
      if (typeof workerId !== 'string' || !relay.heartbeat(workerId)) {
        return fail(res, 404, 'unknown_worker');
      }
      return ok(res, { ok: true });
    }

    /* ---- envelopes: opaque ciphertext in, receipts out ---- */

    if (path === '/api/envelopes' && method === 'POST') {
      const body = await readJson(req);
      if (!body.ok) return fail(res, body.reason === 'too_large' ? 413 : 400, body.reason);
      const result = relay.submit(body.value, body.bytes);
      if (!result.ok) return fail(res, 400, result.rejection);
      return ok(res, { ok: true, envelopeId: result.envelopeId }, 202);
    }

    if (path === '/api/envelopes' && method === 'GET') {
      const workerId = url.searchParams.get('workerId');
      if (!workerId) return fail(res, 400, 'malformed');
      return ok(res, { envelopes: relay.fetchFor(workerId) });
    }

    if (path === '/api/envelopes/ack' && method === 'POST') {
      const body = await readJson(req);
      if (!body.ok) return fail(res, 400, body.reason);
      const parsed = DeliveryReceiptSchema.safeParse(
        (body.value as { receipt?: unknown })?.receipt,
      );
      if (!parsed.success) return fail(res, 400, 'malformed');
      const receipt = parsed.data;
      if (!relay.acknowledge(receipt.envelopeId, receipt.workerId, receipt)) {
        return fail(res, 404, 'unknown_envelope');
      }
      return ok(res, { ok: true });
    }

    if (path === '/api/receipt' && method === 'GET') {
      const envelopeId = url.searchParams.get('envelopeId');
      if (!envelopeId) return fail(res, 400, 'malformed');
      return ok(res, { receipt: relay.receipt(envelopeId) });
    }

    /* ---- Milestone 1 failover demo ---- */

    if (path === '/api/demo/stream') {
      const mode = url.searchParams.get('mode') ?? 'balanced';
      if (!QUALITY_MODES.has(mode)) return fail(res, 400, 'malformed');

      const pool = (url.searchParams.get('pool') ?? 'sim-alpha,sim-beta,sim-gamma')
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean);

      res.writeHead(200, { 'content-type': 'application/x-ndjson', 'cache-control': 'no-store' });
      for await (const event of runTask(
        demoConfig({ qualityMode: mode as QualityMode, failoverPool: pool }),
      )) {
        res.write(`${JSON.stringify(event)}\n`);
      }
      res.end();
      return;
    }

    return fail(res, 404, 'not_found');
  } catch {
    // Never surface an exception message: it can echo input.
    if (!res.headersSent) return fail(res, 500, 'internal_error');
    res.end();
    return;
  }
});

// Expired ciphertext is deleted whether or not a worker ever collected it.
setInterval(() => relay.sweep(), 5_000).unref();

server.listen(PORT, () => {
  console.log(`AgentSwitch control plane (Milestone 2A) listening on :${PORT}`);
  console.log('  This process holds no private key and cannot decrypt any envelope.');
});
