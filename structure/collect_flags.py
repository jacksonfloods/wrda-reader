#!/usr/bin/env python3
"""Gather the flags of every structure file into one list to read.

Usage: collect_flags.py STRUCTURE_DIR OUT.md
"""
import glob, json, pathlib, re, sys

ORDER = ['GAP IN NUMBERING', 'LABEL USED TWICE', 'LABEL OUT OF ORDER', 'LABEL FITS NO LIST', 'DAMAGED LABEL, NO LIST',
         'SECTION NOT FOUND', 'CONTENTS LIST MISMATCH', 'HEADING DIFFERS FROM CONTENTS', 'HEADING WITHOUT PERIOD',
         'QUOTATION LEFT OPEN', 'INDENT REPAIRED', 'LABEL REPAIRED']
MEANING = {
    'GAP IN NUMBERING': 'A label skips ahead. Either the act misnumbers or a paragraph was missed.',
    'LABEL USED TWICE': 'The same label twice in one list. The second gets "-2nd" in its id.',
    'LABEL OUT OF ORDER': 'A label that fits no list where it is printed; kept in place.',
    'LABEL FITS NO LIST': 'A paragraph opens with a label that belongs to no list; kept as text of the unit above.',
    'DAMAGED LABEL, NO LIST': 'A paragraph opens with what may be a misread label; kept as text.',
    'QUOTATION LEFT OPEN': 'A quotation mark with no partner (scans drop them). The paragraphs between the mark and '
                           'the next labelled paragraph or section were kept as quoted text, not split into units.',
    'INDENT REPAIRED': 'A labelled paragraph printed at the wrong indent; placed by its label.',
    'LABEL REPAIRED': 'The scan misread a label; its place in the list says what it is.',
    'HEADING DIFFERS FROM CONTENTS': 'A section heading and its entry in the contents list read differently, and neither is recorded as the misreading.',
}


def main(folder, out):
    lines = ['# Flags from the WRDA structure builds', '',
             'Made by `collect_flags.py` from the structure files. Source line numbers are lines of the source text '
             '(the `.htm` file, or the `.lines.tsv` table for the scans).', '']
    docs = [json.load(open(f, encoding='utf-8')) for f in glob.glob(str(pathlib.Path(folder) / '*.structure.json'))]
    docs.sort(key=lambda d: (re.search(r'\d{4}', d['act']).group(), d['act']))
    lines += ['| Act | Sections | Units | To check | Repaired by the build |', '|---|---|---|---|---|']
    for d in docs:
        fl = d.get('flags', [])
        rep = sum(1 for f in fl if 'REPAIRED' in f['kind'])
        lines.append(f"| {d['act']} | {d['counts']['sections']} | {d['counts']['units']} | {len(fl) - rep} | {rep} |")
    for d in docs:
        fl = d.get('flags', [])
        lines += ['', f"## {d['act']}", '']
        if not fl:
            lines.append('No flags.' if 'flags' in d else 'Built by `build_1986.py`; its judgment calls are in `WRDA 1986.build_log.txt`.')
            continue
        for kind in ORDER + sorted({f['kind'] for f in fl} - set(ORDER)):
            these = [f for f in fl if f['kind'] == kind]
            if not these:
                continue
            lines += [f'**{kind.capitalize()}** ({len(these)}). {MEANING.get(kind, "")}', '']
            lines += [f"- `{f['unit'] or '-'}`, source line {f['source_line'] or '-'}: {f['what']}" for f in these]
            lines.append('')
        fixed = [(s['id'], s['heading_as_read'], s['heading']) for s in d['sections'] if 'heading_as_read' in s]
        if fixed:
            lines += [f'**Section headings corrected** ({len(fixed)}). The scan misread the heading; the wording is taken '
                      'from the contents list. Worth a glance against the page.', '',
                      '| Section | As the scan reads | In the file |', '|---|---|---|']
            lines += [f'| `{i}` | {a} | {h} |' for i, a, h in fixed]
    pathlib.Path(out).write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(f'{sum(len(d.get("flags", [])) for d in docs)} flags in {len(docs)} files -> {out}')


if __name__ == '__main__':
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(*sys.argv[1:])
