"""browser_check.py -- start the reader, use it in a hidden browser, print PASS or FAIL for each step, stop the reader.

Run:  python browser_check.py [DATA_FOLDER]          (default: the data folder beside this file)
Needs the development environment (wrda_reader_dev_env.yml): Playwright and its Chromium.
The reader is checked twice: started with a folder, and started with none, as on a public site.
Nothing is written: no line-up is saved, and the reader is stopped at the end whatever happens.
Set WRDA_SHOTS to a folder to also get pictures of the screen there.
"""
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("WRDA_READER_DATA") or os.path.join(HERE, "data")
SHOTS = os.environ.get("WRDA_SHOTS")
results = []


def check(name, ok, detail=""):
    print(("PASS  " if ok else "FAIL  ") + name + (f"   <- {detail}" if detail and not ok else ""), flush=True)
    results.append(bool(ok))


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def port_is_free(port):
    """True if nothing answers on the port any more."""
    try:
        socket.create_connection(("127.0.0.1", port), timeout=1).close()
        return False
    except OSError:
        return True


def wait_health(port, seconds=90):
    t0 = time.time()
    while time.time() - t0 < seconds:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/_stcore/health", timeout=2) as r:
                if r.status == 200:
                    return True
        except OSError:
            pass
        time.sleep(0.5)
    return False


def settle(pg, quiet_ms=300, timeout=20000):
    """Wait until the panels have stopped changing and Streamlit is idle."""
    t0 = time.time()
    last = None
    since = time.time()
    while time.time() - t0 < timeout / 1000:
        cur = pg.evaluate("() => [window.__wrda ? window.__wrda.swaps : -1, window.__wrda ? (window.__wrda.paints||0) : -1, "
                          "!!document.querySelector('[data-testid=\"stStatusWidget\"]')]")
        if cur != last:
            last = cur
            since = time.time()
        elif (time.time() - since) * 1000 >= quiet_ms and not cur[2]:
            return
        pg.wait_for_timeout(40)


