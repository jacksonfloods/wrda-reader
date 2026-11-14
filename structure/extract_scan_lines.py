#!/usr/bin/env python3
"""Turn a Statutes at Large page scan into a table of its body lines, with
each line's indent. The scan counterpart of extract_lines.py.

A printed page has a running head, a column of body text, and notes in the
outer margin. The body column is in a different place on every page, and on
some pages no line starts at its left edge. So each page is measured against
itself, from the right:

  1. Words and their positions come from the scan's text layer
     (`pdftotext -tsv`). Nothing is read again from the image.
  2. The top line is the running head ("102 STAT. 4016  PUBLIC LAW ...").
     It is dropped; its page number is kept.
  3. Right edge. The act is set justified, so full lines all end at the same
     place. Each printed line is cut wherever two neighbouring words are more
     than GAP points apart (a margin note beside the body). The most common
     right end of the pieces is the right edge of the column.
  4. Left edge = right edge - column width. The column width is the same on
     every page of an act. It is measured on the pages that have full-width
     lines, then applied to all pages.
  5. A word is body text if its centre lies inside the column. Everything
     else is a margin note or scanner noise and is dropped.
  6. The body words are grouped into lines. A line's indent is the distance
     from the left edge to its first word.

Output OUT.tsv has the four columns extract_lines.py writes, and one more:
    line   running number
    page   printed page number, from the running heads
    x0     indent in points from the left edge of the body column on that page
    text   the line's words joined by single spaces
    x1     where the line ends, in points from the same left edge (a line that
           stops short of the column width is the last line of a paragraph)
A row with no text marks extra space between two lines.

OUT.trimmed.txt lists, page by page, the edges found and everything that was
dropped, so the trim can be checked by reading it.

Usage: extract_scan_lines.py PDF OUT.tsv
Needs poppler's pdftotext on the PATH (see wrda_structure_env.yml).
"""
import collections, csv, hashlib, pathlib, re, statistics, subprocess, sys

GAP = 11.0      # points: more than this between two words on a line separates body from margin note
SAME_LINE = 3.0 # points: words whose tops differ by less are on one line
PAD = 4.0       # points: slack on each side of the column
HEAD = re.compile(r'PUBLIC|STAT')
HEAD_PAGE = re.compile(r'STAT\.?\s*(\d{4})')


def page_words(pdf):
    """{pdf page: [(top, left, right, text)]} from the text layer."""
    tsv = subprocess.run(['pdftotext', '-tsv', str(pdf), '-'], check=True,
                         capture_output=True).stdout.decode('utf-8')
    pages = collections.defaultdict(list)
    for row in csv.reader(tsv.splitlines()[1:], delimiter='\t', quoting=csv.QUOTE_NONE):
        if row[0] == '5':                       # level 5 = word
            left, top, width = float(row[6]), float(row[7]), float(row[8])
            pages[int(row[1])].append((top, left, left + width, row[11]))
    return pages


def lines_of(words):
    """Group words into printed lines, top to bottom, each left to right."""
    out, cur = [], None
    for w in sorted(words, key=lambda w: (round(w[0]), w[1])):
        if cur and abs(w[0] - cur[0]) < SAME_LINE:
            cur[1].append(w)
        else:
            cur = (w[0], [w])
            out.append(cur)
    return [sorted(ws, key=lambda w: w[1]) for _, ws in out]


def pieces(line):
    """Cut a line where neighbouring words are more than GAP apart."""
    out = [[line[0]]]
    for a, b in zip(line, line[1:]):
        if b[1] - a[2] > GAP:
            out.append([])
        out[-1].append(b)
    return out


def text_of(ws):
    return ' '.join(w[3] for w in ws)


def common(values, width=3.0):
    """Centre of the densest cluster of values, and how many are in it."""
    values = sorted(values)
    best = max(values, key=lambda v: sum(1 for x in values if v <= x <= v + width))
    cluster = [x for x in values if best <= x <= best + width]
    return statistics.median(cluster), len(cluster)


