#!/usr/bin/env python3
"""Make a copy of an act's PDF with every unit of its structure file
highlighted on the page, so the reading can be checked against the print.

Usage: highlight_pdf.py STRUCTURE.json PDF LINES.tsv OUT.pdf
       highlight_pdf.py STRUCTURE.json PDF - OUT.pdf      (act built from govinfo text)

What is marked
  * The first printed line of every unit (section, subsection, paragraph,
    ... and unnumbered items) gets a highlight in the colour of its level.
    Where two units start on one line ("(a) IN GENERAL.--(1) ..."), the line
    is divided at the second label.
  * The unit's id, without the year ("401.c.3"), is printed small to the
    left of the line. This is what shows which parent a unit was put under.
  * Title and other centred headings are highlighted grey.
  * A unit whose label or heading the build repaired has an orange box, and a
    line with a flag to check has a red box. Both carry a note with the
    details (hover or click in a PDF reader).
  * A key to the colours is printed at the foot of every page.

The source PDF is not changed. Positions come from the PDF's own text layer
(`pdftotext -tsv`), grouped into lines exactly as extract_lines.py and
extract_scan_lines.py do; the script stops if any line differs from
LINES.tsv, the table the structure file was built from.

With "-" in place of LINES.tsv the structure file was built from govinfo's
text, not from this PDF, so there is no table tying units to PDF lines. Each
unit is then found on the page: the page is the one the structure file gives
(its Statutes at Large page, read from the PDF's running heads), and the line
is the next one on that page that begins with the unit's own opening words
(label, heading, text; letters and digits only, so line breaks, small capitals
and quotation-mark styles do not matter). A unit that cannot be found is
reported and left unmarked; nothing is guessed.

Needs poppler's pdftotext and PyMuPDF (see wrda_structure_env.yml).
"""
import collections, csv, json, pathlib, re, statistics, subprocess, sys, unicodedata
import pymupdf
import extract_scan_lines as scan

COLOURS = {                                    # level: (name in the key, RGB)
    'heading':           ('title heading',      (0.60, 0.60, 0.60)),
    'section':           ('section',            (1.00, 0.45, 0.35)),
    'subsection':        ('subsection (a)',     (1.00, 0.85, 0.10)),
    'paragraph':         ('paragraph (1)',      (0.45, 0.85, 0.35)),
    'subparagraph':      ('subparagraph (A)',   (0.35, 0.75, 1.00)),
    'clause':            ('clause (i)',         (0.70, 0.55, 1.00)),
    'subclause':         ('subclause (I)',      (1.00, 0.55, 0.85)),
    'labelled_item':     ('item (aa)',          (0.30, 0.85, 0.80)),
    'labelled_subitem':  ('subitem (AA)',       (0.85, 0.70, 0.45)),
    'item':              ('unnumbered item',    (0.75, 0.65, 0.50)),
    'group':             ('State name',         (0.80, 0.80, 0.80)),
}
REPAIRED, FLAGGED = (1.0, 0.5, 0.0), (0.9, 0.0, 0.0)


def words_by_page(pdf):
    """{pdf page: [(top, left, right, text, bottom)]} from the text layer."""
    tsv = subprocess.run(['pdftotext', '-tsv', str(pdf), '-'], check=True, capture_output=True).stdout.decode('utf-8')
    pages = collections.defaultdict(list)
    for row in csv.reader(tsv.splitlines()[1:], delimiter='\t', quoting=csv.QUOTE_NONE):
        if row[0] == '5':
            left, top, width, height = (float(row[k]) for k in (6, 7, 8, 9))
            pages[int(row[1])].append((top, left, left + width, row[11], top + height))
    return pages


def lines_text_pdf(pages):
    """Printed lines of a text PDF, grouped as extract_lines.py groups them."""
    out = []
    for pg in sorted(pages):
        cur = None
        for w in sorted(pages[pg], key=lambda w: (round(w[0]), w[1])):
            if cur and abs(w[0] - cur[0]) < 3:
                cur[1].append(w)
            else:
                cur = (w[0], [w])
                out.append((pg, cur[1]))
    return [(pg, sorted(ws, key=lambda w: w[1])) for pg, ws in out]


