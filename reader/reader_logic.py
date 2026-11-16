"""reader_logic.py -- everything the WRDA Reader knows that is not Streamlit.

Reading the structure files, addresses, word search, line-ups, and the pages as HTML.
No Streamlit import here, so it can be tested and reused without the app.

Words used here and on the screen:
  act       one structure file (WRDA 1986 ... the 2026 bills)
  piece     a section or anything below it (a "unit" in the structure files)
  address   the piece's id in the structure file: 1986.401.e.3
  children  the pieces directly below a piece
  panel     one column of the screen showing one page
  line-up   the panels on the screen, in order
"""
from __future__ import annotations

import copy
import datetime
import functools
import html
import json
import os
import re
from dataclasses import dataclass, field

SCHEMA = "wrda-structure/1"
LINEUP_FORMAT = "wrda-lineup/1"
FILE_SUFFIX = ".structure.json"
LINEUP_SUFFIX = ".lineup.json"


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------
@dataclass
class Act:
    key: str                     # first part of every address in the act: "1986", "2026H"
    name: str                    # "WRDA 1986"
    file: str                    # file name it was read from
    public_law: str | None
    enacted: str | None          # "1986-11-17" or None (the bills)
    part: str | None             # part_of_source_used
    scan: bool                   # the text comes from a page scan
    sections: list               # the section units, as in the file
    flags: dict                  # address -> [sentence, ...] (the build's doubts and repairs)
    n_pieces: int = 0


@dataclass
class Piece:
    unit: dict
    act: str                     # act key
    parent: str | None           # address of the piece above it (None for a section)
    section: str                 # address of its section
    depth: int                   # 0 for a section
    order: int                   # position in reading order, whole library


@dataclass
class Library:
    folder: str
    acts: dict = field(default_factory=dict)        # key -> Act, oldest first
    pieces: dict = field(default_factory=dict)      # address -> Piece
    problems: list = field(default_factory=list)    # one plain sentence per file not loaded
    order: list = field(default_factory=list)       # addresses in reading order
    norm: list = field(default_factory=list)        # search text of each piece, same order


def structure_files(folder: str) -> list:
    """Paths of the structure files in the folder (not in sub-folders), sorted."""
    names = sorted(n for n in os.listdir(folder) if n.endswith(FILE_SUFFIX) and not n.startswith("."))
    return [os.path.join(folder, n) for n in names]


def folder_signature(folder: str) -> tuple:
    """(name, size, modified) of every structure file: changes when a file is rebuilt."""
    out = []
    for p in structure_files(folder):
        s = os.stat(p)
        out.append((os.path.basename(p), s.st_size, s.st_mtime_ns))
    return tuple(out)


def _walk(unit, parent, depth):
    stack = [(unit, parent, depth)]
    while stack:
        u, p, d = stack.pop()
        yield u, p, d
        kids = u.get("children") or []
        for c in reversed(kids):
            stack.append((c, u.get("id"), d + 1))


def _read_act(path: str):
    """Return (Act, [(unit, parent_address, depth), ...]) or raise ValueError(plain sentence)."""
    name = os.path.basename(path)
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as e:
        raise ValueError(f"{name} is damaged: it stops being valid JSON at line {e.lineno}, column {e.colno}.")
    except (OSError, UnicodeDecodeError) as e:
        raise ValueError(f"{name} could not be read ({e.__class__.__name__}).")
    if not isinstance(data, dict) or not isinstance(data.get("sections"), list):
        raise ValueError(f"{name} does not look like a structure file: it has no list of sections.")
    if data.get("schema") != SCHEMA:
        raise ValueError(f"{name} says its format is {data.get('schema')!r}; this reader knows {SCHEMA!r}.")
    if not data["sections"]:
        raise ValueError(f"{name} holds no sections.")
    first = data["sections"][0]
    if not isinstance(first, dict) or "." not in str(first.get("id", "")):
        raise ValueError(f"{name} does not look like a structure file: its first section has no address.")
    key = first["id"].split(".", 1)[0]
    rows = []
    for sec in data["sections"]:
        for u, p, d in _walk(sec, None, 0):
            if not isinstance(u, dict) or not str(u.get("id", "")).startswith(key + "."):
                raise ValueError(f"{name} is damaged: a piece under {sec.get('id')} has no proper address.")
            rows.append((u, p, d))
    flags: dict = {}
    for fl in data.get("flags") or []:
        if isinstance(fl, dict) and fl.get("unit"):
            flags.setdefault(fl["unit"], []).append(f"{str(fl.get('kind', 'FLAG')).capitalize()}: {fl.get('what', '')}")
    src = data.get("source") or {}
    kind = str((src.get("text") or {}).get("kind", "")) if isinstance(src.get("text"), dict) else ""
    act = Act(
        key=key,
        name=str(data.get("act") or name[: -len(FILE_SUFFIX)]),
        file=name,
        public_law=data.get("public_law"),
        enacted=data.get("enacted"),
        part=data.get("part_of_source_used"),
        scan="scan" in kind.lower(),
        sections=data["sections"],
        flags=flags,
        n_pieces=len(rows),
    )
    return act, rows


def _act_sort_key(act: Act):
    m = re.match(r"\d{4}", act.key)
    return (int(m.group(0)) if m else 9999, act.enacted or "9999", act.name)


def load_library(folder: str) -> Library:
    """Read every structure file in the folder. Never raises for a bad file:
    what could not be used is listed, in plain sentences, in .problems."""
    lib = Library(folder=folder)
    if not folder or not os.path.isdir(folder):
        lib.problems.append(f"There is no folder at {folder!r}." if folder else "No data folder has been given.")
        return lib
    paths = structure_files(folder)
    if not paths:
        lib.problems.append(f"The folder {folder!r} holds no files whose names end in {FILE_SUFFIX}.")
        return lib
    loaded = []
    seen_addresses: dict = {}
    for path in paths:
        try:
            act, rows = _read_act(path)
        except ValueError as e:
            lib.problems.append(str(e))
            continue
        if any(a.key == act.key for a, _ in loaded):
            other = next(a for a, _ in loaded if a.key == act.key)
            lib.problems.append(f"{act.file} was left out: its addresses begin {act.key}. like those of {other.file}.")
            continue
        clash = next((u["id"] for u, _, _ in rows if u["id"] in seen_addresses), None)
        local = set()
        dup = None
        for u, _, _ in rows:
            if u["id"] in local:
                dup = u["id"]
                break
            local.add(u["id"])
        if clash or dup:
            lib.problems.append(f"{act.file} was left out: the address {clash or dup} is used twice.")
            continue
        for a in local:
            seen_addresses[a] = act.key
        loaded.append((act, rows))
    loaded.sort(key=lambda ar: _act_sort_key(ar[0]))
    n = 0
    for act, rows in loaded:
        lib.acts[act.key] = act
        section = None
        for u, p, d in rows:
            if d == 0:
                section = u["id"]
            lib.pieces[u["id"]] = Piece(unit=u, act=act.key, parent=p, section=section, depth=d, order=n)
            lib.order.append(u["id"])
            lib.norm.append(normalize(own_words(u)))
            n += 1
    return lib


# --------------------------------------------------------------------------
# Words
# --------------------------------------------------------------------------
def own_words(unit: dict) -> str:
    """Heading, own text and trailing text of one piece (not its children)."""
    return "\n".join(t for t in (unit.get("heading"), unit.get("own_text"), unit.get("trailing_text")) if t)


_WS = re.compile(r"\s+")
_HYPHEN_BREAK = re.compile(r"(?<=\w)- (?=\w)")


def normalize(text: str) -> str:
    """The form in which text and search words are compared.
    Lower case; `` '' and curly quotes become "; runs of spaces and line breaks
    become one space; a hyphen left hanging by a line break ("non- Federal") is closed up."""
    t = text.lower().replace("``", '"').replace("''", '"').replace("“", '"').replace("”", '"')
    t = t.replace("‘", "'").replace("’", "'")
    t = _WS.sub(" ", t).strip()
    return _HYPHEN_BREAK.sub("-", t)


# --------------------------------------------------------------------------
# A combined search: phrases joined by AND, OR, NOT
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Combined:
    node: tuple          # ("term", phrase) | ("not", node) | ("and", (node, ...)) | ("or", (node, ...))
    terms: tuple         # the phrases looked for (those not under NOT), normalized, in the order typed
    phrases: tuple       # every phrase, under NOT or not
    shown: str           # the search as shown above the results


_OPERATORS = ("AND", "OR", "NOT")
_TOKEN = re.compile(r'\s*(?:"([^"]*)"|([()])|([^\s()"]+))')


