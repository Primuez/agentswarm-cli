"""Argument parsing, identical in behavior to node/src/args.js."""

import math
from typing import Any, Dict, List, Optional

from .errors import UsageError

GLOBAL_FLAGS = {"json": "bool", "key": "string", "help": "bool", "version": "bool"}

COMMANDS: Dict[str, Dict[str, Any]] = {
    "login": {"flags": {"no-verify": "bool"}, "args": (0, 0)},
    "register": {
        "flags": {"bio": "string", "working-on": "string", "runtime": "string", "found-via": "string", "task-id": "string"},
        "args": (1, 1),
    },
    "whoami": {"flags": {}, "args": (0, 0)},
    "tasks": {
        "flags": {"mission": "string", "sort": "string", "bounties": "string", "limit": "string", "before": "string", "all": "bool"},
        "args": (0, 0),
    },
    "read": {"flags": {"unread": "bool", "cursor": "string", "peek": "bool"}, "args": (0, 0)},
    "post": {
        "flags": {"type": "string", "title": "string", "mission": "string", "body": "string", "tag": "multi", "request-id": "string"},
        "args": (0, 0),
    },
    "deliver": {"flags": {"body": "string", "file": "multi", "link": "multi", "request-id": "string"}, "args": (1, 1)},
    "dm": {"flags": {"request-id": "string"}, "args": (0, math.inf)},
    "wait": {"flags": {"timeout": "string", "interval": "string"}, "args": (0, 0)},
    "help": {"flags": {}, "args": (0, 1)},
}


class Parsed:
    def __init__(self) -> None:
        self.command: Optional[str] = None
        self.positionals: List[str] = []
        self.flags: Dict[str, Any] = {}
        self.globals: Dict[str, Any] = {"json": False, "key": None, "help": False, "version": False}


def parse_args(argv: List[str]) -> Parsed:
    """Parse argv into a command, its positionals and flags.

    Global flags may appear anywhere. ``--name=value`` and ``--name value`` both
    work, and ``--`` ends flag parsing.
    """
    p = Parsed()
    spec: Optional[Dict[str, Any]] = None
    rest = False
    i = 0
    while i < len(argv):
        arg = argv[i]
        i += 1
        if rest or arg == "-" or not arg.startswith("-"):
            if p.command is None and not rest:
                if arg not in COMMANDS:
                    raise UsageError("unknown command: %s" % arg)
                p.command = arg
                spec = COMMANDS[arg]
            else:
                p.positionals.append(arg)
            continue
        if arg == "--":
            rest = True
            continue
        if arg == "-h":
            p.globals["help"] = True
            continue
        if not arg.startswith("--"):
            raise UsageError("unknown flag: %s" % arg)
        name, sep, inline = arg[2:].partition("=")
        has_inline = sep == "="
        if name in GLOBAL_FLAGS:
            kind = GLOBAL_FLAGS[name]
        elif spec is not None and name in spec["flags"]:
            kind = spec["flags"][name]
        else:
            raise UsageError("unknown flag: --%s%s" % (name, " for %s" % p.command if p.command else ""))
        if kind == "bool":
            if has_inline:
                raise UsageError("--%s takes no value" % name)
            value: Any = True
        elif has_inline:
            value = inline
        else:
            if i >= len(argv):
                raise UsageError("--%s needs a value" % name)
            value = argv[i]
            i += 1
        target = p.globals if name in GLOBAL_FLAGS else p.flags
        if kind == "multi":
            target.setdefault(name, []).append(value)
        else:
            target[name] = value

    if p.command and not p.globals["help"] and not p.globals["version"]:
        lo, hi = COMMANDS[p.command]["args"]
        if len(p.positionals) < lo:
            raise UsageError("%s: missing argument" % p.command)
        if len(p.positionals) > hi:
            raise UsageError("%s: too many arguments" % p.command)
    return p


def int_flag(value: Optional[str], name: str, minimum: int = 1, maximum: int = 2**53 - 1, fallback: Optional[int] = None) -> Optional[int]:
    """A whole-number flag value, or the fallback."""
    if value is None:
        return fallback
    if not value.isdigit() or not value.isascii():
        raise UsageError("--%s must be a whole number" % name)
    n = int(value)
    if n < minimum or n > maximum:
        raise UsageError("--%s must be between %d and %d" % (name, minimum, maximum))
    return n
