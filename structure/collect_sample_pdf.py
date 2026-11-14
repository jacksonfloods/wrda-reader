#!/usr/bin/env python3
"""Put the sampled pages of the highlighted PDFs into one PDF, in the order of
the tally sheet, for inspection by eye.

Usage: collect_sample_pdf.py HIGHLIGHTED_DIR SAMPLE.csv OUT.pdf

Each page keeps its highlights and notes and gets a line at the top saying
which act and page it is ("12 of 200 - WRDA 1988, PDF page 19 - 9 units"), so
a finding can be written against the matching row of SAMPLE.csv.
"""
import csv, pathlib, sys
import pymupdf


def main(folder, sample, out):
    rows = list(csv.DictReader(open(sample, encoding='utf-8')))
    result, opened = pymupdf.open(), {}
    for k, r in enumerate(rows, 1):
        act, pg = r['act'], int(r['pdf_page'])
        if act not in opened:
            opened[act] = pymupdf.open(pathlib.Path(folder) / f'{act} highlighted.pdf')
        result.insert_pdf(opened[act], from_page=pg - 1, to_page=pg - 1)
        page = result[-1]
        boxes = int(r['orange_or_red_boxes'])
        text = (f"{k} of {len(rows)}  -  {act}, PDF page {pg}  -  {r['units_on_page']} units"
                + (f", {boxes} boxed" if boxes else ''))
        page.insert_text((30, 14), text, fontname='hebo', fontsize=8, color=(0.1, 0.1, 0.6))
    result.save(out, garbage=3, deflate=True)
    print(f'{len(result)} pages -> {out}')


if __name__ == '__main__':
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    main(*sys.argv[1:])
