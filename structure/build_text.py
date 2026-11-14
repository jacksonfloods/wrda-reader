#!/usr/bin/env python3
"""Build the structure file for a WRDA whose source is govinfo's plain text
(the acts of 1996 to 2024 and the two 2026 bills).

Usage: build_text.py KEY RAW_DIR OUT_DIR [--force]
       build_text.py all RAW_DIR OUT_DIR
KEY is one of the keys of ACTS below (1996, 1999, ... 2026H, 2026S).

How the text is read
--------------------
govinfo prints every line at an exact indent, counted in spaces:

    first line of a paragraph   4  12  20  26 (28 in bills)  36  44  48
    its later lines             0   8  16  22 (24 in bills)  32  40  44
    depth                       1   2   3   4                 5   6   7

So a paragraph is a first line and the lines after it that sit 4 spaces to
its left. Text at a later-line indent with no first line is the sentence of
an outer unit resuming after its sub-units (trailing_text).

Rules, in the order they are applied to each line:
 1. Margin notes "<<NOTE: ...>>" and page marks "[[Page 110 STAT. 3663]]"
    are taken out. The page marks give every unit its Statutes at Large page.
 2. A line of dashes opens a table (the project lists of 2014 and later).
    The table is kept whole, as printed, in the unit above it; its numbered
    rows are also listed under "tables".
 3. "Sec. 101. Project authorizations." at the left edge is the contents
    list. It is kept whole in the unit that carries it and is used to check
    the section headings.
 4. "SEC. 101. HEADING." at the left edge starts a section.
 5. A centred "DIVISION", "TITLE", "Subtitle", "PART" or "CHAPTER" line is a
    label on the sections after it, not a level of the tree.
 6. Quoted matter (text the act inserts into other laws) is never split into
    units. Every paragraph of it opens with `` and the last closes with ''.
 7. A first line with labels -- "(a)", "(1)", "(A)", "(i)", "(I)", "(aa)" --
    is placed by wrda_tree.Tree. A first line without one is a further
    paragraph of the unit at its depth.

Each act's file name, hash and (for acts inside larger laws) the lines that
hold the WRDA are in ACTS. The script stops if any character of the input is
not accounted for in the output.
"""
import html, pathlib, re, sys
import wrda_tree as T

