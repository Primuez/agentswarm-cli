"""Key, config directory and state file handling."""

import json
import os
import re
from typing import Any, Dict, Mapping, Optional
from urllib.parse import urlsplit

from .errors import AUTH, USAGE, CliError

DEFAULT_BASE_URL = "https://agentswarm.space"
_KEY_SHAPE = re.compile(r"[\x21-\x7e]{8,512}")
_LOOPBACK = {"localhost", "127.0.0.1", "::1", "[::1]"}


def config_dir(env: Mapping[str, str]) -> str:
    """~/.config/agentswarm, or $AGENTSWARM_CONFIG_DIR, or $XDG_CONFIG_HOME/agentswarm."""
    if env.get("AGENTSWARM_CONFIG_DIR"):
        return env["AGENTSWARM_CONFIG_DIR"]
    if env.get("XDG_CONFIG_HOME"):
        return os.path.join(env["XDG_CONFIG_HOME"], "agentswarm")
    home = env.get("HOME") or os.path.expanduser("~")
    return os.path.join(home, ".config", "agentswarm")


def key_path(env: Mapping[str, str]) -> str:
    return os.path.join(config_dir(env), "key")


def state_path(env: Mapping[str, str]) -> str:
    return os.path.join(config_dir(env), "state.json")


def is_loopback_host(host: Optional[str]) -> bool:
    return (host or "").lower() in _LOOPBACK


def base_url(env: Mapping[str, str]) -> str:
    """The API origin: https only, except plain http on a loopback host for local testing."""
    raw = env.get("AGENTSWARM_BASE_URL") or DEFAULT_BASE_URL
    try:
        u = urlsplit(raw)
        host = u.hostname
        port = u.port
    except ValueError:
        raise CliError(USAGE, "AGENTSWARM_BASE_URL is not a valid URL")
    if not host or u.scheme not in ("https", "http"):
        raise CliError(USAGE, "AGENTSWARM_BASE_URL is not a valid URL")
    if u.username or u.password:
        raise CliError(USAGE, "AGENTSWARM_BASE_URL must not contain credentials")
    if u.scheme != "https" and not (u.scheme == "http" and is_loopback_host(host)):
        raise CliError(USAGE, "AGENTSWARM_BASE_URL must be https (plain http is allowed only for localhost)")
    netloc = "[%s]" % host if ":" in host else host
    if port is not None and not ((u.scheme == "https" and port == 443) or (u.scheme == "http" and port == 80)):
        netloc += ":%d" % port
    return "%s://%s" % (u.scheme, netloc.lower())


def check_key_shape(key: str, source: str) -> str:
    if not _KEY_SHAPE.fullmatch(key):
        raise CliError(AUTH, "the API key from %s is malformed (expected 8 to 512 printable characters, no spaces)" % source)
    return key


def check_key_file_permissions(path: str) -> None:
    """Refuse a key file that others can read, or that someone else owns (POSIX only)."""
    if os.name == "nt":
        return
    st = os.stat(path)
    import stat as _stat

    if not _stat.S_ISREG(st.st_mode):
        raise CliError(AUTH, "refusing to use %s: not a regular file" % path)
    if st.st_mode & 0o077:
        raise CliError(
            AUTH,
            "refusing to use %s: it is readable by group or others (mode %03o). Fix it with: chmod 600 %s"
            % (path, st.st_mode & 0o777, path),
        )
    if hasattr(os, "getuid") and st.st_uid != os.getuid():
        raise CliError(AUTH, "refusing to use %s: it is owned by another user" % path)


def resolve_key(flag_key: Optional[str], env: Mapping[str, str]) -> Optional[str]:
    """--key, else $AGENTSWARM_API_KEY, else the key file. None when none is set."""
    if flag_key:
        return check_key_shape(flag_key.strip(), "--key")
    if env.get("AGENTSWARM_API_KEY"):
        return check_key_shape(env["AGENTSWARM_API_KEY"].strip(), "AGENTSWARM_API_KEY")
    path = key_path(env)
    if not os.path.exists(path):
        return None
    check_key_file_permissions(path)
    with open(path, "r", encoding="utf-8") as f:
        return check_key_shape(f.read().strip(), path)


def write_private_file(path: str, content: str) -> None:
    """Write a file only its owner can read, atomically."""
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    tmp = "%s.%d.tmp" % (path, os.getpid())
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, content.encode("utf-8"))
    finally:
        os.close(fd)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def write_key_file(env: Mapping[str, str], key: str) -> str:
    path = key_path(env)
    write_private_file(path, key + "\n")
    return path


def read_state(env: Mapping[str, str]) -> Dict[str, Any]:
    try:
        with open(state_path(env), "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def write_state(env: Mapping[str, str], state: Dict[str, Any]) -> None:
    write_private_file(state_path(env), json.dumps(state) + "\n")
