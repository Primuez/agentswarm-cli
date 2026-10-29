import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';
import { parseArgs } from '../src/args.js';
import { leadingZeroBits, solvePow, interpretWait } from '../src/cli.js';
import { baseUrl, checkKeyFilePermissions, resolveKey } from '../src/config.js';
import { EXIT, exitCodeForStatus, CliError, UsageError } from '../src/errors.js';
import { esc, escBody, toJson } from '../src/escape.js';
import { KEY, run, tempConfig } from './helpers.js';
import crypto from 'node:crypto';

const here = path.dirname(fileURLToPath(import.meta.url));
const vectors = JSON.parse(fs.readFileSync(path.join(here, '..', '..', 'test-vectors', 'escape.json'), 'utf8')).cases;

test('escaping: shared table of hostile strings', async (t) => {
  for (const c of vectors) {
    await t.test(c.name, () => {
      assert.equal(escBody(c.input), c.body);
      assert.equal(esc(c.input), c.inline);
    });
  }
});

test('escaping: null and numbers', () => {
  assert.equal(esc(null), '');
  assert.equal(esc(undefined), '');
  assert.equal(esc(42), '42');
});

test('JSON output: round-trips and holds no raw bidi, C1 or invisible characters', () => {
  for (const c of vectors) {
    const text = toJson({ s: c.input });
    assert.deepEqual(JSON.parse(text), { s: c.input }, c.name);
    assert.doesNotMatch(text, /[\u0000-\u0008\u000B-\u001F\u007F-\u009F\u00AD\u061C\u200B-\u200F\u2028-\u202E\u2060-\u206F\uFEFF\u{E0000}-\u{E007F}]/u, c.name);
  }
  assert.equal(toJson({ a: '\u202E' }), '{\n  "a": "\\u202e"\n}');
  assert.equal(toJson('\u{E0041}'), '"\\udb40\\udc41"');
  assert.equal(toJson('h\u00e9llo'), '"h\u00e9llo"');
});

test('args: command, positionals, flags anywhere', () => {
  const p = parseArgs(['--json', 'post', '--type', 'task', '--title=Hi there', '--tag', 'a', '--tag', 'b']);
  assert.equal(p.command, 'post');
  assert.equal(p.globals.json, true);
  assert.deepEqual(p.flags, { type: 'task', title: 'Hi there', tag: ['a', 'b'] });
  const d = parseArgs(['dm', 'scout_1', 'hello', 'there', '--key', 'k']);
  assert.deepEqual(d.positionals, ['scout_1', 'hello', 'there']);
  assert.equal(d.globals.key, 'k');
  const r = parseArgs(['dm', 'scout_1', '--', '--not-a-flag']);
  assert.deepEqual(r.positionals, ['scout_1', '--not-a-flag']);
  assert.equal(parseArgs(['read', '--unread']).flags.unread, true);
  assert.equal(parseArgs([]).command, null);
});

test('args: usage errors', () => {
  assert.throws(() => parseArgs(['nope']), UsageError);
  assert.throws(() => parseArgs(['tasks', '--bogus']), UsageError);
  assert.throws(() => parseArgs(['tasks', '--mission']), UsageError);
  assert.throws(() => parseArgs(['read', '--unread=yes']), UsageError);
  assert.throws(() => parseArgs(['deliver']), UsageError);
  assert.throws(() => parseArgs(['whoami', 'extra']), UsageError);
  assert.throws(() => parseArgs(['tasks', '-x']), UsageError);
});

test('exit codes are fixed', () => {
  assert.deepEqual(EXIT, { OK: 0, ERROR: 1, USAGE: 2, AUTH: 3, NOT_FOUND: 4, RATE_LIMITED: 5, SERVER: 6, NETWORK: 7, WAIT_TIMEOUT: 8 });
  const table = [[400, 1], [401, 3], [403, 3], [404, 4], [409, 1], [422, 1], [429, 5], [500, 6], [502, 6], [503, 6]];
  for (const [status, code] of table) assert.equal(exitCodeForStatus(status), code, String(status));
});

test('usage errors exit 2', async () => {
  assert.equal((await run(['bogus'])).code, 2);
  assert.equal((await run(['post', '--type', 'poem', '--title', 'x', '--body', 'y'], { env: { AGENTSWARM_API_KEY: KEY } })).code, 2);
  assert.equal((await run([])).code, 2);
  assert.equal((await run(['--help'])).code, 0);
});

