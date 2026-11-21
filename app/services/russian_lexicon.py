"""Lossless, lemma-centred Russian vocabulary, independent of extraction prompts.

The original cumulative state is never rewritten here.  Source records and their
pronunciations remain attached to entries so a lexical merge is reversible.
Morphological predictions are NOT silently treated as dictionary attestations.
"""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
import unicodedata

VERSION = 2
RESOURCE_DIR = Path(__file__).resolve().parents[1] / "resources"
REFERENCE_FILE = RESOURCE_DIR / "russian_morphology.json"
OVERRIDES_FILE = RESOURCE_DIR / "russian_lexicon_overrides.json"
LEXICON_FILENAME = ".russian_lexicon.json"
VOWELS = "аеёиоуыэюя"
CASES = ("nomn", "gent", "datv", "accs", "ablt", "loct")
CASE_LABELS = (
    "1 الرفع", "2 المضاف إليه", "3 الداتيف",
    "4 النصب", "5 الآلة والمصاحبة", "6 الجر بحرف جر",
)
PERSONS = (
    ("я", "sing", "1per"), ("ты", "sing", "2per"),
    ("он / она / оно", "sing", "3per"), ("мы", "plur", "1per"),
    ("вы", "plur", "2per"), ("они", "plur", "3per"),
)
SECTIONS = ("الأفعال", "الأسماء", "الصفات", "الضمائر", "الظروف", "الأعداد", "العبارات والتعبيرات")
POS_SECTION = {
    "VERB": "الأفعال", "INFN": "الأفعال", "NOUN": "الأسماء",
    "ADJF": "الصفات", "ADJS": "الصفات", "COMP": "الصفات",
    "NPRO": "الضمائر", "ADVB": "الظروف", "PRED": "الظروف", "NUMR": "الأعداد",
}
TOPICS = (
    "التحيات واللباقة", "الصف والتعلم", "اللغة والقواعد", "العائلة",
    "الأشخاص والمهن", "الضمائر والإشارة", "البيت والأثاث", "الملابس والأغراض",
    "الطعام والشراب", "الأماكن والجغرافيا", "الحركة والمواصلات", "العمل والأنشطة",
    "التواصل والمعرفة", "الوقت والتاريخ", "الطبيعة والطقس", "الجسم والصحة",
    "الألوان والأوصاف", "الثقافة والترفيه", "العلوم والتقنية", "الأعداد والحساب", "تعبيرات عامة",
)
FAMILIES = (
    ("писать", "написать"), ("повторять", "повторить"), ("проверять", "проверить"),
    ("учить", "учиться", "изучать"), ("слушать", "послушать"),
    ("спрашивать", "отвечать", "ответить"), ("говорить", "сказать", "разговаривать"),
    ("знать", "понимать", "думать"), ("звонить", "позвонить"),
    ("покупать", "купить"), ("брать", "взять", "дать"), ("любить", "нравиться"),
    ("завтракать", "обедать", "ужинать"), ("работать", "отдыхать"),
    ("мама", "мать", "папа", "отец", "родитель"), ("брат", "сестра"), ("сын", "дочь", "дочка"),
    ("муж", "жена"), ("бабушка", "дедушка"), ("внук", "внучка"), ("дядя", "тётя"),
    ("студент", "студентка"), ("ученик", "школьник", "школьница"),
    ("преподаватель", "учитель", "профессор"), ("журналист", "журналистка"),
    ("спортсмен", "спортсменка"), ("актёр", "актриса"), ("друг", "подруга", "товарищ", "коллега"),
    ("бизнесмен", "бизнесвумен"), ("пенсионер", "пенсионерка"), ("ноль", "нуль"), ("ластик", "резинка"),
    ("гласный", "согласный"), ("звонкий", "глухой"), ("одушевлённый", "неодушевлённый"),
    ("новый", "старый"), ("большой", "маленький"), ("хороший", "плохой"),
    ("дорогой", "дешёвый"), ("бедный", "богатый"), ("тяжёлый", "лёгкий"),
    ("сильный", "слабый"), ("чистый", "грязный"), ("умный", "глупый"),
    ("грустный", "весёлый"), ("трудный", "простой"), ("высокий", "низкий"),
    ("длинный", "короткий"), ("широкий", "узкий"), ("толстый", "тонкий"),
    ("красивый", "некрасивый"), ("вкусный", "невкусный"), ("холодный", "тёплый", "жаркий"),
    ("белый", "чёрный", "серый", "красный", "оранжевый", "жёлтый", "зелёный", "голубой", "синий", "фиолетовый", "розовый", "коричневый"),
)
CATEGORY_TOPIC = {
    "التحيات والوداعات": TOPICS[0], "الصف والتعليمات": TOPICS[1],
    "القواعد والمصطلحات": TOPICS[2], "العائلة": TOPICS[3],
    "الأشخاص والمهن": TOPICS[4], "الضمائر وأسماء الإشارة": TOPICS[5],
    "البيت والأثاث": TOPICS[6], "الملابس والأغراض الشخصية": TOPICS[7],
    "الطعام والشراب": TOPICS[8], "الأماكن والمواصلات": TOPICS[9],
    "الزمن والتاريخ": TOPICS[13], "الطقس والطبيعة": TOPICS[14],
    "الجسم والصحة": TOPICS[15], "الصفات": TOPICS[16],
    "الثقافة والألعاب": TOPICS[17], "العلوم والتقنية": TOPICS[18],
    "الأعداد والكميات": TOPICS[19],
}