def run_checks(url):
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        pg = browser.new_page(viewport={"width": 1440, "height": 900})
        msgs = []
        pg.on("console", lambda m: msgs.append(m.type + ": " + m.text))
        pg.on("pageerror", lambda e: msgs.append("PAGEERROR " + str(e)))
        pg.goto(url, wait_until="domcontentloaded")
        pg.locator(".panel .page").first.wait_for(timeout=90000)
        settle(pg)

        def panel(i):
            return pg.locator(".panel").nth(i)

        def n_panels():
            return pg.locator(".panel").count()

        def has(i, selector):
            return panel(i).locator(selector).count() > 0

        def type_in(i, text, key="Enter"):
            b = panel(i).locator(".box")
            b.click()
            b.fill(text)
            b.press(key)
            settle(pg)

        def click(i, selector, nth=0):
            panel(i).locator(selector).nth(nth).click()
            settle(pg)

        def addr(i):
            a = panel(i).locator(".actline .addr")
            return a.first.inner_text().strip() if a.count() else ""

        def scroll_top(i):
            return panel(i).locator(".page").evaluate("e => Math.round(e.scrollTop)")

        def enabled(i, selector):
            return panel(i).locator(selector).is_enabled()

        def shot(name):
            if SHOTS:
                os.makedirs(SHOTS, exist_ok=True)
                pg.screenshot(path=os.path.join(SHOTS, name))

        # ---- the opening screen
        check("opening screen lists the acts", panel(0).locator(".shelf .act").count() >= 14,
              f"{panel(0).locator('.shelf .act').count()} acts listed")
        check("no separate Word search button", pg.get_by_role("button", name="Word search").count() == 0)
        check("back and forward start switched off", not enabled(0, ".back") and not enabled(0, ".fwd"))

        # ---- one box: a bare number on the opening screen is a search that lists the sections first
        type_in(0, "3104")
        check("typing 3104 gives a list in the same panel", n_panels() == 1 and has(0, ".group .hit"))
        check("the section numbered 3104 comes first", has(0, '.numbered .nsec[data-go="2007.3104"]'))
        check("the box keeps what was typed", panel(0).locator(".box").input_value() == "3104")
        shot("1-list-for-3104.png")

        # ---- an entry opens in place, takes over the panel, and back returns to the list where it was left
        type_in(0, "levee")
        n_hits = panel(0).locator(".hit").count()
        check("typing a word gives a list", n_hits >= 12, f"{n_hits} hits shown")
        click(0, ".hit .where", 2)
        check("clicking an entry opens it in place", panel(0).locator(".hit.open").count() == 1 and n_panels() == 1)
        target = panel(0).locator("[data-here]").nth(11)
        want = target.get_attribute("data-here")
        target.scroll_into_view_if_needed()
        pg.wait_for_timeout(150)
        y0 = scroll_top(0)
        target.click()
        settle(pg)
        check("'go to it' shows the piece in the same panel", n_panels() == 1 and addr(0) == want, f"{addr(0)} vs {want}")
        check("the words looked for are marked in it", has(0, ".text mark"))
        check("back is switched on", enabled(0, ".back"))
        click(0, ".back")
        y1 = scroll_top(0)
        check("back returns to the list", has(0, ".group .hit") and panel(0).locator(".box").input_value() == "levee")
        check("the entry opened in place is still open", panel(0).locator(".hit.open").count() == 1)
        check("the list is where it was left", y0 > 0 and abs(y1 - y0) <= 4, f"left at {y0}, back at {y1}")
        check("forward is switched on", enabled(0, ".fwd"))
        click(0, ".fwd")
        check("forward returns to the piece", addr(0) == want)

        # ---- one box: an address goes straight there
        type_in(0, "1986 401(a)")
        check("typing 1986 401(a) goes there", addr(0) == "1986.401.a", addr(0))
        geo = panel(0).evaluate("""root => {
          const p = root.querySelector('.page').getBoundingClientRect(), s = root.querySelector('.sheet').getBoundingClientRect(),
                c = root.querySelector('.crumbs a[data-go]').getBoundingClientRect();
          return {left: Math.round(s.left - p.left), right: Math.round(p.right - s.right), crumb: Math.round(c.left - s.left)};
        }""")
        check("the column of text stands in the middle of a wide panel", geo["left"] > 100 and abs(geo["left"] - geo["right"]) <= 20,
              f"{geo['left']} px on its left, {geo['right']} px on its right")
        check("the line at the top starts where the text starts", abs(geo["crumb"]) <= 2, f"{geo['crumb']} px apart")
        child = (panel(0).locator(".kids > .piece").nth(1).get_attribute("id") or "")[2:]
        type_in(0, child)
        check("an address as shown on the page goes there", bool(child) and addr(0) == child, f"{addr(0)} vs {child}")

        # ---- the parent's line opens to all of its own words, in place
        line = panel(0).locator('.above[data-above="1986.401.a"]')
        check("the parent shows as one cut-off line", line.count() == 1 and "open" not in (line.get_attribute("class") or ""))
        short = len(line.inner_text())
        line.click()
        settle(pg)
        line = panel(0).locator('.above[data-above="1986.401.a"]')
        long = len(line.inner_text())
        check("clicking it shows all of the parent's own words", "open" in (line.get_attribute("class") or "") and long > short + 100,
              f"{short} characters before, {long} after")
        check("the panel stays on the piece", addr(0) == child)
        shot("2-parent-opened.png")
        line.click()
        settle(pg)
        line = panel(0).locator('.above[data-above="1986.401.a"]')
        check("clicking again shortens it", "open" not in (line.get_attribute("class") or ""))
        click(0, '.crumbs a[data-go="1986.401.a"]')
        check("the line at the top travels up to the parent", addr(0) == "1986.401.a", addr(0))

        # ---- a bare number means the act on the page; if that act lacks it, a list that says so
        type_in(0, "903")
        check("903 typed in WRDA 1986 goes to its section 903", addr(0) == "1986.903", addr(0))
        type_in(0, "3104")
        said = panel(0).locator(".said")
        check("3104 typed in WRDA 1986 gives a list that says why",
              has(0, '.numbered .nsec[data-go="2007.3104"]') and said.is_visible() and "has no section 3104" in said.inner_text())
        click(0, '.numbered .nsec[data-go="2007.3104"]')
        check("clicking the section in the list goes there", addr(0) == "2007.3104", addr(0))
        click(0, ".back")
        check("back returns to that list", has(0, '.numbered .nsec[data-go="2007.3104"]'))

        # ---- quotation marks always mean a word search
        type_in(0, '"1986"')
        check('"1986" in quotation marks is looked for as words', has(0, ".reshead") and not has(0, ".acthead"))
        type_in(0, "1986")
        check("1986 without them opens the act", has(0, ".acthead") and has(0, ".toc .sec"))

        # ---- new panels open beside the one they came from
        type_in(0, "1996 211", key="Control+Enter")
        check("Command-Return opens what was typed in a new panel beside", n_panels() == 2 and addr(1) == "1996.211", addr(1))
        type_in(0, "nonnavigab")
        first = panel(0).locator("[data-open]").first.get_attribute("data-open")
        click(0, "[data-open]", 0)
        check("'open beside' puts the entry in a new panel right beside", n_panels() == 3 and addr(1) == first, f"{addr(1)} vs {first}")
        click(1, ".close")
        check("closing a panel removes it", n_panels() == 2)

        # ---- a panel collapses to a spine in its place, and opens again where it was left
        def is_thin(i):
            return "thin" in (panel(i).get_attribute("class") or "").split()

        def width(i):
            return panel(i).bounding_box()["width"]

        type_in(1, "1986 401")
        panel(1).locator(".page").evaluate("e => { e.scrollTop = 900; }")
        pg.wait_for_timeout(250)
        y_open = scroll_top(1)
        w_before = width(0)
        click(1, ".head .slim")
        check("a panel collapses to a spine", is_thin(1) and width(1) <= 60, f"{width(1)} px wide")
        check("the spine names what the panel holds", "sec. 401" in panel(1).locator(".spine .st").inner_text())
        check("the open panel takes the room", width(0) > w_before + 300, f"{w_before} px before, {width(0)} px after")
        check("the page address remembers the collapse", "p=%3E" in pg.url or "p=>" in pg.url, pg.url[-80:])
        panel(1).locator(".spine").click()
        settle(pg)
        check("clicking the spine opens it again where it was left",
              not is_thin(1) and addr(1) == "1986.401" and y_open > 0 and abs(scroll_top(1) - y_open) <= 4,
              f"left at {y_open}, back at {scroll_top(1)}")
        for _ in range(4):
            pg.locator(".st-key-add_panel button").click()
            settle(pg)
        for i in (5, 4, 3, 2):
            click(i, ".head .slim")
        row = pg.locator(".st-key-row").evaluate("e => [e.scrollWidth, e.clientWidth]")
        check("six panels with four collapsed: the two open ones share the screen",
              n_panels() == 6 and [is_thin(i) for i in range(6)] == [False, False, True, True, True, True]
              and width(0) > 500 and abs(width(0) - width(1)) <= 4 and row[0] <= row[1] + 2,
              f"widths {[round(width(i)) for i in range(6)]}, row {row}")
        shot("3-four-collapsed.png")

        # ---- a combined search: phrases in quotation marks joined by AND
        type_in(0, '"if the secretary determines" AND "construct"')
        check("phrases joined by AND are looked for together",
              "AND" in panel(0).locator(".reshead .q").inner_text() and has(0, '.group[id^="g-"] .hit .snip mark'))
        shot("4-combined-search.png")
        click(0, '[data-jump="apart"]')
        check("the hits split over the pieces under a piece come second and say where each phrase is",
              scroll_top(0) > 0 and has(0, '.group[id^="s-"] .hit .snip .at'))
        shot("5-combined-split.png")
        click(0, '.group[id^="s-"] .hit .where')
        opened = panel(0).locator('.group[id^="s-"] .hit.open')
        check("a split hit opens in place with the pieces under it shown and the phrases marked",
              opened.count() == 1 and opened.locator(".kids .piece").count() > 0 and opened.locator("mark").count() >= 2)
        click(0, '.group[id^="s-"] .hit.open [data-here]')
        check("going to a hit marks every phrase on its page",
              has(0, ".marking") and "AND" in panel(0).locator(".marking").inner_text()
              and panel(0).locator(".text mark").count() >= 2)

        # ---- started with a folder, the reader can save line-ups there
        check("started with a folder, Save is offered", pg.get_by_role("button", name="Save", exact=True).count() == 1)

        # ---- nothing went wrong behind the scenes
        errs = [m for m in msgs if m.startswith("PAGEERROR") or m.startswith("error")]
        exc = pg.locator('[data-testid="stException"]').all_inner_texts()
        check("no errors in the browser or the reader", not errs and not exc, " | ".join((errs + exc)[:3])[:500])
        browser.close()