def lines_scan(pages):
    """Body lines of a page scan, trimmed as extract_scan_lines.py trims them."""
    heads, bodies, edges = {}, {}, {}
    for pg in sorted(pages):
        lines = scan.lines_of(pages[pg])
        if scan.HEAD.search(scan.text_of(lines[0])):
            heads[pg], lines = lines[0], lines[1:]
        bodies[pg] = lines
        edges[pg] = scan.measure(lines)
    spans = {pg: r - s for pg, (r, s) in edges.items()}
    widest = max(spans.values())
    width = statistics.median(v for v in spans.values() if v >= widest - 5)
    out = []
    for pg in sorted(pages):
        right = edges[pg][0]
        left = right - width
        for ln in bodies[pg]:
            inside = [w for w in ln if left - scan.PAD <= (w[1] + w[2]) / 2 <= right + scan.PAD]
            if inside:
                out.append((pg, inside))
    return out


def geometry(pdf, table, is_scan):
    """{line number of LINES.tsv: (pdf page, words)}; stops if the text differs."""
    pages = words_by_page(pdf)
    lines = lines_scan(pages) if is_scan else lines_text_pdf(pages)
    rows = [r for r in csv.reader(open(table, encoding='utf-8'), delimiter='\t', quoting=csv.QUOTE_NONE)][1:]
    rows = [r for r in rows if r[3]]
    if len(rows) != len(lines):
        sys.exit(f'{len(lines)} lines found in the PDF, {len(rows)} in {pathlib.Path(table).name}')
    geo = {}
    for r, (pg, ws) in zip(rows, lines):
        if ' '.join(w[3] for w in ws) != r[3]:
            sys.exit(f'line {r[0]} differs from the lines table: {r[3][:60]!r}')
        geo[int(r[0])] = (pg, ws)
    return geo


def norm(t):
    return re.sub(r'[^a-z0-9]', '', unicodedata.normalize('NFKD', t).lower())


def opening(u):
    return ' '.join(x for x in (u.get('label'), u.get('heading'), u.get('own_text')) if x)


def locate(pdf, wanted):
    """Find lines on the PDF pages by their opening words.
    wanted: [(key, Statutes page, opening text)] in reading order.
    Returns {key: (pdf page, words)} and the keys not found."""
    pages = words_by_page(pdf)
    on_page = collections.defaultdict(list)     # Statutes page -> [(pdf page, [(words, normalised text)])]
    for pg in sorted(pages):
        # the printer's mark set sideways up the edge of the page: its word boxes are tall and narrow
        upright = [w for w in pages[pg] if not (w[4] - w[0] > 14 or (len(w[3]) > 4 and w[4] - w[0] > 1.5 * (w[2] - w[1])))]
        lines = scan.lines_of(upright)
        m = re.search(r'STAT\.\s*(\d{2,4})', scan.text_of(lines[0])) if lines else None
        if not m or len(lines) < 2:
            continue
        right = scan.measure(lines[1:])[0]      # right edge of the body column on this page
        for ln in lines[1:]:
            body = [w for w in ln if (w[1] + w[2]) / 2 <= right + scan.PAD]     # drop a note in the right margin
            # A note in the left margin sits before the body on the same line, set off by a wide
            # gap. So does the space after a label. Try the line from each wide gap on, and the
            # untrimmed line too, for a page whose right edge was measured wrongly.
            starts = [0] + [i for i in range(1, len(body)) if body[i][1] - body[i - 1][2] > scan.GAP]
            tries = [body[i:] for i in starts]
            if len(body) < len(ln):
                last = max(i for i in range(1, len(ln)) if ln[i][1] - ln[i - 1][2] > scan.GAP) if len(ln) > 1 and any(
                    ln[i][1] - ln[i - 1][2] > scan.GAP for i in range(1, len(ln))) else None
                tries += [ln] + ([ln[:last]] if last else [])
            elif len(ln) > 1:
                gaps = [i for i in range(1, len(ln)) if ln[i][1] - ln[i - 1][2] > scan.GAP]
                if gaps and len(gaps) > 0 and gaps[-1] > len(ln) // 2:
                    tries.append(ln[:gaps[-1]])                                 # the line without its last piece
            # a margin note set close beside the last word of the line: try without the last word or two
            tries += [t[:-k] for t in list(tries) for k in (1, 2) if len(t) > k + 3]
            if body or ln:
                on_page[int(m.group(1))].append((pg, [(t, norm(scan.text_of(t))) for t in tries if t]))
    geo, missing, at = {}, [], collections.Counter()
    for key, stat, text in wanted:
        want = norm(text)
        for page in (stat, stat + 1, stat - 1):
            lines = on_page.get(page, [])
            hit = None
            for i in range(at[page], len(lines)):
                for ws, c in lines[i][1]:
                    n = min(len(c), len(want))
                    if c[:n] == want[:n] and (n >= 12 or n == len(want) or (n == len(c) and n >= 6)):     # the line's letters open the unit, to the line's end
                        hit = (i, ws)
                        break
                if hit:
                    break
            if hit:
                at[page] = hit[0] + 1
                geo[key] = (lines[hit[0]][0], hit[1])
                break
        else:
            missing.append(key)
    # Second pass for what is left: read the body column alone. A margin note printed close beside
    # a line can pull that line's words apart when the page is grouped into lines; with the margins
    # cut away first (column edges taken from all pages of the same side) the line reads whole.
    if missing:
        col, edges = {}, {}
        for pg in pages:
            lines = scan.lines_of(pages[pg])
            if len(lines) > 2:
                edges[pg] = scan.measure(lines[1:])     # right edge of the column, and where its full lines start
        for side in (0, 1):
            es = [e for pg, e in edges.items() if pg % 2 == side]
            if es:
                col[side] = (statistics.median(e[1] for e in es), statistics.median(e[0] for e in es))
        stat_of = {x[0]: st for st, v in on_page.items() for x in v}
        wants = {key: (stat, norm(text)) for key, stat, text in wanted}
        for key in list(missing):
            stat, want = wants[key]
            for pg, st in stat_of.items():
                if abs(st - stat) > 1 or pg % 2 not in col:
                    continue
                left, right = col[pg % 2]
                inside = [w for w in pages[pg] if left - scan.PAD <= (w[1] + w[2]) / 2 <= right + scan.PAD]
                for ln in scan.lines_of(inside):
                    for i in [0] + [i for i in range(1, len(ln)) if ln[i][1] - ln[i - 1][2] > scan.GAP]:
                        c = norm(scan.text_of(ln[i:]))
                        n = min(len(c), len(want))
                        if n >= 12 and c[:n] == want[:n]:
                            geo[key] = (pg, ln[i:])
                            break
                    if key in geo:
                        break
                if key in geo:
                    missing.remove(key)
                    break
    return geo, missing


