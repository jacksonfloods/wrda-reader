"""app.py -- the WRDA Reader: the Water Resources Development Acts, piece by piece and side by side.

Start:  streamlit run app.py
            shows the acts in the data folder beside this file. Nothing is saved on the computer it runs on.
        streamlit run app.py -- --data FOLDER [--lineups FOLDER]
            shows your own structure files, and saves line-ups in a folder of yours
            (or set WRDA_READER_DATA / WRDA_READER_LINEUPS).

Started with no folder, the reader is fit for a public site: the page offers no way to name a folder
on the computer it runs on, and line-ups are kept by page address, download and upload only.
"""
import argparse
import hashlib
import json
import os
import sys
import time

import streamlit as st

import reader_logic as L

HERE = os.path.dirname(os.path.abspath(__file__))
PER_ACT = 20            # hits shown per act before "show more"
MIN_PANEL = 340         # px: panels share the screen down to this width, then the row scrolls sideways


def launch_options():
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--data", default=os.environ.get("WRDA_READER_DATA", ""))
    ap.add_argument("--lineups", default=os.environ.get("WRDA_READER_LINEUPS", ""))
    ap.add_argument("--fragments", default=os.environ.get("WRDA_READER_FRAGMENTS", "0"))
    ns, _ = ap.parse_known_args(sys.argv[1:])
    return ns


OPT = launch_options()
USE_FRAGMENTS = OPT.fragments not in ("0", "no", "false")
BUNDLED = os.path.join(HERE, "data")            # the acts that come with the reader
HAS_BUNDLED = os.path.isdir(BUNDLED) and bool(L.structure_files(BUNDLED))
# Started with no folder: the reader shows the acts that came with it and, because it may be running on
# a public site, never asks for a folder on the computer it runs on and never writes there.
HOSTED = HAS_BUNDLED and not OPT.data and not OPT.lineups

st.set_page_config(page_title="WRDA Reader", layout="wide", initial_sidebar_state="collapsed")
ss = st.session_state


@st.cache_resource(show_spinner="Reading the acts…")
def library(folder: str, signature: tuple) -> L.Library:
    return L.load_library(folder)


def read_beside(name: str) -> str:
    with open(os.path.join(HERE, name), encoding="utf-8") as fh:
        return fh.read()


@st.cache_resource
def panel_component(js: str, css: str):
    """The panel as the browser draws it. It is kept for as long as page.js and page.css stay the same and
    made again when either changes, so a reader that is updated while it runs (as a public site is) never
    goes on using the panel script of the version before."""
    return st.components.v2.component("wrda_panel", js=js, css=css)


PANEL = panel_component(read_beside("page.js"), read_beside("page.css"))


@st.cache_resource
def remembered() -> dict:
    """The folders in use, kept for as long as the reader runs, so that a reloaded page does not ask again."""
    data = os.path.expanduser(OPT.data) if OPT.data else (BUNDLED if HAS_BUNDLED else "")
    return {"data": data, "lineups": os.path.expanduser(OPT.lineups)}

# ---------------------------------------------------------------- session
if "data_dir" not in ss:
    ss.data_dir = remembered()["data"]
    ss.lineups_dir = remembered()["lineups"]
    ss.next_id = 1
    ss.w_name = ""
    ss.saved_tokens = None
    ss.notice = None
    ss.focus = None
    ss.reveal = None
    ss.focus_n = 0
    ss.up_n = 0
    ss.runs = 0
ss.runs += 1


def focus_on(pid):
    """Put the cursor in this panel's box, and bring the panel into view, on the next draw."""
    ss.focus_n += 1
    ss.focus = (pid, ss.focus_n) if pid is not None else None
    ss.reveal = ss.focus


def reveal(pid):
    ss.focus_n += 1
    ss.reveal = (pid, ss.focus_n)


def give_id(panel: dict) -> dict:
    panel["id"] = ss.next_id
    ss.next_id += 1
    return panel


def set_panels(panels: list):
    ss.panels = [give_id(p) for p in panels]


