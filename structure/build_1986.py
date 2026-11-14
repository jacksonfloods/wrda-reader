#!/usr/bin/env python3
"""Build the structure file for WRDA 1986 (Public Law 99-662).

Inputs (both pinned by SHA-256 below; the script refuses other files unless
--force is given):
  LINES.tsv      the lines table made by extract_lines.py from the corpus PDF
                 (line, page, x0, text). This is the text that is parsed.
  STATUTES.txt   `pdftotext -layout` of the Statutes at Large print
                 (100 Stat. 4082-4273). Used only to give each unit the page
                 it starts on in the official print.

Outputs, in OUT_DIR:
  WRDA 1986.structure.json   the act as a tree, one entry per section
  WRDA 1986.units.csv        the same units as a flat table, one row each
  WRDA 1986.build_log.txt    counts, hashes and every judgment call made

How the act is read
-------------------
The PDF prints every line at an exact indent. In units of one space
(3.125 pt from the 72 pt margin) the indents mean:

    2, 6, 10, 14   first line of a paragraph at depth 1, 2, 3, 4
    0, 4,  8, 12   a later line of a paragraph at depth 1, 2, 3, 4
    anything else  centred text (headings) or a table row

Centred text was centred on 79 columns, so a line of L characters sits at
indent (79 - L) // 2. That is the test for a heading.

Rules, in the order they are applied to each line:
 1. "TITLE IV--FLOOD CONTROL"  sets the title of the sections that follow.
 2. "SEC. 401. HEADING."       starts a section; a heading may run on to the
    next line. "Sec. 1001. (a) ..." (Titles X and XII) starts a section that
    has no heading and whose text begins on the same line.
 3. A centred line that is not a label and not quoted is a heading. It opens
    an unnumbered item under the unit that introduces the list. In section
    1002 the centred lines are State names; they open a group, and each
    paragraph under a State is an item.
 4. A first line starts a paragraph. Labels at its start -- "(a)", "(1)",
    "(A)", "(i)", alone or run together as in "(b)(1)" or
    "(a) Heading.--(1)" -- make it a labelled unit. A label continues the
    innermost open list that it is next in and that sits at its indent;
    otherwise a first label ("a", "1", "A", "i") opens a new list under the
    unit before it.
 5. A paragraph with no label belongs to the unit above it at the same depth.
    If no unit sits at that depth it is an unnumbered item of the unit above.
 6. Lines at a later-line indent that do not carry on the paragraph before
    them are flush text: the sentence of an outer unit resuming after its
    sub-units. They are stored as that unit's trailing_text.
 7. Quoted matter (text this act inserts into other laws) is never split
    into units. It stays in the text of the unit that inserts it. Every
    paragraph of quoted matter opens with a quotation mark, so an unquoted
    new paragraph ends a quotation that was left open.

Ids are built from the section down: 1986.401.a, 1986.401.e.3.B.iv. Units
with no printed label are numbered by position: items i01, i02 ...; groups
g01, g02 ... A number or label the act prints twice gets "-2nd".

Everything specific to this act is in the block of constants below. The
script stops if any character of the input is not accounted for in the output.
Corrections to the source text are listed in CORRECTIONS and recorded in the
output.

Usage: build_1986.py LINES.tsv STATUTES.txt OUT_DIR [--force]
"""
import bisect, csv, hashlib, json, pathlib, re, sys

# ---------------------------------------------------------------- this act
ACT, PUBLIC_LAW, ENACTED = 'WRDA 1986', '99-662', '1986-11-17'
PREFIX = '1986'
SOURCE_PDF = '1986, Congress, WRDA 1986 (PL 99-662).pdf'
SOURCE_PDF_SHA256 = 'f49cf269217e5e03b2abb2e4695f752f0d4aaaacd4d39685116c73bb316d7f36'
LINES_SHA256 = '0f602e98c51d786b0d193b7e8c011fd950d0211abd12f401176fe261e7a64653'
STATUTES_SHA256 = '0a986e9c5eda56c2d1e4e44a8a1ba9b6d02e3a2dd68098948986747ee4458a4d'
STAT_VOLUME, STAT_FIRST, STAT_LAST = 100, 4082, 4273
RUNNING_HEAD = re.compile(r'100 STAT\. \d{4}|PUBLIC LAW 99-662.{1,4}NOV\. 17, 1986')
BUILDER_VERSION = '1.0'

LEFT, SPACE, WIDTH = 72.0, 3.125, 79        # margin (pt), one space (pt), centring width (characters)
FIRST_SECTION = re.compile(r'^SECTION 1\.')
END_OF_ACT = re.compile(r'^Approved November 17, 1986\.$')
SECTIONS_EXPECTED = 309                     # 308 section numbers, one of them (805) used twice

