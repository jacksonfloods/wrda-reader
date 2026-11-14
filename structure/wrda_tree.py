#!/usr/bin/env python3
"""Shared parts of the structure builders for the acts after 1986.

build_text.py (govinfo text, 1996-2026) and build_scan.py (Statutes at Large
scans, 1988-1992) both turn their source into paragraphs and hand them to the
Tree class here, which places each paragraph in the act's tree by its labels.
build_1986.py is separate and unchanged; the rules are the same ones.

How a label is placed (Tree.labelled), in order:
 1. It is next in an open list printed at the same depth  -> continues it.
 2. It is a first label ("a", "1", "A", "i", "I", "aa", "AA") -> opens a new
    list under the nearest unit above it (or under the unit just before it,
    when an older print sets "(1)" at the same indent as its "(a)").
 3. It repeats the label before it                         -> "-2nd", flagged.
 4. It skips ahead in an open list at its depth ((1) then (3)) -> placed,
    and the gap is flagged: something was missed or the act misnumbers.
 5. It fits nothing -> kept in the list it is printed in, flagged; if there
    is no list at all, the paragraph is kept as text and flagged.

Nothing here stops the build. Every departure is written to `flags`, which
the build scripts save in the build log and in FLAGS.md.
"""
import csv, hashlib, json, pathlib, re

LABEL_RE = re.compile(r'\((\d{1,3}|[a-z]{1,3}|[A-Z]{1,3}|[ivxl]{1,6}|[IVXL]{1,6})\)')
# A heading runs to ".--". It may hold a semicolon ("Deauthorization; Congressional Review.--"), and a
# margin note removed from between the period and the dash leaves a space there ("Described. --").
HEAD_RE = re.compile(r" ?((?:(?!``|''|\. ?--).){1,200}?)\. ?--")
KIND_TYPE = {'lower': 'subsection', 'digit': 'paragraph', 'upper': 'subparagraph', 'roman': 'clause',
             'ROMAN': 'subclause', 'lower2': 'labelled_item', 'upper2': 'labelled_subitem'}
_R = ('i ii iii iv v vi vii viii ix x xi xii xiii xiv xv xvi xvii xviii xix xx xxi xxii xxiii xxiv xxv '
      'xxvi xxvii xxviii xxix xxx xxxi xxxii xxxiii xxxiv xxxv xxxvi xxxvii xxxviii xxxix xl').split()
ROMAN = {s: i + 1 for i, s in enumerate(_R)}
LETTERS = 'abcdefghijklmnopqrstuvwxyz'


def kinds(lab):
    """The kinds of list a label can belong to, with its position in each."""
    out = {}
    if lab.isdigit():
        out['digit'] = int(lab)
        return out
    if lab.lower() in ROMAN:
        out['roman' if lab.islower() else 'ROMAN'] = ROMAN[lab.lower()]
    if lab.isalpha() and len(set(lab)) == 1:
        k = ord(lab[0].lower()) - 96
        out['lower' if lab.islower() else 'upper'] = k + 26 * (len(lab) - 1)     # a..z, aa..zz
        if len(lab) == 2:
            out['lower2' if lab.islower() else 'upper2'] = k                     # (aa) under (I)
    return out