@functools.lru_cache(maxsize=512)
def parse_combined(text: str | None):
    """Read a combined search such as  "if the secretary determines" AND "construct".

    Phrases are joined by AND, OR, NOT in capitals, with brackets if wanted. NOT binds tightest,
    then AND, then OR; two phrases side by side mean AND. Words outside quotation marks, up to
    the next AND/OR/NOT, are a phrase too.

    Returns None unless the text has at least one of those three words AND at least one phrase
    in quotation marks, so a plain phrase is still looked for as it stands (a heading typed in
    capitals, DEAUTHORIZATIONS AND MODIFICATIONS, is one phrase). Also None when the text cannot
    be read (a mark without its pair, AND with nothing after it) or looks for nothing (only NOT)."""
    t = (text or "").replace("“", '"').replace("”", '"').strip()
    toks, pos, quoted = [], 0, 0
    while pos < len(t):
        m = _TOKEN.match(t, pos)
        if not m:
            return None                                   # a quotation mark without its pair
        pos = m.end()
        if m.group(1) is not None:
            toks.append(("term", m.group(1).strip()))
            quoted += 1
        elif m.group(2):
            toks.append((m.group(2),))
        elif m.group(3) in _OPERATORS:
            toks.append(("op", m.group(3)))
        elif toks and toks[-1][0] == "word":
            toks[-1] = ("word", toks[-1][1] + " " + m.group(3))
        else:
            toks.append(("word", m.group(3)))
    if not quoted or not any(k[0] == "op" for k in toks):
        return None
    shown = " ".join("“" + k[1] + "”" if k[0] in ("term", "word") else k[-1] for k in toks)
    shown = shown.replace("( ", "(").replace(" )", ")")
    toks = [("term", normalize(k[1])) if k[0] in ("term", "word") else k for k in toks]
    if any(k[0] == "term" and not k[1] for k in toks):
        return None
    at = 0

    def peek():
        return toks[at] if at < len(toks) else None

    def one():
        nonlocal at
        k = peek()
        if k == ("op", "NOT"):
            at += 1
            return ("not", one())
        if k == ("(",):
            at += 1
            node = either()
            if peek() != (")",):
                raise ValueError("bracket")
            at += 1
            return node
        if k is not None and k[0] == "term":
            at += 1
            return k
        raise ValueError("phrase expected")

    def both():
        nonlocal at
        nodes = [one()]
        while True:
            k = peek()
            if k == ("op", "AND"):
                at += 1
                nodes.append(one())
            elif k is not None and (k[0] == "term" or k in (("(",), ("op", "NOT"))):
                nodes.append(one())                       # side by side means AND
            else:
                break
        return nodes[0] if len(nodes) == 1 else ("and", tuple(nodes))

    def either():
        nonlocal at
        nodes = [both()]
        while peek() == ("op", "OR"):
            at += 1
            nodes.append(both())
        return nodes[0] if len(nodes) == 1 else ("or", tuple(nodes))

    try:
        node = either()
    except ValueError:
        return None
    if at != len(toks):
        return None
    wanted, every = [], []

    def collect(nd, positive):
        if nd[0] == "term":
            if nd[1] not in every:
                every.append(nd[1])
            if positive and nd[1] not in wanted:
                wanted.append(nd[1])
        elif nd[0] == "not":
            collect(nd[1], not positive)
        else:
            for c in nd[1]:
                collect(c, positive)

    collect(node, True)
    if not wanted:
        return None
    return Combined(node=node, terms=tuple(wanted), phrases=tuple(every), shown=shown)


def _phrase_body(q: str, whole_words: bool) -> str:
    """Regular-expression source that finds one normalized phrase in text as stored in the files."""
    parts = []
    for ch in q:
        if ch == " ":
            parts.append(r"\s+")
        elif ch == '"':
            parts.append("(?:``|''|[\"“”])")
        elif ch == "-":
            parts.append(r"-\s?")
        else:
            parts.append(re.escape(ch))
    body = "".join(parts)
    if whole_words:
        body = r"(?<![0-9A-Za-z])" + body + r"(?![0-9A-Za-z])"
    return body


def phrase_pattern(phrase: str, whole_words: bool = False):
    """A regular expression that finds one phrase in text as stored in the files."""
    return re.compile(_phrase_body(normalize(phrase), whole_words), re.IGNORECASE)


def match_pattern(query: str, whole_words: bool = False):
    """A regular expression that finds the query in text as stored in the files
    (tolerant of the same things normalize() removes). None for an empty query.
    For a combined search it finds any of the phrases looked for."""
    cq = parse_combined(query)
    if cq is not None:
        longest_first = sorted(cq.terms, key=len, reverse=True)
        return re.compile("|".join("(?:" + _phrase_body(t, whole_words) + ")" for t in longest_first), re.IGNORECASE)
    q = normalize(query)
    if not q:
        return None
    return re.compile(_phrase_body(q, whole_words), re.IGNORECASE)


# --------------------------------------------------------------------------
# Word search
# --------------------------------------------------------------------------
@dataclass
class Hit:
    address: str
    count: int          # times the words occur in this piece's own words
    where: str          # "heading" or "text"
    before: str         # snippet: words before the first match
    match: str          # the matched words as printed
    after: str          # words after


@dataclass
class SearchResult:
    query: str
    whole_words: bool
    total: int                       # pieces that have the words (a combined search: in their own words)
    by_act: dict                     # act key -> [address, ...] in reading order (every act that has hits)
    apart_total: int = 0             # a combined search: pieces that match only with the pieces under them
    apart: dict = field(default_factory=dict)      # act key -> [address, ...] for those


def _has_phrase(lib: Library, phrase: str, whole_words: bool) -> list:
    """For every piece in reading order: do its own words have the (normalized) phrase?"""
    rx = re.compile(r"(?<![0-9a-z])" + re.escape(phrase) + r"(?![0-9a-z])") if whole_words else None
    return [phrase in t and (rx is None or rx.search(t) is not None) for t in lib.norm]


def _holds(node: tuple, has) -> bool:
    """Is a combined search true, given has(phrase) -> bool?"""
    kind = node[0]
    if kind == "term":
        return has(node[1])
    if kind == "not":
        return not _holds(node[1], has)
    if kind == "and":
        return all(_holds(c, has) for c in node[1])
    return any(_holds(c, has) for c in node[1])


def _search_combined(lib: Library, query: str, cq: Combined, whole_words: bool) -> SearchResult:
    """Phrases joined by AND, OR, NOT.
    `by_act`: the pieces that match in their own words (heading and own text), as a plain search does.
    `apart`:  the pieces that match only when the pieces under them are counted too. The smallest
              such piece is listed: one with no child that matches when counted the same way."""
    res = SearchResult(query=query, whole_words=whole_words, total=0, by_act={})
    order, pieces = lib.order, lib.pieces
    n = len(order)
    own = {ph: _has_phrase(lib, ph, whole_words) for ph in cq.phrases}
    parent = [pieces[pieces[a].parent].order if pieces[a].parent is not None else -1 for a in order]
    under = {ph: list(v) for ph, v in own.items()}
    for i in range(n - 1, -1, -1):                      # a piece stands before its children in reading order
        p = parent[i]
        if p >= 0:
            for ph in cq.phrases:
                if under[ph][i]:
                    under[ph][p] = True
    same = [_holds(cq.node, lambda ph: own[ph][i]) for i in range(n)]
    with_under = [_holds(cq.node, lambda ph: under[ph][i]) for i in range(n)]
    child_holds = [False] * n
    for i in range(n):
        if with_under[i] and parent[i] >= 0:
            child_holds[parent[i]] = True
    for i, a in enumerate(order):
        if same[i]:
            res.by_act.setdefault(pieces[a].act, []).append(a)
            res.total += 1
        elif with_under[i] and not child_holds[i]:
            res.apart.setdefault(pieces[a].act, []).append(a)
            res.apart_total += 1
    return res


def pieces_under(lib: Library, address: str) -> int:
    """How many pieces stand under this one, at every depth."""
    pc = lib.pieces[address]
    j = pc.order + 1
    while j < len(lib.order) and lib.pieces[lib.order[j]].depth > pc.depth:
        j += 1
    return j - pc.order - 1


def term_places(lib: Library, address: str, phrases, whole_words: bool = False) -> list:
    """For a piece and the pieces under it: [(phrase, address of the first piece, in reading order,
    whose own words have it, or None)]."""
    pc = lib.pieces[address]
    stop = pc.order + pieces_under(lib, address) + 1
    out = []
    for ph in phrases:
        rx = re.compile(r"(?<![0-9a-z])" + re.escape(ph) + r"(?![0-9a-z])") if whole_words else None
        where = None
        for j in range(pc.order, stop):
            t = lib.norm[j]
            if ph in t and (rx is None or rx.search(t)):
                where = lib.order[j]
                break
        out.append((ph, where))
    return out


def search(lib: Library, query: str, whole_words: bool = False) -> SearchResult:
    """Every piece whose own heading or text has the query. Case is ignored.
    The query is one phrase; it also matches inside longer words unless whole_words.
    Phrases joined by AND, OR, NOT (see parse_combined) are looked for together."""
    cq = parse_combined(query)
    if cq is not None:
        return _search_combined(lib, query, cq, whole_words)
    q = normalize(query)
    res = SearchResult(query=query, whole_words=whole_words, total=0, by_act={})
    if not q:
        return res
    rx = None
    if whole_words:
        rx = re.compile(r"(?<![0-9a-z])" + re.escape(q) + r"(?![0-9a-z])")
    norm, order, pieces = lib.norm, lib.order, lib.pieces
    for i, t in enumerate(norm):
        if q in t and (rx is None or rx.search(t)):
            a = order[i]
            res.by_act.setdefault(pieces[a].act, []).append(a)
            res.total += 1
    return res