# Sections whose centred headings are group names (States), not item names.
GROUPED = {'1002'}
# Sections that hold a boundary or land description. Its unlabelled paragraphs are part of the piece
# they describe, never unnumbered items of their own (the same rule as NO_ITEMS in wrda_tree.py; the
# list was read and agreed on 2026-11-15).
NO_ITEMS = {'1006', '1125', '1127'}
# Corrections made to the source text before it is parsed:
# line number: (text as printed, text as corrected, unit, reason).
CORRECTIONS = {
    8958: ('the Flood Control Act of 1966.', 'the Flood Control Act of 1966."', '1986.1107.b',
           'closing quotation mark added; the source PDF leaves the quotation open'),
}
# Oddities of the act as printed. Each was checked against the Statutes at Large.
NOTES = {
    '1986.204.e-2nd': 'Section 204 prints two subsections (e): "Reimbursement" and "Operation '
                      'and Maintenance" (so in the Statutes at Large, 100 Stat. 4100). This is '
                      'the second.',
    '1986.805-2nd': 'Printed as "SEC. 805." in Title XIV, between sections 1405 and 1406 '
                    '(so in the Statutes at Large, 100 Stat. 4272). Title VIII also has a '
                    'section 805, so this id ends in -2nd.',
    '1986.909.a': 'The source PDF prints "[TABLE GOES HERE]" in place of the table of river '
                  'basins. The table is supplied under "supplement" from the Statutes at Large.',
    '1986.1107.b': 'A closing quotation mark was added after "Flood Control Act of 1966." '
                   'The source PDF leaves the quotation open.',
    '1986.1117.b.2.3': 'Printed "(3)" but set as the third item of paragraph (2), after (A) and (B) '
                       '(so in the Statutes at Large, 100 Stat. 4236). Probably meant "(C)".',
}
# Text the source PDF leaves out, copied from the Statutes at Large and checked
# against the page image.
SUPPLEMENTS = {
    '1986.909.a': {
        'replaces': '[TABLE GOES HERE]',
        'source': '100 Stat. 4188',
        'columns': ['Basin', 'Act of Congress'],
        'rows': [
            ['Alabama-Coosa River Basin', 'March 2, 1945'],
            ['Arkansas River Basin', 'June 28, 1938'],
            ['Arkansas-Red River Basin', 'November 7, 1966'],
            ['Baltimore Harbor', 'December 31, 1970'],
            ['Blue River Basin', 'December 31, 1970'],
            ['Brazos River Basin', 'September 3, 1954'],
            ['Central and Southern Florida', 'June 30, 1948'],
            ['Columbia River Basin', 'May 17, 1950'],
            ['Connecticut River Basin', 'June 22, 1936'],
            ['Cottonwood Creek, California', 'December 31, 1970'],
            ['Gulf Intracoastal Waterway, St. Marks, Tampa', 'August 13, 1968'],
            ['Mississippi River and Tributaries', 'May 15, 1928'],
            ['Missouri River Basin', 'June 28, 1938'],
            ['North Branch Susquehanna River Basin', 'July 3, 1958'],
            ['Ohio River Basin', 'June 22, 1936'],
            ['Ouachita River Basin', 'May 17, 1950'],
            ['Red Run Drain and Lower Clinton River', 'December 31, 1970'],
            ['Red River Waterway', 'August 13, 1968'],
            ['Sabine River Basin', 'December 31, 1970'],
            ['Sacramento River Basin', 'December 22, 1944'],
            ['San Joaquin River Basin', 'December 22, 1944'],
            ['Santa Ana River Basin', 'June 22, 1936'],
            ['South Platte River Basin', 'May 17, 1950'],
            ['Tampa Harbor', 'December 31, 1970'],
            ['Trinity River Basin', 'October 27, 1965'],
            ['Upper Mississippi River Basin', 'June 28, 1938'],
            ['Wabash River Basin', 'August 13, 1968'],
            ['White River Basin', 'June 28, 1938'],
        ],
    },
}