def box(ws, pad=0.8):
    return pymupdf.Rect(min(w[1] for w in ws) - pad, min(w[0] for w in ws) - pad,
                        max(w[2] for w in ws) + pad, max(w[4] for w in ws) + pad)


def units(doc):
    for sec in doc['sections']:
        stack = [sec]
        while stack:
            u = stack.pop()
            yield u
            stack.extend(reversed(u.get('children', [])))


def split_line(ws, us):
    """Divide a line among the units that start on it, at their labels.
    Returns one rectangle per unit. Two labels can sit in one printed word
    ("(A)(i)"); the word is then divided in proportion to its letters, or in
    half where the scan garbled the pair ("(EXi)")."""
    full = box(ws)
    xs, word, char = [full.x0], 0, 0            # where each unit starts: x, and the word and letter reached
    for u in us[1:]:
        label = u.get('label_as_read') or u.get('label') or ''
        hit = None
        for i in range(word, len(ws)):
            at = ws[i][3].find(label, char + 1 if i == word else 0) if label else -1
            if at >= 0:
                hit = (i, at)
                break
        if hit is None:                         # not readable: halve the word the last label was in
            hit = (word, max(char + 1, len(ws[word][3]) // 2))
        word, char = hit
        w = ws[word]
        xs.append(w[1] + (w[2] - w[1]) * char / max(1, len(w[3])))
    return [pymupdf.Rect(a, full.y0, b, full.y1) for a, b in zip(xs, xs[1:] + [full.x1])]


def main(structure, pdf, table, out):
    doc = json.load(open(structure, encoding='utf-8'))
    missing = []
    if table == '-':
        stat = lambda c: int(re.search(r'(\d+)\s*$', c).group(1))
        by = collections.defaultdict(list)
        for u in units(doc):
            by[u['source_line']].append(u)
        wanted = [(h['source_line'], stat(h['stat_page']), h['text']) for h in doc.get('headings', [])]
        wanted += [(ln, stat(us[0]['stat_page']), ' '.join(opening(u) for u in us)) for ln, us in by.items()]
        geo, missing = locate(pdf, sorted(wanted))
    else:
        geo = geometry(pdf, table, 'pdf' not in doc['source']['text'])
    pdf_doc = pymupdf.open(pdf)
    year = doc['sections'][0]['id'].split('.')[0]
    n = collections.Counter()

    def mark(pg, r, level, note, tag=None):
        page = pdf_doc[pg - 1]
        a = page.add_highlight_annot(r)
        a.set_colors(stroke=COLOURS[level][1])
        a.set_info(title='WRDA structure', content=note)
        a.update()
        if tag:
            size = 4.5
            w = pymupdf.get_text_length(tag, 'helv', size)
            x = max(2, r.x0 - w - 2)
            page.insert_text((x, r.y1 - 2.2), tag, fontname='helv', fontsize=size,
                             color=tuple(0.55 * c for c in COLOURS[level][1]))
        n[level] += 1

    def outline(pg, ws, colour, note):
        page = pdf_doc[pg - 1]
        r = box(ws, 2.0)
        a = page.add_rect_annot(r)
        a.set_colors(stroke=colour)
        a.set_border(width=1.0)
        a.set_info(title='WRDA structure', content=note)
        a.update()
        t = page.add_text_annot((r.x1 + 3, r.y0 - 2), note, icon='Note')
        t.set_colors(stroke=colour)
        t.set_info(title='WRDA structure', content=note)
        t.update()

    for h in doc.get('titles', []) + doc.get('headings', []):
        if h['source_line'] not in geo:
            continue
        pg, ws = geo[h['source_line']]
        mark(pg, box(ws), 'heading', h.get('text') or f"TITLE {h['number']}--{h['heading']}")

    by_line = collections.defaultdict(list)
    for u in units(doc):
        by_line[u['source_line']].append(u)
    for line, us in sorted(by_line.items()):
        if line not in geo:
            continue
        pg, ws = geo[line]
        parts = split_line(ws, us) if len(us) > 1 else [box(ws)]
        for u, part in zip(us, parts):
            tag = u['id'].split('.', 1)[1] if u is us[0] else None    # one id per line; the rest are in the notes
            note = f"{u['id']}  [{u['type']}]" + (f"  {u['heading']}" if u.get('heading') else '')
            mark(pg, part, u['type'], note, tag)
        for u in us:
            fixes = [f"{k.split('_')[0]} as read by the scan: {u[k]!r}" for k in ('label_as_read', 'heading_as_read')
                     if u.get(k) and u[k] != u.get(k.split('_')[0])]
            if fixes:
                outline(pg, ws, REPAIRED, f"{u['id']} repaired by the build. " + '; '.join(fixes))
                n['repaired'] += 1

    for f in doc.get('flags', []):
        if f['kind'] == 'LABEL REPAIRED':
            continue                            # already boxed in orange above
        if f['source_line'] not in geo:
            continue
        pg, ws = geo[f['source_line']]
        outline(pg, ws, FLAGGED, f"{f['kind']}: {f['what']}")
        n['flagged'] += 1
    for c in doc.get('corrections', []):
        if c['source_line'] not in geo:
            continue
        pg, ws = geo[c['source_line']]
        outline(pg, ws, REPAIRED, f"Text corrected in the structure file. Was: {c['was']!r}. Why: {c['why']}")
        n['corrected'] += 1

    used = [k for k in COLOURS if n[k]]
    for page in pdf_doc:                        # key to the colours, at the foot of the page
        x, y = 30, page.rect.height - 10
        for k in used:
            name, rgb = COLOURS[k]
            page.draw_rect(pymupdf.Rect(x, y - 5, x + 8, y + 1), color=None, fill=rgb, fill_opacity=0.8)
            page.insert_text((x + 10, y), name, fontname='helv', fontsize=5, color=(0.25, 0.25, 0.25))
            x += 14 + pymupdf.get_text_length(name, 'helv', 5)
        for name, rgb in (('repaired by the build', REPAIRED), ('flag to check', FLAGGED)):
            page.draw_rect(pymupdf.Rect(x, y - 5, x + 8, y + 1), color=rgb, width=0.8)
            page.insert_text((x + 10, y), name, fontname='helv', fontsize=5, color=(0.25, 0.25, 0.25))
            x += 14 + pymupdf.get_text_length(name, 'helv', 5)

    pdf_doc.save(out, garbage=3, deflate=True)
    total = sum(n[k] for k in COLOURS if k != 'heading')
    print(f"{doc['act']}: {total} units highlighted on {len(pdf_doc)} pages "
          f"({', '.join(f'{n[k]} {k}' for k in used)}); "
          f"{n['repaired']} repaired, {n['flagged']} flagged, {n['corrected']} corrected")
    if missing:
        ids = {u['source_line']: u['id'] for u in units(doc)}
        print(f'  NOT FOUND on the page, left unmarked ({len(missing)} lines): '
              + ', '.join(ids.get(k, f'heading at source line {k}') for k in missing))
    elif total != doc['counts']['units']:
        sys.exit(f"  MISMATCH: the structure file has {doc['counts']['units']} units")

if __name__ == '__main__':
    if len(sys.argv) != 5:
        sys.exit(__doc__)
    main(*sys.argv[1:])
