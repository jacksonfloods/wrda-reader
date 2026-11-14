#!/usr/bin/env python3
"""Check the structure files against the hierarchy the government publishes.

Usage: validate_xml.py STRUCTURE_DIR RAW_DIR OUT.md

For the acts of 2014 and later, and for bills, govinfo publishes an XML file
in which every section, subsection, paragraph ... is a tagged element (USLM
for public laws, the House/Senate bill format for bills). The structure files
were built without it, from the indented text, so the XML is an independent
reading of the same act.

For each act this script
  1. lists the XML's sections outside quoted matter and finds the run of them
     whose numbers are the act's sections (the WRDA may be one division or
     title of a larger law);
  2. for every section, lists the labelled units inside it, in order, as
     (depth, level name, label) -- from the XML tags and from the structure
     file -- and compares the two lists;
  3. where the lists agree, compares the headings, ignoring case, spacing and
     punctuation.
Not compared: unnumbered items, table rows, and the words of the text itself
(the structure files are already checked letter for letter against their own
source). Units inside quoted amendments are not units of the act in either
reading and are left out of both.
"""
import difflib, glob, json, pathlib, re, sys
import xml.etree.ElementTree as ET

XML = {     # act: XML file in RAW_DIR
    'WRRDA 2014': '2014, Congress, WRRDA 2014 (PL 113-121).xml',
    'WRDA 2016': '2016, Congress, WIIN Act incl WRDA 2016 (PL 114-322).xml',
    'WRDA 2018': '2018, Congress, AWIA incl WRDA 2018 (PL 115-270).xml',
    'WRDA 2020': '2020, Congress, Consolidated Appropriations Act 2021 incl WRDA 2020 (PL 116-260).xml',
    'WRDA 2022': '2022, Congress, NDAA FY2023 incl WRDA 2022 (PL 117-263).xml',
    'WRDA 2024': '2024, Congress, WRDA 2024 (PL 118-272).xml',
    'WRDA 2026 House bill': '2026, Congress, WRDA 2026 House bill HR 9497 EH (not enacted).xml',
    'WRDA 2026 Senate bill': '2026, Congress, WRDA 2026 Senate bill S 4949 RS (not enacted).xml',
}
LEVELS = ['section', 'subsection', 'paragraph', 'subparagraph', 'clause', 'subclause', 'item', 'subitem', 'subsubitem']
QUOTED = {'quotedContent', 'quoted-block', 'quotedText', 'quote', 'toc', 'sidenote', 'page', 'footnote', 'meta', 'metadata'}
MINE = {'labelled_item': 'item', 'labelled_subitem': 'subitem'}


def tag(e):
    return e.tag.split('}')[-1]


def text(e):
    if e is None:
        return ''
    out = [e.text or '']
    for c in e:
        if tag(c) not in ('sidenote', 'page', 'footnote'):
            out.append(text(c))
        out.append(c.tail or '')
    return ''.join(out)


def child(e, *names):
    return next((c for c in e if tag(c) in names), None)


def xml_units(e, depth, out):
    """Labelled levels under e, in order: [depth, level, label, heading]."""
    for c in e:
        t = tag(c)
        if t in QUOTED:
            continue
        if t in LEVELS:
            label = text(child(c, 'num', 'enum')).strip()
            if t == 'section':
                m = re.search(r'(\d+[A-Za-z]?)\s*\.?\s*$', label)
                label = m.group(1) if m else label
            out.append([depth, t, label, text(child(c, 'heading', 'header')).strip()])
            xml_units(c, depth + 1, out)
        else:
            xml_units(c, depth, out)
    return out


def xml_sections(path):
    """[(number, heading, [units])] for every section outside quoted matter."""
    root = ET.parse(path).getroot()
    flat = xml_units(root, 0, [])
    secs = []
    for u in flat:
        if u[1] == 'section' and u[0] == 0:
            secs.append((u[2], u[3], []))
        elif secs:
            secs[-1][2].append(u)
    return secs