def measure(lines):
    """Right edge of the body column, and the leftmost start of its full lines."""
    ps = [p for ln in lines for p in pieces(ln)]
    right, _ = common([p[-1][2] for p in ps])
    full = sorted(p[0][1] for p in ps if abs(p[-1][2] - right) <= PAD)
    # leftmost place where at least two full lines start
    start = next((a for a, b in zip(full, full[1:]) if b - a <= 3.0), full[0])
    return right, start


def main(pdf, out):
    pdf, out = pathlib.Path(pdf), pathlib.Path(out)
    pages = page_words(pdf)
    heads, bodies, edges = {}, {}, {}
    for pg in sorted(pages):
        lines = lines_of(pages[pg])
        if HEAD.search(text_of(lines[0])):
            heads[pg], lines = lines[0], lines[1:]
        bodies[pg] = lines
        edges[pg] = measure(lines)

    # Column width: the widest span that pages agree on. Pages with no line at
    # the left edge give a narrower span and are outvoted.
    spans = {pg: r - s for pg, (r, s) in edges.items()}
    widest = max(spans.values())
    width = statistics.median(v for v in spans.values() if v >= widest - 5)

    # Printed page numbers: read from the heads, then counted from the first page.
    seen = {pg: int(m.group(1)) for pg, h in heads.items() for m in [HEAD_PAGE.search(text_of(h))] if m}
    first = collections.Counter(n - pg for pg, n in seen.items()).most_common(1)[0][0] + min(pages)

    rows, report, no = [], [], 0
    pitch = statistics.median(b[0][0] - a[0][0] for ls in bodies.values() for a, b in zip(ls, ls[1:]))
    kept = dropped = 0
    for k, pg in enumerate(sorted(pages)):
        printed = first + k
        right, start = edges[pg]
        left = right - width
        report.append(f'page {printed} (scan page {pg}): body column {left:.1f} to {right:.1f} pt; '
                      f'leftmost full line starts {start - left:+.1f} pt from the left edge')
        if pg in heads:
            report.append(f'    head: {text_of(heads[pg])}')
            if seen.get(pg) not in (None, printed):
                report.append(f'    (head reads page {seen[pg]})')
        else:
            report.append('    NO RUNNING HEAD FOUND')
        body = []
        for ln in bodies[pg]:
            inside = [w for w in ln if left - PAD <= (w[1] + w[2]) / 2 <= right + PAD]
            outside = [w for w in ln if w not in inside]
            if outside:
                dropped += len(outside)
                report.append(f'    dropped: {text_of(outside)}')
            if inside:
                kept += len(inside)
                body.append(inside)
        prev = None
        for ln in body:
            no += 1
            if prev is not None and ln[0][0] - prev > 1.7 * pitch:      # extra space above this line
                rows.append((no, printed, '', '', ''))
                no += 1
            rows.append((no, printed, f'{ln[0][1] - left:.2f}', text_of(ln), f'{ln[-1][2] - left:.2f}'))
            prev = ln[0][0]

    with open(out, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f, delimiter='\t', quoting=csv.QUOTE_NONE, quotechar=None, lineterminator='\n')
        w.writerow(['line', 'page', 'x0', 'text', 'x1'])
        w.writerows(rows)
    trimmed = out.with_name(out.name.replace('.tsv', '') + '.trimmed.txt')
    trimmed.write_text('\n'.join(report) + '\n', encoding='utf-8')
    sha = lambda p: hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
    narrow = [first + k for k, pg in enumerate(sorted(pages)) if spans[pg] < widest - 5]
    print(f'{len(pages)} pages, printed pages {first}-{first + len(pages) - 1}; column width {width:.1f} pt')
    print(f'{kept} body words kept in {sum(1 for r in rows if r[3])} lines; {dropped} words dropped as margin notes')
    print(f'pages with no line at the left edge: {narrow or "none"}')
    print(f'sha256 {sha(pdf)}  {pdf.name}')
    print(f'sha256 {sha(out)}  {out.name}')


if __name__ == '__main__':
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
