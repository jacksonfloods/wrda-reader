# WRDA structure files

Turns one Water Resources Development Act into a structure file: the act as a tree of sections, subsections, paragraphs and unnumbered items, with every unit's text and an id that codes can be keyed to. WRDA 1986 has its own build script; the later acts share two (below).

## Where the files are

The commands in this file are run from the top folder of the repository. They read the sources from `corpus/` and write to `work/`, two folders you make there; they are not part of the repository. Any other folders will do, because every script takes its folders as arguments. `sources.csv` lists where each source file comes from and the name to save it under.

## Adding an act

A new WRDA whose text govinfo publishes takes four steps.

1. **Get the text.** On govinfo, open the public law or the bill and save its text version (`.htm`) in `corpus/raw`. `sources.csv` shows the pattern of the addresses and of the file names.
2. **Describe it.** Add an entry to `ACTS` in `build_text.py`: a key (the year), the act's name, its public law number, date and Statutes at Large volume, the file name, and the file's SHA-256 (`shasum -a 256 FILE`). If the WRDA is one part of a larger law, give the first and last line of that part as `cut`.
3. **Build it and read the checks.**
   ```sh
   python structure/build_text.py KEY corpus/raw work/structure
   ```
   The build stops if any character of the source is not accounted for, and it compares the section headings with the act's contents list. Its log, `WRDA KEY.build_log.txt`, lists every check and every place where the build was in doubt.
4. **Give it to the reader.**
   ```sh
   python reader/refresh_data.py work/structure
   ```

An act that exists only as a Statutes at Large page scan goes through `extract_scan_lines.py` and `build_scan.py` instead (see "The acts after 1986"), and its misread words need a review of their own.

## Rebuild WRDA 1986

Run from the top folder of the repository (see "Where the files are"):

```sh
conda env create -f structure/wrda_structure_env.yml   # once
conda activate wrda-structure

# 1. PDF -> table of printed lines with each line's exact indent
python structure/extract_lines.py \
  "corpus/raw/1986, Congress, WRDA 1986 (PL 99-662).pdf" \
  "corpus/text/1986, Congress, WRDA 1986 (PL 99-662).lines.tsv"

# 2. Statutes at Large scan -> page text (used only for page numbers and checks)
pdftotext -layout \
  "corpus/statutes_at_large/1986, Congress, WRDA 1986 (PL 99-662), 100 Stat 4082.pdf" \
  "corpus/statutes_at_large/1986, Congress, WRDA 1986 (PL 99-662), 100 Stat 4082.txt"

# 3. Build
python structure/build_1986.py \
  "corpus/text/1986, Congress, WRDA 1986 (PL 99-662).lines.tsv" \
  "corpus/statutes_at_large/1986, Congress, WRDA 1986 (PL 99-662), 100 Stat 4082.txt" \
  work/structure

# 4. Check
python structure/validate_1986.py \
  "work/structure/WRDA 1986.structure.json" \
  "corpus/statutes_at_large/1986, Congress, WRDA 1986 (PL 99-662), 100 Stat 4082.txt"
```

Steps 1 and 2 only need rerunning if their outputs are lost; both are stored in the corpus. Steps 3 and 4 use only the Python standard library.

A rebuild is the same if these hashes come out the same (they are printed by the scripts and saved in `WRDA 1986.build_log.txt`):

| File | SHA-256 |
|---|---|
| `corpus/raw/1986 … (PL 99-662).pdf` (working text) | `f49cf269217e5e03b2abb2e4695f752f0d4aaaacd4d39685116c73bb316d7f36` |
| `corpus/text/1986 … .lines.tsv` | `0f602e98c51d786b0d193b7e8c011fd950d0211abd12f401176fe261e7a64653` |
| `corpus/statutes_at_large/1986 … 100 Stat 4082.pdf` (official print) | `46929f0bf398ffcc0d636b37b3362decfba2b634fb87f32bf3bd15b5106d88cb` |
| `corpus/statutes_at_large/1986 … 100 Stat 4082.txt` | `0a986e9c5eda56c2d1e4e44a8a1ba9b6d02e3a2dd68098948986747ee4458a4d` |
| `work/structure/WRDA 1986.structure.json` | `2e7f7c67e6bf298a35bd84796c56ac4febdfdaef8574b34cbb531fdb12593abc` |
| `work/structure/WRDA 1986.units.csv` | `a0b7c504c2cdcb30be4416966295bc9fbd1afdbe0a058bec56239ab4f2b3b262` |