def key(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text).replace("\u0301", "").replace("'", "")).strip().casefold()


def _json(path: Path, default: dict | None = None) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else (default or {})


@lru_cache(maxsize=1)
def reference() -> dict:
    return _json(REFERENCE_FILE, {"entries": {}, "stress": {}})


@lru_cache(maxsize=1)
def overrides() -> dict:
    return _json(OVERRIDES_FILE)


@lru_cache(maxsize=1)
def analyzer():
    try:
        import pymorphy3
    except ImportError as exc:
        raise RuntimeError("Russian dictionary export needs pymorphy3; install requirements.txt first.") from exc
    return pymorphy3.MorphAnalyzer()


def _tokens(text: str) -> list[str]:
    return re.findall(r"[а-яё]+(?:-[а-яё]+)*", key(text))


def _meaning_key(text: str) -> str:
    return re.sub(r"[^\w]+", "", "".join(c for c in unicodedata.normalize("NFKD", text.casefold()) if not unicodedata.combining(c)))


def clean_meanings(values: list[str]) -> str:
    """Deduplicate alternatives without damaging slashes inside parentheses."""
    result, seen = [], set()
    for text in values:
        depth, start, parts = 0, 0, []
        for i, char in enumerate(text):
            depth += (char == "(") - (char == ")")
            if char == "/" and depth == 0:
                parts.append(text[start:i]); start = i + 1
        parts.append(text[start:])
        for part in parts:
            part = part.strip(" /;؛").replace("ۆ", "و")
            normalized = _meaning_key(part)
            if normalized and normalized not in seen:
                result.append(part); seen.add(normalized)
    return " / ".join(result)


def select_parse(word: str, source: dict | None = None):
    source = source or {}
    word = key(word).strip(".!?؟…")
    parses = analyzer().parse(word)
    known = [p for p in parses if p.is_known]
    if not known:
        # A prediction may be used only for a lemma explicitly present in the
        # reference (e.g. парковать missing from this OpenCorpora release).
        refs = reference().get("entries", {})
        known = [p for p in parses if f"{_lexical_pos(p)}:{p.normal_form}" in refs]
        if not known:
            return None
    override = dict(overrides().get("analysis", {}).get(word, {}))
    if word in ("стоит", "стоят") and re.search(r"\bstand(?:s|ing)?\b", source.get("english", ""), re.IGNORECASE):
        override["lemma"] = "стоять"
    if word == "газа" and not re.search(r"\bgaza\b", source.get("english", ""), re.IGNORECASE):
        override = {}
    desired = override.get("pos")
    lemma = override.get("lemma")
    candidates = [p for p in known if (not desired or p.tag.POS == desired) and (not lemma or p.normal_form == lemma)]
    if not candidates:
        return None
    refs = reference().get("entries", {})
    direct = [(pos, refs.get(f"{pos}:{word}")) for pos in ("NOUN", "INFN", "ADJF")]
    direct = [pos for pos, data in direct if data]
    if not desired and len(direct) == 1:
        target = direct[0]
        matching = [p for p in candidates if p.tag.POS == target or target == "INFN" and p.tag.POS == "VERB"]
        if matching:
            candidates = matching
    # Dictionary parses can include impersonal homonyms that cannot supply
    # six personal forms (e.g. стоит meaning 'one should').
    personal = [p for p in candidates if "Impe" not in p.tag and "Impx" not in p.tag]
    if personal:
        candidates = personal
    english = source.get("english", "").casefold()
    command = re.match(r"(?:read|write|speak|talk|tell|compare|check|verify|repeat|listen|look|show|give|answer|begin|start|excuse|forgive|get acquainted|meet|stop|stand still|memorize|remember|have a good rest)(?:\b|$)", english)
    if command and not re.search(r"\b(?:we|you|he|she|they|i)\b", english):
        imperative = [p for p in candidates if p.tag.mood == "impr" and "excl" in p.tag]
        if imperative:
            candidates = imperative
    category = source.get("category", "")
    meaning = (source.get("english", "") + " " + source.get("arabic", "")).casefold()
    if not re.search(r"\b(?:name|surname)\b", meaning) and "علم" not in meaning:
        common = [p for p in candidates if not set(p.tag.grammemes) & {"Name", "Surn", "Patr"}]
        if common:
            candidates = common
    if "female name" in meaning or "علم مؤنث" in meaning:
        names = [p for p in candidates if "Name" in p.tag and p.tag.gender == "femn" and p.tag.case == "nomn"]
        if names:
            candidates = names
    if "ضم" in category:
        pronouns = [p for p in candidates if p.tag.POS == "NPRO" or "Apro" in p.tag]
        if pronouns:
            candidates = pronouns
    return max(candidates, key=lambda p: p.score)


