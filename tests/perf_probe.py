#!/usr/bin/env python3
"""One reproducible perf probe for media-dock's plugin-side hot paths.

Reuses render_gate's stub SDK so `desktop/plugin.js` loads exactly as it does in
the behavior gate. Measures plugin-side CPU only: this is a stubbed Node host, NOT
the Electron renderer, so numbers are comparable ACROSS RUNS here but are not
end-to-end app latency.

    python tests/perf_probe.py                 # 25 runs + CPU profile
    python tests/perf_probe.py --runs 25 --iter 3000
    python tests/perf_probe.py --no-profile   # metrics only

Artifacts: tests/artifacts/perf/<run-id>/{fingerprint.json,baseline.json,
           hotspots.md,<pid>.cpuprofile}
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import platform
import shutil
import statistics
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import render_gate as rg  # noqa: E402  (reuse WORK, SDK/REACT stubs, build())

BENCH = r"""
import { performance } from 'node:perf_hooks'
import { createHash } from 'node:crypto'
import { host } from '@hermes/plugin-sdk'
import { RENDERED } from 'react'

globalThis.addEventListener = () => {}
globalThis.ResizeObserver = class { observe() {} disconnect() {} }
globalThis.innerWidth = 1600
globalThis.innerHeight = 900

// The generated pair is named per run: this work dir is shared with the behavior gate and
// with any other probe, and a fixed filename let one run execute another run's bytes.
const MODULE = process.env.BENCH_MODULE || './under-test.mjs'
const mod = await import(MODULE)
const ITER = Number(process.env.BENCH_ITER || 3000)
const PROFILE = process.env.BENCH_PROFILE === '1'

const URLS = [
  'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
  'https://youtu.be/9bZkp7q19f0',
  'https://www.twitch.tv/somechannel',
  'https://cdn.example.com/flower.mp4',
  'https://example.com/some/page?q=1#frag',
  'https://stream.example.com/live/playlist.m3u8',
  'youtube.com',
  'not a url',
  'ftp://files.example.com/x',
  'https://localhost:8080/ui',
  'https://cdn.example.com/a.MP4?token=abc',
  '//cdn.example.com/b.webm',
  'https://example.com/path/file.name.with.dots.mp3',
  'https://sub.domain.example.co.uk/watch/12345',
  'https://example.com/stream.mpd',
  '',
  '   https://example.com/  ',
  'javascript:alert(1)',
  'https://example.com/%20encoded%20path',
  'https://192.168.1.50:8443/camera',
]

function makeCtx(store) {
  const registered = [], listeners = [], disposers = []
  const storage = new Map(Object.entries(store || {}))
  const ctx = {
    register: (d) => { registered.push(d); return () => {} },
    registerMany: (ds) => { for (const d of ds) registered.push(d); return () => {} },
    registerSettingsPage: (d) => { registered.push({ __settings: true, ...d }); return () => {} },
    rest: async () => ({}), socket: () => () => {}, setTimeout: () => () => {}, setInterval: () => () => {},
    addEventListener: (t, type, fn) => { listeners.push({ type, fn }); return () => {} },
    onEvent: () => () => {}, onDispose: (fn) => disposers.push(fn),
    runAction: () => ({ ok: true }), listActions: () => [],
    storage: {
      get: (k, d) => (storage.has(k) ? storage.get(k) : d),
      set: (k, v) => { storage.set(k, v) },
      remove: (k) => { storage.delete(k) },
    },
    os: { openExternal: () => Promise.resolve(true), writeClipboard: () => Promise.resolve(true) },
    preview: { isAvailable: () => false, executeJavaScript: async () => null },
    i18n: { t: (s) => s },
  }
  return { ctx, registered, disposers }
}

function walk(n, fn) {
  if (!n || typeof n !== 'object') return
  fn(n)
  const c = n.props && n.props.children
  if (Array.isArray(c)) { for (const x of c) walk(x, fn) }
  else if (c && typeof c === 'object') walk(c, fn)
}