The build refuses an input whose hash differs from the one pinned in `build_1986.py` (override with `--force`). The inputs were made with poppler 26.04.0.

## Outputs

- `WRDA 1986.structure.json`: the act as a tree.
- `WRDA 1986.units.csv`: the same 1,825 units as a flat table (id, parent, level, type, label, heading, print page, opening words), for reading in a spreadsheet.
- `WRDA 1986.build_log.txt`: hashes, counts and each judgment call the build made.
- `WRDA 1986.validation.txt`: the result of the 46 checks.

## What a unit holds

| Field | Meaning |
|---|---|
| `id` | Built from the section down: `1986.401.a`, `1986.401.e.3.B.iv`. Titles are not part of the id. |
| `type` | `section`, `subsection` (a), `paragraph` (1), `subparagraph` (A), `clause` (i), `item` (no printed label), `group` (a State heading in sec. 1002). |
| `label` | As printed: `SEC. 401.`, `(a)`. `null` for items and groups. |
| `heading` | As printed. For an item, the centred project name. |
| `own_text` | The unit's own words, before any sub-units. Paragraphs are separated by a line break. |
| `children` | Sub-units, in order. |
| `trailing_text` | Words of this unit that come after its sub-units (the sentence resuming). |
| `stat_page` | Page of the Statutes at Large the unit starts on. |
| `source_page`, `source_line` | Where it starts in the working PDF and in the corpus text file. |
| `note`, `supplement` | Present only on units with an oddity (below). |

Sections also carry `number`, `title` and `title_heading`.

Units with no printed label are numbered by position within their parent: items `i01`, `i02`…, groups `g01`…. A number or label the act prints twice gets `-2nd` on its second use.

## How the act is read

The rules are at the top of `build_1986.py`. In short: the working PDF prints every line at an exact indent, and the indent gives the depth. First lines of paragraphs sit at 2, 6, 10 or 14 spaces; later lines at 0, 4, 8 or 12; centred lines (headings) sit at `(79 − length) // 2`. Labels are placed by sequence within the list at their indent. Quoted matter that the act inserts into other laws is kept whole inside the unit that inserts it.

## What is specific to 1986

All of it is in the block of constants at the top of `build_1986.py`:

- **Section 1002** lists deauthorized projects under centred State names. States are groups; each paragraph under a State is an item.
- **Titles X and XII** use the heading-less form `Sec. 1001. (a) …`.
- **One correction**: a closing quotation mark is added at the end of sec. 1107(b), where the working PDF leaves a quotation open. It is recorded under `corrections` in the file.
- **One supplement**: the working PDF prints `[TABLE GOES HERE]` in sec. 909(a). The 28-row table is supplied from 100 Stat. 4188.
- **Three label oddities, kept as printed** (the Statutes at Large print agrees): sec. 204 has two subsections (e); Title XIV has a section numbered 805; sec. 1117(b)(2) lists (A), (B), (3).

## Checks

`build_1986.py` stops unless every non-space character of the input appears in the output exactly once and in order. `validate_1986.py` then checks:

1. the file against itself (ids, section numbering by title, label order in every list, page order);
2. the file against facts read by hand from the act (for example the six lists of projects "subject to favorable report");
3. the file against the Statutes at Large print: all 273 unnumbered headings are on the print page the file gives them, and 98.6% of the file's words appear in the print in the same order. The only passage of the print missing from the working text is the sec. 909 table.

## Not in the structure file

- Cross-references ("subject to section 903(a) of this Act").
- Which units count as one project.
- Any coding (section type, form of authorization).

These are judgments or derived data and belong in separate files keyed by `id`.

## Known limits of the 1986 working text

