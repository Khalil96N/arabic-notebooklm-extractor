"""A reversible presentation index over the complete reviewed lexicon.

No morphology is guessed here. A reference model predicts a member's forms;
every difference (including stress) is retained as an explicit exception.
The source lexicon is never modified.
"""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy

from app.services.russian_lexicon import key
from app.services.russian_patterns import paradigm_shape, _stress

TENSES = ("المضارع", "الماضي", "المستقبل", "الأمر")


def unit_forms(entry):
    if entry["pos"] == "NOUN":
        return {number + ":" + row["case"]: row.get(number)
                for row in entry.get("declension", []) for number in ("sg", "pl")}
    return {paradigm["label"] + ":" + str(i): form
            for paradigm in entry.get("conjugation", [])
            for i, form in enumerate(paradigm["rows"])}


def _same(left, right):
    if left is None or right is None:
        return left is right
    # Monosyllables may be printed with or without an accent; ё is stressed.
    return key(left) == key(right) and _stress(left) == _stress(right)


def _accent(word, position):
    if position is None or position < 0 or position >= len(word):
        return None
    if word[position] not in "аеёиоуыэюя":
        return None
    return word if word[position] == "ё" else word[:position + 1] + "\u0301" + word[position + 1:]


def predict_form(model_shape, member, slot, *, member_shape=None, stress_rule=None):
    """Apply a model suffix/stress to the member's *reviewed* replaceable stem."""
    own = member_shape if member_shape is not None else paradigm_shape(member)
    if own is None or model_shape is None:
        return None
    rule = model_shape["slots"].get(slot)
    if rule is None:
        return None
    before, suffix, after, stress = rule
    stem = own["stem"]
    if stress_rule == "النبر على أول حركة من النهاية":
        first = next((i for i, char in enumerate(suffix) if char in "аеёиоуыэюя"), None)
        if first is None:
            return None
        position = len(stem) + first
    elif stress == "stem" or stress_rule == "النبر ثابت كما في الكلمة الأساسية":
        position = _stress(member["headword"]["russian"])
        if position is None or position >= len(stem):
            return None
    elif stress[0] == "stem":
        position = len(stem) + stress[1]
    else:
        position = len(stem) + stress[1]
    word = _accent(stem + suffix, position)
    return " ".join(part for part in (before, word, after) if part) if word is not None else None


def _family(entry, label, shape):
    if shape is None:
        return (entry["id"], label)
    grammar = entry.get("grammar", {})
    # A shared infinitive ending alone is never a conjugation classification.
    # The comparison below also checks every attested tense/mood slot.
    features = ((grammar.get("gender"), grammar.get("animate"))
                if entry["pos"] == "NOUN" else
                (grammar.get("aspect"), grammar.get("reflexive")))
    lemma_rule = shape["slots"]["lemma"]
    return (entry["pos"], label, features, lemma_rule[:3])


def _distance(model, member):
    """Count differing ending slots, separately from stress-only exceptions."""
    if model["shape"] is None or member["shape"] is None:
        return 0 if model["entry"]["id"] == member["entry"]["id"] else 1000
    changes = set()
    for slot, form in member["forms"].items():
        if form is None:
            continue  # The word's number restriction is printed in its entry.
        left = model["shape"]["slots"].get(slot)
        right = member["shape"]["slots"].get(slot)
        if left is None or right is None or left[:3] != right[:3]:
            changes.add((left[:3] if left else None, right[:3] if right else None))
    return len(changes)


def _exceptions(model, member):
    result = []
    for slot, form in member["forms"].items():
        if form is None:
            continue
        predicted = predict_form(model["shape"], member["entry"], slot, member_shape=member["shape"])
        if not _same(predicted, form["russian"]):
            left = model["shape"]["slots"].get(slot) if model["shape"] else None
            right = member["shape"]["slots"].get(slot) if member["shape"] else None
            same_ending = left is not None and right is not None and left[:3] == right[:3]
            stress_only = same_ending or (predicted is not None and key(predicted) == key(form["russian"]))
            result.append({"slot": slot, "form": deepcopy(form), "stress_only": stress_only,
                           "stress_rule": _stress_rule(member, slot) if stress_only else None})
    return result


def _stress_rule(member, slot):
    """Human-readable stress rules only when their literal meaning is exact."""
    shape = member["shape"]
    if not shape:
        return None
    rule = shape["slots"][slot]
    stress = rule[3]
    if stress == "stem":
        head_stress = _stress(member["entry"]["headword"]["russian"])
        actual_stress = _stress(member["forms"][slot]["russian"])
        if head_stress is not None and head_stress < len(shape["stem"]) and head_stress == actual_stress:
            return "النبر ثابت كما في الكلمة الأساسية"
        return None
    lemma_suffix = shape["slots"]["lemma"][1]
    if stress[0] != "ending" or lemma_suffix not in ("", "а", "я", "о", "е", "ё", "ь", "й", "ть", "ти", "чь"):
        return None
    vowels = [i for i, char in enumerate(rule[1]) if char in "аеёиоуыэюя"]
    if stress[1] in vowels and vowels.index(stress[1]) == 0:
        return "النبر على أول حركة من النهاية"
    return None


def _exception_cost(model, member):
    if model["shape"] is None or member["shape"] is None:
        return 0
    return sum(model["shape"]["slots"].get(slot) != member["shape"]["slots"].get(slot)
               for slot, form in member["forms"].items() if form is not None)