const { ctx, registered, disposers } = makeCtx({
  settings: { autoTheater: true, theaterScope: 'any', theaterPersist: 'agent' },
  session: { raw: URLS[3], floating: true },
})
mod.default.register(ctx)
const pane = registered.find((d) => d.area === 'panes' && typeof d.render === 'function')

// The dock's COMMON state is a page, not a file: a second registration whose session is a
// site. Same module, same atoms — only the pane's own tree differs (address bar + guest +
// page transport). Rendering the native tree alone left the page tree unmeasured.
// A second MODULE INSTANCE: the atoms are module state, so one instance cannot hold a
// native session and a page session at the same time.
const modPage = await import(MODULE + '?page')
const pageCtx = makeCtx({ settings: { autoTheater: false }, session: { raw: URLS[0], floating: false } })
modPage.default.register(pageCtx.ctx)
const panePage = pageCtx.registered.find((d) => d.area === 'panes' && typeof d.render === 'function')
const fakeFrame = {
  style: {},
  closest: () => fakeFrame,
  getBoundingClientRect: () => ({ width: 480, height: 460, left: 0, top: 0, right: 480, bottom: 460 }),
}
const tree0 = pane.render()
walk(tree0, (n) => { if (n.props && typeof n.props.ref === 'function') n.props.ref(fakeFrame) })

const VP = { width: 1600, height: 900, narrow: false }
const CFG = mod.THEATER_CFG
const S = { supported: true, enabled: true, hasMedia: true, floating: true, busy: true, viewport: VP, persist: 'agent' }
const PARTIAL = { ...mod.SETTINGS_DEFAULTS, autoTheater: true, theaterScope: 'any' }
const QUEUE = Array.from({ length: 12 }, (_, i) => ({ url: 'https://example.com/v/' + i }))
// The ledger's own invariant: count DESC. An ascending fixture put every call on the
// unordered fallback and hid the ordering the production path actually gets.
const VISITS = Array.from({ length: 24 }, (_, i) => ({
  host: 'h' + i + '.example.com', url: 'https://h' + i + '.example.com/p',
  title: 't' + i, count: 24 - i, lastAt: 0,
}))
const VISITS_TOP = VISITS.map((r, i) => ({ ...r, count: 30 - i }))
const SESSIONS = Object.fromEntries(Array.from({ length: 12 }, (_, i) => ['s' + i, i % 3 === 0]))
const PAGE_RAW = { has: true, paused: true, t: 42.5, d: 300, v: 80, muted: false, r: 1, boost: false, can: true, why: '', sel: -1, trk: 0, cue: '', lang: '' }
// A production atom notifies its subscriber, and the subscriber is the pane render.
// Without that listener this workload would measure an object assignment, not a tick.
const mediaAtom = {
  v: null, subs: new Set(),
  get() { return this.v },
  set(x) { this.v = x; for (const f of this.subs) f(x) },
  subscribe(f) { this.subs.add(f); return () => this.subs.delete(f) },
}

// The subscriber is the pane render: this is what a tick actually costs in the host.
mediaAtom.subscribe(() => { pane.render() })