def my_units(d, depth, out):
    for c in d.get('children', []):
        if c.get('label'):
            out.append([depth, MINE.get(c['type'], c['type']), c['label'], c.get('heading') or ''])
            my_units(c, depth + 1, out)
        else:
            my_units(c, depth, out)             # unnumbered item: not compared, but look inside
    return out


def norm(h):
    return re.sub(r'[^a-z0-9]', '', h.lower())


def find_run(xml_nums, mine):
    """Start of the run of XML sections that are the act's sections."""
    n = len(mine)
    best = max(range(max(1, len(xml_nums) - n + 1)),
               key=lambda i: sum(a == b for a, b in zip(xml_nums[i:i + n], mine)))
    return best


def main(sdir, raw, out):
    lines = ['# Structure files checked against the government XML', '',
             'Made by `validate_xml.py`. The XML tags every section, subsection, paragraph and so on; the structure '
             'files were built from the indented text without it. Compared: the labelled units of every section, '
             'in order (depth, level name, label), then headings.', '',
             '| Act | Sections compared | Sections whose units all agree | Labelled units (structure file / XML) | Headings that differ |',
             '|---|---|---|---|---|']
    detail = []
    for act, name in XML.items():
        doc = json.load(open(pathlib.Path(sdir) / f'{act}.structure.json', encoding='utf-8'))
        mine = [s for s in doc['sections']]
        xs = xml_sections(pathlib.Path(raw) / name)
        nums = [s['number'] for s in mine]
        start = find_run([x[0] for x in xs], nums)
        window = {}
        for x in xs[max(0, start - 3):start + len(nums) + 3]:
            window.setdefault(x[0], x)
        agree = n_mine = n_xml = n_head = 0
        notes = []
        absent = [n for n in nums if n not in window]
        if absent:
            notes.append(f'- Sections the XML does not tag as a section: {", ".join(absent)}')
        pairs = [(s, window[s['number']]) for s in mine if s['number'] in window]
        for s, x in pairs:
            a, b = my_units(s, 1, []), x[2]
            n_mine += len(a) + 1
            n_xml += len(b) + 1
            ka, kb = [tuple(u[:3]) for u in a], [tuple(u[:3]) for u in b]
            heads = []
            if norm(s['heading'] or '') != norm(x[1]):
                heads.append(f"  - sec. {s['number']} heading: structure file {s['heading']!r}, XML {x[1]!r}")
            if ka == kb:
                agree += 1
                for u, v in zip(a, b):
                    if norm(u[3]) != norm(v[3]):
                        heads.append(f"  - sec. {s['number']} {u[2]} heading: structure file {u[3]!r}, XML {v[3]!r}")
            else:
                notes.append(f"- sec. {s['number']} ({s['heading']}): units differ")
                sm = difflib.SequenceMatcher(None, ka, kb, autojunk=False)
                for op, i1, i2, j1, j2 in sm.get_opcodes():
                    if op != 'equal':
                        fmt = lambda us: ', '.join(f'{u[1]} {u[2]} at depth {u[0]}' for u in us[:6]) + (' ...' if len(us) > 6 else '') or 'nothing'
                        notes.append(f'  - after unit {i1}: structure file has {fmt(ka[i1:i2])}; XML has {fmt(kb[j1:j2])}')
            n_head += len(heads)
            notes += heads
        lines.append(f'| {act} | {len(pairs)} of {len(mine)} | {agree} | {n_mine} / {n_xml} | {n_head} |')
        detail += ['', f'## {act}', '', f'XML: `{name}`', ''] + (notes or ['No differences.'])
        print(lines[-1])
    pathlib.Path(out).write_text('\n'.join(lines + detail) + '\n', encoding='utf-8')


if __name__ == '__main__':
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    main(*sys.argv[1:])