BUILDER_VERSION = '2.1'
ACTS = {
    '1996': dict(name='WRDA 1996', public_law='104-303', enacted='1996-10-12', volume=110,
                 file='1996, Congress, WRDA 1996 (PL 104-303).htm',
                 sha256='0dd31e8ec94f26536f3ce7853f0f0c80e084724823f54b816bb9a048c81e749b'),
    '1999': dict(name='WRDA 1999', public_law='106-53', enacted='1999-08-17', volume=113,
                 file='1999, Congress, WRDA 1999 (PL 106-53).htm',
                 sha256='8ede24da1358a66d5ced9fb898e5248f06d9fed93a8895fbc32dc618f583f303'),
    '2000': dict(name='WRDA 2000', public_law='106-541', enacted='2000-12-11', volume=114,
                 file='2000, Congress, WRDA 2000 (PL 106-541).htm',
                 sha256='e88e6df7d6ab5ceff0b4ee43dbb648b1c5a1b0fd4c17565dec5694b3d0a1b692'),
    '2007': dict(name='WRDA 2007', public_law='110-114', enacted='2007-11-08', volume=121,
                 file='2007, Congress, WRDA 2007 (PL 110-114).htm',
                 sha256='65b9fe89d7acedc41c79da599e3d947e235ed6406dd4ae5ed025264bb92e7b0b',
                 end_line=15338),          # the act ends with the veto-override record, not "Approved"
    '2014': dict(name='WRRDA 2014', public_law='113-121', enacted='2014-06-10', volume=128,
                 file='2014, Congress, WRRDA 2014 (PL 113-121).htm',
                 sha256='f70c8519a6bb902242729e15af7612857ffbf75a971b8a379f88857d4c437286'),
    '2016': dict(name='WRDA 2016', public_law='114-322', enacted='2016-12-16', volume=130,
                 file='2016, Congress, WIIN Act incl WRDA 2016 (PL 114-322).htm',
                 sha256='60d8f0944e0bbe5a6176e6a18d8bf3c48d8d6fdae054e046dc397e464ffb0b32',
                 cut=(379, 5452), toc=(36, 184), part='Title I of the WIIN Act'),
    '2018': dict(name='WRDA 2018', public_law='115-270', enacted='2018-10-23', volume=132,
                 file='2018, Congress, AWIA incl WRDA 2018 (PL 115-270).htm',
                 sha256='b259c073105b50dbc79fbc70e19541fc6798cb3789dede6d26c2c51742fc55aa',
                 cut=(308, 4676), toc=(34, 218), part="Title I of America's Water Infrastructure Act of 2018"),
    '2020': dict(name='WRDA 2020', public_law='116-260', enacted='2020-12-27', volume=134,
                 file='2020, Congress, Consolidated Appropriations Act 2021 incl WRDA 2020 (PL 116-260).htm',
                 sha256='c5d5b08013295d9a28c6857ef75ddf791cbf28906e9c72d53c222d5c83ea1156',
                 cut=(89308, 98195), part='Division AA of the Consolidated Appropriations Act, 2021'),
    '2022': dict(name='WRDA 2022', public_law='117-263', enacted='2022-12-23', volume=136,
                 file='2022, Congress, NDAA FY2023 incl WRDA 2022 (PL 117-263).htm',
                 sha256='2a74f5e0c828ac5704c31936a795cc507c62c585a832f4a4117be009f6163a89',
                 cut=(84796, 94280), part='Title LXXXI of Division H of the NDAA for Fiscal Year 2023'),
    '2024': dict(name='WRDA 2024', public_law='118-272', enacted='2025-01-04', volume=138,
                 file='2024, Congress, WRDA 2024 (PL 118-272).htm',
                 sha256='d497fe15c8bf910da10f983d69185f6fd098d18ad5672f55f453edc4991774a8',
                 cut=(1, 11215), part='Division A (Division B, Other Matters, is left out)'),
    '2026H': dict(name='WRDA 2026 House bill', public_law=None, enacted=None, volume=None,
                  file='2026, Congress, WRDA 2026 House bill HR 9497 EH (not enacted).htm',
                  sha256='d6b73fac01c0f7fd51b754652f59aa2105cdec269cd351076555ff2ab114bd1c',
                  cut=(1, 7868), part='H.R. 9497 as passed by the House, 2026-09-16; not enacted'),
    '2026S': dict(name='WRDA 2026 Senate bill', public_law=None, enacted=None, volume=None,
                  file='2026, Congress, WRDA 2026 Senate bill S 4949 RS (not enacted).htm',
                  sha256='9935a3dc5bfe364ac1225cbeab0c70c3b539a105dba6757d4331b93579a78d6e',
                  cut=(6424, 11342),
                  part='S. 4949 as reported: the committee substitute, Division A only; not enacted'),
}
# Corrections to a source: {key: {source line: (as printed, as corrected, why)}}
CORRECTIONS = {
    '1996': {
        # a word broken over a page end with no hyphen in the source: the whole word goes on the first line
        853: ('is appro', 'is appropriate,',
              'a word broken over a page end (110 Stat. 3670-3671) with no hyphen in the source: "appro" / "priate,"; '
              'fixed 2026-11-14'),
        857: ('priate, may', 'may', 'the rest of the word broken over the page end, moved up to source line 853'),
        6561: ('hydropower tur', 'hydropower turbines,',
               'a word broken over a page end (110 Stat. 3761-3762) with no hyphen in the source: "tur" / "bines,"; '
               'fixed 2026-11-14'),
        6565: ('bines, including', 'including', 'the rest of the word broken over the page end, moved up to source line 6561'),
        7062: ('South Flor', 'South Florida',
               'a word broken over a page end (110 Stat. 3769-3770) with no hyphen in the source: "Flor" / "ida"; '
               'fixed 2026-11-14'),
        7066: ('ida ecosystem', 'ecosystem', 'the rest of the word broken over the page end, moved up to source line 7062'),
    },
}
# Oddities of an act as printed: {unit id: note}
NOTES = {}

