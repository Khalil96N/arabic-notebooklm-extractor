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
_NOTEBOOKLM_UI_ARTIFACT_LINES = {"thoughts", "expand_more"}
_NOTEBOOKLM_UI_ARTIFACT_LINE_RE = re.compile(
    r"(?im)^\s*(?:more_horiz:?|thoughts|expand_more|\d+\s*:)[ \t]*(?:\r?\n|$)"
)
_BULLET_ARTIFACT_LINE_RE = re.compile(
    r"(?m)^\s*[-*+]\s*(?:[0-9\u0660-\u0669]+|[:\uFF1A.\-]+)\s*$(?:\r?\n)?"
)
_BULLET_NUMBER_PREFIX_RE = re.compile(
    r"(?m)^\s*[-*+]\s*[0-9\u0660-\u0669]+[\.)]\s+"
)
_BULLET_PUNCTUATION_PREFIX_RE = re.compile(
    r"(?m)^\s*[-*+]\s*[:\uFF1A.!؟?]\s*"
)
_NBX_MARKER_RE = re.compile(r"\s*\[\[NBX-[^\]\r\n]+\]\]\s*")
_MISSING_OPENING_ANGLE_TAG_RE = re.compile(
    r"(?m)(^|(?<=\s))"
    r"(quran|hadith|sanad|matn|highlight|subheading|"
    r"russian|pronunciation|translation)>"
)
_LINE_SCOPED_STYLE_TAGS = (
    "matn",
    "highlight",
    "russian",
    "pronunciation",
    "translation",
)
_NOTEBOOKLM_FOLLOWUP_OFFER_LINE_RE = re.compile(
    "(?im)^\\s*[^\\w<]*(?:"
    "Would\\s+you\\s+like\\b|"
    "\\u0647\\u0644\\s+\\u062a\\u0631\\u063a\\u0628\\s+"
    "\\u0641\\u064a\\b|"
    "[\\u0623\\u0627]\\u0633\\u062a\\u0637\\u064a\\u0639\\b"
    "[^\\r\\n]*(?:"
    "\\u0627\\u0644\\u0627\\u0646\\u062a\\u0642\\u0627\\u0644|"
    "\\u0627\\u0644\\u0642\\u0633\\u0645|"
    "\\u0644\\u0646\\u0633\\u062a\\u062e\\u0631\\u062c"
    ")"
    ")[^\\r\\n]*(?:\\r?\\n|$)"
)
_NOTEBOOKLM_TABLE_OFFER_LINE_RE = re.compile(
    "(?im)^\\s*[^\\w<]*(?:"
    "\\u064a\\u0645\\u0643\\u0646\\u0646\\u0627|"
    "\\u064a\\u0645\\u0643\\u0646\\u0646\\u064a"
    ")\\s+\\u0639\\u0645\\u0644\\s+"
    "(?:\\u0645\\u0642\\u0627\\u0631\\u0646\\u0629\\s+"
    "\\u062c\\u062f\\u0648\\u0644\\u064a\\u0629|"
    "\\u062c\\u062f\\u0648\\u0644|"
    "\\u0645\\u0644\\u062e\\u0635|"
    "\\u062e\\u0644\\u0627\\u0635\\u0629)"
    "[^\\r\\n]*(?:\\r?\\n|$)"
)