# ---------------------------------------------------------------- first launch: where are the files?
def setup_screen(problems):
    st.title("WRDA Reader")
    if HOSTED:                      # the bundled acts could not be read: say so, and offer no folder box
        for p in problems or ["The acts that come with the reader could not be read."]:
            st.error(p)
        st.stop()
    st.write("This reader shows the Water Resources Development Acts from their structure files "
             "(the files whose names end in `.structure.json`). Tell it where they are.")
    with st.form("where"):
        folder = st.text_input("Folder that holds the structure files", value=ss.data_dir,
                               placeholder="/path/to/work/structure")
        ok = st.form_submit_button("Open this folder", type="primary")
    if ok:
        ss.data_dir = os.path.expanduser(folder.strip())
        st.rerun()
    for p in problems:
        st.error(p)
    st.caption("You can also give the folder when you start the reader:  "
               "`streamlit run app.py -- --data FOLDER --lineups FOLDER`")
    st.stop()


def get_library():
    folder = ss.data_dir
    if not folder or not os.path.isdir(folder):
        return None, ([f"There is no folder at {folder}."] if folder else [])
    lib = library(folder, L.folder_signature(folder))
    return lib, lib.problems


LIB, PROBLEMS = get_library()
if LIB is None or not LIB.acts:
    setup_screen(PROBLEMS)
remembered()["data"] = ss.data_dir

def adopt_tokens(tokens: list):
    """The browser moved in its history (Back / Forward) or the address was edited:
    make the screen match the address, keeping the panels that have not changed."""
    fresh = L.panels_from_tokens(tokens)
    have = L.panels_to_tokens(ss.panels)
    out = []
    for i, p in enumerate(fresh):
        if i < len(ss.panels) and have[i].lstrip(">") == tokens[i].lstrip(">"):
            ss.panels[i].pop("thin", None)           # the same page; only collapsed or not may differ
            if tokens[i].startswith(">"):
                ss.panels[i]["thin"] = True
            out.append(ss.panels[i])                 # untouched: keeps its place on the page
        elif i < len(ss.panels):
            old = ss.panels[i]
            p["id"] = old["id"]                      # same column, new page: the old one joins its history
            p["back"] = list(old.get("back") or []) + [L.snapshot(old)]
            out.append(p)
        else:
            out.append(give_id(p))
    ss.panels = out


url_tokens = st.query_params.get_all("p")
if "panels" not in ss:
    set_panels(L.panels_from_tokens(url_tokens) if url_tokens else [L.new_panel("shelf")])
    if not url_tokens:
        focus_on(ss.panels[0]["id"])
elif url_tokens != ss.get("synced_tokens", []):
    adopt_tokens(url_tokens or ["-"])


# ---------------------------------------------------------------- what a click does
def panel_by_id(pid):
    return next((p for p in ss.panels if p["id"] == pid), None)


def show_piece(p: dict, address: str, said=None, to=None, up=False, mark=None, whole=False):
    """Point the panel at a piece. "Children hidden" is the panel's own setting and stays;
    folds made by hand lower down, the parents opened in full, and the marked words, last
    while the panel stays in one section."""
    was_piece = p.get("kind") == "piece"
    old = p.get("piece") if was_piece else None
    old_section = LIB.pieces[old].section if old in LIB.pieces else None
    new_section = LIB.pieces[address].section if address in LIB.pieces else None
    same = old_section is not None and old_section == new_section
    hidden = was_piece and old in (p.get("closed") or []) and not up     # going up a level shows where the piece stood
    closed = [c for c in (p.get("closed") or []) if c != old] if same else []
    if hidden:
        closed.append(address)
    above = [a for a in (p.get("above") or []) if address.startswith(a + ".")] if same else []
    if mark is None and same:
        mark, whole = p.get("mark"), bool(p.get("whole"))
    page = dict(piece=address, closed=sorted(closed), above=above, mark=mark or None)
    if mark and whole:
        page["whole"] = True
    L.set_page(p, "piece", **page)
    p.update(said=said, to=to, keep=False)


def box_context(p: dict):
    """(act, section) that a bare number, or a bare (c), typed in this panel's box refers to."""
    if p["kind"] == "piece" and p["piece"] in LIB.pieces:
        return LIB.pieces[p["piece"]].act, LIB.pieces[p["piece"]].section
    if p["kind"] == "contents":
        return p["act"], None
    return None, None