def label_at(kind, pos):
    """The label that stands at position `pos` of a list of this kind."""
    if kind == 'digit':
        return str(pos)
    if kind in ('roman', 'ROMAN'):
        r = _R[pos - 1] if pos <= len(_R) else '?'
        return r if kind == 'roman' else r.upper()
    if kind in ('lower2', 'upper2'):
        a = LETTERS[(pos - 1) % 26] * 2
    else:
        a = LETTERS[(pos - 1) % 26] * ((pos - 1) // 26 + 1)
    return a if kind.startswith('lower') else a.upper()


def split_labels(text):
    """'(a) Heading.--(1) Text' -> [('a', 'Heading'), ('1', None)], 'Text'"""
    labels, pos = [], 0
    while True:
        m = LABEL_RE.match(text, pos)
        if not m:
            break
        pos, head = m.end(), None
        h = HEAD_RE.match(text, pos)
        if h and h.group(1)[0].isalnum() and not LABEL_RE.search(h.group(1)[:6]):
            head, pos = h.group(1).strip(), h.end()
        labels.append((m.group(1), head))
        if head is None and not LABEL_RE.match(text, pos):
            break
    return labels, text[pos:].strip()


# Sections that hold a boundary or land description (metes and bounds, bearings, tracts). The
# unlabelled paragraphs of a description are part of the piece they describe, never units of their
# own, so these sections have no unnumbered items: {act key: section numbers}. The list was read and
# agreed section by section on 2026-11-15. (WRDA 1986 has its own list in build_1986.py.)
NO_ITEMS = {'1988': {'38', '39'}, '1990': {'119', '201'}, '1992': {'116', '335'}, '1996': {'364', '501'},
            '1999': {'563'}, '2000': {'346', '348'}, '2018': {'1331'}}


class Para:
    """A paragraph handed to the tree. kind: first | flush | other."""
    def __init__(self, no, page, kind, depth, text):
        self.no, self.page, self.kind, self.depth, self.text = no, page, kind, depth, text
        self.quoted = False


class Node:
    def __init__(self, id, type, label, heading, depth, line, page, parent, loose=False):
        self.id, self.type, self.label, self.heading = id, type, label, heading
        self.depth, self.line, self.page, self.parent, self.loose = depth, line, page, parent, loose
        self.own, self.children, self.trailing = [], [], []
        self.series, self.last, self.child_depth = None, 0, None
        self.lists, self.trail_at = 0, None
        self.extra = {}
        self.also = set()               # depths of the unlabelled paragraphs of a description this unit took in

    def put(self, text, line=None, page=None):
        if self.children and not self.trailing:
            self.trail_at = (line, page)
        (self.trailing if self.children else self.own).append(text)


class Tree:
    def __init__(self, prefix, flags, log):
        self.prefix, self.flags, self.log = prefix, flags, log
        self.sections, self.stack, self.ids = [], [], set()
        self.no_items = False           # True inside a section listed in NO_ITEMS

    def flag(self, kind, where, line, what):
        self.flags.append({'kind': kind, 'unit': where, 'source_line': line, 'what': what})

    # -- plumbing
    def new(self, parent, suffix, **kw):
        nid = f'{parent.id}.{suffix}'
        while nid in self.ids:
            nid += '-dup'
            self.flag('DUPLICATE ID', nid, kw['line'], 'two units would have had the same id')
        if parent.trailing and self.no_items:     # a description that runs on between two sub-units:
            last = parent.children[-1]            # it is text of the sub-unit before it
            for t in parent.trailing:
                last.put(t, *parent.trail_at)
            self.log.append(f'line {parent.trail_at[0]}: text of a description stands between two sub-units of '
                            f'{parent.id}; kept as text of {last.id}')
            parent.trailing = []
        if parent.trailing:                       # text stood between two sub-units: keep it in its place
            k = sum(1 for c in parent.children if c.type == 'item') + 1
            line, page = parent.trail_at
            t = Node(f'{parent.id}.i{k:02d}', 'item', None, None, parent.child_depth, line, page, parent, loose=True)
            t.own, parent.trailing = parent.trailing, []
            t.extra = {'between_units': True}
            self.ids.add(t.id)
            parent.children.append(t)
            self.log.append(f'line {line}: text of {parent.id} stands between two of its sub-units; kept in place as {t.id}')
        node = Node(nid, parent=parent, **kw)
        self.ids.add(nid)
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
        return self.stack[0] if depth == 1 else None      # the section's own paragraphs

    def above(self, depth):
        return next(x for x in reversed(self.stack) if x.depth is not None and x.depth < depth)

    def top(self):
        return self.stack[-1]

    # -- handlers
    def section(self, label, number, heading, line, page, extra):
        sid = f'{self.prefix}.{number}'
        if sid in self.ids:
            sid += '-2nd'
            self.flag('SECTION NUMBER USED TWICE', sid, line, f'section number {number} is printed a second time')
        node = Node(sid, 'section', label, heading, 0, line, page, None)
        self.no_items = str(number) in NO_ITEMS.get(self.prefix, ())
        self.ids.add(sid)
        node.extra = dict(number=number, **extra)
        self.sections.append(node)
        self.stack = [node]
        return node

    def labelled(self, p, labels, text, raw=None):
        made = None
        for j, (lab, head) in enumerate(labels):
            ks = kinds(lab)
            pick, suffix, pos = None, lab, None
            if j == 0:
                for node in reversed(self.stack):                 # 1. next in an open list at this depth
                    if node.series in ks and ks[node.series] == node.last + 1 and node.child_depth == p.depth:
                        pick = (node, node.series)
                        break
                if pick is None:                                  # ... or in a list opened run-in: "(a)(1)"
                    for node in reversed(self.stack):
                        if (node.series in ks and ks[node.series] == node.last + 1 and node.child_depth is None
                                and node.depth is not None and node.depth <= p.depth):
                            pick = (node, node.series)
                            break
            if pick is None:                                      # 2. first of a new list
                first = [k for k, v in ks.items() if v == 1]
                if first:
                    top = self.top()
                    if j:
                        parent = made                     # run-in: "(a) Heading.--(1)"
                    elif (top.depth == p.depth and top.label and top.series is None and top.parent is not None
                          and top.parent.series != first[0]):
                        parent = top                      # older print: "(1)" set at the indent of its "(a)"
                    else:
                        parent = self.above(p.depth)
                    pick = (parent, first[0])
                    if pick[0].series is not None:
                        pick[0].lists += 1
            if pick is None and j == 0:
                for node in reversed(self.stack):                 # 3. the label before it, again
                    if node.series in ks and ks[node.series] == node.last and node.child_depth == p.depth:
                        pick, suffix, pos = (node, node.series), lab + '-2nd', node.last
                        self.flag('LABEL USED TWICE', f'{node.id}.{suffix}', p.no,
                                  f'({lab}) is printed a second time in {node.id}')
                        break
            if pick is None and j == 0:
                for node in reversed(self.stack):                 # 4. skips ahead
                    if node.series in ks and ks[node.series] > node.last + 1 and node.child_depth == p.depth:
                        missing = ', '.join(f'({label_at(node.series, q)})' for q in range(node.last + 1, ks[node.series]))
                        pick = (node, node.series)
                        self.flag('GAP IN NUMBERING', f'{node.id}.{lab}', p.no,
                                  f'({lab}) follows {node.children[-1].label} in {node.id}; missing {missing}')
                        break
            if pick is None and j == 0:
                for node in reversed(self.stack):                 # 5. fits nothing
                    if node.series and node.child_depth == p.depth:
                        pick, pos = (node, node.series), node.last + 1
                        self.flag('LABEL OUT OF ORDER', f'{node.id}.{lab}', p.no,
                                  f'({lab}) does not fit the list it is printed in '
                                  f'({node.children[-1].label} comes before it); kept there')
                        break
            if pick is None:
                if made is None:
                    self.flag('LABEL FITS NO LIST', self.top().id, p.no,
                              f'({lab}) starts a paragraph but belongs to no list; kept as text: {p.text[:60]!r}')
                    q = Para(p.no, p.page, p.kind, p.depth, raw if raw is not None else p.text)
                    self.unlabelled(q)
                else:
                    self.flag('LABEL FITS NO LIST', made.id, p.no, f'run-in label ({lab}) kept as text of {made.id}')
                    tail = ''.join(f'({l})' + (f' {h}.--' if h else '') for l, h in labels[j:])
                    made.own.append((tail + ' ' + text).strip())
                return
            parent, kind = pick
            if parent.lists:                              # a second list under one unit: ids end in -list2
                suffix += f'-list{parent.lists + 1}'
                if ks.get(kind) == 1 and pos is None:
                    self.log.append(f'line {p.no}: {parent.id} has another list, starting at ({lab}); ids end in -list{parent.lists + 1}')
            made = self.new(parent, suffix, type=KIND_TYPE[kind], label=f'({lab})', heading=head,
                            depth=p.depth, line=p.no, page=p.page)
            parent.series = kind
            parent.child_depth = p.depth if j == 0 else None
            parent.last = ks[kind] if pos is None else pos
        if text:
            made.own.append(text)

    def unlabelled(self, p):
        node = self.at_depth(p.depth)
        if node is not None and not node.loose:                   # a further paragraph of that unit
            self.pop_to(node)
            node.put(p.text, p.no, p.page)
            return
        if self.no_items:                                         # a boundary description: text of the piece
            parent = self.above(p.depth)                          # it describes, and so is all that follows it
            self.pop_to(parent)                                   # at this indent
            if p.depth not in parent.also:
                self.log.append(f'line {p.no}: the description that starts here is kept as text of {parent.id}')
            parent.also.add(p.depth)
            parent.put(p.text, p.no, p.page)
            return
        parent = node.parent if node is not None else self.above(p.depth)
        k = sum(1 for c in parent.children if c.type == 'item') + 1
        item = self.new(parent, f'i{k:02d}', type='item', label=None, heading=None, depth=p.depth,
                        line=p.no, page=p.page, loose=True)
        item.own.append(p.text)

    def flush(self, p):
        node = self.at_depth(p.depth) if p.depth else None
        if node is None:
            node = self.top()
            self.log.append(f'line {p.no}: text at depth {p.depth} has no unit at that depth; '
                            f'kept with {node.id}: {p.text[:50]!r}')
        self.pop_to(node)
        node.put(p.text, p.no, p.page)

    def keep(self, text, line=None, page=None):
        """Quoted matter, a table, or the contents list: text of the unit that carries it."""
        self.top().put(text, line, page)


# ---------------------------------------------------------------- output
def to_dict(node, notes):
    d = {'id': node.id, 'type': node.type, 'label': node.label, 'heading': node.heading}
    d.update(node.extra)
    d['own_text'] = '\n'.join(node.own)
    if node.children:
        d['children'] = [to_dict(c, notes) for c in node.children]
    if node.trailing:
        d['trailing_text'] = '\n'.join(node.trailing)
    d['stat_page'], d['source_line'] = node.page, node.line
    if node.id in notes:
        d['note'] = notes[node.id]
    return d


def walk(d):
    yield d
    for c in d.get('children', []):
        yield from walk(c)


def reading_order(d, parts):
    parts.append(d['label'] or '')
    if d['heading']:
        parts.append(d['heading'] + (('' if d.get('heading_has_no_period') else '.') if d['type'] == 'section'
                                    else '.--' if d['label'] else ''))
    parts.append(d['own_text'])
    for c in d.get('children', []):
        reading_order(c, parts)
    parts.append(d.get('trailing_text', ''))


def squash(s):
    return re.sub(r'\s+', '', s)


def check_lossless(doc, want_text):
    """Every non-space character of the input must be in the file once, in order."""
    parts = list(doc['front_matter'])
    heads = {}
    for h in doc['headings']:
        heads.setdefault(h['before_section'], []).append(h['text'])
    for sec in doc['sections']:
        parts += heads.get(sec['id'], [])
        reading_order(sec, parts)
    parts += heads.get(None, [])
    parts += doc['end_matter']
    got, want = squash(''.join(parts)), squash(want_text)
    if got != want:
        k = next((i for i, (x, y) in enumerate(zip(got, want)) if x != y), min(len(got), len(want)))
        raise SystemExit(f'LOSSLESS CHECK FAILED at character {k}:\n  file : ...{got[max(0, k - 80):k + 80]}\n'
                         f'  input: ...{want[max(0, k - 80):k + 80]}')
    return len(want)


def sha256(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def count_units(doc):
    units = [d for sec in doc['sections'] for d in walk(sec)]
    counts = {'units': len(units)}
    for d in units:
        counts[d['type'] + 's'] = counts.get(d['type'] + 's', 0) + 1
    return counts


def write_outputs(doc, out_dir, name, report_head, log, flags):
    """Write NAME.structure.json, NAME.units.csv, NAME.build_log.txt; return the report."""
    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f'{name}.structure.json'
    out.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')
    table = out_dir / f'{name}.units.csv'
    with open(table, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f, lineterminator='\n')
        w.writerow(['id', 'parent', 'level', 'type', 'label', 'heading', 'stat_page', 'source_line', 'words', 'opening'])

        def row(d, parent, level):
            text = d['own_text'] + ' ' + d.get('trailing_text', '')
            w.writerow([d['id'], parent, level, d['type'], d['label'] or '', d['heading'] or '', d['stat_page'] or '',
                        d['source_line'], len(text.split()), d['own_text'][:80].replace('\n', ' ')])
            for c in d.get('children', []):
                row(c, d['id'], level + 1)
        for sec in doc['sections']:
            row(sec, '', 1)
    report = report_head + [f'output  {out.name}', f'        sha256 {sha256(out)}',
                            f'output  {table.name}', f'        sha256 {sha256(table)}', '', 'counts']
    report += [f'  {k:22s} {v}' for k, v in doc['counts'].items()]
    report += ['', f'flags ({len(flags)}) -- things to check by eye']
    report += [f"  {x['kind']:26s} {x['unit']}  (source line {x['source_line']}): {x['what']}" for x in flags]
    report += ['', f'notes ({len(log)})'] + [f'  {x}' for x in log]
    (out_dir / f'{name}.build_log.txt').write_text('\n'.join(report) + '\n', encoding='utf-8')
    return report
