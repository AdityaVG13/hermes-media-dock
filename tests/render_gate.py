#!/usr/bin/env python3
"""Behavior gate for media-dock — harness-engineered.

Loads the plugin as real ESM against a stateful stub SDK, drives register(),
renders every contribution, clicks every handler, exercises pure geometry /
layout / immersive / fullscreen / resize decisions, and runs a mutation
battery where EVERY mutant must make the gate FAIL.

    python tests/render_gate.py [plugin.js] [--no-mutate]
"""
import json
import pathlib
import re
import shutil
import subprocess
import sys

WORK = pathlib.Path(__file__).resolve().parent / "_render_gate_work"

HARNESS = r"""
import fs from 'node:fs'
import { pathToFileURL } from 'node:url'
import { RENDERED, EFFECTS } from 'react'
import { host } from '@hermes/plugin-sdk'

const target = process.argv[2]
const source = fs.readFileSync(target, 'utf8')
const HERE = new URL('./', import.meta.url)
const failures = []
const ok = (cond, msg) => { if (!cond) failures.push(msg) }
const eq = (a, b, msg) => ok(JSON.stringify(a) === JSON.stringify(b), msg + ' (got ' + JSON.stringify(a) + ')')
const near = (a, b, msg) => ok(Math.abs(a - b) < 0.001, msg + ' (got ' + a + ' want ' + b + ')')

globalThis.addEventListener = () => {}
globalThis.ResizeObserver = class { observe() {} disconnect() {} }

let seq = 0
async function fresh(text) {
  const name = 'case' + (++seq) + '.mjs'
  fs.writeFileSync(new URL(name, HERE), text)
  return await import(new URL(name, HERE).href)
}

function makeCtx(store) {
  const registered = []
  const listeners = []
  const disposers = []
  const events = []
  const storage = new Map(Object.entries(store || {}))
  const ctx = {
    register: (d) => { registered.push(d); if (d.area === 'panes') globalThis.__paneRegistered = d.data || null; return () => {} },
    registerMany: (ds) => { for (const d of ds) registered.push(d); return () => {} },
    registerSettingsPage: (d) => { registered.push({ __settings: true, ...d }); return () => {} },
    rest: async () => ({}),
    socket: () => () => {},
    setTimeout: () => () => {},
    setInterval: () => () => {},
    addEventListener: (t, type, fn) => { listeners.push({ type, fn }); return () => {} },
    onEvent: (type, fn) => { const e = { type, fn }; events.push(e); return () => { const i = events.indexOf(e); if (i >= 0) events.splice(i, 1) } },
    onDispose: (fn) => { disposers.push(fn) },
    runAction: () => ({ ok: true }),
    listActions: () => [],
    storage: {
      get: (k, d) => (storage.has(k) ? storage.get(k) : d),
      set: (k, v) => { storage.set(k, v) },
      remove: (k) => { storage.delete(k) },
    },
    os: { openExternal: () => Promise.resolve(true), writeClipboard: () => Promise.resolve(true) },
    preview: { isAvailable: () => false, executeJavaScript: async () => null },
    i18n: { t: (s) => s },
  }
  return { registered, listeners, disposers, events, storage, ctx }
}

function walk(node, visit, depth, seen) {
  if (!node || typeof node !== 'object' || depth > 60) return
  if (seen.has(node)) return
  seen.add(node)
  if (Array.isArray(node)) { for (const c of node) walk(c, visit, depth + 1, seen); return }
  if (node.props && typeof node.props === 'object') visit(node)
  const kids = node.props && node.props.children
  if (kids) walk(kids, visit, depth + 1, seen)
  if (node.props) for (const k of Object.keys(node.props)) {
    if (k === 'children') continue
    const v = node.props[k]
    if (v && typeof v === 'object') walk(v, visit, depth + 1, seen)
  }
}

const EV = {
  preventDefault() {}, stopPropagation() {}, key: 'Enter',
  clientX: 100, clientY: 80, pointerId: 1, button: 0,
  target: { value: 'https://example.com/pasted.mp4', checked: true, currentTime: 12,
            duration: 100, volume: 0.5, muted: false, error: { code: 4 },
            setPointerCapture() {}, releasePointerCapture() {}, requestFullscreen() { return Promise.resolve() } },
  clipboardData: { getData: () => 'https://example.com/pasted.mp4' },
  dataTransfer: { getData: () => 'https://example.com/dropped.mp4\n', dropEffect: '' },
}

function clickAll(trees, label) {
  let n = 0
  for (const tree of trees) walk(tree, (node) => {
    for (const k of Object.keys(node.props)) {
      if (!/^on[A-Z]/.test(k) || typeof node.props[k] !== 'function') continue
      n++
      try { node.props[k](EV) } catch (err) { failures.push(label + ' handler ' + k + ' threw: ' + (err && err.message)) }
    }
  }, 0, new Set())
  ok(n >= 8, label + ' exposed too few handlers (' + n + ') — the click sweep is vacuous')
  return n
}

function find(tree, pred) {
  let hit = null
  walk(tree, (node) => { if (!hit && pred(node)) hit = node }, 0, new Set())
  return hit
}

// A timing gate is proven by the delay it ARMS, then fired on demand: sleeping the real
// 3.4 s here would cost 123 mutant runs about seven minutes and prove nothing extra.
const gateTimers = []
const realSetTimeout = globalThis.setTimeout
function holdLongTimers() {
  globalThis.setTimeout = (fn, ms, ...rest) => {
    if (ms >= 1000) { const t = { fn, ms, id: 0 }; gateTimers.push(t); t.id = realSetTimeout(() => {}, 0); return t.id }
    return realSetTimeout(fn, ms, ...rest)
  }
}
function fireLongTimer(ms) {
  const i = gateTimers.findIndex((t) => t.ms === ms)
  if (i < 0) return false
  const t = gateTimers.splice(i, 1)[0]
  t.fn()
  return true
}
// Every mounted controller subscribes to the same host atoms, so one busy flip arms several
// settle gates. Fire them all: the assertion is about this controller's own automation state.
function fireLongTimers(ms) { let n = 0; while (fireLongTimer(ms)) n += 1; return n }
function releaseLongTimers() { globalThis.setTimeout = realSetTimeout; gateTimers.length = 0 }

// React calls function refs on mount and with null on unmount; the stub tree
// does not attach them on its own. Drive them so lifecycle behavior is real.
function attachRefs(tree, node) {
  walk(tree, (n) => {
    const r = n.props && n.props.ref
    if (typeof r === 'function') r(node)
  }, 0, new Set())
}

// ---------------------------------------------------------------- pure behavior
const mod = await fresh(source)
const P = mod.parseMediaUrl
ok(typeof P === 'function', 'parseMediaUrl not exported')

const generic = [
  'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
  'https://youtu.be/dQw4w9WgXcQ?t=90',
  'https://www.twitch.tv/nousresearch',
  'https://www.twitch.tv/videos/123456789',
  'https://www.netflix.com/title/1',
  'https://open.spotify.com/track/abc123',
  'https://example.com/doc',
  'https://kick.com/a',
  'youtube.com',
  '//example.com/x',
  'https://例え.テスト/',
  'http://localhost:8080/a',
]
for (const raw of generic) {
  const r = P(raw)
  ok(r && r.ok === true, 'generic URL refused: ' + raw)
  if (!r || !r.ok) continue
  eq(r.kind, 'page', 'generic URL must be kind=page: ' + raw)
  ok(!('provider' in r) && !('id' in r) && !('start' in r), 'per-site field leaked into parse result: ' + raw)
  ok(typeof r.src === 'string' && r.src === r.pageUrl, 'src/pageUrl contract: ' + raw)
  ok(/^https?:\/\//i.test(r.src), 'parse must return an absolute http(s) src: ' + raw)
}
ok(typeof mod.guestOverlay === 'function', 'guestOverlay must decide whether a page is the stage or a failure hint')
if (typeof mod.guestOverlay === 'function') {
  eq(mod.guestOverlay(false), 'stage', 'a working page is the stage, not a hint')
  eq(mod.guestOverlay(true), 'hint', 'a failed guest load is a named hint')
  eq(mod.guestOverlay(undefined), 'stage', 'only a real failure overlays the page')
}

eq(P('https://cdn.example.com/v/flower.mp4').kind, 'native', '.mp4 must be native')
eq(P('https://cdn.example.com/v/flower.mp4').media, 'video', '.mp4 is video')
eq(P('https://cdn.example.com/a/song.MP3').media, 'audio', 'extension matching is case-insensitive')
eq(P('https://x.example/stream.opus').kind, 'native', '.opus must be native')
eq(P('https://example.com/watch?file=a.mp4').kind, 'page', 'classification must use pathname, not query')
// A host:port with no scheme reads as a scheme named after the host. That is a URL, not a
// refused scheme: refusing it told a user pasting localhost:3000 that only http(s) loads here.
eq(P('localhost:3000').ok, true, 'a bare host with a port is a URL, not a scheme')
eq(P('localhost:3000').src, 'https://localhost:3000/', 'the port stays a port and https fills the scheme')
eq(P('example.com:8080/a.mp4').kind, 'native', 'a dotted host with a port and a media path is still a media file')
eq(P('javascript:alert(1)').error, 'scheme', 'a real script scheme stays refused')
eq(P('mailto:someone@example.com').error, 'scheme', 'mailto stays refused')
// Stepping speed from a rate a site chose (1.1x) must move forward, not fall back to the
// first preset — the same dead-second-click trap as the size ladder.
eq(mod.nextRate(1), 1.25, 'speed steps up to the next preset')
eq(mod.nextRate(2), 0.5, 'the last speed wraps to the slowest')
eq(mod.nextRate(1.1), 1.25, 'an off-ladder site rate steps to the next preset up')
eq(mod.nextRate(0.25), 0.5, 'the slowest site rate still steps up')
// A queue row that cannot start must become ONE labelled control, not a dead 0:00, and must not
// shout over a file that is playing or one that failed for a real reason.
const ANG = mod.autoplayNeedsGesture
ok(typeof ANG === 'function', 'autoplayNeedsGesture must be exported')
eq(ANG({ waited: true, paused: true, t: 0, failed: null }), true, 'an autoplay that never started asks for one click')
eq(ANG({ waited: true, paused: false, t: 0.4, failed: null }), false, 'a playing file needs no gate')
eq(ANG({ waited: true, paused: false, t: 0.05, failed: null }), false, 'a file that just started at 0.05s is playing, not blocked')
eq(ANG({ waited: true, paused: true, t: 30, failed: null }), false, 'paused well into playback is not a start failure')
eq(ANG({ waited: true, paused: true, t: 0, failed: 'decode' }), false, 'a real error is reported as the error, not the gate')
eq(ANG({ waited: false, paused: true, t: 0, failed: null }), false, 'no gate before the settle window')
// A control's spoken name must be the text on screen. chromeBtn took its name from the tooltip,
// so the footer's Theater button announced "Grow the player to almost fill the window" and could
// not be found by the label a person reads.
{
  const S = makeCtx({ session: { raw: 'https://example.com/a.mp4', floating: false }, settings: { autoplay: false } })
  const m = await fresh(source)
  m.default.register(S.ctx)
  const pane = S.registered.find((d) => d.area === 'panes' && typeof d.render === 'function')
  const btns = []
  walk(pane.render(), (n) => { if (n.type === 'stub-Button' && n.props && typeof n.props.children === 'string') btns.push(n) }, 0, new Set())
  ok(btns.length >= 3, 'the footer renders text buttons: ' + btns.length)
  const bad = btns.filter((b) => b.props['aria-label'] !== b.props.children).map((b) => b.props.children)
  eq(bad.join('|'), '', 'every text button announces the label it shows')
}

eq(P('https://cdn.example.com/s/master.m3u8').ok, false, 'HLS manifest must be refused')
eq(P('https://cdn.example.com/s/master.m3u8').error, 'manifest', 'HLS refusal must name its cause')
eq(P('https://cdn.example.com/s/a.mpd').ok, false, 'DASH manifest must be refused')
for (const bad of ['javascript:alert(1)', 'file:///tmp/x', 'data:text/html,x', 'ftp://x.example/a']) {
  eq(P(bad).ok, false, 'non-http(s) scheme must be refused: ' + bad)
  eq(P(bad).error, 'scheme', 'scheme refusal must be named: ' + bad)
}
eq(P('').error, 'empty', 'empty input refused as empty')
eq(P('dQw4w9WgXcQ').ok, false, 'bare 11-char id must NOT become a video embed')
eq(P('not a url at all').ok, false, 'garbage must be refused')

eq(mod.classifyMedia('https://x.example/a.mp4?y=.mp3'), { kind: 'native', ext: 'mp4', media: 'video' }, 'classifyMedia pathname only')
eq(mod.classifyMedia('https://x.example/a'), null, 'no extension -> not media')
eq(mod.classifyMedia('garbage'), null, 'classifyMedia refuses non-url')
eq(mod.formatTime(0), '0:00', 'formatTime 0')
eq(mod.formatTime(65), '1:05', 'formatTime 65')
eq(mod.formatTime(3661), '1:01:01', 'formatTime hours')
eq(mod.formatTime(-1), '0:00', 'formatTime negative')
eq(mod.formatTime(NaN), '0:00', 'formatTime NaN')
// A live element reports duration === Infinity. The state must carry that through, because the
// rail's only input for "this cannot seek" is the flag — losing it re-renders a dead scrubber.
eq(mod.pageMediaState({ has: true, live: true, paused: false, t: 61 }).live, true, 'live survives the state allowlist')
eq(mod.pageMediaState({ has: true, paused: false, t: 61, d: 600 }).live, false, 'a VOD is not live')
ok(!mod.pageMediaState({ has: false }).live, 'no media is not live')
// The guest's identity is a compatibility literal: Electron's own token is not a browser any site
// recognises, and one live-streaming site answered it with its mobile page.
ok(/^Mozilla\/5\.0 \(Windows NT/.test(String(mod.GUEST_UA)), 'guest UA is a desktop Chromium string')
ok(String(mod.GUEST_UA).indexOf('Electron/') < 0, 'guest UA carries no Electron token')
eq(mod.clampVolume(-5), 0, 'clampVolume low')
eq(mod.clampVolume(250), 200, 'clampVolume caps boost at 200 (+6 dB)')
eq(mod.clampVolume(37.6), 38, 'clampVolume rounds')
eq(mod.clampVolume(NaN), 80, 'clampVolume NaN -> default')

const D = mod.SETTINGS_DEFAULTS
ok(D && Object.isFrozen(D), 'SETTINGS_DEFAULTS must be frozen')
eq(mod.settingsWithDefaults(D), D, 'defaults round-trip')
eq(mod.settingsWithDefaults(null), D, 'null -> defaults')
const dirty = mod.settingsWithDefaults({ volume: 999, rate: 7, restoreMode: 'bogus', autoplay: 'yes', loop: 1, immersiveOnPlay: 'no' })
eq(dirty.volume, 200, 'volume clamped at the 200% boost ceiling')
eq(dirty.rate, 1, 'invalid rate -> default')
eq(dirty.restoreMode, 'url', 'invalid restoreMode -> default')
eq(dirty.autoplay, false, 'non-boolean autoplay -> default')
eq(dirty.loop, false, 'non-boolean loop -> default')
eq(dirty.immersiveOnPlay, true, 'non-boolean immersiveOnPlay -> default')
eq(mod.settingsWithDefaults(dirty), dirty, 'settingsWithDefaults is idempotent')
for (const mode of ['url', 'playing', 'blank']) eq(mod.settingsWithDefaults({ restoreMode: mode }).restoreMode, mode, 'restoreMode ' + mode)

const q = [{ url: 'a' }, { url: 'b' }, { url: 'c' }]
eq(mod.nextInQueue([], 'a', false), null, 'empty queue')
eq(mod.nextInQueue(q, 'a', false), { url: 'b' }, 'advance a->b')
eq(mod.nextInQueue(q, 'c', false), null, 'no wrap by default')
eq(mod.nextInQueue(q, 'c', true), { url: 'a' }, 'wrap on loop')
eq(mod.nextInQueue(q, 'z', false), { url: 'a' }, 'unknown current -> first')
eq(q.length, 3, 'nextInQueue must not mutate input')
eq(mod.prevInQueue([], 'a', false), null, 'empty queue has no previous')
eq(mod.prevInQueue(q, 'c', false), { url: 'b' }, 'previous c->b')
eq(mod.prevInQueue(q, 'a', false), null, 'no wrap backward by default')
eq(mod.prevInQueue(q, 'a', true), { url: 'c' }, 'previous wraps on loop')
eq(mod.prevInQueue(q, 'z', false), { url: 'c' }, 'unknown current -> last')
const order = [{ id: '1', url: 'a' }, { id: '2', url: 'b' }, { id: '3', url: 'c' }]
eq(mod.movePin(order, '2', 1).map((p) => p.url).join(','), 'a,c,b', 'move later')
eq(mod.movePin(order, '2', -1).map((p) => p.url).join(','), 'b,a,c', 'move earlier')
eq(mod.movePin(order, '1', -1).map((p) => p.url).join(','), 'a,b,c', 'earlier at the head is identity')
eq(mod.movePin(order, '3', 1).map((p) => p.url).join(','), 'a,b,c', 'later at the tail is identity')
eq(order.map((p) => p.url).join(','), 'a,b,c', 'movePin must not mutate input')

const pinA = mod.makePin('https://cdn.example.com/flower.mp4')
const pinB = mod.makePin('https://cdn.example.com/song.mp3')
ok(pinA && pinA.title !== pinB.title, 'distinct pins get distinct titles')
ok(pinA && !('provider' in pinA) && !('mediaId' in pinA), 'pin must not carry per-site fields')
eq(mod.makePin('javascript:alert(1)'), null, 'javascript: must not become a pin')
eq(mod.makePin('https://x.example/a.m3u8'), null, 'manifest must not become a pin')
let acc = mod.upsertPin([], pinA, 12)
acc = mod.upsertPin(acc, pinA, 12)
eq(acc.length, 1, 'upsertPin dedupes by url')
eq(mod.upsertPin(acc, pinB, 12)[0].url, pinB.url, 'new pin lands at front')
eq(mod.removePin(mod.upsertPin(acc, pinB, 12), pinB.id).length, 1, 'removePin drops by id')
let many = []
for (let i = 0; i < 15; i++) many = mod.upsertPin(many, mod.makePin('https://x.example/p' + i + '.mp4'), 12)
eq(many.length, 12, 'pins cap at max')

let v = []
for (const u of ['https://kick.com/a', 'https://www.netflix.com/title/1', 'https://kick.com/b', 'https://kick.com/c']) v = mod.bumpVisit(v, u)
const top = mod.suggestVisits(v, '', 8)
eq(top[0].host, 'kick.com', 'most-visited host ranks first')
eq(top[0].count, 3, 'visit count accumulates')
eq(top[0].url, 'https://kick.com/c', 'latest URL kept per host')
ok(top.some((r) => r.host === 'netflix.com'), 'any host can appear, not a preset list')
eq(mod.suggestVisits(v, 'net', 8).length, 1, 'typed query filters visits')
eq(mod.bumpVisit(v, 'javascript:alert(1)').length, v.length, 'javascript: must not become a visit')
// Metamorphic: passing the caller's already-parsed result must be byte-identical to
// re-parsing the raw URL. This guards the visit-bump shortcut's isomorphism.
for (const u of ['https://kick.com/a', 'https://www.netflix.com/title/1', 'youtube.com', 'javascript:alert(1)', '']) {
  const pp = mod.parseMediaUrl(u)
  const raw2 = pp.pageUrl || u
  eq(mod.bumpVisit(v, raw2, 24, pp), mod.bumpVisit(v, raw2, 24),
     'pre-parsed bumpVisit is isomorphic to re-parse: ' + u)
}
ok(/preview\//.test(mod.previewMarkdown('https://example.com/x')), 'previewMarkdown builds a Browser link')
try { mod.previewMarkdown('not-a-url'); failures.push('previewMarkdown accepted a non-url') } catch { /* expected */ }

ok(/HLS|DASH|decoder/i.test(mod.errorCopy('manifest')), 'manifest error names the cause')
ok(/http\(s\)/i.test(mod.errorCopy('scheme')), 'scheme error names the cause')
ok(/guest|sign-in|embedded/i.test(mod.errorCopy('frame-blocked')), 'frame-blocked names the cause')
ok(/codec|container/i.test(mod.mediaErrorCopy(3)), 'decode error names the cause')

// ------------------------------------------------- geometry: anchor-aware resize
const NEED = ['clampSize', 'sizeAt', 'nextLadder', 'layoutFor', 'chromeFor', 'paintSize', 'unpaintSize', 'fullscreenRequest', 'fullscreenExit']
for (const n of NEED) ok(typeof mod[n] === 'function', n + ' must be exported for behavior testing')

if (typeof mod.clampSize === 'function') {
  const C = mod.clampSize
  eq(C(100, 100, 1920, 1080), { w: 380, h: 300 }, 'clampSize enforces CARD_MIN')
  eq(C(99999, 99999, 1000, 800), { w: 976, h: 776 }, 'clampSize caps at viewport-24')
  eq(C(560, 470, 1920, 1080), { w: 560, h: 470 }, 'clampSize keeps in-range value')
  eq(C(-8, -8, 1920, 1080), { w: 380, h: 300 }, 'clampSize refuses negative')
}
if (typeof mod.sizeAt === 'function') {
  const from = { w: 640, h: 520, left: 200, top: 60, right: 840, bottom: 580 }
  // top-right anchor: dragging the FREE bottom-left corner left/down grows w/h,
  // and the pinned RIGHT and TOP edges must not move.
  const s = mod.sizeAt(from, -120, 80, 1920, 1080)
  eq(s.w, 760, 'sizeAt: drag left grows width (top-right anchor)')
  eq(s.h, 600, 'sizeAt: drag down grows height (top pinned)')
  eq(s.left + s.w, from.right, 'sizeAt: right edge stays pinned')
  eq(s.top, from.top, 'sizeAt: top edge stays pinned')
  const small = mod.sizeAt(from, 99999, 99999, 1000, 800)
  ok(small.w >= 380 && small.h >= 300, 'sizeAt clamps to min on reverse drag')
  eq(from.w, 640, 'sizeAt must not mutate its input')
  const cap = mod.sizeAt(from, -99999, -99999, 1000, 800)
  ok(cap.w <= 976 && cap.h <= 776, 'sizeAt clamps to viewport-24')
}
if (typeof mod.nextLadder === 'function') {
  const L = mod.nextLadder
  eq(L(480, 460), [640, 520], 'nextLadder advances one step')
  let cur = [480, 460], seen = []
  for (let i = 0; i < 8; i++) { cur = L(cur[0], cur[1]); seen.push(cur[0] + 'x' + cur[1]) }
  ok(new Set(seen).size >= 3, 'nextLadder visits several distinct sizes')
  eq(L(...L(...L(...L(480, 460)))), [480, 460], 'nextLadder wraps back to start after a full cycle')
  eq(L(500, 400), [640, 520], 'an off-ladder size steps forward instead of repeating the first preset')
  eq(L(2000, 2000), [480, 460], 'a size past the last step wraps')
}
if (typeof mod.layoutFor === 'function') {
  const F = mod.layoutFor
  for (const w of [15, 120, 189]) eq(F(w, 'auto').rail, true, 'width ' + w + ' must be a rail strip')
  eq(F(190, 'auto').rail, false, '190 is not rail')
  eq(F(190, 'auto').tier, 'compact', '190 is compact')
  eq(F(420, 'auto').tier, 'regular', '420 is regular')
  eq(F(1600, 'auto').tier, 'wide', '1600 is wide')
  eq(F(0, 'auto').rail, false, 'unmeasured width must NOT flash the rail strip')
  eq(F(0, 'auto').tier, 'regular', 'unmeasured width answers the normal tier')
  eq(F(500, 'regular').wrap, true, 'wrap is geometry: 500px wraps even when tier says regular')
  eq(F(1600, 'compact').wrap, false, 'wrap is geometry: wide never wraps')
  eq(F(15, 'ultra').rail, true, 'preference cannot conjure pixels: forced ultra at 15px is still rail')
  eq(F(1600, 'compact').tier, 'compact', 'known override beats measurement for detail')
  eq(F(500, 'bogus-tier').tier, 'regular', 'unknown override falls back to measuring')
  eq(F(120, 'auto').roomy, false, 'unlisted rail tier defaults to the SMALLER promise (positive set)')
  eq(F(1600, 'auto').roomy, true, 'wide is roomy (positive set)')
  eq(F(200, 'auto').roomy, false, 'compact is not roomy')
}
if (typeof mod.chromeFor === 'function') {
  const CF = mod.chromeFor
  const normal = CF(false, mod.layoutFor(900, 'auto'))
  eq(normal.address, true, 'normal chrome shows address bar')
  eq(normal.queue, true, 'normal chrome shows queue')
  eq(normal.transport, true, 'controls always present')
  eq(normal.exit, false, 'no exit affordance outside immersive')
  const focus = CF(true, mod.layoutFor(900, 'auto'))
  eq(focus.address, false, 'immersive hides the address bar')
  eq(focus.queue, true, 'immersive keeps the queue — playing must never hide the watch list')
  eq(focus.footer, false, 'immersive hides the footer')
  eq(focus.transport, true, 'immersive NEVER hides controls (width buys detail, not controls)')
  eq(focus.exit, true, 'immersive must expose an exit affordance')
  eq(CF(true, mod.layoutFor(900, 'auto'), 'page').address, true, 'a page keeps the address bar even in focus')
  eq(CF(true, mod.layoutFor(900, 'auto'), 'page').exit, false, 'a page must not cover its controls with a focus overlay')
  const rail = CF(false, mod.layoutFor(120, 'auto'))
  eq(rail.transport, true, 'rail tier still exposes controls')
  eq(rail.queue, false, 'rail tier drops the queue list')
  eq(CF(false, mod.layoutFor(380, 'auto')).queue, true, 'card minimum still shows the queue')
}
if (typeof mod.paintSize === 'function' && typeof mod.unpaintSize === 'function') {
  const PS = mod.paintSize, US = mod.unpaintSize
  const floating = { style: {} }, docked = { style: {} }
  const s = { w: 760, h: 600, left: 80, top: 60 }
  eq(PS(floating, s, true), true, 'paintSize succeeds on a real frame node')
  eq(floating.style.width, '760px', 'paintSize writes width')
  eq(floating.style.height, '600px', 'paintSize writes height')
  eq(floating.style.left, '80px', 'floating frame gets left')
  eq(floating.style.top, '60px', 'floating frame gets top')
  eq(PS(docked, s, false), true, 'paintSize succeeds on docked root')
  eq(docked.style.width, '760px', 'docked root gets width')
  ok(!('left' in docked.style) && !('top' in docked.style), 'docked must NOT write left/top (track owns x/y)')
  eq(PS(null, s, true), false, 'paintSize refuses a detached node')
  US(floating)
  eq(floating.style.width, '', 'unpaintSize hands the track back')
  ok(!('left' in floating.style) || floating.style.left === '', 'unpaintSize clears position')
}
ok(typeof mod.paintCard === 'function', 'paintCard must be callable so a docked click cannot size the pane')
ok(typeof mod.startResize === 'function', 'startResize must be callable so a docked drag can be refused')
if (typeof mod.paintCard === 'function') {
  const stuck = { style: { width: '87px', height: '1136px', left: '0px', top: '0px' }, closest() { return null } }
  eq(mod.paintCard(stuck), false, 'a docked size click must not paint the pane root')
  eq(stuck.style.width, '', 'a docked size click clears a stuck inline width')
  eq(stuck.style.height, '100%', 'a docked size click restores the pane height instead of blanking it')
  const laidOut = { style: { width: '', height: '100%', left: '', top: '' }, closest() { return null } }
  mod.paintCard(laidOut)
  eq(laidOut.style.height, '100%', 'a docked size click must not wipe the layout height the bar and the page need')
  const frame = { style: {}, closest() { return frame } }
  eq(mod.paintCard(frame), true, 'a floating size click paints the floating frame')
  ok(parseInt(frame.style.width, 10) >= 380, 'floating size click writes a clamped width onto the frame, not the dock')
  ok(!('left' in frame.style) && !('top' in frame.style), 'a size click must not move the floating card to 0,0')
}
if (typeof mod.startResize === 'function') {
  const dockedRoot = { style: { width: '', height: '' }, getBoundingClientRect() { return { width: 87, height: 1136, left: 0, top: 0, right: 87, bottom: 1136 } }, closest() { return null } }
  eq(mod.startResize('corner', { clientX: 10, clientY: 10, preventDefault() {}, stopPropagation() {} }, dockedRoot), false, 'a docked drag must not start')
  eq(dockedRoot.style.width, '', 'a docked drag must not write a width')
}
if (typeof mod.fullscreenRequest === 'function' && typeof mod.fullscreenExit === 'function') {
  let called = 0
  const el = { requestFullscreen() { called++; return Promise.resolve() } }
  eq(mod.fullscreenRequest(el), true, 'fullscreenRequest enters on a user-gesture element')
  eq(called, 1, 'fullscreenRequest called exactly once')
  eq(mod.fullscreenRequest({}), false, 'fullscreenRequest refuses a node without the API')
  eq(mod.fullscreenRequest(null), false, 'fullscreenRequest refuses null')
  let exited = 0
  const doc = { exitFullscreen() { exited++; return Promise.resolve() } }
  eq(mod.fullscreenExit(doc), true, 'fullscreenExit uses the document door')
  eq(exited, 1, 'fullscreenExit called exactly once')
  eq(mod.fullscreenExit({}), false, 'fullscreenExit refuses a doc without the API')
}

// ---------------------------------- theater automation: an overlay, not a dock resize
// The host exposes only revealPane/removePane/undismissPane/paneVisibility, so a docked
// rail cannot be grown. Theater pins the pane's own root to the window instead — the same
// mechanic from either placement — and restores the exact inline style it borrowed.
const TC = mod.THEATER_CFG
ok(TC && Object.isFrozen(TC), 'THEATER_CFG must be a frozen named-tunable object')
ok(TC && Number.isFinite(TC.inset) && TC.inset > 0, 'the window inset must be a named numeric tunable')
ok(TC && Number.isFinite(TC.z) && TC.z > 0, 'the overlay stacking order must be a named number')

const TD = mod.theaterDecision
eq(TD(null), 'off', 'null state -> off')
eq(TD({ enabled: true, hasMedia: false, busy: true }), 'off', 'no media -> off (nothing to show)')
eq(TD({ enabled: false, hasMedia: true, busy: true }), 'normal', 'switch off -> normal (no overlay)')
eq(TD({ enabled: true, hasMedia: true, busy: true }), 'theater', 'switch on + busy -> theater')
eq(TD({ enabled: false, hasMedia: true, busy: true, manual: true }), 'theater', 'the footer toggle enters without the switch')
eq(TD({ enabled: true, hasMedia: true, busy: true, manual: false }), 'normal', 'toggle off beats the switch for this turn')
eq(TD({ enabled: true, hasMedia: true, busy: false }), 'normal', 'idle -> normal (shrink back)')
eq(TD({ enabled: true, hasMedia: true, busy: true, floating: false }), 'theater', 'docked counts too: the overlay is placement-free')

// plan is CHANGE-DRIVEN: zero DOM work on every unchanged tick
const AB = { enabled: true, hasMedia: true, busy: true, persist: 'agent' }
let pl = mod.theaterPlan(null, AB)
eq(pl.mode, 'theater', 'first busy tick plans theater')
eq(pl.changed, true, 'first tick must write once')
eq(pl.own, true, 'theater plan owns the overlay')
eq(mod.theaterPlan(pl, AB).changed, false, 'identical tick -> ZERO DOM work (optimized)')
eq(mod.theaterPlan(pl, { ...AB, viewport: { width: 1280, height: 720 } }).changed, false, 'a viewport change needs no rewrite: the overlay is inset-based')
const idl = mod.theaterPlan(pl, { ...AB, busy: false })
eq(idl.mode, 'normal', 'idle plan -> normal')
eq(idl.changed, true, 'leaving theater restores exactly once')
eq(mod.theaterPlan(idl, { ...AB, busy: false }).changed, false, 'staying idle -> ZERO work')
const latch = mod.theaterPlan(pl, { ...AB, busy: false, persist: 'window' })
eq(latch.own, true, 'persist=window holds theater through an idle tick')
eq(latch.changed, false, 'a latched tick repaints nothing')
eq(mod.theaterPlan(pl, { ...AB, busy: false, persist: 'window', manual: false }).own, false, 'a manual exit ends the latch')
eq(mod.theaterPlan(null, { ...AB, busy: false, persist: 'window' }).own, false, 'a latch never opens from a cold idle tick')
eq(mod.theaterPlan(pl, { ...AB, busy: false, persist: 'window', hasMedia: false }).own, false, 'a latch needs media to hold')

// applyTheaterPlan: overlay in, verbatim restore out
const AP = mod.applyTheaterPlan
const fr = { style: {} }
eq(AP(pl, fr), true, 'theater plan pins the player')
eq(fr.style.position, 'fixed', 'the player is pinned to the window, not resized inside the layout')
eq(fr.style.left, TC.inset + 'px', 'left edge inset by the named value')
eq(fr.style.right, TC.inset + 'px', 'right edge inset too, so width follows the window')
eq(fr.style.top, TC.inset + TC.rail + 'px', 'top edge clears the rail, which owns its own strip')
eq(fr.style.bottom, TC.inset + 'px', 'bottom edge inset: height follows the window')
eq(fr.style.zIndex, String(TC.z), 'the overlay sits above the app chrome it covers')
eq(fr.style.width, 'auto', 'an inline height:100% would push the footer past the window bottom — width goes auto too')
eq(fr.style.height, 'auto', 'height goes auto so the inset box decides the size')
eq(AP(mod.theaterPlan(pl, AB), fr), false, 'unchanged plan on the pinned surface -> no DOM write at all')
// flipping placement hands theater a fresh surface: the same plan must re-target it, or the
// overlay silently stays on the evicted element and the card is never pinned.
const frR = { style: {} }
eq(AP(mod.theaterPlan(pl, AB), frR), true, 'an owned plan re-aims at a newly mounted surface')
eq(AP(mod.theaterPlan(pl, AB), frR), false, 'the same surface twice still writes nothing')
eq(AP(pl, null), false, 'no element -> named refusal')
eq(AP(pl, {}), false, 'element without style -> refusal')
const fr2 = { style: { position: 'absolute', width: '480px', height: '460px', left: '12px', top: '34px', zIndex: '3' } }
fr2.style.removeProperty = function (k) { delete this[k] }
eq(AP(pl, fr2), true, 'enter')
eq(fr2.style.position, 'fixed', 'enter overrides the pane positioning')
const out = mod.theaterPlan(pl, { ...AB, busy: false })
eq(AP(out, fr2), true, 'exit')
eq([fr2.style.position, fr2.style.left, fr2.style.top, fr2.style.zIndex].join('|'), 'absolute|12px|34px|3', 'exit restores the exact inline style it borrowed')
eq(fr2.style.right, undefined, 'styles that did not exist are removed, not left as empty strings')
eq(fr2.style.width, '480px', 'the pane keeps its own inline width after theater')
eq(AP(out, fr2), false, 'a second exit is a no-op (no stale restore)')
// A REAL CSSStyleDeclaration lowercases removeProperty's argument: 'zIndex' is not a property
// name, so the call does nothing. The plain-object stub above deletes any key, which is why a
// clean exit looked proven while the live pane kept z-index 2147482000 and the 10px radius.
function realStyle(init) {
  const kebab = (k) => String(k).replace(/[A-Z]/g, (c) => '-' + c.toLowerCase())
  const map = new Map(Object.entries(init || {}).map(([k, v]) => [kebab(k), v]))
  const api = {
    removeProperty(k) { const kk = String(k).toLowerCase(); if (map.has(kk)) map.delete(kk); return '' },
    setProperty(k, v) { map.set(kebab(k), String(v)) },
  }
  return new Proxy(api, {
    get(t, p) { if (p in t) return t[p]; return map.has(kebab(p)) ? map.get(kebab(p)) : '' },
    set(t, p, v) { if (p in t) { t[p] = v; return true } map.set(kebab(p), String(v)); return true },
  })
}
const frReal = { style: realStyle({ zIndex: '3' }) }
eq(AP(pl, frReal), true, 'enter on a spec-faithful style object')
eq(AP(out, frReal), true, 'exit on a spec-faithful style object')
eq(frReal.style.zIndex, '3', 'the z-index theater added is gone after exit (removeProperty needs a CSS name)')
eq(frReal.style.borderRadius, '', 'the radius theater added is gone after exit')
eq(frReal.style.position, '', 'the position theater added is gone after exit')
// A dragged size is a real rect: width/height explicit, right/bottom must let go or the box is
// over-constrained and the width silently loses to the insets. Absent rect keeps the fill behavior.
const frBox = { style: realStyle({ zIndex: '3' }) }
eq(AP(pl, frBox, null, { w: 900, h: 700 }), true, 'enter with a dragged theater size')
eq(frBox.style.width, '900px', 'the dragged width is used')
eq(frBox.style.height, '700px', 'the dragged height is used')
eq(frBox.style.right, 'auto', 'right must not over-constrain a sized overlay')
eq(frBox.style.left, TC.inset + 'px', 'a sized overlay still sits at the inset')
eq(frBox.style.top, (TC.inset + TC.rail) + 'px', 'a sized overlay also clears the rail strip')
eq(AP(out, frBox), true, 'exit a sized overlay')
eq(frBox.style.width, '', 'exit removes the dragged width')
// The completion toast's one rule, in code the gate can actually execute.
eq(mod.snapPlan(true), { exit: true, collapse: false }, 'in theater, a toast click restores the player instead of collapsing it')
eq(mod.snapPlan(false), { exit: false, collapse: true }, 'outside theater, a toast click still collapses the dock as before')

// capability detection: trust only real atoms, never assume a door
const AC = mod.automationCaps
ok(typeof AC === 'function', 'automationCaps must be exported')
const FAKE = { get: () => false, subscribe: () => () => {} }
const cFull = AC({ state: { busy: FAKE, viewport: FAKE, focusedStoredSessionId: FAKE, busyBySession: FAKE }, notify() {}, openSession() {} }, { onEvent() {} })
eq(cFull.busy, true, 'caps: busy atom detected')
eq(cFull.viewport, true, 'caps: viewport atom detected')
eq(cFull.onEvent, true, 'caps: onEvent door detected')
eq(cFull.notify, true, 'caps: notify door detected')
eq(cFull.openSession, true, 'caps: openSession door detected')
const cOld = AC({}, {})
eq(cOld.busy, false, 'caps: older desktop -> busy false (named refusal, no crash)')
eq(cOld.viewport, false, 'caps: older desktop -> viewport false')
eq(cOld.focusedSession, false, 'caps: older desktop -> focusedSession false')
const cFake = AC({ state: { busy: {}, viewport: 'x' } }, {})
eq(cFake.busy, false, 'caps: non-atom busy must NOT be trusted')
eq(cFake.viewport, false, 'caps: non-atom viewport must NOT be trusted')
const cHalf = AC({ state: { busy: { get: () => false }, viewport: { get: () => 0, subscribe: 'nope' } } }, {})
eq(cHalf.busy, false, 'caps: get-only object is NOT an atom')
eq(cHalf.viewport, false, 'caps: subscribe must be a function, not merely present')
const cReq = AC({ state: { busy: FAKE, viewport: FAKE, focusedStoredSessionId: FAKE, focusedSessionId: FAKE, busyBySession: FAKE }, request() {}, notify() {}, openSession() {} }, { onEvent() {} })
eq(cReq.request, true, 'caps: host.request door detected')
eq(cReq.focusedRuntime, true, 'caps: focusedSessionId atom detected')
const cNoReq = AC({ state: { busy: FAKE, viewport: FAKE, focusedStoredSessionId: FAKE, busyBySession: FAKE }, notify() {}, openSession() {} }, { onEvent() {} })
eq(cNoReq.request, false, 'caps: missing host.request is a named refusal, not a guess')

// ---- part 5: completion decision (pure). Terminal pair is source-verified. ----
const CDEC = (ev, extra) => mod.completionDecision(ev, Object.assign({ enabled: true,
  mapping: { rt1: 'stored-1', rt2: 'stored-2' }, focusedRuntime: null, focusedStored: 'stored-1' }, extra || {}))
eq(mod.TERMINAL_EVENTS, ['message.complete', 'error'], 'terminal event pair must match shipped source')
ok(Object.isFrozen(mod.TERMINAL_EVENTS), 'terminal event pair must be frozen')
eq(CDEC({ type: 'message.complete', session_id: 'rt2' }), { show: true, reason: 'other-chat', storedId: 'stored-2' }, 'other-chat completion shows with the STORED id')
eq(CDEC({ type: 'error', session_id: 'rt2' }).show, true, 'error frame is terminal too')
eq(CDEC({ type: 'message.delta', session_id: 'rt2' }).reason, 'not-terminal', 'non-terminal frame ignored')
eq(CDEC({ type: 'message.complete', session_id: 'rt2', replayed: true }).reason, 'replayed', 'reconnect replay is not fresh work')
eq(CDEC({ type: 'message.complete', session_id: 'rtZ' }).reason, 'unmapped', 'unmapped runtime id -> named refusal, never a fabricated snap')
eq(CDEC({ type: 'message.complete', session_id: '' }).reason, 'no-session', 'missing session id refused')
eq(CDEC({ type: 'message.complete', session_id: 'rt2' }, { focusedRuntime: 'rt2' }).reason, 'focused', 'focused runtime chat never toasts')
eq(CDEC({ type: 'message.complete', session_id: 'rt2' }, { focusedStored: 'stored-2' }).show, false, 'focused stored chat never toasts')
eq(CDEC({ type: 'message.complete', session_id: 'rt2' }, { enabled: false }).reason, 'disabled', 'opt-in off -> no toast')
eq(mod.SETTINGS_DEFAULTS.completionToasts, false, 'completion toasts must be opt-in, off by default')
eq(mod.settingsWithDefaults({ completionToasts: 'yes' }).completionToasts, false, 'garbage stored completionToasts must fall back to off')

// ---- part 1: picked-chats selection (durable stored ids, fail-open) ----------
const SDEC = (scope, focused, list) => mod.sessionDecision(scope, focused, list)
eq(SDEC('all', 'stored-2', []), { show: true, reason: 'all' }, 'scope=all shows the dock in every chat')
eq(SDEC('picked', 'stored-2', ['stored-2']), { show: true, reason: 'picked' }, 'a picked chat shows the dock')
const blocked = SDEC('picked', 'stored-9', ['stored-2'])
eq(blocked.show, false, 'an unpicked chat is gated')
eq(blocked.reason, 'not-picked', 'the gate names the refusal')
eq(blocked.storedId, 'stored-9', 'the gate carries the durable id for Show here')
eq(SDEC('picked', null, ['stored-2']), { show: true, reason: 'no-focused' }, 'no focused id fails OPEN (older Desktop)')
eq(SDEC('picked', '', ['stored-2']).reason, 'no-focused', 'an empty focused id fails open')
eq(SDEC('picked', 'stored-9', null).show, false, 'a non-array picked list is empty, not a crash')
eq(SDEC('bogus', 'stored-9', []), { show: true, reason: 'all' }, 'an unknown scope fails open to all')
eq(mod.SETTINGS_DEFAULTS.sessionScope, 'all', 'picked chats must be OPT-IN (default all)')
eq(mod.settingsWithDefaults({ sessionScope: 'picked' }).sessionScope, 'picked', 'valid sessionScope survives normalization')
eq(mod.settingsWithDefaults({ sessionScope: 'bogus' }).sessionScope, 'all', 'invalid sessionScope falls back to all')
eq(mod.settingsWithDefaults({}).sessionScope, 'all', 'missing sessionScope defaults to all')

// ------------------ theater persistence across chat switches (MAGIC part 1) ----
const TP = mod.THEATER_PERSIST
ok(TP && Object.isFrozen(TP), 'THEATER_PERSIST must be a frozen named config')
eq(TP.agent, 'agent', 'named persist value: follow the agent')
eq(TP.window, 'window', 'named persist value: stay for the window')
eq(mod.SETTINGS_DEFAULTS.theaterPersist, 'agent', 'persist defaults to agent - no behavior change for existing users')
eq(mod.settingsWithDefaults({ theaterPersist: 'window' }).theaterPersist, 'window', 'valid persist value survives normalization')
eq(mod.settingsWithDefaults({ theaterPersist: 'bogus' }).theaterPersist, 'agent', 'invalid persist value falls back to the default')
eq(mod.settingsWithDefaults({}).theaterPersist, 'agent', 'missing persist value is defaulted')

const PW = { ...AB, persist: 'window' }
let pq = mod.theaterPlan(null, PW)
eq(pq.mode, 'theater', 'persist scenario opens on busy')
const held = mod.theaterPlan(pq, { ...PW, busy: false })
eq(held.mode, 'theater', 'window persist keeps theater after the agent stops (chat switch)')
eq(held.own, true, 'latched plan still owns the overlay')
eq(held.changed, false, 'latch does ZERO DOM work when nothing changed')
eq(mod.theaterPlan(pq, { ...AB, busy: false }).mode, 'normal', 'agent persist shrinks back on idle')
eq(mod.theaterPlan(pq, { ...PW, busy: false, floating: false }).mode, 'theater', 'docking cannot end theater: the overlay is placement-free')
eq(mod.theaterPlan(pq, { ...PW, busy: false, enabled: false }).mode, 'normal', 'turning the switch off unlatches theater')
eq(mod.theaterPlan(pq, { ...PW, busy: false, hasMedia: false }).mode, 'normal', 'clearing media unlatches theater')
const noVp = mod.theaterPlan(pq, { ...PW, busy: false, viewport: null })
eq(noVp.own, true, 'an unresolved viewport does not block the overlay (inset-derived)')
eq(noVp.changed, false, 'and an unresolved viewport repaints nothing')
eq(mod.theaterPlan(null, { ...PW, busy: false }).mode, 'normal', 'persist must NOT open theater from cold idle')
eq(mod.theaterPlan(pq, { ...PW, busy: false, viewport: { width: 1280, height: 720 } }).changed, false, 'a viewport change repaints nothing: the overlay is inset-derived')

// ------------------------------------------------------- registration + rendering
const A = makeCtx({})
const plugin = mod.default
ok(plugin && typeof plugin.register === 'function', 'no register()')
ok(plugin && plugin.id === 'media-dock', 'plugin id must be media-dock')
ok(plugin && plugin.defaultEnabled === false, 'plugin must be opt-in (defaultEnabled false)')
plugin.register(A.ctx)

const panes = A.registered.filter((d) => d && d.area === 'panes')
ok(panes.length >= 1, 'register() published no pane')
ok(panes[0].enabled === false, 'plugin load must NOT auto-open a pane')
ok(panes[0].data && panes[0].data.uncloseable === true, 'docked pane must be uncloseable')
// Two SURFACES, at most one LIVE. The docked pane and the floating card are separate
// contribution ids because the shipping build has no `host.removePane`: a single id could not
// evict the surface it left behind, so detaching left the old pane on screen (or killed it).
// Neither may be enabled at load; exactly one is enabled once the user opens one.
const PANES_AREA = 'panes'
const paneRegs = A.registered.filter((d) => d.area === 'panes' && typeof d.render === 'function')
eq(paneRegs.length, 2, 'one renderer per surface: docked card + floating card')
ok(paneRegs.every((d) => d.enabled === false), 'plugin load must NOT auto-open a surface')
ok(!A.registered.some((d) => d.area === 'routes'), 'no route page may be registered')
ok(!A.registered.some((d) => d.area === 'sidebar.nav'), 'no sidebar page may be registered')
ok(A.registered.some((d) => /status/i.test(d.area || '')), 'no status chip registered')
const palette = A.registered.filter((d) => d.area === 'palette')
ok(palette.length === 2, 'palette is Open and Close only, not every transport command')
ok(palette.some((d) => d.id === 'open' && d.data && d.data.label === 'Media Dock'), 'palette must offer Open')
ok(palette.some((d) => d.id === 'close' && d.data && /Close/.test(String(d.data.label || ''))), 'palette must offer Close')
ok(!palette.some((d) => /Play|Previous|Next|Focus|Fullscreen|Cycle|Pin/.test(String(d.data && d.data.label || ''))), 'transport commands must not clutter the palette')
ok(A.registered.filter((d) => /keybind/i.test(d.area || '')).length >= 4, 'keybinds missing (immersive/fullscreen)')
ok(A.listeners.some((l) => l.type === 'offline') && A.listeners.some((l) => l.type === 'online'), 'offline/online must be tracked via ctx.addEventListener')
ok(A.listeners.some((l) => l.type === 'keydown'), 'Escape must be tracked via ctx.addEventListener')
ok(A.listeners.some((l) => l.type === 'pointermove') && A.listeners.some((l) => l.type === 'pointerup') && A.listeners.some((l) => l.type === 'pointercancel'), 'resize pointer lifecycle must be tracked (move/up/CANCEL)')
ok(A.disposers.length >= 1, 'no onDispose teardown registered')
// Theater pins the dock's own root, so a grip must resize THAT element (the card wrapper it used
// to target is no longer what moves) and the result must survive into the next theater entry.
{
  const pinned = { style: {}, getBoundingClientRect() { return { width: 900, height: 700, left: 24, top: 24, right: 924, bottom: 724 } }, closest() { return null } }
  eq(mod.startResize('corner', { clientX: 924, clientY: 724, preventDefault() {}, stopPropagation() {} }, pinned, true), true,
    'a theater grip resizes the pinned surface even with no floating wrapper')
  const mv = A.listeners.filter((l) => l.type === 'pointermove').pop()
  if (mv) mv.fn({ clientX: 1024, clientY: 784 })
  ok(parseInt(pinned.style.width, 10) > 900, 'dragging the corner outward widens the pinned player: ' + pinned.style.width)
  ok(parseInt(pinned.style.height, 10) > 700, 'and its height: ' + pinned.style.height)
  const up = A.listeners.filter((l) => l.type === 'pointerup').pop()
  if (up) up.fn({})
  const saved = A.storage.get('theaterSize')
  ok(!!saved && saved.w > 900 && saved.h > 700, 'the dragged theater size is saved for the next entry: ' + JSON.stringify(saved))
  const next = { el: pinned, keys: [] }
  ok(!!saved, 'theaterSize must be readable back')
  eq(mod.readTheaterSize ? mod.readTheaterSize(A.ctx.storage).w : 0, saved && saved.w, 'the saved theater size reads back on start')
  // The live failure: the pointer crossed from our 8px strip into the guest, which is its own
  // process, so the drag stopped. Capture plus a shield over the card keeps every move here.
  const seen = { id: null, setPointerCapture(id) { this.id = id } }
  const makeEl = () => ({ style: {}, setAttribute() {}, parentNode: null })
  const card2 = { ownerDocument: { createElement: makeEl }, style: {}, getBoundingClientRect: () => ({ width: 900, height: 700, left: 24, top: 24, right: 924, bottom: 724 }), closest: () => null,
    appendChild(n) { n.parentNode = this; this.kids = (this.kids || []).concat(n); return n }, removeChild(n) { n.parentNode = null; this.kids = (this.kids || []).filter((k) => k !== n) } }
  eq(mod.startResize('x', { clientX: 30, clientY: 300, pointerId: 11, target: seen }, card2, true), true, 'a side grip starts a theater drag')
  eq(seen.id, 11, 'the theater grip must capture the pointer')
  ok((card2.kids || []).some((k) => k.style && /z-index:60/.test(String(k.style.cssText))), 'a shield must cover the guest while dragging')
  const mv2 = A.listeners.filter((l) => l.type === 'pointermove').pop()
  if (mv2) mv2.fn({ clientX: 130, clientY: 300 })
  ok(parseInt(card2.style.width, 10) > 900, 'a side drag widens the player: ' + card2.style.width)
  const up2 = A.listeners.filter((l) => l.type === 'pointerup').pop()
  if (up2) up2.fn({})
  ok(!(card2.kids || []).length, 'the shield must be removed on release')
}
// Theater flips a docked pane to a floating card, so the host re-creates the guest. `src` is the
// URL our last explicit load used; in-page navigation only moves play.pageUrl.
{
  const S = makeCtx({ session: { raw: 'https://www.youtube.com/', floating: false } })
  const m = await fresh(source)
  m.default.register(S.ctx)
  const pane = S.registered.find((d) => d.area === 'panes' && typeof d.render === 'function')
  const wv = find(pane.render(), (n) => n.type === 'webview')
  ok(wv && wv.props && typeof wv.props.ref === 'function', 'the guest must expose its ref')
  const mk = () => { const h = {}; return { src: '', handlers: h, addEventListener(t, fn) { h[t] = fn }, removeEventListener() {}, getURL() { return 'https://www.youtube.com/' }, setAudioMuted() {}, executeJavaScript() { return Promise.resolve() }, blur() {} } }
  if (wv) {
    const a = mk()
    wv.props.ref(a)
    ok(typeof a.handlers['did-navigate'] === 'function', 'the guest must track navigation')
    if (a.handlers['did-navigate']) a.handlers['did-navigate']({ url: 'https://www.youtube.com/watch?v=Gro5z03a_Qw' })
    const b = mk()
    wv.props.ref(b)
    await new Promise((r) => setTimeout(r, 30))
    eq(b.src, 'https://www.youtube.com/watch?v=Gro5z03a_Qw', 'a re-created guest must return to the page the user was on')
  }
}
const settingsPage = A.registered.find((d) => d.__settings)
ok(settingsPage, 'no settings page registered')
ok(settingsPage && Array.isArray(settingsPage.children) && settingsPage.children.length >= 2, 'settings page must have sub-pages')
const theaterChild = settingsPage.children.find((c) => c.id === 'theater')
const theaterTree = theaterChild && typeof theaterChild.render === 'function' ? theaterChild.render() : null
ok(theaterTree && find(theaterTree, (n) => n.props && /Stay open/.test(String(n.props['aria-label'] || ''))), 'Theater settings must offer the Stay open choice')
ok(A.storage.has('size'), 'initial card size must be persisted for the next mount')
const genTree = settingsPage && typeof settingsPage.render === 'function' ? settingsPage.render() : null
ok(find(genTree, (n) => n.props && /Other-chat completions/.test(String(n.props['aria-label'] || ''))), 'General settings must offer the Other-chat completions switch')
const sessionsChild = settingsPage.children.find((c) => c.id === 'sessions')
ok(sessionsChild, 'Sessions settings sub-page missing')
const sessionsTree = sessionsChild && typeof sessionsChild.render === 'function' ? sessionsChild.render() : null
ok(find(sessionsTree, (n) => n.props && /Show in/.test(String(n.props['aria-label'] || ''))), 'Sessions settings must offer the Show in choice')
ok(!A.registered.some((d) => d.area === 'palette' && /Pin\/Unpin/.test(String(d.data && d.data.label || ''))), 'Pin/Unpin must not be a palette command')
ok(A.registered.some((d) => /keybind/i.test(d.area || '') && /Pin\/Unpin/.test(String(d.data && d.data.label || ''))), 'Pin/Unpin stays a keybind')

const trees = []
const paneTrees = []
for (const d of A.registered) {
  if (typeof d.render === 'function') {
    try { const t = d.render(); trees.push(t); if (d.area === 'panes') paneTrees.push(t) }
    catch (err) { failures.push('render ' + d.id + ' threw: ' + (err && err.message)) }
  }
  if (d.__settings && Array.isArray(d.children)) for (const c of d.children) {
    if (typeof c.render === 'function') {
      try { trees.push(c.render()) } catch (err) { failures.push('settings ' + c.id + ' threw: ' + (err && err.message)) }
    }
  }
}
for (const d of A.registered) if (d.data && typeof d.data.run === 'function') {
  try { d.data.run() } catch (err) { failures.push('run ' + d.id + ' threw: ' + (err && err.message)) }
}
const clicked = clickAll(trees, 'default')
ok(trees.length >= 4, 'too few contribution trees rendered')
ok(A.storage.has('settings'), 'settings changes must persist through ctx.storage')

const paneTree = paneTrees[0]
ok(find(paneTree, (n) => n.props && n.props.role === 'tablist'), 'queue must render as a tablist')
{
  const pin = { id: 'example.com|https://example.com/a', url: 'https://example.com/a', title: 'clip', host: 'example.com', kind: 'page', addedAt: 0 }
  const S = makeCtx({ pins: [pin], session: { raw: '', floating: false } })
  const m = await fresh(source)
  m.default.register(S.ctx)
  const pane = S.registered.find((d) => d.area === 'panes' && typeof d.render === 'function')
  const queued = pane.render()
  const row = find(queued, (n) => n.props && n.props.role === 'tab' && n.props['aria-selected'] === false)
  ok(!!row, 'a saved pin must render as a queue row')
  // The current item is already queued: the Add control must SAY so instead of
  // looking dead (that silence is what read as a broken button).
  ok(!!find(queued, (n) => n.props && n.props.title === 'Add current URL to the queue'), 'Add current must be offered while the URL is not queued')
  const rm = find(queued, (n) => n.props && n.props.title === 'Remove' && typeof n.props.onClick === 'function')
  ok(!!rm, 'each queue row must be removable from the queue itself')
  let stopped = false
  if (rm) rm.props.onClick({ stopPropagation() { stopped = true }, preventDefault() {} })
  ok(stopped, 'removing a row must not also open it')
  const after = pane.render()
  ok(!find(after, (n) => n.props && n.props.role === 'tab'), 'removing a row must drop that pin')
}
{
  // Load the pinned URL itself: Add current must flip to "In queue", not stay a
  // button that swallows clicks because upsert is a no-op for a row already there.
  const pin = { id: 'example.com|https://example.com/a', url: 'https://example.com/a', title: 'clip', host: 'example.com', kind: 'page', addedAt: 0 }
  const S = makeCtx({ pins: [pin], session: { raw: pin.url, floating: false } })
  const m = await fresh(source)
  m.default.register(S.ctx)
  const pane = S.registered.find((d) => d.area === 'panes' && typeof d.render === 'function')
  const tree = pane.render()
  ok(!!find(tree, (n) => n.props && n.props.title === 'Already in the queue'), 'Add current must read In queue when the current URL is already parked')
  ok(!find(tree, (n) => n.props && n.props.title === 'Add current URL to the queue'), 'the add affordance must not claim the URL is missing while it is queued')
}
{
  // While the URL is queued the control states a fact. Clicking it must not reorder the
  // list under the pointer: row order is play order, and a mis-click would rewrite it.
  const mk = (u) => ({ id: u, url: u, title: u, host: 'example.com', kind: 'page', addedAt: 0 })
  const seeds = [mk('https://example.com/a'), mk('https://example.com/b'), mk('https://example.com/c')]
  const S = makeCtx({ pins: seeds, session: { raw: 'https://example.com/b', floating: false } })
  const m = await fresh(source)
  m.default.register(S.ctx)
  const pane = S.registered.find((d) => d.area === 'panes' && typeof d.render === 'function')
  const add = find(pane.render(), (n) => n.props && n.props.title === 'Already in the queue' && typeof n.props.onClick === 'function')
  ok(!!add, 'the queued state must still render one add control')
  if (add) add.props.onClick(EV)
  eq((S.storage.get('pins') || []).map((p) => p.url).join('|'), seeds.map((p) => p.url).join('|'),
    'clicking In queue must not move an existing row')
}
{
  // Clear / Shuffle: the two bulk queue actions, driven through their real buttons.
  const mk = (u) => ({ id: u, url: u, title: u, host: 'example.com', kind: 'page', addedAt: 0 })
  const seeds = [mk('https://example.com/a'), mk('https://example.com/b'), mk('https://example.com/c')]
  const S = makeCtx({ pins: seeds, session: { raw: '', floating: false } })
  const m = await fresh(source)
  m.default.register(S.ctx)
  const pane = S.registered.find((d) => d.area === 'panes' && typeof d.render === 'function')
  const btn = (label) => find(pane.render(), (n) => n.props && n.props.title === label && typeof n.props.onClick === 'function')
  const clear = btn('Empty the queue'), shuffle = btn('Shuffle the queue')
  ok(!!clear && !!shuffle, 'the queue must offer labelled Clear and Shuffle controls')
  // Math.random pinned high makes Fisher-Yates the identity permutation, which is the
  // case a naive shuffle ships: the button looks dead whenever the result matches.
  const realRandom = Math.random
  Math.random = () => 0.999
  if (shuffle) shuffle.props.onClick(EV)
  Math.random = realRandom
  const order = (S.storage.get('pins') || []).map((p) => p.url)
  ok(order.length === 3 && seeds.every((p) => order.filter((u) => u === p.url).length === 1),
    'Shuffle must keep every queued url exactly once')
  ok(order.join('|') !== seeds.map((p) => p.url).join('|'),
    'Shuffle must move at least one row: an identity permutation is a dead control')
  if (clear) clear.props.onClick(EV)
  eq((S.storage.get('pins') || []).length, 0, 'Clear must empty the queue')
}
{
  // The shelf: saved links live beside the queue, not in it, and survive a remount.
  const S = makeCtx({ pins: [], session: { raw: 'https://example.com/watch', floating: false } })
  const m = await fresh(source)
  m.default.register(S.ctx)
  const pane = S.registered.find((d) => d.area === 'panes' && typeof d.render === 'function')
  const btn = (label) => find(pane.render(), (n) => n.props && n.props.title === label && typeof n.props.onClick === 'function')
  const toSaved = btn('Show saved')
  ok(!!toSaved, 'the list must offer a Saved view beside the queue')
  if (toSaved) toSaved.props.onClick(EV)
  const save = btn('Save current URL to the shelf')
  ok(!!save, 'the Saved view must offer Save current, and it must be labelled in words')
  if (save) save.props.onClick(EV)
  const stored = S.storage.get('shelf') || []
  eq(stored.length, 1, 'Save current must put the open page on the shelf')
  eq(stored[0] && stored[0].url, 'https://example.com/watch', 'the shelf stores the page URL')
  eq((S.storage.get('pins') || []).length, 0, 'saving to the shelf must not touch the play queue')
}
{
  // A stored shelf link renders, opens on click, and removes without opening.
  const row = { id: 'example.com|https://example.com/kept', url: 'https://example.com/kept', title: 'kept', host: 'example.com', kind: 'page', addedAt: 0 }
  const S = makeCtx({ pins: [], shelf: [row], session: { raw: '', floating: false } })
  const m = await fresh(source)
  m.default.register(S.ctx)
  const pane = S.registered.find((d) => d.area === 'panes' && typeof d.render === 'function')
  const toSaved = find(pane.render(), (n) => n.props && n.props.title === 'Show saved' && typeof n.props.onClick === 'function')
  if (toSaved) toSaved.props.onClick(EV)
  const tab = find(pane.render(), (n) => n.props && n.props.role === 'tab' && n.props['aria-selected'] === false)
  ok(!!tab, 'a stored shelf link must render as a row')
  if (tab) tab.props.onClick(EV)
  ok(S.storage.get('session') && S.storage.get('session').raw === 'https://example.com/kept', 'clicking a saved link opens it')
  const rm = find(pane.render(), (n) => n.props && n.props.title === 'Remove' && typeof n.props.onClick === 'function')
  ok(!!rm, 'a saved link must be removable from the shelf itself')
  let opened = false
  const spy = { stopPropagation() { opened = true }, preventDefault() {} }
  if (rm) rm.props.onClick(spy)
  ok(opened, 'removing a saved link must not also open it')
  eq((S.storage.get('shelf') || []).length, 0, 'removing a saved link drops it from the shelf')
}
{
  // Resume points: stored locally, dropped when finished, bounded, and seeked once.
  const S = makeCtx({ session: { raw: '', floating: false } })
  const m = await fresh(source)
  m.default.register(S.ctx)
  m.remember('https://example.com/x', 12.4, 100)
  eq(S.storage.get('progress')['https://example.com/x'], 12, 'a watched position is stored on this machine')
  m.remember('https://example.com/x', 98, 100)
  ok(!(Number(S.storage.get('progress')['https://example.com/x']) > 0), 'a finished item must not resume at the end')
  m.remember('https://example.com/y', 30, 100)
  const node = { currentTime: 0 }
  m.resumeAt(node, 'https://example.com/y', 100)
  eq(node.currentTime, 30, 'reopening a url seeks back to the stored position')
  const started = { currentTime: 9 }
  m.resumeAt(started, 'https://example.com/y', 100)
  eq(started.currentTime, 9, 'a player that already started must not be yanked back')
  for (let i = 0; i < 80; i++) m.remember('https://example.com/p' + i, 10 + i, 100)
  ok(Object.keys(S.storage.get('progress')).length <= 60, 'resume points must stay bounded')
}
{
  const S = makeCtx({
    pins: [
      { url: 'https://example.com/a.mp4', title: 'a' },
      { url: 'https://example.com/b.mp4', title: 'b' },
    ],
    session: { raw: '', floating: false },
  })
  const m = await fresh(source)
  m.default.register(S.ctx)
  const pane = S.registered.find((d) => d.area === 'panes' && typeof d.render === 'function')
  const queued = pane.render()
  const rows = []
  walk(queued, (n) => { if (n.props && n.props.role === 'tab') rows.push(n) }, 0, new Set())
  eq(rows.length, 2, 'two saved urls render as two rows')
  const later = rows[1] && find(rows[1], (n) => n.props && n.props['aria-label'] === 'Move earlier' && typeof n.props.onClick === 'function')
  ok(!!later, 'each row can move earlier in the play order')
  let stopped = false
  if (later) later.props.onClick({ stopPropagation() { stopped = true }, preventDefault() {} })
  ok(stopped, 'reordering a row must not also open it')
  const after = []
  walk(pane.render(), (n) => { if (n.props && n.props.role === 'tab') after.push(n) }, 0, new Set())
  eq(after.length, 2, 'reorder must keep both rows')
  ok(after[0] && after[0].props && after[0].props['aria-selected'] === false, 'the moved row is still a row')
  const titles = after.map((n) => {
    const label = find(n, (c) => c.props && typeof c.props.children === 'string' && c.props.children !== '×' && c.props.children !== '↑' && c.props.children !== '↓')
    return label && label.props.children
  })
  eq(titles.join(','), 'b,a', 'move earlier changes play order, not just the chrome')
}
{
  const S = makeCtx({
    pins: [{ url: 'https://example.com/a.mp4', title: 'a' }],
    settings: { autoplay: false },
    session: { raw: '', floating: false },
  })
  const m = await fresh(source)
  m.default.register(S.ctx)
  const pane = S.registered.find((d) => d.area === 'panes' && typeof d.render === 'function')
  const row = find(pane.render(), (n) => n.props && n.props.role === 'tab')
  ok(!!row, 'a saved pin renders as a queue row')
  if (row) row.props.onClick()
  ok(S.storage.get('session') && S.storage.get('session').raw === 'https://example.com/a.mp4', 'clicking a queue row plays it')
  const media = find(pane.render(), (n) => n.type === 'video' || n.type === 'audio')
  ok(!!media && media.props && media.props.autoPlay === true, 'a queue row click must autoplay the file it opens, like Next does')
}
{
  const S = makeCtx({
    pins: [
      { url: 'https://example.com/a.mp4', title: 'a' },
      { url: 'https://example.com/b.mp4', title: 'b' },
    ],
    settings: { autoAdvance: false },
    session: { raw: 'https://example.com/a.mp4', floating: false },
  })
  const m = await fresh(source)
  m.default.register(S.ctx)
  const same = (id) => {
    const key = S.registered.find((d) => d.id === 'key-' + id)
    const paletteTwin = S.registered.find((d) => d.area === 'palette' && d.id === id)
    return !!(key && key.data && typeof key.data.run === 'function' && !paletteTwin)
  }
  ok(same('next'), 'Next is a keybind, not a second palette command')
  ok(same('prev'), 'Previous is a keybind, not a second palette command')
  ok(same('focus'), 'Focus is a keybind, not a second palette command')
  const pane = S.registered.find((d) => d.area === 'panes' && typeof d.render === 'function')
  const onScreen = find(pane.render(), (n) => n.props && n.props['aria-label'] === 'Next in queue' && typeof n.props.onClick === 'function')
  ok(!!onScreen, 'the player must show a Next control')
  if (onScreen) onScreen.props.onClick(EV)
  ok(S.storage.get('session') && S.storage.get('session').raw === 'https://example.com/b.mp4', 'on-screen Next must play the next item when Auto-advance is off')
  const before = S.storage.get('settings')
  const next = S.registered.find((d) => d.id === 'key-next')
  next.data.run()
  ok(S.storage.get('settings').autoAdvance === before.autoAdvance, 'explicit Next must not flip Auto-advance')
  const saved = S.storage.get('session')
  ok(saved && saved.raw === 'https://example.com/b.mp4', 'explicit Next must play the next item when Auto-advance is off')
  const prev = S.registered.find((d) => d.id === 'key-prev')
  ok(prev && prev.data && typeof prev.data.run === 'function', 'Previous must be a command')
  if (prev) prev.data.run()
  ok(S.storage.get('session') && S.storage.get('session').raw === 'https://example.com/a.mp4', 'explicit Previous must play the previous item when Auto-advance is off')
}
{
  const outside = 'https://cdn.example.com/flower.mp4'
  const S = makeCtx({
    pins: [{ url: 'https://example.com/a.mp4', title: 'a' }, { url: 'https://example.com/b.mp4', title: 'b' }],
    settings: { autoAdvance: true, restoreMode: 'url' },
    session: { raw: outside, floating: false },
  })
  const m = await fresh(source)
  m.default.register(S.ctx)
  const pane = S.registered.find((d) => d.area === 'panes' && typeof d.render === 'function')
  const media = find(pane.render(), (n) => n.type === 'video' || n.type === 'audio')
  ok(!!media && media.props && typeof media.props.onEnded === 'function', 'a file we own must expose ended')
  if (media) media.props.onEnded()
  ok(S.storage.get('session') && S.storage.get('session').raw === outside, 'auto-advance must not start the queue when the file that ended is not in it')
}
{
  const S = makeCtx({
    pins: [{ url: 'https://example.com/a.mp4', title: 'a' }, { url: 'https://example.com/b.mp4', title: 'b' }],
    settings: { autoAdvance: true, restoreMode: 'url' },
    session: { raw: 'https://example.com/a.mp4', floating: false },
  })
  const m = await fresh(source)
  m.default.register(S.ctx)
  const pane = S.registered.find((d) => d.area === 'panes' && typeof d.render === 'function')
  const media = find(pane.render(), (n) => n.type === 'video' || n.type === 'audio')
  if (media && media.props && typeof media.props.onEnded === 'function') media.props.onEnded()
  ok(S.storage.get('session') && S.storage.get('session').raw === 'https://example.com/b.mp4', 'auto-advance plays the next queued item when the one that ended is in the queue')
}
{
  // A row is a tabbable div with its own Enter handler, and its Remove / move controls are
  // buttons inside it whose keydown bubbles to that same handler. Enter aimed at a control
  // must remove or move, never also navigate.
  const S = makeCtx({
    pins: [{ url: 'https://example.com/a.mp4', title: 'a' }, { url: 'https://example.com/b.mp4', title: 'b' }],
    settings: { showQueue: true }, session: { raw: 'https://example.com/outside', floating: false },
  })
  const m = await fresh(source)
  m.default.register(S.ctx)
  const pane = S.registered.find((d) => d.area === 'panes' && typeof d.render === 'function')
  const rows = []
  walk(pane.render(), (n) => { if (n.props && n.props.role === 'tab' && typeof n.props.onKeyDown === 'function') rows.push(n) }, 0, new Set())
  ok(rows.length >= 2, 'every queue row must own an Enter handler')
  const raw = () => (S.storage.get('session') || {}).raw
  if (rows.length) {
    const row = rows[0]
    row.props.onKeyDown({ key: 'Enter', target: row, currentTarget: row })
    eq(raw(), 'https://example.com/a.mp4', 'Enter on the row itself opens that row')
    // A different row, so a stray open is visible: Enter aimed at a control must not navigate.
    rows[1].props.onKeyDown({ key: 'Enter', target: { tag: 'Remove' }, currentTarget: rows[1] })
    eq(raw(), 'https://example.com/a.mp4', 'Enter on a row control must not also open the row')
  }
}
ok(find(paneTree, (n) => n.props && n.props['aria-label'] === 'URL'), 'pane must expose a URL field')
{
  const cardPill = (n) => n.props && /^Card \d+×\d+$/.test(String(n.props.children || '').trim())
  ok(!find(paneTree, cardPill), 'the docked footer must not carry a floating-card size control')
  // A fresh instance, so earlier click sweeps (focus mode, refusals) cannot
  // change what the floating card renders.
  const S2 = makeCtx({})
  const m2 = await fresh(source)
  m2.default.register(S2.ctx)
  const docked2 = S2.registered.find((d) => d.area === 'panes' && typeof d.render === 'function').render()
  const detach = find(docked2, (n) => n.props && n.props.children === 'Detach')
  ok(!!detach, 'the docked footer must offer Detach')
  globalThis.__paneOps = []
  if (detach) detach.props.onClick(EV)
  const livePanes = () => S2.registered.filter((d) => d.area === 'panes' && d.enabled !== false)
  eq(livePanes().length, 1, 'exactly ONE pane surface may be live at a time')
  eq(livePanes()[0].data.placement, 'floating', 'Detach makes the floating card the live surface')
  eq(livePanes()[0].id, 'float', 'the live surface is the floating contribution id')
  // The shipping bundle DOES expose removePane (dist/assets/capabilities-*.js), and a
  // disable-only flip left the abandoned node in the layout tree. Detach must evict the
  // docked id it is leaving and must never evict the id it just made live.
  const flipOps = globalThis.__paneOps || []
  ok(flipOps.some((o) => o.op === 'removePane' && o.id === 'media-dock:card'),
    'detach must evict the docked surface it leaves behind')
  ok(!flipOps.some((o) => o.op === 'removePane' && o.id === 'media-dock:float'),
    'detach must never evict the floating surface it just made live')
  const floatTree = S2.registered.filter((d) => d.area === 'panes' && d.data && d.data.placement === 'floating' && typeof d.render === 'function').pop().render()
  ok(find(floatTree, (n) => n.props && n.props['data-floating-no-drag'] === 'true'), 'resize grips must opt out of host pane-drag')
  ok(find(floatTree, cardPill), 'the floating card must print its current dimensions')
}

// ------------------------------------------------------------- restore is a setting
const RAW = 'https://cdn.example.com/flower.mp4'
async function scenario(store, label) {
  const S = makeCtx(store)
  const m = await fresh(source)
  m.default.register(S.ctx)
  const pane = S.registered.find((d) => d.area === 'panes' && typeof d.render === 'function')
  const tree = pane ? pane.render() : null
  const urlNode = find(tree, (n) => n.props && n.props['aria-label'] === 'URL')
  const value = urlNode && urlNode.props ? String(urlNode.props.value == null ? '' : urlNode.props.value) : null
  const mediaNode = find(tree, (n) => n.type === 'video' || n.type === 'audio')
  clickAll([tree], label)
  return { value, autoPlay: mediaNode && mediaNode.props ? !!mediaNode.props.autoPlay : null, tree, S, mediaNode }
}
const sUrl = await scenario({ session: { raw: RAW, floating: false }, settings: { restoreMode: 'url' } }, 'restore-url')
eq(sUrl.value, RAW, 'restoreMode=url must restore the last URL')
eq(sUrl.autoPlay, false, 'restoreMode=url must NOT autoplay')
const sPlay = await scenario({ session: { raw: RAW, floating: false }, settings: { restoreMode: 'playing' } }, 'restore-playing')
eq(sPlay.value, RAW, 'restoreMode=playing must restore the last URL')
eq(sPlay.autoPlay, true, 'restoreMode=playing must autoplay the restored item')
const sBlank = await scenario({ session: { raw: RAW, floating: false }, settings: { restoreMode: 'blank' } }, 'restore-blank')
eq(sBlank.value, '', 'restoreMode=blank must start empty')
eq(sBlank.autoPlay, null, 'restoreMode=blank must render no media element')
// Page restore is a page-posture case (chrome recedes; no click-sweep minimum).
// Covered below with the other page URLs — scenario() would demand chrome handlers.

// ------------------------------ one generic top-level guest for EVERY page URL
// Paste any http(s) URL -> it plays. No hostname branch, no per-site wrapper,
// no origin rewrite, no framable iframe. A <webview> is its own WebContents
// (top-level), and its partition must be plugin-owned, in-memory, signed-out.
const GUEST_CASES = [
  'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
  'https://www.twitch.tv/nousresearch',
  'https://www.netflix.com/title/1',
  'https://kick.com/a',
  'https://example.com/article',
  'https://例え.テスト/',
  'http://localhost:8080/a',
]
for (const raw of GUEST_CASES) {
  const S = makeCtx({ session: { raw, floating: false }, settings: { restoreMode: 'url' } })
  const m = await fresh(source)
  m.default.register(S.ctx)
  const pane = S.registered.find((d) => d.area === 'panes' && typeof d.render === 'function')
  const tree = pane.render()
  const guest = find(tree, (n) => n.type === 'webview')
  ok(!!guest, 'page URL must render a top-level <webview> guest: ' + raw)
  if (!guest) continue
  eq(guest.props.src, P(raw).src, 'guest src must be the pasted URL as-is: ' + raw)
  ok(/^persist:media-dock$/.test(String(guest.props.partition)),
    'guest must use the plugin-owned persisted session (sign-ins survive restart, never shared): ' + raw)
  ok(!('allowpopups' in guest.props) && !('nodeintegration' in guest.props) && !('webpreferences' in guest.props),
    'guest must not widen Electron privileges: ' + raw)
  // NO preload: the host evaluates this module from a blob: URL, so a relative
  // './guest.js' cannot resolve and a preload would silently never run. The page
  // agent is injected with executeJavaScript instead (one generic agent).
  ok(!('preload' in guest.props),
    'guest must carry no preload (a blob module cannot resolve one): ' + raw)
  ok(!find(tree, (n) => n.type === 'iframe' || n.type === 'stub-SandboxedFrame'),
    'page URL must not fall back to a framable frame: ' + raw)
  ok(!find(tree, (n) => n.props && /blank\?|could not load/i.test(String(n.props.children || ''))),
    'a working page must not carry an apology overlay: ' + raw)
  ok(!!find(tree, (n) => n.props && n.props['aria-label'] === 'URL'),
    'a page keeps the address bar so you can navigate: ' + raw)
  ok(!!find(tree, (n) => n.props && n.props.placeholder === 'Paste a URL'),
    'the address bar must say where a URL goes: ' + raw)
}

// The posture that keeps the page off the chrome. These were the bugs that let the page
// cover the address bar and the footer: an absolute inset-0 guest and a 220 px stage floor.
// Nothing else pins them, so a tidy-up could put them back with every check still green.
{
  const raw = 'https://example.com/article'
  const S = makeCtx({ session: { raw, floating: false }, settings: { restoreMode: 'url' } })
  const m = await fresh(source)
  m.default.register(S.ctx)
  const pane = S.registered.find((d) => d.area === 'panes' && typeof d.render === 'function')
  const t = pane.render()
  const guest = find(t, (n) => n.type === 'webview')
  const gs = (guest && guest.props.style) || {}
  ok(gs.position !== 'absolute' && gs.inset === undefined && gs.top === undefined,
    'the guest must sit in normal flow, not absolute inset 0 (that is what covered the chrome)')
  const stage = find(t, (n) => n.props && n.props.className === 'media-dock-stage')
  ok(!!stage && stage.props.style.minHeight === 0, 'the stage must be able to shrink (minHeight 0)')
  ok(!!stage && stage.props.style.overflow === 'hidden', 'the stage must clip the guest')
  const root = find(t, (n) => n.props && n.props.className === 'media-dock')
  ok(!!root && root.props.style.overflow === 'hidden' && root.props.style.minHeight === 0,
    'the dock root clips and can shrink')
  ok(!find(t, (n) => n.props && n.props.style && n.props.style.minHeight === 220),
    'no 220px floor: it pushed the footer out of a small pane')
}

// A working page is the stage. The hint is a real did-fail-load only — an
// aborted navigation (errorCode -3) is not a failure, and a later successful
// load must not pull chrome back over a user who already exited focus.
{
  const raw = 'https://example.com/article'
  const S = makeCtx({ session: { raw, floating: false }, settings: { restoreMode: 'url' } })
  const m = await fresh(source)
  m.default.register(S.ctx)
  const pane = S.registered.find((d) => d.area === 'panes' && typeof d.render === 'function')
  const guestNode = {
    style: {}, listeners: {}, url: raw, getURL() { return this.url },
    focus() {}, closest: () => null, querySelector: () => null,
    getBoundingClientRect: () => ({ width: 640, height: 480, left: 0, top: 0, right: 640, bottom: 480 }),
    requestFullscreen() { return Promise.resolve() },
    addEventListener(type, fn) { (this.listeners[type] || (this.listeners[type] = [])).push(fn) },
    removeEventListener(type, fn) {
      const a = this.listeners[type] || []
      const i = a.indexOf(fn)
      if (i >= 0) a.splice(i, 1)
    },
  }
  const before = EFFECTS.length
  const t0 = pane.render()
  attachRefs(t0, guestNode)
  for (const fn of EFFECTS.slice(before)) {
    try { fn() } catch (err) { failures.push('page-posture effect threw: ' + err.message) }
  }
  const failFns = guestNode.listeners['did-fail-load'] || []
  const okFns = guestNode.listeners['did-finish-load'] || []
  ok(failFns.length === 1, 'the guest must listen for did-fail-load')
  ok(okFns.length === 1, 'the guest must listen for did-finish-load')
  const fire = (list, ev) => { for (const fn of list) fn(ev) }
  // Assert the decision (the frame-blocked refusal is on screen), not one wording of it.
  const overlay = (tree) => !!find(tree, (n) => n.props && String(n.props.children || '').includes(mod.errorCopy('frame-blocked')))
  if (failFns.length) fire(failFns, { errorCode: -3, validatedURL: raw })
  ok(!overlay(pane.render()), 'an aborted navigation must not overlay the page')
  if (failFns.length) fire(failFns, { errorCode: -2, validatedURL: raw })
  const tFail = pane.render()
  ok(!!find(tFail, (n) => n.type === 'webview'), 'a failed load must keep the guest mounted')
  ok(overlay(tFail), 'a real guest failure must name the cause')
  ok(!!find(tFail, (n) => n.props && /browser/i.test(String(n.props.children || ''))),
    'a failed guest must offer the Browser door')
  ok(!!find(tFail, (n) => n.props && n.props['aria-label'] === 'URL'), 'a failed page must still offer the address bar')
  const startFns = guestNode.listeners['did-start-loading'] || []
  const fireStart = () => { for (const fn of startFns) fn({}) }
  ok(startFns.length === 1, 'the guest must listen for did-start-loading')
  // A new navigation is the reset boundary: start -> finish with no failure clears it.
  fireStart()
  if (okFns.length) fire(okFns, {})
  const tBack = pane.render()
  ok(!!find(tBack, (n) => n.props && n.props['aria-label'] === 'URL'),
    'did-finish-load must not steal chrome back after the user exited focus')
  ok(!overlay(tBack), 'a finished load clears the failure hint')
  // A cert/DNS refusal fails, THEN finishes on Chromium's own error document. Finish
  // must copy the navigation's fault, not erase it.
  fireStart()
  if (failFns.length) fire(failFns, { errorCode: -201, validatedURL: raw })
  if (okFns.length) fire(okFns, {})
  ok(overlay(pane.render()), 'a cert failure must survive the error document\'s finish event')
  fireStart()
  if (okFns.length) fire(okFns, {})
  ok(!overlay(pane.render()), 'a later successful navigation clears the hint')
  const paste = find(tBack, (n) => n.props && typeof n.props.onPaste === 'function')
  ok(!!paste, 'exit focus must return a paste target')
  if (failFns.length) fire(failFns, { errorCode: -2 })
  if (paste) paste.props.onPaste({ preventDefault() {}, clipboardData: { getData: () => 'https://example.com/next-page' } })
  const tNext = pane.render()
  ok(!overlay(tNext), 'a new URL clears a stale guest failure')
  const nextGuest = find(tNext, (n) => n.type === 'webview')
  ok(!!nextGuest && /next-page/.test(String(nextGuest.props.src || '')), 'a new page URL replaces the guest src')
  ok(!!find(tNext, (n) => n.props && n.props['aria-label'] === 'URL'), 'a new page URL keeps the address bar')
  // ONE guest element: re-keying it by URL would erase the guest's history, so
  // Back could never work. Navigation is the src attribute on the same element.
  ok(nextGuest.props.key === undefined, 'the guest must not be re-keyed by URL')
  // The address field is the PAGE's address. A typed load puts the parsed URL in
  // `pageUrl` before the guest ever navigates, so a "pageUrl changed" test alone
  // leaves the typed text in the field; the did-navigate event must still win.
  const navFns = guestNode.listeners['did-navigate'] || []
  ok(navFns.length === 1, 'the guest must track did-navigate for the address bar')
  const bar = (tree) => find(tree, (n) => n.props && n.props['aria-label'] === 'URL')
  const input = bar(tNext)
  ok(!!input && typeof input.props.onPaste === 'function', 'the address bar must accept a pasted address')
  // A bare host keeps the typed text in `raw` while the parsed URL lands in
  // `pageUrl` — exactly the state a real navigation returns from the guest.
  if (input) input.props.onPaste({ preventDefault() {}, clipboardData: { getData: () => 'example.org' } })
  pane.render()
  if (navFns.length) fire(navFns, { url: 'https://example.org/' })
  const tTypedNav = pane.render()
  ok(!!bar(tTypedNav) && bar(tTypedNav).props.value === 'https://example.org/',
    'the address bar must follow the page URL, not the typed text')
  // A failed load of OUR url must not leave the self-navigation guard disarmed: the intent
  // was cleared only on did-finish-load, so one failed paste let every later ad redirect be
  // adopted silently (no 'this page tried to open …' offer).
  const willFns = guestNode.listeners['will-navigate'] || []
  ok(willFns.length === 1, 'the guest must guard will-navigate')
  fireStart()
  if (failFns.length) fire(failFns, { errorCode: -2, validatedURL: 'https://example.org/' })
  let blocked = false
  fire(willFns, { url: 'https://ads.example.net/landing', preventDefault() { blocked = true } })
  ok(blocked, 'after a failed load, a cross-site self-navigation is still stopped')
  ok(!!find(pane.render(), (n) => n.props && /tried to open/i.test(String(n.props.children || ''))),
    'and offered to the user, not silently adopted')
  // Tab only reaches the dock on a page whose focus ring ends; Escape is the exit that always
  // exists, so an Escape the page did not consume must hand the keyboard back to the address bar.
  const conFns = guestNode.listeners['console-message'] || []
  ok(conFns.length === 1, 'the guest must report boundary keys on console-message')
  guestNode.blur = () => {}
  let back = false
  guestNode.focus = () => { back = true }
  // React attaches ref OBJECTS without calling them; hand the address bar its element.
  const barNode = find(t0, (n) => n.props && n.props['aria-label'] === 'URL')
  if (barNode && barNode.props.ref && typeof barNode.props.ref === 'object') barNode.props.ref.current = guestNode
  fire(conFns, { message: '__md:escape' })
  ok(back, 'Escape inside a page returns the keyboard to the address bar')
  // A refusal must carry its reason AND a way out. errorCopy's own unit checks cannot
  // see this: the well is handed the play state, and passing the wrong shape renders a
  // bare "Cannot play here" with no cause and no Browser door.
  const refInput = bar(pane.render())
  if (refInput) refInput.props.onPaste({ preventDefault() {}, clipboardData: { getData: () => 'https://cdn.example.com/s/master.m3u8' } })
  const tRef = pane.render()
  const refText = []
  walk(tRef, (n) => { const c = n.props && n.props.children; if (typeof c === 'string') refText.push(c) }, 0, new Set())
  ok(refText.some((s) => /HLS|DASH|decoder/i.test(s)), 'a refused stream must name its cause on screen')
  ok(!!find(tRef, (n) => n.props && /browser/i.test(String(n.props['aria-label'] || ''))),
    'a refused stream must offer the Browser door')
  ok(!find(tRef, (n) => n.type === 'webview'), 'a refused stream must not mount a guest')
}

// ------------------------------------------- immersive: chrome recedes on playback
async function immersiveCase(immersiveOnPlay, firePlay) {
  const S = makeCtx({ session: { raw: RAW, floating: false }, settings: { restoreMode: 'playing', immersiveOnPlay } })
  const m = await fresh(source)
  m.default.register(S.ctx)
  const pane = S.registered.find((d) => d.area === 'panes' && typeof d.render === 'function')
  const t0 = pane.render()
  const media = find(t0, (n) => n.type === 'video' || n.type === 'audio')
  if (firePlay && media && media.props && typeof media.props.onPlay === 'function') media.props.onPlay(EV)
  const t1 = pane.render()
  return {
    hadUrl: !!find(t0, (n) => n.props && n.props['aria-label'] === 'URL'),
    urlAfter: !!find(t1, (n) => n.props && n.props['aria-label'] === 'URL'),
    videoAfter: !!find(t1, (n) => n.type === 'video' || n.type === 'audio'),
    exitAfter: !!find(t1, (n) => n.props && /exit|back/i.test(String(n.props.title || n.props['aria-label'] || ''))),
  }
}
const imOn = await immersiveCase(true, true)
ok(imOn.hadUrl, 'immersive case starts with chrome')
eq(imOn.urlAfter, false, 'onPlay with immersiveOnPlay=true must hide the address bar')
eq(imOn.videoAfter, true, 'immersive must KEEP the video, not blank the surface')
ok(imOn.exitAfter, 'immersive must expose an exit affordance')
const imOff = await immersiveCase(false, true)
eq(imOff.urlAfter, true, 'immersiveOnPlay=false must keep chrome on play')
const imNoPlay = await immersiveCase(true, false)
eq(imNoPlay.urlAfter, true, 'chrome stays until playback actually starts')

{
  const S = makeCtx({ session: { raw: RAW }, settings: { immersiveOnPlay: true } })
  const m = await fresh(source)
  m.default.register(S.ctx)
  const pane = S.registered.find((d) => d.area === 'panes' && typeof d.render === 'function')
  const t = pane.render()
  const media = find(t, (n) => n.type === 'video' || n.type === 'audio')
  if (media && media.props && typeof media.props.onPlay === 'function') media.props.onPlay(EV)
  const hidden = !find(pane.render(), (n) => n.props && n.props['aria-label'] === 'URL')
  const kd = S.listeners.find((l) => l.type === 'keydown')
  if (kd) { try { kd.fn({ key: 'Escape' }) } catch (e) { failures.push('keydown threw: ' + e.message) } }
  const shown = !!find(pane.render(), (n) => n.props && n.props['aria-label'] === 'URL')
  ok(hidden, 'immersive engaged before Escape')
  eq(shown, true, 'Escape must restore the chrome')
}

const dockProps = RENDERED.find((pr) => pr && typeof pr.toggleFloat === 'function')
ok(dockProps, 'pane must expose toggleFloat')
if (dockProps) {
  try {
    dockProps.toggleFloat()
    const floating = A.registered.filter((d) => d.area === 'panes' && d.data && d.data.placement === 'floating')
    ok(floating.length >= 1, 'Detach must publish a floating pane')
    if (floating.length) {
      eq(floating[0].data.anchor, 'top-right', 'floating pane must spawn top-right')
      eq(floating[0].data.uncloseable, true, 'floating pane must be uncloseable')
    }
  } catch (err) { failures.push('toggleFloat threw: ' + (err && err.message)) }
}

// ------------------------------ reactive automation: subscribe, decide, dispose
{
  const S = makeCtx({ settings: { autoTheater: true }, session: { raw: RAW, floating: false } })
  const m = await fresh(source)
  m.default.register(S.ctx)
  eq(m.automation.get().supported, true, 'shipped host.state atoms detected as supported')
  ok(host.state.busy.__subs() >= 1, 'register subscribes to busy (reactive, no polling)')
  ok(host.state.viewport.__subs() >= 1, 'register subscribes to viewport (reactive, no polling)')
  host.state.busy.set(true)
  eq(m.automation.get().busy, true, 'busy atom drives the live decision without a timer')
  host.state.busy.set(false)
  eq(m.automation.get().busy, false, 'idle atom drives shrink-back decision')
  host.state.viewport.set({ width: 1280, height: 720, narrow: false })
  eq(m.automation.get().viewport.width, 1280, 'viewport resize is observed live')
  const before = host.state.busy.__subs()
  for (const fn of S.disposers) { try { fn() } catch (err) { failures.push('auto dispose threw: ' + (err && err.message)) } }
  ok(host.state.busy.__subs() < before, 'onDispose unsubscribes every automation signal')
  host.state.busy.set(false)
}

// ----------- theater must pin the player where it is, never swap placement -----
{
  // Auto-theater used to flip a docked pane to the floating card, which threw the host's guest
  // away and reloaded the site root. Theater is an overlay of the player the user is looking at.
  const S = makeCtx({ settings: { autoTheater: true }, session: { raw: 'https://example.com/a.mp4', floating: false } })
  const m = await fresh(source)
  m.default.register(S.ctx)
  const pane = S.registered.find((d) => d.area === 'panes' && typeof d.render === 'function')
  const mkEl = () => ({ style: {}, isConnected: true, getBoundingClientRect: () => ({ width: 900, height: 700, left: 24, top: 24, right: 924, bottom: 724 }) })
  const rootEl = mkEl(), stageEl = mkEl()
  const tree = pane.render()
  const rootNode = find(tree, (n) => n.props && typeof n.props.ref === 'function' && n.props.className === 'media-dock')
  const stageNode = find(tree, (n) => n.props && typeof n.props.ref === 'function' && n.props.className === 'media-dock-stage')
  ok(!!rootNode && !!stageNode, 'the pane must expose its root and its player surface')
  if (rootNode) rootNode.props.ref(rootEl)
  if (stageNode) stageNode.props.ref(stageEl)
  globalThis.__paneOps = []
  // Easing only happens if the browser SEES the pinned start box: a rect read flushes layout.
  // Checked on a throwaway element, before theater borrows the real stage.
  const flushSeen = { n: 0 }
  const flushEl = { style: {}, isConnected: true, getBoundingClientRect() { flushSeen.n += 1; return { width: 900, height: 700, left: 24, top: 24 } } }
  mod.applyTheaterPlan({ own: true, changed: true, mode: 'theater' }, flushEl, null, null)
  ok(flushSeen.n >= 2, 'enter must flush the pinned start box before applying the target box (got ' + flushSeen.n + ' reads)')
  mod.applyTheaterPlan({ own: false, changed: true, mode: 'normal' }, flushEl, null, null)
  holdLongTimers()
  host.state.busy.set(true)
  eq(m.automation.get().own, false, 'theater must wait for the turn to settle, not jump on Enter')
  ok(gateTimers.some((t) => t.ms === mod.THEATER_GATE.enter), 'theater must arm a ' + mod.THEATER_GATE.enter + ' ms settle gate, not snap open')
  ok(fireLongTimers(mod.THEATER_GATE.enter) > 0, 'the settle gate must be armed by a busy turn')
  eq(m.automation.get().own, true, 'a busy turn must engage theater after the settle gate')
  eq(stageEl.style.position, 'fixed', 'theater must fullscreen the player surface itself')
  ok(/width \.34s/.test(String(stageEl.style.transition)) && /height \.34s/.test(String(stageEl.style.transition)), 'theater must ease into place, not snap')
  eq(stageEl.style.top, mod.THEATER_CFG.inset + mod.THEATER_CFG.rail + 'px', 'the stage must start below the rail, never under it')
  eq(rootEl.style.position, undefined, 'theater must leave the pane where it is, not pin the whole pane')
  // The pinned player covers the pane's footer, so theater must carry its own way out on top.
  const layer = find(pane.render(), (n) => n.props && n.props.style && n.props.style.zIndex === mod.THEATER_CFG.z + 10)
  ok(!!layer, 'theater must carry a control layer above the pinned player')
  ok(!!(layer && find(layer, (n) => n.props && String(n.props.children) === 'Exit theater')), 'theater must offer Exit theater above the player')
  ok(!!(layer && find(layer, (n) => n.props && String(n.props.children) === 'Close')), 'theater must offer Close above the player')
  ok(!!find(pane.render(), (n) => n.props && n.props.style && n.props.style.zIndex === mod.THEATER_CFG.z + 8), 'theater grips must sit above the pinned player')
  // The rail must span the theater box so the exit commands exist over any site.
  const rail = layer
  eq(!!rail && rail.props.style.left, mod.THEATER_CFG.inset + 'px', 'the theater rail must reach the left edge')
  eq(!!rail && rail.props.style.right, mod.THEATER_CFG.inset + 'px', 'the theater rail must reach the right edge')
  eq(!!rail && rail.props.style.height, mod.THEATER_CFG.rail + 'px', 'the theater rail must own a fixed strip')
  const esc = S.listeners.filter((l) => l.type === 'keydown').pop()
  if (esc) esc.fn({ key: 'Escape', preventDefault() {}, target: { tagName: 'DIV' } })
  eq(m.automation.get().own, false, 'Escape must leave theater: the player cannot trap the window')
  eq((globalThis.__paneOps || []).filter((o) => o.op === 'removePane').length, 0, 'theater must not evict the docked pane')
  eq(S.registered.filter((d) => d.area === 'panes' && d.enabled !== false && d.data && d.data.placement === 'floating').length, 0, 'theater must not spawn a floating card')
  // Closing is a gated motion too: a turn that ends and restarts must not flash the player.
  host.state.busy.set(false)
  await new Promise((r) => setTimeout(r, 60))
  eq(m.automation.get().manual, null, 'a manual exit must last exactly one turn')
  host.state.busy.set(true)
  ok(fireLongTimers(mod.THEATER_GATE.enter) > 0, 'the settle gate arms again for the next turn')
  eq(m.automation.get().own, true, 'theater re-engages after the settle gate')
  host.state.busy.set(false)
  eq(m.automation.get().own, true, 'the exit gate must hold theater open, not snap it shut')
  ok(gateTimers.some((t) => t.ms === mod.THEATER_GATE.exit), 'closing must arm its own ' + mod.THEATER_GATE.exit + ' ms gate')
  ok(fireLongTimers(mod.THEATER_GATE.exit) > 0, 'the exit gate must be armed when a turn ends')
  eq(m.automation.get().own, false, 'theater closes once the exit gate elapses')
  ok(/width \.3s/.test(String(stageEl.style.transition)), 'closing must ease back to the dock, not snap')
  await new Promise((r) => setTimeout(r, 400))
  eq(stageEl.style.position, undefined, 'exit must hand the borrowed style back after the shrink')
  // Dispose this controller: a stale subscription would arm gates for the next scenario.
  for (const fn of S.disposers) { try { fn() } catch (err) { /* older ctx */ } }
  releaseLongTimers()
}
// ----------- persist, reactive: a real chat switch must not shrink theater -----
{
  const T = makeCtx({ settings: { autoTheater: true, theaterPersist: 'window' }, session: { raw: RAW, floating: false } })
  const t = await fresh(source)
  t.default.register(T.ctx)
  const pane = T.registered.find((d) => d.area === 'panes' && typeof d.render === 'function')
  const mark = RENDERED.length
  const tree = pane.render()
  const fakeFrame = { style: {}, closest: () => fakeFrame }
  const rootEl = find(tree, (n) => n.props && typeof n.props.ref === 'function')
  if (rootEl) rootEl.props.ref(fakeFrame)
  const dp = RENDERED.slice(mark).find((pr) => pr && typeof pr.toggleFloat === 'function')
  ok(dp, 'persist scenario exposes toggleFloat')
  if (dp) {
    dp.toggleFloat()
    eq(t.automation.get().floating, true, 'detach before the persist test')
    eq(t.automation.get().hasMedia, true, 'media loaded before the persist test')
    holdLongTimers()
    host.state.busy.set(true)
    ok(fireLongTimers(mod.THEATER_GATE.enter) > 0, 'the settle gate arms in the live controller')
    eq(t.automation.get().mode, 'theater', 'busy opens theater in the live controller')
    host.state.busy.set(false)
    eq(t.automation.get().mode, 'theater', 'window persist survives a chat switch (no shrink)')
    eq(fireLongTimers(mod.THEATER_GATE.exit), 0, 'window persist must not arm an exit gate: it stays open')
    releaseLongTimers()
    const U = makeCtx({ settings: { autoTheater: true, theaterPersist: 'agent' }, session: { raw: RAW, floating: false } })
    const u = await fresh(source)
    u.default.register(U.ctx)
    const pane2 = U.registered.find((d) => d.area === 'panes' && typeof d.render === 'function')
    const mark2 = RENDERED.length
    const tree2 = pane2.render()
    const fakeFrame2 = { style: {}, closest: () => fakeFrame2 }
    const rootEl2 = find(tree2, (n) => n.props && typeof n.props.ref === 'function')
    if (rootEl2) rootEl2.props.ref(fakeFrame2)
    const dp2 = RENDERED.slice(mark2).find((pr) => pr && typeof pr.toggleFloat === 'function')
    if (dp2) dp2.toggleFloat()
    host.state.busy.set(true)
    host.state.busy.set(false)
    eq(u.automation.get().mode, 'normal', 'agent persist shrinks back in the live controller')
    for (const fn of U.disposers) { try { fn() } catch (err) { failures.push('agent dispose threw: ' + (err && err.message)) } }
  }
  for (const fn of T.disposers) { try { fn() } catch (err) { failures.push('persist dispose threw: ' + (err && err.message)) } }
  host.state.busy.set(false)
}

for (const fn of A.disposers) { try { fn() } catch (err) { failures.push('onDispose threw: ' + (err && err.message)) } }

// ---- part 1: live gate through register() (reactive, durable, no polling) ----
host.state.focusedStoredSessionId.set('stored-9')
async function gated(store) {
  const S = makeCtx({ session: { raw: RAW, floating: false }, ...(store || {}) })
  const m = await fresh(source)
  m.default.register(S.ctx)
  const pane = S.registered.find((d) => d.area === 'panes' && typeof d.render === 'function')
  return { S, m, pane, tree: pane ? pane.render() : null }
}
const hasGate = (tree) => !!find(tree, (n) => n.props && /Not shown in this chat/.test(String(n.props.children || '')))
const hasMedia = (tree) => !!find(tree, (n) => n.type === 'video' || n.type === 'audio' || n.type === 'webview')
const gPick = await gated({ settings: { sessionScope: 'picked' }, pickedSessions: ['stored-2'] })
ok(hasGate(gPick.tree), 'an unpicked focused chat must show the NAMED gate well')
ok(hasMedia(gPick.tree), 'the gate must NOT unmount the media element (no playback restart)')
const gAllow = await gated({ settings: { sessionScope: 'picked' }, pickedSessions: ['stored-9'] })
ok(!hasGate(gAllow.tree), 'a picked chat must NOT be gated')
const gAll = await gated({ settings: { sessionScope: 'all' }, pickedSessions: [] })
ok(!hasGate(gAll.tree), 'scope=all must never gate')
const showHere = find(gPick.tree, (n) => n.props && n.props.children === 'Show here' && typeof n.props.onClick === 'function')
ok(showHere, 'the gate must offer Show here')
if (showHere) showHere.props.onClick()
ok(!hasGate(gPick.pane.render()), 'Show here must clear the gate on re-render')
ok((gPick.S.storage.get('pickedSessions', []) || []).indexOf('stored-9') >= 0, 'Show here must persist the DURABLE stored id, not a runtime id')
const pinCmd = gPick.S.registered.find((d) => /keybind/i.test(d.area || '') && /Pin\/Unpin/.test(String(d.data && d.data.label || '')))
ok(pinCmd && typeof pinCmd.data.run === 'function', 'pin command must be runnable')
if (pinCmd) pinCmd.data.run()
ok(hasGate(gPick.pane.render()), 'the pin command toggles the focused chat back OFF')
const gReset = await gated({ settings: { sessionScope: 'picked' }, pickedSessions: [] })
const everywhere = find(gReset.tree, (n) => n.props && n.props.children === 'Show everywhere' && typeof n.props.onClick === 'function')
ok(everywhere, 'the gate must offer Show everywhere')
if (everywhere) everywhere.props.onClick()
eq(gReset.S.storage.get('settings', {}).sessionScope, 'all', 'Show everywhere must reset the scope to all')
{
  const D = makeCtx({})
  const dm = await fresh(source)
  dm.default.register(D.ctx)
  const before = host.state.focusedStoredSessionId.__subs()
  for (const fn of D.disposers) { try { fn() } catch (err) { failures.push('part-1 dispose threw: ' + (err && err.message)) } }
  ok(host.state.focusedStoredSessionId.__subs() < before, 'onDispose must unsubscribe the focused-stored atom')
}
const gClick = await gated({ settings: { sessionScope: 'picked' }, pickedSessions: [] })
clickAll([gClick.tree], 'gate-click')
host.state.focusedStoredSessionId.set(null)

// ---- part 5: live event path through register() (event-driven, no polling) ----
globalThis.__activeSessions = [{ id: 'rt2', session_key: 'stored-2', status: 'idle' }]
globalThis.__notified = []; globalThis.__opened = []; globalThis.__removed = []
const cMod5 = await fresh(source)
const cCtx5 = makeCtx({ settings: { completionToasts: true } })
cMod5.default.register(cCtx5.ctx)
await new Promise((r) => setTimeout(r, 0))
ok(cCtx5.events.some((e) => e.type === 'message.complete') && cCtx5.events.some((e) => e.type === 'error'),
  'both terminal event types must be subscribed via ctx.onEvent')
ok(cCtx5.events.some((e) => e.type === 'sessions.changed'), 'runtime->stored mapping must refresh on sessions.changed, never a timer')
const terminal = cCtx5.events.find((e) => e.type === 'message.complete').fn
terminal({ type: 'message.complete', session_id: 'rt2', seq: 7 })
eq(globalThis.__notified.length, 1, 'one completion toast for another chat')
eq(globalThis.__notified[0] && globalThis.__notified[0].action.label, 'Open chat', 'toast must expose a clickable action')
eq(globalThis.__notified[0] && globalThis.__notified[0].placement, 'bottom-right', 'toast must be in-app, not a native OS notification')
globalThis.__notified[0].action.onClick()
ok(globalThis.__opened.indexOf('stored-2') >= 0, 'action snaps to the STORED session id, not the runtime id')
ok(cCtx5.registered.filter((d) => d.area === 'panes' && d.enabled !== false).length === 0,
  'action collapses the dock before snapping (no live pane surface left)')
terminal({ type: 'message.complete', session_id: 'rt2', seq: 7 })
eq(globalThis.__notified.length, 1, 'a duplicate frame must not double-toast')
terminal({ type: 'message.complete', session_id: 'rt2', seq: 8, replayed: true })
eq(globalThis.__notified.length, 1, 'a reconnect replay is not fresh work')
host.state.focusedStoredSessionId.set('stored-2')
terminal({ type: 'message.complete', session_id: 'rt2', seq: 9 })
eq(globalThis.__notified.length, 1, 'the focused chat must never toast')
host.state.focusedStoredSessionId.set(null)
globalThis.__notified = []
const dMod5 = await fresh(source), dCtx5 = makeCtx({})
dMod5.default.register(dCtx5.ctx)
await new Promise((r) => setTimeout(r, 0))
const offEv = dCtx5.events.find((e) => e.type === 'message.complete')
if (offEv) offEv.fn({ type: 'message.complete', session_id: 'rt2', seq: 10 })
eq(globalThis.__notified.length, 0, 'opt-in off by default: no toast without the setting')
for (const fn of cCtx5.disposers) { try { fn() } catch (err) { failures.push('completion dispose threw: ' + (err && err.message)) } }
ok(!cCtx5.events.some((e) => e.type === 'message.complete' || e.type === 'error' || e.type === 'sessions.changed'),
  'onDispose must retire every completion subscription')

// ---- lifecycle: ONE mounted surface; its ResizeObserver is retired on unmount ----
// A route page used to render beside the pane (two live players, two observers, a
// hand-off dance). The plugin is one surface now, so this case pins that shape.
{
  const L = makeCtx({})
  const lm = await fresh(source)
  lm.default.register(L.ctx)
  const pane = L.registered.find((d) => d.area === 'panes' && typeof d.render === 'function')
  ok(!!pane, 'lifecycle case needs a pane surface')
  ok(!L.registered.some((d) => d.area === 'routes' || d.area === 'sidebar.nav'),
    'the plugin must register one surface only: no route page, no sidebar page')

  let paneFs = 0, observed = 0, disconnected = 0
  const fake = (bump) => ({
    style: {}, focus() {}, closest: () => null, querySelector: () => null,
    getBoundingClientRect: () => ({ width: 640, height: 480, left: 0, top: 0, right: 640, bottom: 480 }),
    requestFullscreen() { bump(); return Promise.resolve() },
  })
  const paneNode = fake(() => { paneFs++ })

  const SavedRO = globalThis.ResizeObserver
  globalThis.ResizeObserver = class {
    observe() { observed++ }
    disconnect() { disconnected++ }
  }
  const before = EFFECTS.length
  const paneTree = pane.render()
  attachRefs(paneTree, paneNode)
  const added = EFFECTS.slice(before)
  const cleanups = []
  for (const fn of added) {
    try { const off = fn(); if (typeof off === 'function') cleanups.push(off) }
    catch (err) { failures.push('lifecycle effect threw: ' + err.message) }
  }
  eq(observed, 1, 'the mounted surface owns its own ResizeObserver')
  for (const off of cleanups) off()
  eq(disconnected, 1, 'the ResizeObserver must be disconnected on unmount')
  globalThis.ResizeObserver = SavedRO

  const hasPlayer = (tree) => !!find(tree, (n) => n.type === 'video' || n.type === 'webview')
  const paste = find(paneTree, (n) => n.props && typeof n.props.onPaste === 'function')
  ok(!!paste, 'the surface must accept a pasted media URL')
  if (paste) paste.props.onPaste(EV)
  const mount = (tree, from) => { const stops = []
    for (const fn of EFFECTS.slice(from)) { try { const off = fn(); if (typeof off === 'function') stops.push(off) } catch (err) { failures.push('mount effect threw: ' + err.message) } }
    return stops }
  ok(hasPlayer(pane.render()), 'the surface mounts the player')
  for (const off of mount(pane.render(), EFFECTS.length)) off()

  // Cold start: the chip opens the pane, and the pane that opens owns playback.
  const C2 = makeCtx({ session: { raw: 'https://example.com/article', floating: false }, settings: { restoreMode: 'url' } })
  const m2 = await fresh(source)
  m2.default.register(C2.ctx)
  const chip2 = C2.registered.find((d) => d.id === 'chip')
  const openIt = chip2 && find(chip2.render(), (n) => n.props && n.props['aria-label'] === 'Open Media Dock')
  ok(!!openIt, 'the status chip must open the pane')
  if (openIt) openIt.props.onClick()
  const liveC2 = C2.registered.filter((d) => d.area === 'panes' && d.enabled !== false)
  eq(liveC2.length, 1, 'a docked open pane is the ONLY live surface (no card beside it)')
  eq(liveC2[0].id, 'card', 'the docked surface is the card id')
  const p2 = C2.registered.find((d) => d.area === 'panes' && typeof d.render === 'function' && d.enabled !== false)
  ok(!!p2, 'the chip must leave the pane open')
  for (const off of mount(p2.render(), EFFECTS.length)) off()
  ok(hasPlayer(p2.render()), 'the opened pane owns playback')

  // A command from register() must target the FRONTED surface, never a dead one.
  const fs = L.registered.find((d) => d.id === 'key-fullscreen' && d.data && typeof d.data.run === 'function')
  ok(!!fs, 'fullscreen command must be registered')
  const down = find(paneTree, (n) => n.props && typeof n.props.onPointerDownCapture === 'function')
  ok(!!down, 'a surface must expose a fronting affordance')
  if (down) down.props.onPointerDownCapture(EV)
  if (fs) fs.data.run()
  eq(paneFs, 1, 'a global command must target the fronted surface')

  // In fullscreen the same control must be the way OUT. A one-way door strands the
  // window: the dock's Close button becomes the only exit.
  const savedDoc = globalThis.document
  let exited = 0
  globalThis.document = { fullscreenElement: paneNode, exitFullscreen() { exited++; return Promise.resolve() } }
  if (fs) fs.data.run()
  eq(exited, 1, 'a second fullscreen press must call exitFullscreen exactly once')
  eq(paneFs, 1, 'the fullscreen press must not request fullscreen again while full')
  globalThis.document = savedDoc

  attachRefs(paneTree, null)
  if (fs) fs.data.run()
  eq(paneFs, 1, 'a detached surface must not remain a command target')
}


if (failures.length) {
  console.log('FAIL  ' + failures.length + ' failure(s); ' + clicked + ' handlers clicked')
  for (const f of failures) console.log('   - ' + f)
  process.exit(1)
}
console.log('OK  ' + A.registered.length + ' registrations, ' + clicked + ' handlers clicked, restore + page posture + geometry + immersive + resize + fullscreen + part-1 gate assertions pass')
"""

