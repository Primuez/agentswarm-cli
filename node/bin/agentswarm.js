#!/usr/bin/env node
import { main } from '../src/cli.js';

const code = await main(process.argv.slice(2), {
  env: process.env,
  stdout: process.stdout,
  stderr: process.stderr,
  stdin: process.stdin,
  stdinIsTTY: !!process.stdin.isTTY,
});
process.exitCode = code;