FIRST = {4: 1, 12: 2, 20: 3, 26: 4, 28: 4, 36: 5, 44: 6, 48: 7, 52: 8}
CONT = {0: 1, 8: 2, 16: 3, 22: 4, 24: 4, 32: 5, 40: 6}      # 44 too, after a first line at 48
PAGE_RE = re.compile(r'^\[\[Page (?:(\d+) STAT\. )?(\d+)\]\]$')
NOTE_RE = re.compile(r'<<NOTE:.*?>>', re.S)
DASH_RE = re.compile(r'^-{20,}$')
ROW_RE = re.compile(r'^(\d+)\. ([A-Z]{2,4})\b')
SEC_RE = re.compile(r'^(SEC(?:\.|TION) (\d+[A-Za-z]?)\.) ?(.*)$')
TOC_RE = re.compile(r'^Sec\. (\d+[A-Za-z]?)\. ?(.*)$')
STRUCT_RE = re.compile(r'^(DIVISION|TITLE|Subtitle|SUBTITLE|PART|Part|CHAPTER|Chapter|Subchapter) '
                       r'([A-Z]{1,8}|\d+) ?-- ?(.*)$')
LEVELS = ['division', 'title', 'subtitle', 'part', 'chapter', 'subchapter']
END_RE = re.compile(r'^(Approved [A-Z][a-z]+ \d+, \d{4}\.|LEGISLATIVE HISTORY)')


class Line:
    def __init__(self, no, page, n, text, raw, blank, hard):
        self.no, self.page, self.n, self.text, self.raw = no, page, n, text, raw
        self.blank, self.hard = blank, hard         # any space above it; space that is not a page break


class P(T.Para):
    def __init__(self, ln, kind, depth, cont):
        super().__init__(ln.no, ln.page, kind, depth, ln.text)
        self.cont = cont

    def add(self, ln):
        self.text += ' ' + ln.text


def read_lines(path, cfg, key):
    """Lines of the WRDA with notes and page marks removed. Returns lines, note count, corrections."""
    raw = html.unescape(pathlib.Path(path).read_text(encoding='utf-8', errors='replace')).split('\n')
    a, z = cfg.get('cut', (1, len(raw)))
    fixes, done = CORRECTIONS.get(key, {}), []
    out, notes, page, k = [], 0, None, a - 1
    snapped = []
    for x in reversed(raw[:a - 1]):                      # the page the cut starts on
        m = PAGE_RE.match(x.strip())
        if m:
            page = int(m.group(2))
            break
    while k < z:
        no, s = k + 1, raw[k]
        while s.count('<<NOTE:') > s.count('>>') and k + 1 < z:       # a note that runs on to the next line
            k += 1
            s = s.rstrip() + ' ' + raw[k].strip()
        k += 1
        if no in fixes:
            was, now, why = fixes[no]
            assert s.count(was) == 1, f'line {no} does not read as expected: {s!r}'
            s = s.replace(was, now)
            done.append({'source_line': no, 'was': was, 'now': now, 'why': why})
        lead = len(s) - len(s.lstrip(' '))
        notes += len(NOTE_RE.findall(s))
        note_first = s.lstrip().startswith('<<NOTE:')
        s2 = NOTE_RE.sub(' ', s)
        text = re.sub(r' {2,}', ' ', s2).strip() if not DASH_RE.match(s2.strip()) else s2.strip()
        text = re.sub(r'^\((\w{1,6}) \)', r'(\1)', text)      # a note set inside a label: "(v <<NOTE: x>> ) any"
        m = PAGE_RE.match(text)
        if m:
            page = int(m.group(2))
            continue
        if not text:
            continue
        if note_first:                                   # "        <<NOTE: x>>     (1) Text": the note sits in the indent
            after_note = re.match(r'\s*(?:<<NOTE:.*?>>\s*)+', s, re.S).group()
            gap = len(after_note) - len(after_note.rstrip(' '))
            lead = lead + gap - 1
        keep_raw = re.sub(r'\s+$', '', NOTE_RE.sub('', s))
        out.append(Line(no, page, lead, text, keep_raw, False, False))
    assert len(done) == len(fixes), 'a correction names a line that is not in the input'
    return out, notes, done, snapped