def show_found(p: dict, f):
    """Point the panel at what read_box() made of the text in the box."""
    if f.kind == "piece":
        show_piece(p, f.address, said=f.said)
    elif f.kind == "contents":
        L.set_page(p, "contents", act=f.address)
        p["said"] = f.said
    elif f.kind == "search":
        # a number starts as whole words (401 is not 1401); other words keep the panel's setting
        whole = L.is_bare_number(f.address) or (p.get("kind") == "search" and bool(p.get("whole")))
        L.set_page(p, "search", query=f.address, whole=whole, opened=[], more={}, closed=[])
        p["said"] = f.said
    else:
        L.set_page(p, "shelf")


def handle(pid: int, ev: dict):
    p = panel_by_id(pid)
    if p is None:
        return
    t = ev.get("t")
    y = ev.get("y") or 0                    # where the page was scrolled to when the click was made
    p.update(said=None, to=None, keep=False, y=None)
    i = ss.panels.index(p)
    before = L.snapshot(p, y)
    if t == "typed":
        p["boxver"] = str(time.time())
        f = L.read_box(LIB, ev.get("text", ""), *box_context(p))
        target = p
        if ev.get("beside") and f.kind != "shelf":
            # Command-Return: this panel stays; what was typed opens in a new panel to its right
            target = give_id(L.new_panel("shelf"))
            ss.panels.insert(i + 1, target)
            reveal(target["id"])
            ss.full = True
        show_found(target, f)
        L.remember(p, before)
    elif t == "go":
        a = ev.get("a", "")
        if a == "":
            L.set_page(p, "shelf")
        elif a in LIB.acts:
            L.set_page(p, "contents", act=a)
        elif a in LIB.pieces:
            came_from = ev.get("from") or None
            show_piece(p, a, to=came_from, up=bool(came_from) and came_from.startswith(a + "."))
        L.remember(p, before)
    elif t == "here":
        # a search hit takes over the panel; the back button returns to the list
        a = ev.get("a")
        if a in LIB.pieces:
            words = L.search_plan(LIB, p.get("query", ""))[0] if p["kind"] == "search" else ""
            show_piece(p, a, mark=words or None, whole=bool(p.get("whole")))
            L.remember(p, before)
    elif t == "back":
        if L.go_back(p, y):
            p["boxver"] = str(time.time())
    elif t == "fwd":
        if L.go_forward(p, y):
            p["boxver"] = str(time.time())
    elif t == "above":
        # a piece that stands above the one being read: all of its own words, or one line again
        above = set(p.get("above") or [])
        above.symmetric_difference_update({ev.get("a")})
        p["above"] = sorted(above)
        p["keep"] = True
    elif t == "fold":
        a = ev.get("a")
        closed = set(p.get("closed") or [])
        closed.symmetric_difference_update({a})
        p["closed"] = sorted(closed)
        p["keep"] = True
        if ev.get("all") and p["kind"] == "piece" and a == p["piece"]:
            # Shift-click on "children shown / hidden": every panel follows this one
            hide = a in closed
            for other in ss.panels:
                if other["kind"] == "piece" and other is not p:
                    c = set(other.get("closed") or [])
                    (c.add if hide else c.discard)(other["piece"])
                    other["closed"] = sorted(c)
                    other["keep"] = True
    elif t == "hit":
        opened = list(p.get("opened") or [])
        a = ev.get("a")
        opened.remove(a) if a in opened else opened.append(a)
        p["opened"] = opened
        p["keep"] = True
    elif t == "more":
        more = dict(p.get("more") or {})
        c = ev.get("c")
        more[ev.get("k")] = "all" if c == "all" else int(c)
        p["more"] = more
        p["keep"] = True
    elif t == "whole":
        p["whole"] = not p.get("whole")
        p["more"] = {}
    elif t == "unmark":
        p["mark"] = None
        p["keep"] = True
    elif t == "open":
        a = ev.get("a")
        if a == "":
            new = give_id(L.new_panel("shelf"))
        elif a in LIB.acts:
            new = give_id(L.new_panel("contents", act=a))
        else:
            words = L.search_plan(LIB, p.get("query", ""))[0] if p["kind"] == "search" else ""
            new = give_id(L.new_panel("piece", piece=a, closed=[], above=[], mark=words or None))
            if words and p.get("whole"):
                new["whole"] = True
            if ev.get("to") in LIB.pieces:          # opened to show one piece inside it: go there
                new["to"] = ev["to"]
        ss.panels.insert(i + 1, new)          # right beside the panel it came from
        reveal(new["id"])
        ss.full = True
    elif t == "thin":
        # collapse the panel to a spine that keeps its place in the row, or open it again
        if p.pop("thin", None):
            reveal(p["id"])
        else:
            p["thin"] = True
        ss.full = True
    elif t == "move":
        # the panel was dragged to another place in the row; its page, history and scroll go with it
        try:
            to = int(ev.get("to"))
        except (TypeError, ValueError):
            to = i
        if L.move_panel(ss.panels, i, to):
            ss.full = True
    elif t == "close":
        ss.panels.remove(p)
        if not ss.panels:
            set_panels([L.new_panel("shelf")])
        ss.full = True


