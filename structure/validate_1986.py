#!/usr/bin/env python3
"""Check the WRDA 1986 structure file.

 1. The file against itself: ids, section numbering, label order, page order.
 2. The file against facts read by hand from the act.
 3. The file against the Statutes at Large print, which was typeset
    independently of the PDF the file was built from: every unnumbered heading
    must be on the print page the file gives it, and the two texts must agree
    word for word.

Usage: validate_1986.py STRUCTURE.json STATUTES.txt
Writes "WRDA 1986.validation.txt" beside the structure file. Exit status 1 if
any check fails.
"""
import collections, difflib, json, pathlib, re, sys
import build_1986 as B

# The two units whose printed label breaks the order of its list (see NOTES in build_1986.py).
ODD_LABELS = {'1986.204.e-2nd', '1986.1117.b.2.3'}
TITLE_SECTIONS = {None: (1, 2), 'I': (101, 109), 'II': (201, 215), 'III': (301, 302), 'IV': (401, 403),
                  'V': (501, 502), 'VI': (601, 616), 'VII': (701, 733), 'VIII': (801, 872),
                  'IX': (901, 951), 'X': (1001, 1006), 'XI': (1101, 1173), 'XII': (1201, 1206),
                  'XIII': (1301, 1311), 'XIV': (1401, 1407)}
# Lists read by hand from the act: the projects "subject to favorable report".
B_LISTS = {
    '1986.201.b': ['Los Angeles and Long Beach Harbors, San Pedro Bay, California',
                   'New York Harbor and Adjacent Channels, New York and New Jersey'],
    '1986.202.b': ['Fresh Kills in Carteret, New Jersey', 'Arthur Kill, New York and New Jersey',
                   'New York Harbor and Adjacent Channels, New York and New Jersey'],
    '1986.301.b': ['Winfield Locks and Dam, Kanawha River, West Virginia'],
    '1986.401.b': ['Guadalupe River, San Jose, California', 'Meredosia, Illinois', 'Muscatine Island, Iowa',
                   'Pearl River Basin, St. Tammany Parish, Louisiana',
                   'West Bank Hurricane Protection Levee, Jefferson Parish, Louisiana',
                   'James River, South Dakota'],
    '1986.501.b': ['Pinellas County, Florida', 'Illinois Beach State Park, Illinois',
                   'Coconut Point, Tutuila Island, American Samoa'],
    '1986.601.b': ['Rillito River, Tucson, Arizona', 'Wailua Falls, Wailua River, Kauai, Hawaii',
                   'Yazoo River, Mississippi', 'Trinity River, Texas'],
}
# Print pages read from the scan, not from the alignment.
PAGES = {'1986.401': 4111, '1986.401.a.i01': 4111, '1986.401.a.i04': 4112, '1986.401.b.i02': 4127,
         '1986.401.b.i03': 4128, '1986.401.e': 4131, '1986.401.e.3': 4132, '1986.204.e-2nd': 4100,
         '1986.909': 4188, '1986.1117.b.2.3': 4236, '1986.805-2nd': 4272}


def position(d):
    lab = d['label'].strip('()')
    if d['type'] in ('clause', 'subclause'):
        return B.ROMAN[lab.lower()]
    return int(lab) if lab.isdigit() else ord(lab[0].lower()) - 96 + 26 * (len(lab) - 1)


def labels(d):
    return [c['label'] for c in d.get('children', [])]


def page(d):
    return int(d['stat_page'].split()[-1])


