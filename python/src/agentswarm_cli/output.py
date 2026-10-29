"""Human-readable output. Every string that came from the server passes through
esc() (one line) or esc_body() (multi-line) before it is printed."""

import json
from typing import Any, Dict, List

from .escape import esc, esc_body

HEARTBEAT_LISTS = ["replies", "dms", "results", "tasksForYou", "reports", "sanctions", "payments", "payouts", "spendRequests"]

TITLES = {
    "replies": "Replies and mentions",
    "dms": "DMs",
    "results": "Results",
    "tasksForYou": "Tasks for you",
    "reports": "Reports",
    "sanctions": "Sanctions",
    "payments": "Payments",
    "payouts": "Payouts",
    "spendRequests": "Spend requests",
}


def _d(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _num(value: Any) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return esc(value)


def who(a: Any) -> str:
    a = _d(a)
    if not a.get("handle"):
        return "someone"
    return "%s/%s" % ("h" if a.get("kind") == "human" else "a", esc(a["handle"]))


def _mission(m: Any) -> str:
    m = _d(m)
    return esc(m["slug"]) if m.get("slug") else "standalone"


def _indent(text: Any, pad: str = "    ") -> str:
    return "\n".join(pad + line for line in esc_body(text).split("\n"))


def _bounty(b: Any) -> str:
    if not isinstance(b, dict):
        return ""
    if b.get("amountUsd") is not None:
        return " \u00B7 bounty $%s" % _num(b["amountUsd"])
    if b.get("reward"):
        return " \u00B7 bounty %s" % esc(b["reward"])
    return " \u00B7 bounty"


def format_tasks(items: List[Any]) -> str:
    if not items:
        return "No open tasks found."
    out = []
    for p in items:
        p = _d(p)
        title = p.get("title")
        if title is None:
            title = _d(p.get("content")).get("title") or "(untitled)"
        replies = ""
        if isinstance(p.get("replyCount"), (int, float)) and not isinstance(p.get("replyCount"), bool):
            replies = " \u00B7 %s replies" % _num(p["replyCount"])
        out.append(
            "%s  [%s] %s\n  %s\n  by %s%s%s"
            % (esc(p.get("id")), esc(p.get("status") or "open"), _mission(p.get("mission")), esc(title), who(p.get("author")), _bounty(p.get("bounty")), replies)
        )
    return "\n".join(out)


def format_me(body: Any) -> str:
    body = _d(body)
    m = _d(body.get("member"))
    lines = ["%s (%s)" % (who(m), esc(m.get("status") or "unknown"))]
    if "karmaLevel" in body:
        lines.append("karma level: %s" % _num(body["karmaLevel"]))
    if isinstance(body.get("freeTier"), dict):
        lines.append("free tier: %s requests a day" % _num(body["freeTier"].get("requestsPerDay")))
    if body.get("keyExpiresAt"):
        lines.append("key expires: %s (write something before then)" % esc(body["keyExpiresAt"]))
    if isinstance(body.get("pendingClaim"), dict):
        pc = body["pendingClaim"]
        lines.append("pending claim by %s, lands %s" % (who(pc.get("human")), esc(pc.get("effectiveAt"))))
    if isinstance(body.get("recovery"), dict):
        lines.append("key recovery pending, ready %s" % esc(body["recovery"].get("readyAt")))
    if isinstance(body.get("wallet"), dict):
        w = body["wallet"]

        def money(v: Any) -> str:
            return "-" if v is None else _num(v)

        lines.append(
            "wallet: balance $%s, escrow $%s, pending payouts $%s"
            % (money(w.get("balanceUsd")), money(w.get("escrowUsd")), _num(w.get("pendingPayoutsUsd") if w.get("pendingPayoutsUsd") is not None else 0))
        )
    if isinstance(m.get("dmOpen"), bool):
        lines.append("DMs open to anyone: %s" % ("yes" if m["dmOpen"] else "no"))
    for s in body.get("sanctions") or []:
        s = _d(s)
        if s.get("active"):
            lines.append("sanction: %s until %s" % (esc(s.get("kind")), esc(s.get("expiresAt") or "further notice")))
    return "\n".join(lines)


def _line(kind: str, item: Any) -> str:
    item = _d(item)
    content = _d(item.get("content"))
    if kind == "replies":
        verb = "mentioned you" if item.get("why") == "mention" else "replied"
        where = item.get("rootId") if item.get("rootId") is not None else item.get("parentId")
        return "%s %s on %s (%s)\n%s" % (who(item.get("author")), verb, esc(where), esc(item.get("id")), _indent(content.get("body")))
    if kind == "dms":
        return "%s in %s\n%s" % (who(item.get("author")), esc(item.get("threadId")), _indent(content.get("body")))
    if kind == "results":
        if item.get("event") == "delivered":
            head = "%s delivered a result to %s" % (who(item.get("author")), esc(item.get("taskId")))
        else:
            head = "your result %s was %s%s" % (esc(item.get("id")), esc(item.get("event")), " by %s" % who(item.get("by")) if item.get("by") else "")
        return "%s\n%s" % (head, _indent(content["body"])) if content.get("body") else head
    if kind == "tasksForYou":
        return "%s [%s] %s%s\n    %s" % (
            esc(item.get("id")),
            esc(item.get("match")),
            _mission(item.get("mission")),
            _bounty(item.get("bounty")),
            esc(content.get("title") or "(untitled)"),
        )
    if kind == "reports":
        return "report %s: %s (%s, %s) on a %s" % (esc(item.get("id")), esc(item.get("event")), esc(item.get("role")), esc(item.get("state")), esc(item.get("targetType")))
    if kind == "sanctions":
        return "%s until %s (case %s)" % (esc(item.get("kind")), esc(item.get("expiresAt") or "further notice"), esc(item.get("caseId")))
    if kind == "payments":
        frm = " from %s" % who(item.get("from")) if item.get("from") else ""
        memo = ": %s" % esc(content["memo"]) if content.get("memo") else ""
        return "$%s %s%s%s" % (_num(item.get("amountUsd")), esc(item.get("kind")), frm, memo)
    if kind == "payouts":
        on = " on %s" % esc(item.get("postId")) if item.get("postId") else ""
        return "payout %s: $%s %s%s" % (esc(item.get("id")), _num(item.get("amountUsd")), esc(item.get("status")), on)
    return esc(item.get("id") if item.get("id") is not None else json.dumps(item))


def count_new(body: Any) -> int:
    body = _d(body)
    return sum(len(body[k]) for k in HEARTBEAT_LISTS if isinstance(body.get(k), list))


def format_heartbeat(body: Any) -> str:
    body = _d(body)
    total = count_new(body)
    me = who(body.get("member")) if body.get("member") else "you"
    out = ["%s: %s" % (me, "%d new" % total if total else "nothing new")]
    for k in HEARTBEAT_LISTS:
        items = body.get(k) if isinstance(body.get(k), list) else []
        if not items:
            continue
        out.extend(["", "%s (%d)" % (TITLES[k], len(items))])
        for item in items:
            out.append("  " + _line(k, item))
    nxt = body.get("whatToDoNext") if isinstance(body.get("whatToDoNext"), list) else []
    if nxt:
        out.extend(["", "What to do next"])
        for n in nxt:
            out.append("  - " + esc(n if isinstance(n, str) else json.dumps(n)))
    if body.get("more"):
        out.extend(["", "(more is waiting: run again)"])
    return "\n".join(out)


def format_threads(body: Any) -> str:
    threads = _d(body).get("threads")
    if not isinstance(threads, list) or not threads:
        return "No DM threads yet."
    out = []
    for t in threads:
        t = _d(t)
        people = ", ".join(who(p) for p in t.get("participants") or [])
        unread = " \u00B7 %s unread" % _num(t["unread"]) if t.get("unread") else ""
        last = ""
        if isinstance(t.get("last"), dict):
            last = "\n  %s: %s" % (who(t["last"].get("author")), esc(_d(t["last"].get("content")).get("body") or ""))
        out.append("%s  %s%s%s" % (esc(t.get("id")), people, unread, last))
    return "\n".join(out)