def _lexical_pos(parse) -> str:
    pos = parse.tag.POS
    if pos in ("VERB", "INFN"):
        return "INFN"
    if pos == "ADJS":
        return "ADJF"
    if "Apro" in parse.tag:
        if parse.normal_form == "один":
            return "NUMR"
        return "NPRO"
    return pos or "PHRASE"


def analyse_source(source: dict) -> dict:
    """Only collapse aliases if ALL alternatives resolve to the same lexeme."""
    original = source.get("russian", "").strip()
    custom = overrides().get("sources", {}).get(key(original), {})
    if custom.get("meaning_pattern") and not re.search(custom["meaning_pattern"], source.get("english", ""), re.IGNORECASE):
        custom = {}
    if custom.get("pos") and custom.get("lemma"):
        return {"id": custom["pos"] + ":" + custom["lemma"], "lemma": custom["lemma"], "pos": custom["pos"], "parses": [], "usage": []}
    if custom.get("keep_phrase"):
        return {"id": "PHRASE:" + key(original), "lemma": original, "pos": "PHRASE", "parses": [], "usage": []}
    parts = re.split(r"\s*/\s*", original)
    found, usage = [], []
    for part in parts:
        part_key = key(part).strip(".!?؟…")
        phrase_match = re.fullmatch(r"(в|во|на|из|с|со|к|ко|о|об|обо|у|без|для|по)\s+([а-яё-]+)", part_key)
        word = phrase_match[2] if phrase_match else part_key
        if not re.fullmatch(r"[а-яё]+(?:-[а-яё]+)*", word):
            found = []; break
        parse = select_parse(word, source)
        if parse is None:
            found = []; break
        pos = _lexical_pos(parse)
        # Only simple preposition + noun constructions are attached to nouns.
        if phrase_match and pos != "NOUN":
            found = []; break
        if phrase_match:
            cases = {"в": {"accs", "loct", "loc2"}, "во": {"accs", "loct", "loc2"}, "на": {"accs", "loct", "loc2"},
                     "из": {"gent", "gen2"}, "с": {"gent", "gen2", "ablt"}, "со": {"gent", "gen2", "ablt"},
                     "к": {"datv"}, "ко": {"datv"}, "о": {"loct"}, "об": {"loct"}, "обо": {"loct"},
                     "у": {"gent"}, "без": {"gent"}, "для": {"gent"}, "по": {"datv", "loct"}}[phrase_match[1]]
            fits = [p for p in analyzer().parse(word) if p.normal_form == parse.normal_form and p.tag.POS == "NOUN" and p.tag.case in cases]
            if fits:
                parse = max(fits, key=lambda p:p.score)
            usage.append({"russian": part, "preposition": phrase_match[1], "case": parse.tag.case, "number": parse.tag.number})
        elif pos == "NOUN" and parse.tag.case == "ablt" and parse.normal_form in ("утро", "день", "вечер", "ночь", "зима", "весна", "лето", "осень"):
            usage.append({"russian": part, "preposition": "", "case": "ablt", "number": parse.tag.number, "role": "time"})
        found.append(parse)
    if found and len({(p.normal_form, _lexical_pos(p)) for p in found}) == 1:
        parse = found[0]
        pos = _lexical_pos(parse)
        lemma = parse.normal_form
        if pos == "COMP":
            lemma = key(original).strip(".!?؟…")
        lemma = overrides().get("analysis", {}).get(key(original), {}).get("display_lemma", lemma)
        pos = overrides().get("analysis", {}).get(key(original), {}).get("display_pos", pos)
        return {"id": f"{pos}:{lemma}", "lemma": lemma, "pos": pos, "parses": found, "usage": usage}
    return {"id": "PHRASE:" + key(original), "lemma": original, "pos": "PHRASE", "parses": [], "usage": []}


