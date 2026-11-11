"""End-to-end proof for level boost and captions, driven through the real pane.

The fixture page carries a steady sine and a real WebVTT track, and reports
`gain`, the measured RMS of the signal leaving the gain node, and the cue the page agent reads
inside document.title — so the dock's own title row carries the measurement out
to UIA. Evidence is a JSON transcript plus a screenshot.

    python tests/fixtures/serve.py 8771     (started here if absent)
    python tests/e2e_volume_captions.py

The graph comparison is 200% against 100% on the SAME graph: Web Audio can route an
element only once, so the honest proof is rms(gain 2.0) / rms(gain 1.0) ~= 2.
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

import live

PORT = 8771
PAGE = "http://127.0.0.1:%d/page.html" % PORT


def server_up():
    try:
        with urllib.request.urlopen("http://127.0.0.1:%d/page.html" % PORT, timeout=1) as r:
            return r.status == 200
    except Exception:
        return False


def start_server():
    if server_up():
        return "already up"
    subprocess.Popen([sys.executable, os.path.join("tests", "fixtures", "serve.py"), str(PORT)],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(40):
        if server_up():
            return "started"
        time.sleep(0.25)
    raise SystemExit("fixture server never answered on %d" % PORT)


def probe_text():
    for e in live.state().get("elements") or []:
        lab = str(e.get("label") or "")
        m = re.search(r"gain=([\d.]+)\s+rms=([\d.]+)", lab)
        if not m:
            continue
        cue = re.search(r"cue=(.*?)\s+sel=", lab)
        sel = re.search(r"sel=(-?\d+)", lab)
        return {"raw": lab, "gain": float(m.group(1)), "rms": float(m.group(2)),
                "cue": (cue.group(1) if cue else ""), "sel": int(sel.group(1)) if sel else -1}
    return None


def settle(seconds=3.0):
    """The last probe sample, after the graph has had time to run."""
    time.sleep(seconds)
    return probe_text()


def volume_btn():
    for e in live.state().get("elements") or []:
        if str(e.get("role")) == "Button" and re.match(r"^Volume \d+ percent$", str(e.get("label") or "")):
            return e["label"]
    return None


def open_popover():
    """The volume popover stays open across clicks, so only open it when it is closed."""
    if not [x for x in live.labels("100%") if x.get("role") == "Button"]:
        lab = volume_btn()
        if not lab:
            raise SystemExit("no volume button — the page transport is not mounted")
        live.click_label(lab)
        time.sleep(0.7)


def main(argv):
    out = {"steps": []}
    out["server"] = start_server()
    live.ensure_pane()
    live.nav(PAGE, wait=7.0)
    time.sleep(1.5)
    out["mounted"] = {"volume": volume_btn(), "transport": [str(x.get("label")) for x in live.labels("page media")]}
    if out["mounted"]["volume"] is None:
        out["verdict"] = "transport not mounted"
        print(json.dumps(out, indent=1))
        return 1
    # Play through the dock's own control, so the element is running before we measure.
    if [e for e in live.labels("Play page media")]:
        live.click_label("Play page media")
    time.sleep(1.0)

    open_popover()
    out["popover"] = sorted({str(x.get("label")) for x in live.state().get("elements") or []
                             if str(x.get("role")) == "Button" and str(x.get("label")) in
                             ("100%", "200%", "Mute", "Reset")})
    live.click_label("200%")
    boosted = settle(3.0)
    out["boosted"] = boosted

    open_popover()
    live.click_label("100%")
    unity = settle(2.5)
    out["unity"] = unity
    ratio = (boosted["rms"] / unity["rms"]) if (boosted and unity and unity["rms"]) else 0.0
    out["ratio"] = round(ratio, 3)

    live.click_label("Captions")
    time.sleep(0.8)
    out["caption_popover"] = [str(x.get("label")) for x in live.state().get("elements") or []
                              if str(x.get("role")) == "Button"][:30]
    live.click_label("English")
    time.sleep(2.5)
    with_cue = probe_text()
    out["captioned"] = with_cue
    live.shot("C:/tmp/media-dock-boost.png")

    ok_boost = bool(boosted and unity and boosted["gain"] >= 1.9 and 1.7 <= ratio <= 2.3)
    ok_cap = bool(with_cue and with_cue["sel"] >= 0 and with_cue["cue"] not in ("", "-"))
    out["verdict"] = {"boost": "PASS" if ok_boost else "FAIL", "captions": "PASS" if ok_cap else "FAIL"}
    print(json.dumps(out, indent=1))
    return 0 if (ok_boost and ok_cap) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
