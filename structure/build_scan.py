#!/usr/bin/env python3
"""Build the structure file for a WRDA whose only source is a Statutes at
Large page scan (1988, 1990, 1992).

Usage: build_scan.py KEY TEXT_DIR OUT_DIR [--force]     (KEY: 1988 | 1990 | 1992 | all)
Input: the lines table made by extract_scan_lines.py (line, page, x0, text, x1).

A scan misreads characters. The layout does not lie, so the act is read from
the layout first and the characters second:

 1. Paragraphs. The act is set justified: every line of a paragraph runs to
    the right edge except its last. A line that stops short ends a paragraph.
    The indent of the next line gives its depth:
        1988, 1990   first lines at 10, 30, 50, 70 pt; later lines at 0, 20, 40, 60
        1992         first lines at 20, 40, 60, 80 pt; later lines 20 pt to their left
    Each page's left edge is refined so that its lines fall on that grid.
 2. Section headings are found by position: a line of capitals at the left
    edge that opens "SEC". They are numbered by their order, checked against
    the act's own table of contents, which lists every section in order. The
    number the scan read ("SEC 4I>.") is kept only as label_as_read.
 3. Labels are placed by sequence (wrda_tree.Tree). A damaged label that
    sits exactly where the next label of an open list belongs ("Ot))" after
    "(a)") is taken as that label; so is a look-alike ("(1)" for "(l)").
    A label that skips ahead is placed and flagged: something was missed.
 4. Quoted matter (text inserted into other laws) is kept whole.
 5. A word broken at a line end is joined again ("develop-" + "ment").
    The hyphen is kept before a capital ("non-" + "Federal") and after a few
    words that take one ("cost-", "right-", "of-").
 6. Wording. Section headings are compared with the contents list; where the
    two differ, the difference is flagged unless a correction is recorded in
    ACTS. Misreadings in ordinary text are left as the scan gives them.

Nothing stops the build except a lost character. Every repair and every
doubt is written to the build log and to "flags" in the structure file.
"""
import csv, difflib, pathlib, re, statistics, sys
import wrda_tree as T

BUILDER_VERSION = '2.4'
ACTS = {
    '1988': dict(name='WRDA 1988', public_law='100-676', enacted='1988-11-17', volume=102,
                 lines='1988, Congress, WRDA 1988 (PL 100-676).lines.tsv',
                 sha256='64a21437d93cecfe3a4155cf8787281fa761a5e4e1c85f4b1afe547f2ad936ce',
                 layout='hanging', titled=False, page_shift={},
                 headings={}),
    '1990': dict(name='WRDA 1990', public_law='101-640', enacted='1990-11-28', volume=104,
                 lines='1990, Congress, WRDA 1990 (PL 101-640).lines.tsv',
                 sha256='e895c34bfe5f8d5b68402386763bc437166ed9c8535650464a75dc1c692275bb',
                 layout='hanging', titled=True, page_shift={},
                 headings={}),
    '1992': dict(name='WRDA 1992', public_law='102-580', enacted='1992-10-31', volume=106,
                 lines='1992, Congress, WRDA 1992 (PL 102-580).lines.tsv',
                 sha256='f68bfdb4315379fd9886be4be0a34cd91f22d1a98e4dc9d37fe47c7a6e5e95ed',
                 layout='block', titled=True,
                 # page 4799: the contents list fills the page and is set 15 pt in; the trimmer
                 # measured the edge from it. The heading "SEC. 2." marks the true left edge.
                 page_shift={4799: 41.06},
                 headings={}),
}
# Section headings where the scan's heading and the act's contents list disagree. One of the two is
# always a plain misreading. HEADINGS: the heading was misread; the value is the corrected heading, or
# None to take the wording of the contents list (in capitals). CONTENTS_MISREAD: the contents entry
# was misread and the heading stands. A disagreement in neither list is flagged for a look.
# The 1988 entries were checked on the page images; the rest were settled by reading the two versions.
HEADINGS = {
    '1988': {12: None, 18: None, 39: None, 28: 'LAND CONVEYANCE, OTTAWA, ILLINOIS'},
    '1990': {111: None, 408: None},
    '1992': {2: None, 105: None, 108: None, 117: None, 202: None, 205: None, 225: None, 312: None, 313: None,
             314: None, 316: None, 317: None, 322: None, 325: None, 335: None, 341: None, 355: None, 356: None,
             357: None, 401: None, 503: None,
             226: 'DEBARMENT OF PERSONS CONVICTED OF FRAUDULENT USE OF "MADE IN AMERICA" LABELS',
             327: 'AVAILABILITY OF CONTAMINATED SEDIMENTS INFORMATION'},
}
# Corrections to a line of the scan's text: {key: {line: (as read, as corrected, why)}}. From builder 2.3 the
# misreadings approved by the author in a review table are kept beside this script in corrections_KEY.tsv
# (line, was, now, why; made by misreads_to_corrections.py) and are applied together with the ones below.
# Only where a misreading hides a heading; ordinary misread words are left alone, with two exceptions
# made on 2026-11-13 (builder 2.2), corrected on every line where they occur:
# "CAUFORNIA" for CALIFORNIA (15 lines, all in paragraph headings) and "^Ebccept" for "Except" (1 line).
_CA = 'the scan misreads CALIFORNIA'
CORRECTIONS = {
    '1988': {77: ('^Ebccept', 'Except', 'the scan misreads "Except" at the start of sec. 3(a)'),
             239: ('CAUFORNIA', 'CALIFORNIA', _CA)},
    '1990': {126: ('NOGALES WASH A N D TRIBUTARIES, A R I Z O N A . — T h e prOJect f o r',
                   'NOGALES WASH AND TRIBUTARIES, ARIZONA.—The project for',
                   'letter-spaced by the scan; the paragraph heading of sec. 101(a)(4) could not be read'),
             148: ('CAUFORNIA', 'CALIFORNIA', _CA), 435: ('CAUFORNIA', 'CALIFORNIA', _CA),
             441: ('CAUFORNIA', 'CALIFORNIA', _CA), 451: ('CAUFORNIA', 'CALIFORNIA', _CA),
             458: ('CAUFORNIA', 'CALIFORNIA', _CA), 912: ('CAUFORNiA', 'CALIFORNIA', _CA),
             915: ('CAUFORNIA', 'CALIFORNIA', _CA), 1135: ('CAUFORNIA', 'CALIFORNIA', _CA),
             1143: ('CAUFORNIA', 'CALIFORNIA', _CA), 1158: ('CAUFORNIA', 'CALIFORNIA', _CA)},
    '1992': {271: ('CAUFORNIA', 'CALIFORNIA', _CA), 276: ('CAUFORNIA', 'CALIFORNIA', _CA),
             451: ('CAUFORNIA', 'CALIFORNIA', _CA), 2074: ('CAUFORNIA', 'CALIFORNIA', _CA)},
    # 1992 line 3558 (the heading of sec. 355) has the same misreading but is left alone: that heading is
    # already taken from the contents list (HEADINGS), and heading_as_read must keep what the scan read.
}
CONTENTS_MISREAD = {
    '1988': {33, 36, 46, 54},
    '1990': {313, 403},
    '1992': {111, 112, 113, 203, 222, 302, 305, 308, 311, 331, 333, 339, 340, 347, 352},
}
NOTES = {}