def _topic(entry: dict) -> str:
    custom = overrides().get("entries", {}).get(entry["id"], {})
    if custom.get("topic"):
        return custom["topic"]
    lemma = entry["lemma"]
    verb_topics = {
        "الصف والتعلم": "читать писать учить учиться изучать повторять запоминать проверять сравнить проверить повторить написать слушать послушать обозначать уменьшать",
        "التواصل والمعرفة": "говорить сказать разговаривать звонить позвонить знать понимать думать дружить спрашивать отвечать ответить показать познакомиться называть называться извинить",
        "الحركة والمواصلات": "идти ходить ехать ездить лететь летать войти находиться бывать парковать стоять",
        "الطعام والشراب": "есть пить готовить завтракать обедать ужинать",
        "العمل والأنشطة": "работать делать отдыхать играть покупать купить брать взять дать любить нравиться думать слушать послушать смотреть посмотреть начать начинать продолжать устать мочь стоить петь быть отправить",
    }
    if entry["pos"] == "INFN":
        for topic, words in verb_topics.items():
            if lemma in words.split():
                return topic
        return "العمل والأنشطة"
    if entry["pos"] == "NPRO":
        return "الضمائر والإشارة"
    if entry["pos"] in ("ADJF", "ADJS", "COMP"):
        return "الألوان والأوصاف"
    if entry["pos"] == "NUMR":
        return "الأعداد والحساب"
    topic = next((CATEGORY_TOPIC[s.get("category", "")] for s in entry["sources"] if s.get("category") in CATEGORY_TOPIC), "تعبيرات عامة")
    # The old classroom category also contained ordinary nouns; use clear
    # semantic signals, never a substring such as Arabic أم inside أماكن.
    meanings = " ".join(s.get("english", "").casefold() for s in entry["sources"])
    if entry["pos"] == "NOUN" and re.search(r"\b(teacher|professor|student|pupil|schoolgirl|schoolboy|doctor|engineer|journalist|scientist|translator|coach|waiter|diplomat|secretary|lawyer|judge|programmer|colleague|housewife|artist|actor|actress|worker|cook)\b", meanings):
        return "الأشخاص والمهن"
    if lemma in "пружина магний ток инструмент ноутбук робот радар реактор техника код сайт аппарат галактика йод магнит гугл".split():
        return "العلوم والتقنية"
    groups = (
        ("الطعام والشراب", r"\b(food|bread|milk|tea|coffee|apple|juice|water|rice|meat|fish|cheese|soup|fruit|vegetable|banana|cucumber|tomato|potato|sugar|salt|butter|egg|lemon|carrot|onion|grape|breakfast|lunch|dinner)\b"),
        ("العائلة", r"\b(mother|father|mom|dad|grandmother|grandfather|brother|sister|daughter|son|husband|wife|aunt|uncle|family|parent)\b"),
        ("البيت والأثاث", r"\b(furniture|sofa|armchair|chair|table|window|door|bed|kitchen|apartment|cupboard|wardrobe|bathroom|ceiling|floor|mirror|carpet|balcony|bedroom)\b"),
        ("الملابس والأغراض", r"\b(clothes|coat|jacket|dress|shirt|trousers|pants|shoe|boot|sock|scarf|hat|skirt|sweater|suit|glove|bag|ring|passport|towel|umbrella)\b"),
        ("الصف والتعلم", r"\b(lesson|exercise|notebook|pencil|pen|eraser|book|textbook|homework|text|dictionary|classroom|ruler)\b"),
        ("الوقت والتاريخ", r"\b(year|month|week|day|night|evening|morning|hour|minute|second|season|winter|summer|autumn|spring|holiday|today|tomorrow|yesterday)\b"),
        ("الحركة والمواصلات", r"\b(bus|tram|train|metro|car|taxi|plane|bicycle|motorcycle|ship|boat|tire|tyre|transport|airport|station)\b"),
        ("الأماكن والجغرافيا", r"\b(city|country|village|capital|school|university|office|hospital|clinic|shop|store|museum|theatre|theater|stadium|restaurant|park|square|street|avenue|bank|library|dormitory|building|hotel|factory|pharmacy|sea|ocean|river|island|mountain|continent|palace|bridge)\b"),
        ("الجسم والصحة", r"\b(body|head|hand|arm|leg|foot|eye|ear|nose|mouth|tooth|teeth|hair|heart|stomach|health|medicine|pain)\b"),
        ("الطبيعة والطقس", r"\b(weather|rain|snow|sun|sky|cloud|wind|tree|flower|forest|garden|leaf|animal|bird|cat|dog|horse|cow|lion|turtle|whale|puma|toad|beetle|hedgehog|monkey|goat|turkey|ferret|oak|fir)\b"),
        ("الأشخاص والمهن", r"\b(student|teacher|professor|doctor|engineer|journalist|worker|pensioner|friend|person|people|child|boy|girl|man|woman|name|surname|nationality)\b"),
        ("الأعداد والحساب", r"\b(number|quantity|rouble|ruble|dollar|price|sum|equation|fraction|numerator|denominator|mathematical|plus|minus|multiply|divide|percent)\b"),
        ("الثقافة والترفيه", r"\b(film|movie|cinema|music|song|poem|poetry|sport|game|chess|football|tennis|guitar|piano|dance|ballet|concert)\b"),
    )
    if entry["pos"] == "NOUN" or topic in ("تعبيرات عامة", "الصف والتعلم"):
        for candidate, pattern in groups:
            if re.search(pattern, meanings):
                return candidate
    return topic


def _with_stress(text: str) -> str:
    """OpenRussian marks stress with an apostrophe AFTER the vowel."""
    return unicodedata.normalize("NFC", text.replace("'", "\u0301"))


