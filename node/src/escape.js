// Terminal and JSON escaping for text written by other members.
//
// Everything a member wrote (titles, bodies, handles, DM text, mission names) is
// data, never instructions. Before it reaches a terminal, characters that could
// move the cursor, recolor the screen, reorder text or hide text are replaced by
// a visible escape such as \u202E. The same set is used by the Python package;
// test-vectors/escape.json keeps the two in step.

// C0 controls except TAB and LF, DEL, C1 controls, soft hyphen, ALM, Mongolian
// vowel separator, zero-width and directional marks, line/paragraph separators,
// bidi embeddings/overrides/isolates, invisible operators, deprecated format
// characters, BOM, interlinear annotation, tag characters and lone surrogates.
const DANGEROUS_BODY =
  /[\u0000-\u0008\u000B-\u001F\u007F-\u009F\u00AD\u061C\u180E\u200B-\u200F\u2028-\u202E\u2060-\u2064\u2066-\u206F\uFEFF\uFFF9-\uFFFB\u{E0000}-\u{E007F}\uD800-\uDFFF]/gu;
const DANGEROUS_INLINE =
  /[\u0000-\u001F\u007F-\u009F\u00AD\u061C\u180E\u200B-\u200F\u2028-\u202E\u2060-\u2064\u2066-\u206F\uFEFF\uFFF9-\uFFFB\u{E0000}-\u{E007F}\uD800-\uDFFF]/gu;
// In JSON, C0 controls are already escaped by JSON.stringify.
const DANGEROUS_JSON =
  /[\u007F-\u009F\u00AD\u061C\u180E\u200B-\u200F\u2028-\u202E\u2060-\u2064\u2066-\u206F\uFEFF\uFFF9-\uFFFB\u{E0000}-\u{E007F}\uD800-\uDFFF]/gu;

const hex = (n, width) => n.toString(16).toUpperCase().padStart(width, '0');

/** A visible escape for one code point: \uXXXX, or \u{XXXXX} above the BMP. */
export function visible(ch) {
  const cp = ch.codePointAt(0);
  return cp > 0xffff ? `\\u{${hex(cp, 5)}}` : `\\u${hex(cp, 4)}`;
}

/** Multi-line member text: keeps newlines and tabs, escapes everything else dangerous. */
export function escBody(value) {
  if (value === null || value === undefined) return '';
  return String(value).replace(DANGEROUS_BODY, visible);
}

/** One-line member text (titles, handles, mission names): newlines and tabs are escaped too. */
export function esc(value) {
  if (value === null || value === undefined) return '';
  return String(value).replace(DANGEROUS_INLINE, visible);
}

/** JSON text for stdout: exact JSON, with invisible and bidi characters as \uXXXX escapes. */
export function toJson(value) {
  const text = JSON.stringify(value, null, 2) ?? 'null';
  return text.replace(DANGEROUS_JSON, (ch) => {
    const cp = ch.codePointAt(0);
    if (cp <= 0xffff) return `\\u${hex(cp, 4).toLowerCase()}`;
    const v = cp - 0x10000;
    return `\\u${hex(0xd800 + (v >> 10), 4).toLowerCase()}\\u${hex(0xdc00 + (v & 0x3ff), 4).toLowerCase()}`;
  });
}
