#!/usr/bin/env python3
"""Build the review table of proposed corrections to the scan of WRDA 1988.
Usage: misreads_review_1988.py STRUCTURE_DIR OUT_DIR
Reads the structure file; writes OUT_DIR/WRDA 1988 misreads to review.html and .tsv. Changes nothing else.

Each entry: (as scanned, planned fix, how sure, note). how sure: yes = plain misreading; look = my best
reading, worth your eye; page = I would read the page image before fixing."""
import collections
import csv
import html
import json
import pathlib
import re
import sys

sdir, odir = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
Y, L, P = 'yes', 'look', 'page'
FIX = [
    # ---- sec. 1(b), the contents list
    ('Montiana', 'Montana', Y, ''), ('C^ifin-nia', 'California', Y, ''), ('Kiammmee', 'Kissimmee', Y, ''),
    ('lUdgefield', 'Ridgefield', Y, ''),
    # ---- sec. 3
    ('flood control. Lower Mission', 'flood control, Lower Mission', Y, 'a period where the comma belongs'),
    ('CaUfomia', 'California', Y, ''), ('fu^t', 'first', Y, ''),
    ('FT. FIERCE', 'FT. PIERCE', Y, 'the text of the item says Ft. Pierce'),
    ('navigation. Ft. Pierce', 'navigation, Ft. Pierce', Y, 'period for comma'),
    ('December 14. 1987', 'December 14, 1987', Y, 'period for comma'), ('EIngineers', 'Engineers', Y, ''),
    ('navigation. Port Sutton', 'navigation, Port Sutton', Y, 'period for comma'),
    ('E n ^ e e r s ,', 'Engineers,', Y, 'letter-spaced by the scan'), ('witii', 'with', Y, ''),
    ('CmCAGOLAND', 'CHICAGOLAND', Y, 'you confirmed'), ('LOWER omo RIVER', 'LOWER OHIO RIVER', Y, 'you confirmed'),
    ('navigation. Lower Ohio', 'navigation, Lower Ohio', Y, 'period for comma'),
    ('52 and 53. Illinois', '52 and 53, Illinois', Y, 'period for comma'),
    ('August 20, 1986. at', 'August 20, 1986, at', Y, 'period for comma'), ('tile costs', 'the costs', Y, ''),
    ('flood control. Hazard', 'flood control, Hazard', Y, 'period for comma'), ('foi*', 'for', Y, ''), ('Cjrpress', 'Cypress', Y, ''),
    ('(bX2XC)', '(b)(2)(C)', Y, ''), ('(bX2XD)', '(b)(2)(D)', Y, ''), ('(2XA)', '(2)(A)', Y, ''), ('"ofthisAct";and', '"of this Act"; and', Y, ''), ('(2XB)', '(2)(B)', Y, ''),
    # ---- sec. 4
    ('bv', 'by', Y, ''), ("Act.*'.", 'Act.".', L, 'a closing quotation mark'), ('K I N G HARBOR', 'KING HARBOR', Y, 'letter-spaced'),
    ('Los ANGELES', 'LOS ANGELES', Y, 'small capitals read as small letters'), ('mclude', 'include', Y, ''),
    ('parsigraph', 'paragraph', Y, ''), ('ANNAPOUS', 'ANNAPOLIS', Y, ''), ('authorised', 'authorized', L, 'z read as s'),
    ('fiood', 'flood', Y, ''), ('flood control. Brush Creek', 'flood control, Brush Creek', Y, 'period for comma'),
    ('flood control. Coyote', 'flood control, Coyote', Y, 'period for comma'), ('navigation. White River', 'navigation, White River', Y, 'period for comma'),
    ('I N GENERAL,--For*', 'IN GENERAL.—For', Y, 'the dash was misread, so the build missed this heading; it will be read as one'), ('control. Redwood River', 'control, Redwood River', Y, 'period for comma'), ('canying', 'carrying', Y, ''),
    ('RTVER', 'RIVER', Y, ''), ('GuLPPORT', 'GULFPORT', Y, ''), ('fix>m', 'from', Y, ''), ('Elnvironmental', 'Environmental', Y, ''),
    ('firom', 'from', Y, ''), ('fi:t>m', 'from', Y, ''), ('h ^ t h', 'health', Y, 'letter-spaced'), ('carr5dng', 'carrying', Y, ''),
    ('carrjdng', 'carrying', Y, ''), ('theplan', 'the plan', Y, ''), ('APPUCABILTTY', 'APPLICABILITY', Y, ''),
    ('T H I N LAYER', 'THIN LAYER', Y, 'letter-spaced'), ('sufHcient', 'sufficient', Y, ''), ('LiBBY', 'LIBBY', Y, ''),
    ('constructiiig', 'constructing', Y, ''),
    ('WATBEWAYS, WASHiNGTON.^The', 'WATERWAYS, WASHINGTON.—The', Y, 'the dash was lost, so the build missed this heading; it will be read as one'),
    ('headiiig', 'heading', Y, ''), ('TAOOMA', 'TACOMA', Y, ''), ('(100 Stat. 40%)', '(100 Stat. 40??)', P, 'a page number of the 1986 act'),
    ('strikmg', 'striking', Y, ''), ('aU', 'all', Y, ''), ('WYNOOCHBE', 'WYNOOCHEE', Y, ''), ('Fedeial', 'Federal', Y, ''),
    ('tiie', 'the', Y, ''), ('"OMR&R^\')', '"OMR&R")', L, 'a closing quotation mark'), ('LmcrrATiONS', 'LIMITATIONS', Y, ''),
    ('r^ulations', 'regulations', Y, ''), ('r^ulation', 'regulation', Y, ''), ('Stirtes', 'States', Y, ''),
    ('n^ligence', 'negligence', Y, ''), ('PubUc', 'Public', Y, ''),
    # ---- secs. 5-37
    ('RES-ERVOIRS', 'RESERVOIRS', Y, 'a line-break hyphen kept'), ('purg oses', 'purposes', Y, ''), ('the ecretary', 'the Secretary', Y, ''),
    ('Virgina', 'Virginia', L, 'unless the print itself has the slip'), ('Qoi)', '(?)', P, 'a subsection label'),
    ('technolo^', 'technology', Y, ''), ('Stetes', 'States', Y, ''), ('Iti determining', 'In determining', Y, ''),
    ('insertmg', 'inserting', Y, ''), ('flscal', 'fiscal', Y, ''), ('1962d- 5a', '1962d-5a', Y, 'a stray space in a U.S.C. section number'),
    ('AoDmONAL', 'ADDITIONAL', Y, ''), ('tiois', 'this', Y, ''), ('applicsd>le', 'applicable', Y, ''), ('recovexy', 'recovery', Y, ''),
    ("' ^ v e the power", '"have the power', L, 'an opening quotation mark and "have"'), ('Provided^', 'Provided,', L, 'the usual ": Provided, That"'),
    ('R^ina', 'Regina', Y, 'the vessel A. Regina'), ('Baige', 'Barge', Y, ''), ('con^tent', 'consistent', Y, ''),
    ('R ^ u r c e s', 'Resources', Y, 'letter-spaced'), ('b^inning', 'beginning', Y, ''), ('proiect', 'project', Y, ''),
    ('Secretaiy', 'Secretary', Y, ''), ('genersd', 'general', Y, ''), ('ADDmoNAL', 'ADDITIONAL', Y, ''), ('l ^ a l', 'legal', Y, 'letter-spaced'),
    ('mcEisures', 'measures', Y, ''), ('Cllalifomia', 'California', Y, ''),
    # ---- sec. 38, the Philadelphia descriptions
    ('r^onal', 'regional', Y, ''), ('proposied', 'proposed', Y, ''), ('Penn- ^Ivania', 'Pennsylvania', Y, ''), ('t<^ether', 'together', Y, ''),
    ('Philadel- §hia', 'Philadelphia', Y, ''), (', urveyor', ', Surveyor', Y, ''), ('R^ulator', 'Regulator', Y, ''), ('R^^ulator', 'Regulator', Y, ''),
    ('BegiiauDg', 'Beginning', Y, ''), ('B^inning', 'Beginning', Y, ''), ('d^rees', 'degrees', Y, ''), ('d^^rees', 'degrees', Y, ''),
    ('d^ree', 'degree', Y, ''), ('d^prees', 'degrees', Y, ''), ('d^^-ees', 'degrees', Y, ''), ('fh>m', 'from', Y, ''), ('wesC', 'west,', L, 'the comma was read as C'),
    ('Se^^ember', 'September', Y, ''), ('£uid', 'and', Y, ''), ('second^', 'seconds', Y, ''), ('distence', 'distance', Y, ''),
    ('nortii', 'north', Y, ''), ('Dk^rict', 'District', Y, ''), ('eeisterly', 'easterly', Y, ''), ('Shackainaxon', 'Shackamaxon', Y, 'spelt Shackamaxon three times nearby'),
    ('RiVERCENTER', 'RIVERCENTER', L, 'looks like a heading in small capitals'), ('establii^hed', 'established', Y, ''),
    ('APPUCABIUTY', 'APPLICABILITY', Y, ''), ('commenccMl', 'commenced', Y, ''),
    ('IVa inches', '? inches', P, 'a fraction of an inch'), ('1 Vz inches', '? inches', P, 'a fraction'), ('IVs inches', '? inches', P, 'a fraction'),
    ('IVz inches', '? inches', P, 'a fraction'), ('iy2 inches', '? inches', P, 'a fraction'), ('OV* inch', '? inch', P, 'a fraction'),
    ('OVs inch', '? inch', P, 'a fraction'), ('ZVs inches', '? inches', P, 'a fraction'), ('^Vs inches', '? inches', P, 'a fraction'),
    ('9V& inches', '? inches', P, 'a fraction'), ('8V& inches', '? inches', P, 'a fraction'), ('SVs inches', '? inches', P, 'a fraction'),
    ('feer^% inches', 'feet ? inches', P, 'a fraction'),
    # ---- secs. 39-54
    ('PUBUC', 'PUBLIC', Y, ''), ('descrU)ed', 'described', Y, ''), ('comer', 'corner', Y, ''), ('d^ri^«es', 'degrees', Y, ''),
    ('(>opsey', 'Cropsey', Y, 'spelt Cropsey three times nearby'), ('nortti', 'north', Y, ''), ('Ot>)', '(b)', Y, 'a subsection label'),
    ('Ot))', '(b)', Y, 'a subsection label'), ('RQ>ORT', 'REPORT', Y, ''), ('enact* ment', 'enactment', Y, ''), ('stcmdards', 'standards', Y, ''),
    ('RESTORATION OP WETLANDS', 'RESTORATION OF WETLANDS', Y, ''), ('f£e', 'the', Y, ''), ('froia', 'from', Y, ''), ('Secret^uy', 'Secretary', Y, ''),
    ('EInvironmental', 'Environmental', Y, ''), ('quaUty', 'quality', Y, ''), ('.^^n^r', 'Agency', Y, 'Illinois Environmental Protection Agency'),
    ('Withm', 'Within', Y, ''), ('appUcation', 'application', Y, ''), ('qusdity', 'quality', Y, ''), ('afifinnative', 'affirmative', Y, ''),
    ('authoraed', 'authorized', Y, ''), ('Blu^ttone', 'Bluestone', Y, ''), ('Lake project. West Virginia', 'Lake project, West Virginia', Y, 'period for comma'),
    ('feasUile', 'feasible', Y, ''), ('Actand', 'Act and', Y, ''), ('r^arding', 'regarding', Y, ''), ('suh;basins', 'sub-basins', L, 'or "subbasins"'),
    ('fQj. j ^ g ^ York', 'for New York', P, 'my guess; the scan is unreadable here'), ('MiANUs', 'MIANUS', Y, ''), ('ILU-NOis', 'ILLINOIS', Y, ''),
    ('ALGOBIA', 'ALGOMA', Y, 'the text says Algoma'), ('DBAUTHORIZATION', 'DEAUTHORIZATION', Y, ''), ('pubUc', 'public', Y, ''),
    ('IMIAINTENANCE', 'MAINTENANCE', Y, ''), ('BREAK-WATERS', 'BREAKWATERS', Y, 'a line-break hyphen kept'), ('responsibiUties', 'responsibilities', Y, ''),
    ('Notwithstandii^', 'Notwithstanding', Y, ''), ('lOOKbXD', '1001(b)(1)', Y, 'the section the U.S.C. cite beside it belongs to'), ('R^M>urces', 'Resources', Y, ''),
    ('(33U.S.C.579a(bXl))', '(33 U.S.C. 579a(b)(1))', Y, ''), ('(33U.S.C.701S)', '(33 U.S.C. 701s)', L, 'section 701s is the small-projects authority'),
    ('PORT OP HICKMAN', 'PORT OF HICKMAN', Y, ''),
]
RULES = [(r'\b(\d{1,2}),((?:19|20)\d\d)\b', r'\1, \2', Y, 'a date printed without the space after its comma'),
         (r'\bI N (?=GENERAL(?!,--))', 'IN ', Y, 'letter-spaced')]

