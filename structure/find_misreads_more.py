#!/usr/bin/env python3
"""Read-only: the checks for misreadings that a word list cannot make, and a digest of find_misreads.py's table.

Usage: find_misreads_more.py STRUCTURE_DIR ACT_KEY [CANDIDATES.tsv]

Prints, for one scanned act: (0) the distinct candidates of find_misreads.py, if its table is given;
(a) heading words that the unit's own text spells differently; (b) real words that do not fit their
neighbours where a look-alike does (judged by word pairs in the acts built from typed text); (c) a period
where a comma belongs; (d) letter-spaced words; (e) "X" read for ")("; odd marks inside a word or number;
(f) hyphens kept from a line end; (g) dates and citations run together; (h) costs that do not add up.
Everything printed is a candidate for a person to judge. Writes nothing."""
import collections
import csv
import json
import pathlib
import re
import sys

w, key = pathlib.Path(sys.argv[1]), sys.argv[2]
SCANNED = ('1988', '1990', '1992')


def walk(u):
    yield u
    for c in u.get('children', []):
        yield from walk(c)


docs = {}
for f in sorted(w.glob('*.structure.json')):
    d = json.load(open(f, encoding='utf-8'))
    docs[d['sections'][0]['id'].split('.')[0]] = d
W1 = re.compile(r"[A-Za-z]+")
freq, big, hyph = collections.Counter(), collections.Counter(), collections.Counter()
for k, d in docs.items():
    if k in SCANNED:
        continue
    for s in d['sections']:
        for u in walk(s):
            for fld in ('heading', 'own_text', 'trailing_text'):
                t = u.get(fld) or ''
                ws = [x.lower() for x in W1.findall(t)]
                freq.update(ws)
                big.update(zip(ws, ws[1:]))
                hyph.update(x.lower() for x in re.findall(r"[A-Za-z]+(?:-[A-Za-z]+)+", t))
units = [u for s in docs[key]['sections'] for u in walk(s)]
allu = [(u, fld, u.get(fld) or '') for u in units for fld in ('heading', 'own_text', 'trailing_text') if u.get(fld)]
short = lambda u: u['id'].split('.', 1)[1]
cut = lambda t, i, j, n=36: t[max(0, i - n):j + n].replace('\n', ' ')

if len(sys.argv) > 3:
    rows = list(csv.DictReader(open(sys.argv[3], encoding='utf-8'), delimiter='\t'))
    groups = collections.OrderedDict()
    for r in rows:
        groups.setdefault((r['as_scanned'], r['fix']), []).append(r)
    print(f"(0) {len(rows)} places, {len(groups)} distinct: count, as scanned -> guess | where | context")
    for (a, f), rs in groups.items():
        c = rs[0]['context']
        i = c.find('[')
        print(f"{len(rs):2d} {a} -> {f or '?'} | {rs[0]['unit'].split('.', 1)[1]}{'/h' if rs[0]['field'] == 'heading' else ''} | {c[max(0, i - 32):i + 44]}")


def lev(a, b):
    p = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        q = [i]
        for j, y in enumerate(b, 1):
            q.append(min(p[j] + 1, q[j - 1] + 1, p[j - 1] + (x != y)))
        p = q
    return p[-1]


print("(a) heading words that the unit's own text spells differently")
for u in units:
    h, t = u.get('heading') or '', u.get('own_text') or ''
    hw, tw = [x for x in W1.findall(h) if len(x) >= 4], {x.lower(): x for x in W1.findall(t) if len(x) >= 4}
    if len(hw) < 2 or sum(x.lower() in tw for x in hw) < len(hw) / 2:
        continue
    for x in hw:
        if x.lower() in tw:
            continue
        near = sorted((lev(x.lower(), y), y) for y in tw if abs(len(y) - len(x)) <= 2 and y[:1] == x[:1].lower() or lev(x.lower(), y) <= 1)
        if near and near[0][0] <= 2 and not (x.lower() in freq and near[0][1] in freq):
            print(f"   {short(u):12} heading {x!r} | text {tw[near[0][1]]!r} | {h[:56]}")

print("(b) real words that do not fit their neighbours, where a look-alike does")
LET = 'abcdefghijklmnopqrstuvwxyz'


def e1(x):
    sp = [(x[:i], x[i:]) for i in range(len(x) + 1)]
    return ({a + b[1:] for a, b in sp if b} | {a + c + b[1:] for a, b in sp if b for c in LET} | {a + c + b for a, b in sp for c in LET}
            | {x.replace(p, q, 1) for p, q in (('li', 'h'), ('h', 'li'), ('il', 'h'), ('rn', 'm'), ('m', 'rn'), ('cl', 'd'), ('ii', 'n'), ('tl', 'th'), ('u', 'li')) if p in x})


