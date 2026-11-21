"""Synchronize noun grammar labels without reflowing unaffected dictionary text."""
import argparse
import importlib.util
import json
from pathlib import Path
from zipfile import ZipFile
from docx import Document
from docx.text.paragraph import Paragraph


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("document", type=Path)
    p.add_argument("lexicon", type=Path)
    p.add_argument("--render-page", type=int)
    p.add_argument("--renderer", type=Path)
    p.add_argument("--qa-dir", type=Path)
    args = p.parse_args()
    entries = json.loads(args.lexicon.read_text(encoding="utf-8"))["entries"]
    doc = Document(args.document)
    headings = [p for p in doc.paragraphs if p.style.name == "Heading 3"]
    assert len(headings) == len(entries)
    changed = []
    for heading, entry in zip(headings, entries):
        assert heading.text.startswith(entry["headword"]["russian"])
        if entry["pos"] != "NOUN":
            continue
        grammar = entry["grammar"]
        gender = {"masc":"مذكر", "femn":"مؤنث", "neut":"محايد", "ms-f":"مشترك الجنس"}.get(grammar.get("gender"), "")
        label = "اسم " + gender
        if grammar.get("animate"):
            label += "، عاقل نحويًا"
        if grammar.get("indeclinable"):
            label += "، غير متصرف"
        if grammar.get("sg_only"):
            label += "، المفرد فقط بهذا الاستعمال"
        if grammar.get("pl_only"):
            label += "، يستعمل بصيغة الجمع"
        paragraph = Paragraph(heading._p.getnext().getnext(), doc._body)
        assert paragraph.text.startswith("اسم ") and len(paragraph.runs) == 1
        if paragraph.text != label:
            changed.append((entry["id"], paragraph.text, label))
            paragraph.runs[0].text = label
    if changed:
        temporary = args.document.with_name(args.document.stem + ".sync.docx")
        doc.save(temporary)
        with ZipFile(args.document) as old, ZipFile(temporary) as new:
            different = [n for n in old.namelist() if old.read(n) != new.read(n)]
            assert different == ["word/document.xml"], different
        temporary.replace(args.document)
    print("Updated labels:", changed, flush=True)
    if args.render_page:
        spec = importlib.util.spec_from_file_location("docx_renderer", args.renderer)
        renderer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(renderer)
        original = renderer.convert_from_path
        def one_page(*a, **kw):
            kw.update(first_page=args.render_page, last_page=args.render_page)
            return original(*a, **kw)
        renderer.convert_from_path = one_page
        renderer.rasterize(str(args.document.resolve()), str(args.qa_dir.resolve()), 110, verbose=False, emit_pdf=True)
        print("Re-rendered changed page", args.render_page, flush=True)


if __name__ == "__main__":
    main()