def hit_detail(lib: Library, address: str, pattern, width: int = 150) -> Hit:
    """Snippet of one hit: the first place the words occur, with words around it."""
    u = lib.pieces[address].unit
    for where, text in (("heading", u.get("heading") or ""), ("text", u.get("own_text") or ""), ("text", u.get("trailing_text") or "")):
        m = pattern.search(text)
        if m:
            break
    else:
        return Hit(address, 0, "text", (own_words(u)[:width]).replace("\n", " "), "", "")
    count = sum(len(pattern.findall(t)) for t in (u.get("heading") or "", u.get("own_text") or "", u.get("trailing_text") or ""))
    lead = max(0, m.start() - width // 3)
    tail = min(len(text), m.end() + (2 * width) // 3)
    before = text[lead:m.start()]
    after = text[m.end():tail]
    if lead > 0:
        before = "…" + before.split(" ", 1)[-1] if " " in before else "…" + before
    if tail < len(text):
        after = (after.rsplit(" ", 1)[0] if " " in after else after) + "…"
    return Hit(address, count, where, before.replace("\n", " "), m.group(0), after.replace("\n", " "))


# --------------------------------------------------------------------------
# Addresses
# --------------------------------------------------------------------------
@dataclass
class Found:
    kind: str                 # "piece", "contents", "shelf", "search" (from read_box) or "none"
    address: str | None       # piece address; act key for contents; the text of the box for a search
    said: str | None = None   # a sentence for the reader: why not, or a caution
    why: str = ""             # for kind "none": "words", "which_act", "no_section" or "ambiguous"


def cite(lib: Library, address: str, with_act: bool = True) -> str:
    """How a person would cite the piece: WRDA 1986 sec. 401(e)(3)."""
    p = lib.pieces[address]
    chain = []
    a = address
    while a is not None:
        chain.append(lib.pieces[a])
        a = lib.pieces[a].parent
    chain.reverse()
    sec = chain[0].unit
    out = "sec. " + str(sec.get("number", ""))
    if sec["id"].endswith("-2nd"):
        out += " (the second)"
    for pc in chain[1:]:
        u = pc.unit
        seg = u["id"].rsplit(".", 1)[-1]
        if u.get("label"):
            out += u["label"]
            if "-" in seg:
                out += " (" + _ordinal_note(seg) + ")"
        elif u.get("type") == "group":
            out += ", " + (u.get("heading") or "group " + seg[1:].lstrip("0"))
        else:
            out += ", item " + seg[1:].lstrip("0")
    return (lib.acts[p.act].name + " " if with_act else "") + out


def _ordinal_note(seg: str) -> str:
    tail = seg.split("-", 1)[1]
    if tail.startswith("list"):
        return "list " + tail[4:]
    return "the " + tail


def box_text(lib: Library, address: str) -> str:
    """What the panel's box shows for a piece, in a form find_address() reads back."""
    p = lib.pieces[address]
    plain = True
    a = address
    labels = []
    while lib.pieces[a].parent is not None:
        u = lib.pieces[a].unit
        seg = a.rsplit(".", 1)[-1]
        if not u.get("label") or u["label"] != f"({seg})":
            plain = False
            break
        labels.append(u["label"])
        a = lib.pieces[a].parent
    sec = lib.pieces[p.section].unit
    if plain and p.section == f"{p.act}.{sec.get('number')}":
        return f"{p.act} {sec.get('number')}" + "".join(reversed(labels))
    return address


_PAREN_PATH = re.compile(r"^(?:\s*\([^()\s]+\))+\s*$")
_NUM_TOKEN = re.compile(r"(?<![\w.])(\d+[a-z]?)((?:\s*\([^()\s]+\))*)", re.IGNORECASE)


def _act_from_words(lib: Library, text: str):
    """(act key or None, sentence or None) from words that name an act."""
    low = text.lower()
    for key, act in lib.acts.items():
        if low in (key.lower(), act.name.lower()):
            return key, None
    return None, None


def find_address(lib: Library, text: str, act: str | None = None, section: str | None = None) -> Found:
    """Read what was typed in a panel's box.

    Understands, where `act` and `section` are what the panel shows now:
      1986.401.e.3          an address as shown on the page
      401   401(e)(3)       a section (and a piece in it) of the panel's act
      (c)   (e)(3)          a piece of the panel's section
      1986 401(e)(3)        act and section (the act first or last)
      section 903(c) of the Water Resources Development Act of 1986
      1986   WRDA 1986      the contents of an act
      (nothing)             the list of acts
    Always returns a Found; .said explains anything not done as typed.
    """
    raw = (text or "").strip()
    if not raw:
        return Found("shelf", None)
    compact = re.sub(r"\s+", "", raw)
    if compact in lib.pieces:
        return Found("piece", compact)
    if act and re.fullmatch(r"[\w.\-]+", compact) and f"{act}.{compact}" in lib.pieces and "." in compact:
        return Found("piece", f"{act}.{compact}")
    # a piece of the section on the page: (c), (e)(3)
    if section and _PAREN_PATH.match(raw):
        labels = re.findall(r"\(([^()\s]+)\)", raw)
        return _descend(lib, section, labels)
    # the name of an act alone
    key, _ = _act_from_words(lib, raw)
    low = raw.lower()
    low = low.replace("§", " sec ")
    tokens = [(m.group(1), re.findall(r"\(([^()\s]+)\)", m.group(2)), m.start(), m.end()) for m in _NUM_TOKEN.finditer(low)]
    if key and not (act and len(tokens) == 1 and not tokens[0][1] and _section_of(lib, act, tokens[0][0])):
        return Found("contents", key)
    if not tokens:
        return Found("none", None, f"“{raw}” is not an address. Type an act and a section, like 1986 401(a).", "words")
    # which number names the act?
    def act_key_at(i):
        num, path, start, end = tokens[i]
        if path or not re.fullmatch(r"(19|20)\d\d[hs]?", num):
            return None
        tail = low[end:end + 12]
        cands = [k for k in lib.acts if k.lower() == num]
        if not cands:
            year = num[:4]
            cands = [k for k in lib.acts if k.lower().startswith(year)]
            if len(cands) > 1:
                m = re.match(r"\s*(house|senate)", tail)
                if m:
                    cands = [k for k in cands if k.lower().endswith(m.group(1)[0])]
        return cands or None

    act_i = None
    cands = None
    if len(tokens) >= 2:
        marked = [i for i, (num, path, start, end) in enumerate(tokens)
                  if path or re.search(r"(sec|section|sections)\.?\s*$", low[:start])]
        order = [i for i in range(len(tokens)) if i not in marked] + []
        for i in order:
            c = act_key_at(i)
            if c:
                act_i, cands = i, c
                break
    elif len(tokens) == 1 and not (act and _section_of(lib, act, tokens[0][0])):
        c = act_key_at(0)
        if c:
            if len(c) > 1:
                return Found("none", None, f"{tokens[0][0]} could be " + " or ".join(lib.acts[k].name for k in c) + ". Type " + " or ".join(c) + ".", "ambiguous")
            return Found("contents", c[0])
    if cands and len(cands) > 1:
        return Found("none", None, f"{tokens[act_i][0]} could be " + " or ".join(lib.acts[k].name for k in cands) + ". Type " + " or ".join(cands) + ".", "ambiguous")
    use_act = cands[0] if cands else act
    rest = [t for i, t in enumerate(tokens) if i != act_i]
    if not rest:
        return Found("contents", use_act)
    if not use_act:
        return Found("none", None, f"Which act? Type the act first, like 1986 {rest[0][0]}.", "which_act")
    num, path = rest[0][0], rest[0][1]
    sec = _section_of(lib, use_act, num)
    if not sec and cands is None and len(tokens) == 1:
        return Found("none", None, f"{lib.acts[use_act].name} has no section {num}." + _near(lib, use_act, num), "no_section")
    if not sec:
        return Found("none", None, f"{lib.acts[use_act].name} has no section {num}." + _near(lib, use_act, num), "no_section")
    found = _descend(lib, sec, path)
    twin = sec + "-2nd"
    if twin in lib.pieces and not found.said:
        found.said = f"{lib.acts[use_act].name} prints two sections {num}. This is the first; the second is at {twin}."
    return found


def _section_of(lib: Library, act: str, number: str):
    a = f"{act}.{number}"
    if a in lib.pieces:
        return a
    for s in lib.acts[act].sections:
        if str(s.get("number", "")).lower() == number.lower():
            return s["id"]
    return None


def _near(lib: Library, act: str, number: str) -> str:
    nums = [str(s.get("number")) for s in lib.acts[act].sections]
    close = [n for n in nums if n.startswith(number[: max(1, len(number) - 1)])][:4]
    if close:
        return " Near it: " + ", ".join(close) + "."
    return f" Its sections run from {nums[0]} to {nums[-1]}."


def _descend(lib: Library, start: str, labels: list) -> Found:
    here = start
    for lab in labels:
        nxt = None
        for c in lib.pieces[here].unit.get("children") or []:
            seg = c["id"].rsplit(".", 1)[-1]
            if seg == lab or (c.get("label") or "").strip("()") == lab:
                nxt = c["id"]
                break
        if nxt is None:
            for c in lib.pieces[here].unit.get("children") or []:
                if (c.get("label") or "").strip("()").lower() == lab.lower():
                    nxt = c["id"]
                    break
        if nxt is None:
            return Found("piece", here, f"{cite(lib, here)} has no ({lab}). This is {cite(lib, here, with_act=False)}.")
        here = nxt
    said = None
    if here + "-2nd" in lib.pieces:
        said = f"{cite(lib, here)} is printed twice. This is the first; the second is at {here}-2nd."
    return Found("piece", here, said)


# --------------------------------------------------------------------------
# The box: an address if it reads as one, otherwise words to find
# --------------------------------------------------------------------------
_BARE_NUMBER = re.compile(r"^(?:sec(?:tions?|s)?\.?\s*|§+\s*)?(\d+[a-z]?)((?:\s*\([^()\s]+\))*)$", re.IGNORECASE)
_ADDRESS_WORDS = frozenset(
    "sec section sections subsection paragraph subparagraph clause of the in act wrda wrrda water resources "
    "reform and development house senate bill".split())


def search_words(typed: str) -> tuple:
    """(words, quoted): the words to look for, and whether they were typed between quotation marks.
    A combined search ("a" AND "b") is kept as typed and always counts as words."""
    t = (typed or "").strip()
    if parse_combined(t) is not None:
        return t, True
    if len(t) >= 2 and t[0] in "\"\u201c" and t[-1] in "\"\u201d":
        return t[1:-1].strip(), True
    return t, False


def numbered_sections(lib: Library, words: str) -> list:
    """What a bare number names in each act: for "3104", every section numbered 3104; for
    "401(a)", subsection (a) of every section 401. Addresses in act order; [] if not a bare number."""
    m = _BARE_NUMBER.match((words or "").strip())
    if not m:
        return []
    labels = re.findall(r"\(([^()\s]+)\)", m.group(2))
    out = []
    for key in lib.acts:
        sec = _section_of(lib, key, m.group(1))
        for s in ((sec, sec + "-2nd") if sec else ()):
            if s in lib.pieces:
                f = _descend(lib, s, labels)
                if lib.pieces[f.address].depth == len(labels):
                    out.append(f.address)
    return out


def search_plan(lib: Library, typed: str) -> tuple:
    """(words, quoted, numbered) for the text in the box of a search.
    A bare number ("sec. 3104") is looked for as the number alone, and the sections it names come first."""
    words, quoted = search_words(typed)
    if quoted:
        return words, True, []
    m = _BARE_NUMBER.match(words)
    if m:
        words = m.group(1) + re.sub(r"\s+", "", m.group(2))
    return words, False, numbered_sections(lib, words)


def is_bare_number(typed: str) -> bool:
    words, quoted = search_words(typed)
    return not quoted and bool(_BARE_NUMBER.match(words))


def _reads_as_address(lib: Library, raw: str, act: str | None, section: str | None) -> bool:
    """True if every word typed belongs to an address: nothing is left once the numbers, "sec.",
    "of the ... Act of" and the like are taken away. "404 permit" is words, not an address."""
    compact = re.sub(r"\s+", "", raw)
    if compact in lib.pieces or (act and "." in compact and f"{act}.{compact}" in lib.pieces):
        return True
    if _PAREN_PATH.match(raw):
        return bool(section)
    if _act_from_words(lib, raw)[0]:
        return True
    low = raw.lower().replace("§", " ")
    if not _NUM_TOKEN.search(low):
        return False
    rest = _NUM_TOKEN.sub(" ", low)
    if re.search(r"[^a-z\s.]", rest):
        return False
    return all(w in _ADDRESS_WORDS for w in re.findall(r"[a-z]+", rest))


def read_box(lib: Library, text: str, act: str | None = None, section: str | None = None) -> Found:
    """Read what was typed in a panel's box; `act` and `section` are what the panel shows now.

    An address that exists takes the panel there (find_address says which forms are understood).
    Anything else is words to find, and so is anything typed between quotation marks.
    kind "search": .address holds the text of the box; .said may explain why it was not an address.
    """
    raw = (text or "").strip()
    if not raw:
        return Found("shelf", None)
    if search_words(raw)[1] or not _reads_as_address(lib, raw, act, section):
        return Found("search", raw)
    f = find_address(lib, raw, act, section)
    if f.kind != "none":
        return f
    return Found("search", raw, f.said if f.why in ("no_section", "ambiguous") else None)


# --------------------------------------------------------------------------
# A panel's history: back and forward, like a tab in a browser
# --------------------------------------------------------------------------
PAGE_KEYS = ("kind", "piece", "act", "query", "whole", "opened", "more", "closed", "mark", "above")
HISTORY = 200


def page_of(panel: dict) -> dict:
    """The page a panel shows: what its history keeps and gives back."""
    return {k: copy.deepcopy(panel[k]) for k in PAGE_KEYS if k in panel}


def set_page(panel: dict, kind: str, **kw):
    """Point the panel at another page, dropping everything that belonged to the old one."""
    for k in PAGE_KEYS:
        panel.pop(k, None)
    panel.update(kind=kind, **kw)


def snapshot(panel: dict, y=0) -> dict:
    """The page a panel shows, with the place it is scrolled to."""
    return {"page": page_of(panel), "y": int(y or 0)}


def remember(panel: dict, before: dict) -> bool:
    """Call after the panel may have gone to another page; `before` is the snapshot taken first.
    If it did go, the old page joins the history and the way forward is forgotten."""
    if page_of(panel) == before["page"]:
        return False
    panel.setdefault("back", []).append(before)
    del panel["back"][:-HISTORY]
    panel["fwd"] = []
    return True


def _step(panel: dict, take: str, give: str, y) -> bool:
    if not panel.get(take):
        return False
    panel.setdefault(give, []).append(snapshot(panel, y))
    snap = panel[take].pop()
    set_page(panel, **snap["page"])
    panel["y"] = snap["y"]
    return True


def go_back(panel: dict, y=0) -> bool:
    """Show the page before this one, scrolled to where it was left. False if there is none."""
    return _step(panel, "back", "fwd", y)


def go_forward(panel: dict, y=0) -> bool:
    return _step(panel, "fwd", "back", y)


def crumbs(lib: Library, address: str) -> list:
    """[(address, words), ...] from the act down to the piece. The act's entry has the act key."""
    p = lib.pieces[address]
    chain = []
    a = address
    while a is not None:
        chain.append(a)
        a = lib.pieces[a].parent
    chain.reverse()
    out = [(p.act, lib.acts[p.act].name)]
    for a in chain:
        u = lib.pieces[a].unit
        seg = a.rsplit(".", 1)[-1]
        if lib.pieces[a].depth == 0:
            words = "Sec. " + str(u.get("number", seg))
        elif u.get("label"):
            words = u["label"]
        elif u.get("type") == "group":
            words = u.get("heading") or "group " + seg[1:].lstrip("0")
        else:
            words = "item " + seg[1:].lstrip("0")
        out.append((a, words))
    return out


# --------------------------------------------------------------------------
# Line-ups
# --------------------------------------------------------------------------
def new_panel(kind: str = "shelf", **kw) -> dict:
    """A panel as kept in the session and in a line-up file."""
    p = {"kind": kind}
    p.update(kw)
    return p


def move_panel(panels: list, i: int, to: int) -> bool:
    """Move the panel at place i of the row to place `to`, where it stands afterwards (both counted
    from 0). A place beyond the row is brought to its end. True if the row changed."""
    if not 0 <= i < len(panels):
        return False
    to = max(0, min(len(panels) - 1, to))
    if to == i:
        return False
    panels.insert(to, panels.pop(i))
    return True


def spine_text(lib: Library, panel: dict) -> str:
    """The words down the spine of a collapsed panel: what the panel holds."""
    kind = panel.get("kind")
    if kind == "piece":
        a = panel.get("piece") or ""
        if a not in lib.pieces:
            return a
        hd = lib.pieces[a].unit.get("heading") or ""
        return cite(lib, a) + (" · " + hd if hd else "")
    if kind == "contents":
        act = lib.acts.get(panel.get("act"))
        return act.name if act else str(panel.get("act") or "")
    if kind == "search":
        words = search_words(panel.get("query") or "")[0]
        cq = parse_combined(words)
        if cq is not None:
            return "Search: " + cq.shown
        return "Search: “" + words + "”" if words else "Search"
    return "All acts"


def lineup_to_dict(lib: Library, name: str, panels: list) -> dict:
    """The line-up file: the panels in order, with a line a person can read for each."""
    out = []
    for p in panels:
        if p["kind"] == "piece":
            a = p["piece"]
            row = {"piece": a}
            if a in lib.pieces:
                row["cite"] = cite(lib, a)
                h = lib.pieces[a].unit.get("heading")
                if h:
                    row["heading"] = h
            row["children"] = a not in (p.get("closed") or [])
            others = sorted(c for c in (p.get("closed") or []) if c != a)
            if others:
                row["children_hidden_in"] = others
            if p.get("above"):
                row["parents_shown_in_full"] = sorted(p["above"])
            if p.get("mark"):
                row["marked_words"] = p["mark"]
            out.append(row)
        elif p["kind"] == "contents":
            out.append({"contents_of": p["act"], "act": lib.acts[p["act"]].name if p["act"] in lib.acts else None})
        elif p["kind"] == "search":
            row = {"word_search": p.get("query", ""), "whole_words": bool(p.get("whole"))}
            if p.get("opened"):
                row["opened"] = list(p["opened"])
            out.append(row)
        else:
            out.append({"empty": True})
        if p.get("thin"):
            out[-1]["collapsed"] = True
    return {
        "format": LINEUP_FORMAT,
        "name": name,
        "saved": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "panels": out,
    }


def lineup_from_dict(data) -> tuple:
    """(name, panels, problems). Panels naming pieces that are not in the library are
    kept (the page says so); rows that cannot be read at all are listed in problems."""
    problems = []
    if not isinstance(data, dict) or data.get("format") != LINEUP_FORMAT or not isinstance(data.get("panels"), list):
        return "", [], ["This is not a line-up file (it does not say " + LINEUP_FORMAT + ")."]
    panels = []
    for i, row in enumerate(data["panels"], 1):
        n = len(panels)
        if not isinstance(row, dict):
            problems.append(f"Panel {i} could not be read.")
        elif isinstance(row.get("piece"), str):
            closed = set(c for c in row.get("children_hidden_in") or [] if isinstance(c, str))
            if row.get("children") is False:
                closed.add(row["piece"])
            above = sorted(a for a in row.get("parents_shown_in_full") or [] if isinstance(a, str))
            panels.append(new_panel("piece", piece=row["piece"], closed=sorted(closed), above=above,
                                    mark=row.get("marked_words") or None))
        elif isinstance(row.get("contents_of"), str):
            panels.append(new_panel("contents", act=row["contents_of"]))
        elif "word_search" in row:
            panels.append(new_panel("search", query=str(row.get("word_search") or ""), whole=bool(row.get("whole_words")),
                                    opened=[a for a in row.get("opened") or [] if isinstance(a, str)]))
        elif row.get("empty"):
            panels.append(new_panel("shelf"))
        else:
            problems.append(f"Panel {i} could not be read.")
        if len(panels) > n and row.get("collapsed") is True:
            panels[-1]["thin"] = True
    return str(data.get("name") or ""), panels, problems


def lineup_file_name(name: str) -> str:
    safe = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "-", name).strip(" .") or "line-up"
    return safe[:120] + LINEUP_SUFFIX


def save_lineup(folder: str, data: dict) -> str:
    """Write the line-up into the folder; returns the path. Raises OSError if it cannot."""
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, lineup_file_name(data["name"]))
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, path)
    return path