doc = json.load(open(sdir / 'WRDA 1988.structure.json', encoding='utf-8'))


def walk(u):
    yield u
    for c in u.get('children', []):
        yield from walk(c)


units = [u for s in doc['sections'] for u in walk(s)]


def cite(uid):
    parts = uid.split('.')[1:]
    return 'sec. ' + parts[0] + ''.join(f'({p})' if not re.fullmatch(r'i\d+', p) else f', item {int(p[1:])}' for p in parts[1:])


def find(pattern):
    hits = []
    for u in units:
        for fld in ('heading', 'own_text', 'trailing_text'):
            t = u.get(fld) or ''
            for m in pattern.finditer(t):
                hits.append((u['id'], fld, t, m.start(), m.end()))
    return hits


rows = []
for was, now, sure, note in FIX:
    pat = re.compile(('(?<![A-Za-z])' if was[0].isalpha() else '') + re.escape(was).replace('\\ ', '\\s+') + ('(?![A-Za-z])' if was[-1].isalpha() else ''))
    rows.append((was, now, sure, note, find(pat)))
for rx, repl, sure, note in RULES:
    hits = find(re.compile(rx))
    ex = hits[0][2][hits[0][3]:hits[0][4]] if hits else rx
    rows.append((ex, re.sub(rx, repl, ex), sure, note + ' (every such place)', hits))