def fix_page_blanks(lines, raw_path, cfg):
    """A blank line is 'hard' unless the only thing in the gap is a page mark."""
    raw = html.unescape(pathlib.Path(raw_path).read_text(encoding='utf-8', errors='replace')).split('\n')
    for prev, ln in zip(lines, lines[1:]):
        gap = [x.strip() for x in raw[prev.no:ln.no - 1]]
        has_page = any(PAGE_RE.match(NOTE_RE.sub('', x).strip()) for x in gap)
        blanks = any(not x for x in gap)
        ln.blank = blanks or has_page
        ln.hard = blanks and not has_page
    lines[0].blank = lines[0].hard = True


def table_end(lines, i):
    """Index after the last line of the table that opens at lines[i]."""
    j, rules = i + 1, 1
    while j < len(lines):
        if DASH_RE.match(lines[j].text):
            rules += 1
            nxt = lines[j + 1].text if j + 1 < len(lines) else ''
            if rules >= 2 and not (ROW_RE.match(nxt) or DASH_RE.match(nxt)):
                return j + 1
        j += 1
    return j


def table_rows(lines):
    """The numbered rows of a project table: number, State, name."""
    rows, cur = [], None
    for ln in lines:
        t = ln.raw
        m = ROW_RE.match(t.strip())
        if DASH_RE.match(t.strip()):
            cur = None
        elif m and not t.startswith('  '):
            f = [x for x in re.split(r'\s{2,}', t.strip()) if x]
            c1 = t.find(f[1]) if len(f) > 1 else None
            c2 = t.find(f[2], c1 + len(f[1])) if len(f) > 2 else len(t) + 40
            cur = {'number': m.group(1), 'state': m.group(2), 'name': f[1] if len(f) > 1 else '', 'cols': (c1, c2)}
            rows.append(cur)
        elif cur and cur['cols'][0] is not None:
            c1, c2 = cur['cols']
            piece = t[max(c1 - 2, 0):c2].strip()
            if piece and not re.match(r'^(Federal|Non-Federal|Total|Initial|Renourishment)\b', piece):
                cur['name'] += ' ' + piece
    for r in rows:
        r.pop('cols')
        r['name'] = re.sub(r'- ', '-', re.sub(r'\s+', ' ', r['name'])).strip()
    return rows


def blocks(lines, flags, log):
    out, cur, in_quote, i = [], None, False, 0

    def after(p):
        if p is None:
            return in_quote
        bal = p.text.count('``') - p.text.count("''")
        if in_quote and p.text.startswith('``'):
            bal -= 1                                   # each quoted paragraph reopens the quotation
        return (1 if in_quote else 0) + bal > 0

    def close():
        nonlocal cur, in_quote
        if cur is not None:
            cur.quoted = in_quote or cur.text.startswith('``')
            in_quote = after(cur)
            out.append(cur)
            cur = None

    while i < len(lines):
        ln, t = lines[i], lines[i].text
        quoting = after(cur)
        if DASH_RE.match(t):
            close()
            j = table_end(lines, i)
            out.append(('table', lines[i:j]))
            i = j
            continue
        toc_intro = cur is not None and not quoting and ln.blank and re.search(
            r'table of contents[^.]*(\.--|:)$', cur.text, re.I) and (TOC_RE.match(t) or STRUCT_RE.match(t))
        if toc_intro or (ln.n == 0 and TOC_RE.match(t) and not quoting and ln.blank):
            close()
            j = i
            while j < len(lines) and not (lines[j].n == 0 and SEC_RE.match(lines[j].text)):
                j += 1
            out.append(('toc', lines[i:j]))
            i = j
            continue
        m = SEC_RE.match(t) if ln.n == 0 else None
        if m:
            close()
            if in_quote:
                flags.append({'kind': 'QUOTATION LEFT OPEN', 'unit': f'before sec. {m.group(2)}', 'source_line': ln.no,
                              'what': 'a quotation was still open where this section starts; treated as closed'})
                in_quote = False
            head, j = m.group(3), i + 1
            while j < len(lines) and not lines[j].blank:
                head += ' ' + lines[j].text
                j += 1
            out.append(('section', m.group(1), m.group(2), head, ln))
            i = j
            continue
        m = STRUCT_RE.match(t)
        if m and ln.blank and (ln.hard or cur is None or ln.n != cur.cont) and not quoting:
            close()
            text, j = t, i + 1
            while j < len(lines) and not lines[j].blank and not SEC_RE.match(lines[j].text):
                text += ' ' + lines[j].text
                j += 1
            m = STRUCT_RE.match(text)
            out.append(('head', m.group(1).lower(), m.group(2), m.group(3), text, ln))
            i = j
            continue
        if cur is not None and not ln.hard:
            if ln.n == cur.cont or (cur.cont is None and not (ln.n in FIRST and (T.LABEL_RE.match(t) or t.startswith('``')))):
                cur.add(ln)
                i += 1
                continue
        close()
        if in_quote and not t.startswith('``') and ln.n in FIRST and T.LABEL_RE.match(t):
            flags.append({'kind': 'QUOTATION LEFT OPEN', 'unit': '', 'source_line': ln.no,
                          'what': f'a quotation was still open at an unquoted labelled paragraph; treated as closed: {t[:50]!r}'})
            in_quote = False
        if ln.n not in FIRST and ln.n not in CONT and ln.n - 1 in FIRST:
            ln.n -= 1                                  # a first line printed one space too far right
            log.append(f'line {ln.no}: first line printed one space too far right; read at its proper indent')
        if ln.n in FIRST:
            cur = P(ln, 'first', FIRST[ln.n], ln.n - 4)
        elif ln.n in CONT:
            cur = P(ln, 'flush', CONT[ln.n], ln.n)
        else:
            cur = P(ln, 'other', None, None)
        i += 1
    close()
    if in_quote:
        flags.append({'kind': 'QUOTATION LEFT OPEN', 'unit': 'end', 'source_line': lines[-1].no,
                      'what': 'a quotation was still open at the end'})
    return out


