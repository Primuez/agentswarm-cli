import io
import json
import os
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qsl, urlsplit

import sys

# Run the tests from a checkout without installing the package.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from agentswarm_cli.cli import IO, main  # noqa: E402

KEY = "sh_agent_test_0123456789abcdef"


class FakeServer:
    """A tiny fake agentswarm.space. routes maps "METHOD /path" to a handler
    (request dict) -> dict(status=, json=, headers=, text=). Every request is recorded."""

    def __init__(self, routes):
        self.routes = routes
        self.requests = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _handle(self):
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length) if length else b""
                u = urlsplit(self.path)
                try:
                    body = json.loads(raw.decode("utf-8")) if raw else None
                except ValueError:
                    body = raw
                entry = {
                    "method": self.command,
                    "path": u.path,
                    "query": dict(parse_qsl(u.query)),
                    "headers": {k.lower(): v for k, v in self.headers.items()},
                    "body": body,
                    "raw": raw,
                }
                outer.requests.append(entry)
                handler = outer.routes.get("%s %s" % (self.command, u.path))
                out = handler(entry) if handler else {"status": 404, "json": {"error": "Not found."}}
                if "text" in out:
                    payload = out["text"].encode("utf-8")
                elif out.get("json") is None:
                    payload = b""
                else:
                    payload = json.dumps(out["json"]).encode("utf-8")
                self.send_response(out.get("status", 200))
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                for k, v in (out.get("headers") or {}).items():
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(payload)

            do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = _handle

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base = "http://127.0.0.1:%d" % self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        self.thread.start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def temp_config():
    return tempfile.mkdtemp(prefix="agentswarm-test-")


class Result:
    def __init__(self, code, stdout, stderr):
        self.code = code
        self.stdout = stdout
        self.stderr = stderr


def run(argv, env=None, stdin="", is_tty=False, sleep=None, now=None, read_secret=None):
    env = dict(env or {})
    env.setdefault("AGENTSWARM_CONFIG_DIR", temp_config())
    out, err = io.StringIO(), io.StringIO()
    the_io = IO(
        env=env,
        stdout=out,
        stderr=err,
        stdin=io.BytesIO(stdin.encode("utf-8")),
        stdin_is_tty=is_tty,
        sleep=sleep or (lambda s: None),
        now=now,
        read_secret=read_secret,
    )
    code = main(argv, the_io)
    return Result(code, out.getvalue(), err.getvalue())


VECTORS = os.path.join(os.path.dirname(__file__), "..", "..", "test-vectors", "escape.json")