rows.sort(key=lambda r: (min((units.index(next(u for u in units if u['id'] == h[0])) for h in r[4]), default=10 ** 6)))

missing = [r[0] for r in rows if not r[4]]
E = html.escape
tr, tsv = [], []
for n, (was, now, sure, note, hits) in enumerate(rows, 1):
    ctx = []
    for uid, fld, t, a, b in hits[:2]:
        ctx.append(f'<div class="c">…{E(t[max(0, a - 48):a])}<mark>{E(t[a:b])}</mark>{E(t[b:b + 48])}…</div>')
    where = cite(hits[0][0]) + (' heading' if hits and hits[0][1] == 'heading' else '') if hits else 'NOT FOUND'
    more = f'<div class="n">{len(hits)} places</div>' if len(hits) > 1 else ''
    tr.append(f'<tr class="{sure}" data-n="{n}"><td class="no">{n}</td><td>{E(where)}{more}</td><td class="w">{E(was)}</td>'
              f'<td class="f">{E(now)}</td><td>{"".join(ctx)}</td><td class="s">{ {"yes": "", "look": "worth a look", "page": "needs the page"}[sure] }'
              f'{("<div class=n>" + E(note) + "</div>") if note else ""}</td>'
              f'<td class="t"><label><input type="checkbox"> no</label><input type="text" placeholder="note"></td></tr>')
    for uid, fld, t, a, b in hits:
        tsv.append({'row': n, 'unit': uid, 'field': fld, 'as_scanned': was, 'planned_fix': now, 'sure': sure, 'note': note,
                    'context': (t[max(0, a - 48):a] + '[' + t[a:b] + ']' + t[b:b + 48]).replace('\n', ' ')})