# ---------------------------------------------------------------- patterns
TITLE_RE = re.compile(r'^TITLE ([IVXL]+)--(.+)$')
SEC_RE = re.compile(r'^(SEC(?:TION)?\.? (\d+)\.) (.+)$')      # SEC. 401. AUTHORIZATION OF PROJECTS.
RUNIN_RE = re.compile(r'^(Sec\. (\d+)\.) (.+)$')              # Sec. 1001. (a) Any project ...
LABEL_RE = re.compile(r'\((\d{1,2}|[a-z]{1,2}|[A-Z]{1,2}|[ivx]{1,5}|[IVX]{1,5})\)')
HEAD_RE = re.compile(r' ([A-Za-z][^"]{0,160}?)\.--')          # "(a) Heading.--"; this source lower-cases some
TOC_RE = re.compile(r'^Title [IVXL]+--')                      # entries of the contents list in sec. 1(b)
SENTENCE_END = re.compile(r'(?:[.:;?!]|--)["\')]*$')
TOKEN = re.compile(r'[a-z0-9]+')
KIND_TYPE = {'lower': 'subsection', 'digit': 'paragraph', 'upper': 'subparagraph',
             'roman': 'clause', 'ROMAN': 'subclause'}
ROMAN = {s: i + 1 for i, s in enumerate(
    'i ii iii iv v vi vii viii ix x xi xii xiii xiv xv xvi xvii xviii xix xx'.split())}


def is_first(n): return n % 4 == 2 and n <= 14
def is_later(n): return n % 4 == 0 and n <= 12
def depth_of(n): return (n + 2) // 4 if is_first(n) else n // 4 + 1


def kinds(lab):
    """The kinds of list a label can belong to, with its position in each."""
    out = {}
    if lab.isdigit():
        out['digit'] = int(lab)
    elif lab.lower() in ROMAN:
        out['roman' if lab.islower() else 'ROMAN'] = ROMAN[lab.lower()]
    if lab.isalpha() and len(set(lab)) == 1:                      # a..z, aa..zz
        out['lower' if lab.islower() else 'upper'] = (ord(lab[0].lower()) - 96) + 26 * (len(lab) - 1)
    return out


class Line:
    def __init__(self, no, page, x0, text, blank_before):
        self.no, self.page, self.text, self.blank_before = no, page, text, blank_before
        self.n = round((x0 - LEFT) / SPACE)


class Para:
    """A paragraph: a first line and the lines that carry it on."""
    def __init__(self, line, kind, depth, text=None):
        self.no, self.page, self.kind, self.depth = line.no, line.page, kind, depth
        self.text = line.text if text is None else text
        self.last = self.text
        self.quoted = False

    def add(self, line, table_row=False):
        self.text += ('\n' if table_row else ' ') + line.text
        self.last = line.text


class Node:
    def __init__(self, id, type, label, heading, depth, line, page, parent, loose=False):
        self.id, self.type, self.label, self.heading = id, type, label, heading
        self.depth, self.line, self.page, self.parent = depth, line, page, parent
        self.loose = loose              # an unnumbered item that is just a paragraph
        self.also = set()               # depths of the unlabelled paragraphs of a description this unit took in
        self.own, self.children, self.trailing = [], [], []
        self.series, self.last, self.child_depth = None, 0, None
        self.extra = {}

    def put(self, text):
        (self.trailing if self.children else self.own).append(text)


def read_lines(path):
    rows = list(csv.reader(open(path, encoding='utf-8', newline=''), delimiter='\t', quoting=csv.QUOTE_NONE))
    assert rows[0] == ['line', 'page', 'x0', 'text'], 'not a lines table'
    lines, blank = [], True
    for no, page, x0, text in rows[1:]:
        if not text:
            blank = True
            continue
        lines.append(Line(int(no), int(page), float(x0), text, blank))
        blank = False
    return lines


def correct(lines):
    """Apply CORRECTIONS to the lines; return a record of each."""
    done = []
    for ln in lines:
        if ln.no in CORRECTIONS:
            was, now, unit, why = CORRECTIONS[ln.no]
            assert ln.text.count(was) == 1, f'line {ln.no} does not read as expected: {ln.text!r}'
            ln.text = ln.text.replace(was, now)
            done.append({'source_line': ln.no, 'unit': unit, 'was': was, 'now': now, 'why': why})
    assert len(done) == len(CORRECTIONS), 'a correction names a line that is not in the input'
    return done


def split_act(lines):
    """Front matter, body (section 1 to the last section) and end matter."""
    a = next(i for i, ln in enumerate(lines) if FIRST_SECTION.match(ln.text))
    z = next(i for i, ln in enumerate(lines) if END_OF_ACT.match(ln.text))
    return lines[:a], lines[a:z], lines[z:]


# ---------------------------------------------------------------- lines -> blocks
def centred(line):
    core = re.sub(r'\s*_$', '', line.text)        # "_" marks a heading that runs on
    return line.n == (WIDTH - len(core)) // 2