_RUSSIAN_BLOCK_RE = re.compile(
    r"<russian>(.*?)</russian>",
    flags=re.IGNORECASE,
)
_CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
_RUSSIAN_STUDENT_RE = re.compile(
    r"(?:الطالب(?:ة|ان|ات|ين)?|الطلاب|الطالبات|"
    r"لل?طالب(?:ة|ين)?|للطلاب|كل\s+طالب|"
    r"تلميذ(?:ة|ان|ات|ين)?)"
)
_RUSSIAN_STUDENT_TURN_RE = re.compile(
    r"^\s*(?:[-*]\s*)?(?:"
    r"الطالب(?:ة|ان|ات|ين)?|الطلاب|الطالبات|"
    r"قراءة\s+(?:الطالب|الطالبة|الطلاب)|"
    r"ترديد\s+(?:الطالب|الطالبة|الطلاب)|"
    r"إجابة\s+(?:الطالب|الطالبة)|"
    r"(?:حوار|المحادثة)[^\n]{0,120}"
    r"(?:والطالب|والطالبة|مع\s+الطالب|مع\s+الطالبة)"
    r")",
)
_RUSSIAN_INDIVIDUAL_DRILL_RE = re.compile(
    r"(?:قراءة|مراجعة|تدريب|ترديد|محاولة|إجابة|دور|أداء|"
    r"أخطأ|أخطأت|نطق|لفظ|"
    r"يقرأ|تقرأ|يعيد|تعيد|يكرر|تكرر|ينطق|تلفظ|يلفظ|يتلو)"
    r"[^\n]{0,180}"
    r"(?:الطالب|الطالبة|الطالبين|لل?طالب(?:ة|ين)?|كل\s+طالب)"
    r"|(?:الطالب|الطالبة|الطالبين|لل?طالب(?:ة|ين)?|كل\s+طالب)"
    r"[^\n]{0,180}"
    r"(?:قراءة|مراجعة|تدريب|ترديد|محاولة|إجابة|دور|أداء|نطق|لفظ|"
    r"يقرأ|تقرأ|يعيد|تعيد|يكرر|تكرر|ينطق|تلفظ|يلفظ|يتلو|"
    r"أخطأ|أخطأت)",
)
_RUSSIAN_TEACHER_CORRECTION_RE = re.compile(
    r"(?:المعلم(?:ة)?|المعلّم(?:ة)?|المدرّس(?:ة)?|المدرس(?:ة)?)"
    r"[^\n]{0,100}"
    r"(?:صحح|صحّح|تصحح|صححت|صحّحت|تصحيح|صوّب|تصوب|"
    r"صححها|نبه|نبّه|تنبه|تنبّه|تدخل|تتدخل)"
    r"|(?:صحح|صحّح|تصحح|صححت|صحّحت|تصحيح|صوّب|تصوب|"
    r"نبه|نبّه|تنبه|تنبّه|تدخل|تتدخل)"
    r"[^\n]{0,100}"
    r"(?:المعلم(?:ة)?|المعلّم(?:ة)?|المدرّس(?:ة)?|المدرس(?:ة)?)",
)
_RUSSIAN_CLASSROOM_ADMIN_RE = re.compile(
    r"(?:تسجيل\s+(?:ال)?حضور|النداء\s+على\s+أسماء|"
    r"أسماء\s+الحاضرين|المنصة\s+التعليمية|"
    r"اسم\s+(?:علم\s+)?(?:ل)?طالب|"
    r"ال(?:ماي|مي)كروفون(?:ات)?|مكبر\s+الصوت|"
    r"الاتصال\s+بالإنترنت|جودة\s+الاتصال|"
    r"القاعة\s+الإلكترونية|قبول\s+دخول|جداول\s+المجموعات|"
    r"(?:الإعلان\s+عن\s+)?(?:فترة\s+)?الاستراحة|"
    r"استراحة\s+(?:قصيرة|لمدة)|بعد\s+انقضاء\s+الاستراحة|"
    r"استئناف\s+(?:الدرس|المحاضرة)\s+بعد\s+الاستراحة|"
    r"حديث\s+(?:جانبي|تنسيقي)|ترتيبات\s+الحضور|تنظيم\s+الطلاب|"
    r"حوار\s+تنظيمي|معالجة\s+الصوت|سجلات\s+الحضور|"
    r"هل\s+تسمع(?:ني)?\s+جيد|تفضل\s+يا)"
)
_RUSSIAN_CLASSROOM_ADMIN_ITEM_RE = re.compile(
    r"(?:"
    r"<russian>[^<]*(?:"
    r"слыш|микроф|выключ|включен|журнал|списк(?:и|ов)?|"
    r"разрешить|будешь\s+здесь|закроем|ближайшее\s+время|"
    r"отмечайте|завтра\s+у\s+меня\s+будут|сорок\s+пять\s+минут|"
    r"предложи|перешли|четверых|какая\s+группа|что\s+за\s+группа|"
    r"что\s+там|нет\s+зву|значок|Мухаммад|Ярит"
    r")[^<]*</russian>"
    r"|اختبار\s+جودة\s+الصوت|تسوية\s+حضور|"
    r"<russian>[^<]*(?:переры[\u0300-\u036f]*в|брейк|отдохни[\u0300-\u036f]*те|\d+\s+минут)[^<]*</russian>|"
    r"تصويب\s+إداري|كلمات\s+إدارية|تدقيق\s+سجلات\s+الحضور|"
    r"الحديث\s+الإداري|المنصة\s+الرقمية|لا\s+يوجد\s+صوت|إغلاق\s+القاعة|"
    r"اطفئ\s+الأجهزة|قوائم\s+المجموعات"
    r")",
    flags=re.IGNORECASE,
)


