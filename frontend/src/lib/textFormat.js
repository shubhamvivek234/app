/**
 * Unicode text transformation utilities for social media posts (LinkedIn, X/Twitter, Threads, etc.)
 *
 * Platforms do not support raw HTML/Markdown styling in standard post bodies.
 * These functions map Latin characters to their mathematical alphanumeric symbols
 * and combining Unicode diacritics.
 */

const UPPER_A = 'A'.charCodeAt(0);
const LOWER_A = 'a'.charCodeAt(0);
const ZERO    = '0'.charCodeAt(0);

// ── 1. Bold (Sans-serif) ───────────────────────────────────────────────────────
const BOLD_SANS_UPPER = Array.from({ length: 26 }, (_, i) => String.fromCodePoint(0x1d5d4 + i));
const BOLD_SANS_LOWER = Array.from({ length: 26 }, (_, i) => String.fromCodePoint(0x1d5ee + i));
const BOLD_SANS_DIGITS = Array.from({ length: 10 }, (_, i) => String.fromCodePoint(0x1d7ec + i));

// ── 2. Bold (Serif) ────────────────────────────────────────────────────────────
const BOLD_SERIF_UPPER = Array.from({ length: 26 }, (_, i) => String.fromCodePoint(0x1d400 + i));
const BOLD_SERIF_LOWER = Array.from({ length: 26 }, (_, i) => String.fromCodePoint(0x1d41a + i));
const BOLD_SERIF_DIGITS = Array.from({ length: 10 }, (_, i) => String.fromCodePoint(0x1d7ce + i));

// ── 3. Italic (Sans-serif) ─────────────────────────────────────────────────────
const ITALIC_SANS_UPPER = Array.from({ length: 26 }, (_, i) => String.fromCodePoint(0x1d608 + i));
const ITALIC_SANS_LOWER = Array.from({ length: 26 }, (_, i) => String.fromCodePoint(0x1d622 + i));

// ── 4. Italic (Serif) ──────────────────────────────────────────────────────────
const ITALIC_SERIF_UPPER = Array.from({ length: 26 }, (_, i) => String.fromCodePoint(0x1d434 + i));
const ITALIC_SERIF_LOWER = Array.from({ length: 26 }, (_, i) =>
  i === 8 ? '\u{1d456}' : String.fromCodePoint(0x1d44e + i)
);

// ── 5. Bold Italic (Sans-serif) ───────────────────────────────────────────────
const BOLD_ITALIC_UPPER = Array.from({ length: 26 }, (_, i) => String.fromCodePoint(0x1d63c + i));
const BOLD_ITALIC_LOWER = Array.from({ length: 26 }, (_, i) => String.fromCodePoint(0x1d656 + i));

// ── 6. Monospace ───────────────────────────────────────────────────────────────
const MONO_UPPER = Array.from({ length: 26 }, (_, i) => String.fromCodePoint(0x1d670 + i));
const MONO_LOWER = Array.from({ length: 26 }, (_, i) => String.fromCodePoint(0x1d68a + i));
const MONO_DIGITS = Array.from({ length: 10 }, (_, i) => String.fromCodePoint(0x1d7f6 + i));

// ── 7. Script / Cursive ───────────────────────────────────────────────────────
const SCRIPT_LOWER = ['𝒶','𝒷','𝒸','𝒹','𝑒','𝒻','𝑔','𝒽','𝒾','𝒿','𝓀','𝓁','𝓂','𝓃','𝑜','𝓅','𝓆','𝓇','𝓈','𝓉','𝓊','𝓋','𝓌','𝓍','𝓎','𝓏'];
const SCRIPT_UPPER = ['𝒜','ℬ','𝒞','𝒟','ℰ','ℱ','𝒢','ℋ','ℐ','𝒥','𝒦','ℒ','ℳ','𝒩','𝒪','𝒫','𝒬','ℛ','𝒮','𝒯','𝒰','𝒱','𝒲','𝒳','𝒴','𝒵'];

const BOLD_SCRIPT_UPPER = Array.from({ length: 26 }, (_, i) => String.fromCodePoint(0x1d4d0 + i));
const BOLD_SCRIPT_LOWER = Array.from({ length: 26 }, (_, i) => String.fromCodePoint(0x1d4ea + i));

// ── 8. Double-Struck / Blackboard ─────────────────────────────────────────────
const DOUBLE_STRUCK_LOWER = Array.from({ length: 26 }, (_, i) => String.fromCodePoint(0x1d552 + i));
const DOUBLE_STRUCK_UPPER = ['𝔸','𝔹','ℂ','𝔻','𝔼','𝔽','𝔾','ℍ','𝕀','𝕁','𝕂','𝕃','𝕄','ℕ','𝕆','ℙ','ℚ','ℝ','𝕊','𝕋','𝕌','𝕍','𝕎','𝕏','𝕐','ℤ'];
const DOUBLE_STRUCK_DIGITS = Array.from({ length: 10 }, (_, i) => String.fromCodePoint(0x1d7d8 + i));