- Some paragraph headings lost their capitals in the working PDF (`Pearl river basin, including shoccoe, mississippi`). They are kept as that PDF prints them.
- Margin notes of the Statutes at Large are not part of the act and are not in the file.

## The acts after 1986

Three more scripts cover the other fourteen acts and the two 2026 bills. They share `wrda_tree.py`, which places each paragraph in the tree by its labels. Run from the top folder of the repository:

```sh
# 1988, 1990, 1992: Statutes at Large scans
python structure/extract_scan_lines.py "corpus/raw/1988, Congress, WRDA 1988 (PL 100-676).pdf" \
  "corpus/text/1988, Congress, WRDA 1988 (PL 100-676).lines.tsv"      # once per scan; needs poppler
python structure/build_scan.py all corpus/text work/structure

# 1996 to 2024 and the 2026 House and Senate bills: govinfo text
python structure/build_text.py all corpus/raw work/structure

# the flags of every act in one list, and the project counts
python structure/collect_flags.py work/structure work/structure/FLAGS.md
python structure/count_projects.py work/structure work/structure/project_entries.csv
```

Each build writes the same three files as 1986 (`.structure.json`, `.units.csv`, `.build_log.txt`). The checks are part of the build and are listed at the top of each build log. Every build refuses an input whose hash differs from the one pinned in its `ACTS` table (override with `--force`), and a rebuild gives byte-identical files.

### What differs from the 1986 file

- `stat_page` comes from the page marks in the govinfo text, or from the running heads of the scan. The bills have none.
- `headings` lists the division, title and subtitle lines; each section carries `title`, `subtitle` and so on as labels.
- `flags` lists every place the build doubted or repaired. `FLAGS.md` gathers them.
- Labels `(aa)` and `(AA)` under a subclause have the types `labelled_item` and `labelled_subitem` (`item` already means a unit with no printed label).
- A unit with two lists gives the later lists ids ending `-list2`, `-list3`. Text that stands between two sub-units is kept in place as an unnumbered item marked `between_units`.
- Project tables (2014 and later) are kept as printed in the text of the unit above them; their numbered rows are also listed under `tables`.
- Where a larger law holds the WRDA (2016, 2018, 2020, 2022, 2024, the Senate bill), only the WRDA part is read. `part_of_source_used` and `source.text.lines` say which.

### How a label is placed

Labels in a list run in order at one indent. A label is placed, in this order: as the next label of an open list at its depth; as the first label of a new list; as a repeat of the label before it (flagged); as a label that skips ahead (placed, and the gap flagged); or it fits nothing (kept, flagged). This is the numbering check: "(c)(1)" followed by "(c)(3)" is flagged as a gap.

### Scans

`extract_scan_lines.py` drops the running head and margin notes, finds the body column on each page from its right edge, and writes one row per printed line with its indent (`x0`) and where it ends (`x1`). `….lines.trimmed.txt` lists what was dropped.

`build_scan.py` reads the layout before the characters:

