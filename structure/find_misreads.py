#!/usr/bin/env python3
"""Read-only: list the words of one scanned act that look misread, each with its context and a proposed fix.

Usage: misreads.py STRUCTURE_DIR ACT_KEY OUT.tsv

A word is suspect if (a) it holds a character that does not belong in a word (^ | * ...), (b) it is found
neither in the acts built from typed text (1986, 1996-2026) nor in the system dictionary, or (c) its
capitals are odd (CAUFORNiA; "Los" inside a heading printed in capitals). The proposed fix is the nearest
word that the typed acts use, the commonest first. Writes only OUT.tsv."""
import collections
import csv
import json
import pathlib
import re
import sys

sdir, key, out = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3]
CLEAN = {'1986', '1996', '1999', '2000', '2007', '2014', '2016', '2018', '2020', '2022', '2024', '2026H', '2026S'}
docs = {}
for f in sorted(sdir.glob('*.structure.json')):
    d = json.load(open(f, encoding='utf-8'))
    docs[d['sections'][0]['id'].split('.')[0]] = d


def walk(u):
    yield u
    for c in u.get('children', []):
        yield from walk(c)


WORD = re.compile(r"[A-Za-z]+")
freq, exact = collections.Counter(), collections.Counter()
for k, d in docs.items():
    if k in CLEAN:
        for s in d['sections']:
            for u in walk(s):
                for fld in ('heading', 'own_text', 'trailing_text'):
                    for w in WORD.findall(u.get(fld) or ''):
                        freq[w.lower()] += 1
                        exact[w] += 1
dictw = {w.strip().lower() for w in open('/usr/share/dict/words', encoding='utf-8', errors='ignore')}
capfreq = collections.Counter({w.lower(): 0 for w in ()})
for w, n in exact.items():
    if w[:1].isupper():
        capfreq[w.lower()] += n
WATCH = {'comer': 'corner', 'comers': 'corners', 'modem': 'modern', 'arid': 'and', 'tbe': 'the', 'die': 'the', 'tune': 'time',
         'bum': 'burn', 'tum': 'turn', 'hie': 'the', 'tiie': 'the', 'wiu': 'will', 'ofthe': 'of the', 'tothe': 'to the'}


def known(w):
    if w in freq or w in dictw:
        return True
    for end, adds in (('ies', ('y',)), ('ied', ('y',)), ('es', ('', 'e')), ('ed', ('', 'e')), ('ing', ('', 'e')), ('s', ('',)),
                      ('d', ('',)), ('ly', ('',)), ('er', ('', 'e')), ('ers', ('', 'e')), ('ment', ('',)), ('ments', ('',))):
        if w.endswith(end) and len(w) - len(end) >= 3:
            stem = w[:-len(end)]
            if any(stem + a in freq or (stem + a in dictw and len(stem + a) >= 5) for a in adds):
                return True
            if len(stem) > 4 and stem[-1] == stem[-2] and (stem[:-1] in dictw or stem[:-1] in freq):
                return True
    return False


LETTERS = 'abcdefghijklmnopqrstuvwxyz'
OCR = [('u', 'li'), ('li', 'u'), ('bc', 'x'), ('rn', 'm'), ('m', 'rn'), ('ii', 'n'), ('ii', 'u'), ('cl', 'd'), ('d', 'cl'),
       ('vv', 'w'), ('tb', 'th'), ('fi', 'fl'), ('fl', 'fi'), ('ri', 'n'), ('n', 'ri'), ('lU', 'ill'), ('u', 'll'), ('ll', 'u'),
       ('h', 'li'), ('li', 'h'), ('ii', 'h'), ('h', 'ii'), ('u', 'h'), ('in', 'm'), ('m', 'in'), ('ni', 'm'), ('m', 'ni'), ('iu', 'm'), ('nn', 'm'), ('w', 'vv')]


def edits1(w):
    sp = [(w[:i], w[i:]) for i in range(len(w) + 1)]
    out = {a + b[1:] for a, b in sp if b}
    out |= {a + b[1] + b[0] + b[2:] for a, b in sp if len(b) > 1}
    out |= {a + c + b[1:] for a, b in sp if b for c in LETTERS}
    out |= {a + c + b for a, b in sp for c in LETTERS}
    for x, y in OCR:
        x = x.lower()
        i = w.find(x)
        while i >= 0:
            out.add(w[:i] + y + w[i + len(x):])
            i = w.find(x, i + 1)
    return out


def propose(low):
    """(best, edits, runner_up) among the words the typed acts use."""
    if len(low) < 2:
        return None, 0, None
    for n, cands in ((1, edits1(low)),):
        hit = sorted((c for c in cands if c in freq), key=lambda c: -freq[c])
        if hit:
            return hit[0], n, (hit[1] if len(hit) > 1 else None)
    if len(low) >= 5:
        seen = collections.Counter()
        for e in edits1(low):
            for c in edits1(e):
                if c in freq:
                    seen[c] = freq[c]
        if seen:
            hit = [c for c, _ in seen.most_common(2)]
            return hit[0], 2, (hit[1] if len(hit) > 1 else None)
    return None, 0, None


