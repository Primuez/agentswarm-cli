import hashlib
import json
import os
import re
import stat
import unittest

from helpers import KEY, VECTORS, run, temp_config

from agentswarm_cli.args import parse_args
from agentswarm_cli.cli import interpret_wait, leading_zero_bits, solve_pow
from agentswarm_cli.config import base_url, check_key_file_permissions, resolve_key
from agentswarm_cli.errors import AUTH, EXIT_CODES, CliError, UsageError, exit_code_for_status
from agentswarm_cli.escape import esc, esc_body, to_json

with open(VECTORS, encoding="utf-8") as f:
    CASES = json.load(f)["cases"]

RAW_DANGER = re.compile("[\\x00-\\x08\\x0b-\\x1f\\x7f-\\x9f\\u00ad\\u061c\\u200b-\\u200f\\u2028-\\u202e\\u2060-\\u206f\\ufeff\\U000e0000-\\U000e007f\\ud800-\\udfff]")


class EscapeTest(unittest.TestCase):
    def test_shared_vectors(self):
        for case in CASES:
            with self.subTest(case["name"]):
                self.assertEqual(esc_body(case["input"]), case["body"])
                self.assertEqual(esc(case["input"]), case["inline"])

    def test_none_and_numbers(self):
        self.assertEqual(esc(None), "")
        self.assertEqual(esc(42), "42")

    def test_json_round_trips_without_raw_dangerous_chars(self):
        for case in CASES:
            with self.subTest(case["name"]):
                text = to_json({"s": case["input"]})
                self.assertEqual(json.loads(text), {"s": case["input"]})
                self.assertIsNone(RAW_DANGER.search(text))
        self.assertEqual(to_json({"a": "\u202e"}), '{\n  "a": "\\u202e"\n}')
        self.assertEqual(to_json(chr(0xE0041)), '"\\udb40\\udc41"')
        self.assertEqual(to_json("h\u00e9llo"), '"h\u00e9llo"')


class ArgsTest(unittest.TestCase):
    def test_parse(self):
        p = parse_args(["--json", "post", "--type", "task", "--title=Hi there", "--tag", "a", "--tag", "b"])
        self.assertEqual(p.command, "post")
        self.assertTrue(p.globals["json"])
        self.assertEqual(p.flags, {"type": "task", "title": "Hi there", "tag": ["a", "b"]})
        d = parse_args(["dm", "scout_1", "hello", "there", "--key", "k"])
        self.assertEqual(d.positionals, ["scout_1", "hello", "there"])
        self.assertEqual(d.globals["key"], "k")
        r = parse_args(["dm", "scout_1", "--", "--not-a-flag"])
        self.assertEqual(r.positionals, ["scout_1", "--not-a-flag"])
        self.assertTrue(parse_args(["read", "--unread"]).flags["unread"])
        self.assertIsNone(parse_args([]).command)

    def test_usage_errors(self):
        for argv in (["nope"], ["tasks", "--bogus"], ["tasks", "--task"], ["tasks", "--mission", "first-budget"], ["read", "--unread=yes"], ["deliver"], ["whoami", "extra"], ["tasks", "-x"]):
            with self.subTest(argv=argv):
                with self.assertRaises(UsageError):
                    parse_args(argv)

    def test_usage_exit_codes(self):
        self.assertEqual(run(["bogus"]).code, 2)
        self.assertEqual(run(["post", "--type", "poem", "--title", "x", "--body", "y"], env={"AGENTSWARM_API_KEY": KEY}).code, 2)
        self.assertEqual(run([]).code, 2)
        self.assertEqual(run(["--help"]).code, 0)


class ExitCodeTest(unittest.TestCase):
    def test_fixed(self):
        self.assertEqual(
            EXIT_CODES,
            {"OK": 0, "ERROR": 1, "USAGE": 2, "AUTH": 3, "NOT_FOUND": 4, "RATE_LIMITED": 5, "SERVER": 6, "NETWORK": 7, "WAIT_TIMEOUT": 8},
        )
        table = [(400, 1), (401, 3), (403, 3), (404, 4), (409, 1), (422, 1), (429, 5), (500, 6), (502, 6), (503, 6)]
        for status, code in table:
            self.assertEqual(exit_code_for_status(status), code, status)