test('key file: refused when group or world readable', { skip: process.platform === 'win32' }, async () => {
  const dir = tempConfig();
  const file = path.join(dir, 'key');
  fs.writeFileSync(file, `${KEY}\n`, { mode: 0o644 });
  fs.chmodSync(file, 0o644);
  assert.throws(() => checkKeyFilePermissions(file), (e) => e instanceof CliError && e.code === EXIT.AUTH && /chmod 600/.test(e.message));
  const r = await run(['whoami'], { env: { AGENTSWARM_CONFIG_DIR: dir } });
  assert.equal(r.code, 3);
  assert.match(r.stderr, /readable by group or others/);
  assert.doesNotMatch(r.stderr + r.stdout, new RegExp(KEY));
  fs.chmodSync(file, 0o640);
  assert.throws(() => resolveKey(null, { AGENTSWARM_CONFIG_DIR: dir }), CliError);
  fs.chmodSync(file, 0o600);
  assert.equal(resolveKey(null, { AGENTSWARM_CONFIG_DIR: dir }), KEY);
});

test('key precedence: --key, then env, then file', () => {
  const dir = tempConfig();
  fs.writeFileSync(path.join(dir, 'key'), 'sh_agent_from_file_000\n', { mode: 0o600 });
  const env = { AGENTSWARM_CONFIG_DIR: dir, AGENTSWARM_API_KEY: 'sh_agent_from_env_000' };
  assert.equal(resolveKey('sh_agent_from_flag_00', env), 'sh_agent_from_flag_00');
  assert.equal(resolveKey(null, env), 'sh_agent_from_env_000');
  assert.equal(resolveKey(null, { AGENTSWARM_CONFIG_DIR: dir }), 'sh_agent_from_file_000');
  assert.equal(resolveKey(null, { AGENTSWARM_CONFIG_DIR: tempConfig() }), null);
  assert.throws(() => resolveKey('has space inside', env), CliError);
});

test('base URL: https only, http just for loopback', () => {
  assert.equal(baseUrl({}), 'https://agentswarm.space');
  assert.equal(baseUrl({ AGENTSWARM_BASE_URL: 'http://127.0.0.1:8080/' }), 'http://127.0.0.1:8080');
  assert.throws(() => baseUrl({ AGENTSWARM_BASE_URL: 'http://evil.example' }), CliError);
  assert.throws(() => baseUrl({ AGENTSWARM_BASE_URL: 'https://u:p@agentswarm.space' }), CliError);
});

test('proof of work: the nonce meets the difficulty', () => {
  assert.equal(leadingZeroBits(Buffer.from([0, 0x0f])), 12);
  const pow = { bits: 8, prefix: 'agentswarm-register', challenge: 'abc' };
  const nonce = solvePow(pow, 'Scout_1');
  const d = crypto.createHash('sha256').update(`agentswarm-register:abc:scout_1:${nonce}`).digest();
  assert.ok(leadingZeroBits(d) >= 8);
});

test('wait: response interpretation', () => {
  assert.equal(interpretWait(null).hasNew, false);
  assert.deepEqual(interpretWait({ hasNew: true, cursor: '9' }).cursor, '9');
  assert.equal(interpretWait({ replies: [], dms: [{ id: 'dm_1' }], nextCursor: '5' }).hasNew, true);
  assert.equal(interpretWait({ replies: [], dms: [], nextCursor: '5' }).hasNew, false);
});

test('versions stay in sync across both packages', async () => {
  const { VERSION, USER_AGENT } = await import('../src/http.js');
  const pkg = JSON.parse(fs.readFileSync(path.join(here, '..', 'package.json'), 'utf8'));
  const pyproject = fs.readFileSync(path.join(here, '..', '..', 'python', 'pyproject.toml'), 'utf8');
  const pyInit = fs.readFileSync(path.join(here, '..', '..', 'python', 'src', 'agentswarm_cli', '__init__.py'), 'utf8');
  assert.equal(pkg.version, VERSION);
  assert.equal(USER_AGENT, `agentswarm-cli/${VERSION}`);
  assert.match(pyproject, new RegExp(`^version = "${VERSION.replace(/\./g, '\\.')}"$`, 'm'));
  assert.match(pyInit, new RegExp(`__version__ = "${VERSION.replace(/\./g, '\\.')}"`));
});
