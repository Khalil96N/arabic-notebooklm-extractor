import re


def arabic_ordinal(number: int, definite: bool = False) -> str:
    """Return an Arabic masculine ordinal suitable for section headings."""
    units = {
        1: "الأول" if definite else "أولاً",
        2: "الثاني" if definite else "ثانياً",
        3: "الثالث" if definite else "ثالثاً",
        4: "الرابع" if definite else "رابعاً",
        5: "الخامس" if definite else "خامساً",
        6: "السادس" if definite else "سادساً",
        7: "السابع" if definite else "سابعاً",
        8: "الثامن" if definite else "ثامناً",
        9: "التاسع" if definite else "تاسعاً",
        10: "العاشر" if definite else "عاشراً",
    }
    teens = {
        11: "الحادي عشر",
        12: "الثاني عشر",
        13: "الثالث عشر",
        14: "الرابع عشر",
        15: "الخامس عشر",
        16: "السادس عشر",
        17: "السابع عشر",
        18: "الثامن عشر",
        19: "التاسع عشر",
    }
    tens = {
        20: "العشرون",
        30: "الثلاثون",
        40: "الأربعون",
        50: "الخمسون",
        60: "الستون",
        70: "السبعون",
        80: "الثمانون",
        90: "التسعون",
    }

    if number in units:
        return units[number]
    if number in teens:
        return teens[number]
    if number in tens:
        return tens[number]
    if 20 < number < 100:
        unit = units[number % 10]
        if not definite:
            unit = unit.replace("اً", "")
            if number % 10 == 1:
                unit = "الحادي"
            elif number % 10 == 2:
                unit = "الثاني"
            elif not unit.startswith("ال"):
                unit = f"ال{unit}"
        return f"{unit} و{tens[number - (number % 10)]}"

    return f"رقم {number}"


def strip_main_heading_ordinal(title: str) -> str:
    """Remove a generated Arabic ordinal prefix from a heading."""
    match = re.match(r"^\s*([^:：]{1,40})\s*[:：]\s*(.+)$", title)
    if not match:
        return title.strip()

    prefix = _normalize_ordinal(match.group(1))
    known_ordinals = {
        _normalize_ordinal(arabic_ordinal(number, definite=definite))
        for number in range(1, 100)
        for definite in (False, True)
    }
    if prefix in known_ordinals or re.fullmatch(r"رقم\s+\d+", prefix):
        return match.group(2).strip()

    return title.strip()


def number_main_heading(title: str, number: int) -> str:
    clean_title = strip_main_heading_ordinal(title)
    return f"{arabic_ordinal(number)}: {clean_title}"


def _normalize_ordinal(text: str) -> str:
    text = re.sub(r"[\u064B-\u065F\u0670]", "", text)
    return re.sub(r"\s+", " ", text).strip()
