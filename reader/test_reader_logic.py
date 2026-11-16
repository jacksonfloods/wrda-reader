"""Tests for the reader's box, its searches, its history and the pages that changed with them.

Run:  python -m pytest -q test_reader_logic.py
They read the structure files in the data folder beside this file and write nothing.
Set WRDA_READER_DATA to read the files in another folder.
"""
import html
import os
import re

import pytest

import reader_logic as L

DATA = os.environ.get("WRDA_READER_DATA") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


@pytest.fixture(scope="module")
def lib():
    if not os.path.isdir(DATA):
        pytest.skip("no structure files at " + DATA)
    library = L.load_library(DATA)
    assert library.acts, library.problems
    return library


def search_panel(query, whole=False):
    return {"kind": "search", "query": query, "whole": whole, "opened": [], "more": {}, "closed": []}


# ---------------------------------------------------------------- the box
def test_an_address_goes_there(lib):
    assert L.read_box(lib, "1986 401(a)") == L.Found("piece", "1986.401.a")
    assert L.read_box(lib, "1986.401.a").address == "1986.401.a"
    f = L.read_box(lib, "section 903(c) of the Water Resources Development Act of 1986")
    assert (f.kind, f.address) == ("piece", "1986.903.c")
    assert L.read_box(lib, "").kind == "shelf"
    assert L.read_box(lib, "1986") == L.Found("contents", "1986")
    assert L.read_box(lib, "WRDA 2007") == L.Found("contents", "2007")


def test_a_bare_number_means_the_act_on_the_page(lib):
    assert L.read_box(lib, "903", "1986").address == "1986.903"
    assert L.read_box(lib, "3104", "2007") == L.Found("piece", "2007.3104")
    assert L.read_box(lib, "(c)", "1986", "1986.903").address == "1986.903.c"


def test_a_bare_number_with_no_act_is_a_search_that_lists_the_sections(lib):
    f = L.read_box(lib, "3104")
    assert (f.kind, f.address, f.said) == ("search", "3104", None)
    words, quoted, numbered = L.search_plan(lib, f.address)
    assert (words, quoted) == ("3104", False)
    assert "2007.3104" in numbered
    assert all(lib.pieces[a].depth == 0 and str(lib.pieces[a].unit["number"]) == "3104" for a in numbered)
    assert L.is_bare_number("sec. 3104") and not L.is_bare_number('"3104"') and not L.is_bare_number("levee")


def test_a_number_the_act_on_the_page_lacks_is_a_search_that_says_so(lib):
    f = L.read_box(lib, "3104", "1986")
    assert f.kind == "search" and "has no section 3104" in f.said
    assert "2007.3104" in L.search_plan(lib, f.address)[2]
    f = L.read_box(lib, "2007 9999")
    assert f.kind == "search" and "has no section 9999" in f.said


def test_a_piece_named_in_every_act(lib):
    numbered = L.numbered_sections(lib, "401(a)")
    assert "1986.401.a" in numbered
    assert all(a.endswith(".401.a") for a in numbered)
    assert L.numbered_sections(lib, "levee") == []


def test_words_are_looked_for(lib):
    assert L.read_box(lib, "nonnavigab") == L.Found("search", "nonnavigab")
    assert L.read_box(lib, "Pearl River", "2007", "2007.3104").kind == "search"
    # a number followed by words is words, even where the act on the page has that section
    assert L.read_box(lib, "401 permit", "1986").kind == "search"
    assert L.read_box(lib, "100-year flood", "1986").kind == "search"
    assert L.read_box(lib, "1,000", "1986").kind == "search"
    assert L.read_box(lib, "33 U.S.C. 2201", "1986").kind == "search"


def test_quotation_marks_always_mean_words(lib):
    f = L.read_box(lib, '"1986"')
    assert (f.kind, f.address) == ("search", '"1986"')
    assert L.search_plan(lib, f.address) == ("1986", True, [])
    assert L.search_plan(lib, "“3104”") == ("3104", True, [])
    assert L.read_box(lib, '"401"', "1986").kind == "search"