// ── 9. Gothic / Fraktur ───────────────────────────────────────────────────────
const GOTHIC_LOWER = Array.from({ length: 26 }, (_, i) => String.fromCodePoint(0x1d51e + i));
const GOTHIC_UPPER = ['𝔄','𝔅','ℭ','𝔇','𝔈','𝔉','𝔊','ℌ','ℑ','𝔍','𝔎','𝔏','𝔐','𝔑','𝔒','𝔓','𝔔','ℜ','𝔖','𝔗','𝔘','𝔙','𝔚','𝔛','𝔜','ℨ'];

// ── 10. Small Caps ────────────────────────────────────────────────────────────
const SMALL_CAPS_MAP = {
  a: 'ᴀ', b: 'ʙ', c: 'ᴄ', d: 'ᴅ', e: 'ᴇ', f: 'ғ', g: 'ɢ', h: 'ʜ', i: 'ɪ',
  j: 'ᴊ', k: 'ᴋ', l: 'ʟ', m: 'ᴍ', n: 'ɴ', o: 'ᴏ', p: 'ᴘ', q: 'ǫ', r: 'ʀ',
  s: 's', t: 'ᴛ', u: 'ᴜ', v: 'ᴠ', w: 'ᴡ', x: 'x', y: 'ʏ', z: 'ᴢ',
};

// ── 11. Circled ───────────────────────────────────────────────────────────────
const CIRCLED_NUMBERS = ['⓪', '①', '②', '③', '④', '⑤', '⑥', '⑦', '⑧', '⑨', '⑩'];
const INVERTED_CIRCLED_NUMBERS = ['⓿', '➊', '➋', '➌', '➍', '➎', '➏', '➐', '➑', '➒', '➓'];

/**
 * Generic character-by-character transformer.
 */
function transformText(str, upperMap, lowerMap, digitMap = null) {
  if (!str) return '';
  return [...str]
    .map((ch) => {
      const code = ch.charCodeAt(0);
      if (code >= UPPER_A && code < UPPER_A + 26 && upperMap) return upperMap[code - UPPER_A] || ch;
      if (code >= LOWER_A && code < LOWER_A + 26 && lowerMap) return lowerMap[code - LOWER_A] || ch;
      if (digitMap && code >= ZERO && code < ZERO + 10) return digitMap[code - ZERO] || ch;
      return ch;
    })
    .join('');
}

// ── Transformation Functions ───────────────────────────────────────────────────

/** Bold (Sans-serif, default modern look) */
export const toBold = (str) => transformText(str, BOLD_SANS_UPPER, BOLD_SANS_LOWER, BOLD_SANS_DIGITS);
export const toBoldSans = toBold;

/** Bold (Serif classic) */
export const toBoldSerif = (str) => transformText(str, BOLD_SERIF_UPPER, BOLD_SERIF_LOWER, BOLD_SERIF_DIGITS);

/** Italic (Sans-serif) */
export const toItalic = (str) => transformText(str, ITALIC_SANS_UPPER, ITALIC_SANS_LOWER);
export const toItalicSans = toItalic;

/** Italic (Serif) */
export const toItalicSerif = (str) => transformText(str, ITALIC_SERIF_UPPER, ITALIC_SERIF_LOWER);

/** Bold Italic */
export const toBoldItalic = (str) => transformText(str, BOLD_ITALIC_UPPER, BOLD_ITALIC_LOWER);

/** Single Underline using combining low line U+0332 */
export const toUnderline = (str) => {
  if (!str) return '';
  return [...str].map((ch) => (ch === '\n' || ch === '\r' ? ch : ch + '\u0332')).join('');
};

/** Double Underline using combining double low line U+0333 */
export const toDoubleUnderline = (str) => {
  if (!str) return '';
  return [...str].map((ch) => (ch === '\n' || ch === '\r' ? ch : ch + '\u0333')).join('');
};

/** Strikethrough using combining long stroke overlay U+0336 */
export const toStrikethrough = (str) => {
  if (!str) return '';
  return [...str].map((ch) => (ch === '\n' || ch === '\r' ? ch : ch + '\u0336')).join('');
};

/** Monospace */
export const toMonospace = (str) => transformText(str, MONO_UPPER, MONO_LOWER, MONO_DIGITS);

