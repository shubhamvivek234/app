/**
 * Unicode text transformation utilities for social media posts.
 *
 * Social platforms (Twitter/X, LinkedIn, Threads) do not render HTML formatting.
 * Instead we map each Latin character to its Unicode Mathematical equivalents,
 * which render as bold or italic in most platforms.
 *
 * Reference ranges:
 *  Bold:             𝗔-𝗭 / 𝗮-𝘇  (U+1D400 – U+1D433)
 *  Italic:           𝘈-𝘡 / 𝘢-𝘻  (U+1D434 – U+1D467)
 *  Bold Italic:      𝘼-𝙕 / 𝙖-𝙯  (U+1D468 – U+1D49B)
 *  Strikethrough:    c̶o̶m̶b̶i̶n̶i̶n̶g̶  (U+0336 combining long stroke overlay)
 *  Monospace:        𝚊-𝚣 / 𝙰-𝚉  (U+1D670 – U+1D6A3)
 */

// ── Bold ────────────────────────────────────────────────────────────────────
const BOLD_UPPER = Array.from({ length: 26 }, (_, i) => String.fromCodePoint(0x1d400 + i));
const BOLD_LOWER = Array.from({ length: 26 }, (_, i) => String.fromCodePoint(0x1d41a + i));
const BOLD_DIGITS = Array.from({ length: 10 }, (_, i) => String.fromCodePoint(0x1d7ce + i));

// ── Italic ──────────────────────────────────────────────────────────────────
const ITALIC_UPPER = Array.from({ length: 26 }, (_, i) => String.fromCodePoint(0x1d434 + i));
const ITALIC_LOWER = Array.from({ length: 26 }, (_, i) =>
  i === 8
    ? '\u{1d456}' // special case: italic small i
    : String.fromCodePoint(0x1d44e + i)
);

// ── Bold Italic ─────────────────────────────────────────────────────────────
const BOLD_ITALIC_UPPER = Array.from({ length: 26 }, (_, i) => String.fromCodePoint(0x1d468 + i));
const BOLD_ITALIC_LOWER = Array.from({ length: 26 }, (_, i) => String.fromCodePoint(0x1d482 + i));

// ── Monospace ───────────────────────────────────────────────────────────────
const MONO_UPPER = Array.from({ length: 26 }, (_, i) => String.fromCodePoint(0x1d670 + i));
const MONO_LOWER = Array.from({ length: 26 }, (_, i) => String.fromCodePoint(0x1d68a + i));

const UPPER_A = 'A'.charCodeAt(0);
const LOWER_A = 'a'.charCodeAt(0);
const ZERO    = '0'.charCodeAt(0);

/**
 * Generic character-by-character transformer.
 * Non-Latin characters pass through unchanged.
 */
function transformText(str, upperMap, lowerMap, digitMap = null) {
  return [...str]
    .map((ch) => {
      const code = ch.charCodeAt(0);
      if (code >= UPPER_A && code < UPPER_A + 26) return upperMap[code - UPPER_A];
      if (code >= LOWER_A && code < LOWER_A + 26) return lowerMap[code - LOWER_A];
      if (digitMap && code >= ZERO && code < ZERO + 10) return digitMap[code - ZERO];
      return ch;
    })
    .join('');
}

// ── Public API ──────────────────────────────────────────────────────────────

/** Transform selected text to Unicode bold */
export const toBold = (str) => transformText(str, BOLD_UPPER, BOLD_LOWER, BOLD_DIGITS);

/** Transform selected text to Unicode italic */
export const toItalic = (str) => transformText(str, ITALIC_UPPER, ITALIC_LOWER);

/** Transform selected text to Unicode bold-italic */
export const toBoldItalic = (str) => transformText(str, BOLD_ITALIC_UPPER, BOLD_ITALIC_LOWER);

/** Add Unicode combining strikethrough to each character */
export const toStrikethrough = (str) => [...str].map((ch) => ch + '\u0336').join('');

/** Transform selected text to Unicode monospace */
export const toMonospace = (str) => transformText(str, MONO_UPPER, MONO_LOWER);

/**
 * Apply a transformation to the selected text range within a textarea value.
 * Returns { newValue, selectionStart, selectionEnd } ready for setState.
 *
 * @param {string} value         current textarea value
 * @param {number} selStart      selection start index
 * @param {number} selEnd        selection end index
 * @param {function} transformFn one of the above transform functions
 */
export function applyFormat(value, selStart, selEnd, transformFn) {
  const before    = value.slice(0, selStart);
  const selected  = value.slice(selStart, selEnd);
  const after     = value.slice(selEnd);
  const formatted = transformFn(selected);
  const newValue  = before + formatted + after;
  return {
    newValue,
    selectionStart: selStart,
    selectionEnd:   selStart + formatted.length,
  };
}
