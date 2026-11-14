#!/usr/bin/env python3
"""Turn an approved review table of misreadings into corrections for the scan lines of one act.

Usage: misreads_to_corrections.py KEY REVIEW.tsv DECISIONS.json LINES.tsv STRUCTURE.json OUT.tsv

REVIEW.tsv     the table made by review_misreads_KEY.py (one line per place; `row` numbers the proposals)
DECISIONS.json the reviewer's answers: {"approved": "YYYY-MM-DD", "skip": [rows], "rows": {row: fix},
               "lines": {row: {scan line: fix}}}  -- a fix here replaces the one in the table
OUT.tsv        line, was, now, why: what build_scan.py reads as corrections_KEY.tsv

Each place is found again on its scan line. A place that runs over a line end is worked out where the
break is plain (the same number of words before and after; a word broken by a hyphen); anything else is
printed for a decision and left out. Writes only OUT.tsv."""
import collections
import csv
import json
import re
import sys

key, review, decisions, lines_path, structure, out = sys.argv[1:7]
dec = json.load(open(decisions, encoding='utf-8'))
skip = set(map(int, dec.get('skip', [])))
row_fix = {int(k): v for k, v in dec.get('rows', {}).items()}
line_fix = {int(k): {int(a): b for a, b in v.items()} for k, v in dec.get('lines', {}).items()}
RULES = {'date': (re.compile(r'\b(\d{1,2}),((?:19|20)\d\d)\b'), r'\1, \2'),
         'I N': (re.compile(r'\bI N GENERAL(?!,(?:--|—))'), 'IN GENERAL')}

lines = [(int(r['line']), r['text']) for r in csv.DictReader(open(lines_path, encoding='utf-8', newline=''), delimiter='\t',
                                                             quoting=csv.QUOTE_NONE) if r['text']]
by_no = dict(lines)
order = [no for no, _ in lines]
nxt = dict(zip(order, order[1:]))
doc = json.load(open(structure, encoding='utf-8'))


def walk(u):
    yield u
    for c in u.get('children', []):
        yield from walk(c)


starts = sorted({u['source_line'] for s in doc['sections'] for u in walk(s) if u.get('source_line')})
unit_line = {u['id']: u.get('source_line') for s in doc['sections'] for u in walk(s)}


def span(uid):
    a = unit_line.get(uid) or 0
    later = [x for x in starts if x > a]
    return a, (later[0] if later else a + 400)


def flex(text, edges=True):
    """A pattern for text of the structure file as it stands on a scan line (dashes and quotation marks vary)."""
    p = re.escape(text).replace(r'\-\-', '(?:--|—)').replace('"', '["“”]').replace("'", "['‘’]").replace(r'\ ', ' +')
    if edges:
        p = ('(?<![A-Za-z])' if text[:1].isalpha() else '') + p + ('(?![A-Za-z])' if text[-1:].isalpha() else '')
    return re.compile(p)


groups = collections.OrderedDict()
for r in csv.DictReader(open(review, encoding='utf-8', newline=''), delimiter='\t'):
    groups.setdefault(int(r['row']), []).append(r)