def toc_text(lines):
    out = []
    for ln in lines:
        if out and ln.n > 0 and not ln.blank and not STRUCT_RE.match(ln.text):
            out[-1] += ' ' + ln.text
        else:
            out.append(ln.text)
    return out


def build(key, raw_dir, out_dir, force=False):
    cfg = ACTS[key]
    path = pathlib.Path(raw_dir) / cfg['file']
    found = T.sha256(path)
    if found != cfg['sha256'] and not force:
        sys.exit(f"{cfg['file']} is not the pinned input.\n  expected {cfg['sha256']}\n  found    {found}")
    lines, n_notes, corrections, snapped = read_lines(path, cfg, key)
    fix_page_blanks(lines, path, cfg)
    # front matter | body | end matter
    a = next(i for i, ln in enumerate(lines) if ln.n == 0 and SEC_RE.match(ln.text)
             or (STRUCT_RE.match(ln.text) and 'cut' in cfg and cfg['cut'][0] > 1))
    z = next((i for i, ln in enumerate(lines) if END_RE.match(ln.text)
              or ('end_line' in cfg and ln.no >= cfg['end_line'])), len(lines))
    front, body, end = lines[:a], lines[a:z], lines[z:]
    want_lines = (list(front), body, end)

    flags, log = [], []
    if snapped:
        log.append(f'{len(snapped)} first lines printed one space too far right were read at their proper indent: source lines {snapped}')
    if 'toc' in cfg:                                      # the contents list sits outside the part used
        raw = html.unescape(path.read_text(encoding='utf-8', errors='replace')).split('\n')
        ext = []
        for x in raw[cfg['toc'][0] - 1:cfg['toc'][1]]:
            x = re.sub(r' {2,}', ' ', NOTE_RE.sub(' ', x)).strip()
            if TOC_RE.match(x) or STRUCT_RE.match(x) or not ext:
                ext.append(x)
            elif x and not PAGE_RE.match(x):
                ext[-1] += ' ' + x
    tree = T.Tree(key, flags, log)
    context, headings, pending, toc = {}, [], [], []
    cite = (lambda p: f"{cfg['volume']} Stat. {p}" if p else None) if cfg['volume'] else (lambda p: None)
    kinds_seen = {'other': 0, 'quoted': 0}
    for b in blocks(body, flags, log):
        if isinstance(b, P):
            b.page = cite(b.page)
            if not tree.sections:
                front.append(Line(b.no, None, 0, b.text, b.text, True, True))
                log.append(f'line {b.no}: text before the first section kept as front matter: {b.text[:50]!r}')
            elif b.quoted:
                kinds_seen['quoted'] += 1
                tree.keep(b.text, b.no, b.page)
            elif b.kind == 'first':
                labels, text = T.split_labels(b.text)
                if labels:
                    tree.labelled(b, labels, text, raw=b.text)
                else:
                    tree.unlabelled(b)
            elif b.kind == 'flush':
                m = T.LABEL_RE.match(b.text)
                ks = T.kinds(m.group(1)) if m else {}
                nxt = next((nd for nd in reversed(tree.stack) if nd.series in ks and ks[nd.series] == nd.last + 1
                            and nd.child_depth is not None), None)
                if m and (nxt is not None or 1 in ks.values()):
                    # a labelled paragraph printed at a later-line indent: the numbering says where it belongs
                    b.depth = nxt.child_depth if nxt is not None else (tree.top().depth or 0) + 1
                    flags.append({'kind': 'INDENT REPAIRED', 'unit': tree.top().id, 'source_line': b.no,
                                  'what': f'a labelled paragraph is printed at a later-line indent; placed by its label: {b.text[:50]!r}'})
                    labels, text = T.split_labels(b.text)
                    tree.labelled(b, labels, text, raw=b.text)
                else:
                    tree.flush(b)
            else:
                kinds_seen['other'] += 1
                log.append(f'line {b.no}: text at an indent no paragraph uses; kept with {tree.top().id}: {b.text[:50]!r}')
                tree.keep(b.text, b.no, b.page)
        elif b[0] == 'head':
            _, level, number, heading, text, ln = b
            for lv in LEVELS[LEVELS.index(level) + 1:]:
                context.pop(lv, None)
                context.pop(lv + '_heading', None)
            context[level], context[level + '_heading'] = number, heading
            h = {'level': level, 'number': number, 'heading': heading, 'text': text, 'source_line': ln.no,
                 'stat_page': cite(ln.page), 'before_section': None}
            headings.append(h)
            pending.append(h)
        elif b[0] == 'section':
            _, label, number, heading, ln = b
            if heading.endswith('.'):
                heading = heading[:-1]
            else:
                flags.append({'kind': 'HEADING WITHOUT PERIOD', 'unit': f'{key}.{number}', 'source_line': ln.no,
                              'what': f'section heading does not end in a period: {heading[:60]!r}'})
                heading = heading + '​'             # marks the missing period; see reading_order
            extra = {lv: context.get(lv) for lv in ('division', 'title', 'subtitle', 'part', 'chapter') if lv in context}
            extra.update({lv + '_heading': context[lv + '_heading'] for lv in list(extra)})
            if not b[3].endswith('.'):
                extra['heading_has_no_period'] = True
            node = tree.section(label, number, heading, ln.no, cite(ln.page), extra)
            for h in pending:
                h['before_section'] = node.id
            pending = []
        elif b[0] == 'toc':
            entries = toc_text(b[1])
            toc.append(entries)
            if tree.sections:
                tree.keep('\n'.join(entries), b[1][0].no, cite(b[1][0].page))
            else:
                front += b[1]
        elif b[0] == 'table':
            rows = table_rows(b[1])
            top = tree.top()
            top.put('\n'.join(ln.raw for ln in b[1]), b[1][0].no, cite(b[1][0].page))
            top.extra.setdefault('tables', []).append(rows)

    doc = {
        'schema': 'wrda-structure/1',
        'act': cfg['name'], 'public_law': cfg['public_law'], 'enacted': cfg['enacted'],
        'part_of_source_used': cfg.get('part', 'the whole act'),
        'source': {'text': {'file': cfg['file'], 'sha256': found,
                            'lines': list(cfg['cut']) if 'cut' in cfg else 'all'},
                   'builder': pathlib.Path(__file__).name, 'builder_version': BUILDER_VERSION},
        'counts': {}, 'corrections': corrections, 'margin_notes_removed': n_notes,
        'front_matter': [ln.text for ln in front],
        'headings': headings,
        'sections': [T.to_dict(s, NOTES) for s in tree.sections],
        'end_matter': [ln.text for ln in end],
        'flags': flags,
    }
    doc['counts'] = T.count_units(doc)
    doc['counts']['table_rows'] = sum(len(r) for sec in doc['sections'] for d in T.walk(sec) for r in d.get('tables', []))
    doc['counts']['quoted_paragraphs'] = kinds_seen['quoted']

    # ---- checks
    front0, body, end = want_lines
    want = ''.join(ln.text for ln in front0) + ''.join(
        (ln.raw if DASH_RE.match(ln.text) else ln.text) for ln in body) + ''.join(ln.text for ln in end)
    checks = []
    n_chars = T.check_lossless(doc, want)
    checks.append(f'PASS  lossless: all {n_chars} non-space characters of the source are in the file, in order')
    pages = [int(d['stat_page'].split()[-1]) for sec in doc['sections'] for d in T.walk(sec) if d['stat_page']]
    checks.append(('PASS' if pages == sorted(pages) else 'FAIL') + '  print pages rise with reading order')
    nums = [int(re.match(r'\d+', s['number']).group()) for s in doc['sections']]
    bad = [doc['sections'][i + 1]['id'] for i, (x, y) in enumerate(zip(nums, nums[1:])) if y <= x]
    checks.append(('PASS' if not bad else 'FAIL') + f'  section numbers rise through the act' + (f': not at {bad}' if bad else ''))
    for x in bad:
        flags.append({'kind': 'SECTION NUMBER OUT OF ORDER', 'unit': x, 'source_line': '', 'what': 'number does not rise'})
    if 'toc' in cfg:
        toc = [ext]
    if toc:
        listed = [(m.group(1), m.group(2)) for e in toc[0] for m in [TOC_RE.match(e)] if m]
        norm = lambda s: re.sub(r'[^a-z0-9]', '', s.lower())
        have = [(s['number'], s['heading']) for s in doc['sections']]
        if 'cut' in cfg:
            nums_have = {n for n, _ in have}
            listed = [x for x in listed if x[0] in nums_have]
        diff_n = [x[0] for x in listed] != [x[0] for x in have]
        checks.append(('FAIL' if diff_n else 'PASS') + f'  the {len(have)} sections are the {len(listed)} entries of the contents list, in order')
        if diff_n:
            flags.append({'kind': 'CONTENTS LIST MISMATCH', 'unit': key, 'source_line': '',
                          'what': f'in contents but not found: {[x[0] for x in listed if x[0] not in {h[0] for h in have}]}; '
                                  f'found but not in contents: {[h[0] for h in have if h[0] not in {x[0] for x in listed}]}'})
        lh = dict(listed)
        n_diff = 0
        for n, h in have:
            if n in lh and norm(lh[n]) != norm(h):
                n_diff += 1
                flags.append({'kind': 'HEADING DIFFERS FROM CONTENTS', 'unit': f'{key}.{n}', 'source_line': '',
                              'what': f'section heading {h!r}; contents list {lh[n]!r}'})
        checks.append(f'{"PASS" if not n_diff else "NOTE"}  section headings read the same as the contents list'
                      + (f' except {n_diff} (flagged)' if n_diff else ''))
        if len(toc) > 1:
            flags.append({'kind': 'SECOND CONTENTS LIST', 'unit': key, 'source_line': '', 'what': f'{len(toc)} blocks read as contents lists'})
    else:
        checks.append('NOTE  this text has no contents list to check the sections against')
    doc['flags'] = flags

    head = [f"{cfg['name']} structure build (builder {BUILDER_VERSION})",
            f"input   {cfg['file']}", f'        sha256 {found}',
            f"        part used: {doc['part_of_source_used']}", '', 'checks'] + [f'  {c}' for c in checks] + ['']
    report = T.write_outputs(doc, out_dir, cfg['name'], head, log, flags)
    return doc, report, checks


if __name__ == '__main__':
    args = [x for x in sys.argv[1:] if x != '--force']
    if len(args) != 3 or (args[0] != 'all' and args[0] not in ACTS):
        sys.exit(__doc__)
    for key in (ACTS if args[0] == 'all' else [args[0]]):
        doc, report, checks = build(key, args[1], args[2], force='--force' in sys.argv)
        c = doc['counts']
        print(f"{doc['act']:22s} {c.get('sections', 0):4d} sections {c['units']:6d} units {c['table_rows']:4d} table rows "
              f"{len(doc['flags']):4d} flags   " + ('; '.join(x for x in checks if not x.startswith('PASS')) or 'all checks pass'))