def list_lineups(folder: str) -> list:
    """[(name, path, saved, n_panels), ...] newest first. Unreadable files are skipped."""
    out = []
    if not folder or not os.path.isdir(folder):
        return out
    for n in os.listdir(folder):
        if not n.endswith(LINEUP_SUFFIX) or n.startswith("."):
            continue
        path = os.path.join(folder, n)
        try:
            with open(path, encoding="utf-8") as fh:
                d = json.load(fh)
            if d.get("format") != LINEUP_FORMAT:
                continue
            out.append((str(d.get("name") or n[: -len(LINEUP_SUFFIX)]), path, str(d.get("saved") or ""), len(d.get("panels") or [])))
        except (OSError, ValueError, AttributeError):
            continue
    out.sort(key=lambda r: r[2], reverse=True)
    return out


def panels_to_tokens(panels: list) -> list:
    """One short string per panel, for the page address (?p=...&p=...)."""
    out = []
    for p in panels:
        if p["kind"] == "piece":
            a = p["piece"]
            t = a
            if p.get("above"):
                t += "^" + ",".join(str(x.count(".") - 1) for x in sorted(p["above"]))
            for c in sorted(p.get("closed") or []):
                if c == a or c.startswith(a + "."):
                    t += "|" + c[len(a):]
            if p.get("mark"):
                t += "~" + p["mark"]
            out.append(t if len(t) <= 400 else a)
        elif p["kind"] == "contents":
            out.append(p["act"])
        elif p["kind"] == "search":
            out.append(("w:" if p.get("whole") else "s:") + p.get("query", ""))
        else:
            out.append("-")
        if p.get("thin"):
            out[-1] = ">" + out[-1]          # a collapsed panel
    return out


