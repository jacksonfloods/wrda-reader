m# Water Resources Development Act (WRDA) Reader


Have you yearned to read project authorizations across multiple WRDAs side by side? Conduct a boolean search across the acts? The wait is over. Vibe-coded and human-tested, WRDA Reader is a free tool, usable on the cloud or locally on your machine, that allows you to read, search, and compare Water Resources Development Acts (WRDAs).

**[WRDA Reader Online](https://wrda-reader.streamlit.app/)**

Water Resources Development Acts are the laws in which Congress authorizes the water projects, studies and policies of the U.S. Army Corps of Engineers. The Congressional Research Service has a short [primer on the acts](https://www.congress.gov/crs-product/IF11322). The reader holds 14 of them, from 1986 to 2024, and the House and Senate WRDA bills of 2026.

More WRDAs can be added with the parsing Python scripts in `structure/`, which turn the text of an act into a file the reader can show.

## What it does

- **Reads any piece of any act.** Pick an act from the list, or type an address in the box: `1986 401(a)`, `2007 3104`, or a citation as printed, such as `section 903(c) of the Water Resources Development Act of 1986`.
- **Lines pieces up side by side.** Open as many panels as you like, each on its own piece, and collapse the ones you are not reading.
- **Searches every act at once.** Type a word or a phrase. Every piece that has it is listed, act by act.
- **Runs boolean searches.** Put each phrase in quotation marks and join them with `AND`, `OR` or `NOT`: `"if the Secretary determines" AND "construct"`. Pieces that match in their own words come first. Pieces that match only together with the pieces under them come second, and each says where the words are.
- **Shares a line-up as a link.** The page address holds the panels on the screen. Copy it to share them, or bookmark it to come back. A line-up can also be downloaded as a small file and opened again later.

## About the text

- **What is included:** WRDA 1986, 1988, 1990, 1992, 1996, 1999, 2000 and 2007; WRRDA 2014; WRDA 2016, 2018, 2020, 2022 and 2024; and the House and Senate WRDA bills of 2026, which are not enacted. Where a WRDA was enacted inside a larger law, only the WRDA is included.
- **As enacted:** each act reads as it was passed. Later amendments are not worked into earlier acts.
- **Where the text comes from:** the acts from 1996 on and the 2026 bills come from the text published by govinfo. The 1988, 1990 and 1992 acts come from scans of the Statutes at Large; they were read through for misread words and corrected, but some may remain. The 1986 act comes from a typed copy.
- **Not an official source:** this is a reading aid. Check anything you rely on against the Statutes at Large or govinfo before you cite it.

Found a misread word or a wrong address? Please open an issue.

## Run it on your own computer

You only need this to work offline or to change the reader.

```sh
git clone https://github.com/jacksonfloods/wrda-reader.git
cd wrda-reader
pip install -r reader/requirements.txt        # or: conda env create -f reader/wrda_reader_env.yml
streamlit run reader/app.py
```

To save line-ups in a folder of yours, or to read your own structure files:

```sh
streamlit run reader/app.py -- --lineups FOLDER --data FOLDER
```

## What is in this repository

| Folder or file | What it is |
|---|---|
| `reader/app.py` | the page (Streamlit) |
| `reader/reader_logic.py` | reading the files, addresses, searches, line-ups and the pages as HTML; it does not use Streamlit |
| `reader/page.js`, `reader/page.css` | the panel shown in the browser |
| `reader/data/` | one structure file for each act (`*.structure.json`) |
| `reader/test_reader_logic.py`, `reader/browser_check.py` | the reader's tests; `reader/wrda_reader_dev_env.yml` sets up what they need |
| `reader/refresh_data.py` | copies rebuilt structure files into `reader/data/` |
| `structure/` | the parsing scripts that build the structure files, their checks, and the corrections made to the scanned acts |

## The structure files

Each file in `reader/data/` holds one act as a tree: its sections, and under them the subsections, paragraphs and so on. Every piece has an address (such as `1986.401.e.3`), its label and heading, its own words, and the page of the Statutes at Large it starts on where the source gives one. The files are plain JSON and can be used without the reader.

`structure/README.md` explains how the files are built and checked, and how to add an act.

## Licence

MIT (see `LICENSE`): use it, change it and share it freely, and keep the copyright notice. The acts themselves are public laws of the United States and are in the public domain.

## Author

Juan Fernandez