def is_heading(lines, k, cur):
    ln, t = lines[k], lines[k].text
    nxt = lines[k + 1] if k + 1 < len(lines) else None
    if not centred(ln) or t[0] in '("':
        return False
    if ln.n > 14 or ln.n % 2:                     # an indent no body line uses
        return True
    # A long name can land on a body indent. It is a heading only if it stands
    # alone: no sentence punctuation, not carrying on the line above, and not
    # carried on by the line below.
    if not t[0].isupper() or re.search(r'[.,;:-]$', t):
        return False
    if is_first(ln.n):
        return not (nxt and nxt.n == ln.n - 2 and not nxt.blank_before)
    above = cur is not None and cur.depth == depth_of(ln.n) and not ln.blank_before
    below = nxt is not None and nxt.n == ln.n and not nxt.blank_before
    return not above and not below


def carries_on(cur, ln):
    """Does line `ln` belong to paragraph `cur`?"""
    if cur is None or is_first(ln.n) or TOC_RE.match(ln.text):
        return False
    if not is_later(ln.n):                        # table row
        return not ln.blank_before
    if cur.depth != depth_of(ln.n):
        return False
    # A blank line inside a sentence is a page-layout gap, not a break.
    return not ln.blank_before or not SENTENCE_END.search(cur.last)


def blocks(lines, log):
    """Turn body lines into titles, section heads, headings and paragraphs."""
    out, cur, in_quote, opened, k = [], None, False, None, 0

    def quote_after(p):
        """Is a quotation open once paragraph `p` ends?"""
        if p is None:
            return in_quote
        odd = p.text.count('"') % 2 == 1
        if in_quote:                              # inside quoted matter
            return odd if p.text.startswith('"') else not odd
        return odd

    def close():
        nonlocal cur, in_quote, opened
        if cur is not None:
            cur.quoted = in_quote or cur.text.startswith('"')
            was, in_quote = in_quote, quote_after(cur)
            if in_quote and not was:
                opened = cur.no
            out.append(cur)
            cur = None

    while k < len(lines):
        ln, t = lines[k], lines[k].text
        structural = TITLE_RE.match(t) or SEC_RE.match(t) or RUNIN_RE.match(t)
        quoting = quote_after(cur)
        heading = not structural and not quoting and is_heading(lines, k, cur)
        if not structural and not heading and carries_on(cur, ln):
            cur.add(ln, table_row=not is_later(ln.n))
            k += 1
            continue
        close()
        if in_quote and not t.startswith('"') and (structural or is_first(ln.n)):
            log.append(f'line {ln.no}: the quotation opened in the paragraph at line {opened} has no '
                       f'closing mark; treated as ended before this line')
            in_quote = False
        m = TITLE_RE.match(t)
        if m:
            out.append(('title', m.group(1), m.group(2), ln))
        elif SEC_RE.match(t):
            m = SEC_RE.match(t)
            head = m.group(3)
            while not head.endswith('.'):         # heading runs on to the next line
                k += 1
                head += ' ' + lines[k].text
            out.append(('section', m.group(1), m.group(2), head[:-1], ln))
        elif RUNIN_RE.match(t):
            m = RUNIN_RE.match(t)
            out.append(('section', m.group(1), m.group(2), None, ln))
            cur = Para(ln, 'first', 1, text=m.group(3))
        elif heading:
            head = re.sub(r'\s*_$', '', t)
            while lines[k].text.endswith('_'):    # two-line heading
                k += 1
                head += ' ' + re.sub(r'\s*_$', '', lines[k].text)
            out.append(('heading', head, ln))
        elif is_first(ln.n):
            cur = Para(ln, 'first', depth_of(ln.n))
        elif is_later(ln.n):
            cur = Para(ln, 'flush', depth_of(ln.n))
        else:
            cur = Para(ln, 'other', None)
        k += 1
    close()
    if in_quote:
        log.append('a quotation was still open at the end of the act')
    return out


def split_labels(text):
    """'(a) Heading.--(1) Text' -> [('a', 'Heading'), ('1', None)], 'Text'"""
    labels, pos = [], 0
    while True:
        m = LABEL_RE.match(text, pos)
        if not m:
            break
        pos, head = m.end(), None
        h = HEAD_RE.match(text, pos)
        if h:
            head, pos = h.group(1), h.end()
        labels.append((m.group(1), head))
        if head is None and not LABEL_RE.match(text, pos):
            break
    return labels, text[pos:].strip()


