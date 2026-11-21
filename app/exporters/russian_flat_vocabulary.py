"""The original six-column Word table, using its retained OOXML components."""
from __future__ import annotations
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile
from lxml import etree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
WIDTHS = (600, 3742, 2100, 3345, 3005, 1688)


def _set_text(container, text):
    p = container if container.tag == W + "p" else container.find(W + "p")
    sample = next((r for r in p.findall(W + "r") if r.find(W + "rPr") is not None), None)
    properties = deepcopy(sample.find(W + "rPr")) if sample is not None else None
    for child in list(p):
        if child.tag != W + "pPr":
            p.remove(child)
    r = ET.SubElement(p, W + "r")
    if properties is not None:
        r.append(properties)
    t = ET.SubElement(r, W + "t")
    t.text = str(text)


def lecture_label(row):
    numbers = sorted(set(row.get("lectures", [])))
    ranges, start, last = [], None, None
    for n in numbers + [None]:
        if start is not None and (n is None or n != last + 1):
            ranges.append(str(start) if start == last else f"{start}-{last}")
            start = None
        if n is not None:
            if start is None:
                start = n
            last = n
    values = [", ".join(ranges)] if ranges else []
    values += row.get("legacy_sources", [])
    return " + ".join(dict.fromkeys(v for v in values if v))


def save_flat_document(review, max_lecture, output_dir, reference):
    """Patch document.xml only; preserve other template parts byte-for-byte."""
    output_dir, reference = Path(output_dir), Path(reference)
    path = output_dir / f"جدول مفردات اللغة الروسية - المحاضرات 1-{max_lecture} - مراجعة.docx"
    if path.resolve() == reference.resolve():
        raise ValueError("The retained reference must not be overwritten")
    with ZipFile(reference) as archive:
        parts = {p.filename: archive.read(p.filename) for p in archive.infolist()}
        infos = archive.infolist()
    before = {name:hashlib.sha256(data).hexdigest() for name,data in parts.items()}
    root = ET.fromstring(parts["word/document.xml"])
    body = root.find(W + "body")
    paragraphs = body.findall(W + "p")
    _set_text(paragraphs[0], f"جدول مفردات اللغة الروسية المحاضرات 1 إلى {max_lecture}")
    ppr = paragraphs[0].find(W + "pPr")
    style = ppr.find(W + "pStyle")
    if style is None:
        style = ET.SubElement(ppr, W + "pStyle")
    style.set(W + "val", "Title")
    _set_text(paragraphs[1], "كلمات وعبارات مرتبة حسب الموضوع، مع اللفظ التقريبي والمعنى بالعربية والإنجليزية وأرقام المحاضرات. بجانب الاسم المنتهي بـ Ь: (он) مذكر، و(она) مؤنث. «الجدول القديم» يشير إلى المصدر السابق ذي الترقيم المختلف.")
    table = body.find(W + "tbl")
    rows = table.findall(W + "tr")
    # Category order comes from the retained table, without importing app-only
    # dependencies into the bundled document runtime.
    categories = ["".join(t.text or "" for t in r.iter(W + "t")) for r in rows if len(r.findall(W + "tc")) == 1]
    header, category_template, row_template = [deepcopy(r) for r in rows[:3]]
    for r in rows:
        table.remove(r)
    grid = table.find(W + "tblGrid")
    for child, width in zip(grid, WIDTHS):
        child.set(W + "w", str(width))
    tbl_width = table.find(W + "tblPr/" + W + "tblW")
    tbl_width.set(W + "type", "dxa")
    tbl_width.set(W + "w", str(sum(WIDTHS)))

    def size_cells(row):
        cells = row.findall(W + "tc")
        for index, cell in enumerate(cells):
            cell.find(W + "tcPr/" + W + "tcW").set(W + "w", str(WIDTHS[index] if len(cells) == 6 else sum(WIDTHS)))
            if index == 0 and len(cells) == 6:
                for side in ("left", "right"):
                    margin = cell.find(W + "tcPr/" + W + "tcMar/" + W + side)
                    if margin is not None:
                        margin.set(W + "w", "65")

    size_cells(header)
    table.append(header)
    rank = {c:i for i,c in enumerate(categories)}
    ordered = sorted(review["vocabulary"], key=lambda r:(rank.get(r.get("category", "أخرى"),999), r.get("order",0)))
    current = None
    for serial, record in enumerate(ordered, 1):
        category = record.get("category", "أخرى")
        if category != current:
            row = deepcopy(category_template)
            size_cells(row)
            _set_text(row.find(W + "tc"), category)
            table.append(row)
            current = category
        row = deepcopy(row_template)
        size_cells(row)
        values = [serial, record["display_russian"], record["pronunciation"], record["arabic"], record["english"], lecture_label(record)]
        for cell, value in zip(row.findall(W + "tc"), values):
            _set_text(cell, value)
            tcpr = cell.find(W + "tcPr")
            shading = tcpr.find(W + "shd")
            if shading is None:
                shading = ET.SubElement(tcpr, W + "shd")
            shading.set(W + "fill", "F5F9FC" if serial % 2 == 0 else "FFFFFF")
        table.append(row)
    parts["word/document.xml"] = ET.tostring(root, encoding="UTF-8", xml_declaration=True, standalone=True)
    settings = ET.fromstring(parts["word/settings.xml"])
    update = settings.find(W + "updateFields")
    if update is None:
        update = ET.SubElement(settings, W + "updateFields")
    update.set(W + "val", "true")
    parts["word/settings.xml"] = ET.tostring(settings, encoding="UTF-8", xml_declaration=True, standalone=True)
    temporary = path.with_suffix(".tmp")
    with ZipFile(temporary, "w") as archive:
        for info in infos:
            archive.writestr(info, parts[info.filename])
    temporary.replace(path)
    changed = [n for n in parts if hashlib.sha256(parts[n]).hexdigest() != before[n]]
    if set(changed) - {"word/document.xml", "word/settings.xml"}:
        raise ValueError("Unexpected template package modification")
    audit = {"reference":str(reference), "reference_sha256":hashlib.sha256(reference.read_bytes()).hexdigest(),
             "preserve_only_parts":{n:h for n,h in before.items() if n not in changed}, "edited_parts":changed,
             "source_count":review["source_count"], "row_count":review["row_count"], "merged_rows":review["merged_rows"],
             "gender_rows":sum(r["display_russian"] != r["russian"] for r in review["vocabulary"])}
    (output_dir / ".russian_flat_template_audit.json").write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding="utf-8")
    return path