def panels_from_tokens(tokens: list) -> list:
    out = []
    for t in tokens:
        thin = t.startswith(">")
        t = t[1:] if thin else t
        if t == "-" or not t:
            out.append(new_panel("shelf"))
        elif t[:2] in ("s:", "w:"):
            out.append(new_panel("search", query=t[2:], whole=t[0] == "w", opened=[]))
        elif "." not in t.split("|")[0].split("~")[0]:
            out.append(new_panel("contents", act=t))
        else:
            mark = None
            if "~" in t:
                t, mark = t.split("~", 1)
            a, *rest = t.split("|")
            levels = ""
            if "^" in a:
                a, levels = a.split("^", 1)
            parts = a.split(".")
            above = sorted(".".join(parts[: int(d) + 2]) for d in levels.split(",") if d.isdigit() and int(d) + 2 < len(parts))
            out.append(new_panel("piece", piece=a, closed=sorted(a + r for r in rest), above=above, mark=mark))
        if thin:
            out[-1]["thin"] = True
    return out


# --------------------------------------------------------------------------
# The page (HTML). Everything that comes from the files is escaped here.
# --------------------------------------------------------------------------
E = html.escape
_RULE = re.compile(r"^\s*-{10,}\s*$")
_MONTHS = "January February March April May June July August September October November December".split()


class _AllBut:
    """A 'closed' set that holds every address except those given (used for search hits,
    whose children start hidden)."""

    def __init__(self, open_ones):
        self.open_ones = set(open_ones)

    def __contains__(self, address):
        return address not in self.open_ones


def long_date(iso: str | None) -> str:
    try:
        d = datetime.date.fromisoformat(iso)
        return f"{_MONTHS[d.month - 1]} {d.day}, {d.year}"
    except (TypeError, ValueError):
        return ""


def act_line(act: Act) -> str:
    bits = [act.name]
    if act.public_law:
        bits.append("Public Law " + act.public_law)
    bits.append(long_date(act.enacted) or "a bill, not enacted")
    return " · ".join(bits)


def _quotes(t: str) -> str:
    return t.replace("``", "“").replace("''", "”")


def _text(t: str, pattern=None) -> str:
    """Escape, show `` '' as printed quotation marks, and mark the search words."""
    if not t:
        return ""
    if pattern is None:
        return E(_quotes(t))
    out, pos = [], 0
    for m in pattern.finditer(t):
        if m.end() == m.start():
            continue
        out.append(E(_quotes(t[pos:m.start()])))
        out.append("<mark>" + E(_quotes(m.group(0))) + "</mark>")
        pos = m.end()
    out.append(E(_quotes(t[pos:])))
    return "".join(out)


def _paragraphs(unit: dict, text: str, pattern) -> list:
    """own_text as a list of blocks: ("p", class, html) paragraphs, or (kind, html) for a
    fixed-width table kept as printed and for a table supplied from the print."""
    if not text:
        return []
    lines = text.split("\n")
    rules = [i for i, ln in enumerate(lines) if _RULE.match(ln)]
    blocks = []
    sup = unit.get("supplement") if isinstance(unit.get("supplement"), dict) else None

    def para(ln):
        if sup and ln.strip() == str(sup.get("replaces", "")).strip():
            head = "".join(f"<th>{E(str(c))}</th>" for c in sup.get("columns") or [])
            body = "".join("<tr>" + "".join(f"<td>{_text(str(c), pattern)}</td>" for c in row) + "</tr>"
                           for row in sup.get("rows") or [])
            cap = (f"Table supplied from {E(str(sup.get('source', 'the print')))}; the working text prints "
                   f"“{E(str(sup.get('replaces', '')))}” here.")
            blocks.append(("table", f'<table class="supp"><caption>{cap}</caption><thead><tr>{head}</tr></thead>'
                                    f"<tbody>{body}</tbody></table>"))
        elif ln.strip():
            start = ln.lstrip()
            cls = "q" if start[:2] == "``" or start[:1] in ('"', "“") else ""
            blocks.append(("p", cls, _text(ln, pattern)))

    if rules:
        for ln in lines[: rules[0]]:
            para(ln)
        blocks.append(("pre", '<pre class="tbl">' + _text("\n".join(lines[rules[0]: rules[-1] + 1]), pattern) + "</pre>"))
        for ln in lines[rules[-1] + 1:]:
            para(ln)
    else:
        for ln in lines:
            para(ln)
    return blocks


def _n_children(n: int) -> str:
    return f"{n} {'child' if n == 1 else 'children'}"


