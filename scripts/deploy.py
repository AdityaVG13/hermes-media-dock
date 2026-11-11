"""Install media-dock into Hermes as junctions back to this repo.

Source of truth is the repo root (this script's parent). The live Hermes plugin dir
(and a `../hermes-plugins/media-dock` shortcut, when this clone sits inside a
collection) is a reparse point, so an edit here is what the app loads. `python scripts/deploy.py`
refreshes those links and the renderer stamp; it does not enable the plugin.
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import shutil
import stat
import subprocess
import sys
import time

PLUGIN = "media-dock"
SRC = pathlib.Path(__file__).resolve().parent.parent
def hermes_home() -> pathlib.Path:
    """Where the app keeps state. HERMES_HOME wins; otherwise the per-OS default."""
    env = os.environ.get("HERMES_HOME")
    if env:
        return pathlib.Path(env).expanduser()
    local = os.environ.get("LOCALAPPDATA")
    if local and (pathlib.Path(local) / "hermes").is_dir():
        return pathlib.Path(local) / "hermes"
    for cand in (
        pathlib.Path.home() / ".hermes",
        pathlib.Path.home() / "Library" / "Application Support" / "hermes",
        pathlib.Path.home() / ".config" / "hermes",
    ):
        if cand.is_dir():
            return cand
    return pathlib.Path.home() / ".hermes"


ABS = hermes_home()
INST = ABS / "plugins" / PLUGIN
PUB = ABS / "desktop-plugins" / PLUGIN
# Optional: a shortcut inside a hermes-plugins collection, only if this clone sits in one.
COLLECTION = SRC.parent / "hermes-plugins"
WORKSPACE_LINK = COLLECTION / PLUGIN if COLLECTION.is_dir() else None

sys.path.insert(0, str(SRC / "tests"))
import jscheck  # noqa: E402


def win(p: pathlib.Path) -> str:
    return str(p.resolve())


def is_reparse(p: pathlib.Path) -> bool:
    try:
        if p.is_symlink():
            return True
        if hasattr(p, "is_junction") and p.is_junction():
            return True
    except OSError:
        pass
    try:
        st = os.lstat(p)
        return bool(getattr(st, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT)
    except OSError:
        return False


def remove_reparse_only(p: pathlib.Path) -> None:
    """Drop a junction/symlink. Never follows into the target tree."""
    os.rmdir(p) if p.is_dir() else os.unlink(p)


def remove_copy_or_reparse(p: pathlib.Path) -> None:
    if not p.exists() and not is_reparse(p):
        return
    if is_reparse(p):
        remove_reparse_only(p)
        return
    if p.is_dir():
        shutil.rmtree(p)
        return
    p.unlink()


def points_at(link: pathlib.Path, target: pathlib.Path) -> bool:
    if not is_reparse(link):
        return False
    try:
        return link.resolve() == target.resolve()
    except OSError:
        return False


def mklink(kind: str, link: pathlib.Path, target: pathlib.Path) -> None:
    """Directory link: a junction on Windows (no admin needed), a symlink elsewhere."""
    link.parent.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        os.symlink(target, link, target_is_directory=True)
        return
    cmd = ["cmd.exe", "/c", "mklink"]
    if kind == "junction":
        cmd.append("/J")
    cmd.extend([win(link), win(target)])
    subprocess.check_call(cmd)


def ensure_junction(link: pathlib.Path, target: pathlib.Path) -> str:
    target = target.resolve()
    if points_at(link, target):
        return "kept"
    if link.exists() or is_reparse(link):
        remove_copy_or_reparse(link)
    mklink("junction", link, target)
    if not points_at(link, target):
        raise SystemExit(f"junction failed: {link} -> {target}")
    return "created"


def publish_renderer(link: pathlib.Path, target: pathlib.Path) -> str:
    """Host-owned copy. A file symlink here gets replaced the next time Hermes
    republishes the renderer; do not fight it."""
    target = target.resolve()
    link.parent.mkdir(parents=True, exist_ok=True)
    if is_reparse(link):
        remove_reparse_only(link)
    if link.exists() and sha(link) == sha(target):
        return "kept"
    shutil.copy2(target, link)
    return "copied"


def sha(p: pathlib.Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


bad = jscheck.check_js(SRC / "desktop")
if bad:
    for f, err in bad:
        print(f"  PARSE ERROR {f.name}: {err}")
    raise SystemExit("deploy aborted: the renderer half does not parse")

ws = ensure_junction(WORKSPACE_LINK, SRC) if WORKSPACE_LINK else "skipped"
inst = ensure_junction(INST, SRC)
print(f"workspace {ws}: {WORKSPACE_LINK or 'no hermes-plugins collection beside this clone'}")
print(f"installed {inst}: {INST}")

PUB.mkdir(parents=True, exist_ok=True)
pub = publish_renderer(PUB / "plugin.js", SRC / "desktop" / "plugin.js")
print(f"published {pub}: {PUB / 'plugin.js'}")
pkg = PUB / ".hermes-package.json"
meta = json.loads(pkg.read_text(encoding="utf-8")) if pkg.exists() else {}
meta["package"] = PLUGIN
meta["source"] = win(SRC / "desktop")
meta["sourceMtimeMs"] = (SRC / "desktop" / "plugin.js").stat().st_mtime * 1000.0
pkg.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
print("sourceMtimeMs =", int(meta["sourceMtimeMs"]))

ha, hb, hc = (
    sha(SRC / "desktop" / "plugin.js"),
    sha(INST / "desktop" / "plugin.js"),
    sha(PUB / "plugin.js"),
)
ok = ha == hb == hc
print(f"\nsha256 plugin.js  {ha[:16]}  {hb[:16]}  {hc[:16]}  {'OK' if ok else 'MISMATCH'}")
print(f"linked at {time.strftime('%H:%M:%S')}")
print("Edits in this repo are the live bytes. Enable in Capabilities -> Plugins -> Media Dock.")
raise SystemExit(0 if ok else 1)

