"""Build a reviewed copy of the retained simple vocabulary table."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.services.russian_flat_vocabulary import review_vocabulary
from app.exporters.russian_flat_vocabulary import save_flat_document


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "output")
    args = parser.parse_args()
    source = args.output_dir / ".russian_course_cumulative.json"
    raw = source.read_bytes()
    state = json.loads(raw)
    maximum = max(int(n) for n in state["lectures"])
    reference = args.output_dir / f"جدول مفردات اللغة الروسية - المحاضرات 1-{maximum}.docx"
    review = review_vocabulary(state["vocabulary"])
    review["raw_sha256"] = hashlib.sha256(raw).hexdigest()
    # Every untouched source is retained internally, even when rows merge.
    review["original_records"] = state["vocabulary"]
    path = save_flat_document(review, maximum, args.output_dir, reference)
    (args.output_dir / ".russian_flat_vocabulary.json").write_text(json.dumps(review,ensure_ascii=False,indent=2),encoding="utf-8")
    assert source.read_bytes() == raw
    print(json.dumps({"path":str(path), "raw_records":review["source_count"], "rows":review["row_count"],
                      "merged_rows":review["merged_rows"], "field_edits":len(review["changes"])},ensure_ascii=False))


if __name__ == "__main__":
    main()
