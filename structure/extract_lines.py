#!/usr/bin/env python3
"""Turn a text-layer PDF into a table of its printed lines, with each line's
left offset.

The structure builders (build_1986.py, ...) read nesting depth from how far a
line is indented. `pdftotext -layout` blurs that (it squeezes the page into
character columns), so this script keeps the exact left edge of every line.

Output: tab-separated, one row per line of `pdftotext -layout` output, so row
N is line N of the corpus text file:
    line   line number in the layout text (1-based)
    page   PDF page the line is on
    x0     left edge of the line in points (blank for an empty line)
    text   the line's words joined by single spaces

Method: `pdftotext -layout` gives the lines, their order and the page breaks;
`pdftotext -tsv` gives every word's position. Words are grouped into printed
lines by page and vertical position, and the two listings are matched one to
one. The script stops if any line fails to match.

Usage: extract_lines.py PDF OUT.tsv
Needs poppler's pdftotext on the PATH (see environment.yml).
"""
import csv, hashlib, pathlib, re, subprocess, sys


def pdftotext(mode, pdf):
    return subprocess.run(['pdftotext', mode, str(pdf), '-'], check=True,
                          capture_output=True).stdout.decode('utf-8')


def squeeze(s):
    return re.sub(r'\s+', ' ', s.replace('\f', ' ')).strip()


def printed_lines(tsv):
    """Group the word rows of `pdftotext -tsv` into printed lines."""
    words = []
    for row in csv.reader(tsv.splitlines()[1:], delimiter='\t', quoting=csv.QUOTE_NONE):
        if row[0] == '5':                       # level 5 = word
            words.append((int(row[1]), float(row[7]), float(row[6]), row[11]))
    words.sort(key=lambda w: (w[0], round(w[1]), w[2]))
    lines, cur = [], None
    for page, top, left, text in words:
        if cur and cur['page'] == page and abs(top - cur['top']) < 3:
            cur['words'].append((left, text))
        else:
            cur = dict(page=page, top=top, words=[(left, text)])
            lines.append(cur)
    for ln in lines:
        ln['words'].sort()
        ln['x0'] = ln['words'][0][0]
        ln['text'] = ' '.join(w for _, w in ln['words'])
    return lines


def main(pdf, out):
    pdf, out = pathlib.Path(pdf), pathlib.Path(out)
    geo = printed_lines(pdftotext('-tsv', pdf))
    layout = pdftotext('-layout', pdf).split('\n')
    while layout and not squeeze(layout[-1]):
        layout.pop()                            # closing newline and form feed
    rows, page, g = [], 1, 0
    for no, raw in enumerate(layout, 1):
        page += raw.count('\f')                 # a form feed starts the next page
        text = squeeze(raw)
        if not text:
            rows.append((no, page, '', ''))
            continue
        if g >= len(geo) or squeeze(geo[g]['text']) != text or geo[g]['page'] != page:
            sys.exit(f'line {no} does not match the word listing: {text[:60]!r}')
        rows.append((no, page, f"{geo[g]['x0']:.2f}", text))
        g += 1
    if g != len(geo):
        sys.exit(f'{len(geo) - g} printed lines were left unmatched')
    with open(out, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f, delimiter='\t', quoting=csv.QUOTE_NONE, quotechar=None, lineterminator='\n')
        w.writerow(['line', 'page', 'x0', 'text'])
        w.writerows(rows)
    sha = lambda p: hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
    print(f'{len(rows)} lines ({g} non-blank), {page} pages')
    print(f'sha256 {sha(pdf)}  {pdf.name}')
    print(f'sha256 {sha(out)}  {out.name}')


if __name__ == '__main__':
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