def stressed_form(word: str, entry: dict, field: str = "") -> tuple[str, str]:
    custom = overrides().get("entries", {}).get(entry["id"], {})
    explicit = custom.get("forms", {}).get(field)
    if explicit:
        return explicit, "reviewed_override"
    if field == "lemma" and custom.get("stress"):
        return custom["stress"], "reviewed_override"
    ref = reference().get("entries", {}).get(entry["id"], {})
    candidates = re.split(r"[,;/]+", ref.get(field, "")) if field else []
    for value in candidates:
        if key(value) == key(word):
            return _with_stress(value.strip()), "OpenRussian"
    if field == "lemma" and ref.get("accented") and key(ref["accented"]) == key(word):
        return _with_stress(ref["accented"]), "OpenRussian"
    observed = [s for s in entry["sources"] if key(s["russian"]) == key(word)]
    for source in observed:
        if "\u0301" in source["russian"] or "ё" in source["russian"].lower():
            return source["russian"].lower(), "course"
    candidates = reference().get("stress", {}).get(key(word), [])
    if isinstance(candidates, str):
        candidates = [candidates]
    accented_candidates = [v for v in candidates if "'" in v or "\u0301" in v or "ё" in v or sum(c in VOWELS for c in key(v)) <= 1]
    if accented_candidates:
        candidates = accented_candidates
    if len(set(candidates)) == 1:
        return _with_stress(candidates[0]), "OpenRussian"
    if sum(c in VOWELS for c in key(word)) <= 1 or "ё" in word:
        return word, "unambiguous"
    # Used only for manually reviewed fixed-stress lemmas, never guessed for
    # mobile-stress nouns such as рука or голова.
    if custom.get("fixed_stress") and custom.get("stress"):
        accented = custom["stress"].lower()
        plain = key(accented)
        index = accented.find("\u0301") - 1
        if index < 0 and sum(c in VOWELS for c in plain) == 1:
            index = next(i for i,c in enumerate(plain) if c in VOWELS)
        if index >= 0 and key(word).startswith(plain[:index+1]):
            return word[:index+1] + "\u0301" + word[index+1:], "reviewed_fixed_stress"
    return word, "unverified_stress"


def arabic_pronunciation(text: str) -> str:
    """Learner-oriented approximation, with stress-aware vowel reduction.

    Arabic cannot encode all Russian phonetic distinctions.  Curated source
    pronunciations always take precedence; this is for newly supplied forms.
    """
    pieces = re.findall(r"[а-яё\u0301]+|[^а-яё\u0301]+", text.casefold())
    result = []
    consonants = {"б":"ب", "в":"ڤ", "г":"گ", "д":"د", "ж":"ژ", "з":"ز", "й":"ي", "к":"ك", "л":"ل", "м":"م", "н":"ن", "п":"پ", "р":"ر", "с":"س", "т":"ت", "ф":"ف", "х":"خ", "ц":"تْس", "ч":"تْش", "ш":"ش", "щ":"شّ"}
    devoiced = {"б":"п", "в":"ф", "г":"к", "д":"т", "ж":"ш", "з":"с"}
    for piece in pieces:
        if not re.fullmatch(r"[а-яё\u0301]+", piece):
            result.append(piece); continue
        letters, stress = [], -1
        for char in piece:
            if char == "\u0301":
                stress = len(letters) - 1
            else:
                letters.append(char)
        if "ё" in letters:
            stress = letters.index("ё")
        if stress < 0 and sum(c in VOWELS for c in letters) == 1:
            stress = next(i for i,c in enumerate(letters) if c in VOWELS)
        output = ""
        for i, char in enumerate(letters):
            previous = letters[i-1] if i else ""
            following = letters[i+1] if i+1 < len(letters) else ""
            if char in consonants:
                sound = devoiced.get(char, char) if not following or following in "кпстфхцчшщ" else char
                if char == "г" and i >= len(letters)-2 and "".join(letters).endswith(("ого", "его")):
                    sound = "в"
                output += consonants.get(sound, char) + "ْ"
            elif char in "ьъ":
                continue
            elif char == "ы":
                output = output.rstrip("ْ") + ("إِي" if not output else "ِي")
            elif char in "аеёэоиуюя":
                initial = i == 0 or previous in VOWELS + "ьъй"
                yot = char in "еёюя" and initial
                if char in "ая":
                    vowel = "ا" if i == stress else "َ"
                    if i == 0:
                        vowel = "آ" if i == stress and not yot else ("أَ" if not yot else vowel)
                elif char == "о":
                    vowel = "ُو" if i == stress or stress < 0 else "َ"
                    if i == 0:
                        vowel = "أُو" if i == stress or stress < 0 else "أَ"
                elif char in "ую":
                    vowel = "ُو" if i == stress else "ُ"
                    if i == 0 and not yot:
                        vowel = "أُو" if i == stress else "أُ"
                elif char == "ё":
                    vowel = "ُو"
                else:
                    vowel = "ِي" if i == stress else "ِ"
                    if i == 0 and not yot:
                        vowel = "إِي" if i == stress else "إِ"
                output = output.rstrip("ْ") + ("ي" if yot else "") + vowel
        result.append(output)
    return "".join(result).strip()


def _form(word: str, entry: dict, field: str, *, label: str = "") -> dict:
    stressed, origin = stressed_form(word, entry, field)
    exact = [s for s in entry["sources"] if key(s["russian"]) == key(word)]
    if not exact:
        exact = [s for s in entry["sources"] if key(s["russian"]).replace("ё", "е") == key(word).replace("ё", "е")]
    if key(stressed) != key(word):
        exact = []
    # Equal spelling is not equal pronunciation: ме́ста (genitive singular)
    # versus места́ (nominative plural), or у́чите versus учи́те.
    variants = reference().get("stress", {}).get(key(word), [])
    if isinstance(variants, str):
        variants = [variants]
    accented_variants = {_with_stress(v).casefold() for v in variants if "'" in v or "\u0301" in v or "ё" in v}
    if field != "lemma" and len(accented_variants) > 1:
        exact = [s for s in exact if ("\u0301" in s["russian"] or "ё" in s["russian"].lower()) and s["russian"].casefold() == stressed.casefold()]
    exact.sort(key=lambda s: not s.get("pronunciation_reviewed", False))
    pronunciation = exact[0].get("pronunciation") if exact else ""
    custom = overrides().get("entries", {}).get(entry["id"], {})
    pronunciation = custom.get("pronunciations", {}).get(field, pronunciation)
    if entry.get("grammar", {}).get("proper_name"):
        stressed = "-".join(part.capitalize() for part in stressed.split("-"))
    return {"russian": stressed, "pronunciation": pronunciation or arabic_pronunciation(stressed), "label": label,
            "origin": origin, "pronunciation_origin": "course" if pronunciation else "stress_based_approximation"}