- A line that stops short of the right edge ends a paragraph. The indent of the next line gives its depth. 1988 and 1990 set first lines at 10, 30, 50 pt; 1992 sets them at 20, 40, 60 pt.
- Section headings are found by position (capitals at the left edge, opening "SEC") and numbered by order against the act's own contents list. All 54, 70 and 126 sections are found.
- A damaged label where the next label of a list belongs is taken as that label ("Ot))" after "(a)" is "(b)"; "(1)" after "(k)" is "(l)" when "(m)" follows). Each repair is flagged with what the scan read.
- A section heading that differs from its contents entry is settled in `HEADINGS` (the heading was misread) or `CONTENTS_MISREAD` (the contents entry was). A new disagreement is flagged.
- Words broken at a line end are joined. Misread ordinary words are left as the scan gives them, with two exceptions corrected on 2026-11-13 (builder 2.2), on every line where they occur: `CAUFORNIA` for CALIFORNIA (15 paragraph headings: 1 in 1988, 10 in 1990, 4 in 1992) and `^Ebccept` for `Except` (the opening of 1988 sec. 3(a)). Each is listed under `corrections` in its file, with the scan line and what the scan read. The heading of 1992 sec. 355 has the same misreading on the scan; it was already taken from the contents list, and its `heading_as_read` keeps `CAUFORNIA`.
- **Boundary descriptions (2026-11-15).** A boundary or land description (metes and bounds, bearings, tracts) is text of the piece it describes. Its unlabelled paragraphs are never unnumbered items. This holds in 15 sections, listed in `NO_ITEMS` in `wrda_tree.py` and in `build_1986.py`: 1986 secs. 1006, 1125 and 1127; 1988 secs. 38 and 39; 1990 secs. 119 and 201; 1992 secs. 116 and 335; 1996 secs. 364 and 501; 1999 sec. 563; 2000 secs. 346 and 348; 2018 sec. 1331. Where a description runs on between two lists of numbered courses (2000 sec. 346(b)), the words between them are kept with the course before them. The change took away 151 unnumbered items (1986: 15; 1988: 11; 1990: 6; 1992: 4; 1996: 20; 1999: 47; 2000: 18; 2018: 30). Each of the 15 sections kept the same words in the same order, and no other section changed. Unnumbered items remain only in WRDA 1986 (519, the project entries) and at one place in WRDA 1999 (sec. 606(c)). The inspection sample was drawn again after this change (`sample_pages.py` with seed 20261115).
- **Words broken over a page end (2026-11-14).** In the govinfo text of WRDA 1996 three words are split over a page end with no hyphen: "appro" / "priate," in sec. 107, "tur" / "bines," in sec. 511(b)(1) and "Flor" / "ida" in sec. 528(c)(2)(A). `CORRECTIONS` in `build_text.py` puts each whole word on the first line (two entries a word), and the structure file lists them under `corrections`. A search of the text-based acts for two fragments that join into a common word found no others.
- **Reviewed misreadings (builder 2.3, 2026-11-13).** For WRDA 1988 the author went through a table of every word the scan looked to have misread. `find_misreads.py` finds the candidates; `review_misreads_1988.py` holds the reading given to each and builds the table; `misreads_to_corrections.py` places each approved fix on its scan line. The 279 approved fixes are in `corrections_1988.tsv` beside the scripts. `build_scan.py` applies them, with the corrections listed in the script, before the text is parsed, never inside a longer word, and lists each under `corrections` in the structure file. A correction may run over a line end (the break is moved so that the word joins) and may empty a line of scanner noise, which is then dropped (one line, in sec. 6(a)). Two corrections restore run-in headings whose dash the scan had lost (secs. 4(s) and 7(a)). Fractions of an inch are written `7 1/8`. The table, the author's answers and the page readings are kept with the author's working files, not in this repository. The statute's italics are not recorded anywhere in these files. WRDA 1990 was reviewed the same way the same day (104 rows, all approved; 143 fixes in `corrections_1990.tsv`, with `review_misreads_1990.py` and `find_misreads_more.py`; words the scan could not settle were read from the page image before the table was shown). From builder 2.4 each row of a corrections table fixes one place, so one line may carry the same fix twice (1990 line 633). A word the print breaks at a line end with a hyphen that belongs (origin-destination, water-dependent) is put whole on the first line. One heading was restored in 1990 (sec. 107(a)(9), CONNEAUT, OHIO). WRDA 1992 was reviewed the same day (485 rows covering 640 places, all approved; 653 fixes in `corrections_1992.tsv`, 32 of them placed by hand where a place runs over a line end; `review_misreads_1992.py`). Two headings were restored (secs. 104(2), CALCASIEU RIVER, LOUISIANA, and 327(a), STUDY). A printer's mark that had been read into sec. 107(a)(1) is dropped. The 1992 file now has 881 pieces, one fewer than before. Mending "inundated by high" in sec. 343(b)(1) put back the words the scan had split off as a false piece (343.b.i01). Two mended quotation marks changed the structure: "ten" in sec. 107(a)(1) closes its quotation, so the false piece 107.a.3.i01 goes back into the quoted amendment of 107(a)(3). In sec. 116(5) the closing quotation mark of "for other purposes" is mended, so the boundary description after 116(5) becomes its own piece (116.i02), as the one after 116(4) already was (116.i01). The two "quotation left open" flags at those places are gone. The date rule also mended the act's closing line ("Approved October 31, 1992."). The headings of secs. 314, 317 and 335 are taken from the contents list (`HEADINGS`), so they are mended through their contents entries. When a word is moved whole to the first line, the punctuation after it moves with it (OPERATIONS-RESPONSE, in sec. 103(d)). Nine more misreadings that none of the tables had were approved on 2026-11-14 and added by hand, three in each act (their `why` says "found after the review"): seven letter-spaced headings (1988 secs. 4(q), 27(a), 53(c); 1990 secs. 104(a)(1), 408(a); 1992 sec. 115(a)(3) and (6)), "6S U.S.C." for 33 U.S.C. in 1990 sec. 321 (the usual citation of sec. 206 of the Flood Control Act of 1960; not checked against the page), and "round Water Basin" for Ground in 1992 sec. 114(a). Only those nine fields changed; pieces, flags and project counts did not. `find_misreads_more.py` finds letter-spacing only in runs of four or more single letters, so a shorter run (N E W, T O) can slip through.

