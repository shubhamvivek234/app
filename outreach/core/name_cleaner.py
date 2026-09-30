"""
Safe, Non-Destructive Name Normalization Engine for Outreach Personalization.
Eliminates naive title-casing bugs (e.g. preserving McDonald, O'Connor, de la Cruz).
Only normalizes 100% ALL-CAPS strings and strips trailing noise/emojis/certifications.
"""
import re
from typing import Tuple

# Emoji & Unicode symbol removal pattern
EMOJI_PATTERN = re.compile(
    r"[\U00010000-\U0010ffff]|[\u2600-\u27ff]|[\u2300-\u23ff]|[\u2b50-\u2b55]|[\u3030\u303d\u3297\u3299]",
    flags=re.UNICODE,
)

# Common certification and headline noise suffixes
CERTIFICATION_SUFFIX_PATTERN = re.compile(
    r"(?i)(?:,\s*|\s+[|/•-]\s+)(?:CPA|MBA|PhD|Ph\.D\.|MD|M\.D\.|PMP|PE|CFA|Esq\.?|Founder|Co-Founder|CEO|CTO|COO|CMO|President|Director|VP|Author|Speaker|Coach|Strategist|Consultant|Advisor|Leader)\b.*$"
)

# Parenthetical or bracketed noise: "John (Hiring)", "Alice [Ex-Google]"
PARENTHETICAL_NOISE_PATTERN = re.compile(r"[\(\[\{].*?[\)\]\}]")


def _smart_title_case_word(word: str) -> str:
    """
    Intelligently capitalizes an ALL-CAPS word, handling Irish (O'...),
    Scottish (Mc...), hyphenated names, and preserving dotted initials (J.R., A.J.).
    """
    if not word:
        return ""

    # Preserve dotted initials: "J.R.", "A.J.", "J.R.R."
    if re.fullmatch(r"([A-Za-z]\.)+", word):
        return word.upper()

    # Hyphenated parts: "JOHN-PAUL" -> "John-Paul"
    if "-" in word:
        return "-".join(_smart_title_case_word(part) for part in word.split("-"))

    # Apostrophe parts: "O'CONNOR" -> "O'Connor", "D'ANGELO" -> "D'Angelo"
    if "'" in word:
        subparts = word.split("'", 1)
        prefix = subparts[0].capitalize()
        suffix = _smart_title_case_word(subparts[1])
        return f"{prefix}'{suffix}"

    # Scottish Mc prefix: "MCDONALD" -> "McDonald", "MCKINLEY" -> "McKinley"
    if len(word) > 2 and word.startswith("MC"):
        return "Mc" + word[2:].capitalize()

    # Scottish Mac prefix: "MACDONALD" -> "MacDonald" (only if length > 4 and 4th char is consonant)
    if len(word) > 4 and word.startswith("MAC") and word[3] not in "AEIOU":
        return "Mac" + word[3:].capitalize()

    return word.capitalize()


def clean_first_name(raw: str | None) -> str:
    """
    Cleans a first name string safely and non-destructively:
    - Strips emojis and trailing certifications/headline noise.
    - Strips bracketed/parenthetical annotations.
    - Preserves mixed-case strings (e.g. McDonald, de la Cruz, van Buren, O'Connor).
    - Safely converts 100% ALL-CAPS strings (e.g. 'JOHN DOE' -> 'John Doe', 'O'CONNOR' -> 'O'Connor').
    - Capitalizes 100% all-lowercase strings (e.g. 'john' -> 'John').
    - Preserves initials-first names (e.g. 'J.R.', 'A.J.').
    """
    if not raw or not isinstance(raw, str):
        return ""

    text = raw.strip()
    if not text:
        return ""

    # 1. Remove bracketed / parenthetical notes
    text = PARENTHETICAL_NOISE_PATTERN.sub("", text).strip()

    # 2. Remove emojis and symbols
    text = EMOJI_PATTERN.sub("", text).strip()

    # 3. Strip certification and professional suffix noise
    text = CERTIFICATION_SUFFIX_PATTERN.sub("", text).strip()

    # 4. Remove lingering commas, pipes, slashes at the end
    text = re.sub(r"[,|/•\-]+$", "", text).strip()

    # 5. Clean up multiple whitespaces
    text = re.sub(r"\s+", " ", text).strip()

    if not text:
        return ""

    # Check case properties
    has_letters = bool(re.search(r"[a-zA-Z]", text))
    if not has_letters:
        return text

    # If already mixed-case (contains both upper and lower case letters), PRESERVE AS-IS!
    # Examples: 'McDonald', 'de la Cruz', 'van Buren', 'O'Connor', 'diCaprio'
    has_lower = any(c.islower() for c in text)
    has_upper = any(c.isupper() for c in text)

    if has_lower and has_upper:
        # Check if first character is lowercase but not a recognized noble particle
        # Noble particles: de, da, di, du, van, von, la, le, del
        words = text.split(" ")
        noble_particles = {"de", "da", "di", "du", "van", "von", "la", "le", "del", "der", "den"}
        if len(words) == 1 and words[0][0].islower():
            # Single word like 'mcdonald' or 'john' that somehow had mixed case?
            # If word is like 'mCDONALD', normalize. If like 'mC', leave.
            return text
        return text

    # If 100% ALL CAPS: "JOHN", "JOHN DOE", "MICHAEL O'CONNOR", "MCDONALD"
    if has_upper and not has_lower:
        words = text.split(" ")
        capitalized_words = [_smart_title_case_word(w) for w in words]
        return " ".join(capitalized_words)

    # If 100% all lowercase: "john", "sarah jane"
    if has_lower and not has_upper:
        words = text.split(" ")
        # Check if particles exist
        noble_particles = {"de", "da", "di", "du", "van", "von", "la", "le", "del"}
        capitalized_words = []
        for idx, w in enumerate(words):
            if idx > 0 and w.lower() in noble_particles:
                capitalized_words.append(w.lower())
            else:
                capitalized_words.append(_smart_title_case_word(w))
        return " ".join(capitalized_words)

    return text
