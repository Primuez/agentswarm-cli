// Fixed exit codes, shared with the Python package and documented in README.md.
export const EXIT = Object.freeze({
  OK: 0,
  ERROR: 1,
  USAGE: 2,
  AUTH: 3,
  NOT_FOUND: 4,
  RATE_LIMITED: 5,
  SERVER: 6,
  NETWORK: 7,
  WAIT_TIMEOUT: 8,
});

/** Exit code for an HTTP error status. */
export function exitCodeForStatus(status) {
  if (status === 401 || status === 403) return EXIT.AUTH;
  if (status === 404) return EXIT.NOT_FOUND;
  if (status === 429) return EXIT.RATE_LIMITED;
  if (status >= 500 && status <= 599) return EXIT.SERVER;
  return EXIT.ERROR;
}

/** An error that ends the command with a fixed exit code. */
export class CliError extends Error {
  /**
   * @param {number} code exit code
   * @param {string} message message for stderr (escaped before printing)
   * @param {{status?: number, body?: unknown, retryAfter?: number|null}} [extra]
   */
  constructor(code, message, extra = {}) {
    super(message);
    this.code = code;
    this.status = extra.status ?? null;
    this.body = extra.body ?? null;
    this.retryAfter = extra.retryAfter ?? null;
  }
}

export class UsageError extends CliError {
  constructor(message) {
    super(EXIT.USAGE, message);
  }
}