n_places = sum(len(r[4]) for r in rows)
page = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><title>WRDA 1988 misreads to review</title>
<style>
body {{ font: 14px/1.45 -apple-system, "Segoe UI", sans-serif; margin: 24px auto; max-width: 1280px; padding: 0 16px; color: #1c1c1c; }}
h1 {{ font-size: 20px; }} p {{ max-width: 60em; }}
table {{ border-collapse: collapse; width: 100%; }} th, td {{ border-bottom: 1px solid #ddd; padding: 5px 8px; vertical-align: top; text-align: left; }}
th {{ position: sticky; top: 0; background: #f3f2ee; }} .no {{ color: #777; text-align: right; }}
.w {{ font-family: ui-monospace, Menlo, monospace; color: #9b1c1c; white-space: nowrap; }} .f {{ font-family: ui-monospace, Menlo, monospace; color: #14622d; white-space: nowrap; }}
.c {{ font-family: Georgia, serif; }} mark {{ background: #ffe58a; }} .n {{ font-size: 12px; color: #777; }}
tr.look .s {{ color: #8a5a00; }} tr.page .s {{ color: #9b1c1c; }} tr.down td {{ background: #fdeceb; }}
.t {{ white-space: nowrap; }} .t input[type=text] {{ width: 150px; margin-left: 6px; }}
#out {{ width: 100%; height: 70px; font: 13px ui-monospace, Menlo, monospace; }} .bar {{ position: sticky; bottom: 0; background: #fff; padding: 10px 0; border-top: 2px solid #1c1c1c; }}
</style></head><body>
<h1>WRDA 1988: words the scan misread, and the planned fix</h1>
<p>{len(rows)} rows covering {n_places} places in the act. Red is what the scan gives; green is what I would put. A row with several places is fixed the same way in each.
Tick <b>no</b> on any row you do not want fixed as shown, and add a note if you like. Everything not ticked counts as a thumbs up.
When you are done, copy the line in the box at the bottom and paste it to me.</p>
<p><b>Worth a look</b> marks my best reading where the print could differ. <b>Needs the page</b> marks places the scan cannot settle (fractions of an inch, a page number): I would read the page image and come back with the reading before changing them.</p>
<table><thead><tr><th>#</th><th>Where</th><th>As scanned</th><th>Planned fix</th><th>Context</th><th>How sure</th><th>Your call</th></tr></thead>
<tbody>{"".join(tr)}</tbody></table>
<div class="bar"><textarea id="out" readonly></textarea></div>
<script>
const KEY = "wrda1988-misreads";
let saved = {{}}; try {{ saved = JSON.parse(localStorage.getItem(KEY) || "{{}}"); }} catch (e) {{}}
const rows = [...document.querySelectorAll("tbody tr")];
function tell() {{
  const no = [], notes = []; const state = {{}};
  rows.forEach(r => {{ const n = r.dataset.n, box = r.querySelector("input[type=checkbox]"), note = r.querySelector("input[type=text]").value.trim();
    r.classList.toggle("down", box.checked); if (box.checked) no.push(n); if (note) notes.push(n + ": " + note); if (box.checked || note) state[n] = [box.checked, note]; }});
  document.getElementById("out").value = "WRDA 1988 misreads. Thumbs down on rows: " + (no.join(", ") || "none") + ". Notes: " + (notes.join(" | ") || "none") + ". All other rows: thumbs up.";
  try {{ localStorage.setItem(KEY, JSON.stringify(state)); }} catch (e) {{}}
}}
rows.forEach(r => {{ const s = saved[r.dataset.n]; if (s) {{ r.querySelector("input[type=checkbox]").checked = s[0]; r.querySelector("input[type=text]").value = s[1]; }}
  r.addEventListener("input", tell); }});
tell();
</script></body></html>'''
odir.mkdir(parents=True, exist_ok=True)
(odir / 'WRDA 1988 misreads to review.html').write_text(page, encoding='utf-8')
with open(odir / 'WRDA 1988 misreads to review.tsv', 'w', encoding='utf-8', newline='') as fh:
    w = csv.DictWriter(fh, fieldnames=['row', 'unit', 'field', 'as_scanned', 'planned_fix', 'sure', 'note', 'context'], delimiter='\t')
    w.writeheader()
    w.writerows(tsv)
print(f'{len(rows)} rows, {n_places} places; by how sure: {dict(collections.Counter(r[2] for r in rows))}')
print('NOT FOUND in the text (my slip, to correct):', missing or 'none')
many = [(r[0], len(r[4])) for r in rows if len(r[4]) > 1]
print('rows with several places:', many)
# ---- things still to look at before the table is final
allt = [(u['id'], t) for u in units for t in (u.get('heading') or '', u.get('own_text') or '') if t]
print("'I N' places:", [(i[5:], t[m.start():m.end() + 22]) for i, t in allt for m in re.finditer(r'\bI N\b', t)])
print('other X-for-")(" places:', sorted({m.group() for i, t in allt for m in re.finditer(r'\(\w{1,3}X\w{1,3}\)', t)}))
print('period then a place name:', [(i[5:], t[max(0, m.start() - 22):m.end() + 26]) for i, t in allt
      for m in re.finditer(r'\b(?:control|navigation|protection|restoration|project|purposes|River|Harbor|Lake|Creek|Dam)\. (?!The |Such |Any |In |If |No |Not |Nothing |Upon |For |Before |Within |Each |This |Section |Subsection |Paragraph |Notwithstanding |After |Funds |There |Sec\. |Subject |Except |To |As |At |On |With |Non|Any|All |An |A |Of |Until |Unless |Prior |During |Beginning |Thence |Running )[A-Z][a-z]+', t)][:25])