### Project counts

`count_projects.py` counts entries the acts set apart: a unit whose heading names a place (a State after a comma), a numbered row of a project table, and in 1986 the unnumbered items. Only the innermost entry counts. It reports the entries in each act's project-authorization section and the entries in the whole act, and writes every entry to `project_entries.csv`. It is a count of headings, not a coding: a project named only in running text is not counted, and a place-named heading counts whatever the provision does.

## Highlighted PDFs (`highlight_pdf.py`)

Makes a copy of an act's PDF with the structure drawn on the page, for
checking the reading against the print. The source PDF is not changed.

    conda activate wrda-structure
    python highlight_pdf.py STRUCTURE.json PDF LINES.tsv OUT.pdf

- The first line of every unit is highlighted in the colour of its level
  (key at the foot of each page); unnumbered items and State names included.
- The unit's id without the year ("401.c.3") is printed small to the left of
  the line. Where two units start on one line the line is divided at the
  second label and only the first id is printed; each highlight's note holds
  its own id.
- Orange box: label or heading repaired by the build, or text corrected.
  Red box: a flag to check. Both carry a note with the details.
- The script regroups the PDF's text layer into lines and stops if any line
  differs from LINES.tsv, and it stops if the number of highlights differs
  from the number of units in the structure file.

Two ways of placing the highlights:

- 1986, 1988, 1990, 1992 (built from the PDF): pass the act's LINES.tsv. Every
  unit's line is known exactly, and the count of highlights must equal the
  count of units.
- 1996, 1999, 2000, 2007 (built from govinfo text): pass `-` for LINES.tsv.
  The slip-law PDF is in the corpus `raw/` folder beside the `.htm`. Each unit
  is found on its Statutes at Large page by its opening words; a unit that is
  not found is listed and left unmarked. Not found on 2026-11-12: one unit,
  an unnumbered item in WRDA 1999 sec. 606(c), whose text starts in the
  middle of a printed line.

The acts of 2014 and later are not highlighted: they are checked against the
government XML instead (next section). Outputs go in
`work/structure/highlighted/`.

## Check against the government XML (`validate_xml.py`)

    python validate_xml.py STRUCTURE_DIR RAW_DIR OUT.md

For WRRDA 2014 and later, and for the 2026 bills, govinfo publishes XML in
which each section, subsection, paragraph ... is a tagged element (USLM for
public laws, the bill DTD for bills). The files are in the corpus `raw/`
folder beside the `.htm` text. The structure files are built without the XML,
so it is an independent reading: the script compares, section by section, the
labelled units in order (depth, level name, label) and then the headings.
The result is written to `work/structure/XML_VALIDATION.md`.

Builder 2.1 (2026-11-12) fixed two faults this check found: a unit heading
holding a semicolon, or followed by a margin note before its dash, was not
read as a heading (71 headings across all acts); and one label split by a
margin note, WRDA 2020 sec. 511(b)(3)(B)(v), was missed.
