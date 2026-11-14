#!/usr/bin/env python3
"""Count the project entries in each WRDA structure file.

Usage: count_projects.py STRUCTURE_DIR [OUT.csv]

This is a count of entries the acts themselves set apart, not a coding of
what each provision does. An ENTRY is one of:

  * a unit whose heading names a place: one part of the heading, split at
    commas and at "and", is the name of a State, the District of Columbia or
    a territory ("Pearl River Basin, Mississippi"; "(5) Hamilton Airfield,
    California.--"). Scan misreadings of a State name are matched loosely.
  * a numbered row of a project table (the acts of 2014 and later);
  * in WRDA 1986, an unnumbered item under a centred project name, and each
    paragraph under a State name in the deauthorization list of sec. 1002.

Only the innermost entry counts: if a place-named unit holds place-named
sub-units or table rows, the sub-units are counted and the parent is not.
A section with a place-named heading and no entries inside it counts once.

Two figures per act:
  AUTHORIZATION LIST   entries inside the act's project-authorization
                       section(s), named in AUTH below. From 2016 on that
                       section ends with a table headed "Modifications and
                       other projects"; its rows are shown separately.
  ALL ENTRIES          entries anywhere in the act

Known limits: a project named only in running text ("the project for
navigation, X Harbor, Maine, is modified ...") has no heading and is not
counted; a heading that names a place is counted whatever the provision does
(study, modification, land transfer, naming, deauthorization).
"""
import csv, difflib, glob, json, pathlib, re, sys

STATES = """Alabama Alaska Arizona Arkansas California Colorado Connecticut Delaware Florida Georgia Hawaii Idaho
Illinois Indiana Iowa Kansas Kentucky Louisiana Maine Maryland Massachusetts Michigan Minnesota Mississippi Missouri
Montana Nebraska Nevada New_Hampshire New_Jersey New_Mexico New_York North_Carolina North_Dakota Ohio Oklahoma Oregon
Pennsylvania Rhode_Island South_Carolina South_Dakota Tennessee Texas Utah Vermont Virginia Washington West_Virginia
Wisconsin Wyoming District_of_Columbia Puerto_Rico Guam American_Samoa Virgin_Islands United_States_Virgin_Islands
Northern_Mariana_Islands Commonwealth_of_the_Northern_Mariana_Islands D.C. DC""".split()
STATES = {s.replace('_', ' ').upper() for s in STATES}

# The project-authorization section(s) of each act, by section number.
AUTH = {
    'WRDA 1986': ['201', '202', '301', '401', '501', '601'],
    'WRDA 1988': ['3'], 'WRDA 1990': ['101'], 'WRDA 1992': ['101'], 'WRDA 1996': ['101'], 'WRDA 1999': ['101'],
    'WRDA 2000': ['101'], 'WRDA 2007': ['1001'], 'WRRDA 2014': ['7002'], 'WRDA 2016': ['1401'], 'WRDA 2018': ['1401'],
    'WRDA 2020': ['401'], 'WRDA 2022': ['8401'], 'WRDA 2024': ['1401'],
    'WRDA 2026 House bill': ['401'], 'WRDA 2026 Senate bill': ['1401'],
}


# Entries in an authorization list whose heading names no State, added by hand.
EXTRA = {
    '1990.101.b': 'subsection (b) is itself one project (Los Angeles County Drainage Area, California); its heading is '
                  '"Project subject to favorable report of the Chief of Engineers"',
    '2000.101.b.11': 'heading reads "Delaware coast from cape henlopen to fenwick island", with no State after a comma',
}


def is_state(part, loose):
    p = re.sub(r'[^A-Z. ]', '', part.upper()).strip()
    p = re.sub(r'^(THE )?(STATE|STATES|COMMONWEALTH|TERRITORY) OF ', '', p)
    if p in STATES:
        return True
    return loose and len(p) >= 4 and bool(difflib.get_close_matches(p, STATES, n=1, cutoff=0.8))


def names_place(heading, loose=False):
    if not heading:
        return False
    parts = [q for part in heading.split(',') for q in re.split(r'\band\b|\bAND\b|&', part)]
    return any(is_state(q, loose) for q in parts[1:])


def entries(d, act, loose, in_group=False):
    """Innermost entries in unit d: list of (id, kind, name)."""
    found = []
    for c in d.get('children', []):
        found += entries(c, act, loose, in_group or d['type'] == 'group')
    for rows in d.get('tables', []):
        kind = 'table row (modification)' if re.search(r'modif', d['heading'] or '', re.I) else 'table row'
        found += [(f"{d['id']}#row{r['number']}", kind, f"{r['name']}, {r['state']}") for r in rows]
    if found:
        return found
    if d['type'] == 'group':
        return []
    if in_group and d['type'] == 'item':
        return [(d['id'], 'item under a State name', d['own_text'][:60])]
    if act == 'WRDA 1986' and d['type'] == 'item' and d['heading']:
        return [(d['id'], 'item under a project name', d['heading'])]
    if names_place(d['heading'], loose) or d['id'] in EXTRA:
        return [(d['id'], d['type'], d['heading'])]
    return []


def main(folder, out=None):
    rows, table = [], []
    for f in sorted(glob.glob(str(pathlib.Path(folder) / '*.structure.json'))):
        doc = json.load(open(f, encoding='utf-8'))
        act = doc['act']
        loose = 'lines_table' in doc['source']['text'] and act != 'WRDA 1986'      # scans
        auth, every = [], []
        for sec in doc['sections']:
            e = entries(sec, act, loose)
            every += e
            if sec['number'] in AUTH[act] and not sec['id'].endswith('-2nd'):
                auth += e
        for e in every:
            rows.append([act, e[0], e[1], e[2], 'yes' if e in auth else ''])
        mods = sum(1 for e in auth if 'modification' in e[1])
        table.append((act, len(doc['sections']), len(auth) - mods, mods, len(every)))
    print(f"{'Act':24s} {'sections':>8s} {'authorization list':>19s} {'+ modifications':>16s} {'all entries':>12s}")
    for act, n, a, m, e in sorted(table, key=lambda r: (re.search(r'\d{4}', r[0]).group(), r[0])):
        print(f'{act:24s} {n:8d} {a:19d} {m:16d} {e:12d}')
    if out:
        with open(out, 'w', newline='', encoding='utf-8') as fh:
            w = csv.writer(fh, lineterminator='\n')
            w.writerow(['act', 'unit', 'kind', 'name', 'in_authorization_list'])
            w.writerows(rows)


if __name__ == '__main__':
    if len(sys.argv) not in (2, 3):
        sys.exit(__doc__)
    main(*sys.argv[1:])
