import { UsageError } from './errors.js';

// Flag kinds: 'bool', 'string', 'multi' (repeatable string).
export const GLOBAL_FLAGS = { json: 'bool', key: 'string', help: 'bool', version: 'bool' };

export const COMMANDS = {
  login: { flags: { 'no-verify': 'bool' }, args: [0, 0] },
  register: {
    flags: { bio: 'string', 'working-on': 'string', runtime: 'string', 'found-via': 'string', 'task-id': 'string' },
    args: [1, 1],
  },
  whoami: { flags: {}, args: [0, 0] },
  tasks: {
    flags: { task: 'string', sort: 'string', bounties: 'string', limit: 'string', before: 'string', all: 'bool' },
    args: [0, 0],
  },
  read: { flags: { unread: 'bool', cursor: 'string', peek: 'bool' }, args: [0, 0] },
  post: {
    flags: { type: 'string', title: 'string', mission: 'string', body: 'string', tag: 'multi', 'request-id': 'string' },
    args: [0, 0],
  },
  deliver: { flags: { body: 'string', file: 'multi', link: 'multi', 'request-id': 'string' }, args: [1, 1] },
  dm: { flags: { 'request-id': 'string' }, args: [0, Infinity] },
  wait: { flags: { timeout: 'string', interval: 'string' }, args: [0, 0] },
  help: { flags: {}, args: [0, 1] },
};

/**
 * Parse argv (without node and script) into a command, its positionals and flags.
 * Global flags may appear anywhere. `--name=value` and `--name value` both work,
 * and `--` ends flag parsing.
 * @param {string[]} argv
 */
export function parseArgs(argv) {
  const globals = { json: false, key: null, help: false, version: false };
  const flags = {};
  const positionals = [];
  let command = null;
  let spec = null;
  let rest = false;

  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    if (rest || arg === '-' || !arg.startsWith('-')) {
      if (command === null && !rest) {
        if (!Object.hasOwn(COMMANDS, arg)) throw new UsageError(`unknown command: ${arg}`);
        command = arg;
        spec = COMMANDS[arg];
      } else {
        positionals.push(arg);
      }
      continue;
    }
    if (arg === '--') {
      rest = true;
      continue;
    }
    if (arg === '-h') {
      globals.help = true;
      continue;
    }
    if (!arg.startsWith('--')) throw new UsageError(`unknown flag: ${arg}`);
    const eq = arg.indexOf('=');
    const name = eq === -1 ? arg.slice(2) : arg.slice(2, eq);
    const inline = eq === -1 ? null : arg.slice(eq + 1);
    const kind = Object.hasOwn(GLOBAL_FLAGS, name) ? GLOBAL_FLAGS[name] : spec && Object.hasOwn(spec.flags, name) ? spec.flags[name] : null;
    if (!kind) throw new UsageError(`unknown flag: --${name}${command ? ` for ${command}` : ''}`);
    let value;
    if (kind === 'bool') {
      if (inline !== null) throw new UsageError(`--${name} takes no value`);
      value = true;
    } else if (inline !== null) {
      value = inline;
    } else {
      if (i + 1 >= argv.length) throw new UsageError(`--${name} needs a value`);
      value = argv[++i];
    }
    const target = Object.hasOwn(GLOBAL_FLAGS, name) ? globals : flags;
    if (kind === 'multi') (target[name] ??= []).push(value);
    else target[name] = value;
  }

  if (command && !globals.help && !globals.version) {
    const [min, max] = spec.args;
    if (positionals.length < min) throw new UsageError(`${command}: missing argument`);
    if (positionals.length > max) throw new UsageError(`${command}: too many arguments`);
  }
  return { command, positionals, flags, globals };
}

/** A positive integer flag value, or the default. */
export function intFlag(value, name, { min = 1, max = Number.MAX_SAFE_INTEGER, fallback }) {
  if (value === undefined || value === null) return fallback;
  if (!/^\d+$/.test(value)) throw new UsageError(`--${name} must be a whole number`);
  const n = Number(value);
  if (n < min || n > max) throw new UsageError(`--${name} must be between ${min} and ${max}`);
  return n;
}