# ---------------------------------------------------------------- blocks -> tree
class Builder:
    def __init__(self, log):
        self.sections, self.titles, self.stack, self.log = [], [], [], log
        self.title = None
        self.ids = set()

    def new(self, parent, suffix, **kw):
        node = Node(f'{parent.id}.{suffix}', parent=parent, **kw)
        assert node.id not in self.ids, f'duplicate id {node.id}'
        self.ids.add(node.id)
        self.pop_to(parent)
        parent.children.append(node)
        self.stack.append(node)
        return node

    def pop_to(self, node):
        while self.stack[-1] is not node:
            self.stack.pop()

    def at_depth(self, depth):
        for node in reversed(self.stack):
            if node.depth == depth or depth in node.also:
                return node

    def unnumbered(self, parent, prefix, **kw):
        k = sum(1 for c in parent.children if c.type == kw['type']) + 1
        return self.new(parent, f'{prefix}{k:02d}', label=None, **kw)

    # -- one handler per kind of block
    def title_line(self, number, heading, ln):
        self.title = (number, heading)
        self.titles.append({'number': number, 'heading': heading, 'source_line': ln.no})

    def section(self, label, number, heading, ln):
        sid = f'{PREFIX}.{number}'
        if sid in self.ids:
            sid += '-2nd'
            self.log.append(f'line {ln.no}: section number {number} is printed a second time; id {sid}')
        node = Node(sid, 'section', label, heading, 1, ln.no, ln.page, None)
        assert node.id not in self.ids, f'duplicate section {node.id} at line {ln.no}'
        self.ids.add(node.id)
        node.extra = {'number': number, 'title': self.title[0] if self.title else None,
                      'title_heading': self.title[1] if self.title else None}
        self.sections.append(node)
        self.stack = [node]

    def heading(self, text, ln):
        sec = self.stack[0]
        if sec.extra['number'] in GROUPED:
            self.unnumbered(sec, 'g', type='group', heading=text, depth=0, line=ln.no, page=ln.page)
            return
        parent = self.stack[-1]
        for node in reversed(self.stack):         # close the item before this one
            if node.type == 'item' and not node.loose:
                parent = node.parent
                break
        self.unnumbered(parent, 'i', type='item', heading=text, depth=None, line=ln.no, page=ln.page)

    def labelled(self, p, labels, text):
        if self.stack[-1].type == 'item' and self.stack[-1].depth is None:
            self.stack[-1].depth = p.depth        # an item whose body starts with a label
        for j, (lab, head) in enumerate(labels):
            ks = kinds(lab)
            pick, suffix, pos = None, lab, None
            if j == 0:                            # next in an open list at this indent
                for node in reversed(self.stack):
                    if node.series in ks and ks[node.series] == node.last + 1 and node.child_depth == p.depth:
                        pick = (node, node.series)
                        break
            if pick is None:                      # first of a new list
                for kind, k in ks.items():
                    if k == 1:
                        pick = (self.stack[-1], kind)
            if pick is None:                      # the act repeats the label before it
                for node in reversed(self.stack):
                    if node.series in ks and ks[node.series] == node.last and node.child_depth == p.depth:
                        pick, suffix, pos = (node, node.series), lab + '-2nd', node.last
                        self.log.append(f'line {p.no}: label ({lab}) is printed a second time in {node.id}; '
                                        f'id {node.id}.{suffix}')
                        break
            if pick is None:                      # the label belongs to no list: keep it where it is printed
                for node in reversed(self.stack):
                    if node.series and node.child_depth == p.depth:
                        pick, pos = (node, node.series), node.last + 1
                        self.log.append(f'line {p.no}: label ({lab}) does not fit the list it is printed in '
                                        f'({node.children[-1].label} comes before it); kept there as '
                                        f'{node.id}.{lab}')
                        break
                else:
                    sys.exit(f'line {p.no}: label ({lab}) fits no open list: {p.text[:60]!r}')
            parent, kind = pick
            if parent.series not in (None, kind):
                self.log.append(f'line {p.no}: {parent.id} has a second list, starting at ({lab})')
            node = self.new(parent, suffix, type=KIND_TYPE[kind], label=f'({lab})', heading=head,
                            depth=p.depth, line=p.no, page=p.page)
            parent.series, parent.child_depth = kind, p.depth
            parent.last = ks[kind] if pos is None else pos
        if text:
            node.own.append(text)

    def unlabelled(self, p):
        top = self.stack[-1]
        if top.type == 'item' and top.depth is None:      # body of the item a heading opened
            top.depth = p.depth
            top.own.append(p.text)
            return
        node = self.at_depth(p.depth)
        if node is not None and not node.loose:           # a further paragraph of that unit
            self.pop_to(node)
            node.put(p.text)
            return
        if self.stack[0].extra['number'] in NO_ITEMS:     # a boundary description: text of the piece it
            parent = next(x for x in reversed(self.stack) if x.depth is not None and x.depth < p.depth)
            self.pop_to(parent)                           # describes, and so is all that follows at this indent
            if p.depth not in parent.also:
                self.log.append(f'line {p.no}: the description that starts here is kept as text of {parent.id}')
            parent.also.add(p.depth)
            parent.put(p.text)
            return
        if node is not None:                              # next in a run of unnumbered paragraphs
            parent = node.parent
        else:
            parent = next(x for x in reversed(self.stack) if x.depth is not None and x.depth < p.depth)
        item = self.unnumbered(parent, 'i', type='item', heading=None, depth=p.depth,
                               line=p.no, page=p.page, loose=True)
        item.own.append(p.text)

    def flush(self, p):
        node = self.at_depth(p.depth) if p.depth else None
        if node is None:
            node = self.stack[-1]
            self.log.append(f'line {p.no}: text at depth {p.depth} has no unit at that depth; '
                            f'kept with {node.id}: {p.text[:50]!r}')
        self.pop_to(node)
        node.put(p.text)

    def paragraph(self, p):
        if p.quoted:                                      # rule 7
            self.stack[-1].put(p.text)
        elif p.kind == 'first':
            labels, text = split_labels(p.text)
            if labels:
                self.labelled(p, labels, text)
            else:
                self.unlabelled(p)
        else:
            self.flush(p)

    def run(self, blks):
        for b in blks:
            if isinstance(b, Para):
                self.paragraph(b)
            elif b[0] == 'title':
                self.title_line(*b[1:])
            elif b[0] == 'section':
                self.section(*b[1:])
            else:
                self.heading(*b[1:])