# ---------------------------------------------------------------- the pages
def test_results_page_lists_numbered_sections_first(lib):
    page = L.render_results(lib, search_panel("3104", whole=True))
    assert "Sections numbered 3104" in page
    assert 'class="nsec" data-go="2007.3104"' in page
    assert page.index("Sections numbered 3104") < page.index('class="group"')
    assert "data-here=" in page and "data-open=" in page and "data-hit=" in page
    quoted = L.render_results(lib, search_panel('"3104"', whole=True))
    assert "Sections numbered" not in quoted and "data-hit=" in quoted


def test_results_page_for_words(lib):
    page = L.render_results(lib, search_panel("nonnavigab"))
    assert "Sections numbered" not in page
    res = L.search(lib, "nonnavigab")
    assert res.total > 0 and f"<b>{res.total:,}</b>" in page


def test_a_parent_line_opens_to_all_of_its_own_words(lib):
    parent = "1986.401.a"
    child = lib.pieces[parent].unit["children"][1]["id"]
    lead = lib.pieces[parent].unit["own_text"].split("\n")[0]
    assert len(lead) > 160, "this test needs a parent whose words are cut short"
    whole_lead = html.escape(L._quotes(lead))

    shut = L.render_piece(lib, child)
    assert f'<div class="above" data-above="{parent}"' in shut
    assert 'class="above open"' not in shut
    assert whole_lead not in shut
    assert 'class="above" data-go' not in shut            # a click on the line no longer travels up

    opened = L.render_piece(lib, child, above=[parent])
    assert f'<div class="above open" data-above="{parent}"' in opened
    assert whole_lead in opened
    assert f'<div class="above" data-above="1986.401"' in opened    # the section's own line stays short
    # the way up is the line at the top of the page
    assert f'data-go="{parent}" data-from="{child}"' in opened


def test_open_parents_survive_the_page_address_and_a_saved_line_up(lib):
    child = lib.pieces["1986.401.a"].unit["children"][1]["id"]
    panels = [L.new_panel("piece", piece=child, closed=[child], above=["1986.401", "1986.401.a"], mark="levee")]
    back = L.panels_from_tokens(L.panels_to_tokens(panels))
    assert back == panels
    name, again, problems = L.lineup_from_dict(L.lineup_to_dict(lib, "t", panels))
    assert (name, problems) == ("t", []) and again == panels
    plain = [L.new_panel("piece", piece=child, closed=[], above=[], mark=None)]
    assert L.panels_from_tokens(L.panels_to_tokens(plain)) == plain


def test_a_collapsed_panel_survives_the_page_address_and_a_saved_line_up(lib):
    panels = [L.new_panel("piece", piece="1986.401.a", closed=[], above=[], mark=None, thin=True),
              L.new_panel("contents", act="1986", thin=True),
              L.new_panel("search", query="levee", whole=False, opened=[], thin=True),
              L.new_panel("shelf", thin=True),
              L.new_panel("contents", act="2007")]
    tokens = L.panels_to_tokens(panels)
    assert [tok.startswith(">") for tok in tokens] == [True, True, True, True, False]
    assert L.panels_from_tokens(tokens) == panels
    name, again, problems = L.lineup_from_dict(L.lineup_to_dict(lib, "t", panels))
    assert problems == [] and again == panels


def test_the_spine_names_what_the_panel_holds(lib):
    assert L.spine_text(lib, L.new_panel("shelf")) == "All acts"
    assert L.spine_text(lib, L.new_panel("contents", act="1986")) == lib.acts["1986"].name
    assert L.spine_text(lib, L.new_panel("search", query='"levee"')) == "Search: \u201clevee\u201d"
    assert L.spine_text(lib, L.new_panel("piece", piece="1986.401.a")).startswith(lib.acts["1986"].name + " sec. 401(a)")


# ---------------------------------------------------------------- back and forward
def test_history_goes_back_and_forward():
    p = L.new_panel("shelf")
    before = L.snapshot(p, 0)
    L.set_page(p, "contents", act="1986")
    assert L.remember(p, before)
    before = L.snapshot(p, 120)
    L.set_page(p, "piece", piece="1986.401", closed=[], above=[], mark=None)
    assert L.remember(p, before)

    assert L.go_back(p, 40)
    assert (p["kind"], p["act"], p["y"]) == ("contents", "1986", 120) and "piece" not in p
    assert L.go_forward(p, 5)
    assert (p["kind"], p["piece"], p["y"]) == ("piece", "1986.401", 40) and "act" not in p
    assert L.go_back(p) and L.go_back(p)
    assert p["kind"] == "shelf" and not L.go_back(p)
    assert len(p["fwd"]) == 2


