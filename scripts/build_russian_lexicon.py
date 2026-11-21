"""Prepare Russian morphology resources and export the cumulative dictionary.

Reference CSVs are explicitly downloaded by the maintainer, not at app runtime.
Only course-relevant lemmas are retained; no audio or large language model.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def prepare_reference(csv_dir: Path, state: dict) -> None:
    import pymorphy3
    from app.services.russian_lexicon import REFERENCE_FILE, key, save_lexicon, overrides
    morph = pymorphy3.MorphAnalyzer()
    lemmas = set()
    for source in state["vocabulary"]:
        for token in re.findall(r"[а-яё]+(?:-[а-яё]+)*", key(source["russian"])):
            lemmas.add(token)
            lemmas.update(p.normal_form for p in morph.parse(token) if p.is_known)
    lemmas.update(k.split(":", 1)[-1] for k in overrides().get("entries", {}))
    entries, stress = {}, {}
    digests = []
    for name, pos in (("nouns", "NOUN"), ("verbs", "INFN"), ("adjectives", "ADJF"), ("others", "OTHER")):
        path = csv_dir / f"{name}.csv"
        digests.append(hashlib.sha256(path.read_bytes()).hexdigest())
        with path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                if key(row["bare"]) not in lemmas:
                    continue
                row = {k:v for k,v in row.items() if k != "translations_de" and v}
                entries[f"{pos}:{key(row['bare'])}"] = row
                for field, value in row.items():
                    if field not in ("accented", "bare") and not field.startswith(("sg_", "pl_", "past_", "presfut_", "imperative_", "decl_", "short_")):
                        continue
                    for form in re.split(r"[,;/]+", value):
                        if re.fullmatch(r"[а-яё'\u0301-]+", form.strip()):
                            form = form.strip()
                            target = stress.setdefault(key(form), [])
                            if form not in target:
                                target.append(form)
    payload = {"revision": hashlib.sha256("".join(digests).encode()).hexdigest(),
               "sources": [{"name":"OpenRussian", "url":"https://en.openrussian.org/dictionary-data", "license":"CC BY-SA 4.0", "repository":"https://github.com/Badestrand/russian-dictionary"},
                           {"name":"OpenCorpora via pymorphy3", "url":"https://opencorpora.org/", "license":"CC BY-SA 3.0"},
                           {"name":"Gramota", "url":"https://gramota.ru/", "license":"مرجع تدقيق لغوي"},
                           {"name":"Wiktionary Russian inflections", "url":"https://ru.wiktionary.org/", "license":"CC BY-SA 4.0"}],
               "entries": entries, "stress": stress}
    save_lexicon(payload, REFERENCE_FILE)
    print(f"Reference subset: {len(entries)} lemmas, {len(stress)} forms, {REFERENCE_FILE.stat().st_size:,} bytes")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "output")
    parser.add_argument("--reference-csv-dir", type=Path)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--render-only", action="store_true")
    parser.add_argument("--sample", action="store_true")
    parser.add_argument("--layout", choices=("study", "compact", "expanded"), default="study")
    parser.add_argument("--rebuild", action="store_true")
    args = parser.parse_args()
    state = json.loads((args.output_dir / ".russian_course_cumulative.json").read_text(encoding="utf-8"))
    if args.reference_csv_dir:
        prepare_reference(args.reference_csv_dir, state)
    from app.services.russian_lexicon import LEXICON_FILENAME, get_lexicon
    if args.render_only:
        lexicon = json.loads((args.output_dir / LEXICON_FILENAME).read_text(encoding="utf-8"))
    elif args.rebuild:
        from app.services.russian_lexicon import build_lexicon, save_lexicon
        lexicon = build_lexicon(state)
        save_lexicon(lexicon, args.output_dir / LEXICON_FILENAME)
    else:
        lexicon = get_lexicon(state, args.output_dir)
    print(f"{lexicon['source_count']} original records -> {len(lexicon['entries'])} lexemes and expressions")
    print(f"Review flags: {len(lexicon['unresolved'])}")
    for item in lexicon["unresolved"]:
        print(item)
    if not args.prepare_only:
        from app.exporters.russian_lexicon import save_dictionary_document
        if args.sample:
            wanted = {"INFN:читать", "INFN:работать", "INFN:писать", "INFN:дать", "NOUN:школа", "NOUN:книга", "NOUN:группа", "NOUN:кофе", "NOUN:ребёнок", "NOUN:стол", "NOUN:окно", "NOUN:диктант"}
            lexicon = dict(lexicon, entries=[e for e in lexicon["entries"] if e["id"] in wanted])
        path = save_dictionary_document(lexicon, args.output_dir, sample=args.sample,
                                        expanded=args.layout == "expanded",
                                        layout="study" if args.layout == "study" else "compact")
        print(path)


if __name__ == "__main__":
    main()