def run_hosted_checks(url):
    """The reader started with no folder, as on a public site: the acts that come with it, and nothing
    that names or writes to a folder on the computer it runs on."""
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        pg = browser.new_page(viewport={"width": 1440, "height": 900})
        msgs = []
        pg.on("console", lambda m: msgs.append(m.type + ": " + m.text))
        pg.on("pageerror", lambda e: msgs.append("PAGEERROR " + str(e)))
        pg.goto(url, wait_until="domcontentloaded")
        pg.locator(".panel .page").first.wait_for(timeout=90000)
        settle(pg)
        n_acts = pg.locator(".panel .shelf .act").count()
        check("with no folder given, the reader shows the acts that come with it", n_acts >= 14, f"{n_acts} acts listed")
        check("it offers no Save and no Open of line-ups kept where it runs",
              pg.get_by_role("button", name="Save", exact=True).count() == 0
              and pg.locator(".st-key-open_none, .st-key-open_menu").count() == 0)
        pg.locator(".st-key-files button").first.click()
        settle(pg)
        check("Files offers a download and an upload, and no box for a folder",
              pg.get_by_text("Download this line-up").count() > 0
              and pg.get_by_label("Folder for saved line-ups").count() == 0
              and pg.get_by_label("Folder that holds the structure files").count() == 0)
        if SHOTS:
            os.makedirs(SHOTS, exist_ok=True)
            pg.screenshot(path=os.path.join(SHOTS, "6-public-files-menu.png"))
        pg.keyboard.press("Escape")
        settle(pg)
        box = pg.locator(".panel .box").first
        box.click()
        box.fill("1996 301(b)(9)")
        box.press("Enter")
        settle(pg)
        other = browser.new_page(viewport={"width": 1440, "height": 900})
        other.goto(pg.url, wait_until="domcontentloaded")
        other.locator(".panel .page").first.wait_for(timeout=90000)
        settle(other)
        a = other.locator(".panel .actline .addr")
        check("the page address alone brings the line-up back in another window",
              a.count() > 0 and a.first.inner_text().strip() == "1996.301.b.9", pg.url[-60:])
        errs = [m for m in msgs if m.startswith("PAGEERROR") or m.startswith("error")]
        exc = pg.locator('[data-testid="stException"]').all_inner_texts()
        check("no errors in the browser or the reader", not errs and not exc, " | ".join((errs + exc)[:3])[:500])
        browser.close()