def _piece_html(lib: Library, address: str, closed, pattern, state: dict, top: bool) -> str:
    pc = lib.pieces[address]
    u = pc.unit
    kids = u.get("children") or []
    typ = str(u.get("type", ""))
    is_closed = bool(kids) and address in closed
    A = E(address, True)
    out = [f'<div class="piece t-{E(typ)}{" top" if top else ""}{" closed" if is_closed else ""}" id="a-{A}">']
    if not top:
        out.append(f'<a class="tag" data-go="{A}" title="Click to read this piece alone; \u2318-click to open it in a new panel">{A}</a>')
    # --- first line: fold mark, label, heading, page of the Statutes at Large
    page = u.get("stat_page")
    pg = ""
    if page and page != state.get("page"):
        pg = f'<span class="pg" title="This piece starts on {E(str(page))}">{E(str(page))}</span>'
    if page:
        state["page"] = page
    fold = ""
    if kids:
        fold = (f'<span class="fold" data-fold="{A}" title="{"Show" if is_closed else "Hide"} the {_n_children(len(kids))} '
                f'of this piece">{"▸" if is_closed else "▾"}</span>')
    label, heading = u.get("label"), u.get("heading")
    if top:
        go = f' title="{A}"'
    else:
        go = f' data-go="{A}" title="{A} — click to read this piece alone; ⌘-click to open it in a new panel"'
    blocks = _paragraphs(u, u.get("own_text") or "", pattern)
    first = ""
    if blocks and blocks[0][0] == "p" and not blocks[0][1]:
        first = blocks[0][2]
        blocks = blocks[1:]
    if typ == "section":
        hd = ""
        if heading:
            hd = f' <span class="hd">{_text(heading, pattern)}{"" if u.get("heading_has_no_period") else "."}</span>'
        if heading or not first:
            out.append(f'<div class="line sec">{pg}{fold}<span class="lab"{go}>{E(label or "Sec.")}</span>{hd}</div>')
            if first:
                out.append(f'<p class="own">{first}</p>')
        else:   # 1986 Titles X and XII: "Sec. 1002. The following projects ..." runs on
            out.append(f'<p class="line own">{pg}{fold}<span class="lab secrun"{go}>{E(label or "Sec.")}</span> {first}</p>')
    elif not label and heading:
        # an item or a State group with no label: its heading stands centred, as printed
        out.append(f'<div class="line ctr">{pg}{fold}<span class="hd lab"{go}>{_text(heading, pattern)}</span></div>')
        if first:
            out.append(f'<p class="own">{first}</p>')
    else:
        lab = f'<span class="lab"{go}>{E(label)}</span> ' if label else ""
        hd = ""
        if heading:
            caps = " caps" if heading.upper() == heading else ""
            hd = f'<span class="hd{caps}">{_text(heading, pattern)}</span><span class="dash">.\u2014</span>'
        out.append(f'<p class="line own">{pg}{fold}{lab}{hd}{first}</p>')
    for b in blocks:
        if b[0] == "p":
            out.append(f'<p class="own next {b[1]}">{b[2]}</p>')
        else:
            out.append(b[1])
    # --- notes: oddities the file records about this piece
    notes = []
    if u.get("note"):
        notes.append(str(u["note"]))
    if u.get("label_as_read"):
        notes.append(f"The scan read this label as “{u['label_as_read']}”; it was repaired when the file was built.")
    if u.get("heading_as_read"):
        notes.append(f"The scan read this heading as “{u['heading_as_read']}”; it was repaired when the file was built.")
    if u.get("between_units"):
        notes.append("In the print these words stand between two labelled pieces; the file keeps them as a piece with no label.")
    notes.extend(lib.acts[pc.act].flags.get(address, []))
    for n in notes:
        out.append(f'<div class="note"><b>Note</b> {E(n)}</div>')
    # --- children, or a line saying how many are not shown
    if kids:
        if is_closed:
            out.append(f'<div class="hid" data-fold="{A}" title="Show them">▸ {_n_children(len(kids))} not shown</div>')
        else:
            out.append('<div class="kids">')
            for c in kids:
                out.append(_piece_html(lib, c["id"], closed, pattern, state, False))
            out.append("</div>")
    if u.get("trailing_text"):
        for ln in str(u["trailing_text"]).split("\n"):
            if ln.strip():
                out.append(f'<p class="own trail">{_text(ln, pattern)}</p>')
    out.append("</div>")
    return "".join(out)


def _group_lines(unit: dict) -> str:
    """The division / title / subtitle a section stands under."""
    bits = []
    for lvl in ("division", "title", "subtitle"):
        if unit.get(lvl):
            h = unit.get(lvl + "_heading")
            bits.append(f"{lvl.capitalize()} {E(str(unit[lvl]))}" + (f"—{E(str(h))}" if h else ""))
    return " · ".join(bits)


def _crumbs_html(lib: Library, address: str, closed=()) -> str:
    cr = crumbs(lib, address)
    out = ['<a data-go="" title="The list of acts">All acts</a>']
    for i, (a, words) in enumerate(cr):
        if i == len(cr) - 1:
            out.append(f"<b>{E(words)}</b>")
        else:
            out.append(f'<a data-go="{E(a, True)}" data-from="{E(address, True)}">{E(words)}</a>')
    kids = lib.pieces[address].unit.get("children") or []
    sw = ""
    if kids:
        if address in closed:
            sw = (f'<a class="sw off" data-fold="{E(address, True)}" title="Show the {_n_children(len(kids))} of this piece. '
                  f'Shift-click: in every panel">\u25b8 children hidden</a>')
        else:
            sw = (f'<a class="sw" data-fold="{E(address, True)}" title="Show only the words of this piece itself. '
                  f'Shift-click: in every panel">\u25be children shown</a>')
    return '<nav class="crumbs">' + sw + '<span class="sep">›</span>'.join(out) + "</nav>"


def _above_words(unit: dict, after_heading: bool, pattern) -> str:
    """All of a piece's own words (not its children), for a piece that stands above the one being read."""
    blocks = _paragraphs(unit, unit.get("own_text") or "", pattern)
    out = []
    if blocks and blocks[0][0] == "p":
        sep = ".\u2014" if after_heading else " "
        out.append(f'<span class="lead">{sep}{blocks[0][2]}</span>')
        blocks = blocks[1:]
    for b in blocks:
        out.append(f'<p class="{b[1]}">{b[2]}</p>' if b[0] == "p" else b[1])
    trail = [ln for ln in str(unit.get("trailing_text") or "").split("\n") if ln.strip()]
    if trail:
        out.append('<p class="after">After its children it goes on:</p>')
        out.extend(f"<p>{_text(ln, pattern)}</p>" for ln in trail)
    return "".join(out)


def render_piece(lib: Library, address: str, closed=(), mark: str | None = None, whole: bool = False, above=()) -> str:
    """The page for one piece: where it stands, the act, and the piece with its children.
    `closed` holds the addresses whose children are hidden; `mark` is a search phrase to mark."""
    if address not in lib.pieces:
        key = address.split(".", 1)[0]
        why = (f"The act it belongs to ({E(key)}) is not among the files in the data folder."
               if key not in lib.acts else f"{E(lib.acts[key].name)} is loaded, but it has no piece with this address.")
        return ('<nav class="crumbs"><a data-go="">All acts</a></nav>'
                f'<div class="empty"><b>{E(address)}</b> is not here.<br>{why}</div>')
    pc = lib.pieces[address]
    act = lib.acts[pc.act]
    pattern = match_pattern(mark, whole) if mark else None
    sec = lib.pieces[pc.section].unit
    out = [_crumbs_html(lib, address, closed), '<div class="sheet">']
    scan = (' <span class="scan" title="The text of this act comes from a scan of the printed pages; '
            'some words are misread.">text from a scan</span>') if act.scan else ""
    out.append(f'<div class="actline"><span>{E(act_line(act))}{scan}</span>'
               f'<span class="addr" title="The address of this piece">{E(address)}</span></div>')
    grp = _group_lines(sec)
    if grp:
        out.append(f'<div class="grp">{grp}</div>')
    if pc.depth > 0:
        # the pieces above, one line each, so a narrowed piece still says what it stands under;
        # a click opens a line to all of that piece's own words, and a second click shortens it again
        chain = []
        a = pc.parent
        while a is not None:
            chain.append(a)
            a = lib.pieces[a].parent
        for a in reversed(chain):
            u = lib.pieces[a].unit
            lab = E(u.get("label") or "")
            hd = f' <span class="hd">{_text(u["heading"], pattern)}</span>' if u.get("heading") else ""
            A = E(a, True)
            name = E(cite(lib, a, with_act=False), True)
            if a in above:
                full = _above_words(u, bool(hd), pattern)
                if lab or hd or full:
                    out.append(f'<div class="above open" data-above="{A}" title="Click to shorten {name} again">'
                               f'<span class="tw">\u25be</span>{lab}{hd}{full}</div>')
                continue
            words = (u.get("own_text") or "").split("\n")[0]
            lead = f'<span class="lead">{"." if hd else ""}{"—" if hd else " "}{_text(words[:160])}{"…" if len(words) > 160 else ""}</span>' if words else ""
            if lab or hd or lead:
                out.append(f'<div class="above" data-above="{A}" title="Click to read every word of {name} here">'
                           f'<span class="tw">\u25b8</span>{lab}{hd}{lead}</div>')
    if mark:
        cq = parse_combined(mark)
        marked = E(cq.shown) if cq is not None else f"“{E(mark)}”"
        out.append(f'<div class="marking">Marking {marked} · <a data-ev="unmark">stop marking</a></div>')
    out.append('<div class="text">' + _piece_html(lib, address, closed if isinstance(closed, _AllBut) else set(closed), pattern, {}, True) + "</div>")
    out.append(_neighbours_html(lib, address) + "</div>")
    return "".join(out)


def neighbours(lib: Library, address: str) -> tuple:
    """(address before, address after) among the pieces that share this piece's parent;
    for a section, the sections of its act. None where there is none."""
    pc = lib.pieces[address]
    sibs = ([s["id"] for s in lib.acts[pc.act].sections] if pc.parent is None
            else [c["id"] for c in lib.pieces[pc.parent].unit.get("children") or []])
    i = sibs.index(address)
    return (sibs[i - 1] if i > 0 else None, sibs[i + 1] if i + 1 < len(sibs) else None)


