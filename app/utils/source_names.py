import re
from dataclasses import dataclass


@dataclass(frozen=True)
class SourceNameParts:
    compact: str
    words: tuple[str, ...]
    numbers: tuple[str, ...]


def normalize_source_name(text: str) -> str:
    if not text:
        return ""
    text = normalize_arabic_text(text).casefold()
    text = re.sub(r"[\u064B-\u065F\u0670]", "", text)
    return re.sub(r"[^\u0621-\u064A0-9a-z]", "", text)


def source_names_match(target: str, candidate: str) -> bool:
    if not target or not candidate:
        return False

    target_parts = source_name_parts(target)
    candidate_parts = source_name_parts(candidate)

    # Compare numeric tokens before any substring-based fuzzy matching.  This
    # prevents a source such as "(1)" from matching the requested "(10)"
    # merely because its compact name is a prefix of the longer one.
    if target_parts.numbers and not all(
        number in candidate_parts.numbers for number in target_parts.numbers
    ):
        return False

    if target in candidate or (len(candidate) > 8 and candidate in target):
        return True

    if target_parts.compact in candidate_parts.compact or (
        len(candidate_parts.compact) > 8
        and candidate_parts.compact in target_parts.compact
    ):
        return True

    meaningful_words = tuple(word for word in target_parts.words if len(word) > 1)
    if len(meaningful_words) < 2:
        return False

    return is_subsequence(meaningful_words, candidate_parts.words)


def source_name_parts(text: str) -> SourceNameParts:
    text = normalize_arabic_text(text).casefold()
    text = re.sub(r"\b(?:mp3|mp4|m4a|wav|webm|pdf|docx?)\b", " ", text)
    tokens = re.findall(r"[\u0621-\u064A]+|[a-z]+|\d+", text)
    words = tuple(token for token in tokens if not token.isdigit())
    numbers = tuple(str(int(token)) for token in tokens if token.isdigit())
    return SourceNameParts(
        compact=normalize_source_name(text),
        words=words,
        numbers=numbers,
    )


def normalize_arabic_text(text: str) -> str:
    digits = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
    text = text.translate(digits)
    text = re.sub(r"[\u064B-\u065F\u0670]", "", text)
    return (
        text.replace("أ", "ا")
        .replace("إ", "ا")
        .replace("آ", "ا")
        .replace("ٱ", "ا")
        .replace("ى", "ي")
    )


def is_subsequence(needles: tuple[str, ...], haystack: tuple[str, ...]) -> bool:
    if not needles:
        return False
    position = 0
    for token in haystack:
        if token == needles[position]:
            position += 1
            if position == len(needles):
                return True
    return False
