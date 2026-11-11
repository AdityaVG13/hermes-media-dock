"""Parse desktop/plugin.js as an ES module. `node --check` is not a parse gate."""
import pathlib
import shutil
import subprocess
import sys

_PROBE = (
    "const vm=require('vm'),fs=require('fs');"
    "const src=fs.readFileSync(process.argv[1],'utf8');"
    "try{new vm.SourceTextModule(src);console.log('OK')}"
    "catch(e){console.log('ERR '+e.message)}"
)


def parse_error(path, node=None):
    node = node or shutil.which("node")
    if not node:
        return "node not found (cannot parse-check)"
    try:
        r = subprocess.run(
            [node, "--experimental-vm-modules", "--no-warnings", "-e", _PROBE, str(path)],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        return "parse timed out"
    out = (r.stdout or r.stderr or "").strip()
    if out.startswith("OK"):
        return ""
    return (out[:300] or "no output from the parser").replace("ERR ", "", 1)


def check_js(root, node=None):
    root = pathlib.Path(root)
    files = [root] if root.is_file() else sorted(root.rglob("*.js"))
    return [(f, err) for f in files if (err := parse_error(f, node))]


def main(argv):
    if len(argv) < 2:
        print("usage: python tests/jscheck.py <file-or-dir>")
        return 2
    bad = []
    for a in argv[1:]:
        bad.extend(check_js(a))
    if not bad:
        print("OK")
        return 0
    for f, err in bad:
        print(f"PARSE ERROR {f}: {err}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