/** Script / Cursive */
export const toScript = (str) => transformText(str, SCRIPT_UPPER, SCRIPT_LOWER);

/** Bold Script */
export const toBoldScript = (str) => transformText(str, BOLD_SCRIPT_UPPER, BOLD_SCRIPT_LOWER);

/** Double Struck / Blackboard */
export const toDoubleStruck = (str) => transformText(str, DOUBLE_STRUCK_UPPER, DOUBLE_STRUCK_LOWER, DOUBLE_STRUCK_DIGITS);

/** Gothic / Fraktur */
export const toGothic = (str) => transformText(str, GOTHIC_UPPER, GOTHIC_LOWER);

/** Small Caps */
export const toSmallCaps = (str) => {
  if (!str) return '';
  return [...str].map((ch) => SMALL_CAPS_MAP[ch.toLowerCase()] || ch).join('');
};

/**
 * Remove combining diacritics and convert mathematical alphanumerics back to plain ASCII text.
 */
export const toPlainText = (str) => {
  if (!str) return '';
  const normalized = str.normalize('NFKD');
  return normalized.replace(/[\u0300-\u036f]/g, '');
};

/**
 * Format a multiline block with custom bullet points.
 */
export const toBulletList = (str, bullet = '•') => {
  if (!str) return '';
  return str
    .split('\n')
    .map((line) => (line.trim() ? `${bullet} ${line.replace(/^[•\-\*➊-➓①-⑩\d\.]+\s*/, '')}` : ''))
    .join('\n');
};

/**
 * Format lines with circled numbered points ➊ ➋ ➌ ...
 */
export const toCircledNumberedList = (str, inverted = true) => {
  if (!str) return '';
  const numbers = inverted ? INVERTED_CIRCLED_NUMBERS : CIRCLED_NUMBERS;
  let counter = 1;
  return str
    .split('\n')
    .map((line) => {
      if (!line.trim()) return '';
      const numSymbol = counter <= 10 ? numbers[counter] : `${counter}.`;
      counter++;
      return `${numSymbol} ${line.replace(/^[•\-\*➊-➓①-⑩\d\.]+\s*/, '')}`;
    })
    .join('\n');
};

/**
 * Style catalogue for toolbars and dropdowns.
 */
export const STYLE_CATALOGUE = [
  { id: 'bold-sans', name: 'Bold Sans', preview: '𝗕𝗼𝗹𝗱', fn: toBoldSans },
  { id: 'bold-serif', name: 'Bold Serif', preview: '𝐁𝐨𝐥𝐝', fn: toBoldSerif },
  { id: 'italic-sans', name: 'Italic Sans', preview: '𝘐𝘵𝘢𝘭𝘪𝘤', fn: toItalicSans },
  { id: 'italic-serif', name: 'Italic Serif', preview: '𝐼𝑡𝑎𝑙𝑖𝑐', fn: toItalicSerif },
  { id: 'bold-italic', name: 'Bold Italic', preview: '𝘽𝙤𝙡𝙙 𝙄𝘵𝘢𝘭𝙞𝙘', fn: toBoldItalic },
  { id: 'underline', name: 'Underline', preview: 'u̲n̲d̲e̲r̲', fn: toUnderline },
  { id: 'double-underline', name: 'Double Underline', preview: 'u̳n̳d̳e̳r̳', fn: toDoubleUnderline },
  { id: 'strikethrough', name: 'Strikethrough', preview: 's̶t̶r̶i̶k̶e̶', fn: toStrikethrough },
  { id: 'monospace', name: 'Monospace', preview: '𝚖𝚘𝚗𝚘', fn: toMonospace },
  { id: 'script', name: 'Script / Cursive', preview: '𝒮𝒸𝓇𝒾𝓅𝓉', fn: toScript },
  { id: 'double-struck', name: 'Double Struck', preview: '𝔻𝕠𝕦𝕓𝕝𝕖', fn: toDoubleStruck },
  { id: 'gothic', name: 'Gothic / Fraktur', preview: '𝔊𝔬𝔱𝔥𝔦𝔠', fn: toGothic },
  { id: 'small-caps', name: 'Small Caps', preview: 'sᴍᴀʟʟ ᴄᴀᴘs', fn: toSmallCaps },
];

/**
 * Selection-aware formatting helper.
 */
export function applyFormat(value, selStart, selEnd, transformFn) {
  if (typeof value !== 'string') return { newValue: '', selectionStart: 0, selectionEnd: 0 };
  if (selStart === selEnd) {
    const formatted = transformFn(value);
    return {
      newValue: formatted,
      selectionStart: 0,
      selectionEnd: formatted.length,
    };
  }
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
