"""Drive the running Hermes window for live Media Dock checks.

The gate (tests/render_gate.py) proves logic against a stub host. This proves the
pixels: it talks to the local cua-driver daemon, captures the Hermes window, clicks
window-local screenshot pixels, and saves a PNG I can look at.

The pane's own controls ARE in the UIA tree (`state()` returns them with label,
value and disabled), so drive it by element token, not by pixels: `click-label`,
`labels`, and `nav` all read the live tree. Pixel `click X Y` remains for the
guest page itself, which has no UIA elements.

`nav` and `palette` are the two composite moves this plugin needs:
  nav <url>        set the URL field with ValuePattern, then press Go  (no typing)
  palette <text>   Ctrl+K, type, Enter — e.g. `palette "reload desktop plugins"`

Keys and text need `delivery_mode:"foreground"` (cua-driver drops background keys
on Chromium); `key()` / `type_text()` already pass it.

Usage:
  python tests/live.py where                 # Hermes pid/window id + screenshot size
  python tests/live.py shot out.png          # capture to a PNG
  python tests/live.py click X Y             # click window-local pixels (guest page)
  python tests/live.py click-label Detach    # click a UIA element by exact label
  python tests/live.py labels media          # list UIA labels/values matching a word
  python tests/live.py nav https://example.com
  python tests/live.py palette "reload desktop plugins"
  python tests/live.py queue [base-url] [--cap]  # assert the queue loop live (starts the 8771 fixture server itself)
  python tests/live.py autoadvance [base-url]    # a queued file that ends must play the next item
  python tests/live.py rails [base-url]          # exactly one transport rail after a source switch
  python tests/live.py resume <mp4-url> [secs]   # play, pause, leave, return: does it resume?
  python tests/live.py type "some text"      # type into the focused field
  python tests/live.py key Enter
"""
import base64
import json
import os
import re
import shutil
import subprocess
import sys
import time

# The live checks drive the app through the CUA UIA driver, which this repo does not ship.
# Point CUA_DRIVER at the executable, or leave it on PATH as `cua-driver`. No home layout assumed.
DRIVER = os.environ.get("CUA_DRIVER") or shutil.which("cua-driver") or ""
APP_TITLE = "Hermes"