def main(structure, statutes):
    structure = pathlib.Path(structure)
    doc = json.loads(structure.read_text(encoding='utf-8'))
    units = [d for sec in doc['sections'] for d in B.walk(sec)]
    by = {d['id']: d for d in units}
    out, fails = [], []

    def check(ok, what, detail=''):
        out.append(f"  {'ok  ' if ok else 'FAIL'}  {what}" + (f'  [{detail}]' if detail and not ok else ''))
        if not ok:
            fails.append(what)

    # ---- 1. the file against itself
    out.append('1. The file against itself')
    check(len(by) == len(units), f'{len(units)} unit ids are all different')
    bad = [c['id'] for d in units for c in d.get('children', []) if not c['id'].startswith(d['id'] + '.')]
    check(not bad, 'every id extends the id of the unit it sits in', bad[:5])
    for title, (lo, hi) in TITLE_SECTIONS.items():
        nums = [int(s['number']) for s in doc['sections'] if s['title'] == title and not s['id'].endswith('-2nd')]
        check(nums == list(range(lo, hi + 1)), f"title {title or '(none)'}: sections {lo}-{hi} in unbroken order", nums[:8])
    bad = []
    for d in units:
        seq = [position(c) for c in d.get('children', []) if c['label'] and c['id'] not in ODD_LABELS]
        if seq != list(range(1, len(seq) + 1)):
            bad.append((d['id'], labels(d)))
    check(not bad, 'labels run in unbroken order in every list (two noted exceptions set aside)', bad[:5])
    bad = [d['id'] for d in units if not (d['own_text'] or d['heading'] or d.get('children'))]
    check(not bad, 'no empty units', bad[:5])
    pages = [page(d) for d in units]
    check(pages == sorted(pages) and B.STAT_FIRST <= pages[0] and pages[-1] <= B.STAT_LAST,
          f'print pages rise with reading order, {pages[0]} to {pages[-1]}')
    types = collections.Counter(d['type'] + 's' for d in units)
    check(all(doc['counts'].get(k) == v for k, v in types.items()), 'counts in the file match its units')

    # ---- 2. the file against facts read by hand
    out.append('2. The file against facts read by hand from the act')
    check(len(doc['sections']) == 309 and len(doc['titles']) == 14, '309 sections in 14 titles')
    check(labels(by['1986.401']) == ['(a)', '(b)', '(c)', '(d)', '(e)'], 'sec. 401 has subsections (a)-(e)')
    for uid, want in B_LISTS.items():
        got = [c['heading'] for c in by[uid]['children']]
        check(got == want, f'{uid}: the {len(want)} projects subject to favorable report', got)
    e = by['1986.401.e']
    check(labels(e) == ['(1)', '(2)', '(3)', '(4)', '(5)'] and all(c['heading'] for c in e['children']),
          'sec. 401(e) has five headed paragraphs')
    e3 = by['1986.401.e.3']
    check(labels(e3) == ['(A)', '(B)'] and labels(by['1986.401.e.3.B']) == ['(i)', '(ii)', '(iii)', '(iv)', '(v)', '(vi)']
          and e3.get('trailing_text', '').startswith('For purposes of analyzing the costs and benefits'),
          'sec. 401(e)(3) Pearl River: (A), (B)(i)-(vi), then the closing sentence as trailing text')
    check(labels(by['1986.903']) == ['(a)', '(b)', '(c)', '(d)'] and labels(by['1986.903.a']) == ['(1)', '(2)', '(3)']
          and labels(by['1986.903.a.2']) == ['(A)', '(B)', '(C)'], 'sec. 903: (a)(1)-(3), (a)(2)(A)-(C), (b), (c), (d)')
    a102 = by['1986.102.a']
    check(labels(a102) == ['(1)', '(2)', '(3)'] and a102.get('trailing_text', '').startswith('shall be paid only from'),
          'sec. 102(a): the sentence resumes after (1)-(3) as trailing text')
    groups = by['1986.1002']['children']
    check(len(groups) == 45 and groups[0]['heading'] == 'Alabama' and groups[-1]['heading'] == 'Wyoming'
          and all(g['type'] == 'group' and all(c['type'] == 'item' and not c['heading'] for c in g['children']) for g in groups),
          f"sec. 1002: 45 State groups, Alabama to Wyoming, holding {sum(len(g['children']) for g in groups)} projects")
    desc = by['1986.1006.b']                  # a boundary description is text of the piece it describes
    check(desc['own_text'].split('\n')[-1].startswith('Beginning at a point')
          and labels(desc) == ['(1)', '(2)', '(3)', '(4)']
          and desc.get('trailing_text') == 'the point and place of beginning.',
          'sec. 1006(b): the boundary description is text of (b), with its four courses and its closing words')
    check(by['1986.1.b']['own_text'].split('\n')[0] == 'Title I--Cost Sharing' and by['1986.1.b']['own_text'].count('\n') == 13,
          'sec. 1(b): the 14 lines of the table of contents')
    heads = {d['heading'] for d in units if d['label'] is None and d['heading']}
    check({'Bonneville Lock and Dam, Oregon and Washington--Columbia River and Tributaries, Washington',
           'Neponset River, Milton Town Landing to Port Norfolk, Massachusetts'} <= heads,
          'headings printed on two lines are joined')
    check(labels(by['1986.204']).count('(e)') == 2 and by['1986.805-2nd']['title'] == 'XIV'
          and labels(by['1986.1117.b.2']) == ['(A)', '(B)', '(3)'], 'the three label oddities are where the act prints them')
    check(len(by['1986.909.a']['supplement']['rows']) == 28, 'sec. 909(a): the 28-row table is supplied')
    check(labels(by['1986.1107']) == ['(a)', '(b)', '(c)'] and by['1986.1107.b']['own_text'].endswith('1966."'),
          'sec. 1107: (b) ends with the added quotation mark and (c) is its own subsection')
    check('"SEC. 4461. IMPOSITION OF TAX.' in by['1986.1402.a']['own_text'] and not by['1986.1402.a'].get('children'),
          'sec. 1402(a): quoted matter stays whole in the unit that inserts it')
    bad = {uid: page(by[uid]) for uid, p in PAGES.items() if page(by[uid]) != p}
    check(not bad, f'{len(PAGES)} print pages read from the scan', bad)

    # ---- 3. the file against the Statutes at Large print
    out.append('3. The file against the Statutes at Large print')
    text = pathlib.Path(statutes).read_text(encoding='utf-8', errors='replace').split('\f')
    low = []
    for d in units:
        if d['label'] is None and d['heading']:
            want = ' '.join(B.tokens(d['heading']))
            words = B.tokens(B.RUNNING_HEAD.sub(' ', text[page(d) - B.STAT_FIRST]))
            n = len(want.split())
            score = max(difflib.SequenceMatcher(None, want, ' '.join(words[k:k + n]), autojunk=False).ratio()
                        for k in range(max(1, len(words) - n + 1)))
            if score < 0.75:
                low.append((d['id'], d['heading'], round(score, 2)))
    n_heads = sum(1 for d in units if d['label'] is None and d['heading'])
    check(not low, f'all {n_heads} unnumbered headings are on the print page the file gives them', low[:5])

    a, _ = B.act_tokens(doc)
    n_front, n_end = (len(B.tokens(' '.join(doc[k]))) for k in ('front_matter', 'end_matter'))
    b, page_of = B.print_tokens(statutes)
    match = B.align(a, b)
    hit = sorted(match)
    matched, only_file, only_print = len(match), [], []
    edges = [(-1, -1)] + [(i, match[i]) for i in hit] + [(len(a), len(b))]
    for (i1, j1), (i2, j2) in zip(edges, edges[1:]):          # compare the words between anchors
        x, y = a[i1 + 1:i2], b[j1 + 1:j2]
        for tag, x1, x2, y1, y2 in difflib.SequenceMatcher(None, x, y, autojunk=False).get_opcodes():
            if tag == 'equal':
                matched += x2 - x1
                continue
            spaced = lambda w: sum(len(t) == 1 for t in w) > len(w) / 2      # l e t t e r - s p a c e d by the scan
            in_body = n_front <= i1 + 1 + x1 < len(a) - n_end      # title page and history are laid out differently
            if x2 - x1 >= 4 and in_body and not spaced(y[y1:y2]):
                only_file.append(' '.join(x[x1:x2])[:100])
            if y2 - y1 >= 12 and not spaced(y[y1:y2]):
                only_print.append(f"p. {page_of[j1 + 1 + y1]}: {' '.join(y[y1:y2])[:100]}")
    share = matched / len(a)
    check(share >= 0.98, f'{share:.1%} of the file\'s {len(a)} words are in the print, in the same order')
    check(not only_file, 'no run of 4 or more words in the body of the file is missing from the print', only_file[:5])
    check(len(only_print) == 1 and only_print[0].startswith('p. 4188'),
          'the only run of 12 or more words in the print that the file lacks is the sec. 909 table '
          '(supplied as a supplement)', only_print[:5])

    head = [f"{doc['act']} structure file: validation", f'file    {structure.name}',
            f'        sha256 {B.sha256(structure)}', '']
    tail = ['', f'{len(out) - 3 - len(fails)} checks passed, {len(fails)} failed']
    report = '\n'.join(head + out + tail) + '\n'
    (structure.parent / f"{doc['act']}.validation.txt").write_text(report, encoding='utf-8')
    print(report, end='')
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