def test_a_new_page_forgets_the_way_forward():
    p = L.new_panel("shelf")
    before = L.snapshot(p)
    L.set_page(p, "contents", act="1986")
    L.remember(p, before)
    L.go_back(p)
    assert p["fwd"]
    before = L.snapshot(p)
    L.set_page(p, "search", query="levee", whole=False, opened=[], more={}, closed=[])
    assert L.remember(p, before)
    assert p["fwd"] == [] and len(p["back"]) == 1


def test_staying_on_the_page_is_not_remembered():
    p = L.new_panel("search", query="levee", whole=False, opened=[], more={}, closed=[])
    before = L.snapshot(p, 300)
    assert not L.remember(p, before)
    assert "back" not in p


def test_back_returns_to_the_list_as_it_was_left():
    p = L.new_panel("search", query="levee", whole=False, opened=[], more={}, closed=[])
    p["opened"] = ["1986.401.a"]                # a hit opened in place: part of the page, not a new page
    before = L.snapshot(p, 850)
    L.set_page(p, "piece", piece="1986.401.a", closed=[], above=[], mark="levee")
    assert L.remember(p, before)
    assert L.go_back(p, 10)
    assert (p["kind"], p["query"], p["opened"], p["y"]) == ("search", "levee", ["1986.401.a"], 850)


# ---------------------------------------------------------------- a combined search: phrases joined by AND, OR, NOT
COMBINED = '"if the secretary determines" AND "construct"'
SHOWN = "“if the secretary determines” AND “construct”"


def test_only_marked_phrases_joined_in_capitals_are_a_combined_search():
    c = L.parse_combined(COMBINED)
    assert c.terms == ("if the secretary determines", "construct") and c.shown == SHOWN
    # curly marks, capitals in a phrase, and a bare word beside a marked phrase are all read the same way
    assert L.parse_combined("“If the Secretary determines” AND construct").terms == c.terms
    for plain in ("levee AND construct", "DEAUTHORIZATIONS AND MODIFICATIONS", '"levee"', '"levee" and "dam"',
                  '"levee" "dam"', '"levee" AND', 'NOT "levee"', '"levee', '"levee" AND ""', '("levee" OR "dam"'):
        assert L.parse_combined(plain) is None, plain
    c = L.parse_combined('("levee" OR "floodwall") AND NOT "study"')
    assert c.node == ("and", (("or", (("term", "levee"), ("term", "floodwall"))), ("not", ("term", "study"))))
    assert c.terms == ("levee", "floodwall") and c.phrases == ("levee", "floodwall", "study")
    assert L.parse_combined('"levee" NOT "study"').node == ("and", (("term", "levee"), ("not", ("term", "study"))))
    assert L.parse_combined('"a" OR "b" AND "c"').node == ("or", (("term", "a"), ("and", (("term", "b"), ("term", "c")))))


def test_the_box_reads_a_combined_search_as_words(lib):
    f = L.read_box(lib, '"401" AND "levee"', "1986")
    assert (f.kind, f.address) == ("search", '"401" AND "levee"')
    assert L.read_box(lib, '"if the secretary determines" AND construct', "2007", "2007.3104").kind == "search"
    assert L.search_plan(lib, COMBINED) == (COMBINED, True, [])
    assert not L.is_bare_number('"401" AND "levee"')
    assert L.spine_text(lib, L.new_panel("search", query=COMBINED)) == "Search: " + SHOWN


def _own(lib, a, phrase):
    return phrase in lib.norm[lib.pieces[a].order]


def _with_under(lib, a, phrase):
    first = lib.pieces[a].order
    return any(phrase in lib.norm[j] for j in range(first, first + L.pieces_under(lib, a) + 1))