const W = {
  parse: (i) => mod.parseMediaUrl(URLS[i % URLS.length]),
  bumpVisit: (i) => mod.bumpVisit(VISITS, URLS[i % URLS.length], 24),
  // The production common case: the same site pasted again while its row already leads.
  bumpTop: () => mod.bumpVisit(VISITS_TOP, 'https://h0.example.com/p', 24),
  // Mirrors applyParsed(): parse once for play.set, then bump visits with that
  // same parsed result. On the baseline the 4th arg is ignored and bumpVisit
  // re-parses internally; pass 2 eliminates that second parse.
  visitReal: (i) => {
    const u = URLS[i % URLS.length]
    const pp = mod.parseMediaUrl(u)
    return mod.bumpVisit(VISITS, pp.pageUrl || u, 24, pp)
  },
  settings: () => mod.settingsWithDefaults(PARTIAL),
  queue: (i) => mod.nextInQueue(QUEUE, QUEUE[i % QUEUE.length].url, true),
  // Native playback reports the same second up to four times; only the first writes.
  remember: () => mod.remember('https://example.com/some/page?q=1#frag', 42.5, 300),
  layout: (i) => mod.chromeFor(false, mod.layoutFor(300 + (i % 900), 'auto')),
  theater: (i) => {
    const st = { ...S, busy: !!(i % 2) }
    const p = mod.theaterPlan(null, st)
    return mod.theaterPlan(p, { ...st, busy: false })
  },
  render: () => pane.render(),
  renderPage: () => panePage.render(),
  // Mirrors readGuest(): the guest answers a half-second poll with the same numbers while
  // the page sits paused. Baseline had no guard, so `same` is a false-predicate there and
  // every tick published a fresh object.
  poll: () => {
    const s = mod.pageMediaState(PAGE_RAW)
    if (!(mod.samePageMedia || (() => false))(mediaAtom.get(), s)) mediaAtom.set(s)
  },
  tick: (i) => {
    host.state.busy.set(!!(i % 2))
    host.state.viewport.set({ width: 1500 + (i % 200), height: 900, narrow: false })
    host.state.busyBySession.set(SESSIONS)
  },
}
function mixed(i) {
  mod.parseMediaUrl(URLS[i % URLS.length])
  mod.bumpVisit(VISITS, URLS[(i + 3) % URLS.length], 24)
  mod.settingsWithDefaults(PARTIAL)
  mod.nextInQueue(QUEUE, QUEUE[i % QUEUE.length].url, true)
  mod.chromeFor(false, mod.layoutFor(300 + (i % 900), 'auto'))
  mod.theaterPlan(null, { ...S, busy: !!(i % 2) })
  pane.render()
  const ps = mod.pageMediaState(PAGE_RAW); if (!(mod.samePageMedia || (() => false))(mediaAtom.get(), ps)) mediaAtom.set(ps)
  host.state.busy.set(!!(i % 2))
  host.state.viewport.set({ width: 1500 + (i % 200), height: 900, narrow: false })
  host.state.busyBySession.set(SESSIONS)
}

function bench(name, fn, iters) {
  for (let i = 0; i < 200; i++) fn(i)          // warm: JIT is not the hotspot
  const t0 = performance.now()
  for (let i = 0; i < iters; i++) fn(i)
  const t1 = performance.now()
  return { name, ms: +(t1 - t0).toFixed(3), iters, nsPerOp: +((t1 - t0) * 1e6 / iters).toFixed(1) }
}