found, undecided = [], []
for n, places in groups.items():
    if n in skip:
        continue
    was, now, note = places[0]['as_scanned'], row_fix.get(n, places[0]['planned_fix']), places[0]['note']
    why = f"misreading approved in the review of {dec['approved']}, row {n}" + (f": {note}" if note and 'every such place' not in note else '')
    if 'every such place' in note:
        rx, repl = RULES['date'] if re.search(r'\d,\d', was) else RULES['I N']
        hits = [(no, m.group(), rx.sub(repl, m.group())) for no, t in lines for m in rx.finditer(t)]
        if len(hits) != len(places):
            undecided.append((n, was, now, f'the rule finds {len(hits)} places on the scan lines, the table has {len(places)}', []))
        found += [(no, a, b, why) for no, a, b in hits]
        continue
    rx = flex(was)
    hits = [(no, m.group()) for no, t in lines for m in rx.finditer(t)]
    if len(hits) == len(places):
        found += [(no, a, line_fix.get(n, {}).get(no, now), why) for no, a in hits]
        continue
    # ---- some places run over a line end
    done = [(no, a, line_fix.get(n, {}).get(no, now), why) for no, a in hits]
    left = len(places) - len(hits)
    w_tok, n_tok = was.split(' '), now.split(' ')
    cross = []
    for uid in dict.fromkeys(p['unit'] for p in places):
        a, z = span(uid)
        for no in [x for x in order if a <= x < z]:
            t, t2 = by_no[no], by_no.get(nxt.get(no), '')
            for i in range(1, len(w_tok)):                      # the break falls between two words
                A, B = ' '.join(w_tok[:i]), ' '.join(w_tok[i:])
                if flex(A, False).search(t) and re.search(flex(A, False).pattern + '$', t) and re.match(flex(B, False).pattern, t2):
                    if len(w_tok) == len(n_tok):
                        A2, B2 = ' '.join(n_tok[:i]), ' '.join(n_tok[i:])
                        cross.append([(no, re.search(flex(A, False).pattern + '$', t).group(), A2, why),
                                      (nxt[no], re.match(flex(B, False).pattern, t2).group(), B2, why)])
                    else:
                        cross.append(('ask', no, t[-60:], t2[:60]))
            if ' ' not in was:
                for i in range(2, len(was) - 1):                # one word broken by a hyphen at the line end
                    A, B = was[:i], was[i:]
                    if t.endswith(A + '-') and t2.startswith(B) and not t[:-len(A) - 1][-1:].isalpha():
                        if now == A + '-' + B:                   # the hyphen belongs: the whole word goes on the first line,
                            tail = re.match(re.escape(B) + r'([^\sA-Za-z0-9]*)(?: |$)', t2)   # with any mark after it
                            if tail:
                                cross.append([(no, A + '-', now + tail.group(1), why), (nxt[no], tail.group(), '', why)])
                            else:
                                cross.append(('ask', no, t[-60:], t2[:60]))
                        elif now.endswith(B):
                            cross.append([(no, A + '-', now[:-len(B)] + '-', why)])
                        elif now.startswith(A):
                            cross.append([(nxt[no], B, now[len(A):], why)])
                        else:
                            cross.append(('ask', no, t[-60:], t2[:60]))
    good = [c for c in cross if isinstance(c, list)]
    if len(good) == left and not any(isinstance(c, tuple) for c in cross):
        for c in good:
            done += [x for x in c if x[1] != x[2]]
        found += done
    else:
        undecided.append((n, was, now, f'{len(places)} places in the table, {len(hits)} found on single lines', cross))

found.sort()
with open(out, 'w', encoding='utf-8', newline='') as fh:
    fh.write('line\twas\tnow\twhy\n')
    for no, a, b, why in found:
        assert '\t' not in a + b + why
        fh.write(f'{no}\t{a}\t{b}\t{why}\n')
per_line = collections.Counter(no for no, *_ in found)
print(f'{len(found)} corrections on {len(per_line)} scan lines -> {out}')
print(f'{len(undecided)} rows left for a decision:')
for n, was, now, what, cross in undecided:
    print(f'  row {n}: {was!r} -> {now!r}: {what}')
    for c in cross:
        print('     ', c if isinstance(c, tuple) else [x[:3] for x in c])
    for p in groups[n][:3]:
        a, z = span(p['unit'])
        first = was.split(' ')[0]
        near = [(no, by_no[no][-70:], by_no.get(nxt.get(no), '')[:50]) for no in order if a <= no < z and (first[:4] in by_no[no] or was[-4:] in by_no[no])][:3]
        print(f"      {p['unit']} lines {a}-{z}: {near}")
