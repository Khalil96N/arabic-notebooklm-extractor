"""Page-level PDF geometry audit and full-size page sheets for visual QA."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from PIL import Image, ImageDraw
import pdfplumber
from pypdf import PdfReader
import pypdfium2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("render_dir", type=Path)
    args = parser.parse_args()
    pdf_path = next(args.render_dir.glob("*.pdf"))
    report = {"page_count":0, "blank_pages":[], "out_of_bounds":[], "replacement_glyphs":[], "sparse_pages":[], "visual_sheets":[]}
    with pdfplumber.open(pdf_path) as document:
        report["page_count"] = len(document.pages)
        for i, page in enumerate(document.pages, 1):
            chars = page.chars
            if len(chars) < 10:
                report["blank_pages"].append(i)
            if len(chars) < 180:
                report["sparse_pages"].append(i)
            bad = [c["text"] for c in chars if c["x0"] < 30 or c["x1"] > page.width-30 or c["top"] < 20 or c["bottom"] > page.height-12]
            if bad:
                report["out_of_bounds"].append({"page": i, "characters":"".join(bad)[:200]})
            if any(c["text"] in ("\ufffd", "\u25a1") for c in chars):
                report["replacement_glyphs"].append(i)
    reader = PdfReader(pdf_path)
    outlines = []
    def walk(items):
        for item in items:
            if isinstance(item, list):
                walk(item)
            else:
                outlines.append({"title": str(item.title), "page":reader.get_destination_page_number(item)+1})
    walk(reader.outline)
    report["bookmarks"] = len(outlines)
    report["outline"] = outlines
    # A separate 72-dpi pass yields native 612x792 pages, not resized contact
    # thumbnails. Every page in these sheets is shown at 100% raster scale;
    # the higher-resolution original page PNGs remain available for details.
    pdf = pypdfium2.PdfDocument(pdf_path)
    sheets = args.render_dir / "sheets"
    sheets.mkdir(exist_ok=True)
    for start in range(0, len(pdf), 6):
        pages = [pdf[i].render(scale=1).to_pil().convert("RGB") for i in range(start, min(start+6, len(pdf)))]
        width, height = pages[0].size
        sheet = Image.new("RGB", (width*3+32, (height+22)*2+20), "#d7d7d7")
        draw = ImageDraw.Draw(sheet)
        for j, page in enumerate(pages):
            x, y = 8+j%3*(width+8), 8+j//3*(height+22)+16
            sheet.paste(page, (x,y))
            draw.text((x+4,y-14), f"Page {start+j+1}", fill="black")
            page.close()
        path = sheets / f"pages-{start+1:03d}-{min(start+6,len(pdf)):03d}.png"
        sheet.save(path)
        report["visual_sheets"].append(str(path))
        sheet.close()
    pdf.close()
    path = args.render_dir / "qa_report.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items() if k not in ("outline", "visual_sheets")}, ensure_ascii=False, indent=2))
    print(f"{len(report['visual_sheets'])} native-scale sheets; {path}")


if __name__ == "__main__":
    main()