def test_and_lists_pieces_with_both_phrases_then_those_split_over_the_pieces_under_them(lib):
    A, B = "if the secretary determines", "construct"
    res = L.search(lib, COMBINED)
    same = [a for v in res.by_act.values() for a in v]
    apart = [a for v in res.apart.values() for a in v]
    assert res.total == len(same) > 0 and res.apart_total == len(apart) > 0
    # checked against a plain reading of every piece
    assert same == [a for a in lib.order if _own(lib, a, A) and _own(lib, a, B)]
    want = []
    for a in lib.order:
        if _with_under(lib, a, A) and _with_under(lib, a, B) and not (_own(lib, a, A) and _own(lib, a, B)):
            kids = [c["id"] for c in lib.pieces[a].unit.get("children") or []]
            if not any(_with_under(lib, k, A) and _with_under(lib, k, B) for k in kids):
                want.append(a)
    assert apart == want
    assert not set(same) & set(apart)
    swapped = L.search(lib, '"construct" AND "if the secretary determines"')
    assert (swapped.by_act, swapped.apart) == (res.by_act, res.apart)


def test_or_and_not(lib):
    def hits(q, **kw):
        r = L.search(lib, q, **kw)
        return {a for v in r.by_act.values() for a in v}, r

    levee, wall = hits("levee")[0], hits("floodwall")[0]
    assert levee and wall and levee - wall
    either, r = hits('"levee" OR "floodwall"')
    assert either == levee | wall and r.apart_total == 0        # OR never needs the pieces under a piece
    assert hits('"levee" NOT "floodwall"')[0] == levee - wall
    assert hits('"levee" AND NOT "floodwall"')[0] == levee - wall
    # whole words apply to every phrase: "construction" no longer counts for "construct"
    loose, strict = hits('"levee" AND "construct"')[0], hits('"levee" AND "construct"', whole_words=True)[0]
    assert strict and strict < loose


def test_results_page_of_a_combined_search(lib):
    res = L.search(lib, COMBINED)
    page = L.render_results(lib, search_panel(COMBINED))
    assert SHOWN in page
    assert f"<b>{res.total:,}</b> pieces match in their own words" in page
    assert f"<b>{res.apart_total:,}</b> more match only when the pieces under them are counted" in page
    assert page.index('id="apart"') > page.index('class="group" id="g-')      # the split ones come second
    first = next(iter(res.apart.values()))[0]
    assert f'id="s-{lib.pieces[first].act}"' in page
    # a split hit says which piece has each phrase ...
    places = [at for _, at in L.term_places(lib, first, ("if the secretary determines", "construct"))]
    assert all(places) and len(set(places)) == 2
    for at in places:
        assert f'<span class="at">{html.escape(L.cite(lib, at, with_act=False))}</span>' in page
    # ... and opens with the pieces under it shown and both phrases marked
    panel = search_panel(COMBINED)
    panel["opened"] = [first]
    opened = L.render_results(lib, panel)
    start = opened.index('<div class="hit open">')
    end = opened.find('<div class="hit">', start)
    block = opened[start: end if end > 0 else None]
    assert f'data-hit="{first}"' in block and '<div class="kids">' in block
    assert re.search(r"<mark>if\s+the\s+secretary\s+determines</mark>", block, re.I)
    assert re.search(r"<mark>construct</mark>", block, re.I)


def test_a_piece_opened_from_a_combined_search_marks_every_phrase(lib):
    a = next(iter(L.search(lib, COMBINED).by_act.values()))[0]
    page = L.render_piece(lib, a, mark=COMBINED)
    assert "Marking " + SHOWN in page
    assert re.search(r"<mark>if\s+the\s+secretary\s+determines</mark>", page, re.I)
    assert re.search(r"<mark>construct</mark>", page, re.I)


def test_a_combined_search_survives_the_page_address():
    p = L.new_panel("search", query=COMBINED, whole=False, opened=[])
    assert L.panels_from_tokens(L.panels_to_tokens([p]))[0]["query"] == COMBINED
    piece = L.new_panel("piece", piece="1996.301.b.9", closed=[], above=[], mark=COMBINED)
    assert L.panels_from_tokens(L.panels_to_tokens([piece]))[0]["mark"] == COMBINED