def recase(tok, cand, caps_heading):
    if caps_heading or (tok.isupper() and len(tok) > 1):
        return cand.upper()
    if tok[:1].isupper():
        forms = [(n, w) for w, n in exact.items() if w.lower() == cand and w[:1].isupper() and not w.isupper()]
        return max(forms)[1] if forms else cand.capitalize()
    forms = [(n, w) for w, n in exact.items() if w.lower() == cand and w[:1].islower()]
    return max(forms)[1] if forms else cand


STRIP = '.,;:!?()[]{}"\'`“”‘’—–-'
ODD = re.compile(r"[^A-Za-z0-9'’\-/.,&$%()]")
NUMBERISH = re.compile(r"^[$(]?\d[\d,.\-/()a-zA-Z]{0,12}$")
rows = []
doc = docs[key]
for s in doc['sections']:
    for u in walk(s):
        for fld in ('heading', 'own_text', 'trailing_text'):
            text = u.get(fld) or ''
            if not text:
                continue
            letters = [ch for ch in text if ch.isalpha()]
            caps_heading = fld == 'heading' and letters and sum(ch.isupper() for ch in letters) / len(letters) > 0.7
            toks = [(m.group(), m.start()) for m in re.finditer(r'\S+', text)]
            for i, (raw, pos) in enumerate(toks):
                core = raw.strip(STRIP)
                if not re.search('[A-Za-z]', core) or NUMBERISH.match(core):
                    continue
                core = re.sub(r"['’]s$", '', core)
                for part in [p for p in re.split(r'[-/]', core) if re.search('[A-Za-z]', p)]:
                    low = ''.join(ch for ch in part if ch.isalpha()).lower()
                    reason = None
                    if ODD.search(part) or re.search(r'[A-Za-z]\d|\d[A-Za-z]', part):
                        reason = 'odd character'
                    elif low in WATCH:
                        reason = 'a real word that scans often print by mistake'
                    elif not known(low):
                        reason = 'name, or misread?' if (part[:1].isupper() and not caps_heading) else 'not a known word'
                    elif caps_heading and part != part.upper():
                        reason = 'small letters in a heading of capitals'
                    elif (re.search(r'[a-z][A-Z]', part) or re.search(r'[A-Z]{2,}[a-z]', part)) and part not in exact:
                        reason = 'odd capitals'
                    if not reason:
                        continue
                    fix, n, other, sure = None, 0, None, 'check'
                    if low in WATCH:
                        fix, sure = recase(part, WATCH[low], caps_heading), 'check'
                    elif known(low) and reason not in ('not a known word', 'name, or misread?'):
                        fix, sure = recase(part if reason == 'odd character' else part, low, caps_heading or reason == 'small letters in a heading of capitals'), 'sure'
                        if reason == 'odd capitals' and not caps_heading:
                            forms = [(c, w) for w, c in exact.items() if w.lower() == low]
                            fix = max(forms)[1] if forms else low
                    else:
                        cand = None
                        inner = re.sub(r'^[^A-Za-z]+|[^A-Za-z]+$', '', part)
                        if reason == 'odd character' and re.search(r'[^A-Za-z]', inner):
                            pat = re.compile('^' + re.sub(r'[^a-z]+', '[a-z]{1,3}', inner.lower()) + '$')
                            hits = sorted((w for w in freq if pat.match(w)), key=lambda w: -freq[w])
                            if hits:
                                cand, n, other = hits[0], 1, (hits[1] if len(hits) > 1 else None)
                        if cand is None:
                            cand, n, other = propose(low)
                        if cand and reason == 'name, or misread?' and capfreq[cand] < 3:
                            cand = None
                        two = next(((low[:j], low[j:]) for j in range(2, len(low) - 1)
                                    if freq[low[:j]] >= 40 and freq[low[j:]] >= 40), None)
                        if cand is None and two:
                            fix, sure, reason = ' '.join(two), 'check', 'two words run together'
                        elif cand:
                            fix = recase(part, cand, caps_heading)
                            strong = freq[cand] >= 20 and (other is None or freq[cand] >= 5 * freq[other])
                            sure = 'sure' if (n == 1 and strong) else 'check'
                    ctx = ' '.join(t for t, _ in toks[max(0, i - 5):i]) + ' [' + raw + '] ' + ' '.join(t for t, _ in toks[i + 1:i + 6])
                    rows.append({'unit': u['id'], 'field': fld, 'as_scanned': part, 'fix': fix or '', 'confidence': sure if fix else 'no idea',
                                 'why': reason, 'other': other or '', 'context': ctx})

with open(out, 'w', encoding='utf-8', newline='') as fh:
    w = csv.DictWriter(fh, fieldnames=['unit', 'field', 'as_scanned', 'fix', 'confidence', 'why', 'other', 'context'], delimiter='\t')
    w.writeheader()
    w.writerows(rows)

n_words = sum(len(re.findall(r'\S+', (u.get(f) or ''))) for s in doc['sections'] for u in walk(s) for f in ('heading', 'own_text', 'trailing_text'))
print(f"{doc['act']}: {n_words:,} words; {len(rows)} suspect ({len(rows) / n_words:.1%}); "
      f"{len({(r['as_scanned'], r['fix']) for r in rows})} distinct")
print('by confidence:', dict(collections.Counter(r['confidence'] for r in rows)))
print('by reason    :', dict(collections.Counter(r['why'] for r in rows)))
print('in units under sec. 3(a):', sum(1 for r in rows if r['unit'].startswith(key + '.3.a')))