def on_event(slot: int):
    """What to do when the panel drawn in this column of the row reports a click. The column is kept when
    another panel comes to stand in it, so the click itself says which panel it was made in."""
    def cb():
        res = ss.get(f"slot_{slot}")
        ev = res.get("ev") if res else None
        if not ev:
            return
        pid = ev.get("id")
        if pid is None and slot < len(ss.panels):
            # a page that was open before the reader was updated may still run the panel script of the
            # version before, whose clicks do not say which panel: it is the one standing in this column
            pid = ss.panels[slot]["id"]
        if pid is not None:
            handle(int(pid), dict(ev))
    return cb


# ---------------------------------------------------------------- one panel
def panel_data(p: dict) -> dict:
    kind = p["kind"]
    thin = bool(p.get("thin"))
    if thin:
        page, box = "", ""          # a collapsed panel sends no page: it is drawn when the panel is opened again
    elif kind == "piece":
        page = L.render_piece(LIB, p["piece"], p.get("closed") or (), p.get("mark"), bool(p.get("whole")), p.get("above") or ())
        box = L.box_text(LIB, p["piece"]) if p["piece"] in LIB.pieces else p["piece"]
    elif kind == "contents":
        page = L.render_contents(LIB, p["act"])
        box = p["act"]
    elif kind == "search":
        page = L.render_results(LIB, p, PER_ACT)
        box = p.get("query", "")
    else:
        page = L.render_shelf(LIB)
        box = ""
    return {
        "id": p["id"],
        "kind": kind,
        "html": page,
        "ver": "thin" if thin else hashlib.md5(page.encode("utf-8")).hexdigest(),
        "box": box,
        "boxver": p.get("boxver", "") + "|" + box,
        "placeholder": "Address or words: 1986 401(a), 3104, levee",
        "boxhelp": ("Type an address (1986 401(a), 401, (c), or a citation as printed) or words to find, and press Return. "
                    "Words between quotation marks are always looked for. "
                    'Join phrases with AND, OR or NOT to look for them together: "levee" AND "construct".'),
        "said": p.get("said"),
        "to": p.get("to"),
        "keep": bool(p.get("keep")),
        "y": p.get("y"),
        "can_back": bool(p.get("back")),
        "can_fwd": bool(p.get("fwd")),
        "thin": thin,
        "spine": L.spine_text(LIB, p) if thin else "",
        "focus": str(ss.focus[1]) if ss.focus and ss.focus[0] == p["id"] else "",
        "reveal": str(ss.reveal[1]) if ss.reveal and ss.reveal[0] == p["id"] else "",
    }


def sync_address():
    """Keep the line-up in the page address, so a reload or a bookmark brings it back."""
    tokens = L.panels_to_tokens(ss.panels)
    if tokens == ["-"]:
        tokens = []                      # one empty panel: a clean address
    if tokens != st.query_params.get_all("p"):
        st.query_params.from_dict({"p": tokens} if tokens else {})
    ss.synced_tokens = tokens


