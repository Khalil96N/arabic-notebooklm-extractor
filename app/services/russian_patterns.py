"""Lossless display grouping of already reviewed Russian paradigms.

The morphology cache stays complete. Only Word presentation is compressed.
Shared endings alone are insufficient: stress, stem alternation, animacy,
number restrictions and every displayed tense must also agree.
"""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
import re
import unicodedata

from app.services.russian_lexicon import key

VOWELS = set("аеёиоуыэюя")
WORD = re.compile(r"[А-Яа-яЁё\u0301]+")


def _common_prefix(words):
    result = words[0]
    for word in words[1:]:
        n = 0
        while n < min(len(result), len(word)) and result[n] == word[n]:
            n += 1
        result = result[:n]
    return result


def _stress(word):
    word = unicodedata.normalize("NFC", word.casefold())
    plain, stresses = [], []
    for char in word:
        if char == "\u0301":
            stresses.append(len(plain)-1)
        elif char == "ё":
            stresses.append(len(plain))
            plain.append(char)
        else:
            plain.append(char)
    if len(stresses) == 1:
        return stresses[0]
    vowels = [i for i,c in enumerate(plain) if c in VOWELS]
    return vowels[0] if len(vowels) == 1 else None


def paradigm_shape(entry):
    """Return a reproducible ending/stress map and the replaceable stem.

    Ambiguous multi-variant cells deliberately get a private shape. Analytic
    futures retain their auxiliary and replace only the lexical verb token.
    """
    slots = [("lemma", entry["headword"]["russian"])]
    if entry["pos"] == "NOUN":
        for row in entry.get("declension", []):
            for number in ("sg", "pl"):
                value = row.get(number)
                slots.append((number+":"+row["case"], value["russian"] if value else None))
    elif entry["pos"] == "INFN":
        if not entry.get("conjugation"):
            return None
        for paradigm in entry.get("conjugation", []):
            for i, row in enumerate(paradigm["rows"]):
                slots.append((paradigm["label"]+":"+str(i), row["russian"]))
    else:
        return None
    lemma = key(entry["lemma"])
    lexical = []
    for slot, text in slots:
        if text is None:
            lexical.append((slot, None, "", "")); continue
        if "/" in text or "-" in text:
            return None
        matches = list(WORD.finditer(text))
        if not matches:
            return None
        match = max(matches, key=lambda m: len(_common_prefix([lemma, key(m.group())])))
        before, after = key(text[:match.start()]), key(text[match.end():])
        lexical.append((slot, match.group(), before, after))
    stem = _common_prefix([key(word) for _,word,_,_ in lexical if word])
    if not stem:
        return None
    inside = {_stress(word) for _,word,_,_ in lexical if word and _stress(word) is not None and _stress(word) < len(stem)}
    fixed_stem_stress = len(inside) <= 1
    shape = {}
    for slot, word, before, after in lexical:
        if word is None:
            shape[slot] = None; continue
        stress = _stress(word)
        if stress is None:
            return None
        if stress < len(stem):
            stress_code = "stem" if fixed_stem_stress else ("stem", stress-len(stem))
        else:
            stress_code = ("ending", stress-len(stem))
        shape[slot] = (before, key(word)[len(stem):], after, stress_code)
    grammar = entry.get("grammar", {})
    if entry["pos"] == "NOUN":
        features = tuple(grammar.get(k) for k in ("gender", "animate", "indeclinable", "sg_only", "pl_only"))
    else:
        features = tuple(grammar.get(k) for k in ("aspect", "reflexive"))
    return {"stem":stem, "features":features, "slots":shape}


def pattern_groups(entries):
    """Every entry occurs exactly once, under a compatible complete model.

    A verb with fewer attested tenses may follow a fuller model, but a member
    with a different or additional paradigm can never be silently absorbed.
    """
    shapes = {entry["id"]:paradigm_shape(entry) for entry in entries}
    remaining = list(entries)
    groups = []
    while remaining:
        seed = remaining[0]
        shape = shapes[seed["id"]]
        if not shape:
            groups.append({"model":seed, "members":[], "stem":None})
            remaining.pop(0); continue
        core_names = [name for name in shape["slots"] if name == "lemma"]
        if seed["pos"] == "INFN" and seed.get("conjugation"):
            label = seed["conjugation"][0]["label"]+":"
            core_names += [name for name in shape["slots"] if name.startswith(label)]
        else:
            core_names = list(shape["slots"])
        candidates = []
        for entry in remaining:
            other = shapes[entry["id"]]
            if seed["pos"] == "INFN" and (not entry.get("conjugation") or entry["conjugation"][0]["label"] != seed["conjugation"][0]["label"]):
                continue
            if other and other["features"] == shape["features"] and all(other["slots"].get(name) == shape["slots"][name] for name in core_names):
                candidates.append(entry)
        models = [e for e in candidates if all(name in shapes[e["id"]]["slots"] and shapes[e["id"]]["slots"][name] == value for name,value in shape["slots"].items())]
        model = max(models, key=lambda e:len(shapes[e["id"]]["slots"]))
        model_shape = shapes[model["id"]]
        compatible = []
        for entry in candidates:
            other = shapes[entry["id"]]
            if all(name in model_shape["slots"] and model_shape["slots"][name] == value for name,value in other["slots"].items()):
                compatible.append(entry)
        ids = {entry["id"] for entry in compatible}
        assert seed["id"] in ids
        groups.append({"model":model, "members":[e for e in compatible if e["id"] != model["id"]], "stem":model_shape["stem"]})
        remaining = [entry for entry in remaining if entry["id"] not in ids]
    assert sum(1+len(g["members"]) for g in groups) == len(entries)
    return groups


def verb_pattern_groups(entries):
    """Share each tense/mood model independently, never infer another tense.

    For example, читать and работать share the present model even though only
    работать has an attested past paradigm. Give the past its own model once,
    rather than printing работать's present table a second time.
    """
    groups = []
    for label in ("المضارع", "الماضي", "المستقبل", "الأمر"):
        views = []
        for entry in entries:
            paradigms = [p for p in entry.get("conjugation", []) if p["label"] == label]
            if paradigms:
                view = deepcopy(entry)
                view["conjugation"] = paradigms
                views.append(view)
        for group in pattern_groups(views):
            groups.append(dict(group, label=label))
    for entry in entries:
        if not entry.get("conjugation"):
            groups.append({"model":entry, "members":[], "stem":None, "label":"المصدر"})
    return groups