// Deterministic behavior fingerprint. Byte-identical across every optimization pass
// is the isomorphism proof; a change here means behavior changed, not just speed.
function golden() {
  const out = []
  for (const u of URLS) out.push('parse|' + u + '|' + JSON.stringify(mod.parseMediaUrl(u)))
  for (const u of URLS) out.push('classify|' + u + '|' + JSON.stringify(mod.classifyMedia(u)))
  for (const u of URLS) out.push('bump|' + u + '|' + JSON.stringify(mod.bumpVisit(VISITS, u, 24)))
  for (const q of ['', 'ex', 'youtube', 'zzz', '.example']) out.push('suggest|' + q + '|' + JSON.stringify(mod.suggestVisits(VISITS, q, 6)))
  out.push('settings|' + JSON.stringify(mod.settingsWithDefaults(PARTIAL)))
  out.push('settingsEmpty|' + JSON.stringify(mod.settingsWithDefaults({})))
  out.push('settingsBad|' + JSON.stringify(mod.settingsWithDefaults({ theaterPersist: 'bogus', rate: 99, volume: -4 })))
  out.push('queue|' + JSON.stringify(mod.nextInQueue(QUEUE, QUEUE[3].url, true)))
  out.push('queueWrap|' + JSON.stringify(mod.nextInQueue(QUEUE, QUEUE[11].url, true)))
  out.push('queueNoWrap|' + JSON.stringify(mod.nextInQueue(QUEUE, QUEUE[11].url, false)))
  out.push('layout|' + JSON.stringify(mod.layoutFor(640, 'auto')))
  out.push('chrome|' + JSON.stringify(mod.chromeFor(false, mod.layoutFor(300, 'auto'))))
  out.push('theater|' + JSON.stringify(mod.theaterPlan(null, S)))
  out.push('theaterIdle|' + JSON.stringify(mod.theaterPlan(mod.theaterPlan(null, S), { ...S, busy: false })))
  out.push('theaterWindow|' + JSON.stringify(mod.theaterPlan(mod.theaterPlan(null, { ...S, persist: 'window' }), { ...S, persist: 'window', busy: false })))
  // Theater is an inline-style overlay now: there is no computed theater rect. The
  // geometry that IS still pure is the card ladder and the drag clamp.
  out.push('sizeClamp|' + JSON.stringify(mod.clampSize(640, 520, 400, 300)))
  out.push('ladder|' + JSON.stringify(mod.nextLadder(1024, 720)) + '|' + JSON.stringify(mod.nextLadder(500, 500)))
  out.push('sizeAt|' + JSON.stringify(mod.sizeAt({ w: 480, h: 460, left: 40, top: 60 }, 120, 80, 1600, 900)))
  out.push('pin|' + JSON.stringify(mod.upsertPin([], mod.makePin(URLS[0]), 12)))
  out.push('visitEmpty|' + JSON.stringify(mod.bumpVisit([], URLS[0], 24)))
  out.push('pageState|' + JSON.stringify(mod.pageMediaState(PAGE_RAW)) + '|' + JSON.stringify(mod.pageMediaState(null)) + '|' + JSON.stringify(mod.pageMediaState({ has: true, t: -5, d: 1e9, r: 99, v: 999 })))
  out.push('sameMedia|' + String(!!(mod.samePageMedia && mod.samePageMedia(mod.pageMediaState(PAGE_RAW), mod.pageMediaState(PAGE_RAW))))
    + '|' + String(!!(mod.samePageMedia && mod.samePageMedia(mod.pageMediaState(PAGE_RAW), mod.pageMediaState({ ...PAGE_RAW, t: 43 })))))
  return createHash('sha256').update(out.join('\n')).digest('hex')
}