REACT = r"""
export const useState = (init) => [typeof init === 'function' ? init() : init, () => {}]
export const EFFECTS = []
export const useEffect = (fn) => { EFFECTS.push(fn) }
export const useLayoutEffect = () => {}
export const useRef = (v) => ({ current: v })
export const useCallback = (fn) => fn
export const useMemo = (fn) => fn()
export const memo = (fn) => fn
export const useSyncExternalStore = (sub, get) => get()
export const RENDERED = []
export function __render(fn, props) { RENDERED.push(props || {}); return fn(props || {}) }
"""

JSX_RUNTIME = r"""
import { __render } from './index.js'
export function jsx(type, props, key) {
  if (typeof type === 'function') return __render(type, props || {})
  return { type, props: props || {} }
}
export const jsxs = jsx
export const Fragment = '__fragment__'
"""

SDK = r"""
export const atom = (init) => {
  let v = init
  const subs = new Set()
  return {
    get: () => v,
    set: (n) => { v = n; subs.forEach((f) => f(v)) },
    subscribe: (f) => { subs.add(f); return () => subs.delete(f) },
    __subs: () => subs.size,
  }
}
export const useValue = (a) => (a && typeof a.get === 'function' ? a.get() : undefined)
export const cn = (...a) => a.filter(Boolean).join(' ')
export const useTheme = () => ({ themeName: 'test', resolvedMode: 'dark' })
export const pluginSettingsHref = (id, page) => '/settings?tab=plugins&plugin=' + id + '&ppage=' + page
export const host = {
  state: {
    busy: atom(false), busyBySession: atom({}),
    viewport: atom({ width: 1600, height: 900, narrow: false }),
    focusedStoredSessionId: atom(null), activeSessionId: atom(null), focusedSessionId: atom(null),
  },
  request: async (m) => m === 'session.active_list' ? { sessions: globalThis.__activeSessions || [] } : {},
  notify: (i) => { (globalThis.__notified || (globalThis.__notified = [])).push(i); return 'ok' },
  notifyError: () => {}, navigate: () => {},
  undismissPane: (id) => {
    const ops = globalThis.__paneOps || (globalThis.__paneOps = [])
    ops.push({ op: 'undismissPane', id, placement: (globalThis.__paneRegistered || {}).placement })
  },
  removePane: (id) => {
    const ops = globalThis.__paneOps || (globalThis.__paneOps = [])
    ops.push({ op: 'removePane', id, placement: (globalThis.__paneRegistered || {}).placement })
    const removed = globalThis.__removed || (globalThis.__removed = [])
    removed.push(id)
  },
  openWorkspace: () => () => {},
  openSession: (id) => { (globalThis.__opened || (globalThis.__opened = [])).push(id) },
}
export const PANES_AREA = 'panes'
export const PALETTE_AREA = 'palette'
export const ROUTES_AREA = 'routes'
export const SIDEBAR_NAV_AREA = 'sidebar.nav'
export const KEYBINDS_AREA = 'keybinds'
export const STATUSBAR_AREAS = { left: 'statusBar.left', right: 'statusBar.right' }
export const SETTINGS_PLUGINS_AREA = 'settings.plugins'
const inert = (name) => { const C = (props) => ({ type: 'stub-' + name, props: props || {} }); C.displayName = name; return C }
export const Button = inert('Button')
export const Codicon = inert('Codicon')
export const SandboxedFrame = inert('SandboxedFrame')
export const MessageTextContent = inert('MessageTextContent')
export const Input = inert('Input')
"""