def call(tool, **kwargs):
    if not DRIVER:
        raise SystemExit("live checks need the CUA driver: set CUA_DRIVER to its executable path")
    proc = subprocess.run(
        [DRIVER, "call", tool, "--json", json.dumps(kwargs)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
    )
    out = (proc.stdout or "").strip()
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        raise SystemExit(f"{tool} failed ({proc.returncode}): {out or proc.stderr}")
    if isinstance(data, dict) and (data.get("success") is False or data.get("refusal")):
        raise SystemExit(f"{tool} refused: {data.get('error') or data.get('refusal') or data}")
    return data


def window():
    """The Hermes main window: {pid, window_id, width, height}. Exits if absent."""
    for w in call("list_windows").get("_legacy_windows", []):
        if str(w.get("title", "")).strip() == APP_TITLE:
            return w
    raise SystemExit("Hermes window not found — is the app open?")


def state():
    """Full UIA snapshot + a PNG of the window (base64 in the payload).

    The host can swap its window (a hot reload or a pane rebuild does it), which leaves
    one call holding a dead window id. Re-list and retry once instead of ending the run.
    """
    for attempt in range(2):
        w = window()
        try:
            d = call("get_window_state", pid=w["pid"], window_id=w["window_id"])
        except SystemExit as exc:
            if attempt or "No window" not in str(exc):
                raise
            time.sleep(1.0)
            continue
        d["_window"] = w
        return d


def shot(path):
    d = state()
    png = base64.b64decode(d["screenshot_png_b64"])
    with open(path, "wb") as fh:
        fh.write(png)
    return {
        "path": os.path.abspath(path),
        "width": d.get("screenshot_width"),
        "height": d.get("screenshot_height"),
        "elements": len(d.get("elements") or []),
        "window": d["_window"],
    }


# Transcript text can carry the same words as a control (a chat message saying
# "Open Media Dock" shadowed the real button and clicks landed on the message).
# Prefer a real control, and let callers pin the role.
ACTIONABLE = ("Button", "TabItem", "ListItem", "TreeItem", "MenuItem", "Tab")
# Top band of the app window is its titlebar (min/max/close), never a plugin control.
CHROME_BAND = 40
# Only these labels can BE the titlebar buttons. Filtering every label by y hid the dock's
# own address bar, which sits at y=35 when the pane starts at the window's top edge.
TITLEBAR_LABELS = frozenset({"close", "minimise", "minimize", "restore", "maximise", "maximize"})


def find(d, label, role=None, pane=False):
    hits = [e for e in d.get("elements") or [] if str(e.get("label", "")).strip() == label]
    if role:
        hits = [e for e in hits if str(e.get("role", "")) == role]
    # Never hand back the window's own chrome. A bare "Close" resolved to the app's
    # titlebar button once: it put a Quit dialog on screen and every later click in the
    # run landed on the modal.
    hits = [e for e in hits if str(e.get("label", "")).strip().lower() not in TITLEBAR_LABELS
            or ((e.get("frame") or {}).get("y") is None
                or (e.get("frame") or {}).get("y") >= CHROME_BAND)]
    if pane:
        inside = [id(e) for e in _pane_els(label, role, snapshot=d)]
        scoped = [e for e in hits if id(e) in inside]
        hits = scoped or hits
    for e in hits:
        if str(e.get("role", "")) in ACTIONABLE:
            return e
    return hits[0] if hits else None


def click_xy(x, y):
    # Coordinate clicks are synthetic events: they reach the renderer only when the
    # point really is inside the control. Prefer click_label (UIA element token),
    # which the renderer honours regardless of foreground state.
    w = window()
    return call("click", pid=w["pid"], window_id=w["window_id"], x=int(x), y=int(y))


def click_token(element):
    """Click one exact element from a `state()` snapshot.

    This is the only click path that reliably reaches the renderer: coordinate
    clicks are synthetic and often land nowhere, and delivery_mode:"foreground"
    fails whenever the shell steals the foreground. A re-render between snapshot and
    click makes the driver refuse the token as stale, so on that one refusal the
    element is re-resolved by label+role (nearest y when a label repeats) and clicked
    again — the same control, a newer handle.
    """
    # window(), never state(): a second snapshot invalidates the caller's tokens.
    w = window()
    try:
        return call("click", pid=w["pid"], window_id=w["window_id"], element_token=element["element_token"])
    except SystemExit as err:
        if "stale" not in str(err):
            raise
    label, role = str(element.get("label") or ""), str(element.get("role") or "")
    y0 = (element.get("frame") or {}).get("y") or 0
    d = state()
    hits = [e for e in d.get("elements") or []
            if e.get("label") == label and e.get("role") == role and (e.get("frame") or {}).get("x") is not None]
    if not hits:
        raise SystemExit(f"element {label!r} vanished before the click landed")
    hits.sort(key=lambda e: abs(((e.get("frame") or {}).get("y") or 0) - y0))
    w2 = d["_window"]
    return call("click", pid=w2["pid"], window_id=w2["window_id"], element_token=hits[0]["element_token"])


def click_token_real(element):
    """A FOREGROUND click: the renderer counts it as a user gesture, so `play()` is allowed.

    The default token click routes through the accessibility tree and is NOT trusted — a
    queue row clicked that way loads the file and leaves it at 0:00. Use this only where a
    real gesture is the thing under test; it steals the foreground for a moment.
    """
    w = window()
    return call("click", pid=w["pid"], window_id=w["window_id"], element_token=element["element_token"], delivery_mode="foreground")


def click_label(label, role=None, pane=False):
    d = state()
    e = find(d, label, role, pane=pane)
    if not e:
        raise SystemExit(f"no element labelled {label!r} in this window")
    # Element-token clicks are the reliable path here: they synthesise events on the
    # exact control, while delivery_mode:"foreground" adds a strict assertion that
    # fails whenever the shell grabs the foreground between calls.
    w = d["_window"]
    return call("click", pid=w["pid"], window_id=w["window_id"], element_token=e["element_token"])


def type_text(text):
    w = window()
    # driver tool is `type_text` (character-by-character PostMessage); "type" is not a tool name
    return call("type_text", pid=w["pid"], window_id=w["window_id"], text=text, delivery_mode="foreground")


def key(*parts):
    # The driver's hotkey tool takes an ARRAY of chord tokens: ['ctrl','a'] or ['Return'].
    # Accept ('ctrl','a'), ('ctrl+a',), (['ctrl','a'],) so callers don't have to care.
    toks = []
    for part in parts:
        if isinstance(part, (list, tuple)):
            toks.extend(str(x).strip() for x in part if str(x).strip())
        else:
            toks.extend(t.strip() for t in str(part).replace(",", "+").split("+") if t.strip())
    w = window()
    return call("hotkey", pid=w["pid"], window_id=w["window_id"], keys=toks, delivery_mode="foreground")


def by_label(label, role=None):
    d = state()
    return d, find(d, label, role)


def press(d, element):
    """Invoke one control, preferring the element-token path.

    A foreground click is refused (`foreground_unavailable`) whenever anything steals
    focus mid-run — a toast, the shell, an antivirus popup — which made an unattended
    queue walk die at a random step. The renderer honours a token click without the
    foreground, so that is tried first and the foreground mode is the fallback.
    """
    w = d["_window"]
    last = None
    for attempt in range(3):
        try:
            return call("click", pid=w["pid"], window_id=w["window_id"], element_token=element["element_token"])
        except SystemExit as exc:
            last = exc
            time.sleep(0.5)  # a re-render can stale the token; the next try is the same control
    raise last


def set_url(url):
    # An Edit, not any element whose text happens to read "URL": transcript text
    # and the guest page can both carry that word and a false hit makes the
    # "is the pane open?" probe lie.
    d, e = by_label("URL", "Edit")
    if not e:
        raise SystemExit("no URL field on screen (is the dock open?)")
    w = d["_window"]
    call("set_value", pid=w["pid"], window_id=w["window_id"], element_token=e["element_token"], value=url)
    time.sleep(0.5)


def nav(url, wait=4.5, verify=True):
    """Load a URL without typing: one snapshot, ValuePattern on the field, click Go.

    A `state()` costs ~5 s on this window, so a navigation that took two snapshots
    (field, then Go) cost more than the page load it triggered.
    """
    focus()
    d = state()
    e = find(d, "URL", "Edit")
    if not e:
        raise SystemExit("no URL field on screen (is the dock open?)")
    g = find(d, "Go")
    if not g:
        raise SystemExit("no Go button on screen")
    w = d["_window"]
    call("set_value", pid=w["pid"], window_id=w["window_id"], element_token=e["element_token"], value=url)
    press(d, g)
    time.sleep(wait)
    if not verify:
        return {"url": url}
    _, f = by_label("URL", "Edit")
    got = str((f or {}).get("value") or "")
    # A Go click that landed nowhere left the OLD page loaded while the field still
    # showed the new text, so every later assertion read a page nobody navigated to.
    if got.rstrip("/") != url.rstrip("/"):
        raise SystemExit("navigation did not load: wanted %r, field shows %r" % (url, got))
    return {"url": got}


def _hwnd():
    return int(window()["window_id"])


def _foreground_ok(hwnd):
    """Read-only check: is this window foreground right now? Never steals focus.

    No keybd_event, no SetForegroundWindow, no ShowWindow. Synthesising an Alt tap to
    grab focus is indistinguishable from the agent driving the user's desktop, and it
    can hit the app's own menu accelerators. The only source of foreground here is the
    driver's own `bring_to_front`.
    """
    try:
        import ctypes
        return ctypes.windll.user32.GetForegroundWindow() == hwnd
    except Exception:
        return False


def focus():
    """Report whether the window is foreground — and NEVER raise it.

    bring_to_front yanks the window over whatever the owner is doing, which is a visible
    hijack of his desktop. Element-token clicks reach the renderer without the
    foreground, so a window that stays behind is a note, not a reason to act.
    """
    w = window()
    return {"raised": None, "foreground": _foreground_ok(int(w["window_id"])), "note": "never brought to front"}


def ensure_pane():
    """Bring up the DOCKED pane beside the chat, never the sidebar page.

    The status chip (`Open Media Dock`, bottom of the pane column) opens the pane
    and leaves the chat readable; the sidebar `Media Dock` entry swaps the whole
    shell to the plugin's route page and hides the conversation, so it is only a
    last resort.
    """
    focus()
    d, e = by_label("URL", "Edit")
    if e:
        return d
    # A floating card in focus mode hides the address bar but still owns the dock's
    # controls; that is an open pane, not a missing one.
    if _pane_box():
        return state()

    def chip_from(snapshot):
        best = None
        for el in snapshot.get("elements") or []:
            if (el.get("label") or "").strip() != "Open Media Dock" or not el.get("frame"):
                continue
            if str(el.get("role")) != "Button":
                continue
            # The chip sits in the status row, low in the window; transcript text
            # that happens to read the same words sits higher up.
            if el["frame"]["y"] > (snapshot.get("_window", {}).get("height", 1080) * 0.85):
                best = el
        return best

    for _ in range(3):
        d, _ = by_label("URL", "Edit")
        chip = chip_from(d)
        if not chip:
            break
        # A plain element click: foreground delivery pops the Windows taskbar on this
        # machine and is only worth it when the gesture itself is what is under test.
        click_token(chip)
        time.sleep(2.0)
        d2, field = by_label("URL", "Edit")
        if field:
            return d2
        # A docked pane whose group is shorter than its chrome renders no address bar;
        # its own controls still prove the surface is up.
        if _pane_box(d2):
            return d2

    for _ in range(2):
        d, item = by_label("Media Dock", "Button")
        if not item:
            break
        # Token click only: a foreground click is a visible takeover of the owner's screen.
        click_token(item)
        time.sleep(2.5)
        d2, field = by_label("URL", "Edit")
        if field:
            return d2
    raise SystemExit("Media Dock did not come up (chip and sidebar entry both probed)")


def ensure_url_field():
    """Guarantee the address bar is on screen before a test navigates.

    The bar only renders on a surface wide enough for it — a docked band is not — so a
    time-ordered suite that starts there dies on its first nav. Detach floats the pane
    (a card always shows the bar); the placement stays one click away from where it was.
    """
    for _ in range(3):
        d, f = by_label("URL", "Edit")
        if f:
            return True
        e = find(d, "Detach", "Button") or find(d, "Dock", "Button")
        if not e:
            time.sleep(1.2)
            continue
        click_token(e)
        time.sleep(2.8)
    d, f = by_label("URL", "Edit")
    return bool(f)


def time_text():
    """The native player's 'M:SS / M:SS' readout, or None when it is not exposed."""
    d = state()
    for e in d.get("elements") or []:
        lab = str(e.get("label") or "")
        if re.match(r"^\d+:\d\d / \d+:\d\d$", lab):
            return lab
    return None


def resume_test(url, secs=8.0):
    """Play, pause, leave, come back — the readout must land near where we paused."""
    ensure_pane()
    ensure_url_field()
    nav(url, wait=6)
    click_label("Play/Pause")
    time.sleep(float(secs))
    click_label("Play/Pause")
    time.sleep(0.8)
    paused = time_text()
    nav("https://example.com/", wait=3)
    nav(url, wait=6)
    time.sleep(1.2)
    return {"paused_at": paused, "reopened_at": time_text()}


PANES_MIN_X = -960


# The dock moves: a right-edge pane, a bottom pane, a floating card. Anchoring on its own
# controls finds it wherever the host put it; a fixed x threshold silently returned nothing
# whenever the pane was not on the right, which read as "the queue lost Add current".
PANE_ANCHORS = ("Media Dock settings", "Add current", "In queue", "Clear", "Shuffle")


def _pane_box(snapshot=None):
    d = snapshot or state()
    boxes = []
    for e in d.get("elements") or []:
        lab = str(e.get("label") or "")
        f = e.get("frame") or {}
        if f.get("x") is None:
            continue
        # Only controls count: the same words appear in chat prose and in run cards as
        # Text, and one sentence mentioning "In queue" used to fake an open pane.
        if str(e.get("role")) not in ("Button", "Edit"):
            continue
        if (lab in PANE_ANCHORS or lab.startswith("Card size ") or lab.startswith("Play/Pause")
                or lab.startswith("Seek") or lab.startswith("Volume ")
                or lab.startswith("playback speed") or lab.startswith("Page playback speed")
                or lab.startswith("Fullscreen")):
            boxes.append(f)
    if not boxes:
        return None
    left = min(b["x"] for b in boxes)
    right = max(b["x"] + b["w"] for b in boxes)
    top = min(b["y"] for b in boxes)
    bottom = max(b["y"] + b["h"] for b in boxes)
    return {"x": left, "y": top, "w": right - left, "h": bottom - top}


def _pane_els(pattern=None, role=None, snapshot=None):
    """Elements inside the Media Dock surface, found by its own controls.

    Pass `snapshot` when several readings must come from ONE instant: separate
    snapshots straddle a re-render and a pair of them can disagree.
    """
    d = snapshot or state()
    box = _pane_box(d)
    if not box:
        # No dock on screen: an empty answer, never a sweep of the chat that happens to
        # sit to the right of the dock's usual position.
        return []
    out = []
    for e in d.get("elements") or []:
        f = e.get("frame") or {}
        if f.get("x") is None:
            continue
        inside = box and (box["x"] - 14 <= f["x"] <= box["x"] + box["w"] + 14
                          and box["y"] - 300 <= f["y"] <= box["y"] + box["h"] + 14)
        if not inside and f["x"] < PANES_MIN_X:
            continue
        if role and str(e.get("role")) != role:
            continue
        lab = str(e.get("label") or "")
        if pattern and pattern.lower() not in lab.lower():
            continue
        out.append(e)
    return out


def _queue_rows():
    """Queue rows in visual order. Each row is one tab whose name joins its own controls."""
    rows = [e for e in _pane_els("Move earlier", "TabItem")]
    rows.sort(key=lambda e: (e.get("frame") or {}).get("y") or 0)
    return [(str(r.get("label") or "").split(" Move earlier")[0].strip(), r) for r in rows]


FIXTURE_PORT = 8771
FIXTURE_BASE = "http://127.0.0.1:%d" % FIXTURE_PORT


def ensure_fixtures():
    """Serve tests/fixtures on 8771 if nothing already answers there.

    Started with CREATE_NO_WINDOW: a test must never pop a console onto the user's
    desktop. The process is left running; it is idempotent and harmless.
    """
    import urllib.request
    try:
        urllib.request.urlopen(FIXTURE_BASE + "/page.html", timeout=1)
        return {"serving": True, "started": False}
    except Exception:
        pass
    here = os.path.dirname(os.path.abspath(__file__))
    serve = os.path.join(here, "fixtures", "serve.py")
    kw = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if os.name == "nt":
        kw["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
    subprocess.Popen([sys.executable, serve, str(FIXTURE_PORT)], **kw)
    for _ in range(20):
        time.sleep(0.25)
        try:
            urllib.request.urlopen(FIXTURE_BASE + "/page.html", timeout=1)
            return {"serving": True, "started": True}
        except Exception:
            continue
    raise SystemExit("fixture server did not come up on %d" % FIXTURE_PORT)


def wait_for(fn, timeout=8.0, step=0.5):
    """Poll a predicate that reads FRESH snapshots until it holds or the deadline passes.

    One snapshot per decision: pairs of `_pane_els` calls read at different instants, so a
    label that flips a beat after a click made an atomic-looking assertion lie.
    """
    end = time.time() + timeout
    val = fn()
    while not val and time.time() < end:
        time.sleep(step)
        val = fn()
    return val


def _queued_count():
    """The header's own 'N queued' text is the row count the user reads."""
    for e in _pane_els():
        m = re.match(r"^(\d+) queued$", str(e.get("label") or "").strip())
        if m:
            return int(m.group(1))
    return 0


def _url_value():
    e = next((x for x in _pane_els(role="Edit") if str(x.get("label")) == "URL"), None)
    return str((e or {}).get("value") or "")


def _row_buttons(pattern, y):
    return [e for e in _pane_els(pattern, "Button")
            if abs(((e.get("frame") or {}).get("y") or 0) - y) < 12]


def pane_state():
    """Everything the queue assertions need, read from one UIA snapshot."""
    d = state()
    els = _pane_els(snapshot=d)
    labels = [str(e.get("label") or "") for e in els]
    m = next((re.match(r"^(\d+) queued$", s.strip()) for s in labels if re.match(r"^\d+ queued$", s.strip())), None)
    rows = [e for e in _pane_els("Move earlier", "TabItem", snapshot=d)]
    rows.sort(key=lambda e: (e.get("frame") or {}).get("y") or 0)
    field = next((e for e in els if str(e.get("role")) == "Edit" and str(e.get("label")) == "URL"), None)
    return {
        "count": int(m.group(1)) if m else 0,
        "add": any(l.strip() == "Add current" for l in labels),
        "in_queue": any(l.strip() == "In queue" for l in labels),
        "next": any(l.strip() == "Next in queue" for l in labels),
        "prev": any(l.strip() == "Previous in queue" for l in labels),
        "empty_hint": any("Queue is empty" in l for l in labels),
        "rows": rows,
        "url": str((field or {}).get("value") or ""),
    }


def queue_test(base="http://127.0.0.1:8771/page.html", cap=False):
    """Prove the queue the way a user drives it, and assert every step.

    Each check names a behaviour a person can see (the header count, the Add/In-queue
    label, prepend order, row open, Next/Previous, reorder, remove, clear, the cap,
    and surviving a close/reopen). A step waits for the state it expects instead of
    sleeping a fixed time: a 0.8 s sleep after a page load was a coin flip.
    """
    a_url, b_url = base + "?q=a", base + "?q=b"
    ensure_fixtures()
    checks = []

    def check(name, cond, detail=""):
        checks.append({"check": name, "ok": bool(cond), "detail": detail})
        print(json.dumps({"check": name, "ok": bool(cond), "detail": detail}), flush=True)
        return bool(cond)

    def until(pred, timeout=8.0):
        """Fresh pane_state() per poll; returns the winning state or the last one read.

        A snapshot costs ~5 s here, so the poll step is 1.2 s: polling faster only
        bought snapshots, not responsiveness.
        """
        end = time.time() + timeout
        st = pane_state()
        while not pred(st) and time.time() < end:
            time.sleep(1.2)
            st = pane_state()
        return st

    def row_buttons(pattern, y):
        return _row_buttons(pattern, y)

    ensure_pane()
    focus()
    if not ensure_url_field():
        raise SystemExit("queue: no address bar on any placement")

    # 1. A clean queue: the empty state, Add current, no dead Next/Previous pair.
    if pane_state()["count"]:
        click_label("Clear", "Button")
        until(lambda s: s["count"] == 0)
    st = pane_state()
    check("empty queue says so", st["empty_hint"])
    check("empty queue offers Add current", st["add"])
    check("empty queue hides Next/Previous", not st["next"] and not st["prev"])

    # 2. Add current parks the loaded page and flips its own label to In queue.
    nav(a_url, wait=2.4)
    click_label("Add current", "Button")
    st = until(lambda s: s["count"] == 1 and s["in_queue"])
    check("add parks one row", st["count"] == 1, "count %s" % st["count"])
    check("label flips to In queue", st["in_queue"] and not st["add"])
    check("transport grows Next/Previous once queued", st["next"] and st["prev"])

    # 3. Re-adding the same URL replaces, never duplicates.
    click_label("In queue", "Button")
    time.sleep(0.9)
    st = pane_state()
    check("re-adding the same URL stays one row", st["count"] == 1, "count %s" % st["count"])

    # 4. A second URL prepends: the newest is the first row.
    nav(b_url, wait=2.4)
    click_label("Add current", "Button")
    st = until(lambda s: s["count"] == 2)
    check("second add makes two rows", st["count"] == 2, "count %s" % st["count"])
    if check("two rows are visible", len(st["rows"]) == 2, "%d tabs" % len(st["rows"])):
        click_token(st["rows"][0])
        st = until(lambda s: s["url"].rstrip("/") == b_url, timeout=6)
        check("top row is the newest add", st["url"].rstrip("/") == b_url, st["url"])

    # 5. Next/Previous walk the list in order.
    click_label("Next in queue", "Button")
    st = until(lambda s: s["url"].rstrip("/") == a_url, timeout=6)
    check("next opens the following row", st["url"].rstrip("/") == a_url, st["url"])
    click_label("Previous in queue", "Button")
    st = until(lambda s: s["url"].rstrip("/") == b_url, timeout=6)
    check("previous comes back", st["url"].rstrip("/") == b_url, st["url"])

    # 6. Reorder moves a row in the list the user sees, not just in state.
    st = pane_state()
    if len(st["rows"]) == 2:
        top_y = (st["rows"][0].get("frame") or {}).get("y") or 0
        laters = row_buttons("Move later", top_y)
        if check("top row has a move-later control", bool(laters)):
            click_token(laters[0])
            time.sleep(0.9)
            st2 = pane_state()
            click_token(st2["rows"][0])
            st3 = until(lambda s: s["url"].rstrip("/") == a_url, timeout=6)
            check("move later reorders the visible list", st3["url"].rstrip("/") == a_url, st3["url"])

    # 6.5 Shuffle must move what the user sees. Two rows make the case that used to fail:
    # a permutation can land on the same order, and the button then looks dead.
    st = pane_state()
    if len(st["rows"]) == 2:
        before = st["url"].rstrip("/")
        click_label("Shuffle", "Button")
        time.sleep(0.9)
        st2 = pane_state()
        click_token(st2["rows"][0])
        st3 = until(lambda s: s["url"].rstrip("/") != before, timeout=6)
        check("shuffle moves the top row", st3["url"].rstrip("/") != before, st3["url"])

    # 7. Remove drops exactly one row; Clear empties and restores Add current.
    st = pane_state()
    if st["rows"]:
        y = (st["rows"][0].get("frame") or {}).get("y") or 0
        xs = row_buttons("Remove", y)
        if check("row has a remove control", bool(xs)):
            click_token(xs[0])
            st = until(lambda s: s["count"] == 1)
            check("remove drops one row", st["count"] == 1, "count %s" % st["count"])
    click_label("Clear", "Button")
    st = until(lambda s: s["count"] == 0)
    check("clear empties the queue", st["count"] == 0, "count %s" % st["count"])
    check("clear restores Add current", st["add"] and not st["in_queue"])

    # 8. The cap: 13 distinct URLs leave 12 rows.
    if cap:
        added = 0
        for i in range(13):
            for attempt in range(2):
                try:
                    nav("%s?n=%d" % (base, i + 1), wait=1.9, verify=False)
                    d = state()  # the header re-renders per add: refresh the tokens
                    add = find(d, "Add current", "Button") or find(d, "In queue", "Button")
                    if add:
                        press(d, add)
                        added += 1
                    break
                except SystemExit as exc:
                    print(json.dumps({"nav_retry": str(exc)[:120]}), flush=True)
                    time.sleep(0.6)
            time.sleep(0.4)
        st = until(lambda s: s["count"] >= 12, timeout=10)
        check("queue caps at 12", st["count"] == 12, "count %s after %d adds" % (st["count"], added))
        click_label("Clear", "Button")
        until(lambda s: s["count"] == 0)

    # 9. Closing and reopening the pane keeps the rows.
    nav(a_url, wait=2.4)
    click_label("Add current", "Button")
    until(lambda s: s["count"] == 1)
    click_label("Close", "Button", pane=True)
    time.sleep(1.5)
    ensure_pane()
    st = until(lambda s: s["count"] == 1, timeout=8)
    check("reopening the pane keeps the queue", st["count"] == 1, "count %s" % st["count"])
    if st["count"]:
        click_label("Clear", "Button")
        time.sleep(0.6)

    failed = [c for c in checks if not c["ok"]]
    for f in failed:
        print("FAILED: %s (%s)" % (f["check"], f["detail"]), flush=True)
    return {"checks": checks, "ok": not failed, "failed": len(failed)}


def rail_counts():
    """How many transport rails the pane shows, by their own seek labels.

    `Seek` is the rail for a file we own; `Seek page media` is the rail for the guest's
    player. Both on screen means a stale rail survived a source switch.
    """
    labs = [str(e.get("label") or "") for e in _pane_els() if str(e.get("role")) in ("Slider", "Button")]
    return {"native": sum(1 for l in labs if l == "Seek"),
            "page": sum(1 for l in labs if l == "Seek page media"),
            "page_play": sum(1 for l in labs if l == "Play/Pause page media")}


def rails_test(base=None):
    """Switching source must leave exactly ONE transport rail on the stage.

    A page keeps its player while a guest is mounted; switching to a file we own used to
    leave the page's rail (and its dead Play/Seek buttons) under the file's own rail.
    """
    base = (base or FIXTURE_BASE).rstrip("/")
    ensure_fixtures()
    checks = []

    def check(name, cond, detail=""):
        checks.append({"check": name, "ok": bool(cond), "detail": detail})
        print(json.dumps({"check": name, "ok": bool(cond), "detail": detail}), flush=True)
        return bool(cond)

    ensure_pane()
    ensure_url_field()
    nav(base + "/page.html?q=rail", wait=3.5)
    r = rail_counts()
    check("a page with media shows its own rail", r["page"] == 1 and r["native"] == 0, json.dumps(r))

    nav(base + "/tone.wav", wait=2.6)
    r = rail_counts()
    check("a file we own shows its own rail", r["native"] == 1, json.dumps(r))
    check("the page rail is gone after the switch", r["page"] == 0 and r["page_play"] == 0, json.dumps(r))

    failed = [c for c in checks if not c["ok"]]
    for f in failed:
        print("FAILED: %s (%s)" % (f["check"], f["detail"]), flush=True)
    return {"checks": checks, "ok": not failed, "failed": len(failed)}


def autoadvance_test(base=None):
    """A queued FILE that ends must move playback to the next queued item.

    Auto-advance is the one queue behaviour no gate can see: it needs a real element
    firing `ended`. The fixture's tone.wav is 8 s, so the file ends on its own.
    """
    base = (base or FIXTURE_BASE).rstrip("/")
    ensure_fixtures()
    checks = []

    def check(name, cond, detail=""):
        checks.append({"check": name, "ok": bool(cond), "detail": detail})
        print(json.dumps({"check": name, "ok": bool(cond), "detail": detail}), flush=True)
        return bool(cond)

    ensure_pane()
    ensure_url_field()
    st = pane_state()
    if st["count"]:
        click_label("Clear", "Button")
        time.sleep(1.0)

    page_url, tone_url = base + "/page.html?q=adv", base + "/tone.wav"
    nav(page_url, wait=2.4)
    click_label("Add current", "Button")
    time.sleep(0.8)
    nav(tone_url, wait=2.4)
    click_label("Add current", "Button")
    st = pane_state()
    check("both items are queued", st["count"] == 2, "count %s" % st["count"])

    if st["rows"]:
        click_token_real(st["rows"][0])   # tone.wav, newest at the top; a real gesture plays
        time.sleep(3.0)
        st = pane_state()
        check("the queued file is on the stage", st["url"].endswith("/tone.wav"), st["url"])
        t0 = time_text()
        check("a native player owns it", bool(t0), "no time readout")
        # A row click promises to start the file, not just load it. Chromium can refuse
        # an unmuted play() with no live gesture, so this is the muted-fallback contract.
        t1 = time_text()
        check("a clicked queue row starts playing", bool(t0 and t1 and t0 != t1),
              "readout %s -> %s" % (t0, t1))
        moved = until_url_change(tone_url, timeout=22)
        check("a finished file advances to the next item", moved.rstrip("/") == page_url.rstrip("/"),
              moved or "still on the file")
        click_label("Clear", "Button")
        time.sleep(0.8)
    failed = [c for c in checks if not c["ok"]]
    for f in failed:
        print("FAILED: %s (%s)" % (f["check"], f["detail"]), flush=True)
    return {"checks": checks, "ok": not failed, "failed": len(failed)}


def until_url_change(prev, timeout=20.0):
    """Poll until the live URL field stops naming `prev`; returns the new URL or ''."""
    prev = prev.rstrip("/")
    end = time.time() + timeout
    while True:
        st = pane_state()
        got = st["url"].rstrip("/")
        if got and got != prev:
            return st["url"]
        if time.time() > end:
            return ""
        time.sleep(1.2)


def palette_open(d=None):
    d = d or state()
    return any(str(e.get("label", "")) == "Command palette" for e in d.get("elements") or [])


def palette(text, wait=1.5):
    """Open the palette, type, run — refusing rather than typing blind.

    Ctrl+K is a chord the driver can drop, and `type_text` then lands in whatever
    holds focus: the chat composer. The trailing Enter would send that text to the
    focused session as a message and interrupt streaming work. So the palette is
    proven on screen before a single character is typed; if it never appears, this
    returns a refusal and nothing is typed.
    """
    key("ctrl", "k")
    time.sleep(1.0)
    if not palette_open():
        return {"ran": None, "why": "palette did not open — refused, nothing typed"}
    type_text(text)
    time.sleep(1.0)
    if palette_open():
        hit = find(state(), text, "ListItem") or find(state(), text)
        if not hit:
            key("Escape")  # palette is open, so this dismisses it — it cannot reach the composer
            return {"ran": None, "why": "no matching row — palette dismissed"}
    key("Enter")
    time.sleep(wait)
    return {"ran": text, "open": palette_open()}


def labels(pattern=""):
    d = state()
    out = []
    for e in d["elements"]:
        lab = str(e.get("label", ""))
        if pattern and pattern.lower() not in lab.lower():
            continue
        v = e.get("value")
        out.append({"role": e.get("role"), "label": lab[:90], "value": None if v is None else str(v)[:50],
                    "disabled": e.get("disabled")})
    return out[:40]


def theater_test(base="http://127.0.0.1:8771/page.html"):
    """Theater in and out from the placement the pane is in: overlay, then the exact place.

    The gate proves the arithmetic; this proves the host honours a `fixed` surface and that
    the borrowed inline style comes back. Docked and floating take different paths, so the
    case is read from the footer rather than assumed.
    """
    ON, OFF = "Grow the player to almost fill the window", "Return the player to its dock"
    checks, failed = [], []

    def check(name, cond, detail=""):
        checks.append({"name": name, "ok": bool(cond), "detail": detail})
        if not cond:
            failed.append(name)

    ensure_fixtures()
    d = ensure_pane()
    ensure_url_field()
    if not find(d, ON, "Button") and by_label("URL", "Edit")[1]:
        nav(base)
    d = state()
    on = find(d, ON, "Button")
    if not on:
        raise SystemExit("theater: no Theater button on screen (load a media URL first)")
    win = d.get("_window") or {}
    before, was_docked = _pane_box(d), bool(find(d, "Detach", "Button"))
    click_token(on)
    time.sleep(2.6)
    d2 = state()
    after, off = _pane_box(d2), find(d2, OFF, "Button")
    left, width = (win.get("x") or 0) + 24, (win.get("width") or 0) - 48
    check("theater spans the window", after and abs(after["x"] - left) <= 8 and abs(after["w"] - width) <= 8,
          "%s vs left=%s w=%s" % (after, left, width))
    check("exit control offered", bool(off))
    if off:
        try:
            click_token(off)
        except SystemExit as err:
            # A re-render can invalidate the token after the click already landed; the state
            # checks below decide whether the exit happened.
            if "vanished" not in str(err):
                raise
        time.sleep(2.6)
        d3 = state()
        back = _pane_box(d3)
        check("exit restores the place", back and before and abs(back["x"] - before["x"]) <= 8 and abs(back["w"] - before["w"]) <= 8,
              "%s -> %s" % (before, back))
        check("placement restored", bool(find(d3, "Detach" if was_docked else "Dock", "Button")))
        check("media survives theater", bool(find(d3, ON, "Button")))
    return {"ok": not failed, "failed": failed, "checks": checks}


def main(argv):
    if not argv:
        raise SystemExit(__doc__)
    cmd = argv[0]
    if cmd == "where":
        w = window()
        d = state()
        print(json.dumps({
            "pid": w["pid"], "window_id": w["window_id"],
            "png": [d.get("screenshot_width"), d.get("screenshot_height")],
            "elements": len(d.get("elements") or []),
        }))
    elif cmd == "shot":
        print(json.dumps(shot(argv[1] if len(argv) > 1 else "shot.png")))
    elif cmd == "click":
        print(json.dumps(click_xy(argv[1], argv[2])))
        time.sleep(0.4)
    elif cmd == "click-label":
        print(json.dumps(click_label(argv[1])))
        time.sleep(0.4)
    elif cmd == "type":
        print(json.dumps(type_text(argv[1])))
    elif cmd == "key":
        print(json.dumps(key(argv[1])))
    elif cmd == "labels":
        print(json.dumps(labels(argv[1] if len(argv) > 1 else ""), indent=1))
    elif cmd == "nav":
        print(json.dumps(nav(argv[1])))
    elif cmd == "rails":
        base = next((a for a in argv[1:] if not a.startswith("--")), None)
        r = rails_test(base)
        print(json.dumps({"ok": r["ok"], "failed": r["failed"], "checks": len(r["checks"])}))
        if not r["ok"]:
            raise SystemExit(2)
    elif cmd == "autoadvance":
        base = next((a for a in argv[1:] if not a.startswith("--")), None)
        r = autoadvance_test(base)
        print(json.dumps({"ok": r["ok"], "failed": r["failed"], "checks": len(r["checks"])}))
        if not r["ok"]:
            raise SystemExit(2)
    elif cmd == "queue":
        rest = [a for a in argv[1:] if not a.startswith("--")]
        r = queue_test(rest[0] if rest else "http://127.0.0.1:8771/page.html", cap="--cap" in argv)
        print(json.dumps({"ok": r["ok"], "failed": r["failed"], "checks": len(r["checks"])}))
        if not r["ok"]:
            raise SystemExit(2)
    elif cmd == "theater":
        base = next((a for a in argv[1:] if not a.startswith("--")), None)
        r = theater_test(base) if base else theater_test()
        print(json.dumps({"ok": r["ok"], "failed": r["failed"], "checks": len(r["checks"])}))
        if not r["ok"]:
            raise SystemExit(2)
    elif cmd == "palette":
        print(json.dumps(palette(argv[1])))
    elif cmd == "resume":
        secs = float(argv[2]) if len(argv) > 2 else 8.0
        print(json.dumps(resume_test(argv[1], secs)))
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