_BROKEN_INLINE_MATH_RE = re.compile(
    r"([xw])\s*\n\s*(?:-\s*)?\u200b"
)


def repair_notebooklm_math_artifacts(text: str) -> str:
    """Repair subscripts split by NotebookLM's rendered response DOM."""
    text = re.sub(
        r"x\s*\n\s*n\s*\n\s*(?:-\s*)?\u200b",
        "xₙ",
        text,
    )
    text = re.sub(
        r"y\s*\n\s*\^\s*\n\s*\u200b",
        "ŷ",
        text,
    )
    text = _BROKEN_INLINE_MATH_RE.sub(
        lambda match: f"{match.group(1)}<missing-subscript>",
        text,
    )

    chunks = re.split(
        r"(?=^##\s)|(?=^<subheading>)",
        text,
        flags=re.MULTILINE,
    )
    repaired_chunks: list[str] = []
    for chunk in chunks:
        counters = {"x": 0, "w": 0}

        def restore_subscript(match: re.Match) -> str:
            variable = match.group(1)
            counters[variable] += 1
            subscript = "₁" if counters[variable] % 2 else "₂"
            return f"{variable}{subscript}"

        chunk = re.sub(
            r"([xw])<missing-subscript>",
            restore_subscript,
            chunk,
        )
        repaired_chunks.append(chunk)

    text = "".join(repaired_chunks)

    math_token = r"(?:[xw][₁₂₃ₙ]|ŷ)"
    text = re.sub(
        rf"({math_token})\s*\n+\s*(?=[(،,)=+\-])",
        r"\1",
        text,
    )
    text = re.sub(
        rf"([،,+\-=])\s*\n+\s*(?={math_token})",
        r"\1 ",
        text,
    )
    text = re.sub(
        rf"({math_token})\s*\n+\s*(?={math_token}|و\s+{math_token}|"
        r"يمثلان|تمثل|يمثل)",
        r"\1 ",
        text,
    )
    text = re.sub(
        rf"([^\n])\n+\s*(?=ŷ(?:\s|[،,:؛؛.؟?()]))",
        r"\1 ",
        text,
    )
    text = text.replace("\u200b", "").replace("\ufeff", "")
    return text


def ensure_output_dir() -> None:
    settings.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def safe_output_name(name: str, fallback: str = "final_transcript") -> str:
    safe_name = "".join(
        character
        for character in name
        if character.isalnum() or character in (" ", "-", "_")
    ).strip()
    return safe_name or fallback


def _is_notebooklm_ui_artifact(line: str) -> bool:
    return line.strip().casefold() in _NOTEBOOKLM_UI_ARTIFACT_LINES


def _delete_line_and_following_blanks(lines: list[str], index: int) -> None:
    del lines[index]
    while index < len(lines) and not lines[index].strip():
        del lines[index]


