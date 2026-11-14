#!/usr/bin/env python3
"""Draw a random sample of pages of the highlighted PDFs for inspection by eye.

Usage: sample_pages.py HIGHLIGHTED_DIR OUT.csv [SEED]

The pages are drawn at random without replacement inside three groups, with a
fixed seed, so the same command always gives the same list:
    scans (1988, 1990, 1992)          80 pages   (heaviest: OCR, least other support)
    WRDA 1986                         40 pages
    1996, 1999, 2000, 2007            80 pages
Inside a group every page of every act has the same chance. Pages with no
units on them (contents lists) stay in: a unit missed there would show as a
label with no highlight.

OUT.csv has one row per sampled page, in reading order, with the number of
highlighted units on it and empty columns to fill in: checked (y), errors
found, and a note.
"""
import csv, pathlib, random, sys
import pymupdf

GROUPS = [('scans', ['WRDA 1988', 'WRDA 1990', 'WRDA 1992'], 80),
          ('typed PDF', ['WRDA 1986'], 40),
          ('govinfo slip laws', ['WRDA 1996', 'WRDA 1999', 'WRDA 2000', 'WRDA 2007'], 80)]


def main(folder, out, seed='20261112'):
    rng = random.Random(int(seed))
    rows = []
    for group, acts, n in GROUPS:
        pool = []
        for act in acts:
            doc = pymupdf.open(pathlib.Path(folder) / f'{act} highlighted.pdf')
            for i, page in enumerate(doc, 1):
                units = sum(1 for a in page.annots() or [] if a.type[1] == 'Highlight' and '[' in a.info.get('content', '')
                            and '[heading' not in a.info.get('content', ''))
                boxes = sum(1 for a in page.annots() or [] if a.type[1] == 'Square')
                pool.append((act, i, units, boxes))
        picked = sorted(rng.sample(pool, n))
        rows += [(group, act, pg, units, boxes, '', '', '') for act, pg, units, boxes in picked]
        print(f'{group:18s} {n:3d} of {len(pool):4d} pages ({100 * n / len(pool):.0f}%), '
              f'{sum(p[2] for p in picked)} units on them; by act: '
              + ', '.join(f'{a} {sum(1 for p in picked if p[0] == a)}' for a in acts))
    with open(out, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f, lineterminator='\n')
        w.writerow(['group', 'act', 'pdf_page', 'units_on_page', 'orange_or_red_boxes', 'checked', 'errors_found', 'note'])
        w.writerows(rows)
    print(f'{len(rows)} pages, {sum(r[3] for r in rows)} units, seed {seed} -> {out}')


if __name__ == '__main__':
    if len(sys.argv) not in (3, 4):
        sys.exit(__doc__)
    main(*sys.argv[1:])