def build_study_index(lexicon):
    """Return full models plus per-word links/exceptions, with exact coverage.

    At most two different endings may be stated beside a word. More substantial
    structural differences get their own model; stress alone never forces one.
    Indeclinables require a label, not a twelve-cell repeated-word table.
    """
    families = defaultdict(list)
    bindings = {e["id"]: [] for e in lexicon["entries"]}
    for entry in lexicon["entries"]:
        if entry["pos"] == "NOUN":
            if entry.get("grammar", {}).get("indeclinable"):
                continue
            views = [("الأسماء", entry)]
        elif entry["pos"] == "INFN":
            views = []
            for label in TENSES:
                paradigms = [p for p in entry.get("conjugation", []) if p["label"] == label]
                if paradigms:
                    view = dict(entry, conjugation=paradigms)
                    views.append((label, view))
        else:
            continue
        for label, view in views:
            shape = paradigm_shape(view)
            unit = {"entry": view, "shape": shape, "forms": unit_forms(view), "label": label}
            families[_family(view, label, shape)].append(unit)

    models = []
    noun_number = verb_number = 0
    for family in families.values():
        remaining = list(family)
        while remaining:
            # Prefer the model covering most words, then fewer printed stress
            # exceptions; original order is the deterministic final tie-break.
            candidates = []
            for model in remaining:
                covered = [member for member in remaining if _distance(model, member) <= 2]
                cost = sum(_exception_cost(model, member) for member in covered)
                candidates.append((len(covered), -cost, model, covered))
            _, _, model, covered = max(candidates, key=lambda value: value[:2])
            noun = model["entry"]["pos"] == "NOUN"
            if noun:
                noun_number += 1; code = f"اسم {noun_number}"
            else:
                verb_number += 1; code = f"فعل {verb_number}"
            record = {"code": code, "anchor": f"study_model_{len(models)+1}",
                      "entry": model["entry"], "shape": model["shape"],
                      "label": model["label"], "members": []}
            for member in covered:
                own_model = member["entry"]["id"] == model["entry"]["id"]
                exceptions = [] if own_model else _exceptions(model, member)
                binding = {"code": code, "anchor": record["anchor"], "label": record["label"],
                           "model_id": model["entry"]["id"], "exceptions": exceptions}
                bindings[member["entry"]["id"]].append(binding)
                record["members"].append(member["entry"]["id"])
            models.append(record)
            covered_ids = {m["entry"]["id"] for m in covered}
            remaining = [m for m in remaining if m["entry"]["id"] not in covered_ids]
    index = {"models": models, "bindings": bindings}
    validate_study_index(lexicon, index)
    return index


def validate_study_index(lexicon, index):
    """Reconstruct every complete reviewed form from model plus exceptions."""
    models = {model["code"]: model for model in index["models"]}
    assert set(index["bindings"]) == {entry["id"] for entry in lexicon["entries"]}
    checked = 0
    for entry in lexicon["entries"]:
        original = unit_forms(entry)
        if entry["pos"] == "NOUN" and entry.get("grammar", {}).get("indeclinable"):
            assert all(form is None or _same(form["russian"], entry["headword"]["russian"])
                       for form in original.values()), entry["id"]
        seen = set()
        for binding in index["bindings"][entry["id"]]:
            model = models[binding["code"]]
            assert entry["id"] in model["members"]
            overrides = {value["slot"]: value for value in binding["exceptions"]}
            view = entry if entry["pos"] == "NOUN" else dict(entry, conjugation=[p for p in entry["conjugation"] if p["label"] == binding["label"]])
            own_shape = paradigm_shape(view)
            for slot, form in unit_forms(view).items():
                if form is None:
                    continue
                if entry["id"] == model["entry"]["id"]:
                    actual = unit_forms(model["entry"])[slot]["russian"]
                else:
                    exception = overrides.get(slot)
                    if exception and not exception.get("stress_rule"):
                        actual = exception["form"]["russian"]
                    else:
                        actual = predict_form(model["shape"], view, slot, member_shape=own_shape,
                                              stress_rule=exception.get("stress_rule") if exception else None)
                assert _same(actual, form["russian"]), (entry["id"], slot, actual, form["russian"])
                seen.add(slot); checked += 1
        if entry["pos"] in ("NOUN", "INFN") and not entry.get("grammar", {}).get("indeclinable"):
            assert seen == {slot for slot, form in original.items() if form is not None}, entry["id"]
    return checked


def displayed_exceptions(bindings):
    """Identical exception forms are shown once, with all applicable slots."""
    grouped = {}
    for binding in bindings:
        for exception in binding["exceptions"]:
            if exception.get("stress_rule"):
                continue
            form = exception["form"]
            identity = (form["russian"], form["pronunciation"])
            if identity not in grouped:
                grouped[identity] = {"form": form, "slots": [], "stress_only": True}
            target = grouped[identity]
            target["slots"].append(exception["slot"])
            target["stress_only"] &= exception["stress_only"]
    return list(grouped.values())


def displayed_stress_notes(bindings):
    grouped = defaultdict(list)
    for binding in bindings:
        for exception in binding["exceptions"]:
            if exception.get("stress_rule"):
                grouped[exception["stress_rule"]].append(exception["slot"])
    return [{"rule": rule, "slots": slots} for rule, slots in grouped.items()]