def clean_spacing(text: str) -> str:
    """Clean reference artifacts and unnecessary Arabic text spacing."""
    text = repair_notebooklm_math_artifacts(text)
    # NotebookLM occasionally misspells or duplicates the requested Russian
    # study-block closing tags. Repair them before balancing line-scoped tags.
    text = re.sub(
        r"</pron(?!unciation\b)[^>]*>",
        "</pronunciation>",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"</\s*</translation>",
        "</translation>",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"</?clarification>",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"</?raw>",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"(<translation>[^<]*?)\s*(<highlight>.*?</highlight>)\s*"
        r"</translation>",
        r"\1</translation> \2",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"(?m)^\s*<russian>(.*?)</russian>\s*\(([^)\r\n]+)\)\s*$",
        (
            r"<russian>\1</russian> "
            r"<pronunciation>اللفظ بالعربية: \2</pronunciation> "
            r"<translation>المعنى بالعربية: لم يذكر المصدر معنى مستقلاً؛ "
            r"استُخدم العنصر للتدريب على النطق أو الإملاء</translation>"
        ),
        text,
    )
    text = _MISSING_OPENING_ANGLE_TAG_RE.sub(r"<\2>", text)
    text = _balance_line_scoped_style_tags(text)

    for artifact_pattern in (
        _BULLET_ARTIFACT_LINE_RE,
        _BULLET_NUMBER_PREFIX_RE,
        _BULLET_PUNCTUATION_PREFIX_RE,
        _NBX_MARKER_RE,
        _NOTEBOOKLM_UI_ARTIFACT_LINE_RE,
        _NOTEBOOKLM_FOLLOWUP_OFFER_LINE_RE,
        _NOTEBOOKLM_TABLE_OFFER_LINE_RE,
    ):
        text = artifact_pattern.sub("", text)

    text = re.sub(r"\n\s*\d+\s*\n\s*\.\s*", "\n", text)
    text = re.sub(r"\n\s*\d+\s*\n", "\n", text)
    # A trailing citation marker has no following newline to anchor on, so it
    # survives the pattern above and leaks into the document as its own line.
    text = re.sub(r"\n\s*\d+\s*$", "", text)
    text = re.sub(r"\s*\[[\s\d،,\-]+\]\s*", " ", text)
    text = re.sub(r"\s+([،؛\.;:!\?؟)\]\}»﴾])", r"\1", text)
    text = re.sub(r"([\(\[\{«﴿])\s+", r"\1", text)
    text = re.sub(r"[^\S\n]{2,}", " ", text)
    text = re.sub(r" +\n", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text)


def _russian_item_key(value: str) -> str:
    """Normalize one Cyrillic study item for conservative deduplication."""
    value = unicodedata.normalize("NFKD", value)
    value = "".join(
        character
        for character in value
        if not unicodedata.combining(character)
    )
    return re.sub(r"[\W_]+", "", value, flags=re.UNICODE).casefold()


def _remove_student_specific_correction_context(line: str) -> str:
    """Keep a teacher's correction while removing the student's turn details."""
    russian_start = line.casefold().find("<russian>")
    if russian_start > 0:
        line = line[russian_start:]

    line = re.sub(
        r"\s*\([^()\n]*(?:الطالب|الطالبة|الطلاب)[^()\n]*\)",
        "",
        line,
    )
    line = re.sub(
        r"\s*<highlight>[^\n<]*(?:الطالب|الطالبة|الطلاب)"
        r"[^\n<]*</highlight>",
        "",
        line,
        flags=re.IGNORECASE,
    )
    return line.strip()


def _remove_individual_student_sentences(line: str) -> str:
    """Drop personal drill sentences while retaining general teaching context."""
    sentences = re.split(r"(?<=[.!؟])\s+", line)
    useful_sentences = [
        sentence
        for sentence in sentences
        if not (
            _RUSSIAN_STUDENT_RE.search(sentence)
            and (
                _RUSSIAN_STUDENT_TURN_RE.search(sentence)
                or _RUSSIAN_INDIVIDUAL_DRILL_RE.search(sentence)
            )
        )
    ]
    return " ".join(useful_sentences).strip()


def _remove_classroom_admin_sentences(line: str) -> str:
    """Remove administrative sentences without discarding adjacent teaching."""
    sentences = re.split(r"(?<=[.!؟])\s+", line)
    return " ".join(
        sentence
        for sentence in sentences
        if not _RUSSIAN_CLASSROOM_ADMIN_RE.search(sentence)
    ).strip()


def _strip_personal_greeting_address(line: str) -> str:
    """Turn a teacher's name-specific greeting into the reusable greeting."""
    russian_match = _RUSSIAN_BLOCK_RE.search(line)
    if not russian_match or "," not in russian_match.group(1):
        return line

    _address, greeting = russian_match.group(1).split(",", 1)
    greeting_key = _russian_item_key(greeting)
    if not any(
        greeting_word in greeting_key
        for greeting_word in ("добры", "доброе", "привет", "здравств")
    ):
        return line

    line = re.sub(
        r"<russian>[^<,]+,\s*",
        "<russian>",
        line,
        count=1,
        flags=re.IGNORECASE,
    )
    line = re.sub(
        r"(<pronunciation>[^<:]+:\s*)[^<،]+،\s*",
        r"\1",
        line,
        count=1,
        flags=re.IGNORECASE,
    )
    line = re.sub(
        r"(<translation>[^<:]+:\s*)[^<،]+،\s*",
        r"\1",
        line,
        count=1,
        flags=re.IGNORECASE,
    )
    return line