# ---------------------------------------------------------------- pages of the official print
def tokens(text):
    return TOKEN.findall(text.lower())


def print_tokens(path):
    """Words of the Statutes at Large print, each with the page it is on."""
    pages = pathlib.Path(path).read_text(encoding='utf-8', errors='replace').split('\f')
    while pages and not pages[-1].strip():
        pages.pop()
    assert len(pages) == STAT_LAST - STAT_FIRST + 1, f'{len(pages)} pages in the print text'
    words, page_of = [], []
    for k, text in enumerate(pages):
        m = re.search(r'100 STAT\. (\d{4})', text)
        assert m is None or int(m.group(1)) == STAT_FIRST + k, f'running head on scan page {k + 1}'
        w = tokens(RUNNING_HEAD.sub(' ', text))
        words += w
        page_of += [STAT_FIRST + k] * len(w)
    return words, page_of


def act_tokens(doc):
    """Words of the structure file in reading order, and where each unit and title starts."""
    words, start = [], {}

    def unit(d):
        start[d['id']] = len(words)
        words.extend(tokens(f"{d['label'] or ''} {d['heading'] or ''} {d['own_text']}"))
        for c in d.get('children', []):
            unit(c)
        words.extend(tokens(d.get('trailing_text', '')))

    words.extend(tokens(' '.join(doc['front_matter'])))
    title = None
    for sec in doc['sections']:
        if sec['title'] != title:
            title = sec['title']
            start['TITLE ' + title] = len(words)
            words.extend(tokens(f"TITLE {title} {sec['title_heading']}"))
        unit(sec)
    words.extend(tokens(' '.join(doc['end_matter'])))
    return words, start


def align(a, b, n=5):
    """Match words of `a` to words of `b`.

    Anchors are runs of n words that occur exactly once in each text; the
    longest set of anchors that keeps the same order in both is kept. Returns
    {index in a: index in b} for every word inside a kept anchor.
    """
    def once(x):
        seen = {}
        for i in range(len(x) - n + 1):
            g = tuple(x[i:i + n])
            seen[g] = -1 if g in seen else i
        return {g: i for g, i in seen.items() if i >= 0}

    ga, gb = once(a), once(b)
    pairs = sorted((i, gb[g]) for g, i in ga.items() if g in gb)
    tails, at, prev = [], [], [-1] * len(pairs)   # longest increasing run of b-positions
    for k, (_, j) in enumerate(pairs):
        pos = bisect.bisect_left(tails, j)
        if pos == len(tails):
            tails.append(j)
            at.append(k)
        else:
            tails[pos], at[pos] = j, k
        prev[k] = at[pos - 1] if pos else -1
    match, k = {}, at[-1]
    while k != -1:
        i, j = pairs[k]
        for d in range(n):
            match[i + d] = j + d
        k = prev[k]
    return match