def draw_panel(slot: int):
    """Draw the panel that stands at this place in the row. The piece of the page that shows it belongs to
    the place, not to the panel: when panels are moved, each place is handed its new panel and nothing is
    taken down and put up again."""
    if USE_FRAGMENTS and ss.get("full"):
        ss.full = False
        st.rerun()          # the row itself changed: redraw the whole screen
    if slot >= len(ss.panels):
        return
    p = ss.panels[slot]
    PANEL(key=f"slot_{slot}", data=panel_data(p), on_ev_change=on_event(slot))
    p["y"] = None            # the place to scroll back to is used once
    if USE_FRAGMENTS:
        sync_address()


if USE_FRAGMENTS:
    draw_panel = st.fragment(draw_panel)


# ---------------------------------------------------------------- the bar
def add_panel():
    new = give_id(L.new_panel("shelf"))
    ss.panels.append(new)
    focus_on(new["id"])


def clear_screen():
    set_panels([L.new_panel("shelf")])
    ss.w_name = ""
    ss.open_name = None
    ss.saved_tokens = None
    focus_on(ss.panels[0]["id"])


def current_lineup() -> dict:
    return L.lineup_to_dict(LIB, ss.w_name.strip() or "untitled", ss.panels)


def save_clicked():
    name = ss.w_name.strip()
    if not name:
        ss.notice = ("warn", "Give the line-up a name first.")
        return
    data = current_lineup()
    if ss.lineups_dir:
        target = os.path.join(ss.lineups_dir, L.lineup_file_name(name))
        if os.path.exists(target) and name != ss.get("open_name") and ss.get("asked_replace") != name:
            ss.asked_replace = name
            ss.notice = ("warn", f"A line-up named \u201c{name}\u201d is already saved. Press Save again to replace it, or change the name.")
            return
        ss.asked_replace = None
        try:
            path = L.save_lineup(ss.lineups_dir, data)
            ss.open_name = name
            ss.notice = ("ok", f"Saved “{name}” in {os.path.dirname(path)}")
            ss.saved_tokens = L.panels_to_tokens(ss.panels)
            return
        except OSError as e:
            ss.notice = ("warn", f"Could not write in {ss.lineups_dir} ({e.__class__.__name__}). Use Files › Download instead.")
            return
    ss.notice = ("warn", "No folder for line-ups is set, so nothing was written. Use Files › Download this line-up, or set a folder there.")


def open_lineup(data, source: str):
    name, panels, problems = L.lineup_from_dict(data)
    if not panels:
        ss.notice = ("warn", " ".join(problems) or f"{source} holds no panels.")
        return
    set_panels(panels)
    ss.w_name = name
    ss.open_name = name
    ss.saved_tokens = L.panels_to_tokens(ss.panels)
    ss.notice = ("ok", f"Opened “{name}”" + ((" — " + " ".join(problems)) if problems else ""))


SPINE = 40              # px: the width of a collapsed panel


st.html("""<style>
header[data-testid="stHeader"] { display: none; }
[data-testid="stMainBlockContainer"] { padding: 8px 12px 0 12px; max-width: none; }
.st-key-topbar { min-height: 44px; }
.st-key-topbar [data-testid="stForm"] { padding: 0; border: 0; }
.st-key-row [data-testid="stColumn"] { min-width: %dpx; }
/* the column of a collapsed panel is as narrow as its spine; the panel marks its own column (page.js),
   so the width changes in the same instant as what the column shows */
.st-key-row [data-testid="stColumn"][data-wrda-thin="1"] { flex: 0 0 %dpx !important; width: %dpx !important; min-width: %dpx !important; }
/* messages appear at the bottom right, clear of the bar and its menus */
[data-testid="stToastContainer"] { top: auto !important; bottom: 12px; }
</style>""" % (MIN_PANEL, SPINE, SPINE, SPINE))

saved = L.list_lineups(ss.lineups_dir)


def open_chosen():
    row = next((r for r in saved if r[0] == ss.get("open_menu")), None)
    if row is None:
        return
    try:
        with open(row[1], encoding="utf-8") as fh:
            open_lineup(json.load(fh), row[0])
    except (OSError, ValueError) as e:
        ss.notice = ("warn", f"Could not open {os.path.basename(row[1])} ({e.__class__.__name__}).")