def compact_russian_classroom_content(text: str) -> str:
    """Remove student-by-student drills while preserving useful Russian teaching.

    Russian course exports are study notes, not attendance logs or verbatim
    classroom transcripts.  The prompt already asks NotebookLM to omit student
    turns; this conservative post-processing pass is a second guard for the
    common cases where it still emits attendance, technical chatter, individual
    repetitions, or an exact duplicate Russian study item.
    """
    text = clean_spacing(text)
    compacted_lines: list[str] = []
    seen_russian_items: set[str] = set()

    for original_line in text.splitlines():
        line = original_line.strip()
        if not line:
            if compacted_lines and compacted_lines[-1]:
                compacted_lines.append("")
            continue

        # Preserve the lesson summary, but avoid carrying attendance-style
        # parentheticals with individual student names into the study notes.
        line = re.sub(
            r"الطلاب\s+الحاضرين\s*\([^)]*\)",
            "الطلاب",
            line,
        )
        line = _strip_personal_greeting_address(line)
        russian_items = _RUSSIAN_BLOCK_RE.findall(line)
        if russian_items and _RUSSIAN_CLASSROOM_ADMIN_ITEM_RE.search(line):
            continue
        if russian_items and not any(
            _CYRILLIC_RE.search(item) for item in russian_items
        ):
            # NotebookLM occasionally wraps an English classroom instruction
            # in the Russian tag. It is outside the Russian study material.
            continue
        has_student_reference = bool(_RUSSIAN_STUDENT_RE.search(line))
        is_student_turn = bool(
            _RUSSIAN_STUDENT_TURN_RE.search(line)
            or _RUSSIAN_INDIVIDUAL_DRILL_RE.search(line)
        )
        is_teacher_correction = bool(
            _RUSSIAN_TEACHER_CORRECTION_RE.search(line)
        )
        is_classroom_admin = bool(_RUSSIAN_CLASSROOM_ADMIN_RE.search(line))

        if is_classroom_admin:
            line = _remove_classroom_admin_sentences(line)
            if not line:
                continue
            russian_items = _RUSSIAN_BLOCK_RE.findall(line)
            has_student_reference = bool(_RUSSIAN_STUDENT_RE.search(line))
            is_student_turn = bool(
                _RUSSIAN_STUDENT_TURN_RE.search(line)
                or _RUSSIAN_INDIVIDUAL_DRILL_RE.search(line)
            )

        if not russian_items:
            if has_student_reference and is_student_turn:
                line = _remove_individual_student_sentences(line)
                if not line:
                    continue
            if re.match(
                r"^(?:بعد\s+انتهاء\s+المحاولة|ينتقل\s+التدريب\s+مع|"
                r"تمرين\s+القراءة[^\n]*\([^)]*[اأإآء-ي][^)]*\))",
                line,
            ):
                continue
            compacted_lines.append(line)
            continue

        item_keys = {
            key
            for item in russian_items
            if (key := _russian_item_key(item))
        }

        if has_student_reference and is_student_turn:
            if not is_teacher_correction:
                continue
            line = _remove_student_specific_correction_context(line)
            if not line:
                continue

        if item_keys and item_keys.issubset(seen_russian_items):
            # Keep a genuinely new teacher note even when its Russian example
            # repeats, but never keep a duplicate individual correction turn.
            if "<highlight>" not in line.casefold() or has_student_reference:
                continue

        seen_russian_items.update(item_keys)
        compacted_lines.append(line)

    return re.sub(
        r"\n{3,}",
        "\n\n",
        "\n".join(compacted_lines),
    ).strip()


def _balance_line_scoped_style_tags(text: str) -> str:
    """Keep matn/highlight styling from leaking into later paragraphs."""
    balanced_lines: list[str] = []
    for original_line in text.splitlines():
        line = original_line
        for tag in _LINE_SCOPED_STYLE_TAGS:
            pattern = re.compile(rf"</?{tag}>", re.IGNORECASE)
            parts: list[str] = []
            position = 0
            depth = 0
            for match in pattern.finditer(line):
                parts.append(line[position : match.start()])
                token = match.group(0)
                if token.startswith("</"):
                    if depth:
                        depth -= 1
                        parts.append(token)
                else:
                    depth += 1
                    parts.append(token)
                position = match.end()
            parts.append(line[position:])
            if depth:
                parts.extend(f"</{tag}>" for _ in range(depth))
            line = "".join(parts)

        if original_line.strip() and not line.strip():
            continue
        balanced_lines.append(line)
    return "\n".join(balanced_lines)


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


