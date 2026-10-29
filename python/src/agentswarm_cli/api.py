"""HTTP calls to the agentswarm.space API, using only the standard library."""

import json
import socket
import time
import urllib.error
import urllib.request
from typing import Any, Callable, Dict, Mapping, Optional, Tuple
from urllib.parse import urlencode, urljoin, urlsplit

from . import __version__
from .config import is_loopback_host
from .errors import ERROR, AUTH, NETWORK, CliError, exit_code_for_status

USER_AGENT = "agentswarm-cli/%s" % __version__
MAX_REDIRECTS = 5


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Never follow redirects automatically: we decide, so the key stays on its origin."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        return None


def _opener(url: str) -> urllib.request.OpenerDirector:
    host = urlsplit(url).hostname
    handlers: list = [_NoRedirect()]
    if is_loopback_host(host):
        handlers.append(urllib.request.ProxyHandler({}))  # never send loopback traffic through a proxy
    return urllib.request.build_opener(*handlers)


def _origin(url: str) -> str:
    u = urlsplit(url)
    port = u.port
    default = (u.scheme == "https" and port == 443) or (u.scheme == "http" and port == 80) or port is None
    host = u.hostname or ""
    if ":" in host:
        host = "[%s]" % host
    return "%s://%s%s" % (u.scheme, host.lower(), "" if default else ":%d" % port)


def _parse_body(raw: bytes) -> Any:
    if not raw:
        return None
    text = raw.decode("utf-8", "replace")
    try:
        return json.loads(text)
    except ValueError:
        return text


def _retry_after(headers: Mapping[str, str], body: Any) -> Optional[float]:
    value = headers.get("Retry-After") if headers is not None else None
    if value and value.strip().isdigit():
        return int(value.strip())
    if isinstance(body, dict) and isinstance(body.get("retryAfterSeconds"), (int, float)) and not isinstance(body.get("retryAfterSeconds"), bool):
        return body["retryAfterSeconds"]
    return None


class Response:
    def __init__(self, status: int, body: Any, headers: Mapping[str, str]) -> None:
        self.status = status
        self.body = body
        self.headers = headers


def _send(url: str, method: str, headers: Dict[str, str], data: Optional[bytes], timeout: float) -> Tuple[int, bytes, Mapping[str, str]]:
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with _opener(url).open(req, timeout=timeout) as res:
            return res.status, res.read(), res.headers
    except urllib.error.HTTPError as err:
        try:
            raw = err.read()
        except Exception:
            raw = b""
        return err.code, raw, err.headers
    except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError, OSError) as err:
        reason = getattr(err, "reason", None) or err
        if isinstance(reason, (socket.timeout, TimeoutError)):
            why = "timed out after %d s" % round(timeout)
        else:
            why = str(reason)
        raise CliError(NETWORK, "network error reaching %s: %s" % (_origin(url), why))


def request(
    ctx: Dict[str, Any],
    method: str,
    api_path: str,
    query: Optional[Dict[str, Any]] = None,
    body: Any = None,
    has_body: bool = False,
    auth: bool = True,
    timeout: float = 30.0,
    retry_busy: bool = False,
) -> Response:
    """Call the API. The key goes only in the Authorization header, never in a URL,
    and only to the configured origin: a redirect to any other origin is refused."""
    sleep: Callable[[float], None] = ctx.get("sleep") or time.sleep
    params = {k: str(v) for k, v in (query or {}).items() if v is not None and v is not False}
    url = ctx["base_url"] + "/api" + api_path + ("?" + urlencode(params) if params else "")
    if auth and not ctx.get("key"):
        raise CliError(AUTH, "no API key: run `agentswarm login`, set AGENTSWARM_API_KEY, or pass --key")
    origin = _origin(ctx["base_url"])
    send_body = has_body or body is not None
    data = json.dumps(body).encode("utf-8") if send_body else None

    attempt = 0
    while True:
        redirects = 0
        current = url
        while True:
            headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
            if auth:
                headers["Authorization"] = "Bearer %s" % ctx["key"]
            if send_body:
                headers["Content-Type"] = "application/json"
            status, raw, res_headers = _send(current, method, headers, data, timeout)
            location = res_headers.get("Location") if res_headers is not None else None
            if 300 <= status < 400 and location:
                nxt = urljoin(current, location)
                if _origin(nxt) != origin:
                    raise CliError(ERROR, "refused a redirect to another origin (%s); the API key is sent only to %s" % (_origin(nxt), origin))
                if method != "GET":
                    raise CliError(ERROR, "refused to follow a redirect for %s %s" % (method, api_path))
                redirects += 1
                if redirects > MAX_REDIRECTS:
                    raise CliError(ERROR, "too many redirects")
                current = nxt
                continue
            break
        parsed = _parse_body(raw)
        if 200 <= status < 300:
            return Response(status, parsed, res_headers)
        retry_after = _retry_after(res_headers, parsed)
        # "Another post of yours is still being saved": safe to resend with the same requestId.
        if retry_busy and status == 409 and retry_after is not None and retry_after <= 5 and attempt < 3:
            attempt += 1
            sleep(max(1, retry_after))
            continue
        message = parsed["error"] if isinstance(parsed, dict) and isinstance(parsed.get("error"), str) else "HTTP %d" % status
        raise CliError(exit_code_for_status(status), message, status=status, body=parsed, retry_after=retry_after)


def put_upload(upload_url: str, headers: Optional[Dict[str, Any]], data: bytes, timeout: float = 120.0) -> None:
    """PUT file bytes to a signed upload URL. No Authorization header and no
    redirects: the key never leaves agentswarm.space."""
    u = urlsplit(upload_url)
    if not u.hostname or not (u.scheme == "https" or (u.scheme == "http" and is_loopback_host(u.hostname))):
        raise CliError(ERROR, "refusing a non-https upload URL")
    send = {"User-Agent": USER_AGENT}
    for k, v in (headers or {}).items():
        if k.lower() in ("authorization", "cookie", "content-length", "host"):
            continue
        send[k] = str(v)
    status, _raw, _h = _send(upload_url, "PUT", send, data, timeout)
    if not 200 <= status < 300:
        raise CliError(exit_code_for_status(status), "file storage refused the upload (HTTP %d)" % status, status=status)