def test_a_plain_search_that_finds_nothing_says_how_to_combine(lib):
    page = L.render_results(lib, search_panel("zzzq AND qqqz"))
    assert "No piece has these words" in page and "put each in quotation marks" in page
    assert "put each in quotation marks" not in L.render_results(lib, search_panel("zzzq qqqz"))


# ---------------------------------------------------------------- moving a panel along the row
def test_a_panel_is_moved_to_another_place_in_the_row():
    row = [L.new_panel("piece", piece=a) for a in ("1986.401", "1996.211", "2007.3104")]
    assert L.move_panel(row, 0, 2) and [p["piece"] for p in row] == ["1996.211", "2007.3104", "1986.401"]
    assert L.move_panel(row, 2, 0) and [p["piece"] for p in row] == ["1986.401", "1996.211", "2007.3104"]
    assert L.move_panel(row, 1, 99) and [p["piece"] for p in row] == ["1986.401", "2007.3104", "1996.211"]    # past the end: the end
    assert not L.move_panel(row, 1, 1) and not L.move_panel(row, 7, 0)                                        # nothing to move
    assert L.panels_to_tokens(row) == ["1986.401", "2007.3104", "1996.211"]                                   # the page address follows


# ---------------------------------------------------------------- what later acts say of a piece
def test_citations_by_other_acts_are_put_on_the_piece_they_name(lib):
    cited = {c.address: c for c in lib.cited_by["1986.401.e.3"]}
    assert list(cited) == ["2007.3104.a", "2016.1322.b.4.A", "2026H.210.c.1"]      # reading order, oldest act first
    assert cited["2007.3104.a"].does == "modifies" and cited["2016.1322.b.4.A"].does == ""
    c = cited["2007.3104.a"]
    assert L.own_words(lib.pieces[c.address].unit)[c.start:c.end] == \
        "section 401(e)(3) of the Water Resources Development Act of 1986"
    for a, places in lib.cited_by.items():
        assert all(lib.pieces[c.address].act != lib.pieces[a].act for c in places)   # never the act's own sections
        assert len({(c.address, c.beyond) for c in places}) == len(places)           # and no place twice


def test_what_a_citing_sentence_does():
    assert L.what_it_does(" (100 Stat. 4132), is modified to authorize the Secretary") == "modifies"
    assert L.what_it_does(" (33 U.S.C. 2309a(a)) is amended by striking") == "amends"
    assert L.what_it_does(", as modified by section 3104 of the Water Resources Development Act of 2007") == ""
    assert L.what_it_does(" (100 Stat. 4134). The project is modified to") == ""     # the next sentence is another matter
    assert L.what_it_does(" is repealed.") == "repeals"
    assert L.what_it_does(" are not authorized after the date of enactment") == "deauthorizes"


def test_the_list_of_citing_places_under_a_piece(lib):
    page = L.render_piece(lib, "1986.401.e.3")
    assert '<details class="later"><summary>Cited in 3 places in later acts and bills (1 modification)</summary>' in page
    assert 'data-go="2007.3104" data-from="2007.3104.a"' in page       # read in its section, in this panel
    assert 'data-open="2007.3104" data-to="2007.3104.a"' in page       # or in a new panel beside this one
    assert '<span class="cref">section 401(e)(3) of the Water Resources Development Act of 1986</span>' in page
    uncited = next(a for a in lib.order if a not in lib.cited_by and not lib.pieces[a].unit.get("children"))
    assert '<details class="later">' not in L.render_piece(lib, uncited)


def test_a_citation_of_a_paragraph_the_act_does_not_have_goes_on_the_piece_above(lib):
    a, c = next((a, c) for a, places in lib.cited_by.items() for c in places if c.beyond)
    assert a in lib.pieces and c.beyond.startswith("(")
    assert "which this act as passed does not have" in L.render_piece(lib, a)


def test_notes_on_how_a_file_was_built_are_not_shown_to_readers(lib, monkeypatch):
    assert "repaired" not in L.render_piece(lib, "1988.4.f")
    assert "prints two subsections" in L.render_piece(lib, "1986.204.e-2nd")      # an oddity of the print stays
    monkeypatch.setattr(L, "BUILD_NOTES", True)
    assert "Label repaired" in L.render_piece(lib, "1988.4.f")