def _short_name(lib: Library, address: str) -> str:
    u = lib.pieces[address].unit
    lab = crumbs(lib, address)[-1][1]
    hd = u.get("heading") or ""
    if not hd:
        hd = (u.get("own_text") or "").split("\n")[0][:48]
    return (lab + " " + hd).strip()


def _neighbours_html(lib: Library, address: str) -> str:
    before, after = neighbours(lib, address)
    if not before and not after:
        return ""
    out = ['<nav class="nbrs">']
    if before:
        out.append(f'<a class="prev" data-go="{E(before, True)}" title="{E(before, True)}">\u2039 {E(_short_name(lib, before))}</a>')
    if after:
        out.append(f'<a class="next" data-go="{E(after, True)}" title="{E(after, True)}">{E(_short_name(lib, after))} \u203a</a>')
    out.append("</nav>")
    return "".join(out)


def render_shelf(lib: Library) -> str:
    """The page of an empty panel: every act, oldest first."""
    out = ['<nav class="crumbs"><b>All acts</b></nav>', '<div class="sheet"><div class="shelf">']
    for key, act in lib.acts.items():
        sub = []
        if act.public_law:
            sub.append("Public Law " + act.public_law)
        sub.append(long_date(act.enacted) or "a bill, not enacted")
        sub.append(f"{len(act.sections)} sections")
        if act.scan:
            sub.append("text from a scan")
        out.append(f'<a class="act" data-go="{E(key, True)}"><span class="nm">{E(act.name)}</span>'
                   f'<span class="sub">{E(" · ".join(sub))}</span></a>')
    out.append("</div>")
    if lib.problems:
        out.append('<div class="warn"><b>Not loaded</b><ul>' + "".join(f"<li>{E(p)}</li>" for p in lib.problems) + "</ul></div>")
    out.append('<div class="hint">Choose an act, or type in the box above and press Return. '
               "An address goes straight there: <i>1986 401</i> &nbsp;<i>1996 211(e)(1)</i> &nbsp;"
               "<i>section 903(c) of the Water Resources Development Act of 1986</i>. "
               "Anything else is looked for in every act: <i>nonnavigab</i> &nbsp;<i>3104</i>. "
               "Words between quotation marks are always looked for: <i>&quot;1986&quot;</i>. "
               "Join phrases with AND, OR or NOT to look for them together: "
               "<i>&quot;if the Secretary determines&quot; AND &quot;construct&quot;</i></div>"
               '<div class="hint">On a page of an act: click a label such as <i>(a)</i> to read that piece alone; '
               "the line at the top of the page takes you back up; \u25be hides the children of a piece. "
               "\u2039 and \u203a beside the box go back and forward. "
               "Hold \u2318 while you click or press Return to open in a new panel instead.</div></div>")
    return "".join(out)


def render_contents(lib: Library, key: str) -> str:
    """The contents page of one act: its titles and every section."""
    if key not in lib.acts:
        return ('<nav class="crumbs"><a data-go="">All acts</a></nav>'
                f'<div class="empty">No act with addresses beginning <b>{E(key)}</b> is in the data folder.</div>')
    act = lib.acts[key]
    out = [f'<nav class="crumbs"><a data-go="">All acts</a><span class="sep">›</span><b>{E(act.name)}</b></nav>',
           '<div class="sheet">']
    out.append(f'<div class="acthead"><div class="nm">{E(act.name)}</div>'
               f'<div class="sub">{E(act_line(act).split(" · ", 1)[-1])}</div>')
    if act.part and act.part != "the whole act":
        out.append(f'<div class="sub">This file holds: {E(act.part)}</div>')
    if act.scan:
        out.append('<div class="sub">The text comes from a scan of the printed pages; some words are misread.</div>')
    out.append(f'<div class="sub">{len(act.sections)} sections, {act.n_pieces:,} pieces</div></div>')
    last = None
    out.append('<div class="toc">')
    for s in act.sections:
        grp = _group_lines(s)
        if grp != last and grp:
            out.append(f'<div class="grp">{grp}</div>')
        last = grp
        hd = E(s.get("heading") or "")
        if not hd:
            words = s.get("own_text") or ""
            if not words and s.get("children"):
                words = s["children"][0].get("own_text") or ""
            hd = f'<span class="nohd">{E(words[:70])}…</span>' if words else ""
        out.append(f'<a class="sec" data-go="{E(s["id"], True)}" title="{E(s["id"], True)}">'
                   f'<span class="no">{E(str(s.get("number", "")))}</span><span class="hd">{hd}</span></a>')
    out.append("</div></div>")
    return "".join(out)


def _hit_head(lib: Library, a: str, is_open: bool, extra: str = "") -> str:
    """Opens the block of one search hit: where it is, and the links to read it."""
    A = E(a, True)
    return (f'<div class="hit{" open" if is_open else ""}">'
            f'<div class="hline"><a class="where" data-hit="{A}" title="{A} — click to read it here">'
            f'{"▾" if is_open else "▸"} {E(cite(lib, a, with_act=False))}</a>{extra}'
            f'<span class="acts"><a data-here="{A}" title="Leave the list and read {A} in this panel; ‹ comes back to the list">go to it</a>'
            f'<a data-open="{A}" title="Open {A} in a new panel beside this one">open beside ›</a></span></div>')


def _more_line(act_name: str, key: str, n_all: int, n_shown: int) -> str:
    """The line under an act's hits that says how many are held back; "" when all are shown."""
    left = n_all - n_shown
    if left <= 0:
        return ""
    step = min(left, 100)
    return (f'<div class="morehits">{left:,} more in {E(act_name)} are not shown. '
            f'<a data-more="{E(key, True)}" data-n="{n_shown + step}">show {step} more</a>'
            + (f' · <a data-more="{E(key, True)}" data-n="all">show all {n_all:,}</a>' if left > step else "")
            + "</div>")