def _review_usage(entry: dict) -> None:
    """Avoid attaching an entire alias pronunciation to only half an alias."""
    source_by_id = {s["source_id"]: s for s in entry["sources"]}
    for usage in entry["usage"]:
        source = source_by_id.get(usage.get("source_id"))
        if not source or "/" not in source["russian"]:
            continue
        parts = re.split(r"\s*/\s*", source["russian"])
        i = next((i for i, part in enumerate(parts) if key(part) == key(usage["russian"])), None)
        if i is None:
            continue
        for field in ("pronunciation", "arabic", "english"):
            values = re.split(r"\s*/\s*", source[field])
            if len(values) == len(parts):
                usage[field] = values[i]
            elif field == "pronunciation":
                noun = _tokens(usage["russian"])[-1]
                forms = [f for row in entry.get("declension", []) for f in (row.get("sg"), row.get("pl")) if f and key(f["russian"]) == noun]
                stressed = forms[0]["russian"] if forms else noun
                usage[field] = arabic_pronunciation(usage["preposition"] + " " + stressed)
            elif field in ("arabic", "english") and usage["preposition"] in ("в", "во", "на"):
                location = usage.get("case") in ("loct", "loc2")
                usage[field] = (("في " if location else "إلى ") + entry["arabic"]) if field == "arabic" else (("at " if location else "to ") + entry["english"])


def _noun_forms(entry: dict, parse) -> None:
    ref = reference().get("entries", {}).get(entry["id"], {})
    custom = overrides().get("entries", {}).get(entry["id"], {})
    if parse is None:
        # Explicitly reviewed paradigms for modern loans missing from both
        # packaged dictionaries. Never apply a guessed default noun ending.
        grammar = custom.get("manual_grammar")
        if not grammar:
            raise ValueError(f"No attested noun analysis: {entry['id']}")
        entry["grammar"] = dict(grammar)
        rows = []
        for case, label, suffix in zip(CASES, CASE_LABELS, ("nom", "gen", "dat", "acc", "inst", "prep")):
            row = {"case": case, "label": label}
            for prefix, excluded in (("sg", grammar.get("pl_only")), ("pl", grammar.get("sg_only"))):
                field = f"{prefix}_{suffix}"
                word = custom.get("forms", {}).get(field)
                row[prefix] = None if excluded or not word else _form(key(word), entry, field)
                if not excluded and not word:
                    entry["review_flags"].append("missing:"+field)
            rows.append(row)
        entry["declension"] = rows
        return
    name = custom.get("proper_name", bool(set(parse.tag.grammemes) & {"Name", "Surn", "Patr", "Geox", "Orgn", "Trad"}))
    sg_only = custom.get("sg_only", ref.get("sg_only") == "1" or "Sgtm" in parse.tag or name)
    pl_only = custom.get("pl_only", ref.get("pl_only") == "1" or "Pltm" in parse.tag)
    indeclinable = custom.get("indeclinable", ref.get("indeclinable") == "1" or "Fixd" in parse.tag)
    entry["grammar"] = {"gender": custom.get("gender", parse.tag.gender), "animate": custom.get("animate", parse.tag.animacy == "anim"), "indeclinable": indeclinable,
                        "sg_only": bool(sg_only), "pl_only": bool(pl_only), "proper_name": name}
    rows = []
    for case, label in zip(CASES, CASE_LABELS):
        row = {"case": case, "label": label}
        for number, prefix, excluded in (("sing", "sg", pl_only), ("plur", "pl", sg_only)):
            if excluded:
                row[prefix] = None; continue
            ref_case = {"nomn":"nom", "gent":"gen", "datv":"dat", "accs":"acc", "ablt":"inst", "loct":"prep"}[case]
            field = f"{prefix}_{ref_case}"
            explicit = custom.get("forms", {}).get(field)
            if explicit:
                row[prefix] = _form(key(explicit), entry, field)
                continue
            inflected = parse.inflect({case, number})
            if not inflected and indeclinable:
                word = entry["lemma"]
            elif not inflected:
                row[prefix] = None
                entry["review_flags"].append(f"missing:{prefix}_{case}"); continue
            else:
                word = inflected.word
            # Prefer the reference's common variant (стулья, учителя, цветы),
            # but only when the analyzer independently confirms its lemma,
            # number and case. Malformed dictionary cells stay rejected.
            for candidate in re.split(r"[,;/]+", ref.get(f"{prefix}_{ref_case}", "")):
                candidate = key(candidate)
                matches = [p for p in analyzer().parse(candidate) if p.is_known and p.tag.POS == "NOUN" and
                           p.normal_form == parse.normal_form and p.tag.case == case and p.tag.number == number]
                if matches:
                    word = candidate; break
            row[prefix] = _form(word, entry, f"{prefix}_{ref_case}")
        rows.append(row)
    entry["declension"] = rows