MUTATIONS = [
    # --- original invariants -------------------------------------------------
    ("scheme guard removed", "if (url.protocol !== 'http:' && url.protocol !== 'https:') return { ok: false, error: 'scheme' }", "if (false) return { ok: false, error: 'scheme' }"),
    ("docked size click paints the pane", "if (!card) { releaseDockPaint(root); return false }", "if (false) { releaseDockPaint(root); return false }"),
    ("bare-token guard removed", "if (!hostname || (!hostname.includes('.') && hostname !== 'localhost')) return { ok: false, error: 'not-a-url' }", "if (false) return { ok: false, error: 'not-a-url' }"),
    ("manifest refusal removed", "if (MANIFEST_EXT[ext]) return { kind: 'manifest', ext, media: null }", "if (false) return { kind: 'manifest', ext, media: null }"),
    ("volume ceiling removed", "return Math.max(0, Math.min(VOL_MAX, Math.round(n)))", "return n"),
    ("queue loop wrap removed", "return loop && i >= 0 ? rows[0] : null", "return null"),
    ("queue remove is a no-op", "owner.set(removePin(owner.get(), p.id))", "owner.set(owner.get())"),
    ("shelf writes land in the queue", "owner = shelfMode ? shelf : pins", "owner = pins"),
    ("queue remove also opens the row", "if (e && e.stopPropagation) e.stopPropagation()", "void e"),
    ("queue move is a no-op", "const next = rows.slice()", "return rows; const next = rows.slice()"),
    ("queue move also opens the row", "keepRow(e); pins.set(movePin(pins.get(), p.id, -1))", "void e; pins.set(movePin(pins.get(), p.id, -1))"),
    ("auto-advance ignores queue membership", "if (!Array.isArray(rows) || !rows.some((p) => p && p.url === cur)) return null", "if (false) return null"),
    ("explicit previous obeys auto-advance", "function playPrev() {", "function playPrev() { if (!settings.get().autoAdvance) return null;"),
    ("explicit next obeys auto-advance", "function playNext() {", "function playNext() { if (!settings.get().autoAdvance) return null;"),
    ("restore setting ignored", "if (cfg.restoreMode !== 'blank' && saved", "if (true && saved"),
    ("uncloseable removed", "uncloseable: true", "uncloseable: false"),
    ("tracked listeners removed", "ctx.addEventListener(globalThis, 'offline', () => net.set('offline'))", "0 && ctx.addEventListener(globalThis, 'offline', () => net.set('offline'))"),
    ("per-site field reintroduced", "return { ...base, kind: 'page', media: null, ext: null }", "return { ...base, kind: 'page', media: null, ext: null, provider: 'web' }"),
    # --- live streams / guest identity ---------------------------------------
    ("live flag lost in the allowlist", "live: m.live === true", "live: false"),
    ("guest UA removed", "export const GUEST_UA = 'Mozilla/5.0", "export const GUEST_UA = ''"),
    # --- geometry ------------------------------------------------------------
    ("anchor math flipped", "const c = clampSize(E.left ? from.w + dx : from.w - dx, E.top ? from.h + dy : from.h - dy, vpW, vpH)", "const c = clampSize(from.w + dx, from.h + dy, vpW, vpH)"),
    ("viewport cap removed", "Math.max(CARD_MIN.w, (Number(vpW) || 0) - 24)", "99999"),
    ("min size removed", "Math.max(CARD_MIN.w, a)", "a"),
    ("docked writes position", "if (floating) { st.left = s.left + 'px'; st.top = s.top + 'px' }", "st.left = s.left + 'px'; st.top = s.top + 'px'"),
    ("detach leaves the docked track", "paneOp('removePane', floating ? PANE_ID : FLOAT_ID)", "paneOp('removePane', floating ? FLOAT_ID : FLOAT_ID)"),
    ("queue row click does not autoplay", "onOpen: (url) => { setDraft(url); loadUrl(url, true) }", "onOpen: (url) => { setDraft(url); loadUrl(url) }"),
    ("ladder does not cycle", "return SIZE_LADDER[(i + 1) % SIZE_LADDER.length]", "return SIZE_LADDER[0]"),
    ("rail inferred from tier", "const rail = w > 0 && w < RAIL_MIN", "const rail = tier === 'rail'"),
    ("wrap inferred from tier", "const wrap = !rail && w > 0 && w < ROW_MIN", "const wrap = tier === 'compact'"),
    ("roomy negative set", "const roomy = ROOMY.indexOf(tier) >= 0", "const roomy = tier !== 'compact'"),
    # --- chrome / immersive / fullscreen ------------------------------------
    ("controls dropped in focus", "transport: true,", "transport: !immersive,"),
    ("immersive setting ignored", "if (cfg.immersiveOnPlay) immersive.set(true)", "if (false) immersive.set(true)"),
    ("exit affordance removed", "exit: !!immersive && kind !== 'page'", "exit: false"),
    ("fullscreen no-op", "const f = el && (el.requestFullscreen || el.webkitRequestFullscreen)", "const f = null"),
    ("Escape ignored", "if (ev && ev.key === 'Escape') { immersive.set(false); fullscreenExit(globalThis.document); if (automation.get().own) theaterManual.set(false) }", "if (false) { immersive.set(false); fullscreenExit(globalThis.document); if (automation.get().own) theaterManual.set(false) }"),
    ("fullscreen stays a one-way door", "? fullscreenExit(d) : (el ? fullscreenRequest(el) : false)", "? fullscreenRequest(el) : (el ? fullscreenRequest(el) : false)"),
    # --- one surface ----------------------------------------------------------
    ("dock registered as a route page", "area: PANES_AREA, title: NAME", "area: 'routes', title: NAME"),
    ("pointercancel dropped", "ctx.addEventListener(globalThis, 'pointercancel', onPointerCancel)", "0 && ctx.addEventListener(globalThis, 'pointercancel', onPointerCancel)"),
    ("size not persisted", "storage.set('size', s)", "0 && storage.set('size', s)"),
    ("frame hint removed", "frameHint(now)", "null /* frameHint removed */"),
    ("guest overlay ignores failure", "return failed ? 'hint' : 'stage'", "return 'stage'"),
    ("guest overlay always hints", "return failed ? 'hint' : 'stage'", "return 'hint'"),
    ("page loses its address bar", "const open = kind === 'page' || !immersive", "const open = !immersive"),
    ("stale fault survives a new url", "function clearGuestFault() { pageFault.set(false) }", "function clearGuestFault() {}"),
    ("fail listener dropped", "['did-fail-load', onFail]", "['did-fail-load', () => {}]"),
    ("abort counted as failure", "if (ev && ev.errorCode === -3) return", "if (false) return"),
    ("finish load keeps the failure", "pageFault.set(guestLoadFailed)", "pageFault.set(false)"),
    # --- restore, coercion and stepping (each pinned by an assertion above) ---
    ("theater restore passes a camelCase key", "st.removeProperty(cssName(k))", "st.removeProperty(k)"),
    ("theater ignores the dragged size", "if (rect && rect.w > 0 && rect.h > 0) {", "if (false) {"),
    ("theater drag targets the card wrapper", "const card = theater ? root : (root.closest ? root.closest('[data-floating-pane]') : null)", "const card = root.closest ? root.closest('[data-floating-pane]') : null"),
    ("theater drag forgets the size", "writeTheaterSize(settingsStore, theaterRect)", "0 && writeTheaterSize(settingsStore, theaterRect)"),
    ("escape only exits focus mode", "if (msg === '__md:escape') { exitFocus(); unstick() }", "if (msg === '__md:escape') { exitFocus() }"),
    ("button name comes from the tooltip", "onClick, title, 'aria-label': label, children: label })", "onClick, title, 'aria-label': title, children: label })"),
    ("start gate ignores the settle window", "  if (!s.waited) return false\n  return !!s.paused && !(Number(s.t) > 0.25)", "  return !!s.paused && !(Number(s.t) > 0.25)"),
    ("start gate claims a paused file", "return !!s.paused && !(Number(s.t) > 0.25)", "return !(Number(s.t) > 0.25)"),
    ("guest back to absolute inset", "const guestStyle = { flex: '1 1 auto', width: '100%', height: '100%', minHeight: 0, border: 0, background: V.editor }", "const guestStyle = { position: 'absolute', inset: 0, border: 0, background: V.editor }"),
    ("stage floor restored", "style: { flex: '1 1 auto', minHeight: 0, position: 'relative', display: 'flex', overflow: 'hidden', background: V.editor }", "style: { flex: '1 1 auto', minHeight: 220, position: 'relative', display: 'flex', overflow: 'hidden', background: V.editor }"),
    ("host:port read as a scheme", "if (scheme && !/^\\d+([/?#]|$)/.test(text.slice(scheme[0].length))) return text", "if (scheme) return text"),
    ("off-ladder rate falls back to the first preset", "return RATES.find((x) => x > r + 0.001) || RATES[0]", "return RATES[(Math.max(0, RATES.indexOf(r)) + 1) % RATES.length]"),
    ("failed load keeps the navigation intent", "    navIntent = null\n    guestLoadFailed = true", "    guestLoadFailed = true"),
    # --- generic isolated guest ---------------------------------------------
    ("guest demoted to iframe", "jsx('webview', {", "jsx('iframe', {"),
    ("guest shares app preview partition", "const GUEST_PARTITION = 'persist:media-dock'", "const GUEST_PARTITION = 'persist:hermes-preview'"),
    ("guest src rewritten", "src: now.src, partition: GUEST_PARTITION", "src: now.pageUrl + '?embed=1', partition: GUEST_PARTITION"),
    ("guest widens privileges", "style: guestStyle }),", "style: guestStyle, allowpopups: true }),"),
    ("address bar keeps the paste", "if (cur.pageUrl !== url || cur.raw !== url)", "if (cur.pageUrl !== url)"),
    # --- theater automation: config-driven, reactive, OS-agnostic --------------
    ("theater ignores disable", "return s.enabled && s.busy ? 'theater' : 'normal'", "return s.busy ? 'theater' : 'normal'"),
    ("theater ignores manual off", "if (s.manual === false) return 'normal'", "if (false) return 'normal'"),
    ("theater needs no agent", "return s.enabled && s.busy ? 'theater' : 'normal'", "return s.enabled ? 'theater' : 'normal'"),
    ("theater ignores media", "if (!s || !s.hasMedia) return 'off'", "if (!s) return 'off'"),
    ("plan writes every tick", "changed: own !== !!(prev && prev.own)", "changed: true"),
    ("plan never restores", "changed: own !== !!(prev && prev.own)", "changed: own && !(prev && prev.own)"),
    ("inset magic-number baked", "inset: 24,", "inset: 0,"),
    ("overlay pins the whole pane, not the player", "const el = plan.own ? theaterHandle() :", "const el = false ? theaterHandle() :"),
    ("overlay ignores inset", "st.left = st.right = st.bottom = t.inset + 'px'; st.top = t.inset + t.rail + 'px'", "st.left = st.right = st.bottom = '0px'; st.top = '0px'"),
    ("stage covers the rail", "st.left = t.inset + 'px'; st.top = t.inset + t.rail + 'px'", "st.left = t.inset + 'px'; st.top = t.inset + 'px'"),
    ("enter never flushes the start box", "if (b0 && b0.width > 0 && el.getBoundingClientRect) void el.getBoundingClientRect()", "if (b0 && b0.width > 0) void st.width"),
    ("rail loses its right edge", "left: THEATER_CFG.inset + 'px', right: THEATER_CFG.inset + 'px', height: THEATER_CFG.rail + 'px'", "left: THEATER_CFG.inset + 'px', height: THEATER_CFG.rail + 'px'"),
    ("restore leaves empty strings", "else if (typeof st.removeProperty === 'function') st.removeProperty(cssName(k)); else delete st[k]", "else st[k] = ''"),
    ("restore skipped entirely", "if (!theaterSaved || theaterSaved.el !== el) return false", "return false"),
    ("caps trusts non-atom", "typeof a.subscribe === 'function'", "true"),
    ("automation polls instead of subscribing", "host.state.busy.subscribe(autoTick)", "0 && host.state.busy.subscribe(autoTick)"),
    ("dispose does not unsubscribe", "for (const off of autoStops) { if (typeof off === 'function') off() }", "void autoStops"),
    ('persist config not frozen', "export const THEATER_PERSIST = Object.freeze({ agent: 'agent', window: 'window' })", "export const THEATER_PERSIST = { agent: 'agent', window: 'window' }"),
    ('persist default inverted', 'theaterPersist: THEATER_PERSIST.agent', 'theaterPersist: THEATER_PERSIST.window'),
    ('persist value unvalidated', 'THEATER_PERSISTS.indexOf(s.theaterPersist) >= 0 ? s.theaterPersist : SETTINGS_DEFAULTS.theaterPersist', 's.theaterPersist || SETTINGS_DEFAULTS.theaterPersist'),
    ('persist latch removed', "const hold = !own0 && !!s && s.enabled && s.hasMedia && s.persist === THEATER_PERSIST.window && s.manual == null && !!(prev && prev.own)", "const hold = false"),
    ('persist opens from cold idle', "&& s.manual == null && !!(prev && prev.own)", "&& s.manual == null"),
    ('persist ignores manual exit', "const hold = !own0 && !!s && s.enabled && s.hasMedia && s.persist === THEATER_PERSIST.window && s.manual == null && !!(prev && prev.own)", "const hold = !own0 && !!s && s.enabled && s.hasMedia && s.persist === THEATER_PERSIST.window && !!(prev && prev.own)"),
    ('persist ignores media', "s.enabled && s.hasMedia && s.persist === THEATER_PERSIST.window", "s.enabled && s.persist === THEATER_PERSIST.window"),
    ('persist setting not wired to controller', 'persist: cfg.theaterPersist || SETTINGS_DEFAULTS.theaterPersist', 'persist: SETTINGS_DEFAULTS.theaterPersist'),
    ('persist choice not offered', "{ kind: 'choice', key: 'theaterPersist', label: 'Stay open'", "{ kind: 'choice', key: 'theaterPersist', label: 'Hidden'"),
    ('pre-parsed visit shortcut diverges', "const parsed = pre || parseMediaUrl(raw)",
     "const parsed = pre ? { ...pre, hostname: 'mutant' } : parseMediaUrl(raw)"),
    # --- part 5: other-chat completion toasts -----------------------------------
    ('terminal pair widened', "Object.freeze(['message.complete', 'error'])", "Object.freeze(['message.complete', 'error', 'message.delta'])"),
    ('replayed frame fires', "if (ev.replayed) return { show: false, reason: 'replayed' }", "if (false) return { show: false, reason: 'replayed' }"),
    ('focused runtime toasts', "if (s.focusedRuntime && rid === String(s.focusedRuntime)) return { show: false, reason: 'focused' }", "if (false) return { show: false, reason: 'focused' }"),
    ('unmapped snap fabricated', "if (!sid) return { show: false, reason: 'unmapped' }", "if (false) return { show: false, reason: 'unmapped' }"),
    ('focused stored toasts', "if (s.focusedStored && sid === String(s.focusedStored)) return { show: false, reason: 'focused' }", "if (false) return { show: false, reason: 'focused' }"),
    ('opt-in ignored', "if (!ev || !s || !s.enabled) return { show: false, reason: 'disabled' }", "if (!ev || !s) return { show: false, reason: 'disabled' }"),
    ('snap uses runtime id', "onClick: () => snapToChat(d.storedId)", "onClick: () => snapToChat(ev.session_id)"),
    ("snap plan forgets the collapse", "return { exit: !!own, collapse: !own }", "return { exit: !!own, collapse: false }"),
    ('mapping maps runtime to itself', "next[String(a)] = String(b)", "next[String(a)] = String(a)"),
    ('duplicate frame double-toasts', "if (key === completionLast) return", "if (false) return"),
    ('completion setting not validated', "completionToasts: typeof s.completionToasts === 'boolean' ? s.completionToasts : SETTINGS_DEFAULTS.completionToasts", "completionToasts: s.completionToasts || SETTINGS_DEFAULTS.completionToasts"),
    ('completion default inverted', "completionToasts: false,", "completionToasts: true,"),
    ('completion choice not offered', "label: 'Other-chat completions'", "label: 'Hidden'"),
    ('mapping refresh not subscribed', "ctx.onEvent('sessions.changed', refreshCompletionMap)", "0 && ctx.onEvent('sessions.changed', refreshCompletionMap)"),
    ('completion subscriptions not disposed', "for (const off of completionStops) { if (typeof off === 'function') off() }", "void completionStops"),
    # --- part 1: picked chats ----------------------------------------------------
    ('gate ignores scope', "if (scope !== 'picked') return { show: true, reason: 'all' }", "if (false) return { show: true, reason: 'all' }"),
    ('gate fails closed on no focused id', "if (!sid) return { show: true, reason: 'no-focused' }", "if (!sid) return { show: false, reason: 'no-focused' }"),
    ('gate inverts membership', "return list.indexOf(sid) >= 0 ? { show: true, reason: 'picked' } : { show: false, reason: 'not-picked', storedId: sid }", "return list.indexOf(sid) >= 0 ? { show: false, reason: 'picked' } : { show: true, reason: 'not-picked', storedId: sid }"),
    ('gate ignores the picked list', "const list = Array.isArray(picked) ? picked : []", "const list = []"),
    ('gate drops durable id', "{ show: false, reason: 'not-picked', storedId: sid }", "{ show: false, reason: 'not-picked', storedId: null }"),
    ('sessionScope default inverted', "sessionScope: 'all',", "sessionScope: 'picked',"),
    ('sessionScope unvalidated', "SESSION_SCOPES.indexOf(s.sessionScope) >= 0 ? s.sessionScope : SETTINGS_DEFAULTS.sessionScope", "s.sessionScope || SETTINGS_DEFAULTS.sessionScope"),
    ('pick does not toggle', "cur.indexOf(id) >= 0 ? cur.filter((x) => x !== id) : [id, ...cur].slice(0, PICK_MAX)", "[id, ...cur].slice(0, PICK_MAX)"),
    ('picked changes not persisted', "picked.subscribe ? picked.subscribe((list) => writeList(ctx, 'pickedSessions', list, PICK_MAX)) : null", "null"),
    ('focused stored not subscribed', "host.state.focusedStoredSessionId.subscribe(() => focusedStored.set(host.state.focusedStoredSessionId.get()))", "0 && host.state.focusedStoredSessionId.subscribe(() => focusedStored.set(host.state.focusedStoredSessionId.get()))"),
    ('session subscriptions not disposed', "for (const off of sessionStops) { if (typeof off === 'function') off() }", "void sessionStops"),
    ('gate well never shown', "gate.show ? null : jsx('div', { style: { position: 'absolute', inset: 0, zIndex: 40, display: 'flex', background: V.editor }", "true ? null : jsx('div', { style: { position: 'absolute', inset: 0, zIndex: 40, display: 'flex', background: V.editor }"),
    ('Show here does not pick', "chromeBtn('Show here', () => pickSession(id))", "chromeBtn('Show here', () => {})"),
    ('Show everywhere does not reset', "chromeBtn('Show everywhere', () => patchSettings({ sessionScope: 'all' }))", "chromeBtn('Show everywhere', () => {})"),
    ('pin command missing id', "run: () => pickSession(focusedStored.get())", "run: () => pickSession(null)"),
    ('sessions settings page hidden', "{ id: 'sessions', title: 'Sessions'", "{ id: 'hidden-sessions', title: 'Hidden'"),
    # --- queue ---------------------------------------------------------------
    ('shuffle can stay identical', "if (a.length > 1 && a.every((p, i) => p === pins.get()[i])) { const x = a[0]; a[0] = a[1]; a[1] = x }", "0"),
    ('row Enter fires on a control', "onKeyDown: (e) => { if (rowEnterOpens(e)) onOpen(p.url) }", "onKeyDown: (e) => { if (e && e.key === 'Enter') onOpen(p.url) }"),
    ('add current reorders a queued row', "onClick: () => { if (!inList) (shelfMode ? saveToShelf : onAdd)() }", "onClick: () => { (shelfMode ? saveToShelf : onAdd)() }"),
]


