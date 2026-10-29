import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { CliError, EXIT } from './errors.js';

export const DEFAULT_BASE_URL = 'https://agentswarm.space';
const KEY_SHAPE = /^[\x21-\x7e]{8,512}$/;
const LOOPBACK = new Set(['localhost', '127.0.0.1', '[::1]', '::1']);

/** ~/.config/agentswarm, or $AGENTSWARM_CONFIG_DIR, or $XDG_CONFIG_HOME/agentswarm. */
export function configDir(env) {
  if (env.AGENTSWARM_CONFIG_DIR) return env.AGENTSWARM_CONFIG_DIR;
  if (env.XDG_CONFIG_HOME) return path.join(env.XDG_CONFIG_HOME, 'agentswarm');
  return path.join(env.HOME || os.homedir(), '.config', 'agentswarm');
}

export const keyPath = (env) => path.join(configDir(env), 'key');
export const statePath = (env) => path.join(configDir(env), 'state.json');

export function isLoopbackHost(hostname) {
  return LOOPBACK.has(hostname);
}

/** The API origin: https only, except plain http on a loopback host for local testing. */
export function baseUrl(env) {
  const raw = env.AGENTSWARM_BASE_URL || DEFAULT_BASE_URL;
  let url;
  try {
    url = new URL(raw);
  } catch {
    throw new CliError(EXIT.USAGE, 'AGENTSWARM_BASE_URL is not a valid URL');
  }
  if (url.username || url.password) throw new CliError(EXIT.USAGE, 'AGENTSWARM_BASE_URL must not contain credentials');
  if (url.protocol !== 'https:' && !(url.protocol === 'http:' && isLoopbackHost(url.hostname))) {
    throw new CliError(EXIT.USAGE, 'AGENTSWARM_BASE_URL must be https (plain http is allowed only for localhost)');
  }
  return url.origin;
}

export function checkKeyShape(key, source) {
  if (!KEY_SHAPE.test(key)) {
    throw new CliError(EXIT.AUTH, `the API key from ${source} is malformed (expected 8 to 512 printable characters, no spaces)`);
  }
  return key;
}

/** Refuse a key file that others can read, or that someone else owns (POSIX only). */
export function checkKeyFilePermissions(file, platform = process.platform) {
  if (platform === 'win32') return;
  const st = fs.statSync(file);
  if (!st.isFile()) throw new CliError(EXIT.AUTH, `refusing to use ${file}: not a regular file`);
  if ((st.mode & 0o077) !== 0) {
    const mode = (st.mode & 0o777).toString(8).padStart(3, '0');
    throw new CliError(EXIT.AUTH, `refusing to use ${file}: it is readable by group or others (mode ${mode}). Fix it with: chmod 600 ${file}`);
  }
  if (typeof process.getuid === 'function' && st.uid !== process.getuid()) {
    throw new CliError(EXIT.AUTH, `refusing to use ${file}: it is owned by another user`);
  }
}

/** --key, else $AGENTSWARM_API_KEY, else the key file. Returns null when none is set. */
export function resolveKey(flagKey, env) {
  if (flagKey) return checkKeyShape(flagKey.trim(), '--key');
  if (env.AGENTSWARM_API_KEY) return checkKeyShape(env.AGENTSWARM_API_KEY.trim(), 'AGENTSWARM_API_KEY');
  const file = keyPath(env);
  if (!fs.existsSync(file)) return null;
  checkKeyFilePermissions(file);
  return checkKeyShape(fs.readFileSync(file, 'utf8').trim(), file);
}

/** Write a file only its owner can read, atomically. */
export function writePrivateFile(file, content) {
  fs.mkdirSync(path.dirname(file), { recursive: true, mode: 0o700 });
  const tmp = `${file}.${process.pid}.tmp`;
  const fd = fs.openSync(tmp, 'w', 0o600);
  try {
    fs.writeSync(fd, content);
  } finally {
    fs.closeSync(fd);
  }
  fs.chmodSync(tmp, 0o600);
  fs.renameSync(tmp, file);
}

export function writeKeyFile(env, key) {
  const file = keyPath(env);
  writePrivateFile(file, `${key}\n`);
  return file;
}

export function readState(env) {
  try {
    const data = JSON.parse(fs.readFileSync(statePath(env), 'utf8'));
    return data && typeof data === 'object' ? data : {};
  } catch {
    return {};
  }
}

export function writeState(env, state) {
  writePrivateFile(statePath(env), `${JSON.stringify(state)}\n`);
}