def _verb_forms(entry: dict, parse, observed: list) -> None:
    aspect = parse.tag.aspect
    entry["grammar"] = {"aspect": aspect, "reflexive": entry["lemma"].endswith(("ся", "сь"))}
    paradigms = []
    tense_tags = {p.tag.tense for p in observed}
    moods = {p.tag.mood for p in observed}
    custom = overrides().get("entries", {}).get(entry["id"], {})
    ref = reference().get("entries", {}).get(entry["id"], {})
    if aspect == "impf":
        paradigms.append(("المضارع", "pres", "presfut"))
    else:
        entry["notes"].append("فعل تام؛ لا مضارع له. لا نسمّي تصريف مستقبله مضارعًا.")
    if "futr" in tense_tags or custom.get("include_future"):
        paradigms.append(("المستقبل", "futr", "presfut"))
    entry["conjugation"] = []
    for label, tense, ref_prefix in paradigms:
        rows = []
        for i, (pronoun, number, person) in enumerate(PERSONS):
            result = parse.inflect({tense, number, person})
            if result:
                field = f"{ref_prefix}_{'sg' if number == 'sing' else 'pl'}{person[0]}"
                word = result.word
                if not parse.is_known and ref.get(field):
                    # Unknown-lemma prediction produced паркуёшь, while the
                    # attested dictionary has парку́ешь. Prefer the reference.
                    word = key(re.split(r"[,;/]+", ref[field])[0])
                rows.append(_form(word, entry, field, label=pronoun))
            else:
                entry["review_flags"].append(f"missing:{tense}:{person}:{number}")
        if rows:
            entry["conjugation"].append({"label": label, "rows": rows})
    if "past" in tense_tags or custom.get("include_past"):
        rows = []
        for gender, label, ref_field in (("masc", "هو", "past_m"), ("femn", "هي", "past_f"), ("neut", "للمحايد", "past_n"), (None, "نحن / أنتم / هم", "past_pl")):
            result = parse.inflect({"past", gender, "sing"} if gender else {"past", "plur"})
            if result:
                rows.append(_form(result.word, entry, ref_field, label=label))
        entry["conjugation"].append({"label": "الماضي", "rows": rows})
    if "impr" in moods or custom.get("include_imperative"):
        rows = []
        for number, label, field in (("sing", "ты", "imperative_sg"), ("plur", "вы", "imperative_pl")):
            result = parse.inflect({"impr", number, "excl"})
            if result:
                rows.append(_form(result.word, entry, field, label=label))
        if rows:
            entry["conjugation"].append({"label": "الأمر", "rows": rows})


def _source_id(source: dict, index: int) -> str:
    # order is persistent in cumulative data; the digest prevents collisions.
    return f"{source.get('order', index + 1)}:{hashlib.sha256(source.get('russian', '').encode()).hexdigest()[:10]}"