for u, fld, t in allu:
    ms = list(W1.finditer(t))
    ws = [m.group().lower() for m in ms]
    for i in range(1, len(ws) - 1):
        x, L, R = ws[i], ws[i - 1], ws[i + 1]
        if len(x) < 2 or x not in freq or big[(L, x)] or big[(x, R)]:
            continue
        best = max(((big[(L, c)] + big[(c, R)], c) for c in e1(x) if c in freq and big[(L, c)] >= 2 and big[(c, R)] >= 2), default=None)
        if best and best[0] >= 12 and freq[best[1]] >= 5 * freq[x]:
            print(f"   {short(u):12} {ms[i].group()!r} -> {best[1]!r} | {cut(t, ms[i].start(), ms[i].end())}")

print("(c) a period where a comma may belong")
START = (r'The |Such |Any |In |If |No |Not |Nothing |Upon |For |Before |Within |Each |This |Section |Subsection |Paragraph |Notwithstanding |After |'
         r'Funds |There |Sec\. |Subject |Except |To |As |At |On |With |Non|All |An |A |Of |Until |Unless |Prior |During |Beginning |Thence |Running |'
         r'Amounts |Nonstructural |Costs |Federal |Recreation|Projects |Work |Construction |Operation |Appropriations |Benefits |These |Those |It |He |Report')
for u, fld, t in allu:
    for m in re.finditer(r'(\S+)\. ([a-z]\S*)', t):
        if not re.fullmatch(r'(?:U\.S\.C|Stat|No|seq|St|Ft|Mt|Dr|Jr|Sr|Inc|Co|Pub|L|Sec|sec|app|etc|i\.e|e\.g|[A-Z])', m.group(1).strip('(')):
            print(f"   {short(u):12} small letter after: {cut(t, m.start(), m.end())}")
    for m in re.finditer(r'[A-Z][a-z]+ \d{1,2}\. ?(?:19|20)\d\d|(?:19|20)\d\d\. (?:at|with|and)\b', t):
        print(f"   {short(u):12} in a date: {cut(t, m.start(), m.end())}")
    for m in re.finditer(r'\b(?:control|navigation|protection|restoration|enhancement|project|purposes|River|Harbor|Lake|Creek|Dam|Channel|Bay|Basin|\d+)\. (?!' + START + r')[A-Z][a-z]+', t):
        if fld != 'heading':
            print(f"   {short(u):12} before a name: {cut(t, m.start(), m.end(), 30)}")

print("(d) letter-spaced words")
for u, fld, t in allu:
    for m in re.finditer(r'(?:(?<=\s)|^)(?:\S ){3,}\S(?=[\s,.;:]|$)|\bI N (?=[A-Z])', t):
        print(f"   {short(u):12}{'/h' if fld == 'heading' else '':3} {m.group()!r} | {cut(t, m.start(), m.end(), 30)}")

print('(e) "X" for ")(" and odd marks inside a word or number')
for u, fld, t in allu:
    for m in re.finditer(r'\(\w{1,3}X\w{1,3}(?:X\w{1,3})?\)|\S*[A-Za-z0-9)(][!?*^|~<>]+[A-Za-z0-9()]\S*|\S*\d[OlISB]\d\S*|\b[lO]\d{2,}\b|\b\d+[lO]\b', t):
        print(f"   {short(u):12} {m.group()!r} | {cut(t, m.start(), m.end(), 26)}")

print("(f) hyphens kept from a line end? (one word in the typed acts, never hyphenated there)")
seen = collections.Counter(x for u, fld, t in allu for x in re.findall(r'\b[A-Za-z]{2,}-[A-Za-z]{2,}\b', t)
                           if freq[x.lower().replace('-', '')] >= 3 and not hyph[x.lower()])
print('  ', dict(seen))

print("(g) dates and citations run together")
allt = '\n'.join(t for _, _, t in allu)
print("   day,year:", len(re.findall(r'\b\d{1,2},(?:19|20)\d\d\b', allt)), re.findall(r'\S+ \d{1,2},(?:19|20)\d\d\b', allt)[:3],
      "| U.S.C.:", sorted(set(re.findall(r'\S*\d+ ?U\.S\.C\.\S+|\S*\dU\.S\.C\. ?\S*', allt)))[:12])

print("(h) costs that do not add up (total against Federal + non-Federal)")
num = lambda s: int(s.replace(',', ''))
n = 0
for u, fld, t in allu:
    for m in re.finditer(r'total (?:project )?cost of \$([\d,]+),? ?with an estimated first Federal cost of \$([\d,]+),? and an estimated first non-Federal cost of \$([\d,]+)', t):
        n += 1
        a, b, c = map(num, m.groups())
        if a != b + c:
            print(f"   {short(u):12} {a:,} against {b:,} + {c:,} = {b + c:,}")
print("   entries checked:", n)