def with_reader(reader_args, checks):
    """Start the reader with these arguments, run the checks against it, and stop it."""
    port = free_port()
    log = tempfile.TemporaryFile(mode="w+")
    env = {k: v for k, v in os.environ.items() if not k.startswith("WRDA_READER_")}
    server = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", "app.py", "--server.port", str(port), "--server.address", "127.0.0.1",
         "--server.headless", "true", "--server.fileWatcherType", "none", "--browser.gatherUsageStats", "false"]
        + (["--"] + reader_args if reader_args else []),
        cwd=HERE, env=env, stdout=log, stderr=subprocess.STDOUT)
    try:
        if not wait_health(port):
            check("the reader starts", False, "no answer on port %d" % port)
        else:
            try:
                checks(f"http://127.0.0.1:{port}")
            except Exception as e:      # a step that could not even be tried
                check("the check ran to the end", False, f"{e.__class__.__name__}: {str(e)[:400]}")
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait()
        log.seek(0)
        text = log.read()
        if "Traceback" in text:
            print("--- from the reader's own log ---")
            print(text[-1500:])
        print("reader stopped; its port is free" if port_is_free(port) else f"WARNING: port {port} is still in use")


def main():
    if not os.path.isdir(DATA):
        print("FAIL  no folder of structure files at " + DATA)
        return 1
    with_reader(["--data", DATA], run_checks)
    if os.path.isdir(os.path.join(HERE, "data")):
        print("--- started with no folder, as on a public site")
        with_reader([], run_hosted_checks)
    print(f"{sum(results)} of {len(results)} steps passed")
    return 0 if results and all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
