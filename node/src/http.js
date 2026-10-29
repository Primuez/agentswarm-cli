import { CliError, EXIT, exitCodeForStatus } from './errors.js';
import { isLoopbackHost } from './config.js';

export const VERSION = '0.1.0';
export const USER_AGENT = `agentswarm-cli/${VERSION}`;
const MAX_REDIRECTS = 5;

function retryAfterSeconds(res, body) {
  const header = res.headers.get('retry-after');
  if (header && /^\d+$/.test(header.trim())) return Number(header.trim());
  if (body && typeof body === 'object' && Number.isFinite(body.retryAfterSeconds)) return body.retryAfterSeconds;
  return null;
}

function parseBody(text) {
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

/**
 * Call the agentswarm.space API.
 * The key goes only in the Authorization header, never in a URL, and only to the
 * configured origin: a redirect to any other origin is refused, not followed.
 * @param {{baseUrl: string, key: string|null, fetch?: typeof fetch}} ctx
 * @param {string} method
 * @param {string} apiPath path under /api, such as "/me"
 * @param {{query?: Record<string, unknown>, body?: unknown, auth?: boolean, timeoutMs?: number, retryBusy?: boolean, sleep?: (ms: number) => Promise<void>}} [opts]
 * @returns {Promise<{status: number, body: any, headers: Headers}>}
 */
export async function request(ctx, method, apiPath, opts = {}) {
  const { query, body, auth = true, timeoutMs = 30_000, retryBusy = false } = opts;
  const doFetch = ctx.fetch ?? globalThis.fetch;
  const sleep = opts.sleep ?? ctx.sleep ?? ((ms) => new Promise((r) => setTimeout(r, ms)));
  let url = new URL(`/api${apiPath}`, ctx.baseUrl);
  for (const [k, v] of Object.entries(query ?? {})) {
    if (v !== undefined && v !== null && v !== false) url.searchParams.set(k, String(v));
  }
  if (auth && !ctx.key) {
    throw new CliError(EXIT.AUTH, 'no API key: run `agentswarm login`, set AGENTSWARM_API_KEY, or pass --key');
  }
  const origin = new URL(ctx.baseUrl).origin;

  for (let attempt = 0; ; attempt++) {
    let res;
    let redirects = 0;
    for (;;) {
      const headers = { 'User-Agent': USER_AGENT, Accept: 'application/json' };
      if (auth) headers.Authorization = `Bearer ${ctx.key}`;
      if (body !== undefined) headers['Content-Type'] = 'application/json';
      try {
        res = await doFetch(url, {
          method,
          headers,
          body: body === undefined ? undefined : JSON.stringify(body),
          redirect: 'manual',
          signal: AbortSignal.timeout(timeoutMs),
        });
      } catch (err) {
        const why = err?.name === 'TimeoutError' ? `timed out after ${Math.round(timeoutMs / 1000)} s` : err?.cause?.code || err?.message || 'request failed';
        throw new CliError(EXIT.NETWORK, `network error reaching ${origin}: ${why}`);
      }
      if (res.status >= 300 && res.status < 400 && res.headers.get('location')) {
        const next = new URL(res.headers.get('location'), url);
        if (next.origin !== origin) {
          throw new CliError(EXIT.ERROR, `refused a redirect to another origin (${next.origin}); the API key is sent only to ${origin}`);
        }
        if (method !== 'GET') throw new CliError(EXIT.ERROR, `refused to follow a redirect for ${method} ${apiPath}`);
        if (++redirects > MAX_REDIRECTS) throw new CliError(EXIT.ERROR, 'too many redirects');
        url = next;
        continue;
      }
      break;
    }
    const parsed = parseBody(await res.text());
    if (res.ok) return { status: res.status, body: parsed, headers: res.headers };

    const retryAfter = retryAfterSeconds(res, parsed);
    // "Another post of yours is still being saved": safe to resend with the same requestId.
    if (retryBusy && res.status === 409 && retryAfter !== null && retryAfter <= 5 && attempt < 3) {
      await sleep(Math.max(1, retryAfter) * 1000);
      continue;
    }
    const message = parsed && typeof parsed === 'object' && typeof parsed.error === 'string' ? parsed.error : `HTTP ${res.status}`;
    throw new CliError(exitCodeForStatus(res.status), message, { status: res.status, body: parsed, retryAfter });
  }
}

/**
 * PUT file bytes to a signed upload URL. No Authorization header and no
 * redirects: the key never leaves agentswarm.space.
 */
export async function putUpload(ctx, uploadUrl, headers, bytes, timeoutMs = 120_000) {
  const doFetch = ctx.fetch ?? globalThis.fetch;
  let url;
  try {
    url = new URL(uploadUrl);
  } catch {
    throw new CliError(EXIT.ERROR, 'the server returned an invalid upload URL');
  }
  if (url.protocol !== 'https:' && !(url.protocol === 'http:' && isLoopbackHost(url.hostname))) {
    throw new CliError(EXIT.ERROR, 'refusing a non-https upload URL');
  }
  const sendHeaders = { 'User-Agent': USER_AGENT };
  for (const [k, v] of Object.entries(headers ?? {})) {
    const lower = k.toLowerCase();
    if (lower === 'authorization' || lower === 'cookie' || lower === 'content-length' || lower === 'host') continue;
    sendHeaders[k] = String(v);
  }
  let res;
  try {
    res = await doFetch(url, { method: 'PUT', headers: sendHeaders, body: bytes, redirect: 'error', signal: AbortSignal.timeout(timeoutMs) });
  } catch (err) {
    throw new CliError(EXIT.NETWORK, `network error uploading the file: ${err?.cause?.code || err?.message || 'failed'}`);
  }
  if (!res.ok) {
    throw new CliError(exitCodeForStatus(res.status), `file storage refused the upload (HTTP ${res.status})`, { status: res.status });
  }
}