def _snips(lib: Library, address: str, patterns: list, mark, width: int = 150) -> list:
    """Stretches of one piece's own words around the first place each pattern occurs, as html with
    the search words marked. Stretches that meet are joined into one."""
    u = lib.pieces[address].unit
    heading = u.get("heading") or ""
    rest = " ".join(t for t in (u.get("own_text"), u.get("trailing_text")) if t).replace("\n", " ")
    text = heading + ".—" + rest if heading and rest else heading or rest      # a heading runs in as printed
    spans = []
    for rx in patterns:
        m = rx.search(text)
        if m:
            spans.append((max(0, m.start() - width // 3), min(len(text), m.end() + (2 * width) // 3)))
    spans.sort()
    joined = []
    for a, b in spans:
        if joined and a <= joined[-1][1]:
            joined[-1] = (joined[-1][0], max(b, joined[-1][1]))
        else:
            joined.append((a, b))
    out = []
    for a, b in joined:
        seg, lead, tail = text[a:b], "", ""
        if a > 0:                                   # start and end at a whole word (never inside a match:
            lead = "…"                              # a match stands at least width/3 from either end)
            if " " in seg[:40]:
                seg = seg.split(" ", 1)[1]
        if b < len(text):
            tail = "…"
            if " " in seg[-40:]:
                seg = seg.rsplit(" ", 1)[0]
        out.append(lead + _text(seg, mark) + tail)
    return out


def _render_combined(lib: Library, panel: dict, words: str, cq: Combined, per_act: int) -> str:
    """The page of a combined search: the pieces that match in their own words, act by act, then
    the pieces that match only together with the pieces under them."""
    whole = bool(panel.get("whole"))
    res = search(lib, words, whole)
    pattern = match_pattern(words, whole)
    term_patterns = [phrase_pattern(t, whole) for t in cq.terms]
    out = ['<nav class="crumbs"><a data-go="" title="The list of acts">All acts</a><span class="sep">›</span><b>Search</b></nav>',
           '<div class="sheet">', f'<div class="reshead"><div class="q">{E(cq.shown)}</div></div>']
    mode = "Whole words only." if whole else "Parts of words count too."
    other = "count parts of words too" if whole else "whole words only"
    one = res.total == 1
    out.append(f'<div class="reshead"><div class="n"><b>{res.total:,}</b> {"piece matches" if one else "pieces match"} in '
               f'{"its" if one else "their"} own words, in {len(res.by_act)} of {len(lib.acts)} acts. '
               f'{mode} <a data-ev="whole">{other}</a></div>')
    if res.apart_total:
        one = res.apart_total == 1
        out.append(f'<div class="n"><b>{res.apart_total:,}</b> more {"matches" if one else "match"} only when the pieces under '
                   f'{"it" if one else "them"} are counted. <a data-jump="apart">Go down to {"it" if one else "them"}</a></div>')
    if res.total:
        chips = "".join(f'<a class="chip" data-jump="g-{E(k, True)}" title="Go down to {E(lib.acts[k].name, True)}">'
                        f"{E(k)} <i>{len(v):,}</i></a>" for k, v in res.by_act.items())
        out.append(f'<div class="chips">{chips}</div>')
    out.append("</div>")
    if not res.total and not res.apart_total:
        out.append('<div class="empty">No piece matches. Check the spelling, or try fewer words. '
                   "Acts whose text comes from a scan contain misread words.</div></div>")
        return "".join(out)
    more = panel.get("more") or {}
    opened = set(panel.get("opened") or [])
    folded = _AllBut(panel.get("closed") or [])     # a hit in its own words opens with its children hidden: "closed" lists those shown
    unfolded = set(panel.get("closed") or [])       # a split hit opens with its children shown: "closed" lists those hidden
    shown_total = 0

    def listing(by_act: dict, apart: bool):
        nonlocal shown_total
        for key, addrs in by_act.items():
            act = lib.acts[key]
            mkey = key + "+" if apart else key
            limit = more.get(mkey, per_act)
            show = addrs if limit == "all" else addrs[: int(limit)]
            shown_total += len(show)
            out.append(f'<div class="group" id="{"s" if apart else "g"}-{E(key, True)}"><div class="ghead">{E(act.name)} '
                       f'<span>{len(addrs):,} {"piece" if len(addrs) == 1 else "pieces"}</span></div>')
            last_sec = None
            for a in show:
                pc = lib.pieces[a]
                if pc.section != last_sec:
                    su = lib.pieces[pc.section].unit
                    out.append(f'<div class="hsec">Sec. {E(str(su.get("number", "")))}. {E(su.get("heading") or "")}</div>')
                    last_sec = pc.section
                A = E(a, True)
                is_open = a in opened
                extra = ""
                if apart:
                    n = pieces_under(lib, a)
                    extra = f' <span class="x">with {n:,} {"piece" if n == 1 else "pieces"} under it</span>'
                out.append(_hit_head(lib, a, is_open, extra))
                if is_open:
                    out.append('<div class="text inhit">'
                               + _piece_html(lib, a, unfolded if apart else folded, pattern, {}, True) + "</div>")
                elif apart:
                    where = {}                      # each piece that has one of the phrases -> the phrases it has
                    for ph, at in term_places(lib, a, cq.terms, whole):
                        if at:
                            where.setdefault(at, []).append(phrase_pattern(ph, whole))
                    for at in sorted(where, key=lambda x: lib.pieces[x].order):
                        for s in _snips(lib, at, where[at], pattern):
                            out.append(f'<div class="snip" data-hit="{A}" title="Click to read it here">'
                                       f'<span class="at">{E(cite(lib, at, with_act=False))}</span>{s}</div>')
                else:
                    snips = _snips(lib, a, term_patterns, pattern)
                    for s in snips or [E(_quotes(own_words(pc.unit)[:150].replace("\n", " ")))]:
                        out.append(f'<div class="snip" data-hit="{A}" title="Click to read it here">{s}</div>')
                out.append("</div>")
            out.append(_more_line(act.name, mkey, len(addrs), len(show)))
            out.append("</div>")

    listing(res.by_act, False)
    if res.apart_total:
        one = res.apart_total == 1
        out.append('<div class="aparthead" id="apart">Split between a piece and the pieces under it</div>'
                   f'<div class="apartnote">{"This piece matches" if one else "These pieces match"} only when read together '
                   f'with the pieces under {"it" if one else "them"}. The smallest such piece is listed, and each line says '
                   "where the words are. A piece with many pieces under it may join words that stand far apart.</div>")
        chips = "".join(f'<a class="chip" data-jump="s-{E(k, True)}" title="Go down to {E(lib.acts[k].name, True)}">'
                        f"{E(k)} <i>{len(v):,}</i></a>" for k, v in res.apart.items())
        out.append(f'<div class="chips">{chips}</div>')
        listing(res.apart, True)
    total = res.total + res.apart_total
    if shown_total < total:
        out.append(f'<div class="foot">{shown_total:,} of {total:,} pieces are listed: the first {per_act} in each act, '
                   "unless you asked for more. Each act says how many it is holding back.</div>")
    else:
        out.append(f'<div class="foot">All {total:,} pieces are listed.</div>')
    out.append("</div>")
    return "".join(out)


_COMBINE_TIP = ("To look for two things together, put each in quotation marks and join them with AND, OR or NOT: "
                "<i>&quot;if the Secretary determines&quot; AND &quot;construct&quot;</i>")


def render_results(lib: Library, panel: dict, per_act: int = 20) -> str:
    """The page of a search: the sections a bare number names, then every piece that has the words, act by act.
    Phrases joined by AND, OR, NOT have their own page (_render_combined)."""
    words, quoted, numbered = search_plan(lib, panel.get("query") or "")
    whole = bool(panel.get("whole"))
    cq = parse_combined(words)
    if cq is not None:
        return _render_combined(lib, panel, words, cq, per_act)
    out = ['<nav class="crumbs"><a data-go="" title="The list of acts">All acts</a><span class="sep">›</span><b>Search</b></nav>',
           '<div class="sheet">']
    if not normalize(words):
        out.append('<div class="hint">Type a word or a phrase in the box above and press Return. Every piece, in every act, '
                   "that has it in its heading or in its own text is listed here. Capitals do not matter. "
                   f"{_COMBINE_TIP}</div></div>")
        return "".join(out)
    res = search(lib, words, whole)
    pattern = match_pattern(words, whole)
    out.append(f'<div class="reshead"><div class="q">“{E(words)}”</div></div>')
    if numbered:
        m = _BARE_NUMBER.match(words)
        what = f"Sec. {words} in each act that has it" if m.group(2) else f"Sections numbered {m.group(1)}"
        out.append(f'<div class="numbered"><div class="nhead">{E(what)}</div>')
        for a in numbered:
            pc = lib.pieces[a]
            u = pc.unit
            hd = u.get("heading") or (u.get("own_text") or "").split("\n")[0][:90]
            A = E(a, True)
            out.append(f'<a class="nsec" data-go="{A}" title="{A} — click to read it in this panel; ⌘-click to open it in a new panel">'
                       f'<span class="nm">{E(lib.acts[pc.act].name)}</span>'
                       f'<span class="ct">{E(cite(lib, a, with_act=False))}</span><span class="hd">{_text(hd)}</span></a>')
        out.append("</div>")
    mode = "Whole words only." if whole else "Parts of words count too."
    other = "count parts of words too" if whole else "whole words only"
    verb = ("mentions" if res.total == 1 else "mention") if numbered else ("has" if res.total == 1 else "have")
    out.append(f'<div class="reshead"><div class="n"><b>{res.total:,}</b> {"piece" if res.total == 1 else "pieces"} {verb} it, '
               f'in {len(res.by_act)} of {len(lib.acts)} acts. {mode} <a data-ev="whole">{other}</a></div>')
    if res.total:
        chips = "".join(f'<a class="chip" data-jump="g-{E(k, True)}" title="Go down to {E(lib.acts[k].name, True)}">'
                        f"{E(k)} <i>{len(v):,}</i></a>" for k, v in res.by_act.items())
        out.append(f'<div class="chips">{chips}</div>')
    out.append("</div>")
    if not res.total:
        tip = " " + _COMBINE_TIP if re.search(r"\b(?:AND|OR|NOT)\b", words) else ""
        out.append('<div class="empty">No piece has these words. Check the spelling, or try fewer words. '
                   f"Acts whose text comes from a scan contain misread words.{tip}</div></div>")
        return "".join(out)
    more = panel.get("more") or {}
    opened = set(panel.get("opened") or [])
    spread = _AllBut(panel.get("closed") or [])     # in a search panel, "closed" lists the hits whose children are shown
    shown_total = 0
    for key, addrs in res.by_act.items():
        act = lib.acts[key]
        limit = more.get(key, per_act)
        show = addrs if limit == "all" else addrs[: int(limit)]
        shown_total += len(show)
        out.append(f'<div class="group" id="g-{E(key, True)}"><div class="ghead">{E(act.name)} '
                   f'<span>{len(addrs):,} {"piece" if len(addrs) == 1 else "pieces"}</span></div>')
        last_sec = None
        for a in show:
            pc = lib.pieces[a]
            if pc.section != last_sec:
                su = lib.pieces[pc.section].unit
                out.append(f'<div class="hsec">Sec. {E(str(su.get("number", "")))}. {E(su.get("heading") or "")}</div>')
                last_sec = pc.section
            h = hit_detail(lib, a, pattern)
            A = E(a, True)
            times = f' <span class="x">{h.count}×</span>' if h.count > 1 else ""
            is_open = a in opened
            out.append(_hit_head(lib, a, is_open, times))
            if is_open:
                out.append('<div class="text inhit">' + _piece_html(lib, a, spread, pattern, {}, True) + "</div>")
            else:
                hd = ' <span class="inhd">in the heading</span>' if h.where == "heading" else ""
                out.append(f'<div class="snip" data-hit="{A}" title="Click to read it here">{E(_quotes(h.before))}'
                           f"<mark>{E(_quotes(h.match))}</mark>{E(_quotes(h.after))}{hd}</div>")
            out.append("</div>")
        out.append(_more_line(act.name, key, len(addrs), len(show)))
        out.append("</div>")
    if shown_total < res.total:
        out.append(f'<div class="foot">{shown_total:,} of {res.total:,} pieces are listed: the first {per_act} in each act, '
                   "unless you asked for more. Each act says how many it is holding back.</div>")
    else:
        out.append(f'<div class="foot">All {res.total:,} pieces are listed.</div>')
    out.append("</div>")
    return "".join(out)
