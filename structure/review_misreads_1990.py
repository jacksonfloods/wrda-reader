#!/usr/bin/env python3
"""Build the review table of proposed corrections to the scan of WRDA 1990 (same form as review_misreads_1988.py).
Usage: misreads_review_1988.py STRUCTURE_DIR OUT_DIR
Reads the structure file; writes OUT_DIR/WRDA 1990 misreads to review.html and .tsv. Changes nothing else.

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
    ('commercifd', 'commercial', Y, ''), ('Gteorge', 'George', Y, ''),
    # ---- sec. 101
    ('annusil', 'annual', Y, ''), ('flood control. Coyote', 'flood control, Coyote', Y, 'a period where the comma belongs'),
    ('OcEANSiDE', 'OCEANSIDE', Y, 'small capitals read as small letters'), ('M C A L P I N E LOCK', 'MCALPINE LOCK', Y, 'letter-spaced by the scan'),
    ('flood control. Fort', 'flood control, Fort', Y, 'period for comma'), ('Wajnie', 'Wayne', Y, ''),
    ('navigation. Great Lakes', 'navigation, Great Lakes', Y, 'period for comma'), ('MICHI-GAN', 'MICHIGAN', Y, 'a line-break hyphen kept'),
    ('CoLDWATER', 'COLDWATER', Y, ''), ('flood control. River Des Peres', 'flood control, River Des Peres', Y, 'period for comma'),
    ('Peissaic', 'Passaic', Y, ''), ('medn', 'main', Y, 'read from the page'), ('APPUCABIUTY', 'APPLICABILITY', Y, ''),
    ('evEduate', 'evaluate', Y, ''), ('EsTABUSHMENT', 'ESTABLISHMENT', Y, ''), ('shedl', 'shall', Y, 'read from the page'),
    ('flood control. Upper Jordan', 'flood control, Upper Jordan', Y, 'period for comma'), ('BuENA', 'BUENA', Y, ''),
    # ---- sec. 102
    ('flood control. Village Creek', 'flood control, Village Creek', Y, 'period for comma'), ('KoDiAK', 'KODIAK', Y, ''),
    ('Los ANGELES', 'LOS ANGELES', Y, 'small capitals read as small letters'), ('fiood', 'flood', Y, ''), ('traiLs', 'trails', Y, ''),
    ('RiVER', 'RIVER', Y, ''), ('MARY-LAND', 'MARYLAND', Y, 'a line-break hyphen kept'), ('remsiin', 'remain', Y, ''),
    ('navigation. Manatee', 'navigation, Manatee', Y, 'period for comma'), ('WILDUFE', 'WILDLIFE', Y, ''),
    ('B E T W E E N F O R T P E C K D A M ,', 'BETWEEN FORT PECK DAM,', Y, 'letter-spaced'), ('N E W', 'NEW', Y, 'letter-spaced'),
    ('sdternative', 'alternative', Y, ''), ('O N OCEAN', 'ON OCEAN', Y, 'letter-spaced; read from the page'),
    ('Environmentel', 'Environmental', Y, ''), ('Clommunication', 'Communication', Y, ''),
    # ---- secs. 103-108
    ('prOJect', 'project', Y, ''), ('flood control. Old Sulfur', 'flood control, Old Sulfur', Y, 'period for comma'),
    ('SAYAN', 'SAVAN', Y, 'read from the page: Savan Gut'), ('HiLLSBORO', 'HILLSBORO', Y, ''),
    ('flood control. Little Calumet', 'flood control, Little Calumet', Y, 'period for comma'), ('ginalysis', 'analysis', Y, ''),
    ('(DoNNEAUT', 'CONNEAUT', Y, 'read from the page; the build missed this heading and will now read it'), ('C!onneaut', 'Conneaut', Y, ''),
    ('such project. Congress', 'such project, Congress', Y, 'period for comma; read from the page'),
    # ---- sec. 116
    ('origindestination', 'origin-destination', L, 'the print breaks it at a line end after "origin-"; the line above prints "origin-to-destination"'),
    ('NoRCO', 'NORCO', Y, ''), ('KissiMMEE', 'KISSIMMEE', Y, ''), ('(BOUNTY', 'COUNTY', Y, 'the text of the item says Nassau County'),
    ('BuFFUMViLLE', 'BUFFUMVILLE', Y, ''), ('QUAUTY', 'QUALITY', Y, ''), ('Reclsmiation', 'Reclamation', Y, ''), ('£is', 'as', Y, ''),
    ('carrjdng', 'carrying', Y, ''), ('MIN-NESOTA', 'MINNESOTA', Y, 'a line-break hyphen kept'), ('AcEQUiAS', 'ACEQUIAS', Y, ''),
    ('FEASIBIUTY', 'FEASIBILITY', Y, ''), ('appHcation', 'application', Y, ''),
    # ---- sec. 119
    ('water supply project. Big River', 'water supply project, Big River', Y, 'period for comma'),
    ("N39''5855E", 'N39°5855E', Y, 'read from the page: a degree sign; the print has no minute or second marks in these bearings'),
    ('CoNNEAUT', 'CONNEAUT', Y, ''), ('l3dng', 'lying', Y, ''),
    # ---- title II
    ('subsection 0>)', 'subsection (b)', Y, 'read from the page'), ('OP', 'OF', Y, ''),
    # ---- title III
    ('(aXl)', '(a)(1)', Y, ''), ('(IXA)', '(1)(A)', Y, ''), ('ABIUTY T O PAY', 'ABILITY TO PAY', Y, ''), ('(aX2)', '(a)(2)', Y, ''),
    ('(2XC)', '(2)(C)', Y, ''), ('GrOALS AND ACTION P L A N', 'GOALS AND ACTION PLAN', Y, ''),
    ('approf >riate', 'appropriate', Y, 'read from the page'), ('wetands', 'wetlands', Y, ''), ('Secretery', 'Secretary', Y, ''),
    ('ESTABUSHMENT', 'ESTABLISHMENT', Y, ''), ('To THE', 'TO THE', Y, 'small capitals read as small letters'), ('To CONGRESS', 'TO CONGRESS', Y, 'small capitals read as small letters'), ('DEUNEATORS', 'DELINEATORS', Y, ''),
    ('Identif3dng', 'Identifying', Y, ''), ('1991;or', '1991; or', Y, 'read from the page'),
    ('waterdependent', 'water-dependent', Y, 'the print has "water-dependent" in mid-line in the paragraph before'), ('CosT', 'COST', Y, ''),
    ('APPUCABILITY', 'APPLICABILITY', Y, ''), ('(Dhief', 'Chief', Y, ''), ('PuBUC', 'PUBLIC', Y, ''),
    ('this subsection. including', 'this subsection, including', Y, 'period for comma'), ('NoNPROJECT', 'NONPROJECT', Y, ''),
    ('subsection Oa)', 'subsection (a)', Y, ''), ('C!OST', 'COST', Y, ''), ('21(KaX2)', '210(a)(2)', Y, 'read from the page'),
    ('purpOSO', 'purpose', Y, ''), ('storgige', 'storage', Y, ''), ('Low INCOME', 'LOW INCOME', Y, 'small capitals read as small letters'),
    # ---- title IV
    ('m a n ^ e', 'manage', Y, 'letter-spaced'), ('pajmtient', 'payment', Y, ''), ('includ- ing', 'including', Y, 'a word broken at a line end'),
    ('subsection Qo)', 'subsection (b)', Y, 'read from the page'), ('storsige', 'storage', Y, ''), ('mansigement', 'management', Y, ''),
    ('Ex OFFICIO', 'EX OFFICIO', Y, 'small capitals read as small letters'), ('LIABIUTY', 'LIABILITY', Y, ''),
    ('^^.^^ ^j^g', 'Act, the', Y, 'read from the page'), ('EUenville', 'Ellenville', Y, ''),
]
RULES = [(r'\b(\d{1,2}),((?:19|20)\d\d)\b', r'\1, \2', Y, 'a date printed without the space after its comma'),
         (r'\bI N (?=GENERAL(?!,--))', 'IN ', Y, 'letter-spaced')]

doc = json.load(open(sdir / 'WRDA 1990.structure.json', encoding='utf-8'))


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
page = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><title>WRDA 1990 misreads to review</title>
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
<h1>WRDA 1990: words the scan misread, and the planned fix</h1>
<p>{len(rows)} rows covering {n_places} places in the act. Red is what the scan gives; green is what I would put. A row with several places is fixed the same way in each.
Tick <b>no</b> on any row you do not want fixed as shown, and add a note if you like. Everything not ticked counts as a thumbs up.
When you are done, copy the line in the box at the bottom and paste it to me.</p>
<p><b>Worth a look</b> marks my best reading where the print could differ. Where the scan could not settle a word, I read the page image first: those rows say "read from the page".</p>
<table><thead><tr><th>#</th><th>Where</th><th>As scanned</th><th>Planned fix</th><th>Context</th><th>How sure</th><th>Your call</th></tr></thead>
<tbody>{"".join(tr)}</tbody></table>
<div class="bar"><textarea id="out" readonly></textarea></div>
<script>
const KEY = "wrda1990-misreads";
let saved = {{}}; try {{ saved = JSON.parse(localStorage.getItem(KEY) || "{{}}"); }} catch (e) {{}}
const rows = [...document.querySelectorAll("tbody tr")];
function tell() {{
  const no = [], notes = []; const state = {{}};
  rows.forEach(r => {{ const n = r.dataset.n, box = r.querySelector("input[type=checkbox]"), note = r.querySelector("input[type=text]").value.trim();
    r.classList.toggle("down", box.checked); if (box.checked) no.push(n); if (note) notes.push(n + ": " + note); if (box.checked || note) state[n] = [box.checked, note]; }});
  document.getElementById("out").value = "WRDA 1990 misreads. Thumbs down on rows: " + (no.join(", ") || "none") + ". Notes: " + (notes.join(" | ") || "none") + ". All other rows: thumbs up.";
  try {{ localStorage.setItem(KEY, JSON.stringify(state)); }} catch (e) {{}}
}}
rows.forEach(r => {{ const s = saved[r.dataset.n]; if (s) {{ r.querySelector("input[type=checkbox]").checked = s[0]; r.querySelector("input[type=text]").value = s[1]; }}
  r.addEventListener("input", tell); }});
tell();
</script></body></html>'''
odir.mkdir(parents=True, exist_ok=True)
(odir / 'WRDA 1990 misreads to review.html').write_text(page, encoding='utf-8')
with open(odir / 'WRDA 1990 misreads to review.tsv', 'w', encoding='utf-8', newline='') as fh:
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