def stat_pages(doc, statutes_path, log):
    """Give every unit and title the page of the print it starts on."""
    a, start = act_tokens(doc)
    b, page_of = print_tokens(statutes_path)
    match = align(a, b)
    hit = sorted(match)
    assert all(match[x] < match[y] for x, y in zip(hit, hit[1:])), 'alignment is not in order'
    how, pages = {'exact': 0, 'between': 0, 'page turn': 0}, {}
    for uid, i in start.items():
        if i in match:                            # the unit's first word is matched
            pages[uid] = page_of[match[i]]
            how['exact'] += 1
            continue
        k = bisect.bisect_left(hit, i)
        before = hit[k - 1] if k else None        # nearest matched words on each side
        after = hit[k] if k < len(hit) else None
        pb = page_of[match[before]] if before is not None else None
        pa = page_of[match[after]] if after is not None else None
        if pb == pa or pa is None or pb is None:
            pages[uid] = pa or pb
            how['between'] += 1
            continue
        # The page turns between the two matched words. If the unit's opening
        # words read the same in the print, its start is fixed; otherwise count
        # words from each side.
        j = max(match[after] - (after - i), 0)
        pages[uid] = page_of[j]
        how['page turn'] += 1
        if a[i:after] != b[j:match[after]]:
            eb = page_of[min(match[before] + (i - before), len(b) - 1)]
            if eb != page_of[j]:
                log.append(f'{uid}: starts where the print turns from page {pb} to {pa}; the word counts '
                           f'disagree, {page_of[j]} used -- check by eye')
    cite = lambda p: f'{STAT_VOLUME} Stat. {p}'
    for sec in doc['sections']:
        for d in walk(sec):
            d['stat_page'] = cite(pages[d['id']])
    for t in doc['titles']:
        t['stat_page'] = cite(pages['TITLE ' + t['number']])
    order = [pages[d['id']] for sec in doc['sections'] for d in walk(sec)]
    assert order == sorted(order), 'print pages do not rise with reading order'
    return how, len(match) / len(a)


# ---------------------------------------------------------------- output
def to_dict(node):
    d = {'id': node.id, 'type': node.type, 'label': node.label, 'heading': node.heading}
    d.update(node.extra)
    d['own_text'] = '\n'.join(node.own)
    if node.children:
        d['children'] = [to_dict(c) for c in node.children]
    if node.trailing:
        d['trailing_text'] = '\n'.join(node.trailing)
    d['stat_page'] = None
    d['source_page'], d['source_line'] = node.page, node.line
    if node.id in NOTES:
        d['note'] = NOTES[node.id]
    if node.id in SUPPLEMENTS:
        assert SUPPLEMENTS[node.id]['replaces'] in d['own_text'], node.id
        d['supplement'] = SUPPLEMENTS[node.id]
    return d


def walk(d):
    yield d
    for c in d.get('children', []):
        yield from walk(c)


def reading_order(d, parts):
    """Append the text of unit `d` to `parts` as it reads in the act."""
    parts.append(d['label'] or '')
    if d['heading']:
        parts.append(d['heading'] + ('.' if d['type'] == 'section' else '.--' if d['label'] else ''))
    parts.append(d['own_text'])
    for c in d.get('children', []):
        reading_order(c, parts)
    parts.append(d.get('trailing_text', ''))


def check_lossless(doc, lines):
    """Every character of the input must be in the file exactly once, in order."""
    parts, title = list(doc['front_matter']), None
    for sec in doc['sections']:
        if sec['title'] != title:
            title = sec['title']
            parts.append(f"TITLE {title}--{sec['title_heading']}")
        reading_order(sec, parts)
    parts += doc['end_matter']
    squash = lambda s: re.sub(r'\s+', '', s)
    got = squash(''.join(parts))
    want = squash(''.join(re.sub(r'\s*_$', '', ln.text) if centred(ln) else ln.text for ln in lines))
    if got != want:
        k = next((i for i, (x, y) in enumerate(zip(got, want)) if x != y), min(len(got), len(want)))
        sys.exit(f'LOSSLESS CHECK FAILED at character {k}:\n  file : ...{got[max(0, k - 60):k + 60]}\n'
                 f'  input: ...{want[max(0, k - 60):k + 60]}')
    return len(want)