def file_given():
    up = ss.get(f"up_{ss.up_n}")
    if up is None:
        return
    try:
        open_lineup(json.loads(up.getvalue().decode("utf-8")), up.name)
    except (ValueError, UnicodeDecodeError):
        ss.notice = ("warn", f"{up.name} is not a line-up file.")
    ss.up_n += 1


def folders_changed():
    ss.lineups_dir = os.path.expanduser(ss.w_lineups_dir.strip())
    ss.data_dir = os.path.expanduser(ss.w_data_dir.strip())
    remembered()["lineups"] = ss.lineups_dir


with st.container(horizontal=True, vertical_alignment="center", gap="small", key="topbar"):
    st.markdown("**WRDA Reader**", width="content")
    st.button("Add a panel", icon=":material/add:", on_click=add_panel, key="add_panel", shortcut="Mod+J")
    st.space("stretch")
    tokens_now = L.panels_to_tokens(ss.panels)
    if HOSTED:
        pass                        # nothing is saved on the computer the reader runs on: see Files
    elif ss.saved_tokens is None:
        st.caption("Line-up not saved", width="content")
    elif tokens_now != ss.saved_tokens:
        st.caption("\u25cf Changed since it was saved", width="content")
    else:
        st.caption("\u2713 Saved", width="content")
    if not HOSTED:
        with st.form("save_form", border=False, width=380):
            with st.container(horizontal=True, vertical_alignment="center", gap="xsmall"):
                st.text_input("Line-up name", key="w_name", label_visibility="collapsed",
                              placeholder="Name this line-up to save it")
                st.form_submit_button("Save", on_click=save_clicked)
        if saved:
            st.menu_button("Open", options=[r[0] for r in saved], key="open_menu", on_click=open_chosen,
                           help=f"Line-ups saved in {ss.lineups_dir}")
        else:
            st.button("Open", disabled=True, key="open_none",
                      help=("No line-ups are saved in the folder yet" if ss.lineups_dir else "Set a folder for line-ups under Files"))
    st.button("Clear", on_click=clear_screen, key="clear", help="Close every panel and start a new line-up")
    with st.popover("Files", key="files"):
        if HOSTED:
            st.caption("The address of this page holds the line-up on the screen: copy it to share it, or bookmark it "
                       "to come back. A line-up can also be kept as a small file.")
        st.download_button("Download this line-up", data=json.dumps(current_lineup(), indent=1, ensure_ascii=False),
                           file_name=L.lineup_file_name(ss.w_name.strip() or "untitled"), mime="application/json",
                           on_click="ignore", icon=":material/download:")
        st.file_uploader("Open a line-up file", type=["json"], key=f"up_{ss.up_n}", on_change=file_given)
        if not HOSTED:              # folders on this computer: offered only when the reader was started with one
            st.text_input("Folder for saved line-ups", value=ss.lineups_dir, key="w_lineups_dir", placeholder="/path/to/lineups",
                          on_change=folders_changed)
            st.caption(f"{len(saved)} line-ups in this folder." if ss.lineups_dir and os.path.isdir(ss.lineups_dir)
                       else ("This folder does not exist yet; it is made on the first save." if ss.lineups_dir else
                             "Without a folder, save a line-up with Download and reopen it with the box above."))
            st.text_input("Folder that holds the structure files", value=ss.data_dir, key="w_data_dir", on_change=folders_changed)
        st.caption(f"{len(LIB.acts)} acts, {len(LIB.pieces):,} pieces." + (f" {len(PROBLEMS)} files not loaded." if PROBLEMS else ""))

if ss.notice:
    kind, words = ss.notice
    st.toast(words, icon=":material/check:" if kind == "ok" else ":material/warning:", duration="long" if kind != "ok" else "short")
    ss.notice = None

# ---------------------------------------------------------------- the row of panels
sync_address()
cols = st.container(key="row").columns(len(ss.panels), gap="xsmall", wrap=False)
for slot, col in enumerate(cols):
    with col:
        draw_panel(slot)
ss.focus = None
ss.reveal = None