def source_fingerprint(state: dict) -> str:
    payload = {"vocabulary": state.get("vocabulary", []), "version": VERSION,
               "reference": reference().get("revision"), "overrides": overrides()}
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def build_lexicon(state: dict) -> dict:
    groups, observed = {}, defaultdict(list)
    for index, source in enumerate(state.get("vocabulary", [])):
        targets = overrides().get("sources", {}).get(key(source["russian"]), {}).get("targets", [])
        analyses = []
        if targets:
            for target in targets:
                pos, lemma = target.split(":", 1)
                parse = select_parse(lemma, source) if pos in ("NOUN", "INFN") else None
                analyses.append({"id":target, "lemma":lemma, "pos":pos, "parses":[parse] if parse else [], "usage":[]})
        else:
            analyses = [analyse_source(source)]
        record = deepcopy(source)
        record["source_id"] = _source_id(source, index)
        for position, analysis in enumerate(analyses):
            entry_id = analysis["id"]
            if entry_id not in groups:
                groups[entry_id] = {"id": entry_id, "lemma": analysis["lemma"], "pos": analysis["pos"],
                                   "sources": [], "source_refs": [], "related_entries": [], "alias_source_ids": [],
                                   "usage": [], "notes": [], "review_flags": [], "order": source.get("order", index+1)}
            entry = groups[entry_id]
            if position == 0:
                entry["sources"].append(record)
            else:
                entry["source_refs"].append(record["source_id"])
            if targets:
                entry["alias_source_ids"].append(record["source_id"])
                entry["related_entries"].extend(t for t in targets if t != entry_id)
            observed[entry_id].extend(analysis["parses"])
            for usage in analysis["usage"]:
                usage.update({"pronunciation": source["pronunciation"], "arabic": source["arabic"], "english": source["english"], "source_id": record["source_id"]})
                entry["usage"].append(usage)
    entries = []
    for entry_id, entry in groups.items():
        custom = overrides().get("entries", {}).get(entry_id, {})
        ref = reference().get("entries", {}).get(entry_id, {})
        direct = [s for s in entry["sources"] if key(s["russian"]) == key(entry["lemma"])]
        base_sources = direct or entry["sources"]
        entry["arabic"] = custom.get("arabic") or clean_meanings([s.get("arabic", "") for s in base_sources])
        entry["english"] = custom.get("english") or clean_meanings([s.get("english", "") for s in base_sources])
        if not direct and entry["pos"] in ("INFN", "NOUN"):
            if not custom.get("arabic"):
                entry["review_flags"].append("base_meaning_from_inflected_source")
        entry["topic"] = _topic(entry)
        entry["section"] = POS_SECTION.get(entry["pos"], "العبارات والتعبيرات")
        if entry["pos"] in ("NOUN", "INFN"):
            parse = next((p for p in observed[entry_id] if p.tag.POS in ("NOUN", "VERB", "INFN")), observed[entry_id][0] if observed[entry_id] else None)
            if entry["pos"] == "NOUN":
                _noun_forms(entry, parse)
            else:
                _verb_forms(entry, parse, observed[entry_id])
        entry["headword"] = _form(entry["lemma"], entry, "lemma")
        entry["notes"].extend(custom.get("notes", []))
        entry["usage"].extend(custom.get("usage", []))
        _review_usage(entry)
        supplied_forms = [entry["headword"]] + [f for row in entry.get("declension", []) for f in (row.get("sg"), row.get("pl")) if f] + [f for p in entry.get("conjugation", []) for f in p["rows"]]
        if entry["pos"] in ("NOUN", "INFN") and any(f["origin"] == "unverified_stress" and f["pronunciation_origin"] != "course" for f in supplied_forms):
            entry["review_flags"].append("new_pronunciation_needs_stress_review")
        entries.append(entry)
    family_for = {lemma: family for family in FAMILIES for lemma in family}
    first_order = {}
    for entry in entries:
        family = family_for.get(entry["lemma"], (entry["lemma"],))
        group = (entry["section"], entry["topic"], family)
        first_order[group] = min(first_order.get(group, entry["order"]), entry["order"])
    def sort_key(entry):
        family = family_for.get(entry["lemma"], (entry["lemma"],))
        group = (entry["section"], entry["topic"], family)
        return (SECTIONS.index(entry["section"]), TOPICS.index(entry["topic"]), first_order[group], family.index(entry["lemma"]), entry["order"])
    entries.sort(key=sort_key)
    result = {"version": VERSION, "fingerprint": source_fingerprint(state), "entries": entries,
              "source_count": len(state.get("vocabulary", [])), "max_lecture": max((int(k) for k in state.get("lectures", {}) if str(k).isdigit()), default=1),
              "references": reference().get("sources", []), "unresolved": []}
    result["unresolved"] = [{"id": e["id"], "flags": e["review_flags"]} for e in entries if e["review_flags"]]
    validate_lexicon(result)
    return result


def validate_lexicon(lexicon: dict) -> None:
    ids = [s["source_id"] for e in lexicon["entries"] for s in e["sources"]]
    if len(ids) != lexicon["source_count"] or len(ids) != len(set(ids)):
        raise ValueError("Lexicon migration must preserve every original record exactly once")
    entry_ids = [e["id"] for e in lexicon["entries"]]
    if len(entry_ids) != len(set(entry_ids)):
        raise ValueError("Duplicate lexemes in Russian dictionary")
    for entry in lexicon["entries"]:
        if not entry["sources"] and not entry.get("source_refs"):
            raise ValueError("Dictionary must not add unrelated headwords")
        if not set(entry.get("source_refs", [])) <= set(ids):
            raise ValueError("Dangling dictionary source reference")
        if not entry["arabic"] or not entry["english"] or not entry["headword"]["pronunciation"]:
            raise ValueError(f"Missing dictionary fields: {entry['id']}")
        if entry["pos"] == "NOUN" and len(entry["declension"]) != 6:
            raise ValueError(f"Expected six cases: {entry['id']}")
        if entry["pos"] == "INFN" and entry["grammar"]["aspect"] == "perf" and any(p["label"] == "المضارع" for p in entry["conjugation"]):
            raise ValueError(f"Perfective verb incorrectly labelled present: {entry['id']}")


def ensure_ready_for_export(lexicon: dict) -> None:
    """An extraction can be saved while newly generated morphology is reviewed."""
    if lexicon.get("unresolved"):
        words = ", ".join(item["id"].split(":", 1)[-1] for item in lexicon["unresolved"][:12])
        raise ValueError("حُفظت المفردات الأصلية، لكن تصدير القاموس يحتاج تدقيق الصيغ أو المعنى الأساسي للكلمات: " + words)


def save_lexicon(lexicon: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(lexicon, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def get_lexicon(state: dict, output_dir: Path) -> dict:
    path = output_dir / LEXICON_FILENAME
    current = _json(path)
    if current.get("fingerprint") == source_fingerprint(state):
        validate_lexicon(current)
        return current
    result = build_lexicon(state)
    save_lexicon(result, path)
    return result