def build():
    (WORK / "node_modules/react").mkdir(parents=True, exist_ok=True)
    (WORK / "node_modules/@hermes/plugin-sdk").mkdir(parents=True, exist_ok=True)
    (WORK / "node_modules/react/package.json").write_text(json.dumps({
        "name": "react", "version": "0.0.0-stub", "type": "module",
        "exports": {".": "./index.js", "./jsx-runtime": "./jsx-runtime.js"}}), encoding="utf-8")
    (WORK / "node_modules/react/index.js").write_text(REACT, encoding="utf-8")
    (WORK / "node_modules/react/jsx-runtime.js").write_text(JSX_RUNTIME, encoding="utf-8")
    (WORK / "node_modules/@hermes/plugin-sdk/package.json").write_text(json.dumps({
        "name": "@hermes/plugin-sdk", "version": "0.0.0-stub", "type": "module",
        "main": "index.js"}), encoding="utf-8")
    (WORK / "node_modules/@hermes/plugin-sdk/index.js").write_text(SDK, encoding="utf-8")
    (WORK / "harness.mjs").write_text(HARNESS, encoding="utf-8")


def run_node(target_text, filename="under-test.mjs"):
    path = WORK / filename
    path.write_text(target_text, encoding="utf-8")
    proc = subprocess.run(
        [shutil.which("node") or "node", "harness.mjs", str(path)],
        capture_output=True, text=True, cwd=str(WORK), timeout=120, check=False,
    )
    return proc.returncode == 0, (proc.stdout + proc.stderr).strip()


