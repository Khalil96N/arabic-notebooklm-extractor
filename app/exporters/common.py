import json
import re
import unicodedata
import urllib.request
from datetime import datetime

from app.config.settings import settings

_LIST_INTRODUCTION_RE = re.compile(
    r"(?:"
    r"منها|من أهمها|من أشهرها|من أشهر|أبرزها|أشهرها|نذكر منها|"
    r"كالآتي|كما يأتي|الآتية|التالية|وهي|وتفصيلها|تفصيلها|"
    r"إلى\s+\S+\s+آراء|لعدة أسباب|عدة أسباب|مثل|بأوصاف منها"
    r")\s*[:：]\s*$"
)
_NARRATIVE_START_RE = re.compile(
    r"^(?:"
    r"وقد|وهذا|وهذه|وللتذكير|وسنتعرف|وأريد|أريد|أما|وأما|ثم|"
    r"ننتقل|أنتقل|لذا|لذلك|ولا شك|وبهذا|ومن هنا|وهنا|لكن|"
    r"إلا أن|فهذا|فهذه|كما أن|وعليه|وأحياناً|وأحيانًا"
    r")\b"
)
_EXPLICIT_LIST_RE = re.compile(r"^(?:[-*•●◦▪]\s+|\d+[\.)]\s+)")


def ensure_output_dir() -> None:
    settings.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def safe_output_name(name: str, fallback: str = "final_transcript") -> str:
    safe_name = "".join(
        character
        for character in name
        if character.isalnum() or character in (" ", "-", "_")
    ).strip()
    return safe_name or fallback


def clean_spacing(text: str) -> str:
    """Clean reference artifacts and unnecessary Arabic text spacing."""
    text = re.sub(r"\n\s*\d+\s*\n\s*\.\s*", "\n", text)
    text = re.sub(r"\n\s*\d+\s*\n", "\n", text)
    text = re.sub(r"\s*\[[\s\d،,\-]+\]\s*", " ", text)
    text = re.sub(r"\s+([،؛\.;:!\?؟)\]\}»﴾])", r"\1", text)
    text = re.sub(r"([\(\[\{«﴿])\s+", r"\1", text)
    text = re.sub(r"[^\S\n]{2,}", " ", text)
    text = re.sub(r" +\n", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text)


def normalize_implicit_lists(text: str) -> str:
    """Add Markdown bullets to clearly introduced multi-item lists."""

    def plain_line(line: str) -> str:
        line = re.sub(r"<[^>]+>", "", line)
        return line.replace("**", "").replace("#", "").strip()

    def is_formal_subheading(line: str) -> bool:
        if line.lstrip().startswith("<highlight>"):
            return False

        plain = plain_line(line)
        if ":" not in plain:
            return False

        prefix = plain.split(":", 1)[0]
        letter_count = sum(character.isalpha() for character in prefix)
        mark_count = sum(
            bool(unicodedata.combining(character))
            for character in prefix
        )
        return (
            mark_count >= 3
            and letter_count > 0
            and mark_count / letter_count >= 0.18
        )

    lines = text.splitlines()
    implicit_bullets: set[int] = set()

    for index, line in enumerate(lines):
        if not _LIST_INTRODUCTION_RE.search(plain_line(line)):
            continue

        candidates: list[int] = []
        for candidate_index in range(index + 1, min(len(lines), index + 21)):
            candidate = lines[candidate_index].strip()
            if not candidate:
                break
            if candidate.startswith("#"):
                break

            candidate_plain = plain_line(candidate)
            if (
                is_formal_subheading(candidate)
                or _NARRATIVE_START_RE.match(candidate_plain)
            ):
                break

            candidates.append(candidate_index)

        if len(candidates) >= 2:
            implicit_bullets.update(candidates)

    index = 0
    while index < len(lines):
        if not lines[index].lstrip().startswith("<highlight>"):
            index += 1
            continue

        run_start = index
        while (
            index < len(lines)
            and lines[index].lstrip().startswith("<highlight>")
        ):
            index += 1

        if index - run_start >= 2:
            implicit_bullets.update(range(run_start, index))

    for index in implicit_bullets:
        stripped = lines[index].lstrip()
        if not stripped or _EXPLICIT_LIST_RE.match(stripped):
            continue
        indentation = lines[index][: len(lines[index]) - len(stripped)]
        lines[index] = f"{indentation}- {stripped}"

    return "\n".join(lines)


def strip_repeated_heading(text: str, heading: str) -> str:
    """Remove a generated leading title when it repeats the section heading."""

    def normalized(value: str) -> str:
        value = re.sub(r"<[^>]+>", "", value)
        value = value.replace("**", "").replace("#", "")
        value = unicodedata.normalize("NFKD", value)
        value = "".join(
            character
            for character in value
            if not unicodedata.combining(character)
        )
        value = value.translate(
            str.maketrans(
                {
                    "أ": "ا",
                    "إ": "ا",
                    "آ": "ا",
                    "ٱ": "ا",
                    "ى": "ي",
                    "ـ": "",
                }
            )
        )
        return re.sub(r"[\W_]+", "", value, flags=re.UNICODE).casefold()

    def remove_heading_prefix(line: str, normalized_heading: str) -> str | None:
        """Return the text after a repeated heading at the start of a line."""
        matched_end = None
        for end_index in range(1, len(line) + 1):
            normalized_prefix = normalized(line[:end_index])
            if normalized_prefix == normalized_heading:
                matched_end = end_index
            elif matched_end is not None:
                break

        if matched_end is None:
            return None
        return line[matched_end:].strip()

    lines = text.strip().splitlines()
    first_content_index = next(
        (index for index, line in enumerate(lines) if line.strip()),
        None,
    )
    if first_content_index is None:
        return ""

    normalized_heading = normalized(heading)
    while first_content_index < len(lines):
        remaining_text = remove_heading_prefix(
            lines[first_content_index].strip(),
            normalized_heading,
        )
        if remaining_text is None:
            break
        if remaining_text:
            lines[first_content_index] = remaining_text
            break

        del lines[first_content_index]
        while (
            first_content_index < len(lines)
            and not lines[first_content_index].strip()
        ):
            del lines[first_content_index]

    return "\n".join(lines).strip()


def get_current_dates() -> tuple[str, str, str]:
    now = datetime.now()
    gregorian = now.strftime("%Y-%m-%d")
    days = [
        "الإثنين",
        "الثلاثاء",
        "الأربعاء",
        "الخميس",
        "الجمعة",
        "السبت",
        "الأحد",
    ]
    day_name = days[now.weekday()]

    try:
        url = (
            "http://api.aladhan.com/v1/gToH?"
            f"date={now.strftime('%d-%m-%Y')}"
        )
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        with urllib.request.urlopen(request, timeout=3) as response:
            data = json.loads(response.read().decode())
            hijri = data["data"]["hijri"]
            hijri_month = re.sub(
                r"^ذو\s+الحجة$",
                "ذوالحجة",
                hijri["month"]["ar"].strip(),
            )
            hijri_date = (
                f"{hijri['day']} {hijri_month} "
                f"{hijri['year']}هـ"
            )
    except Exception:
        hijri_date = "غير متاح"

    return day_name, hijri_date, gregorian