if (PROFILE) {
  // Long, even loops so the sampler can rank self-time per function.
  const long = ITER * 12
  for (const [name, fn] of Object.entries(W)) bench(name, fn, long)
  bench('mixed', mixed, long)
  console.log(JSON.stringify({ profile: true, iter: long, golden: golden() }))
} else {
  const heapBefore = process.memoryUsage().heapUsed
  const results = []
  for (const [name, fn] of Object.entries(W)) results.push(bench(name, fn, ITER))
  results.push(bench('mixed', mixed, ITER))
  const mu = process.memoryUsage()
  console.log(JSON.stringify({
    iter: ITER, golden: golden(),
    workloads: results,
    heapDelta: mu.heapUsed - heapBefore,
    heapPeak: mu.heapUsed,
    rss: mu.rss,
  }))
}
"""


def git_state():
    """HEAD plus a dirty marker. A missing git is a named unknown, never a crash."""
    try:
        head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=str(ROOT),
                             capture_output=True, text=True, timeout=10)
        tag = head.stdout.strip() if head.returncode == 0 else "no-commit"
        dirty = subprocess.run(["git", "status", "--porcelain"], cwd=str(ROOT),
                              capture_output=True, text=True, timeout=10)
        return tag + (" (dirty working tree)" if dirty.stdout.strip() else "")
    except (OSError, subprocess.SubprocessError):
        return "unavailable"


def fingerprint(source_sha, runs, iters, profile):
    return {
        "run_id": dt.datetime.now().strftime("%Y%m%dT%H%M%S"),
        "timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source_sha256": source_sha,
        "git_sha": git_state(),
        "cpu_model": platform.processor() or "unavailable on this Windows host",
        "cpu_cores": os.cpu_count(),
        "smt_state": "unavailable",
        "governor_no_turbo": "unavailable (Windows)",
        "ram_bytes": "unavailable (Windows, no /proc/meminfo)",
        "storage_fs": "NTFS (Windows)",
        "kernel": platform.platform(),
        "node": subprocess.run(["node", "-v"], capture_output=True, text=True).stdout.strip(),
        "python": platform.python_version(),
        "build_profile": "uncompiled ESM, loaded directly by Node (matches the shipped plugin)",
        "workload_isolation": "single Node process per run, no taskset/cgroup (Windows)",
        "cache_state": "warm: 200-iteration warmup before every timed loop; 25 independent processes",
        "runs": runs,
        "iter_per_workload": iters,
        "profile_mode": profile,
        "scenario": (
            "Detached/floating dock, autoTheater=true, theaterScope=any, "
            "12 concurrent sessions, 24-row visit ledger, 12-row queue. "
            "Per iteration: 1 URL paste/validation, 1 visit bump, 1 settings "
            "normalization, 1 queue advance, 1 layout+chrome decision, "
            "1 theater plan, 1 full pane render, 3 reactive atom ticks."
        ),
    }


def percentile(xs, p):
    s = sorted(xs)
    if not s:
        return None
    k = (len(s) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return round(s[lo] + (s[hi] - s[lo]) * (k - lo), 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=25)
    ap.add_argument("--iter", type=int, default=3000)
    ap.add_argument("--no-profile", action="store_true")
    ap.add_argument("--source", default=None,
                    help="override plugin.js path (for A/B against a frozen baseline)")
    args = ap.parse_args()

    source_path = pathlib.Path(args.source) if args.source else (ROOT / "desktop" / "plugin.js")
    # Hash the SHIPPED bytes, not read_text() output: universal-newline
    # translation would turn CRLF into LF and report a hash that is not
    # the deployed module (the byte-exact claim in .gitattributes).
    source_bytes = source_path.read_bytes()
    sha = hashlib.sha256(source_bytes).hexdigest()
    source = source_bytes.decode("utf-8")
    run_id = dt.datetime.now().strftime("%Y%m%dT%H%M%S")
    art = ROOT / "tests" / "artifacts" / "perf" / run_id
    art.mkdir(parents=True, exist_ok=True)

    rg.build()                              # same stub SDK as the behavior gate
    # Unique per run (run id + pid): two probes, or a probe racing the gate, share this
    # directory. Writing one fixed `under-test.mjs`/`bench.mjs` let a run import another
    # run's module (or another run's template) while printing its own sha.
    work_mod = "under-test-%s-%d.mjs" % (run_id, os.getpid())
    work_bench = "bench-%s-%d.mjs" % (run_id, os.getpid())
    (rg.WORK / work_mod).write_bytes(source_bytes)
    (rg.WORK / work_bench).write_text(BENCH, encoding="utf-8")
    node = shutil.which("node") or "node"

    fp = fingerprint(sha, args.runs, args.iter, not args.no_profile)
    fp["run_id"] = run_id
    (art / "fingerprint.json").write_text(json.dumps(fp, indent=2), encoding="utf-8")

    env = dict(os.environ, BENCH_ITER=str(args.iter), BENCH_PROFILE="0",
               BENCH_MODULE="./" + work_mod)
    runs_out = []
    for r in range(args.runs):
        proc = subprocess.run([node, work_bench], capture_output=True, text=True,
                              cwd=str(rg.WORK), env=env, timeout=300, check=False)
        if proc.returncode != 0:
            print("BENCH RUN FAILED (module %s, sha %s):\n%s%s"
                  % (work_mod, sha[:16], proc.stdout, proc.stderr))
            return 1
        runs_out.append(json.loads(proc.stdout.strip().splitlines()[-1]))

    names = [w["name"] for w in runs_out[0]["workloads"]]
    golds = {r["golden"] for r in runs_out}
    if len(golds) != 1:
        print("NON-DETERMINISTIC GOLDEN:", golds)
        return 1
    baseline = {"unit": "ns/op (plugin-side CPU, stubbed Node host)", "runs": args.runs,
                "iter_per_workload": args.iter, "golden_sha256": golds.pop(), "workloads": {}}
    for name in names:
        xs = [next(w["nsPerOp"] for w in r["workloads"] if w["name"] == name) for r in runs_out]
        baseline["workloads"][name] = {
            "p50": percentile(xs, 0.50), "p95": percentile(xs, 0.95),
            "p99": percentile(xs, 0.99), "max": round(max(xs), 1),
            "mean": round(statistics.mean(xs), 1),
            "ops_per_sec": round(1e9 / statistics.mean(xs), 0),
        }
    heap = [r["heapDelta"] for r in runs_out]
    baseline["heap_delta_bytes"] = {"p50": percentile(heap, 0.50), "max": max(heap)}
    baseline["rss_bytes"] = max(r["rss"] for r in runs_out)
    (art / "baseline.json").write_text(json.dumps(baseline, indent=2), encoding="utf-8")

    hotspots = []
    if not args.no_profile:
        penv = dict(os.environ, BENCH_ITER=str(args.iter), BENCH_PROFILE="1",
                    BENCH_MODULE="./" + work_mod)
        p = subprocess.run([node, "--cpu-prof", "--cpu-prof-dir", str(art), work_bench],
                           capture_output=True, text=True, cwd=str(rg.WORK), env=penv,
                           timeout=600, check=False)
        if p.returncode != 0:
            print("PROFILE RUN FAILED (module %s, sha %s):\n%s%s"
                  % (work_mod, sha[:16], p.stdout, p.stderr))
            return 1
        cps = sorted(art.glob("*.cpuprofile"))
        if cps:
            prof = json.loads(cps[-1].read_text(encoding="utf-8"))
            counts = {}
            for n in prof.get("nodes", []):
                cf = n.get("callFrame", {})
                hc = n.get("hitCount", 0)
                if not hc:
                    continue
                label = "%s @ %s:%d" % (cf.get("functionName") or "(anonymous)",
                                        cf.get("url") or "(native)", cf.get("lineNumber", -1) + 1)
                counts[label] = counts.get(label, 0) + hc
            total = sum(counts.values()) or 1
            for label, hc in sorted(counts.items(), key=lambda kv: -kv[1])[:20]:
                hotspots.append({"function": label, "hitCount": hc,
                                 "pct": round(100.0 * hc / total, 2)})
            (art / "profile_nodes.json").write_text(
                json.dumps({"total_samples": total, "top20": hotspots}, indent=2), encoding="utf-8")

    lines = ["# Hotspot table — media-dock plugin-side CPU", "",
             "Run `%s` · source sha256 `%s`" % (run_id, sha[:16]), "",
             "Baseline: `%s` · Profile: `%s`" % (art / "baseline.json",
                                                 (sorted(art.glob("*.cpuprofile")) or ["(none)"])[-1]), "",
             "| Rank | Location | Metric | Value | Category | Evidence |",
             "|---|---|---|---|---|---|"]
    for i, name in enumerate(names, 1):
        b = baseline["workloads"][name]
        lines.append("| %d | %s | p95 ns/op | %s | CPU | baseline.json#workloads.%s |"
                     % (i, name, b["p95"], name))
    for i, h in enumerate(hotspots[:8], len(names) + 1):
        lines.append("| %d | %s | sampler hitCount | %s (%.2f%%) | CPU | %s |"
                     % (i, h["function"].replace("|", "/"), h["hitCount"], h["pct"],
                        (sorted(art.glob("*.cpuprofile")) or ["(none)"])[-1].name))
    lines += ["", "**Not measured here:** Electron renderer/compositor cost, webview decode, "
              "host-side React reconciliation, GPU. Those are outside `desktop/plugin.js`.", ""]
    (art / "hotspots.md").write_text("\n".join(lines), encoding="utf-8")

    print("RUN", run_id, "sha", sha[:16])
    print("GOLDEN", baseline["golden_sha256"])
    print("workload".ljust(14), "p50".rjust(10), "p95".rjust(10), "p99".rjust(10),
          "max".rjust(10), "ops/s".rjust(12))
    for name in names:
        b = baseline["workloads"][name]
        print(name.ljust(14), str(b["p50"]).rjust(10), str(b["p95"]).rjust(10),
              str(b["p99"]).rjust(10), str(b["max"]).rjust(10), str(b["ops_per_sec"]).rjust(12))
    print("heap delta p50 bytes:", baseline["heap_delta_bytes"]["p50"])
    print("profile top:", hotspots[:5])
    print("artifacts:", art)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
