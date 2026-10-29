import fs from 'node:fs';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import { Readable } from 'node:stream';
import { main } from '../src/cli.js';

export const KEY = 'sh_agent_test_0123456789abcdef';

/**
 * A tiny fake agentswarm.space. `routes` maps "METHOD /path" to a handler
 * (req, body) => {status, json?, headers?, text?}. Every request is recorded.
 */
export async function fakeServer(routes) {
  const requests = [];
  const server = http.createServer((req, res) => {
    const chunks = [];
    req.on('data', (c) => chunks.push(c));
    req.on('end', () => {
      const raw = Buffer.concat(chunks);
      const url = new URL(req.url, 'http://x');
      let body = null;
      try {
        body = raw.length ? JSON.parse(raw.toString('utf8')) : null;
      } catch {
        body = raw;
      }
      const entry = { method: req.method, path: url.pathname, query: Object.fromEntries(url.searchParams), headers: req.headers, body, raw };
      requests.push(entry);
      const handler = routes[`${req.method} ${url.pathname}`];
      const out = handler ? handler(entry) : { status: 404, json: { error: 'Not found.' } };
      res.writeHead(out.status ?? 200, { 'content-type': 'application/json', ...(out.headers ?? {}) });
      res.end(out.text ?? (out.json === undefined ? '' : JSON.stringify(out.json)));
    });
  });
  await new Promise((r) => server.listen(0, '127.0.0.1', r));
  const base = `http://127.0.0.1:${server.address().port}`;
  return { base, requests, close: () => new Promise((r) => server.close(r)) };
}

export function tempConfig() {
  return fs.mkdtempSync(path.join(os.tmpdir(), 'agentswarm-test-'));
}

/** Run the CLI in-process and capture its output. */
export async function run(argv, { env = {}, stdin = '', isTTY = false, sleep, now, readSecret } = {}) {
  let stdout = '';
  let stderr = '';
  const io = {
    env: { AGENTSWARM_CONFIG_DIR: env.AGENTSWARM_CONFIG_DIR ?? tempConfig(), ...env },
    stdout: { write: (s) => (stdout += s) },
    stderr: { write: (s) => (stderr += s) },
    stdin: Readable.from(stdin ? [Buffer.from(stdin)] : []),
    stdinIsTTY: isTTY,
    sleep: sleep ?? (async () => {}),
    now,
    readSecret,
  };
  const code = await main(argv, io);
  return { code, stdout, stderr };
}