def static_contract(text):
    """Named no-claim boundaries the behavior assertions cannot reach.

    Each rule forbids a CLASS of implementation (a per-site branch, an OS probe,
    a polling loop, a widened guest, a bare global listener). Exact declaration
    spellings, variable names, and string-presence pins were change-detectors and
    were removed: every one is covered by a HARNESS behavior assertion that fails
    on the same regression without pinning how the code is spelled.
    """
    problems = []
    # The agent is page-side code by design (it runs in the guest document).
    host = re.sub(r"const AGENT_SRC = `.*?`\n", "", text, flags=re.S)
    specs = re.findall(r"from\s+['\"]([^'\"]+)['\"]", text) + re.findall(r"import\s+['\"]([^'\"]+)['\"]", text)
    allowed = {"@hermes/plugin-sdk", "react", "react/jsx-runtime"}
    for s in specs:
        if s not in allowed:
            problems.append("unsupported import specifier: " + s)
    if re.search(r"^import\s", text, re.MULTILINE) is None:
        problems.append("no imports found")
    if re.search(r"#[0-9a-fA-F]{3,8}\b|rgba?\(", text):
        problems.append("hardcoded color literal")
    for tok in ("youtube", "twitch", "youtu.be", "nocookie", "player.twitch",
                "127.0.0.1", "getEmbedHostOrigin", "WRAP_ORIGIN", "embedHost",
                "youtubePlayerSrc", "twitchPlayerSrc", "pageGuest", "twitchGuest"):
        if tok.lower() in text.lower():
            problems.append("per-site literal in renderer: " + tok)
    # One generic top-level guest for ALL page URLs: never a framable frame,
    # never the app's preview partition, never widened Electron privileges.
    if not re.search(r"jsx\('webview'", text):
        problems.append("page URLs must render a top-level <webview> guest")
    if re.search(r"persist:hermes-preview|preview guest|jsx\('iframe'|SandboxedFrame", text, re.IGNORECASE):
        problems.append("guest escapes isolation: preview partition or framable frame fallback")
    for tok in ("allowpopups", "nodeintegration", "webpreferences"):
        if tok.lower() in text.lower():
            problems.append("guest widens Electron privileges: " + tok)
    # A <webview preload> is REFUSED outright now: the host evaluates this module
    # from a blob: URL, so a relative preload path cannot resolve and a preload
    # would silently never run (that was the "no transport" defect). The page agent
    # is injected instead — one generic agent, no per-site script.
    if re.search(r"preload:\s", text):
        problems.append("guest must carry no preload: it cannot resolve from a blob: module")
    if "AGENT_SRC" not in text or not re.search(r"executeJavaScript\(\s*AGENT_SRC\s*\)", text):
        problems.append("page agent must be injected into the guest with executeJavaScript")
    if re.search(r"window\.(addEventListener|setInterval|setTimeout)|document\.(querySelector|body|createElement)", host):
        problems.append("bare global listener / DOM reach-in")
    if "'#000'" in text or '"#000"' in text or "'black'" in text:
        problems.append("hardcoded black")
    if re.search(r"paneOpen:\s*true", text) or "paneOpen !== false" in text:
        problems.append("pane must not default open")
    for tok in ("process.platform", "navigator.platform", "navigator.userAgent",
                "os.platform", "screen.width", "screen.height", "app.getPath",
                "requestSingleInstanceLock", "powerMonitor"):
        if tok in text:
            problems.append("OS-specific probe in renderer (must be OS-agnostic): " + tok)
    if re.search(r"\brequestAnimationFrame\(", host):
        problems.append("automation must be reactive subscriptions, not animation-frame polling")
    if len(re.findall(r"\bsetInterval\(", host)) > 1 or ("setInterval(" in host and "clearInterval(" not in host):
        problems.append("the guest read is ONE bounded interval, cleared on detach")
    # Cap raised 1500 -> 1700 (gain stage + captions) -> 1800 (one transport rail for both
    # guests) -> 1850 (the saved shelf shares the queue panel: two views, one component).
    # sources). One file, no new imports, loader limit 16 MiB: this is a readability budget
    # held by subtraction, not a wall. Keep it tight; do not grow past it without a cut.
    # A live stream has no authored timeline. The rail must show a label and the page rail must
    # pass the flag the agent reports; a scrubber over an unseekable element is a dead control.
    if not re.search(r"live \? jsx\('span'", text) or not re.search(r"children: live \? formatTime\(at\)", text):
        problems.append("a live stream must show LIVE, not a seek bar that cannot seek")
    if "live: !!m.live" not in text:
        problems.append("the page rail must pass the live flag it read from the guest element")
    # Electron's UA token is an unknown browser: Twitch answered with its MOBILE site (m.twitch.tv).
    if "useragent: GUEST_UA" not in text or not re.search(r"const GUEST_UA = 'Mozilla/5\.0 \(Windows NT", text):
        problems.append("guest must carry a desktop UA — Electron's token served m.twitch.tv")
    if len(text.splitlines()) > 1900:
        problems.append("plugin.js exceeds the 1900-line cap")
    return problems

def check(plugin_js, mutate=True):
    text = pathlib.Path(plugin_js).read_text(encoding="utf-8")
    problems = static_contract(text)
    build()
    ok, out = run_node(text)
    report = [out]
    if problems:
        report.insert(0, "STATIC CONTRACT FAILURES:")
        report[1:1] = ["   - " + p for p in problems]
        ok = False
    if mutate and ok:
        for name, old, new in MUTATIONS:
            if old not in text:
                report.append("   ! mutation anchor missing (skipped): " + name)
                ok = False
                continue
            m_ok, _m_out = run_node(text.replace(old, new, 1), "mutant.mjs")
            if m_ok:
                report.append("   ! MUTANT SURVIVED: " + name + " — assertions are too weak")
                ok = False
            else:
                report.append("   mutant caught: " + name)
    return ok, "\n".join(report)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    mutate = "--no-mutate" not in sys.argv
    root = pathlib.Path(__file__).resolve().parents[1]
    target = pathlib.Path(args[0]) if args else root / "desktop" / "plugin.js"
    good, out = check(target, mutate=mutate)
    print(out)
    raise SystemExit(0 if good else 1)