def normalize_arabic_key(value: str) -> str:
    """Normalize Arabic text for loose heading/title comparison.

    Strips tags and Markdown emphasis, folds diacritics and alef/yaa
    variants, drops remaining punctuation/whitespace, and casefolds the
    result so two headings that differ only in diacritics, alef spelling, or
    spacing compare equal.
    """
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


def strip_repeated_heading(text: str, heading: str) -> str:
    """Remove a generated leading title when it repeats the section heading."""

    def remove_heading_prefix(line: str, normalized_heading: str) -> str | None:
        """Return the text after a repeated heading at the start of a line."""
        matched_end = None
        for end_index in range(1, len(line) + 1):
            normalized_prefix = normalize_arabic_key(line[:end_index])
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

    while (
        first_content_index < len(lines)
        and _is_notebooklm_ui_artifact(lines[first_content_index])
    ):
        _delete_line_and_following_blanks(lines, first_content_index)

    if first_content_index >= len(lines):
        return ""

    while first_content_index < len(lines):
        lines[first_content_index] = _NBX_MARKER_RE.sub(
            "",
            lines[first_content_index],
        ).lstrip()
        if lines[first_content_index].strip():
            break
        _delete_line_and_following_blanks(lines, first_content_index)

    if first_content_index >= len(lines):
        return ""

    normalized_heading = normalize_arabic_key(heading)
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

        _delete_line_and_following_blanks(lines, first_content_index)

    return "\n".join(lines).strip()


_RULE_SUBHEADING_RE = re.compile(
    r"<subheading>\s*(.*?)\s*</subheading>",
    re.IGNORECASE | re.DOTALL,
)


def parse_rule_blocks(text: str) -> list[tuple[str | None, str]]:
    """Split one rules-section text into its individual <subheading> blocks.

    Returns a list of (title, block_text) pairs in order. Content appearing
    before the first <subheading> tag (e.g. a "no new rule in this part"
    fallback line) is kept as its own block with a `None` title so it is
    never treated as a match for a real rule name.
    """
    text = text.strip()
    if not text:
        return []

    starts = [
        match.start()
        for match in re.finditer(r"<subheading>", text, re.IGNORECASE)
    ]
    if not starts:
        return [(None, text)]

    blocks: list[tuple[str | None, str]] = []
    if starts[0] > 0:
        leading = text[: starts[0]].strip()
        if leading:
            blocks.append((None, leading))

    boundaries = starts[1:] + [len(text)]
    for start, end in zip(starts, boundaries):
        block_text = text[start:end].strip()
        match = _RULE_SUBHEADING_RE.match(block_text)
        title = match.group(1).strip() if match else None
        blocks.append((title, block_text))
    return blocks


def merge_adjacent_rule_chunks(chunk_texts: list[str]) -> str:
    """Join per-chunk rules-section texts, merging a rule split across a
    chunk boundary into one block instead of leaving two separate,
    near-duplicate <subheading> entries.

    Each Russian lesson chunk is extracted independently, so a grammar rule
    the teacher starts explaining near the end of one chunk and finishes at
    the start of the next comes back as two blocks with the same heading.
    This walks the flattened block sequence and appends a block onto the
    previous one whenever their normalized titles match, dropping the
    repeated <subheading> line from the continuation.
    """
    merged: list[tuple[str | None, str]] = []
    for chunk_text in chunk_texts:
        for title, block_text in parse_rule_blocks(chunk_text):
            previous = merged[-1] if merged else None
            if (
                previous is not None
                and title is not None
                and previous[0] is not None
                and normalize_arabic_key(title) == normalize_arabic_key(previous[0])
            ):
                continuation = _RULE_SUBHEADING_RE.sub(
                    "", block_text, count=1
                ).strip()
                merged[-1] = (
                    previous[0],
                    f"{previous[1]}\n{continuation}".strip(),
                )
            else:
                merged.append((title, block_text))

    return "\n\n".join(block_text for _title, block_text in merged)


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
