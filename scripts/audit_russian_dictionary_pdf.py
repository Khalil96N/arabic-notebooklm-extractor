"""Verify that prepared conjugation/declension forms survive PDF rendering.

Uses drawing-order text extraction, not visual-column reordering, since accents
can otherwise cause a PDF extractor to rotate the letters of a Cyrillic word.
"""
import argparse
import json
from pathlib import Path
import re
import sys
from pypdf import PdfReader

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.russian_patterns import pattern_groups, verb_pattern_groups


def canonical(text):
    return re.sub("[^А-Яа-яЁё]", "", text).lower().replace("ё", "е")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("lexicon", type=Path)
    layout = parser.add_mutually_exclusive_group()
    layout.add_argument("--compact", action="store_true", help="Check the shared model forms and all headwords, not hidden member paradigms")
    layout.add_argument("--study", action="store_true", help="Check study entries, reference models, and printed exceptions")
    args = parser.parse_args()
    reader = PdfReader(args.pdf)
    parts = []
    for i, page in enumerate(reader.pages, 1):
        parts.append(canonical(page.extract_text()))
        if i % 50 == 0:
            print(f"Read {i}/{len(reader.pages)} rendered pages", flush=True)
    rendered = "".join(parts)
    data = json.loads(args.lexicon.read_text(encoding="utf-8"))
    missing = []
    checked = 0
    models = []
    study_exceptions = []
    if args.study:
        from app.services.russian_study import build_study_index, displayed_exceptions
        study = build_study_index(data)
        models = [model["entry"] for model in study["models"]]
        study_exceptions = [(entry, [item["form"] for item in displayed_exceptions(study["bindings"][entry["id"]])]) for entry in data["entries"]]
    if args.compact:
        models += [g["model"] for g in pattern_groups([e for e in data["entries"] if e["pos"] == "NOUN"])]
        models += [g["model"] for g in verb_pattern_groups([e for e in data["entries"] if e["pos"] == "INFN"])]
    abbreviated = args.compact or args.study
    targets = [(e, [e["headword"]]) for e in data["entries"]] if abbreviated else []
    targets += study_exceptions
    for entry in models if abbreviated else data["entries"]:
        targets.append((entry, [entry["headword"]] + [f for row in entry.get("declension", []) for f in (row.get("sg"),row.get("pl")) if f] + [f for paradigm in entry.get("conjugation", []) for f in paradigm["rows"]]))
    if abbreviated:
        for entry in data["entries"]:
            forms = list(entry.get("usage", []))
            if entry["pos"] not in ("NOUN", "INFN"):
                forms += [s for s in entry["sources"] if s["source_id"] not in entry.get("alias_source_ids", [])]
            targets.append((entry, forms))
    for entry, forms in targets:
        for form in forms:
            for variant in form["russian"].split(" / "):
                text = canonical(variant)
                checked += 1
                if text and text not in rendered:
                    missing.append({"id":entry["id"], "russian":variant})
    result = {"checked_forms": checked, "missing_rendered_forms":missing}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if missing:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