def sha256(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def pinned(path, expected, force):
    found = sha256(path)
    if expected and found != expected and not force:
        sys.exit(f'{pathlib.Path(path).name} is not the pinned input.\n  expected {expected}\n  found    {found}\n'
                 'Regenerate it from the corpus PDF, or pass --force to build anyway.')
    return found


def main(lines_path, statutes_path, out_dir, force=False):
    lines_path, statutes_path, out_dir = map(pathlib.Path, (lines_path, statutes_path, out_dir))
    lines_sha = pinned(lines_path, LINES_SHA256, force)
    statutes_sha = pinned(statutes_path, STATUTES_SHA256, force)
    lines = read_lines(lines_path)
    corrections = correct(lines)
    front, body, end = split_act(lines)

    log = []
    b = Builder(log)
    b.run(blocks(body, log))
    doc = {
        'schema': 'wrda-structure/1',
        'act': ACT, 'public_law': PUBLIC_LAW, 'enacted': ENACTED,
        'citation': f'{STAT_VOLUME} Stat. {STAT_FIRST}',
        'source': {
            'text': {'pdf': SOURCE_PDF, 'pdf_sha256': SOURCE_PDF_SHA256,
                     'lines_table': lines_path.name, 'lines_table_sha256': lines_sha},
            'pages': {'print': f'Statutes at Large, {STAT_VOLUME} Stat. {STAT_FIRST}-{STAT_LAST}',
                      'text': statutes_path.name, 'text_sha256': statutes_sha},
            'builder': pathlib.Path(__file__).name, 'builder_version': BUILDER_VERSION,
        },
        'counts': {},
        'corrections': corrections,
        'front_matter': [ln.text for ln in front],
        'titles': b.titles,
        'sections': [to_dict(s) for s in b.sections],
        'end_matter': [ln.text for ln in end],
    }
    units = [d for sec in doc['sections'] for d in walk(sec)]
    counts = doc['counts']
    counts['units'] = len(units)
    for d in units:
        counts[d['type'] + 's'] = counts.get(d['type'] + 's', 0) + 1
    counts['items_with_heading'] = sum(1 for d in units if d['type'] == 'item' and d['heading'])

    n_chars = check_lossless(doc, lines)
    assert counts['sections'] == SECTIONS_EXPECTED, f"{counts['sections']} sections, expected {SECTIONS_EXPECTED}"
    for uid in list(NOTES) + list(SUPPLEMENTS) + [c['unit'] for c in corrections]:
        assert uid in b.ids, f'note, supplement or correction for a unit that does not exist: {uid}'
    by_id = {d['id']: d for d in units}
    for c in corrections:
        assert c['now'] in by_id[c['unit']]['own_text'], f"correction is not in {c['unit']}"
    how, share = stat_pages(doc, statutes_path, log)

    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f'{ACT}.structure.json'
    out.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')

    table = out_dir / f'{ACT}.units.csv'
    with open(table, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f, lineterminator='\n')
        w.writerow(['id', 'parent', 'level', 'type', 'label', 'heading', 'stat_page', 'source_page',
                    'source_line', 'words', 'opening'])

        def row(d, parent, level):
            text = d['own_text'] + ' ' + d.get('trailing_text', '')
            w.writerow([d['id'], parent, level, d['type'], d['label'] or '', d['heading'] or '', d['stat_page'],
                        d['source_page'], d['source_line'], len(text.split()), d['own_text'][:80].replace('\n', ' ')])
            for c in d.get('children', []):
                row(c, d['id'], level + 1)
        for sec in doc['sections']:
            row(sec, '', 1)

    report = [f'{ACT} structure build (builder {BUILDER_VERSION})',
              f'input   {lines_path.name}', f'        sha256 {lines_sha}',
              f'input   {statutes_path.name}', f'        sha256 {statutes_sha}',
              f'output  {out.name}', f'        sha256 {sha256(out)}',
              f'output  {table.name}', f'        sha256 {sha256(table)}', '',
              f'lossless check passed: all {n_chars} non-space characters of the input are in the output, in order'
              f' (after {len(corrections)} recorded correction{"s" * (len(corrections) != 1)})',
              f"print pages: {how['exact']} units start on a matched word, {how['between']} between two matched "
              f"words on one page, {how['page turn']} at a page turn; {share:.1%} of words anchored", '',
              'counts'] + [f'  {k:20s} {v}' for k, v in counts.items()] + [
              '', f'judgment calls ({len(log)})'] + [f'  {x}' for x in log]
    (out_dir / f'{ACT}.build_log.txt').write_text('\n'.join(report) + '\n', encoding='utf-8')
    print('\n'.join(report))


if __name__ == '__main__':
    args = [x for x in sys.argv[1:] if x != '--force']
    if len(args) != 3:
        sys.exit(__doc__)
    main(*args, force='--force' in sys.argv)
