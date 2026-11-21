"""Audit a prepared Russian lexicon against every original cumulative record."""
from __future__ import annotations
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.services.russian_lexicon import key, validate_lexicon, ensure_ready_for_export


def visible_forms(entry):
    yield entry["headword"]["russian"]
    for row in entry.get("declension", []):
        for field in ("sg", "pl"):
            if row.get(field):
                yield row[field]["russian"]
    for paradigm in entry.get("conjugation", []):
        for row in paradigm["rows"]:
            yield row["russian"]
    for usage in entry.get("usage", []):
        yield usage["russian"]
    if entry["pos"] not in ("NOUN", "INFN"):
        for source in entry["sources"]:
            if source["source_id"] not in entry.get("alias_source_ids", []):
                yield source["russian"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "output")
    args = parser.parse_args()
    raw = json.loads((args.output_dir / ".russian_course_cumulative.json").read_text(encoding="utf-8"))
    lexicon = json.loads((args.output_dir / ".russian_lexicon.json").read_text(encoding="utf-8"))
    validate_lexicon(lexicon)
    ensure_ready_for_export(lexicon)
    originals = Counter(json.dumps(s, ensure_ascii=False, sort_keys=True) for s in raw["vocabulary"])
    preserved = Counter(json.dumps({k:v for k,v in s.items() if k != "source_id"}, ensure_ascii=False, sort_keys=True) for e in lexicon["entries"] for s in e["sources"])
    assert originals == preserved, "Original records changed or lost"
    absent = []
    by_id = {e["id"]:e for e in lexicon["entries"]}
    for entry in lexicon["entries"]:
        forms = {key(part).replace("ё", "е").strip(".!?؟…") for form in visible_forms(entry) for part in re.split(r"\s*/\s*", form)}
        for related in entry.get("related_entries", []):
            forms.update(key(part).replace("ё", "е").strip(".!?؟…") for form in visible_forms(by_id[related]) for part in re.split(r"\s*/\s*", form))
        for source in entry["sources"]:
            for part in re.split(r"\s*/\s*", source["russian"]):
                if key(part).replace("ё", "е").strip(".!?؟…") not in forms:
                    absent.append({"id": entry["id"], "source": source["russian"], "not_displayed": part})
    report = {"source_records": len(raw["vocabulary"]), "dictionary_entries": len(lexicon["entries"]),
              "unchanged_source_records": sum(preserved.values()), "sections": dict(Counter(e["section"] for e in lexicon["entries"])),
              "noun_entries": sum(e["pos"] == "NOUN" for e in lexicon["entries"]),
              "verb_entries": sum(e["pos"] == "INFN" for e in lexicon["entries"]), "missing_visible_forms": absent,
              "unresolved": lexicon["unresolved"]}
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