SHORT = 8.0          # pt: a line ending this far short of the column width ends a paragraph
TOL = 3.6            # pt: how far a line may sit from its grid position
KEEP_HYPHEN = {'cost', 'right', 'of', 'acre', 'year', 'foot', 'mile', 'self', 'long', 'short', 'high', 'low',
               'non', 'well', 'one', 'two', 'three', 'four', 'five', 'six', 'ten'}
SEC_HEAD = re.compile(r'^(S\s?E\s?C(?:TION)?\s?\.?\s?[0-9A-Za-z>)(|!]{1,5}?\.)\s*(.*)$')
TOC_RE = re.compile(r'^Sec\.? ?([0-9A-Za-z>)(|!]{1,5})\.? (.*)$')
TITLE_RE = re.compile(r'^TITLE ([IVXL1l]+) ?-- ?(.*)$')
DAMAGED = re.compile(r'^(\(?\S{1,4}?[)>}\]]{1,2})(?= )')
ALIKE = str.maketrans('lIOoSsZzB', '110055228')
END_RE = re.compile(r'^Approved [A-Z][a-z]+ \d+, ?\d{4}\.?$')
SIGNATURE = re.compile(r'^\d\d-\d\d\d [0O] ?- ?\d')          # "59-194 0 - 93 - 10 : QL 3 (Pt. 6)" at a page foot
QUOTE_START = re.compile(r'^("|[^A-Za-z0-9(\s]{1,3}\((?=[0-9A-Za-z]{1,3}\)))')   # a quotation mark, or what the scan made of one
TERMINAL = re.compile(r'(?:[.;:]|--|; and|; or)["\')]*$')


def sec_head(t):
    """('SEC 4I>.', 'KISSIMMEE RIVER, FLORIDA.') for a section heading line, however the label was read."""
    m = re.match(r'^S\s?E\s?C(?:TION)?\s?\.?\s?', t)
    if not m:
        return None
    k = t.find('.', m.end() + 1)
    if k == -1 or k - m.end() > 12:
        k = t.find(' ', m.end() + 1)
        if k == -1:
            return None
    return t[:k + 1].strip(), t[k + 1:].strip()


def caps(t):
    a = re.sub(r'[^A-Za-z]', '', t)
    return len(a) >= 3 and sum(c.isupper() for c in a) / len(a) >= 0.85