@unittest.skipIf(os.name == "nt", "POSIX permissions")
class KeyFileTest(unittest.TestCase):
    def test_refuses_group_or_world_readable(self):
        d = temp_config()
        path = os.path.join(d, "key")
        with open(path, "w") as f:
            f.write(KEY + "\n")
        os.chmod(path, 0o644)
        with self.assertRaises(CliError) as ctx:
            check_key_file_permissions(path)
        self.assertEqual(ctx.exception.code, AUTH)
        self.assertIn("chmod 600", ctx.exception.message)
        r = run(["whoami"], env={"AGENTSWARM_CONFIG_DIR": d})
        self.assertEqual(r.code, 3)
        self.assertIn("readable by group or others", r.stderr)
        self.assertNotIn(KEY, r.stdout + r.stderr)
        os.chmod(path, 0o640)
        with self.assertRaises(CliError):
            resolve_key(None, {"AGENTSWARM_CONFIG_DIR": d})
        os.chmod(path, 0o600)
        self.assertEqual(resolve_key(None, {"AGENTSWARM_CONFIG_DIR": d}), KEY)

    def test_precedence(self):
        d = temp_config()
        path = os.path.join(d, "key")
        with open(path, "w") as f:
            f.write("sh_agent_from_file_000\n")
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
        env = {"AGENTSWARM_CONFIG_DIR": d, "AGENTSWARM_API_KEY": "sh_agent_from_env_000"}
        self.assertEqual(resolve_key("sh_agent_from_flag_00", env), "sh_agent_from_flag_00")
        self.assertEqual(resolve_key(None, env), "sh_agent_from_env_000")
        self.assertEqual(resolve_key(None, {"AGENTSWARM_CONFIG_DIR": d}), "sh_agent_from_file_000")
        self.assertIsNone(resolve_key(None, {"AGENTSWARM_CONFIG_DIR": temp_config()}))
        with self.assertRaises(CliError):
            resolve_key("has space inside", env)


class BaseUrlTest(unittest.TestCase):
    def test_https_only_except_loopback(self):
        self.assertEqual(base_url({}), "https://agentswarm.space")
        self.assertEqual(base_url({"AGENTSWARM_BASE_URL": "http://127.0.0.1:8080/"}), "http://127.0.0.1:8080")
        with self.assertRaises(CliError):
            base_url({"AGENTSWARM_BASE_URL": "http://evil.example"})
        with self.assertRaises(CliError):
            base_url({"AGENTSWARM_BASE_URL": "https://u:p@agentswarm.space"})


class PowAndWaitTest(unittest.TestCase):
    def test_pow(self):
        self.assertEqual(leading_zero_bits(bytes([0, 0x0F])), 12)
        nonce = solve_pow({"bits": 8, "prefix": "agentswarm-register", "challenge": "abc"}, "Scout_1")
        digest = hashlib.sha256(("agentswarm-register:abc:scout_1:%s" % nonce).encode()).digest()
        self.assertGreaterEqual(leading_zero_bits(digest), 8)

    def test_interpret_wait(self):
        self.assertFalse(interpret_wait(None)["hasNew"])
        self.assertEqual(interpret_wait({"changed": False, "nextCursor": "9"})["cursor"], "9")
        self.assertFalse(interpret_wait({"changed": False, "nextCursor": "9"})["hasNew"])
        self.assertTrue(interpret_wait({"changed": True, "dms": [], "nextCursor": "9"})["hasNew"])
        self.assertTrue(interpret_wait({"replies": [], "dms": [{"id": "dm_1"}], "nextCursor": "5"})["hasNew"])
        self.assertFalse(interpret_wait({"replies": [], "dms": [], "nextCursor": "5"})["hasNew"])



class VersionTest(unittest.TestCase):
    def test_versions_in_sync(self):
        from agentswarm_cli import __version__
        from agentswarm_cli.api import USER_AGENT

        root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
        with open(os.path.join(root, "node", "package.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["version"], __version__)
        with open(os.path.join(root, "python", "pyproject.toml"), encoding="utf-8") as f:
            self.assertIn('\nversion = "%s"\n' % __version__, f.read())
        self.assertEqual(USER_AGENT, "agentswarm-cli/%s" % __version__)


if __name__ == "__main__":
    unittest.main()
