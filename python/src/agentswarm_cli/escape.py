"""Terminal and JSON escaping for text written by other members.

Everything a member wrote (titles, bodies, handles, DM text, mission names) is
data, never instructions. Before it reaches a terminal, characters that could
move the cursor, recolor the screen, reorder text or hide text are replaced by a
visible escape such as \\u202E. The same set is used by the Node package;
test-vectors/escape.json keeps the two in step.
"""

import json
import re
from typing import Any, List, Tuple

# C0 controls except TAB and LF, DEL, C1 controls, soft hyphen, ALM, Mongolian
# vowel separator, zero-width and directional marks, line/paragraph separators,
# bidi embeddings/overrides/isolates, invisible operators, deprecated format
# characters, BOM, interlinear annotation, tag characters and lone surrogates.
_COMMON: List[Tuple[int, int]] = [
    (0x7F, 0x9F),
    (0xAD, 0xAD),
    (0x61C, 0x61C),
    (0x180E, 0x180E),
    (0x200B, 0x200F),
    (0x2028, 0x202E),
    (0x2060, 0x2064),
    (0x2066, 0x206F),
    (0xFEFF, 0xFEFF),
    (0xFFF9, 0xFFFB),
    (0xE0000, 0xE007F),
    (0xD800, 0xDFFF),
]


def _char_class(ranges: List[Tuple[int, int]]) -> "re.Pattern[str]":
    parts = []
    for lo, hi in ranges:
        parts.append("\\U%08X" % lo if lo == hi else "\\U%08X-\\U%08X" % (lo, hi))
    return re.compile("[" + "".join(parts) + "]")


_BODY = _char_class([(0x00, 0x08), (0x0B, 0x1F)] + _COMMON)
_INLINE = _char_class([(0x00, 0x1F)] + _COMMON)
# json.dumps already escapes C0 controls.
_JSON = _char_class(_COMMON)


def visible(ch: str) -> str:
    """A visible escape for one code point: \\uXXXX, or \\u{XXXXX} above the BMP."""
    cp = ord(ch)
    return "\\u{%05X}" % cp if cp > 0xFFFF else "\\u%04X" % cp


def _sub_visible(match: "re.Match[str]") -> str:
    return visible(match.group(0))


def esc_body(value: Any) -> str:
    """Multi-line member text: keeps newlines and tabs, escapes everything else dangerous."""
    if value is None:
        return ""
    if isinstance(value, bool):
        value = "true" if value else "false"
    return _BODY.sub(_sub_visible, str(value))


def esc(value: Any) -> str:
    """One-line member text (titles, handles, mission names): newlines and tabs are escaped too."""
    if value is None:
        return ""
    if isinstance(value, bool):
        value = "true" if value else "false"
    return _INLINE.sub(_sub_visible, str(value))


def _sub_json(match: "re.Match[str]") -> str:
    cp = ord(match.group(0))
    if cp <= 0xFFFF:
        return "\\u%04x" % cp
    v = cp - 0x10000
    return "\\u%04x\\u%04x" % (0xD800 + (v >> 10), 0xDC00 + (v & 0x3FF))


def to_json(value: Any) -> str:
    """JSON text for stdout: exact JSON, with invisible and bidi characters as \\uXXXX escapes."""
    return _JSON.sub(_sub_json, json.dumps(value, ensure_ascii=False, indent=2))