class Line:
    def __init__(self, no, page, x0, text, x1):
        self.no, self.page, self.x0, self.text, self.x1 = no, page, x0, text, x1
        self.gap = False        # extra space above
        self.glue = False       # joins the line above with no space (a word broken at the line end)


class P(T.Para):
    def __init__(self, ln, kind, depth, cont):
        super().__init__(ln.no, ln.page, kind, depth, ln.text)
        self.cont, self.x0 = cont, ln.x0
        self.alt = None             # 1992: a paragraph with no label may be set flush, all lines at one indent

    def add(self, ln, sep=' '):
        self.text += ('' if ln.glue else sep) + ln.text


def read_lines(path, cfg, log):
    rows = list(csv.reader(open(path, encoding='utf-8', newline=''), delimiter='\t', quoting=csv.QUOTE_NONE))
    assert rows[0] == ['line', 'page', 'x0', 'text', 'x1'], 'not a scan lines table'
    lines, gap = [], True
    for no, page, x0, text, x1 in rows[1:]:
        if not text:
            gap = True
            continue
        if not re.search(r'[A-Za-z0-9]', text) or SIGNATURE.match(text):   # specks; printer's sheet mark
            log.append(f'line {no}: no letters or digits, dropped as scanner noise: {text!r}')
            continue
        ln = Line(int(no), int(page), float(x0), text, float(x1))
        ln.gap, gap = gap, False
        lines.append(ln)
    width = statistics.median(sorted(ln.x1 for ln in lines)[-len(lines) // 2:])
    grid = 10.0
    for page in sorted({ln.page for ln in lines}):               # refine each page's left edge
        here = [ln for ln in lines if ln.page == page]
        if page in cfg['page_shift']:
            d = cfg['page_shift'][page]
            log.append(f'page {page}: left edge moved {d:+.2f} pt (set by hand; see ACTS)')
        else:
            body = [ln.x0 for ln in here if not TOC_RE.match(ln.text) and not ln.text.startswith('TITLE')]
            score = lambda d: sum(1 for x in body if abs((x - d + grid / 2) % grid - grid / 2) <= 1.6)
            d = max((k / 4 for k in range(-12, 13)), key=lambda d: (score(d), -abs(d)))
            if abs(d) >= 1.5:
                log.append(f'page {page}: left edge moved {d:+.2f} pt so that the lines fall on the indent grid')
        for ln in here:
            ln.x0 -= d
            ln.x1 -= d
    return lines, width


def normalise(lines):
    """Dash forms, and words broken at a line end. Returns counts."""
    dashes = joined = 0
    for ln in lines:
        t = ln.text.replace('—^', '--').replace('—', '--').replace('“', '"').replace('”', '"')
        dashes += t != ln.text
        ln.text = t
    for a, b in zip(lines, lines[1:]):
        m = re.search(r'([A-Za-z]+)-$', a.text)
        if m and b.text[:1].isalpha() and not b.gap:
            b.glue = True
            if (b.text[0].islower() and m.group(1).lower() not in KEEP_HYPHEN) or (caps(a.text) and caps(b.text)
                                                                                    and len(m.group(1)) > 3):
                a.text = a.text[:-1]
                joined += 1
    return dashes, joined


def blocks(lines, cfg, width, flags, log):
    """Titles, section headings, the contents list and paragraphs, from layout."""
    block = cfg['layout'] == 'block'
    step = 20.0
    out, cur, in_quote, i, prev = [], None, False, 0, None
    held = 0                    # paragraphs kept as quoted matter since the open quotation began

    def after(p):
        if p is None:
            return in_quote
        odd = p.text.count('"') % 2 == 1
        if in_quote:
            return odd if p.text.startswith('"') else not odd
        return odd

    def close():
        nonlocal cur, in_quote, held
        if cur is not None:
            cur.quoted = in_quote or bool(QUOTE_START.match(cur.text))
            held = held + 1 if in_quote else 0
            in_quote = after(cur)
            out.append(cur)
            cur = None

    def place(x):
        """(kind, depth, later-line indent) for a paragraph starting at indent x."""
        if block:
            g = round(x / step)
            if abs(x - g * step) > TOL + 2:
                return 'other', None, None
            return ('flush', 1, 0.0) if g == 0 else ('start', g, (g - 1) * step)
        n = round(x / 10)
        if abs(x - n * 10) > TOL or n > 9:
            return 'other', None, None
        return ('first', (n + 1) // 2, (n - 1) * 10.0) if n % 2 else ('flush', n // 2 + 1, n * 10.0)

    while i < len(lines):
        ln, t = lines[i], lines[i].text
        short_before = prev is None or prev.x1 < width - SHORT or ln.page != prev.page and prev.x1 < width - SHORT
        quoting = after(cur)
        m = TITLE_RE.match(t)
        if m and caps(t) and not quoting and cfg['titled'] and (cur is None or short_before or ln.gap):
            close()
            text, j = t, i + 1
            while j < len(lines) and caps(lines[j].text) and not sec_head(lines[j].text) \
                    and not lines[j].text.startswith('"') and abs(lines[j].x0) > 6:
                text += ' ' + lines[j].text
                j += 1
            m = TITLE_RE.match(text)
            out.append(('title', m.group(1).replace('1', 'I').replace('l', 'I'), m.group(2), text, ln))
            prev, i = lines[j - 1], j
            prev = None
            continue
        m = sec_head(t)
        if m and abs(ln.x0) <= TOL and caps(t) and not t.startswith('"'):
            close()
            if in_quote:
                if held:
                    flags.append({'kind': 'QUOTATION LEFT OPEN', 'unit': '', 'source_line': ln.no,
                                  'what': f'a quotation mark is unpaired above this section heading; treated as closed '
                                          f'({held} paragraph(s) above it were kept as quoted matter)'})
                in_quote = False
            head, j = m[1], i + 1
            while j < len(lines) and lines[j].x0 > 25 and not lines[j].gap and lines[j - 1].x1 >= width - SHORT \
                    and not TITLE_RE.match(lines[j].text) and not T.LABEL_RE.match(lines[j].text):
                head += ('' if lines[j].glue else ' ') + lines[j].text
                j += 1
            out.append(('section', m[0], head, ln))
            prev, i = None, j
            continue
        if cur is not None and re.search(r'TABLE OF CONTENTS\.?--$', cur.text) and TOC_RE.match(t):
            close()
            j = i
            while j < len(lines) and not (sec_head(lines[j].text) and abs(lines[j].x0) <= TOL + 45
                                          and caps(lines[j].text) and not TOC_RE.match(lines[j].text)):
                j += 1
            out.append(('toc', lines[i:j]))
            prev, i = None, j
            continue
        kind, depth, cont = place(ln.x0)
        new = cur is None or short_before
        if not new:
            if cur.cont is None:                                   # carries on whatever the indent
                new = False
            elif abs(ln.x0 - cur.cont) <= TOL + 2 or (cur.alt is not None and abs(ln.x0 - cur.alt) <= TOL + 2):
                # same indent as the later lines: a new paragraph only if it opens with a label
                # and the line above ends a clause, or the label is followed by a heading in capitals
                lab = T.LABEL_RE.match(t) or DAMAGED.match(t)
                new = bool(block and lab and kind == 'start' and (
                    TERMINAL.search(prev.text) or prev.text.endswith(',') or re.match(r' [A-Z]{2}', t[lab.end():])))
                if not new and cur.alt is not None:
                    cur.cont, cur.alt = ln.x0, None
                if new:
                    log.append(f'line {ln.no}: the line above runs to the right edge, but this one opens with a label '
                               f'at a first-line indent; read as a new paragraph: {t[:40]!r}')
            elif kind == 'other' or ln.glue:
                new = False
            else:
                new = True
        if not new:
            cur.add(ln)
        else:
            close()
            if in_quote and not t.startswith('"') and kind in ('first', 'start') and T.LABEL_RE.match(t):
                msg = f'a quotation mark is unpaired above this unquoted labelled paragraph; treated as closed: {t[:40]!r}'
                if held:
                    flags.append({'kind': 'QUOTATION LEFT OPEN', 'unit': '', 'source_line': ln.no,
                                  'what': msg + f' ({held} paragraph(s) above it were kept as quoted matter)'})
                else:
                    log.append(f'line {ln.no}: {msg}')
                in_quote = False
            cur = P(ln, kind, depth, cont)
            if kind == 'start' and not T.LABEL_RE.match(t) and not DAMAGED.match(t):
                cur.alt = ln.x0
        prev = ln
        i += 1
    close()
    return out


def expected_numbers(n_sections, toc_entries, titled):
    """Section numbers by order: 1, 2, 3 ... and, in a titled act, 101, 102 ... after each title line."""
    nums, k, title = [], 0, 0
    for e in toc_entries:
        if e[0] == 'title':
            title += 1
            k = title * 100
        else:
            k += 1
            nums.append(k)
    return nums


def norm_head(s):
    return re.sub(r'[^A-Z0-9]', '', s.upper())


def fix_pattern(was):
    """The words to replace on a scan line, never as part of a longer word."""
    return re.compile(('(?<![A-Za-z])' if was[:1].isalpha() else '') + re.escape(was) + ('(?![A-Za-z])' if was[-1:].isalpha() else ''))


def all_corrections(key):
    """{line: [(as read, as corrected, why), ...]}: those listed in CORRECTIONS, then those in corrections_KEY.tsv."""
    out = {}
    for no, fix in CORRECTIONS.get(key, {}).items():
        out.setdefault(no, []).append(fix)
    path = pathlib.Path(__file__).with_name(f'corrections_{key}.tsv')
    if path.exists():
        rows = list(csv.reader(open(path, encoding='utf-8', newline=''), delimiter='\t', quoting=csv.QUOTE_NONE))
        assert rows[0] == ['line', 'was', 'now', 'why'], 'not a corrections table'
        for no, was, now, why in rows[1:]:
            out.setdefault(int(no), []).append((was, now, why))
    return out


def build(key, text_dir, out_dir, force=False):
    cfg = ACTS[key]
    path = pathlib.Path(text_dir) / cfg['lines']
    found = T.sha256(path)
    if found != cfg['sha256'] and not force:
        sys.exit(f"{cfg['lines']} is not the pinned input.\n  expected {cfg['sha256']}\n  found    {found}")
    flags, log = [], []
    lines, width = read_lines(path, cfg, log)
    corrections = []
    fixes = all_corrections(key)
    for ln in lines:
        for was, now, why in fixes.get(ln.no, ()):
            ln.text, n = fix_pattern(was).subn(lambda m: now, ln.text, count=1)   # one row, one place
            assert n, f'line {ln.no} does not read {was!r}: {ln.text!r}'
            corrections.append({'source_line': ln.no, 'was': was, 'now': now, 'why': why})
    assert len(corrections) == sum(map(len, fixes.values())), 'a correction names a line that is not in the input'
    kept, carry = [], False                        # a correction may empty a line (scanner noise): the line is dropped
    for ln in lines:
        if not ln.text.strip():
            carry = carry or ln.gap
            log.append(f'line {ln.no}: emptied by a correction, dropped')
            continue
        ln.gap, carry = ln.gap or carry, False
        kept.append(ln)
    lines = kept
    dashes, joined = normalise(lines)
    a = next(i for i, ln in enumerate(lines) if sec_head(ln.text) and caps(ln.text) and abs(ln.x0) <= TOL)
    z = next(i for i, ln in enumerate(lines) if END_RE.match(ln.text))
    front, body, end = lines[:a], lines[a:z], lines[z:]
    want = ''.join(ln.text for ln in lines)
    order = {}

    blks = blocks(body, cfg, width, flags, log)
    # ---- the contents list gives the section numbers
    toc_lines = next((b[1] for b in blks if not isinstance(b, P) and b[0] == 'toc'), [])
    toc_entries, toc_text = [], []
    for ln in toc_lines:
        t = ln.text
        m, mt = TOC_RE.match(t), TITLE_RE.match(t)
        if mt and caps(t):
            toc_entries.append(['title', mt.group(1), mt.group(2)])
            toc_text.append(t)
        elif m:
            toc_entries.append(['sec', m.group(1), m.group(2)])
            toc_text.append(t)
        elif toc_entries:
            toc_entries[-1][2] += ('' if ln.glue else ' ') + t
            toc_text[-1] += ('' if ln.glue else ' ') + t
        else:
            toc_text.append(t)
    numbers = expected_numbers(None, toc_entries, cfg['titled'])
    toc_secs = [e for e in toc_entries if e[0] == 'sec']
    for num, e in zip(numbers, toc_secs):
        read = e[1].translate(ALIKE)
        if read != str(num):
            log.append(f'contents list: entry read as "Sec. {e[1]}." is number {num} by its order')
    heads_found = [b for b in blks if not isinstance(b, P) and b[0] == 'section']
    n_heads = len(heads_found)
    # match each heading found to its contents entry: in order, but a heading may have been missed
    sim = lambda a, b: difflib.SequenceMatcher(None, norm_head(a), norm_head(b)).ratio()
    match, j = [], 0
    for b in heads_found:
        cand = [(sim(b[2], toc_secs[q][2]), -q, q) for q in range(j, min(j + 4, len(toc_secs)))]
        best = max(cand) if cand else None
        if best and best[0] >= 0.6:
            for q in range(j, best[2]):
                flags.append({'kind': 'SECTION NOT FOUND', 'unit': f'{key}.{numbers[q]}', 'source_line': '',
                              'what': f'the contents list has "Sec. {numbers[q]}. {toc_secs[q][2]}" but no heading was found for it'})
            match.append(best[2])
            j = best[2] + 1
        elif j < len(toc_secs):
            match.append(j)
            j += 1
        else:
            match.append(None)
    checks = []
    ok = n_heads == len(numbers)
    checks.append(('PASS' if ok else 'FAIL') + f'  {n_heads} section headings found by position; the contents list has {len(numbers)} entries')
    if not ok:
        flags.append({'kind': 'CONTENTS LIST MISMATCH', 'unit': key, 'source_line': '',
                      'what': f'{n_heads} headings found by position but {len(numbers)} entries in the contents list; '
                              'sections are numbered by order from the headings found'})

    tree = T.Tree(key, flags, log)
    title, headings, pending, k = None, [], [], 0
    cite = lambda p: f"{cfg['volume']} Stat. {p}"
    fixed = HEADINGS.get(key, {})
    repairs = 0
    n_title = 0
    for bi, b in enumerate(blks):
        if isinstance(b, P):
            b.page = cite(b.page)
            if b.quoted:
                tree.keep(b.text, b.no, b.page)
                continue
            if b.kind == 'other':
                log.append(f'line {b.no}: text at an indent no paragraph uses ({b.x0:.0f} pt); kept with {tree.top().id}: {b.text[:40]!r}')
                tree.keep(b.text, b.no, b.page)
                continue
            labels, text = T.split_labels(b.text)
            raw = b.text
            if b.kind == 'start':                                   # 1992: first line, or text resuming
                deeper = tree.at_depth(b.depth + 1)
                if not labels and not DAMAGED.match(b.text) and deeper is not None and deeper.children \
                        and deeper is not tree.stack[0]:
                    b.depth += 1
                    tree.flush(b)
                    continue
                b.kind = 'first'
            if b.kind == 'flush':
                m = T.LABEL_RE.match(b.text)
                ks = T.kinds(m.group(1)) if m else {}
                nxt = next((nd for nd in reversed(tree.stack) if nd.series in ks and ks[nd.series] == nd.last + 1
                            and nd.child_depth is not None), None)
                if m and nxt is not None:
                    b.depth = nxt.child_depth
                    flags.append({'kind': 'INDENT REPAIRED', 'unit': tree.top().id, 'source_line': b.no,
                                  'what': f'a labelled paragraph sits at a later-line indent; placed by its label: {b.text[:40]!r}'})
                    tree.labelled(b, labels, text, raw=raw)
                else:
                    tree.flush(b)
                continue
            open_list = next((nd for nd in reversed(tree.stack) if nd.series and nd.child_depth == b.depth), None)
            mx = re.match(r'^\(([0-9A-Za-z]{1,3})X([0-9A-Za-z]{1,3})\)', b.text)       # "(EXi)" for "(E)(i)"
            if not labels and mx and open_list is not None and mx.group(1) == T.label_at(open_list.series, open_list.last + 1) \
                    and 1 in T.kinds(mx.group(2)).values():
                b.text = f'({mx.group(1)})({mx.group(2)})' + b.text[mx.end():]
                labels, text = T.split_labels(b.text)
                repairs += 1
                flags.append({'kind': 'LABEL REPAIRED', 'unit': f'{open_list.id}.{mx.group(1)}', 'source_line': b.no,
                              'what': f'scan reads {mx.group()!r}; taken as ({mx.group(1)})({mx.group(2)})', 'as_read': mx.group(),
                              'run_in': f'{open_list.id}.{mx.group(1)}.{mx.group(2)}'})
            if not labels:
                m = DAMAGED.match(b.text)
                if m and open_list is None:                             # first label of a list: the next label says which
                    nxt_lab = next((T.split_labels(q.text)[0][0][0] for q in blks[bi + 1:] if isinstance(q, P)
                                    and not q.quoted and q.kind in ('first', 'start') and q.depth == b.depth
                                    and T.split_labels(q.text)[0]), None)
                    kind2 = [kd for kd, v in T.kinds(nxt_lab).items() if v == 2] if nxt_lab else []
                    if kind2:
                        want_lab = T.label_at(kind2[0], 1)
                        rest = b.text[m.end():]
                        b.text = f'({want_lab})' + rest
                        labels, text = T.split_labels(b.text)
                        repairs += 1
                        flags.append({'kind': 'LABEL REPAIRED', 'unit': f'{tree.above(b.depth).id}.{want_lab}', 'source_line': b.no,
                                      'what': f'scan reads {m.group(1)!r}; taken as ({want_lab}), the label before ({nxt_lab})',
                                      'as_read': m.group(1)})
                        m = None
                if labels:
                    pass
                elif m and open_list is not None:
                    want_lab = T.label_at(open_list.series, open_list.last + 1)
                    rest = b.text[m.end():]
                    labels, text = T.split_labels(f'({want_lab})' + rest)
                    b.text = f'({want_lab})' + rest
                    repairs += 1
                    flags.append({'kind': 'LABEL REPAIRED', 'unit': f'{open_list.id}.{want_lab}', 'source_line': b.no,
                                  'what': f'scan reads {m.group(1)!r}; taken as ({want_lab}), next after '
                                          f'{open_list.children[-1].label} in {open_list.id}', 'as_read': m.group(1)})
                elif m and not re.match(r'^\d+\)', b.text):
                    flags.append({'kind': 'DAMAGED LABEL, NO LIST', 'unit': tree.top().id, 'source_line': b.no,
                                  'what': f'paragraph opens with {m.group(1)!r}, which may be a misread label; kept as text'})
            elif open_list is None and 1 not in T.kinds(labels[0][0]).values():
                nxt_lab = next((T.split_labels(q.text)[0][0][0] for q in blks[bi + 1:] if isinstance(q, P)
                                and not q.quoted and q.kind in ('first', 'start') and q.depth == b.depth
                                and T.split_labels(q.text)[0]), None)
                kind2 = [kd for kd, v in T.kinds(nxt_lab).items() if v == 2] if nxt_lab else []
                if kind2:
                    lab, want_lab = labels[0][0], T.label_at(kind2[0], 1)
                    b.text = f'({want_lab})' + b.text[len(lab) + 2:]
                    labels = [(want_lab, labels[0][1])] + labels[1:]
                    repairs += 1
                    flags.append({'kind': 'LABEL REPAIRED', 'unit': f'{tree.above(b.depth).id}.{want_lab}', 'source_line': b.no,
                                  'what': f'scan reads ({lab}); taken as ({want_lab}), the label before ({nxt_lab})',
                                  'as_read': f'({lab})'})
            elif open_list is not None:
                lab = labels[0][0]
                ks = T.kinds(lab)
                fits = any(nd.series in ks and ks[nd.series] == nd.last + 1 and nd.child_depth == b.depth
                           for nd in tree.stack)
                want_lab = T.label_at(open_list.series, open_list.last + 1)
                alike = lab != want_lab and lab.translate(ALIKE) == want_lab.translate(ALIKE)
                if alike and (fits or 1 in ks.values()):
                    # "(1)" where "(l)" is due could also be a real "(1)": the next label at this depth decides
                    after2 = T.label_at(open_list.series, open_list.last + 2)
                    nxt_lab = next((T.split_labels(q.text)[0][0][0] for q in blks[bi + 1:] if isinstance(q, P)
                                    and not q.quoted and q.kind in ('first', 'start') and q.depth == b.depth
                                    and T.split_labels(q.text)[0]), None)
                    alike = nxt_lab is not None and nxt_lab.translate(ALIKE) == after2.translate(ALIKE) and nxt_lab != '2'
                    fits = not alike
                if not fits and alike:
                    b.text = f'({want_lab})' + b.text[len(lab) + 2:]
                    labels = [(want_lab, labels[0][1])] + labels[1:]
                    repairs += 1
                    flags.append({'kind': 'LABEL REPAIRED', 'unit': f'{open_list.id}.{want_lab}', 'source_line': b.no,
                                  'what': f'scan reads ({lab}); taken as ({want_lab}), next after '
                                          f'{open_list.children[-1].label} in {open_list.id}', 'as_read': f'({lab})'})
            if labels:
                tree.labelled(b, labels, text, raw=b.text)
            else:
                at = tree.at_depth(b.depth)
                if open_list is not None and at is not None and at.label and at is not tree.stack[0]:
                    log.append(f'line {b.no}: paragraph with no label at the indent of the list in {open_list.id}; '
                               f'kept as a further paragraph of {at.id}: {b.text[:40]!r}')
                tree.unlabelled(b)
        elif b[0] == 'title':
            _, number, heading, text, ln = b
            n_title += 1
            title = (number, heading)
            h = {'level': 'title', 'number': number, 'heading': heading, 'text': text, 'source_line': ln.no,
                 'stat_page': cite(ln.page), 'before_section': None}
            headings.append(h)
            pending.append(h)
        elif b[0] == 'section':
            _, label_read, head, ln = b
            q = match[k]
            k += 1
            number = numbers[q] if q is not None else int(tree.sections[-1].extra['number']) + 1
            entry = toc_secs[q][2] if q is not None else None
            extra = {'title': title[0] if title else None, 'title_heading': title[1] if title else None}
            period = head.endswith('.')
            heading = head[:-1] if period else head
            if not period:
                extra['heading_has_no_period'] = True
            want_label = 'SECTION 1.' if number == 1 else f'SEC. {number}.'
            if re.sub(r'\s', '', label_read) != re.sub(r'\s', '', want_label):
                extra['label_as_read'] = label_read
            if number in fixed:
                extra['heading_as_read'] = heading
                heading = fixed[number] or entry.rstrip('.').upper()
                log.append(f'sec. {number}: heading read as {extra["heading_as_read"]!r}; corrected to {heading!r}')
            elif entry is not None and norm_head(entry.rstrip('.')) != norm_head(heading) \
                    and number in CONTENTS_MISREAD.get(key, ()):
                log.append(f'sec. {number}: the contents list misreads this heading ({entry!r}); the heading stands')
            elif entry is not None and norm_head(entry.rstrip('.')) != norm_head(heading):
                flags.append({'kind': 'HEADING DIFFERS FROM CONTENTS', 'unit': f'{key}.{number}', 'source_line': ln.no,
                              'what': f'heading reads {heading!r}; contents list reads {entry!r}'})
            node = tree.section(want_label, str(number), heading, ln.no, cite(ln.page), extra)
            for h in pending:
                h['before_section'] = node.id
            pending = []
        elif b[0] == 'toc':
            tree.keep('\n'.join(toc_text), b[1][0].no, cite(b[1][0].page))

    doc = {
        'schema': 'wrda-structure/1',
        'act': cfg['name'], 'public_law': cfg['public_law'], 'enacted': cfg['enacted'],
        'citation': f"{cfg['volume']} Stat. {lines[0].page}",
        'source': {'text': {'lines_table': cfg['lines'], 'lines_table_sha256': found,
                            'kind': 'Statutes at Large page scan, GPO text layer'},
                   'builder': pathlib.Path(__file__).name, 'builder_version': BUILDER_VERSION},
        'counts': {}, 'corrections': corrections,
        'front_matter': [ln.text for ln in front],
        'headings': headings,
        'sections': [T.to_dict(s, NOTES) for s in tree.sections],
        'end_matter': [ln.text for ln in end],
        'flags': flags,
    }
    doc['counts'] = T.count_units(doc)
    doc['counts']['labels_repaired'] = repairs
    doc['counts']['words_rejoined_at_line_ends'] = joined

    # the lossless check runs against the file with repairs undone
    n_chars = lossless_scan(doc, want, flags, fixed)
    checks.insert(0, f'PASS  lossless: all {n_chars} non-space characters of the lines table are in the file, in order '
                     f'(after the recorded corrections and label and heading repairs)')
    pages = [int(d['stat_page'].split()[-1]) for sec in doc['sections'] for d in T.walk(sec) if d['stat_page']]
    checks.append(('PASS' if pages == sorted(pages) else 'FAIL') + '  print pages rise with reading order')
    if cfg['titled']:
        n_toc_titles = sum(1 for e in toc_entries if e[0] == 'title')
        checks.append(('PASS' if n_title == n_toc_titles else 'FAIL') + f'  {n_title} title lines in the body; {n_toc_titles} in the contents list')
    n_diff = sum(1 for f in flags if f['kind'] == 'HEADING DIFFERS FROM CONTENTS')
    checks.append(f'{"PASS" if not n_diff else "NOTE"}  section headings read the same as the contents list'
                  + (f' except {n_diff} (flagged)' if n_diff else '') + (f'; {len(fixed)} corrected by hand' if fixed else ''))
    head = [f"{cfg['name']} structure build (builder {BUILDER_VERSION})",
            f"input   {cfg['lines']}", f'        sha256 {found}', '', 'checks'] + [f'  {c}' for c in checks] + ['']
    report = T.write_outputs(doc, out_dir, cfg['name'], head, log, flags)
    return doc, report, checks


def lossless_scan(doc, want, flags, fixed):
    """Undo the recorded repairs in a copy of the text stream, then compare with the lines table."""
    parts = list(doc['front_matter'])
    heads = {}
    for h in doc['headings']:
        heads.setdefault(h['before_section'], []).append(h['text'])
    repaired = {f['unit']: f['as_read'] for f in flags if f['kind'] == 'LABEL REPAIRED'}
    repaired.update({f['run_in']: '' for f in flags if 'run_in' in f})

    def order(d):
        if d['type'] == 'section':
            parts.append(d.get('label_as_read', d['label']))
            parts.append(d.get('heading_as_read', d['heading']) + ('' if d.get('heading_has_no_period') else '.'))
        else:
            parts.append(repaired.get(d['id'], d['label'] or ''))
            if d['heading']:
                parts.append(d['heading'] + ('.--' if d['label'] else ''))
        parts.append(d['own_text'])
        for c in d.get('children', []):
            order(c)
        parts.append(d.get('trailing_text', ''))

    for sec in doc['sections']:
        parts += heads.get(sec['id'], [])
        order(sec)
    parts += doc['end_matter']
    got, want = T.squash(''.join(parts)), T.squash(want)
    if got != want:
        k = next((i for i, (x, y) in enumerate(zip(got, want)) if x != y), min(len(got), len(want)))
        sys.exit(f"LOSSLESS CHECK FAILED ({doc['act']}) at character {k}:\n  file : ...{got[max(0, k - 90):k + 90]}\n"
                 f'  input: ...{want[max(0, k - 90):k + 90]}')
    return len(want)


if __name__ == '__main__':
    args = [x for x in sys.argv[1:] if x != '--force']
    if len(args) != 3 or (args[0] != 'all' and args[0] not in ACTS):
        sys.exit(__doc__)
    for key in (ACTS if args[0] == 'all' else [args[0]]):
        doc, report, checks = build(key, args[1], args[2], force='--force' in sys.argv)
        c = doc['counts']
        print(f"{doc['act']:22s} {c.get('sections', 0):4d} sections {c['units']:6d} units {c['labels_repaired']:3d} labels repaired "
              f"{len(doc['flags']):4d} flags   " + ('; '.join(x for x in checks if not x.startswith('PASS')) or 'all checks pass'))
