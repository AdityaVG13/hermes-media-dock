// media-dock: standalone Hermes Desktop plugin (disk door, ONE ESM file). Contract: hermes-agent.nousresearch.com/docs/developer-guide/desktop-plugin-sdk * only @hermes/plugin-sdk + react* resolve; a sibling import fails the load, so this file cannot be split. Under the 1,850-line cap, held by subtraction (the SDK forbids splitting). * no JSX (loaded uncompiled): jsx()/jsxs() from react/jsx-runtime. * no core patching, no hardcoded colors, tracked listeners via ctx.*. * a guest load failure is a named hint; a working page is the stage, with our chrome receded. * resize paints the host [data-floating-pane] frame; it never re-registers, because a remount drops pointer capture AND restarts our media element.
import * as SDK from '@hermes/plugin-sdk'
import { useEffect, useRef, useState } from 'react'
import { jsx, jsxs } from 'react/jsx-runtime'
// ------------------------------------------------------------------ sdk aliases
const atom = SDK.atom
const useValue = SDK.useValue
const host = SDK.host
const PANES_AREA = SDK.PANES_AREA || 'panes'
const PALETTE_AREA = SDK.PALETTE_AREA || 'palette'
const KEYBINDS_AREA = SDK.KEYBINDS_AREA || 'keybinds'
const STATUS_RIGHT = (SDK.STATUSBAR_AREAS && SDK.STATUSBAR_AREAS.right) || 'statusBar.right'
const Button = SDK.Button || null
const Codicon = SDK.Codicon || null
const MessageTextContent = SDK.MessageTextContent || null
const useTheme = SDK.useTheme || (() => ({ themeName: '', resolvedMode: '' }))
const ID = 'media-dock'
const NAME = 'Media Dock'
const PANE_ID = ID + ':card'
// The floating card is its OWN id: flipping placement on one id left the old surface on screen (or evicted it), so two ids exist and the dead one is evicted on every flip.
const FLOAT_ID = ID + ':float'
// One generic TOP-LEVEL guest per http(s) URL, plugin-owned persist partition: sign-ins
// stay in this machine's app data, and not being an iframe no per-site rule is needed.
const GUEST_PARTITION = 'persist:media-dock'
// Electron's UA token reads as an unknown browser: a live-streaming site answered with its MOBILE page. A desktop Chromium string is a compatibility literal, not an OS probe: nothing branches on it.
export const GUEST_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
// The page agent is INJECTED, never a `<webview preload>`: modules load from a blob: URL, so
// './guest.js' resolved to nothing and no transport appeared. Any player is a media element.
const AGENT_SRC = `(() => { if (window.__mdAgent) return 'ok'
  const pick = () => { let b = null, s = -1; for (const el of document.querySelectorAll('video,audio')) { const v = (el.paused ? 0 : 4e9) + (el.duration > 0 ? 1e9 : 0) + el.offsetWidth * el.offsetHeight; if (v > s) { s = v; b = el } } return b }
  // A cross-origin element goes permanently silent the instant it is routed through Web
  // Audio, so the source is classified BEFORE a gain node exists: boost is then a named
  // refusal, never a quiet mute. blob:/data: sources (every MSE site) are same-origin.
  const safe = (u) => { try { const x = new URL(u || '', location.href); return x.protocol === 'blob:' || x.protocol === 'data:' || x.origin === location.origin } catch (e) { return false } }
  const gainOf = (el) => { if (el.__mdG) return el.__mdG; const C = window.AudioContext || window.webkitAudioContext; if (!C) return null
    try { const ctx = new C(), g = ctx.createGain(), s = ctx.createMediaElementSource(el); s.connect(g); g.connect(ctx.destination); el.__mdG = { ctx, g }; return el.__mdG } catch (e) { return null } }
  // 0-100 is the element's own volume (no graph at all); 101-300 adds a gain stage on top.
  const level = (el, v) => { const n = Math.max(0, Math.min(300, Math.round(Number(v) || 0)))
    if (n > 100) { if (!safe(el.currentSrc || el.src)) return { ok: false, why: 'this source is cross-origin, so boost would silence it' }
      const o = gainOf(el); if (!o) return { ok: false, why: 'this page has no Web Audio' }
      try { if (o.ctx.state !== 'running') o.ctx.resume() } catch (e) {}
      el.volume = 1; el.muted = false; o.g.gain.value = n / 100 }
    else { el.volume = n / 100; el.muted = n === 0; if (el.__mdG) { try { el.__mdG.g.gain.value = 1 } catch (e) {} } }
    return { ok: true } }
  const cue = (el, i) => { if (!el || i < 0) return ''
    try { const t = el.textTracks[i]; if (!t || !t.activeCues) return ''
      for (let k = 0; k < t.activeCues.length; k++) { const s = String(t.activeCues[k].text || ''); if (s) return s } } catch (e) {} return '' }
  const track = (el, i) => { try { return el && el.textTracks && el.textTracks[i] ? String(el.textTracks[i].language || '') : '' } catch (e) { return '' } }
  const state = () => { const el = pick(); if (!el) return { has: false, trk: 0 }
    const d = Number(el.duration), g = el.__mdG, boosted = !!(g && g.g.gain.value > 1.0001), i = el.__mdSel == null ? -1 : el.__mdSel
    return { has: true, paused: !!el.paused, live: d === Infinity, t: Number(el.currentTime) || 0, d: isFinite(d) && d > 0 ? d : 0,
      v: Math.round((boosted ? g.g.gain.value : (Number(el.volume) || 0)) * 100), muted: !!el.muted, r: Number(el.playbackRate) || 1,
      trk: el.textTracks ? el.textTracks.length : 0, sel: i, lang: track(el, i), cue: cue(el, i),
      boost: boosted, can: safe(el.currentSrc || el.src) } }
  // A guest owns its keyboard: Tab wraps inside the page and Escape never reaches the plugin.
  // Report the boundary key on console, the one channel a webview exposes without a preload.
  const FOCUSABLE = 'a[href],button,input,select,textarea,video[controls],audio[controls],[tabindex]:not([tabindex="-1"])'
  window.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !e.defaultPrevented) { console.log('__md:escape'); return }
    if (e.key !== 'Tab' || e.defaultPrevented || e.altKey || e.ctrlKey || e.metaKey) return
    const items = Array.prototype.filter.call(document.querySelectorAll(FOCUSABLE), (n) => !n.disabled && (n === document.activeElement || n.offsetParent !== null || n.getClientRects().length > 0)), i = items.indexOf(document.activeElement)
    if (i >= 0 && (e.shiftKey ? i === 0 : i === items.length - 1)) { e.preventDefault(); console.log(e.shiftKey ? '__md:tab-back' : '__md:tab-out') }
  }, true)
  window.__mdAgent = { v: 2, state,
    tracks() { const el = pick(), out = []
      if (el && el.textTracks) for (let i = 0; i < el.textTracks.length; i++) out.push({ i, label: String(el.textTracks[i].label || el.textTracks[i].language || ('Track ' + (i + 1))), lang: String(el.textTracks[i].language || ''), kind: String(el.textTracks[i].kind || '') })
      return { tracks: out } },
    cmd(op, v) { const el = pick(); if (!el) return { has: false }; let why = ''
      try {
        if (op === 'play' || (op === 'toggle' && el.paused)) { const p = el.play(); if (p && p.catch) p.catch(() => {}) }
        else if (op === 'pause' || op === 'toggle') el.pause()
        else if (op === 'seek' && isFinite(v)) el.currentTime = Math.max(0, v)
        else if (op === 'level') { const r = level(el, v); why = r.ok ? '' : r.why }
        else if (op === 'mute' && isFinite(v)) { el.muted = v !== 0; if (!el.muted && !(el.volume > 0)) el.volume = 1 }
        else if (op === 'rate' && isFinite(v)) el.playbackRate = Math.min(4, Math.max(0.25, v))
        else if (op === 'track') { const i = Math.round(Number(v)); el.__mdSel = i >= 0 ? i : -1
          try { for (let k = 0; k < el.textTracks.length; k++) el.textTracks[k].mode = k === i ? 'hidden' : 'disabled' } catch (e) {} }
      } catch (x) {} const s = state(); if (why) s.why = why; return s } }
  return 'ok' })()`
// `has:false` is a real answer (no media on this page), never a missing value.
const pageMedia = atom({ has: false })
const navState = atom({ back: false, fwd: false, loading: false })
let guestEl = null
let guestVolInit = false
let guestResumed = false
let guestPoll = 0
export function pageMediaState(m) {
  const n = (v, lo, hi, d) => { const x = Number(v); return isFinite(x) ? Math.min(hi, Math.max(lo, x)) : d }
  if (!m || !m.has) return { has: false }
  return { has: true, paused: !!m.paused, live: m.live === true, t: n(m.t, 0, 86400, 0), d: n(m.d, 0, 86400, 0), v: Math.round(n(m.v, 0, 300, 100)), muted: !!m.muted, r: n(m.r, 0.25, 4, 1),
    boost: !!m.boost, can: m.can !== false, why: m.why ? String(m.why) : '' }
}
// A new object per poll is a new atom value: subscribers re-render even when every
// field is identical. The poll is half-second and the page can sit paused for hours.
export function samePageMedia(a, b) {
  return !!a && !!b && a.has === b.has && a.paused === b.paused && a.t === b.t && a.d === b.d && a.v === b.v
    && a.muted === b.muted && a.r === b.r && a.boost === b.boost && a.can === b.can && a.why === b.why
}
function sendGuest(op, value, done) {
  const el = guestEl; if (!el || typeof el.executeJavaScript !== 'function') return false
  const v = value === undefined ? 0 : (Number(value) || 0)
  try {
    const p = el.executeJavaScript('window.__mdAgent && window.__mdAgent.cmd(' + JSON.stringify(op) + ',' + v + ')')
    if (p && p.catch) p.catch(() => {})
    if (p && p.then && done) p.then((s) => { if (s) done(s) }, () => {})
    return true
  } catch { return false }
}
function guestEval(js) {
  const el = guestEl; if (!el || typeof el.executeJavaScript !== 'function') return Promise.resolve(null)
  try { return Promise.resolve(el.executeJavaScript(js)).catch(() => null) } catch { return Promise.resolve(null) }
}
// One caption model for both transports. `owner` says whose track list it is, so a page switch never leaves the native player reading a stale page subtitle.
const captions = atom({ owner: '', tracks: [], sel: -1, lang: '', cue: '', target: '', why: '' })
function setCaps(patch) { captions.set({ ...captions.get(), ...patch }) }
let guestTrackAt = 0
function loadGuestTracks() {
  const now = Date.now(); if (now - guestTrackAt < 1500) return
  guestTrackAt = now
  guestEval('window.__mdAgent ? window.__mdAgent.tracks() : null').then((r) => { if (r && r.tracks) setCaps({ owner: 'page', tracks: r.tracks }) })
}
// Caption translation: one cue at a time to a public, keyless endpoint. Both endpoints answer
// with Access-Control-Allow-Origin: *, so the pane's own fetch works from the renderer; the
// earlier path needed Chromium's on-device Translator, which this build does not expose.
const trCache = new Map()
let trKey = '', trWhy = '', trBusy = false
async function trOnce(src, tgt, text, signal) {
  const g = 'https://translate.googleapis.com/translate_a/single?client=gtx&dt=t'
    + '&sl=' + encodeURIComponent(src || 'auto') + '&tl=' + encodeURIComponent(tgt) + '&q=' + encodeURIComponent(text)
  try {
    const r = await fetch(g, { signal })
    if (r.ok) {
      const j = await r.json()
      const out = (Array.isArray(j && j[0]) ? j[0] : []).map((s) => (s && s[0]) || '').join('').trim()
      if (out) return out
    }
  } catch { /* the second endpoint answers */ }
  const m = 'https://api.mymemory.translated.net/get?q=' + encodeURIComponent(text)
    + '&langpair=' + encodeURIComponent((src || 'en') + '|' + tgt)
  const r2 = await fetch(m, { signal })
  if (!r2.ok) throw new Error('HTTP ' + r2.status)
  const j2 = await r2.json()
  const out2 = j2 && j2.responseData ? String(j2.responseData.translatedText || '').trim() : ''
  if (!out2 || /MYMEMORY WARNING/i.test(out2)) throw new Error('no answer')
  return out2
}
function translationOf(text) {
  const c = captions.get()
  const tgt = c.target
  if (!text || !tgt || String(text).trim().length < 2) return ''
  const k = (c.lang || 'auto') + '|' + tgt + '|' + text
  const hit = trCache.get(k); if (hit) return hit
  if (trKey !== k && !trBusy) {
    trKey = k; trBusy = true
    // A cue is one line. A request that never answers must time out AND release the latch:
    // the 15 s message alone left trBusy true, so every later cue was refused for the life
    // of the pane. AbortController is the exit; the timer clears the latch if it is absent.
    const ctl = typeof AbortController === 'function' ? new AbortController() : null
    const timer = setTimeout(() => { if (ctl) ctl.abort(); else { trWhy = 'translation timed out'; trBusy = false } }, 15000)
    Promise.resolve().then(async () => {
      try {
        const out = await trOnce(c.lang || '', tgt, text, ctl ? ctl.signal : undefined)
        trCache.set(k, out)
        if (trCache.size > 400) trCache.clear()
        trWhy = ''
        if (captions.get().cue === text) setCaps({})
      } catch (e) { trWhy = e && e.name === 'AbortError' ? 'translation timed out' : 'translation failed: ' + (e && e.message ? e.message : e) }
      finally { clearTimeout(timer); trBusy = false }
    })
  }
  return ''
}
// The agent has no IPC channel, so the host reads it: one bounded half-second poll.
function stopPoll() { if (guestPoll) { clearInterval(guestPoll); guestPoll = 0 } }
function readGuest() {
  const el = guestEl; if (!el || typeof el.executeJavaScript !== 'function') return
  try {
    el.executeJavaScript('window.__mdAgent ? window.__mdAgent.state() : null').then((raw) => {
      if (!raw) return
      const s = pageMediaState(raw); if (!samePageMedia(pageMedia.get(), s)) pageMedia.set(s)
      if (s.has && !guestVolInit) { guestVolInit = true; sendGuest('level', settings.get().volume) }
      if (s.has) {
        const c = captions.get(), sel = raw.sel == null ? -1 : raw.sel
        if (c.owner !== 'page' || c.sel !== sel || (raw.trk || 0) !== c.tracks.length || (raw.cue || '') !== c.cue) {
          setCaps({ owner: 'page', sel, lang: raw.lang || '', cue: raw.cue || '', why: raw.why || '' })
          if ((raw.trk || 0) !== c.tracks.length) loadGuestTracks()
        }
      }
      if (!s.has) return
      const url = play.get().pageUrl
      if (!guestResumed && s.d > 0) { guestResumed = true; const at = Number(progress.get()[url]) || 0; if (at > 3 && at < s.d - 5) sendGuest('seek', at) }
      if (s.paused) remember(url, s.t, s.d)
    }, () => {})
  } catch { /* guest gone */ }
}
function pageHost(url) { try { return new URL(url).hostname } catch { return '' } }
function syncNav(el, loading) {
  const e = el || guestEl
  const cur = navState.get()
  let back = false, fwd = false
  if (e) { try { back = !!e.canGoBack(); fwd = !!e.canGoForward() } catch { /* not ready */ } }
  const next = { back, fwd, loading: loading === undefined ? cur.loading : !!loading }
  if (cur.back !== next.back || cur.fwd !== next.fwd || cur.loading !== next.loading) navState.set(next)
}
function navGo(dir) {
  const e = guestEl
  if (!e) return false
  try {
    if (dir < 0 && e.canGoBack && e.canGoBack()) { e.goBack(); return true }
    if (dir > 0 && e.canGoForward && e.canGoForward()) { e.goForward(); return true }
  } catch { /* guest gone */ }
  return false
}
function reloadGuest() {
  const e = guestEl
  if (!e || typeof e.reload !== 'function') return false
  try { e.reload(); return true } catch { return false }
}
function stopGuest() {
  const e = guestEl
  if (!e || typeof e.stop !== 'function') return false
  try { e.stop(); return true } catch { return false }
}
function navBtn(mark, onClick, label, enabled, active) {
  return jsx('button', { type: 'button', title: label, 'aria-label': label, onClick, disabled: !enabled, style: { border: 0, background: 'transparent', color: enabled ? (active ? V.text : V.accent) : V.dim, opacity: enabled ? 1 : 0.35,
      width: 26, height: 28, padding: 0, borderRadius: 5, fontSize: 12, lineHeight: 1, cursor: enabled ? 'pointer' : 'default', flex: '0 0 auto' }, children: mark })
}
const PIN_MAX = 12
const SHELF_MAX = 40
const VISIT_MAX = 24
const SUGGEST_MAX = 6
const PICK_MAX = 32
// ------------------------------------------------------- geometry (pure, exported). Source-verified: no host API resizes a pane. The floating card is the host's [data-floating-pane] element with inline width/height from registration data. A direct DOM write survives re-renders while chrome size is unchanged. Anchors pin two edges; a top-right card grows toward its FREE bottom-left corner.
const CARD_ANCHOR = 'top-right'
const EDGES = Object.freeze({
  left: /left/.test(CARD_ANCHOR), right: /right/.test(CARD_ANCHOR), top: /top/.test(CARD_ANCHOR), bottom: /bottom/.test(CARD_ANCHOR),
})
const CARD_MIN = Object.freeze({ w: 380, h: 300 })
// ------------------------------------------------------------ theater automation. Theater is an OVERLAY of the player, not a resized dock: the host exposes only revealPane/removePane/undismissPane/paneVisibility, so a docked rail cannot be grown. Pinning the pane's own root to the window works from either placement, leaves the layout tree untouched, and restores the exact inline style it borrowed. No native fullscreen (macOS opens a new Space) and no second window.
export const THEATER_CFG = Object.freeze({ inset: 24, rail: 34, z: 2147482000 })
// Motion gate: starting a turn is not yet a reason to take the screen. Both edges wait,
// so a burst of turns cannot flash the player open and shut.
export const THEATER_GATE = Object.freeze({ enter: 3400, exit: 2200 })
const THEATER_EASE = 'cubic-bezier(.22,.75,.2,1)'
// How long theater survives a chat switch. Named values, never scattered strings.
export const THEATER_PERSIST = Object.freeze({ agent: 'agent', window: 'window' })
const THEATER_PERSISTS = Object.freeze(Object.keys(THEATER_PERSIST))
// null = follow the switch; true = the player's own toggle; false = left theater this turn.
export const theaterManual = atom(null)
// Enter on: media loaded, plus the player's toggle or the opt-in switch while a turn is busy.
export function theaterDecision(s) {
  if (!s || !s.hasMedia) return 'off'
  if (s.manual === true) return 'theater'
  if (s.manual === false) return 'normal'
  return s.enabled && s.busy ? 'theater' : 'normal'
}
// Change-driven: one DOM write per transition, zero work on unchanged ticks.
export function theaterPlan(prev, s) {
  const own0 = theaterDecision(s) === 'theater'
  // Hold-on: an idle tick keeps an overlay that already exists until something ends it.
  const hold = !own0 && !!s && s.enabled && s.hasMedia && s.persist === THEATER_PERSIST.window && s.manual == null && !!(prev && prev.own)
  const own = own0 || hold
  return { own, changed: own !== !!(prev && prev.own), mode: own ? 'theater' : 'normal' }
}
// A toast click frees the screen: theater restores itself, the plain dock collapses as before.
export function snapPlan(own) { return { exit: !!own, collapse: !own } }
// The inline style theater borrowed; restored verbatim so an exit cannot drift the pane.
const THEATER_KEYS = ['position', 'width', 'height', 'left', 'top', 'right', 'bottom', 'zIndex', 'borderRadius', 'border', 'transition', 'background']
let theaterSaved = null, theaterRect = null   // borrowed inline style / dragged box (null = fill)
let theaterHome = null, theaterExitTimer = 0  // pre-theater box / pending shrink-restore
export function applyTheaterPlan(plan, el, cfg, rect) {
  if (!plan || (!plan.changed && !(plan.own && theaterSaved && theaterSaved.el !== el)) || !el || !el.style) return false
  const t = cfg || THEATER_CFG, st = el.style
  if (plan.own) {
    if (theaterExitTimer) { globalThis.clearTimeout(theaterExitTimer); theaterExitTimer = 0; releaseTheaterStyle(st, theaterSaved); theaterSaved = null }
    if (!theaterSaved || theaterSaved.el !== el) theaterSaved = { el, keys: THEATER_KEYS.map((k) => [k, st[k] || '']) }
    // Normal flow cannot transition INTO a fixed box: pin it at the box it already occupies first.
    const b0 = el.getBoundingClientRect ? el.getBoundingClientRect() : null
    theaterHome = b0 && b0.width > 0 ? { left: b0.left, top: b0.top, width: b0.width, height: b0.height } : null
    if (b0 && b0.width > 0) { st.transition = 'none'; st.position = 'fixed'; st.left = b0.left + 'px'; st.top = b0.top + 'px'; st.width = b0.width + 'px'; st.height = b0.height + 'px'; st.right = st.bottom = 'auto' }
    // Reading the rect forces style+layout: `void st.width` does NOT flush, so the browser never
    // saw the start box and snapped into fullscreen instead of easing.
    if (b0 && b0.width > 0 && el.getBoundingClientRect) void el.getBoundingClientRect()
    st.transition = ['left .34s', 'top .34s', 'width .34s', 'height .34s'].map((k) => k + ' ' + THEATER_EASE).join(', ') + ', border-radius .34s ease, opacity .34s ease'
    // The surface carries an inline height:100%; keep it and the inset box overflows the
    // window's bottom edge (the footer lands below the screen). Both must go to auto.
    st.position = 'fixed'
    const vpW = Number(globalThis.innerWidth) || 0, vpH = Number(globalThis.innerHeight) || 0
    if (rect && rect.w > 0 && rect.h > 0) {
      const box = rect
      // A dragged size pins width/height; a left-over right/bottom would over-constrain the box.
      const w = vpW > 0 ? Math.max(CARD_MIN.w, Math.min(box.w, vpW - 2 * t.inset)) : box.w, h = vpH > 0 ? Math.max(CARD_MIN.h, Math.min(box.h, vpH - 2 * t.inset - t.rail)) : box.h
      st.width = Math.round(w) + 'px'; st.height = Math.round(h) + 'px'
      st.right = st.bottom = 'auto'
      st.left = t.inset + 'px'; st.top = t.inset + t.rail + 'px'
    } else { st.width = st.height = 'auto'; st.left = st.right = st.bottom = t.inset + 'px'; st.top = t.inset + t.rail + 'px' }
    st.zIndex = String(t.z)
    st.borderRadius = '10px'
    st.border = '1px solid ' + V.stroke
    st.background = V.editor
    return true
  }
  if (!theaterSaved || theaterSaved.el !== el) return false
  // Closing is a motion, not a disappearance: shrink to the box the pane came from, then
  // hand the inline style back. Restoring first would snap and skip the animation entirely.
  const home = theaterHome, saved = theaterSaved
  if (home && typeof globalThis.setTimeout === 'function' && plan.animate !== false) {
    st.transition = ['left .3s', 'top .3s', 'width .3s', 'height .3s'].map((k) => k + ' ' + THEATER_EASE).join(', ')
    st.left = home.left + 'px'; st.top = home.top + 'px'; st.width = home.width + 'px'; st.height = home.height + 'px'
    if (theaterExitTimer) globalThis.clearTimeout(theaterExitTimer)
    theaterExitTimer = globalThis.setTimeout(() => { theaterExitTimer = 0; releaseTheaterStyle(st, saved); theaterSaved = null; theaterHome = null }, 340)
    return true
  }
  releaseTheaterStyle(st, saved); theaterSaved = null; theaterHome = null; return true
}
// Hand back exactly the keys theater borrowed; a failed animation must not strand the box.
function releaseTheaterStyle(st, saved) {
  if (!saved || !st) return
  // removeProperty lowercases its argument: 'zIndex' -> 'zindex', not a property, so the call did
  // nothing and the pane kept the overlay's z-index/radius after exit. Translate the key first.
  for (const [k, v] of saved.keys) { if (v) st[k] = v; else if (typeof st.removeProperty === 'function') st.removeProperty(cssName(k)); else delete st[k] }
  return true
}

// Trust only real atoms/functions; older Desktop gets a named refusal.
export function automationCaps(hostLike, ctxLike) {
  const h = hostLike || {}
  const st = h.state || {}
  const isAtom = (a) => !!(a && typeof a.get === 'function' && typeof a.subscribe === 'function')
  return {
    busy: isAtom(st.busy), viewport: isAtom(st.viewport), focusedSession: isAtom(st.focusedStoredSessionId), anyBusy: isAtom(st.busyBySession),
    focusedRuntime: isAtom(st.focusedSessionId), request: typeof h.request === 'function', onEvent: !!(ctxLike && typeof ctxLike.onEvent === 'function'),
    notify: typeof h.notify === 'function', openSession: typeof h.openSession === 'function', }
}
// Terminal turn events are source-verified, not guessed: group-turns.ts:444/493 treats message.complete + error as the terminal pair; replayed frames are reconnect echoes (gateway-events.ts:60), never fresh work.
export const TERMINAL_EVENTS = Object.freeze(['message.complete', 'error'])
export function completionDecision(ev, s) {
  if (!ev || !s || !s.enabled) return { show: false, reason: 'disabled' }
  if (ev.replayed) return { show: false, reason: 'replayed' }
  if (TERMINAL_EVENTS.indexOf(ev.type) < 0) return { show: false, reason: 'not-terminal' }
  const rid = String(ev.session_id || '')
  if (!rid) return { show: false, reason: 'no-session' }
  if (s.focusedRuntime && rid === String(s.focusedRuntime)) return { show: false, reason: 'focused' }
  const m = s.mapping || {}, sid = Object.prototype.hasOwnProperty.call(m, rid) ? String(m[rid] || '') : ''
  if (!sid) return { show: false, reason: 'unmapped' }
  if (s.focusedStored && sid === String(s.focusedStored)) return { show: false, reason: 'focused' }
  return { show: true, reason: 'other-chat', storedId: sid }
}
// part 1: per-session selection. Durable stored ids only (runtime ids rotate on compression); a global pane gates its OWN content, never the host layout tree.
export function sessionDecision(scope, focusedStored, picked) {
  if (scope !== 'picked') return { show: true, reason: 'all' }
  const sid = focusedStored ? String(focusedStored) : ''
  if (!sid) return { show: true, reason: 'no-focused' }
  const list = Array.isArray(picked) ? picked : []
  return list.indexOf(sid) >= 0 ? { show: true, reason: 'picked' } : { show: false, reason: 'not-picked', storedId: sid }
}
const SIZE_LADDER = Object.freeze([[480, 460], [640, 520], [820, 620], [1024, 720]])
export function clampSize(w, h, vpW, vpH) {
  const maxW = Math.max(CARD_MIN.w, (Number(vpW) || 0) - 24)
  const maxH = Math.max(CARD_MIN.h, (Number(vpH) || 0) - 24)
  const a = Math.round(Number(w) || CARD_MIN.w)
  const b = Math.round(Number(h) || CARD_MIN.h)
  return { w: Math.min(maxW, Math.max(CARD_MIN.w, a)), h: Math.min(maxH, Math.max(CARD_MIN.h, b)) }
}
export function sizeAt(from, dx, dy, vpW, vpH, edges) {
  const E = edges || EDGES
  const c = clampSize(E.left ? from.w + dx : from.w - dx, E.top ? from.h + dy : from.h - dy, vpW, vpH)
  return { w: c.w, h: c.h, left: Math.max(8, E.left ? from.left : from.left + from.w - c.w), top: Math.max(8, E.top ? from.top : from.top + from.h - c.h) }
}
// Theater pins left+top, so its free corner is bottom-right, the opposite of the card's top-right.
const THEATER_EDGES = Object.freeze({ left: true, right: false, top: true, bottom: false })
export function nextLadder(w, h) {
  const i = SIZE_LADDER.findIndex((p) => p[0] === w && p[1] === h)
  if (i >= 0) return SIZE_LADDER[(i + 1) % SIZE_LADDER.length]
  // A drag or a clamp leaves a size that is not a step. Stepping back to the first preset forever is why a second click looked like it did nothing.
  const next = SIZE_LADDER.find((p) => p[0] > w || (p[0] === w && p[1] > h))
  return next || SIZE_LADDER[0]
}
export function paintSize(el, s, floating) {
  if (!el || !el.style) return false
  const st = el.style
  st.width = s.w + 'px'
  st.height = s.h + 'px'
  if (floating) { st.left = s.left + 'px'; st.top = s.top + 'px' }
  return true
}
export function unpaintSize(el) {
  if (!el || !el.style) return false
  const st = el.style
  st.width = ''; st.height = ''; st.left = ''; st.top = ''
  return true
}
/** Undo a pixel size painted onto a docked pane. Never blank the height the column needs. */
export function releaseDockPaint(el) {
  if (!el || !el.style) return false
  const st = el.style
  if (st.width && st.width !== '100%') st.width = ''
  if (typeof st.height === 'string' && st.height.endsWith('px')) st.height = '100%'
  st.left = ''
  st.top = ''
  return true
}
export function fullscreenRequest(el) {
  const f = el && (el.requestFullscreen || el.webkitRequestFullscreen)
  if (typeof f !== 'function') return false
  try { const p = f.call(el); if (p && typeof p.catch === 'function') p.catch(() => {}) } catch { return false }
  return true
}
export function fullscreenExit(doc) {
  const f = doc && (doc.exitFullscreen || doc.webkitExitFullscreen)
  if (typeof f !== 'function') return false
  try { const p = f.call(doc); if (p && typeof p.catch === 'function') p.catch(() => {}) } catch { return false }
  return true
}
// --------------------------------------------------------- density (pure, exported)
const RAIL_MIN = 190
const ROW_MIN = 560
const LAYOUT_TIERS = Object.freeze(['auto', 'compact', 'regular', 'wide', 'ultra'])
const ROOMY = Object.freeze(['regular', 'wide', 'ultra'])
export function layoutFor(paneW, override) {
  const w = Number(paneW) || 0
  const known = typeof override === 'string' && LAYOUT_TIERS.indexOf(override) >= 0 && override !== 'auto'
  const measured = w <= 0 ? 'regular' : w < RAIL_MIN ? 'rail' : w < 420 ? 'compact' : w >= 760 ? 'wide' : 'regular'
  const tier = known ? override : measured
  const rail = w > 0 && w < RAIL_MIN
  const wrap = !rail && w > 0 && w < ROW_MIN
  const roomy = ROOMY.indexOf(tier) >= 0
  return { tier, rail, wrap, roomy, captions: roomy, tags: roomy, detail: roomy }
}
/** Which chrome survives. Width buys DETAIL, never controls; immersive recedes it. */
export function chromeFor(immersive, layout, kind) {
  const L = layout || layoutFor(0, 'auto')
  const open = kind === 'page' || !immersive
  return {
    address: open, suggestions: open && !L.rail,
    // Focus recedes the address bar and footer, never the queue: it is the way back to it.
    queue: !L.rail, footer: open, nowPlaying: !immersive && !L.rail, transport: true,
    exit: !!immersive && kind !== 'page', grips: open && !L.rail, ladder: open && !L.rail, }
}
/** Page overlay. A working guest is the stage; the hint is a real load failure only. */
export function guestOverlay(failed) {
  return failed ? 'hint' : 'stage'
}
function clearGuestFault() { pageFault.set(false) }
// ------------------------------------------------------------ media + settings
const MEDIA_EXT = Object.freeze({
  mp4: 'video', m4v: 'video', webm: 'video', ogv: 'video', mov: 'video', mp3: 'audio', m4a: 'audio', aac: 'audio', flac: 'audio', wav: 'audio',
  ogg: 'audio', oga: 'audio', opus: 'audio', })
const MANIFEST_EXT = Object.freeze({ m3u8: 1, mpd: 1 })
const RATES = Object.freeze([0.5, 0.75, 1, 1.25, 1.5, 2])
const RESTORE_MODES = Object.freeze(['url', 'playing', 'blank'])
const THEATER_SCOPES = Object.freeze(['focused', 'any'])
const SESSION_SCOPES = Object.freeze(['all', 'picked'])
export const SETTINGS_DEFAULTS = Object.freeze({
  restoreMode: 'url', autoplay: false, immersiveOnPlay: true, autoAdvance: true, loop: false, volume: 80, dockMuted: false, rate: 1,
  showSuggestions: true, showQueue: true, layout: 'auto', autoTheater: false, theaterScope: 'focused', theaterPersist: THEATER_PERSIST.agent, completionToasts: false, sessionScope: 'all', })
const pins = atom([])
const shelf = atom([])
const listMode = atom('queue')
const visits = atom([])
const settings = atom(SETTINGS_DEFAULTS)
export const automation = atom({ supported: false, enabled: false, mode: 'off', busy: false, hasMedia: false, floating: false, viewport: null, scope: 'focused', own: false })
export const completion = atom({ enabled: false, mapped: 0, last: 'off', reason: 'off' })
const picked = atom([])
const focusedStored = atom(null)
const net = atom('online')
const diag = atom({ transport: null, lastError: null, source: null })
const immersive = atom(false)
// A navigation the page tried on its own. Blocked and offered, never adopted silently.
const navOffer = atom(null)
const pageFault = atom(false)
// ONE surface mounts a player (a re-registration can briefly mount a second root); stable ids keep it mounted.
const cardSize = atom({ w: 480, h: 460 })
const play = atom({
  raw: '', src: null, pageUrl: null, title: '', hostname: '', kind: null, media: null, error: null, floating: false, autoplayOnce: false,
})
let settingsStore = null
let osDoor = null
// Per-instance DOM handles: a root, width, or media element belongs to ONE mounted MediaDock. One surface renders at a time, so commands go to the FRONTED root.
const surfaces = new Map()
let frontRoot = null
// One pointer means one drag in flight: genuinely global, unlike a DOM handle.
let dragState = null
const surfaceHandle = () => surfaces.get(frontRoot) || surfaces.values().next().value || null
let theaterSettle = 0, theaterExit = 0, stageEl = null
const theaterHandle = () => stageEl || (surfaceHandle() ? surfaceHandle().root : null), stageRef = (n) => { stageEl = n || null }
// Theater pins the PLAYER surface in place; swapping placement would destroy the guest.
function toggleTheater() { theaterManual.set(automation.get().own ? false : true) }
function writeSettings() {
  try { if (settingsStore) settingsStore.set('settings', settings.get()) } catch { /* optional */ }
}
function patchSettings(patch) {
  settings.set(settingsWithDefaults({ ...settings.get(), ...patch }))
  writeSettings()
}
function readSize(store) {
  try {
    const v = store && store.get('size', null)
    if (v && isFinite(Number(v.w)) && isFinite(Number(v.h))) return clampSize(v.w, v.h, globalThis.innerWidth || 1920, globalThis.innerHeight || 1080)
  } catch { /* optional */ }
  return { w: 480, h: 460 }
}
function writeSize(storage, s) {
  try { storage.set('size', s) } catch { /* optional */ }
}
// The dragged size of the pinned player (not `size`, which is the card's ladder). Absent = fill.
export function readTheaterSize(store) {
  try { const v = store && store.get('theaterSize', null), w = Math.round(Number(v && v.w) || 0), h = Math.round(Number(v && v.h) || 0)
    if (w > 0 && h > 0) return { w, h } } catch { /* optional */ }
  return null
}
function writeTheaterSize(storage, r) { try { storage.set('theaterSize', r) } catch { /* optional */ } }
// Seconds each URL was left at, in the same local storage as the queue, this machine only. Bounded: the oldest keys fall off past PROGRESS_MAX.
const progress = atom({})
const PROGRESS_MAX = 60
function readProgress(store) {
  try { const v = store && store.get('progress', null); return v && typeof v === 'object' ? { ...v } : {} } catch { return {} }
}
export function remember(url, t, d) {
  if (!url || !(t > 3)) return
  const next = d > 0 && t > d - 5 ? 0 : Math.round(t)
  const cur = progress.get()
  // The guard runs BEFORE the copy: a paused page reports the same second four times a
  // second, and every one of those used to clone the whole resume map to throw it away.
  if (cur[url] === next || (!next && !(url in cur))) return
  const m = { ...cur }
  delete m[url]
  if (next) m[url] = next
  const keys = Object.keys(m)
  for (const k of keys.slice(0, Math.max(0, keys.length - PROGRESS_MAX))) delete m[k]
  progress.set(m)
  try { settingsStore && settingsStore.set('progress', m) } catch { /* optional */ }
}
export function resumeAt(n, url, d) {
  const at = Number(progress.get()[url]) || 0
  if (n && at > 3 && d > 5 && at < d - 5 && !(n.currentTime > 1)) { try { n.currentTime = at } catch { /* not seekable */ } }
}
// ------------------------------------------------------------------ url helpers
export function coerceUrl(raw) {
  const text = String(raw == null ? '' : raw).trim()
  if (!text) return ''
  if (/^\/\//.test(text)) return 'https:' + text
  const scheme = /^[a-z][a-z0-9+.-]*:/i.exec(text)
  // `localhost:3000` and `example.com:8080/a.mp4` parse as a SCHEME named after the host, so
  // they were refused as "only http(s) loads here". A scheme's payload is not a port: when
  // the colon is followed by digits, the text is a host and port.
  if (scheme && !/^\d+([/?#]|$)/.test(text.slice(scheme[0].length))) return text
  return 'https://' + text
}
export function classifyMedia(url) {
  let path = ''
  try { path = (url instanceof URL ? url : new URL(String(url))).pathname || '' } catch { return null }
  const dot = path.lastIndexOf('.'); if (dot < 0) return null
  const ext = path.slice(dot + 1).toLowerCase().replace(/[^a-z0-9]/g, '')
  if (MANIFEST_EXT[ext]) return { kind: 'manifest', ext, media: null }
  const media = MEDIA_EXT[ext]
  return media ? { kind: 'native', ext, media } : null
}
/** Generic validator. No provider, no id extraction, no host branches. */
export function parseMediaUrl(raw) {
  const text = coerceUrl(raw)
  if (!text) return { ok: false, error: 'empty' }
  let url
  try { url = new URL(text) } catch { return { ok: false, error: 'not-a-url' } }
  if (url.protocol !== 'http:' && url.protocol !== 'https:') return { ok: false, error: 'scheme' }
  const hostname = url.hostname
  if (!hostname || (!hostname.includes('.') && hostname !== 'localhost')) return { ok: false, error: 'not-a-url' }
  const cls = classifyMedia(url)
  const base = {
    ok: true, src: url.href, pageUrl: url.href, raw: text, title: hostname.replace(/^www\./, ''), hostname, error: null,
  }
  // HLS/DASH is a named refusal: the manifest is a real URL, the reason is the decoder.
  if (cls && cls.kind === 'manifest') return { ok: false, error: 'manifest', src: url.href, pageUrl: url.href, raw: text, title: base.title, hostname, kind: null, media: null }
  if (cls && cls.kind === 'native') return { ...base, kind: 'native', media: cls.media, ext: cls.ext }
  return { ...base, kind: 'page', media: null, ext: null }
}
export function errorCopy(code) {
  const m = { empty: 'Paste an http(s) URL to park it here.', 'not-a-url': 'That is not a URL. Enter a full http(s) address.',
    scheme: 'Only http(s) URLs load here. file:, javascript: and data: are refused.',
    manifest: 'This is an HLS/DASH stream manifest. Chromium has no decoder for it. Open it in your browser.',
    'frame-blocked': 'This page would not load here: sign-in or embedding restriction. Open it in your browser.',
    'media-error': 'The media file could not play.', offline: 'Network is offline. Playback may stall.', 'no-focused-session': 'No focused session to pick. Open a chat first.' }
  return m[code] || (code ? String(code) : '')
}
export function mediaErrorCopy(code) {
  const m = { 1: 'Playback was aborted.', 2: 'Network error: the host dropped the connection.', 3: 'Decode error: Chromium cannot play this codec or container.',
    4: 'Source not supported: the URL is not a playable media file, or the host refused the range request.' }
  return m[Number(code)] || 'The media file could not play (code ' + (code == null ? '?' : code) + ').'
}
export function formatTime(sec) {
  const s = Number(sec)
  if (!isFinite(s) || s < 0) return '0:00'
  const total = Math.floor(s), h = Math.floor(total / 3600), m = Math.floor((total % 3600) / 60), r = total % 60
  const pad = (v) => String(v).padStart(2, '0')
  return h > 0 ? h + ':' + pad(m) + ':' + pad(r) : m + ':' + pad(r)
}
/** 200% is +6 dB; past that a boost on a quiet master is a jump-scare, not a feature. */
export const VOL_MAX = 200
// A site can set a playbackRate that is not one of ours (1.1x). Stepping must move FORWARD
// from it; the old index+1 fell back to the first preset, so the click looked dead or went
// backwards. Same trap the size ladder had.
// A queue row must actually start: an unmuted play() can be refused, the muted retry can be refused
// too, and a cold element can miss readiness. Past a settle window a still-paused file at 0:00 becomes
// one labelled control instead of looking broken. Pure, so the table is testable without a browser.
export function autoplayNeedsGesture(s) {
  if (!s || s.failed) return false
  if (!s.waited) return false
  return !!s.paused && !(Number(s.t) > 0.25)
}
export function nextRate(current) {
  const r = Number(current) || 0
  return RATES.find((x) => x > r + 0.001) || RATES[0]
}
function cssName(k) { return String(k).replace(/[A-Z]/g, (c) => '-' + c.toLowerCase()) }
// A row's own Enter opens it. Its Remove and move controls are buttons inside that same row,
// and their keydown bubbles, so the row must ignore an Enter aimed at one of them.
export function rowEnterOpens(e) { return !!e && e.key === 'Enter' && (!e.target || !e.currentTarget || e.target === e.currentTarget) }
export function clampVolume(v) {
  const n = Number(v)
  if (!isFinite(n)) return SETTINGS_DEFAULTS.volume
  return Math.max(0, Math.min(VOL_MAX, Math.round(n)))
}
export function settingsWithDefaults(value) {
  const s = value && typeof value === 'object' ? value : {}
  const rate = Number(s.rate)
  return {
    restoreMode: RESTORE_MODES.indexOf(s.restoreMode) >= 0 ? s.restoreMode : SETTINGS_DEFAULTS.restoreMode, autoplay: typeof s.autoplay === 'boolean' ? s.autoplay : SETTINGS_DEFAULTS.autoplay,
    immersiveOnPlay: typeof s.immersiveOnPlay === 'boolean' ? s.immersiveOnPlay : SETTINGS_DEFAULTS.immersiveOnPlay, autoAdvance: typeof s.autoAdvance === 'boolean' ? s.autoAdvance : SETTINGS_DEFAULTS.autoAdvance,
    loop: typeof s.loop === 'boolean' ? s.loop : SETTINGS_DEFAULTS.loop, volume: clampVolume(s.volume == null ? SETTINGS_DEFAULTS.volume : s.volume),
    dockMuted: typeof s.dockMuted === 'boolean' ? s.dockMuted : SETTINGS_DEFAULTS.dockMuted, rate: RATES.indexOf(rate) >= 0 ? rate : SETTINGS_DEFAULTS.rate,
    showSuggestions: typeof s.showSuggestions === 'boolean' ? s.showSuggestions : SETTINGS_DEFAULTS.showSuggestions, showQueue: typeof s.showQueue === 'boolean' ? s.showQueue : SETTINGS_DEFAULTS.showQueue,
    layout: LAYOUT_TIERS.indexOf(s.layout) >= 0 ? s.layout : SETTINGS_DEFAULTS.layout, autoTheater: typeof s.autoTheater === 'boolean' ? s.autoTheater : SETTINGS_DEFAULTS.autoTheater,
    theaterScope: THEATER_SCOPES.indexOf(s.theaterScope) >= 0 ? s.theaterScope : SETTINGS_DEFAULTS.theaterScope, theaterPersist: THEATER_PERSISTS.indexOf(s.theaterPersist) >= 0 ? s.theaterPersist : SETTINGS_DEFAULTS.theaterPersist,
    completionToasts: typeof s.completionToasts === 'boolean' ? s.completionToasts : SETTINGS_DEFAULTS.completionToasts, sessionScope: SESSION_SCOPES.indexOf(s.sessionScope) >= 0 ? s.sessionScope : SETTINGS_DEFAULTS.sessionScope,
  }
}
export function nextInQueue(list, currentUrl, loop) {
  const rows = Array.isArray(list) ? list.filter((p) => p && p.url) : []
  if (!rows.length) return null
  const i = rows.findIndex((p) => p.url === currentUrl)
  const n = i < 0 ? 0 : i + 1
  if (n < rows.length) return rows[n]
  return loop && i >= 0 ? rows[0] : null
}
export function prevInQueue(list, currentUrl, loop) {
  const rows = Array.isArray(list) ? list.filter((p) => p && p.url) : []
  if (!rows.length) return null
  const i = rows.findIndex((p) => p.url === currentUrl)
  if (i < 0) return rows[rows.length - 1]
  if (i > 0) return rows[i - 1]
  return loop ? rows[rows.length - 1] : null
}
export function movePin(list, id, dir) {
  const rows = Array.isArray(list) ? list.filter((p) => p && p.id) : []
  const i = rows.findIndex((p) => p.id === id)
  const j = i + (dir < 0 ? -1 : 1)
  if (i < 0 || j < 0 || j >= rows.length) return rows
  const next = rows.slice()
  const [row] = next.splice(i, 1)
  next.splice(j, 0, row)
  return next
}
export function previewMarkdown(url) {
  if (typeof url !== 'string' || !/^https?:\/\//i.test(url)) {
    throw new Error('previewMarkdown requires an http(s) URL')
  }
  return '[Open in Hermes Browser](#preview/' + encodeURIComponent(url) + ')'
}
// -------------------------------------------------------------------- pins/visits
function pinLabel(parsed) {
  const page = parsed && parsed.pageUrl
  if (!page) return 'Saved link'
  try {
    const u = new URL(page)
    const seg = u.pathname.split('/').filter(Boolean).pop()
    if (seg) return decodeURIComponent(seg).slice(0, 80)
    return u.hostname.replace(/^www\./, '')
  } catch { return 'Saved link' }
}
export function makePin(raw) {
  const parsed = parseMediaUrl(raw)
  if (!parsed || !parsed.ok) return null
  const url = parsed.pageUrl
  return {
    id: (parsed.hostname + '|' + url).slice(0, 160), url, title: pinLabel(parsed), kind: parsed.kind,
    host: parsed.hostname, addedAt: 0, }
}
export function upsertPin(list, pin, max) {
  if (!pin || typeof pin.url !== 'string') return Array.isArray(list) ? list : []
  const rows = (Array.isArray(list) ? list : []).filter((p) => p && p.url !== pin.url)
  return [pin, ...rows].slice(0, Number(max) > 0 ? Number(max) : 12)
}
export function removePin(list, id) {
  if (!Array.isArray(list)) return []
  return list.filter((p) => p && p.id !== id)
}
export function bumpVisit(list, raw, max, pre) {
  const parsed = pre || parseMediaUrl(raw)
  if (!parsed || !parsed.ok) return Array.isArray(list) ? list : []
  const rows = Array.isArray(list) ? list.slice() : []
  const host = String(parsed.hostname).replace(/^www\./, '').toLowerCase()
  const i = rows.findIndex((r) => r && r.host === host)
  const row = {
    host, url: parsed.pageUrl, title: parsed.title || host, count: i >= 0 ? (Number(rows[i].count) || 0) + 1 : 1, lastAt: 0,
  }
  // Common case: the host being bumped is already the top row and the queue is full.
  // Its count only grew, so no other row can pass it: the order cannot change and one
  // sort (plus one unshift) per paste is pure waste.
  if (i === 0) {
    rows[0] = row
  } else {
    if (i > 0) rows.splice(i, 1)
    // The stored rows are already ordered (count desc, then lastAt desc), so the new row's
    // slot is ONE linear scan. Sorting 24 rows to insert one is the same result for more work;
    // a list that arrives unordered still takes the sort fallback.
    const cmp = (a, b) => (b.count - a.count) || (b.lastAt - a.lastAt)
    let j = -1, ordered = true
    for (let k = 0; k < rows.length; k++) {
      if (k && cmp(rows[k - 1], rows[k]) > 0) { ordered = false; break }
      // Strictly-better rows stay ahead; the first row that only ties stops the scan, so the
      // newcomer lands BEFORE its equals, the same slot a stable sort gives the front row.
      if (j < 0 && cmp(rows[k], row) >= 0) j = k
    }
    if (ordered) rows.splice(j < 0 ? rows.length : j, 0, row)
    else { rows.unshift(row); rows.sort(cmp) }
  }
  const cap = Number(max) > 0 ? Number(max) : 24
  return rows.length > cap ? rows.slice(0, cap) : rows
}
export function suggestVisits(list, query, limit) {
  if (!Array.isArray(list)) return []
  const q = String(query || '').trim().toLowerCase()
  const rows = list.filter((r) => r && typeof r.host === 'string' && typeof r.url === 'string'
    && /^https?:\/\//i.test(r.url) && (!q || r.host.toLowerCase().includes(q) || String(r.title || '').toLowerCase().includes(q)))
  return rows.slice(0, Number(limit) > 0 ? Number(limit) : 6)
}
// ---------------------------------------------------------------------- storage
function readSession(ctx) {
  try { const v = ctx.storage.get('session', null); return v && typeof v === 'object' && typeof v.then !== 'function' ? v : null } catch { return null }
}
function writeSession(ctx, snapshot) { try { ctx.storage.set('session', snapshot) } catch { /* optional */ } }
function readPins(ctx, key = 'pins', max = PIN_MAX) {
  try {
    const v = ctx.storage.get(key, [])
    if (!Array.isArray(v)) return []
    const out = []
    for (const row of v) {
      const pin = row && typeof row.url === 'string' ? makePin(row.url) : null
      if (pin) out.push({ ...pin, title: typeof row.title === 'string' && row.title ? row.title : pin.title })
    }
    return out.slice(0, max)
  } catch { return [] }
}
function writeList(ctx, key, list, max) {
  try { ctx.storage.set(key, (Array.isArray(list) ? list : []).slice(0, max)) } catch { /* optional */ }
}
function readVisits(ctx) {
  try {
    const v = ctx.storage.get('visits', [])
    if (!Array.isArray(v)) return []
    const out = []
    for (const row of v) {
      const ok = row && typeof row.host === 'string' && typeof row.url === 'string' && /^https?:\/\//i.test(row.url) && Number(row.count) > 0
      if (ok) out.push({ host: row.host, url: row.url, title: typeof row.title === 'string' && row.title ? row.title : row.host, count: Number(row.count), lastAt: Number(row.lastAt) || 0 })
    }
    return out.slice(0, VISIT_MAX)
  } catch { return [] }
}
function readPicked(ctx) {
  try { const v = ctx.storage.get('pickedSessions', []); return Array.isArray(v) ? v.filter((x) => typeof x === 'string' && x).slice(0, PICK_MAX) : [] } catch { return [] }
}
function pickSession(sid) {
  const id = sid ? String(sid) : ''
  if (!id) { diag.set({ transport: 'refuse', lastError: 'no-focused-session', source: '' }); return }
  const cur = picked.get()
  picked.set(cur.indexOf(id) >= 0 ? cur.filter((x) => x !== id) : [id, ...cur].slice(0, PICK_MAX))
}
function readSettings(ctx) { try { return settingsWithDefaults(ctx.storage.get('settings', null)) } catch { return settingsWithDefaults(null) } }
// ------------------------------------------------------------------ play core
function applyParsed(parsed, raw, record, autoplayOnce) {
  clearGuestFault()
  const cur = play.get()
  if (!parsed || parsed.ok === false) {
    play.set({
      ...cur, raw: raw || '', src: parsed && parsed.src ? parsed.src : null, pageUrl: parsed && parsed.pageUrl ? parsed.pageUrl : null,
      title: '', hostname: '', kind: null, media: null, error: (parsed && parsed.error) || 'not-a-url', autoplayOnce: false,
    })
    diag.set({ transport: 'refuse', lastError: (parsed && parsed.error) || 'not-a-url', source: raw || '' })
    return
  }
  play.set({
    ...cur, raw: raw || parsed.pageUrl || '', src: parsed.src || null, pageUrl: parsed.pageUrl || null, title: pinLabel(parsed) || parsed.title || '', hostname: parsed.hostname || '',
    kind: parsed.kind || null, media: parsed.media || null, error: null, autoplayOnce: !!autoplayOnce,
  })
  diag.set({ transport: parsed.kind, lastError: null, source: parsed.pageUrl || '' })
  // Leaving a page for a file we own must forget the page's player. The agent only reports while a guest is mounted, so a stale {has:true} otherwise keeps a second, dead transport rail (and its diagnostics line) alive under the file's own rail.
  if (parsed.kind !== 'page') pageMedia.set({ has: false })
  if (parsed.kind === 'page') { immersive.set(false); navIntent = parsed.src || null }
  if (record !== false) visits.set(bumpVisit(visits.get(), parsed.pageUrl || raw, VISIT_MAX, parsed))
}
/** Every entry point (paste, drop, Go, queue row, keybind, restore) lands here. */
function loadUrl(raw, autoplayOnce) {
  applyParsed(parseMediaUrl(raw), raw, true, autoplayOnce)
}
function playItem(item, label) {
  if (!item) return null
  loadUrl(item.url, true)
  if (host && typeof host.notify === 'function') {
    try { host.notify({ kind: 'info', message: label + item.title }) } catch { /* older desktop */ }
  }
  return item
}
function playNext() {
  return playItem(nextInQueue(pins.get(), play.get().pageUrl, settings.get().loop), 'Up next: ')
}
function playPrev() {
  return playItem(prevInQueue(pins.get(), play.get().pageUrl, settings.get().loop), 'Previous: ')
}
function advance() {
  if (!settings.get().autoAdvance) return null
  const cur = play.get().pageUrl
  const rows = pins.get()
  if (!Array.isArray(rows) || !rows.some((p) => p && p.url === cur)) return null
  return playNext()
}
function toggleMediaNode(n) {
  if (!n) return
  try {
    if (n.paused) {
      const p = n.play && n.play()
      if (p && typeof p.catch === 'function') p.catch(() => {})
    } else if (n.pause) n.pause()
  } catch { /* detached node */ }
}
function togglePlayback() {
  const s = surfaceHandle()
  toggleMediaNode(s && s.root.querySelector ? s.root.querySelector('video, audio') : null)
}
function droppedUrl(ev) {
  const dt = ev && ev.dataTransfer
  if (!dt) return ''
  const blob = dt.getData('text/uri-list') || dt.getData('text/plain') || ''
  return blob.split(/\r?\n/).map((s) => s.trim()).find((s) => s && s[0] !== '#') || ''
}
// ------------------------------------------------------------------ resize drag. Paints the element that can actually move. NEVER calls registerPane: a remount drops pointer capture and restarts the media element. The size persists and is fed back into the registration data on the next mount.
export function startResize(axis, ev, root, theater) {
  if (!root || typeof root.getBoundingClientRect !== 'function') return false
  // Theater pins the dock's own root, so the card wrapper is not what moves: resizing it did nothing.
  const card = theater ? root : (root.closest ? root.closest('[data-floating-pane]') : null)
  if (!card || typeof card.getBoundingClientRect !== 'function') return false
  const box = card.getBoundingClientRect()
  const from = { x: Number(ev.clientX) || 0, y: Number(ev.clientY) || 0, w: box.width, h: box.height, left: box.left, top: box.top, right: box.right, bottom: box.bottom }
  dragState = { axis, el: card, card: !theater, theater: !!theater, edges: theater ? THEATER_EDGES : EDGES, transition: card.style ? card.style.transition : '', preview: null, from, vpW: globalThis.innerWidth || 1920, vpH: globalThis.innerHeight || 1080 }
  if (theater && card.style) card.style.transition = 'none'   // a 0.2 s ease per frame is a rubber band
  try { if (ev && ev.pointerId != null && ev.target && ev.target.setPointerCapture) ev.target.setPointerCapture(ev.pointerId) } catch { /* older DOM */ }
  // The guest is its own process: a pointer that leaves our 8px strip for the page is delivered
  // there, so the drag stopped moving. A shield over the card keeps every move in this document.
  const doc = card.ownerDocument
  if (theater && !dragState.shield && doc && typeof doc.createElement === 'function' && card.appendChild) {
    const sh = doc.createElement('div')
    sh.setAttribute('data-md-drag-shield', '1')
    sh.style.cssText = 'position:absolute;inset:0;z-index:60;cursor:' + (axis === 'y' ? 'ns-resize' : 'ew-resize')
    card.appendChild(sh)
    dragState.shield = sh
  }
  if (ev && ev.preventDefault) ev.preventDefault()
  if (ev && ev.stopPropagation) ev.stopPropagation()
  return true
}
function onPointerMove(ev) {
  const d = dragState
  if (!d) return
  const dx = (Number(ev.clientX) || 0) - d.from.x
  const dy = (Number(ev.clientY) || 0) - d.from.y
  const s = sizeAt(d.from, d.axis === 'y' ? 0 : dx, d.axis === 'x' ? 0 : dy, d.vpW, d.vpH, d.edges)
  d.preview = s
  if (d.theater && d.el.style) { d.el.style.width = s.w + 'px'; d.el.style.height = s.h + 'px' }
  else paintSize(d.el, s, d.card)
}
function onPointerUp(ev) {
  const d = dragState
  if (!d) return
  const s = d.preview || sizeAt(d.from, 0, 0, d.vpW, d.vpH, d.edges)
  if (d.shield && d.shield.parentNode) { try { d.shield.parentNode.removeChild(d.shield) } catch { /* gone */ } }
  if (d.theater) {
    const c = clampSize(s.w, s.h, d.vpW, d.vpH); theaterRect = { w: c.w, h: c.h }; writeTheaterSize(settingsStore, theaterRect)
    if (d.el.style) { d.el.style.transition = d.transition || ''; d.el.style.width = c.w + 'px'; d.el.style.height = c.h + 'px' }
  } else { if (d.card) paintSize(d.el, s, true); else unpaintSize(d.el); commitSize(s) }
  dragState = null
}
function onPointerCancel(ev) { onPointerUp(ev) }
function commitSize(s) {
  const c = clampSize(s.w, s.h, globalThis.innerWidth || 1920, globalThis.innerHeight || 1080)
  cardSize.set(c)
  writeSize(settingsStore, c)
  return c
}
export function paintCard(root) {
  if (!root) return false
  const card = root.closest ? root.closest('[data-floating-pane]') : null
  if (!card) { releaseDockPaint(root); return false }
  const s = cardSize.get()
  return paintSize(card, { w: s.w, h: s.h }, false)
}
function cycleSize(root) {
  const cur = cardSize.get()
  const s = nextLadder(cur.w, cur.h)
  commitSize({ w: s[0], h: s[1] })
  const front = surfaceHandle()
  const node = root || (front && front.root)
  // Docked: the label is the only effect; painting here was a one-shot repair that made the first click move the pane and the later ones look dead.
  if (node && node.closest && node.closest('[data-floating-pane]')) paintCard(node)
}
// Press while full exits; press while empty enters. Request-only stranded the window.
function fullscreenToggle(el) { const d = globalThis.document; return d && (d.fullscreenElement || d.webkitFullscreenElement) ? fullscreenExit(d) : (el ? fullscreenRequest(el) : false) }
function dockFullscreen() { const s = surfaceHandle(); return fullscreenToggle(s && s.root) }
function exitFocus() {
  immersive.set(false)
  fullscreenExit(globalThis.document)
}
function toggleFocus() { immersive.set(!immersive.get()) }
const COMMANDS = Object.freeze([ { id: 'playpause', label: 'Play/Pause', description: 'Play or pause the file.', keys: ['mod+alt+p'], run: togglePlayback },
  { id: 'prev', label: 'Previous', description: 'Play the previous queued item.', keys: ['mod+alt+shift+n'], run: playPrev }, { id: 'next', label: 'Next', description: 'Play the next queued item.', keys: ['mod+alt+n'], run: playNext },
  { id: 'focus', label: 'Focus mode', description: 'Hide the bars around the video.', keys: ['mod+alt+f'], run: toggleFocus },
  { id: 'fullscreen', label: 'Fullscreen', description: 'Fill the screen (Esc to exit).', keys: ['mod+alt+Enter'], run: dockFullscreen }, ])
// ---------------------------------------------------------------------- chrome
const V = {
  text: 'var(--ui-text-primary, var(--foreground))', sub: 'var(--ui-text-secondary, var(--muted-foreground))', dim: 'var(--ui-text-tertiary, var(--muted-foreground))', stroke: 'var(--ui-stroke-primary, var(--border))',
  accent: 'var(--ui-accent, var(--accent))', editor: 'var(--ui-bg-editor, var(--card))', chrome: 'var(--ui-bg-chrome, var(--ui-bg-editor, var(--card)))',
}
const ICON_STYLE = { border: 0, background: 'transparent', color: V.sub, width: 28, height: 28, padding: 0, borderRadius: 6, fontSize: 14, lineHeight: 1, cursor: 'pointer', flex: '0 0 auto' }
function iconBtn(mark, onClick, label) { return jsx('button', { type: 'button', title: label, 'aria-label': label, onClick, style: ICON_STYLE, children: mark }) }
function chromeBtn(label, onClick, opts) {
  const title = (opts && opts.title) || label
  // The spoken name is the text on screen, not the tooltip: name-from-title announced a sentence
  // where the button shows one word, so neither a reader nor the live driver could find it.
  if (Button) return jsx(Button, { type: 'button', variant: 'ghost', size: 'sm', onClick, title, 'aria-label': label, children: label })
  return jsx('button', { type: 'button', title, 'aria-label': label, onClick,
    style: { border: '1px solid ' + V.stroke, background: 'transparent', color: V.sub, borderRadius: 'var(--radius-md, 6px)', padding: '3px 9px', fontSize: 11, cursor: 'pointer' }, children: label })
}
function glyph(name) {
  if (Codicon) return jsx(Codicon, { name, size: '0.8rem' })
  return null
}
function BrowserCta({ url, label }) {
  if (!url || !/^https?:\/\//i.test(url)) return null
  const link = MessageTextContent ? jsx(MessageTextContent, { media: false, text: previewMarkdown(url) }) : null
  const ext = chromeBtn(label || 'Open in browser', () => { if (osDoor && typeof osDoor.openExternal === 'function') { try { osDoor.openExternal(url) } catch { /* unavailable */ } } })
  return jsxs('div', { style: { display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', justifyContent: 'center' }, children: [link, ext] })
}
function Well({ title, body, cta, tone }) {
  const color = tone === 'error' ? V.text : V.sub
  return jsxs('div', { className: 'media-dock-stage',
    style: { flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 10, padding: 24, background: V.editor, color, fontSize: 13, lineHeight: 1.5, textAlign: 'center' },
    children: [title ? jsx('div', { style: { fontSize: 14, fontWeight: 600, color: V.text }, children: title }) : null, body ? jsx('div', { style: { maxWidth: 380 }, children: body }) : null, cta || null] })
}
function EmptyWell() { return jsx(Well, { title: 'Nothing playing', body: 'Paste a video, an audio file or any site into the bar above, or drop a link on this pane.' }) }
function RefusalWell({ now }) {
  const ctaUrl = /^https?:\/\//i.test(now.src || '') ? now.src : null
  return jsx(Well, { title: 'Cannot play here', body: errorCopy(now.error), cta: jsx(BrowserCta, { url: ctaUrl }), tone: 'error' })
}
function PickedWell({ id }) {
  return jsx(Well, { title: 'Not shown in this chat', body: 'Show in is set to Picked chats, and this chat is not one of them. Playback continues underneath.',
    cta: jsxs('div', { style: { display: 'flex', gap: 6 }, children: [chromeBtn('Show here', () => pickSession(id)), chromeBtn('Show everywhere', () => patchSettings({ sessionScope: 'all' }))] }) })
}
/** Shown only after the guest actually fails to load. A working page has no overlay. */
const frameHint = (now) => jsxs('div', {
  style: { position: 'absolute', left: 8, right: 8, bottom: 8, display: 'flex', alignItems: 'center', gap: 8, justifyContent: 'space-between', padding: '5px 9px', borderRadius: 8, fontSize: 10, background: V.chrome, border: '1px solid ' + V.stroke, color: V.dim },
  children: [jsx('span', { children: errorCopy('frame-blocked') }), jsx(BrowserCta, { url: now.pageUrl, label: 'Open in browser' })],
})
// The page moved on its own. Say which host it wanted, and offer the two real answers.
function NavOffer({ now }) {
  const offer = useValue(navOffer)
  if (!offer) return null
  return jsxs('div', {
    style: { position: 'absolute', left: 8, right: 8, top: 8, zIndex: 30, display: 'flex', alignItems: 'center', gap: 8, justifyContent: 'space-between', padding: '5px 9px', borderRadius: 8, fontSize: 11, background: V.chrome, border: '1px solid ' + V.stroke, color: V.text },
    children: [jsx('span', { children: 'This page tried to open ' + (pageHost(offer.url) || offer.url) }), jsxs('div', { style: { display: 'flex', gap: 6, flexShrink: 0 }, children: [
        chromeBtn('Open anyway', () => { const u = offer.url; navOffer.set(null); loadUrl(u, false) }), chromeBtn('Stay', () => navOffer.set(null))] })] })
}
function PageFrame({ now }) {
  const failed = useValue(pageFault)
  // ONE guest element for the life of the pane: a remount erased the guest's history (Back could
  // never work) and raced the listeners attached at commit. Navigation is the src attribute.
  const guestStyle = { flex: '1 1 auto', width: '100%', height: '100%', minHeight: 0, border: 0, background: V.editor }
  return jsxs('div', { ref: stageRef, className: 'media-dock-stage', style: { flex: '1 1 auto', minHeight: 0, position: 'relative', display: 'flex', overflow: 'hidden', background: V.editor },
    children: [jsx('webview', { ref: guestRefCallback, src: now.src, partition: GUEST_PARTITION, useragent: GUEST_UA, style: guestStyle }), jsx(NavOffer, { now }),
      jsx(CueLine, { owner: 'page' }), guestOverlay(failed) === 'hint' ? frameHint(now) : null] })
}
// The guest's only writer. Every handler reads the atoms at call time, so the wiring survives renders and never closes over a stale `now`.
let guestCleanup = null
let hostFocus = null  // where focus returns when the guest tab-exits
// The URL OUR load asked for. A renderer navigation while this is set is part of that load
// (a short-link domain redirecting to its canonical one); with it null, a navigation is
// the page acting on its own.
let navIntent = null
function sameSite(a, b) {
  try { const x = new URL(a).hostname.replace(/^www\./, ''), y = new URL(b || '').hostname.replace(/^www\./, '')
    return !!x && !!y && (x === y || x.endsWith('.' + y) || y.endsWith('.' + x)) } catch { return false }
}
function detachGuest() {
  if (guestCleanup) { guestCleanup(); guestCleanup = null }
}
function attachGuest(el) {
  detachGuest()
  guestEl = el
  if (!el || typeof el.addEventListener !== 'function') return
  // `src` is the URL our last explicit load used. In-page navigation only updates play.pageUrl,
  // so a guest the host re-creates (theater flips the pane to a floating card) came back at the
  // site's root and dropped the playing video. Restore the live URL once React has set src.
  const liveNav = play.get().pageUrl
  if (liveNav && /^https?:\/\//i.test(liveNav) && liveNav !== play.get().src) {
    globalThis.setTimeout(() => { try { if (guestEl === el) el.src = liveNav } catch { /* gone */ } }, 0)
  }
  // A failed navigation still fires did-finish-load (Chromium's error document), so the fault belongs to the failure.
  let guestLoadFailed = false
  const onFail = (ev) => {
    if (ev && ev.errorCode === -3) return
    // Clear the intent here, not only on did-finish-load: after a failed paste the intent
    // stayed set, so every later self-navigation was treated as part of our own load and
    // adopted without the "this page tried to open …" offer.
    navIntent = null
    guestLoadFailed = true
    pageFault.set(true)
    syncNav(el, false)
  }
  const onOk = () => { navIntent = null; pageFault.set(guestLoadFailed); syncNav(el, false) }
  const onStart = () => { guestLoadFailed = false; pageMedia.set({ has: false }); guestVolInit = false; guestResumed = false; syncNav(el, true) }
  const onStop = () => syncNav(el, false)
  // The address field follows the PAGE, not the paste: SPA route changes arrive as did-navigate-in-page, a new document as did-navigate.
  const onNav = (ev) => {
    const url = ev && ev.url
    if (!url || !/^https?:\/\//i.test(url)) return
    navOffer.set(null)
    const cur = play.get()
    // `raw` is what the field shows. After a typed load applyParsed already set
    // pageUrl to the parsed URL, so comparing pageUrl alone skipped the write and
    // the field kept the typed text ("example.org") instead of the page's URL.
    if (cur.pageUrl !== url || cur.raw !== url) play.set({ ...cur, pageUrl: url, raw: url, hostname: pageHost(url) })
    pageMedia.set({ has: false }); guestVolInit = false; guestResumed = false
    syncNav(el, false)
  }
  const onTitle = (ev) => {
    const t = ev && ev.title
    if (!t) return
    const cur = play.get()
    if (cur.title !== t) play.set({ ...cur, title: t })
  }
  const onReady = () => {
    applyGuestMute(el)
    // Inject the page agent into the new document; the next poll reads it.
    try { const p = el.executeJavaScript(AGENT_SRC); if (p && p.catch) p.catch(() => {}) } catch { /* not ready */ }
    // The guest may already be past its first navigation when we attach.
    try {
      const url = el.getURL ? el.getURL() : ''
      if (url && /^https?:\/\//i.test(url) && play.get().pageUrl !== url) onNav({ url })
    } catch { /* not ready */ }
    syncNav(el, false)
    stopPoll(); guestPoll = setInterval(readGuest, 500); readGuest()
  }
  // A webview keeps Tab and Escape in its own process; the agent reports the boundary keys on console.
  // Escape is the way OUT: Tab only reaches the dock on a page whose focus ring ends (a feed never does).
  const unstick = () => { try { el.blur() } catch { /* gone */ } if (hostFocus) { try { hostFocus() } catch { /* unmounted */ } } }
  const onConsole = (ev) => {
    const msg = String((ev && ev.message) || '')
    if (msg === '__md:escape') { exitFocus(); unstick() }
    else if (msg === '__md:tab-out' || msg === '__md:tab-back') unstick()
  }
  // A page that navigates ITSELF is an ad, a redirect, or a link. Only a same-site move is
  // adopted silently; anything else is stopped before it replaces your source and offered.
  const onWillNav = (ev) => {
    const url = ev && ev.url
    if (!url || !/^https?:\/\//i.test(url) || navIntent || sameSite(url, play.get().pageUrl)) return
    if (ev.preventDefault) ev.preventDefault()
    navOffer.set({ url, from: play.get().pageUrl })
  }
  const pairs = [['did-fail-load', onFail], ['did-finish-load', onOk], ['did-start-loading', onStart], ['did-stop-loading', onStop], ['did-navigate', onNav], ['did-navigate-in-page', onNav],
    ['page-title-updated', onTitle], ['dom-ready', onReady], ['console-message', onConsole], ['will-navigate', onWillNav], ['will-redirect', onWillNav]]
  for (const [name, fn] of pairs) el.addEventListener(name, fn)
  guestCleanup = () => {
    for (const [name, fn] of pairs) el.removeEventListener(name, fn)
    stopPoll()
    if (guestEl === el) { guestEl = null; navState.set({ back: false, fwd: false, loading: false }) }
  }
  syncNav(el, false)
}
// The dock's own mute, applied to the guest's WebContents: page audio and our element are
// the same "dock sound"; the app's notification track is not ours to touch.
function applyGuestMute(el) {
  const e = el || guestEl
  if (!e || typeof e.setAudioMuted !== 'function') return
  try { e.setAudioMuted(!!settings.get().dockMuted) } catch { /* not ready */ }
}
function guestRefCallback(n) { if (n) attachGuest(n); else detachGuest() }
// Our transport over the PAGE's own player: it renders only while the guest agent reports a
// media element, and every control is one named command: no guessed element, no per-site
// script. One popover for both transports: ≤100% is the element's volume, >100% a gain stage.
const CAP_LANGS = Object.freeze([['', 'Original track'], ['en', 'English'], ['es', 'Spanish'], ['fr', 'French'], ['de', 'German'], ['pt', 'Portuguese'], ['hi', 'Hindi'], ['ja', 'Japanese'], ['ko', 'Korean'], ['zh', 'Chinese'], ['ar', 'Arabic'], ['ru', 'Russian']])
function popStyle() { return { position: 'absolute', bottom: 30, right: 0, zIndex: 40, width: 244, padding: '9px 11px', background: V.chrome, border: '1px solid ' + V.stroke, borderRadius: 8, fontSize: 11, color: V.text } }
function chipBtn(label, onClick, title, on) {
  return jsx('button', { type: 'button', title, onClick, 'aria-pressed': !!on,
    style: { border: '1px solid ' + (on ? V.accent : V.stroke), background: 'transparent', color: on ? V.accent : V.sub, borderRadius: 5, padding: '2px 7px', fontSize: 10, cursor: 'pointer' }, children: label })
}
function VolumeControl({ level, muted, boost, canBoost, why, onLevel }) {
  const [open, setOpen] = useState(false)
  const lv = clampVolume(level)
  const note = canBoost
    ? (boost ? 'Boosted, ' + lv + '% of the file\'s own level.' : 'Above 100% adds a gain stage, up to 200% (+6 dB).')
    : (why || 'Boost would silence this source, so it stops at 100%.')
  return jsxs('div', { style: { position: 'relative', flex: '0 0 auto' }, children: [ jsx('button', { type: 'button', title: 'Volume ' + lv + '% (0-200). Click to adjust', 'aria-label': 'Volume ' + lv + ' percent',
      onClick: () => setOpen(!open),
      style: { border: 0, background: 'transparent', color: muted ? V.dim : (boost ? V.accent : V.text), font: 'inherit', fontSize: 11, padding: '2px 5px', cursor: 'pointer', minWidth: 46, fontVariantNumeric: 'tabular-nums' },
      children: (muted ? '×' : boost ? '▲' : '♫') + ' ' + (muted ? '0' : String(lv)) + '%' }), open ? jsxs('div', { style: popStyle(), children: [
      jsxs('div', { style: { display: 'flex', alignItems: 'center', gap: 6 }, children: [ jsx('input', { type: 'range', min: 0, max: VOL_MAX, step: 5, value: lv, 'aria-label': 'Volume level, 0 to 200 percent',
          onChange: (e) => onLevel(Number(e && e.target ? e.target.value : 0)), style: { flex: 1, accentColor: V.accent } }),
        jsx('span', { style: { width: 38, textAlign: 'right', fontVariantNumeric: 'tabular-nums' }, children: String(lv) + '%' }) ] }), jsxs('div', { style: { display: 'flex', gap: 4, marginTop: 7 }, children: [
        chipBtn('100%', () => onLevel(100), 'The file at its own level'), chipBtn('150%', () => onLevel(150), 'Boost about 3.5 dB over the file level'),
        chipBtn('200%', () => onLevel(200), 'Boost 6 dB over the file level (the ceiling)'), chipBtn('Mute', () => onLevel(0), 'Level to 0%'),
        chipBtn('Reset', () => onLevel(80), 'Default level, 80%') ] }), jsx('div', { style: { marginTop: 7, color: V.dim, lineHeight: 1.45 }, children: note }),
    ] }) : null ] })
}
// Site tracks are the real subtitle source: a site that offers translated captions lists
// them here. Translation of the cues we already have is a second path, and it is offered
// only when this build ships Chromium's on-device Translator.
function CaptionControl({ owner }) {
  const c = useValue(captions)
  const [open, setOpen] = useState(false)
  const mine = c.owner === owner
  const list = mine ? c.tracks : []
  const sel = mine ? c.sel : -1
  // No tracks means no captions. A CC button whose only answer is "this player exposes no caption track" is a dead control in a 380px card; it appears when a source has one.
  if (!list.length && sel < 0) return null
  const set = (i) => { setOpen(false); setCaps({ owner, sel: i, cue: '' }); if (owner === 'page') sendGuest('track', i); else if (typeof nativeTrackHook === 'function') nativeTrackHook(i) }
  const label = sel >= 0 ? 'CC ' + ((mine && c.lang) || 'on') : 'CC'
  return jsxs('div', { style: { position: 'relative', flex: '0 0 auto' }, children: [ jsx('button', { type: 'button', title: sel >= 0 ? 'Captions on. Click to change' : 'Captions', 'aria-label': 'Captions',
      onClick: () => {
        // A site can add or swap tracks after load (ads, auto-translated captions), so the list is refreshed when the user asks for it, not only when the count changes.
        if (owner === 'page') { guestTrackAt = 0; loadGuestTracks() }
        setOpen(!open)
      }, style: { border: 0, background: 'transparent', color: sel >= 0 ? V.accent : V.sub, font: 'inherit', fontSize: 11, padding: '2px 5px', cursor: 'pointer' }, children: label }),
    open ? jsxs('div', { style: popStyle(), children: [ jsx('div', { style: { color: V.dim, marginBottom: 4 }, children: 'Track' }),
      list.length <= 6
        ? jsxs('div', { style: { display: 'flex', flexWrap: 'wrap', gap: 4, marginBottom: 6 }, children: [ chipBtn('Off', () => set(-1), 'Show no captions', sel < 0),
            ...list.map((k) => chipBtn(k.label, () => set(k.i), 'Show ' + k.label + ' captions', sel === k.i)) ] })
        : jsx('select', { value: String(sel), 'aria-label': 'Caption track', onChange: (e) => set(Number(e && e.target ? e.target.value : -1)),
            style: { width: '100%', marginBottom: 6, background: V.editor, color: V.text, border: '1px solid ' + V.stroke, borderRadius: 5, fontSize: 11, padding: '2px 4px' },
            children: [jsx('option', { value: '-1', children: 'Off' }), ...list.map((k) => jsx('option', { value: String(k.i), children: k.label + (k.kind === 'subtitles' ? '' : ' (' + k.kind + ')') }))] }),
      jsxs('div', { style: { display: 'flex', alignItems: 'center', gap: 6 }, children: [ jsx('span', { style: { color: V.dim }, children: 'Language' }),
        jsx('select', { value: c.target, 'aria-label': 'Translate captions to', onChange: (e) => { trWhy = ''; setCaps({ target: String(e && e.target ? e.target.value : '') }) },
          style: { flex: 1, background: V.editor, color: V.text, border: '1px solid ' + V.stroke, borderRadius: 5, fontSize: 11, padding: '2px 4px' }, children: CAP_LANGS.map(([v, n]) => jsx('option', { value: v, children: n })) }) ] }),
      jsx('div', { style: { marginTop: 7, color: V.dim, lineHeight: 1.45 }, children: !list.length ? 'This player exposes no caption track.'
          : c.target ? (trWhy || 'Each cue is sent to a public translation service as it appears; nothing is kept here.')
            : 'Pick a language to translate the cues already loaded. Cue text leaves this machine.' }), ] }) : null ] })
}
let nativeTrackHook = null
// The native element's keys, published for the pane's own handler: a <video> with no controls is only keyboard-playable if the pane owns the keys.
let nativeCtl = null
function CueLine({ owner }) {
  const c = useValue(captions)
  if (c.owner !== owner || c.sel < 0 || !c.cue) return null
  const tr = translationOf(c.cue)
  return jsx('div', { 'aria-live': 'polite', style: { position: 'absolute', left: 0, right: 0, bottom: 10, margin: '0 auto', width: 'fit-content', maxWidth: '92%', padding: '3px 10px', borderRadius: 6,
      background: V.chrome, color: V.text, border: '1px solid ' + V.stroke, fontSize: 12, lineHeight: 1.4, textAlign: 'center', pointerEvents: 'none', zIndex: 5 }, children: tr || c.cue })
}
// The page's player and a file player are the same controls in the same order. Two rails with
// different spacing read as two apps glued together. A live stream has no authored timeline
// (duration is Infinity), so it shows LIVE where a VOD shows the scrubber; nothing else differs.
function NowPlaying({ title }) {
  if (!title) return null
  return jsx('div', { className: 'media-dock-now-playing', style: { display: 'flex', alignItems: 'center', padding: '6px 10px 0', background: V.chrome, color: V.text, fontSize: 12 },
    children: jsx('span', { style: { flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontWeight: 600 }, children: title }) })
}
function TransportRail({ kind, live, playing, time, duration, level, muted, boost, canBoost, why, rate, onPlay, onSeek, onLevel, onRate, onFullscreen }) {
  const queued = useValue(pins).length
  const span = isFinite(duration) && duration > 0 ? duration : 0
  const at = Math.min(Number(time) || 0, span > 0 ? span : 1)
  return jsxs('div', { className: 'media-dock-transport', 'data-transport': kind,
    style: { display: 'flex', alignItems: 'center', gap: 2, padding: '2px 6px 6px', background: V.chrome, borderTop: '1px solid ' + V.stroke, flex: '0 0 auto', minWidth: 0 }, children: [
      iconBtn(playing ? '❚❚' : '▶', onPlay, kind === 'page' ? 'Play/Pause page media' : 'Play/Pause'),
      // Queue steps exist only when the queue can step: an always-on pair of arrows over an empty queue is two dead controls.
      queued ? iconBtn('⏮', () => playPrev(), 'Previous in queue') : null, queued ? iconBtn('⏭', () => playNext(), 'Next in queue') : null,
      live ? jsx('span', { 'aria-label': 'Live stream: elapsed, no seek bar', style: { flex: 1, minWidth: 44, color: V.accent, fontSize: 10, fontWeight: 700, letterSpacing: 0.4 }, children: 'LIVE' }) : jsx('input', { type: 'range', min: 0, max: span > 0 ? span : 1, step: 0.1, value: at, onChange: (e) => onSeek(Number(e && e.target ? e.target.value : 0)),
        'aria-label': kind === 'page' ? 'Seek page media' : 'Seek', style: { flex: 1, minWidth: 44, accentColor: V.accent } }), jsx('span', { style: { color: V.dim, fontSize: 10, whiteSpace: 'nowrap', fontVariantNumeric: 'tabular-nums' },
        children: live ? formatTime(at) : formatTime(at) + ' / ' + formatTime(span) }), jsx(VolumeControl, { level, muted, boost, canBoost, why, onLevel }),
      jsx(CaptionControl, { owner: kind }), iconBtn(String(rate) + '×', onRate, (kind === 'page' ? 'Page ' : '') + 'playback speed. Click to step'),
      iconBtn('⛶', onFullscreen, 'Fullscreen. Click again or Esc to exit'), ] })
}
function PageTransport({ showTitle }) {
  const m = useValue(pageMedia), now = useValue(play)
  if (!m || !m.has) return null
  const level = (v) => sendGuest('level', v, (s) => { if (s) pageMedia.set(pageMediaState(s)) })
  return jsxs('div', { className: 'media-dock-page-transport', style: { display: 'flex', flexDirection: 'column', flex: '0 0 auto', minWidth: 0 },
    children: [ showTitle ? jsx(NowPlaying, { title: now.title }) : null,
      jsx(TransportRail, { kind: 'page', live: !!m.live, playing: !m.paused, time: m.t, duration: m.d, level: m.muted ? 0 : m.v, muted: m.muted, boost: m.boost, canBoost: m.can, why: m.why, rate: m.r,
        onPlay: () => sendGuest('toggle'), onSeek: (v) => sendGuest('seek', v), onLevel: level, onRate: () => sendGuest('rate', nextRate(m.r)),
        onFullscreen: dockFullscreen }), ] })
}
// -------------------------------------------------------------- our own player
// Same level model as the page agent on the element we own: ≤100% volume, >100% a gain
// node, and a graph only for a source that cannot taint it: cross-origin would go silent.
function nativeBoost(n) {
  if (n.__mdG) return n.__mdG
  const C = window.AudioContext || window.webkitAudioContext; if (!C) return null
  try { const ctx = new C(), g = ctx.createGain(), s = ctx.createMediaElementSource(n); s.connect(g); g.connect(ctx.destination); n.__mdG = { ctx, g }; return n.__mdG } catch { return null }
}
// Every gain change is a short linear ramp: a slider drag must not click, and engaging the
// boost stage must not double the loudness in one sample.
function rampGain(g, ctx, target) {
  try {
    const t = ctx.currentTime
    if (g.gain.cancelScheduledValues) g.gain.cancelScheduledValues(t)
    if (g.gain.setValueAtTime) g.gain.setValueAtTime(g.gain.value, t)
    if (g.gain.linearRampToValueAtTime) g.gain.linearRampToValueAtTime(target, t + 0.08)
    else g.gain.value = target
  } catch { try { g.gain.value = target } catch { /* detached */ } }
}
function sameOriginMedia(n) { try { const x = new URL(n.currentSrc || n.src, location.href); return x.protocol === 'blob:' || x.protocol === 'data:' || x.origin === location.origin } catch { return false } }
function applyNativeLevel(n, level) {
  const v = clampVolume(level)
  if (!n) return { ok: true, v }
  if (v > 100) {
    if (!sameOriginMedia(n)) return { ok: false, v: 100, why: 'this source is cross-origin, so boost would silence it' }
    const o = nativeBoost(n); if (!o) return { ok: false, v: 100, why: 'this build has no Web Audio' }
    try { if (o.ctx.state !== 'running') o.ctx.resume() } catch { /* suspended */ }
    n.volume = 1; n.muted = !!settings.get().dockMuted; rampGain(o.g, o.ctx, v / 100)
    return { ok: true, v }
  }
  n.volume = v / 100
  n.muted = !!settings.get().dockMuted || v === 0
  // A boost node left at 1 while the element drops is an instant level jump; ramp the gain back.
  if (n.__mdG) rampGain(n.__mdG.g, n.__mdG.ctx, 1)
  return { ok: true, v }
}
function trackList(n) {
  const out = []
  try { const L = n.textTracks || []; for (let i = 0; i < L.length; i++) out.push({ i, label: String(L[i].label || L[i].language || ('Track ' + (i + 1))), lang: String(L[i].language || ''), kind: String(L[i].kind || '') }) } catch { /* no tracks */ }
  return out
}
/** Real transport. Every control mutates the DOM node we own, or a settings key. */
function NativePlayer({ now, showTitle }) {
  const cfg = useValue(settings)
  const mediaRef = useRef(null)
  const [playing, setPlaying] = useState(false)
  const [muted, setMuted] = useState(false)
  const [volume, setVolume] = useState(clampVolume(cfg.volume))
  const [rate, setRate] = useState(Number(cfg.rate) || 1)
  const [time, setTime] = useState(0)
  const [duration, setDuration] = useState(0)
  const [failed, setFailed] = useState(null)
  const [needPlay, setNeedPlay] = useState(false); const [startMuted, setStartMuted] = useState(false)
  const tag = now.media === 'audio' ? 'audio' : 'video'
  const el = () => mediaRef.current
  const toggle = () => toggleMediaNode(el())
  const [boost, setBoost] = useState(false)
  const [boostWhy, setBoostWhy] = useState('')
  const setVol = (v) => {
    const r = applyNativeLevel(el(), v)
    setVolume(r.v)
    setMuted(r.v === 0)
    setBoost(!!r.ok && !!el() && !!el().__mdG && el().__mdG.g.gain.value > 1.0001)
    setBoostWhy(r.ok ? '' : (r.why || ''))
    patchSettings({ volume: r.v })
  }
  const toggleMute = () => {
    const m = !muted
    setMuted(m)
    const n = el()
    if (n) n.muted = m || !!cfg.dockMuted
  }
  // The dock-wide mute outranks the rail's own: turning it on silences this element too.
  useEffect(() => { const n = el(); if (n) n.muted = !!cfg.dockMuted || volume === 0 }, [cfg.dockMuted, volume])
  useEffect(() => {
    let active = null
    const onCue = () => {
      let s = ''
      try { for (let k = 0; active && active.activeCues && k < active.activeCues.length; k++) { const x = String(active.activeCues[k].text || ''); if (x) s += (s ? ' ' : '') + x } } catch { /* none */ }
      if (s !== captions.get().cue) setCaps({ cue: s })
    }
    nativeTrackHook = (i) => {
      const n = el()
      if (active) { try { active.removeEventListener('cuechange', onCue) } catch { /* none */ } active = null }
      if (n) { try { for (let k = 0; k < n.textTracks.length; k++) n.textTracks[k].mode = k === i ? 'hidden' : 'disabled' } catch { /* none */ } }
      active = n && n.textTracks ? n.textTracks[i] : null
      if (active) { try { active.addEventListener('cuechange', onCue) } catch { /* none */ } }
      setCaps({ owner: 'native', sel: i, lang: i >= 0 ? String((trackList(n)[i] || {}).lang || '') : '', cue: '' })
    }
    return () => { nativeTrackHook = null; if (active) { try { active.removeEventListener('cuechange', onCue) } catch { /* detached */ } } }
  }, [now.src])
  const seekTo = (v) => { const n = el()
    if (n && isFinite(duration) && duration > 0) n.currentTime = v
    setTime(v) }
  const setSpeed = (r) => { setRate(r); const n = el()
    if (n) n.playbackRate = r
    patchSettings({ rate: r }) }
  // One effect applies settings to the element: a new source and a change made in Settings
  // while this player is open both land here (the Settings slider used to be ignored until
  // the next load).
  useEffect(() => {
    const n = el()
    if (n) { const r = applyNativeLevel(n, cfg.volume); n.playbackRate = Number(cfg.rate) || 1
      setVolume(r.v); setBoost(!!r.ok && r.v > 100); setBoostWhy(r.ok ? '' : (r.why || '')) }
    setNeedPlay(false); setStartMuted(false)
  }, [now.src, cfg.volume, cfg.rate])
  // Autoplay is a decision, not an attribute: Chromium refuses an unmuted play() with no live
  // gesture, and a queue row that only has the attribute loads and does nothing. Play here and
  // on readiness, falling back to muted once; the fallback is what makes a click start the file.
  const tryAuto = (n) => {
    if (!n || !(cfg.autoplay || now.autoplayOnce) || !n.paused || n.currentTime > 0.25) return
    const pr = n.play()
    if (pr && pr.catch) pr.catch(() => { try { n.muted = true; setStartMuted(true); const p2 = n.play(); if (p2 && p2.catch) p2.catch(() => { /* refused even muted */ }) } catch { /* refused */ } })
  }
  // Both attempts can still end paused; say so with a control instead of a broken-looking 0:00.
  useEffect(() => {
    if (!(cfg.autoplay || now.autoplayOnce)) return undefined
    const t = setTimeout(() => {
      const n = el()
      setNeedPlay(autoplayNeedsGesture({ waited: true, paused: !n || n.paused, t: n ? n.currentTime : 0, failed }))
    }, 1500)
    return () => clearTimeout(t)
  }, [now.src, now.autoplayOnce, failed])
  useEffect(() => {
    const n = el(); if (!n) return undefined
    const go = () => tryAuto(n)
    go()
    n.addEventListener('canplay', go)
    n.addEventListener('loadeddata', go)
    return () => { n.removeEventListener('canplay', go); n.removeEventListener('loadeddata', go) }
  }, [now.src, now.autoplayOnce])
  // Keys: re-registered every render so the closures hold this render's duration/volume.
  useEffect(() => {
    nativeCtl = {
      toggle, seekBy: (by) => { const n = el(); if (!n) return
        const end = isFinite(duration) && duration > 0 ? duration : (n.duration || 0)
        n.currentTime = Math.max(0, Math.min(end || Infinity, n.currentTime + by)); setTime(n.currentTime) }, levelBy: (by) => setVol(clampVolume(volume + by)),
      toggleMute, }
    return () => { nativeCtl = null }
  })
  const mediaProps = {
    key: now.src, ref: mediaRef, src: now.src, autoPlay: !!(cfg.autoplay || now.autoplayOnce), playsInline: true,
    onCanPlay: () => { const n = el(); if (n) tryAuto(n) },   // readiness beats effect timing
    onPlay: () => { setPlaying(true); setNeedPlay(false); if (cfg.immersiveOnPlay) immersive.set(true) }, onPause: () => { setPlaying(false); const n = el(); if (n) remember(now.src, n.currentTime, n.duration) },
    onTimeUpdate: (e) => { const n = e && e.target, t = n ? n.currentTime : 0; setTime(t); if (n && Math.floor(t) % 5 === 0) remember(now.src, t, n.duration) }, onLoadedMetadata: (e) => {
      const n = e && e.target, d = n ? n.duration : 0
      setDuration(d); resumeAt(n, now.src, d)
      const r = applyNativeLevel(n, settings.get().volume)
      if (n) { setVolume(r.v); setBoost(!!r.ok && r.v > 100); setBoostWhy(r.ok ? '' : (r.why || '')) }
      setCaps({ owner: 'native', tracks: trackList(n), sel: -1, cue: '', lang: '', why: '' })
    }, onDurationChange: (e) => setDuration(e && e.target ? e.target.duration : 0),
    onVolumeChange: (e) => {
      const n = e && e.target
      // While a gain stage is boosting, element volume is pinned at 1, so reading it back would report 100% and erase the level the user set.
      if (!n || (n.__mdG && n.__mdG.g.gain.value > 1.0001)) return
      setMuted(!!n.muted); if (!n.muted) setStartMuted(false); setVolume(clampVolume((n.volume || 0) * 100))
    }, onEnded: () => { setPlaying(false); immersive.set(false); advance() },
    onError: (e) => {
      const n = e && e.target
      setFailed(mediaErrorCopy(n && n.error ? n.error.code : null))
      diag.set({ transport: 'native', lastError: 'media-error', source: now.src })
    }, style: { flex: 1, minHeight: 0, width: '100%', background: V.editor, objectFit: 'contain', display: 'block' },
  }
  return jsxs('div', { ref: stageRef, className: 'media-dock-stage', style: { flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', background: V.editor, position: 'relative' },
    children: [ jsx(tag, mediaProps),
      needPlay ? jsx('button', { onClick: () => { setNeedPlay(false); toggle() }, style: { position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%)', padding: '10px 16px', border: '1px solid ' + V.stroke, borderRadius: 8, background: V.chrome, color: V.text, fontSize: 12, cursor: 'pointer', zIndex: 4 }, children: 'Press play to start' }) : null,
      startMuted ? jsx('div', { style: { padding: '4px 10px', background: V.chrome, color: V.dim, fontSize: 10, textAlign: 'center', borderTop: '1px solid ' + V.stroke }, children: 'Started without sound: this browser blocks audio until you click. Press M or the speaker to unmute.' }) : null,
      jsx(CueLine, { owner: 'native' }), failed ? jsx('div', { style: { padding: '8px 10px', background: V.chrome, color: V.text, fontSize: 11, textAlign: 'center' }, children: failed }) : null,
      showTitle ? jsx(NowPlaying, { title: now.title || now.src }) : null, jsx(TransportRail, { kind: 'native', playing, time, duration, level: volume, muted, boost, canBoost: !boostWhy, why: boostWhy, rate,
        onPlay: toggle, onSeek: seekTo, onLevel: setVol, onRate: () => setSpeed(nextRate(rate)),
        onFullscreen: dockFullscreen }), ] })
}
function Stage({ now, showTitle }) {
  if (now.error) return jsx(RefusalWell, { now })
  if (now.kind === 'native' && now.src) return jsx(NativePlayer, { key: now.src, now, showTitle })
  return now.kind === 'page' && now.src ? jsx(PageFrame, { now }) : jsx(EmptyWell, {})
}
// ---------------------------------------------------------------------- queue
function keepRow(e) { if (e) e.stopPropagation && e.stopPropagation() }
function clearPins() { if (pins.get().length) pins.set([]) }
function saveToShelf() { const p = makePin(play.get().raw || (play.get().pageUrl || '')); if (p) shelf.set(upsertPin(shelf.get(), p, SHELF_MAX)) }
function clearShelf() { if (shelf.get().length) shelf.set([]) }
function shufflePins() { const a = pins.get().slice(); for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); const x = a[i]; a[i] = a[j]; a[j] = x } if (a.length > 1 && a.every((p, i) => p === pins.get()[i])) { const x = a[0]; a[0] = a[1]; a[1] = x } pins.set(a) }
function Queue({ activeUrl, onOpen, onAdd }) {
  const list = useValue(pins), cfg = useValue(settings), saved = useValue(shelf), mode = useValue(listMode)
  if (!cfg.showQueue) return null
  const shelfMode = mode === 'saved', rows = shelfMode ? saved : list
  const inList = !!activeUrl && rows.some((p) => p.url === activeUrl)
  const modeBtn = (label, m) => jsx('button', { type: 'button', onClick: () => listMode.set(m), 'aria-pressed': mode === m, title: 'Show ' + label.toLowerCase(),
    style: { border: 0, background: mode === m ? V.editor : 'transparent', color: mode === m ? V.text : V.dim, borderRadius: 5, padding: '3px 7px', fontSize: 11, cursor: 'pointer' }, children: label })
  return jsxs('div', { role: 'tablist', 'aria-label': shelfMode ? 'Saved links' : 'Queue', style: { flex: '0 1 auto', display: 'flex', flexDirection: 'column', background: V.chrome, borderTop: '1px solid ' + V.stroke },
    children: [
      // One header line owns the bulk actions, and the two labels switch the list under it.
      jsxs('div', { style: { display: 'flex', alignItems: 'center', gap: 2, padding: '2px 8px 2px 2px' }, children: [ modeBtn('Queue', 'queue'), modeBtn('Saved', 'saved'),
        jsx('button', { type: 'button', onClick: () => { if (!inList) (shelfMode ? saveToShelf : onAdd)() }, title: inList ? (shelfMode ? 'Already saved' : 'Already in the queue') : (shelfMode ? 'Save current URL to the shelf' : 'Add current URL to the queue'),
          style: { display: 'flex', alignItems: 'center', gap: 6, flex: 1, minWidth: 0, border: 0, background: 'transparent', color: inList ? V.dim : V.sub, cursor: inList ? 'default' : 'pointer', padding: '5px 8px', fontSize: 12, textAlign: 'left' },
          children: [glyph(inList ? 'check' : 'add'), jsx('span', { style: { overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }, children: inList ? (shelfMode ? 'Saved' : 'In queue') : (shelfMode ? 'Save current' : 'Add current') })] }),
        rows.length ? jsx('span', { style: { color: V.dim, fontSize: 10, whiteSpace: 'nowrap', padding: '0 2px' }, children: rows.length + (shelfMode ? ' saved' : ' queued') }) : null,
        !shelfMode && rows.length > 1 ? chromeBtn('Shuffle', shufflePins, { title: 'Shuffle the queue' }) : null,
        rows.length ? chromeBtn('Clear', shelfMode ? clearShelf : clearPins, { title: shelfMode ? 'Empty the shelf' : 'Empty the queue' }) : null,
      ] }),
      // Rows scroll under the header; the actions never scroll away. A saved row has no play order.
      rows.length ? jsx('div', { style: { overflowY: 'auto', maxHeight: 148 }, children: rows.map((p) => {
        const on = p.url === activeUrl, owner = shelfMode ? shelf : pins
        const drop = (e) => { if (e && e.stopPropagation) e.stopPropagation(); owner.set(removePin(owner.get(), p.id)) }
        return jsxs('div', { key: p.id, role: 'tab', 'aria-selected': on, tabIndex: 0, onClick: () => onOpen(p.url), onKeyDown: (e) => { if (rowEnterOpens(e)) onOpen(p.url) },
          style: { display: 'flex', alignItems: 'center', gap: 8, padding: '6px 8px 6px 10px', cursor: 'pointer', fontSize: 12, color: on ? V.text : V.sub, background: on ? V.editor : 'transparent', borderLeft: on ? '2px solid ' + V.accent : '2px solid transparent' },
          children: [glyph(on ? 'play' : 'circle-outline'), jsxs('div', { style: { flex: 1, minWidth: 0 }, children: [
              jsx('div', { style: { overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }, children: p.title }), jsx('div', { style: { fontSize: 9, color: V.dim }, children: p.host }),
            ] }), shelfMode ? null : iconBtn('↑', (e) => { keepRow(e); pins.set(movePin(pins.get(), p.id, -1)) }, 'Move earlier'),
            shelfMode ? null : iconBtn('↓', (e) => { keepRow(e); pins.set(movePin(pins.get(), p.id, 1)) }, 'Move later'), iconBtn('×', drop, 'Remove')] })
        }) }) : jsx('div', { style: { padding: '0 10px 6px', color: V.dim, fontSize: 10 }, children: shelfMode ? 'Shelf is empty. Save current keeps this page here.' : 'Queue is empty. Add current parks this page here.' }), ] })
}
function Suggestions({ draft, open, onPick }) {
  const cfg = useValue(settings)
  if (!cfg.showSuggestions || !open) return null
  const rows = suggestVisits(visits.get(), draft, SUGGEST_MAX)
  if (!rows.length) return null
  return jsx('div', { style: { background: V.chrome, borderBottom: '1px solid ' + V.stroke, maxHeight: 168, overflowY: 'auto' }, children: rows.map((r) => jsx('button', { key: r.host, type: 'button',
      onMouseDown: (e) => { if (e && e.preventDefault) e.preventDefault(); onPick(r.url) },
      style: { display: 'flex', alignItems: 'center', width: '100%', gap: 8, padding: '6px 12px', border: 0, background: 'transparent', color: V.sub, cursor: 'pointer', fontSize: 12, textAlign: 'left' },
      children: [glyph('history'), jsx('span', { style: { flex: 1 }, children: r.title }), jsx('span', { style: { color: V.dim, fontSize: 10 }, children: String(r.count) })] })) })
}
// ------------------------------------------------------- resize grips + size readout
function SizeReadout({ size, onCycle }) {
  const label = size.w + '×' + size.h
  const fire = (e) => {
    if (e && e.preventDefault) e.preventDefault()
    if (e && e.stopPropagation) e.stopPropagation()
    onCycle()
  }
  return jsx('button', { type: 'button', onClick: fire, 'data-floating-no-drag': 'true', title: 'Steps this card through its saved sizes.', 'aria-label': 'Card size ' + label,
    style: { border: '1px solid ' + V.stroke, background: 'transparent', color: V.sub, borderRadius: 5, padding: '2px 8px', fontSize: 10, cursor: 'pointer', fontVariantNumeric: 'tabular-nums' }, children: 'Card ' + label })
}
function EdgeGrips({ onResize, anchor, fixed, z }) {
  const corner = { [anchor.left ? 'right' : 'left']: 0, [anchor.top ? 'bottom' : 'top']: 0 }
  // Grips outrank every chrome band (address bar and footer are zIndex 6): at 5 the transparent footer ate the corner's pointerdown, so the handle drew itself and did nothing.
  const grip = (axis, extra, cursor, title, child) => jsx('div', { key: axis, 'data-floating-no-drag': 'true', title,
    onPointerDown: (e) => onResize(axis, e), style: { position: 'absolute', zIndex: 9, pointerEvents: 'auto', cursor, ...extra }, children: child })
  // Two 45° strokes hugging the free corner: the size grip every window manager uses. A ring in a circle reads as a control (record / radio), not a handle.
  const flip = 'scale(' + (anchor.left ? -1 : 1) + ',' + (anchor.bottom ? -1 : 1) + ')'
  const lines = jsx('svg', { width: 16, height: 16, viewBox: '0 0 16 16', 'aria-hidden': 'true', style: { display: 'block', pointerEvents: 'none', transform: flip }, children: jsx('path', { d: 'M3 13 13 3M3 7.5 7.5 3', fill: 'none', stroke: V.sub, strokeWidth: 1, strokeLinecap: 'round', opacity: 0.6 }) })
  return jsxs('div', { style: { position: fixed ? 'fixed' : 'absolute', inset: 0, zIndex: z || 9, pointerEvents: 'none' }, children: [ grip('x', { left: 0, top: 28, bottom: 28, width: 8 }, 'ew-resize', 'Drag to change width'),
    grip('y', { bottom: 0, left: 28, right: 28, height: 8 }, 'ns-resize', 'Drag to change height'), grip('corner', { ...corner, width: 16, height: 16 }, 'nesw-resize', 'Drag to resize', lines),
  ] })
}
// ------------------------------------------------------------------ the dock
function MediaDock({ toggleFloat, onClose }) {
  const now = useValue(play)
  const auto = useValue(automation)
  const cfg = useValue(settings)
  const pk = useValue(picked), fs = useValue(focusedStored)
  const gate = sessionDecision(cfg.sessionScope, fs, pk)
  const focus = useValue(immersive)
  const size = useValue(cardSize)
  const nav = useValue(navState)
  const [width, setWidth] = useState(0)
  const layout = layoutFor(width, cfg.layout)
  const chrome = chromeFor(focus, layout, now.kind)
  const [draft, setDraft] = useState(now.raw || '')
  const [suggesting, setSuggesting] = useState(false)
  const urlRef = useRef(null)
  const rootRef = useRef(null)
  useEffect(() => { if (now.raw && now.raw !== draft) setDraft(now.raw) }, [now.raw])
  useEffect(() => {
    const el = rootRef.current
    if (el && !now.floating) releaseDockPaint(el)
    const s = cardSize.get()
    const c = clampSize(s.w, s.h, globalThis.innerWidth || 1920, globalThis.innerHeight || 1080)
    if (c.w !== s.w || c.h !== s.h) commitSize(c)
  }, [now.floating])
  useEffect(() => {
    const node = urlRef.current
    if (node && typeof node.focus === 'function') node.focus()
    hostFocus = () => { const n = urlRef.current; if (n && typeof n.focus === 'function') n.focus() }; return () => { hostFocus = null }
  }, [])
  useEffect(() => { applyGuestMute() }, [cfg.dockMuted])
  useEffect(() => {
    const el = rootRef.current
    if (!el || typeof globalThis.ResizeObserver !== 'function') return
    const ro = new globalThis.ResizeObserver((entries) => {
      if (entries && entries[0]) setWidth(Math.round(entries[0].contentRect.width))
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  const go = () => {
    const parsed = parseMediaUrl(draft)
    const cur = play.get()
    loadUrl(draft)
    // Same address already showing: the key cannot change, so Go must reload explicitly.
    if (parsed && parsed.ok && parsed.kind === 'page' && parsed.src === cur.src) reloadGuest()
  }
  const onKey = (ev) => {
    if (ev && ev.key === 'Enter') { if (ev.preventDefault) ev.preventDefault(); go() }
  }
  const onPaste = (ev) => {
    const clip = ev && ev.clipboardData && ev.clipboardData.getData('text')
    if (!clip) return
    // A refused paste must say why: swallowing it made an HLS manifest look like the paste
    // never landed. loadUrl owns both arms (ok and named refusal).
    const text = String(clip).trim()
    if (ev.preventDefault) ev.preventDefault()
    setDraft(text)
    loadUrl(text)
  }
  const onFocusUrl = (ev) => {
    setSuggesting(true)
    const n = ev && ev.target
    if (n && typeof n.select === 'function') { try { n.select() } catch { /* detached */ } }
  }
  const onDragOver = (ev) => {
    if (ev.preventDefault) ev.preventDefault()
    if (ev.dataTransfer) ev.dataTransfer.dropEffect = 'copy'
  }
  const onDrop = (ev) => {
    if (ev.preventDefault) ev.preventDefault()
    const uri = droppedUrl(ev)
    if (!uri) return
    setDraft(uri)
    loadUrl(uri)
  }
  const pinCurrent = () => {
    const live = now.kind === 'page' ? (now.pageUrl || now.raw) : null
    const pin = makePin(live || draft || now.raw || now.pageUrl)
    if (pin) pins.set(upsertPin(pins.get(), pin, PIN_MAX))
    else if (urlRef.current && typeof urlRef.current.focus === 'function') urlRef.current.focus()
  }
  // Pane-local keys, only while the dock holds focus: space/arrows/m/f on the video or the
  // page's own player. A focused input keeps its typing; the guest keeps its own keys.
  const onDockKey = (ev) => {
    if (!ev || ev.defaultPrevented || ev.altKey || ev.ctrlKey || ev.metaKey) return
    const t = ev.target, tag = t && t.tagName ? String(t.tagName).toUpperCase() : ''
    const type = t && t.type ? String(t.type).toLowerCase() : ''
    // Text fields keep every key. A focused range keeps its arrows (they fire onChange and
    // seek once); space still reaches the transport, so play/pause works after a seek.
    if (tag === 'TEXTAREA' || tag === 'SELECT' || (t && t.isContentEditable)) return
    if (tag === 'INPUT' && type !== 'range') return
    const k = ev.key, page = play.get().kind === 'page', pm = pageMedia.get()
    if (type === 'range' && k.indexOf('Arrow') === 0) return
    const run = (op, v) => { if (page) sendGuest(op, v); else if (nativeCtl && nativeCtl[op]) nativeCtl[op](v) }
    if (k === ' ' || k === 'Spacebar') { if (ev.preventDefault) ev.preventDefault(); run('toggle') }
    else if (k === 'ArrowLeft' || k === 'ArrowRight') {
      if (ev.preventDefault) ev.preventDefault()
      const by = k === 'ArrowLeft' ? -5 : 5
      if (page) { if (pm.has) sendGuest('seek', Math.max(0, (pm.t || 0) + by)) } else run('seekBy', by)
    } else if (k === 'ArrowUp' || k === 'ArrowDown') {
      if (ev.preventDefault) ev.preventDefault()
      const by = k === 'ArrowUp' ? 5 : -5
      if (page) { if (pm.has) sendGuest('level', Math.max(0, Math.min(300, (pm.v || 0) + by))) } else run('levelBy', by)
    } else if (k === 'm' || k === 'M') { if (ev.preventDefault) ev.preventDefault(); if (!page) run('toggleMute') }
    else if (k === 'f' || k === 'F') { if (ev.preventDefault) ev.preventDefault(); dockFullscreen() }
  }
  const openSettings = () => {
    const href = SDK.pluginSettingsHref ? SDK.pluginSettingsHref(ID) : '/settings?tab=plugins&plugin=' + ID
    if (host && typeof host.navigate === 'function') { try { host.navigate(href) } catch { /* older desktop */ } }
  }
  return jsxs('div', {
    ref: (n) => {
      const prev = rootRef.current
      rootRef.current = n
      if (prev) { surfaces.delete(prev); if (frontRoot === prev) frontRoot = null }
      if (n) surfaces.set(n, { root: n })
    }, onPointerDownCapture: () => {
      frontRoot = rootRef.current
      // Clicking the stage makes the pane the keyboard owner; the URL field and the guest keep their own focus because both sit outside this capture.
      const r = rootRef.current
      if (r && typeof r.focus === 'function' && globalThis.document && globalThis.document.activeElement !== r) {
        try { r.focus({ preventScroll: true }) } catch { /* older DOM */ }
      }
    }, tabIndex: 0, onKeyDown: onDockKey,
    className: 'media-dock', onDragOver, onDrop, style: { display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0, overflow: 'hidden', outline: 'none',
      background: V.editor, color: V.text, position: 'relative' }, children: [
      // A rail of our own, not the site's: it is host DOM above the guest, so no page can cover
      // it. The stage starts below it, which keeps the rail out of the player's pixels.
      auto.own ? jsx('div', { className: 'media-dock-theater-rail', style: { position: 'fixed', top: THEATER_CFG.inset + 'px', left: THEATER_CFG.inset + 'px', right: THEATER_CFG.inset + 'px', height: THEATER_CFG.rail + 'px', boxSizing: 'border-box', zIndex: THEATER_CFG.z + 10, pointerEvents: 'auto', display: 'flex', alignItems: 'center', gap: 6, padding: '0 8px', background: V.chrome, border: '1px solid ' + V.stroke, borderBottom: 'none', borderRadius: '10px 10px 0 0' },
        children: [jsx('span', { style: { marginRight: 'auto', fontSize: 11, color: V.sub }, children: 'Theater' }), chromeBtn('Exit theater', toggleTheater, { title: 'Return the player to its dock' }), chromeBtn('Close', onClose, { title: 'Close Media Dock' })] }) : null,
      (now.floating || auto.own) && chrome.grips ? jsx(EdgeGrips, { onResize: (axis, ev) => startResize(axis, ev, auto.own ? theaterHandle() : rootRef.current, auto.own), anchor: auto.own ? THEATER_EDGES : EDGES, fixed: auto.own, z: auto.own ? THEATER_CFG.z + 8 : 9 }) : null,
      chrome.address ? jsxs('div', { style: { display: 'flex', gap: 4, padding: '6px 8px', alignItems: 'center', flex: '0 0 auto', background: V.chrome, borderBottom: '1px solid ' + V.stroke, position: 'relative', zIndex: 6 }, children: [
          // Back / Forward / Reload act on the guest only, never on a native player.
          now.kind === 'page' ? navBtn('◀', () => navGo(-1), 'Back', nav.back) : null, now.kind === 'page' ? navBtn('▶', () => navGo(1), 'Forward', nav.fwd) : null,
          now.kind === 'page' ? (nav.loading ? navBtn('×', stopGuest, 'Stop loading', true, true) : navBtn('⟳', reloadGuest, 'Reload page', true)) : null,
          jsx('input', { ref: urlRef, type: 'text', value: draft, placeholder: 'Paste a URL', 'aria-label': 'URL', className: 'desktop-input-chrome',
            onChange: (ev) => setDraft(ev && ev.target ? ev.target.value : ''), onKeyDown: onKey, onPaste, onFocus: onFocusUrl, onBlur: () => setSuggesting(false),
            style: { flex: 1, minWidth: 0, height: 28, padding: '0 10px', fontSize: 12, color: V.text, caretColor: V.text, borderRadius: 'var(--radius-md, 6px)' } }), chromeBtn('Go', go),
        ] }) : null, chrome.suggestions ? jsx(Suggestions, { draft, open: suggesting,
        onPick: (url) => { setDraft(url); setSuggesting(false); loadUrl(url) } }) : null, jsx(Stage, { now, showTitle: chrome.nowPlaying }),
      now.kind === 'page' ? jsx(PageTransport, { showTitle: chrome.nowPlaying }) : null,
      gate.show ? null : jsx('div', { style: { position: 'absolute', inset: 0, zIndex: 40, display: 'flex', background: V.editor }, children: jsx(PickedWell, { id: gate.storedId }) }),
      chrome.queue ? jsx(Queue, { activeUrl: now.pageUrl || now.raw, onOpen: (url) => { setDraft(url); loadUrl(url, true) }, onAdd: pinCurrent }) : null,
      focus ? jsx('div', { style: { position: 'absolute', top: 8, right: 8, zIndex: 30, display: 'flex', gap: 6 }, children: [
          iconBtn('✕', exitFocus, 'Exit focus (Esc)'), iconBtn('⏮', () => playPrev(), 'Previous in queue'),
          iconBtn('⏭', () => playNext(), 'Next in queue'), iconBtn('⛶', () => fullscreenToggle(rootRef.current), 'Fullscreen. Click again or Esc to exit'),
        ] }) : null,
      chrome.footer ? jsx('div', { style: { display: 'flex', justifyContent: 'flex-end', alignItems: 'center', gap: 4, padding: '4px 8px 6px', borderTop: '1px solid ' + V.stroke, flexWrap: 'wrap', flex: '0 0 auto', position: 'relative', zIndex: 6 }, children:
          jsxs('div', { style: { display: 'flex', gap: 4, flexWrap: 'wrap', justifyContent: 'flex-end' }, children: [ now.src ? chromeBtn(auto.own ? 'Exit theater' : 'Theater', toggleTheater,
              { title: auto.own ? 'Return the player to its dock' : 'Grow the player to almost fill the window' }) : null, chromeBtn('Settings', openSettings, { title: 'Media Dock settings' }),
            // The size pill belongs to the FLOATING card only; docked it read as a queue number.
            !auto.own && now.floating && chrome.ladder ? jsx(SizeReadout, { size, onCycle: () => cycleSize(rootRef.current) }) : null, auto.own ? null : chromeBtn(now.floating ? 'Dock' : 'Detach', toggleFloat),
            chromeBtn('Close', onClose), ] }) }) : null,
    ] })
}
// --------------------------------------------------------------- settings pages
// One shape for every page: a `group` row opens a section, the row before it closes one:
// the last row of a section carries no rule, so sections end instead of trailing a line.
function Group({ label }) { return jsx('div', { style: { fontSize: 10, letterSpacing: '.08em', textTransform: 'uppercase', color: V.dim, margin: '18px 0 2px' }, children: label }) }
// The sidebar lists these pages; the main screen has to offer them too, or finding one
// means hunting a 15-item sidebar. Deep link = pluginSettingsHref(ID, page) -> ?ppage.
function goSettings(page) { const href = SDK.pluginSettingsHref ? SDK.pluginSettingsHref(ID, page) : '/settings?tab=plugins&plugin=' + ID + '&ppage=' + page
  if (host && typeof host.navigate === 'function') { try { host.navigate(href) } catch { /* older desktop */ } } }
function NavCard({ page, title, hint }) { return jsx('button', { type: 'button', onClick: () => goSettings(page), title: 'Open ' + title,
  style: { display: 'block', textAlign: 'left', width: '100%', border: '1px solid ' + V.stroke, background: 'transparent', borderRadius: 8, padding: '10px 12px', cursor: 'pointer', color: V.text },
  children: [jsx('div', { style: { fontSize: 12, fontWeight: 600 }, children: title }), jsx('div', { style: { fontSize: 10, color: V.dim, marginTop: 3, lineHeight: 1.4 }, children: hint })] }) }
function Row({ label, hint, children, last }) {
  return jsxs('div', { style: { display: 'flex', alignItems: 'center', gap: 12, padding: '10px 2px', minHeight: 44, borderBottom: last ? 'none' : '1px solid ' + V.stroke }, children: [jsxs('div', { style: { flex: 1, minWidth: 0 }, children: [jsx('div', { style: { fontSize: 12, color: V.text, lineHeight: 1.3 }, children: label }), hint ? jsx('div', { style: { fontSize: 10, color: V.dim, marginTop: 2, lineHeight: 1.4 }, children: hint }) : null] }), children] })
}
function SwitchRow({ label, hint, value, onChange, last }) {
  return jsx(Row, { label, hint, last, children: jsx('input', { type: 'checkbox', checked: !!value, 'aria-label': label, onChange: (e) => onChange(!!(e && e.target && e.target.checked)), style: { accentColor: V.accent, width: 16, height: 16, margin: 0, cursor: 'pointer' } }) }) }
function ChoiceRow({ label, hint, value, choices, onChange, last }) {
  return jsx(Row, { label, hint, last, children: jsxs('div', { style: { display: 'flex', gap: 5, flexWrap: 'wrap', justifyContent: 'flex-end' },
    children: choices.map((c) => { const on = value === c.value; return jsx('button', { key: c.value, type: 'button', 'aria-label': label + ': ' + c.label, title: c.label, 'aria-pressed': on, onClick: () => onChange(c.value),
      style: { border: '1px solid ' + (on ? V.accent : V.stroke), color: on ? V.accent : V.sub, fontWeight: on ? 600 : 400, background: on ? 'color-mix(in srgb, ' + V.accent + ' 14%, transparent)' : 'transparent', borderRadius: 6, padding: '3px 9px', fontSize: 10.5, lineHeight: 1.4, cursor: 'pointer' }, children: c.label }) }) }) }) }
function RangeRow({ label, hint, value, onChange, last }) {
  return jsx(Row, { label, hint, last, children: jsxs('div', { style: { display: 'flex', alignItems: 'center', gap: 8 }, children: [
    jsx('input', { type: 'range', min: 0, max: VOL_MAX, step: 1, value, 'aria-label': label, onChange: (e) => onChange(e && e.target ? e.target.value : 0), style: { accentColor: V.accent, width: 132 } }),
    jsx('span', { style: { fontSize: 11, color: V.sub, width: 34, textAlign: 'right', fontVariantNumeric: 'tabular-nums' }, children: String(value) + '%' }) ] }) })
}
function SettingsPage({ title, note, rows, cfg }) { const pk = useValue(picked), body = []
  rows.forEach((r, i) => {
    const last = !rows[i + 1] || rows[i + 1].kind === 'group'
    if (r.kind === 'group') body.push(jsx(Group, { key: 'g' + i, label: r.label }))
    else if (r.kind === 'nav') body.push(jsx('div', { key: 'nav', style: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))', gap: 8, marginTop: 10 }, children: r.items.map((it) => jsx(NavCard, { key: it.page, page: it.page, title: it.title, hint: it.hint })) }))
    else if (r.kind === 'sessions') body.push(jsxs('div', { key: 'sessions', children: [
      jsx('div', { style: { fontSize: 10, color: V.dim, padding: '6px 2px 2px' }, children: pk.length ? 'Picked chats: the dock shows only in these sessions.' : 'No picked chats yet. Use Show here in the dock.' }),
      ...pk.map((sid) => jsx(SwitchRow, { key: sid, label: sid, hint: 'Click to unpin', value: true, onChange: () => pickSession(sid) })) ] }))
    else { const C = r.kind === 'range' ? RangeRow : r.kind === 'switch' ? SwitchRow : ChoiceRow
      body.push(jsx(C, { key: r.key, label: r.label, hint: r.hint, last, value: cfg[r.key], choices: r.choices, onChange: (v) => patchSettings({ [r.key]: v }) })) }
  })
  return jsxs('div', { style: { maxWidth: 520 }, children: [jsx('div', { style: { fontSize: 13, fontWeight: 600 }, children: title }),
    note ? jsx('div', { style: { fontSize: 10, color: V.dim, marginTop: 4, lineHeight: 1.5 }, children: note }) : null, ...body] })
}
// Every page's reading order lives in one table, so "what comes next" is a data decision, not a layout guess.
const SETTINGS_PAGES = {
  overview: { title: 'Overview', note: 'Sign-ins, queue and resume points stay in this machine\'s app data folder. The only thing sent out is caption text you ask to translate.', rows: [ { kind: 'nav', items: [
      { page: 'playback', title: 'Playback', hint: 'Volume, speed, auto-advance, density.' }, { page: 'theater', title: 'Theater', hint: 'Grow the dock while an agent works.' },
      { page: 'sessions', title: 'Sessions', hint: 'All chats, or only the ones you pick.' }, { page: 'diagnostics', title: 'Diagnostics', hint: 'Live state and saved resume points.' }, ] },
    { kind: 'group', label: 'Startup' }, { kind: 'choice', key: 'restoreMode', label: 'On reopen', choices: [{ value: 'url', label: 'Last URL' }, { value: 'playing', label: 'Resume playing' }, { value: 'blank', label: 'Start blank' }] },
    { kind: 'switch', key: 'autoplay', label: 'Autoplay', hint: 'Native media starts as soon as a URL loads.' },
    { kind: 'group', label: 'Chrome' }, { kind: 'switch', key: 'immersiveOnPlay', label: 'Focus on play', hint: 'Hides the bars around the video when playback starts.' },
    { kind: 'switch', key: 'showQueue', label: 'Show queue' },
    { kind: 'switch', key: 'showSuggestions', label: 'Visit suggestions', hint: 'From hosts you have already opened.' },
    { kind: 'group', label: 'Notifications' }, { kind: 'switch', key: 'completionToasts', label: 'Other-chat completions', hint: 'Toast when another chat finishes. Clicking it collapses the dock and jumps to that chat.' }, ] },
  playback: { title: 'Playback', rows: [
    { kind: 'group', label: 'Sound' }, { kind: 'range', key: 'volume', label: 'Dock volume' },
    { kind: 'switch', key: 'dockMuted', label: 'Mute the dock' },
    { kind: 'choice', key: 'rate', label: 'Default speed', choices: RATES.map((r) => ({ value: r, label: r + '×' })) },
    { kind: 'group', label: 'Queue' }, { kind: 'switch', key: 'autoAdvance', label: 'Auto-advance', hint: 'Plays the next queued item when a file ends. A page has no end event, so use Next.' },
    { kind: 'switch', key: 'loop', label: 'Loop queue' },
    { kind: 'group', label: 'Layout' }, { kind: 'choice', key: 'layout', label: 'Density', hint: 'Auto follows the pane width.', choices: LAYOUT_TIERS.map((t) => ({ value: t, label: t })) }, ] },
  sessions: { title: 'Sessions', rows: [
    { kind: 'group', label: 'Scope' }, { kind: 'choice', key: 'sessionScope', label: 'Show in', hint: 'All chats, or only the chats you pick below.', choices: [{ value: 'all', label: 'All chats' }, { value: 'picked', label: 'Picked chats' }] },
    { kind: 'group', label: 'Picked chats' }, { kind: 'sessions' }, ] },
  theater: { title: 'Theater', note: 'The player grows to almost fill this window, docked or detached, while an agent works, then returns to where it was.', rows: [
    { kind: 'group', label: 'Automation' }, { kind: 'switch', key: 'autoTheater', label: 'Auto-theater' },
    { kind: 'choice', key: 'theaterPersist', label: 'Stay open', choices: [{ value: 'agent', label: 'While agent works' }, { value: 'window', label: 'Until I turn it off' }] },
    { kind: 'choice', key: 'theaterScope', label: 'Trigger', hint: 'Which chat counts as busy.', choices: [{ value: 'focused', label: 'Focused chat' }, { value: 'any', label: 'Any chat' }] }, ] },
}
function SettingsFor({ page }) { const cfg = useValue(settings), P = SETTINGS_PAGES[page]
  return jsx(SettingsPage, { title: P.title, note: P.note, rows: P.rows, cfg }) }
function SettingsTheater() { const a = useValue(automation)
  return jsxs('div', { children: [jsx(SettingsFor, { page: 'theater' }),
    jsx('div', { style: { fontSize: 10, color: V.dim, marginTop: 12, lineHeight: 1.5 }, children: 'Theater: ' + a.mode + ' · trigger: ' + a.scope + ' · persist: ' + a.persist + ' · cover ' + (a.own ? (a.cover ? 'yes' : 'no') : 'n/a') + ' · viewport ' + (a.viewport ? a.viewport.width + '×' + a.viewport.height : 'window') }) ] })
}

function SettingsDiagnostics() {
  const d = useValue(diag), netState = useValue(net)
  const cfg = useValue(settings), size = useValue(cardSize), pk = useValue(picked), fs = useValue(focusedStored)
  const a = useValue(automation), c = useValue(completion)
  const pm = useValue(pageMedia)
  let themeName = ''
  try { themeName = (useTheme() || {}).themeName || '' } catch { /* older desktop */ }
  const rows = [['Now'], ['Transport', d.transport || 'none'], ['Source', d.source || 'none'], ['Last error', d.lastError ? errorCopy(d.lastError) : 'none'], ['Network', netState], ['Theme', themeName || 'app default'], ['Layout'],
    ['Restore', cfg.restoreMode], ['Focus', cfg.immersiveOnPlay ? 'on play' : 'manual'], ['Size', size.w + '×' + size.h], ['Theater', a.mode + ' · ' + a.scope], ['Persist', cfg.theaterPersist], ['Automation', a.supported ? 'ready' : 'needs newer Desktop'], ['Chats'],
    ['Completions', c.reason + ' · ' + c.mapped + ' mapped · last: ' + c.last], ['Sessions', cfg.sessionScope + ' · ' + pk.length + ' picked · ' + sessionDecision(cfg.sessionScope, fs, pk).reason], ['Page & storage'],
    ['Page guest', 'plugin-owned local session; sign-ins stay on this machine'], ['Resume', Object.keys(progress.get()).length + ' saved'], ['Page media', pm.has ? (pm.paused ? 'paused' : 'playing') + ' · ' + formatTime(pm.t) + ' / ' + formatTime(pm.d) : 'no element found'], ['Native player', 'our own element, not the guest'],
  ]
  return jsxs('div', { style: { maxWidth: 520 }, children: [ jsx('div', { style: { fontSize: 13, fontWeight: 600 }, children: 'Diagnostics' }),
    rows.map((row, i) => row.length === 1 ? jsx(Group, { key: 'g' + i, label: row[0] })
      : jsxs('div', { key: row[0], style: { display: 'flex', gap: 10, padding: '5px 0', borderBottom: i === rows.length - 1 ? 'none' : '1px solid ' + V.stroke, fontSize: 11 },
        children: [jsx('span', { style: { color: V.dim, width: 92, flex: '0 0 92px' }, children: row[0] }), jsx('span', { style: { color: V.text, wordBreak: 'break-word' }, children: String(row[1]) })] })),
  ] })
}
function StatusChip({ onOpen }) {
  const now = useValue(play), label = now.src ? (now.title || NAME) : NAME
  return jsx('button', { type: 'button', title: 'Open ' + NAME, 'aria-label': 'Open ' + NAME, onClick: onOpen, className: 'px-1.5 text-[0.6875rem]', style: { color: now.src ? V.accent : V.dim }, children: label })
}
function bindTheater(caps) {
  let autoPrev = null
  const autoTick = () => {
    const cfg = settings.get(), p = play.get()
    const viewport = caps.viewport ? host.state.viewport.get() : null
    const busy = caps.busy ? !!host.state.busy.get() : false
    const scope = cfg.theaterScope || SETTINGS_DEFAULTS.theaterScope
    let watched = busy
    if (scope === 'any' && caps.anyBusy) {
      const m = host.state.busyBySession.get()
      watched = !!(m && typeof m === 'object' && Object.keys(m).some((k) => !!k && m[k]))
    }
    // A manual exit lasts exactly one turn: once nothing is busy, hand control back to the
    // switch so the next turn can enter again.
    if (theaterManual.get() === false && !watched) theaterManual.set(null)
    const state = { supported: true, enabled: !!cfg.autoTheater, manual: theaterManual.get(), hasMedia: !!p.src, floating: !!p.floating, busy: watched, viewport, persist: cfg.theaterPersist || SETTINGS_DEFAULTS.theaterPersist }
    const plan = theaterPlan(autoPrev, state)
    const entering = plan.own && !(autoPrev && autoPrev.own) && theaterManual.get() == null && theaterSettle !== -1
    if (entering && !theaterSettle) theaterSettle = globalThis.setTimeout(() => { theaterSettle = -1; autoTick() }, THEATER_GATE.enter)
    if (!entering) { if (theaterSettle > 0) globalThis.clearTimeout(theaterSettle); theaterSettle = 0 }
    // The exit edge waits too, but only for the switch: a manual exit (Esc, Exit theater)
    // must be instant. `theaterExit === -1` means the gate already fired.
    const leaving = !plan.own && !!(autoPrev && autoPrev.own) && state.manual == null && theaterExit !== -1
    if (leaving && !theaterExit) theaterExit = globalThis.setTimeout(() => { theaterExit = -1; autoTick() }, THEATER_GATE.exit)
    if (!leaving) { if (theaterExit > 0) globalThis.clearTimeout(theaterExit); theaterExit = 0 }
    const holdOut = leaving && theaterExit !== -1
    const wait = entering && theaterSettle !== -1
    // Exit must target the surface theater actually borrowed, not whichever root is in
    // front: releasing the wrong element left the player pinned over the pane.
    const el = plan.own ? theaterHandle() : (theaterSaved && theaterSaved.el ? theaterSaved.el : (surfaceHandle() ? surfaceHandle().root : null))
    // An evicted surface proves nothing: leave the plan un-owned so the next tick retries.
    const painted = !wait && !holdOut && applyTheaterPlan(plan, el, null, theaterRect) && !(el && el.isConnected === false)
    if (!plan.changed || painted) autoPrev = plan
    // `cover` is the honest answer to "is it actually almost fullscreen": measured, not
    // assumed, because a transformed ancestor would contain the fixed overlay.
    const r = el && el.getBoundingClientRect ? el.getBoundingClientRect() : null, want = ((viewport ? viewport.width : globalThis.innerWidth) || 0) - 2 * THEATER_CFG.inset - 2
    automation.set({ ...state, mode: wait ? 'normal' : (plan.own || holdOut) ? 'theater' : 'normal', own: !wait && (plan.own || holdOut), scope, cover: !!(r && want > 0 && Math.round(r.width) >= want) })
  }
  const autoStops = [play.subscribe, settings.subscribe, theaterManual.subscribe]
    .map((sub) => (typeof sub === 'function' ? sub(autoTick) : null))
  if (caps.busy) autoStops.push(host.state.busy.subscribe(autoTick))
  if (caps.anyBusy) autoStops.push(host.state.busyBySession.subscribe(autoTick))
  if (caps.viewport) autoStops.push(host.state.viewport.subscribe(autoTick))
  autoTick()
  return () => { for (const off of autoStops) { if (typeof off === 'function') off() } }
}
function bindInput(ctx) {
  if (typeof ctx.addEventListener !== 'function' || typeof globalThis.addEventListener !== 'function') return
  ctx.addEventListener(globalThis, 'offline', () => net.set('offline'))
  ctx.addEventListener(globalThis, 'online', () => net.set('online'))
  ctx.addEventListener(globalThis, 'keydown', (ev) => { if (ev && ev.key === 'Escape') { immersive.set(false); fullscreenExit(globalThis.document); if (automation.get().own) theaterManual.set(false) } })
  ctx.addEventListener(globalThis, 'pointermove', onPointerMove)
  ctx.addEventListener(globalThis, 'pointerup', onPointerUp)
  ctx.addEventListener(globalThis, 'pointercancel', onPointerCancel)
}
function bindCompletions(ctx, caps, closePane, isRetired) {
  const completionStops = [], completionReady = caps.onEvent && caps.notify && caps.openSession && caps.focusedSession && caps.request
  let completionMap = {}, completionBusy = false, completionLast = ''
  // Theater covers the chat, so clicking the toast must shrink the player first. Outside
  // theater the dock collapses exactly as before: one gesture, no hidden second step.
  const snapToChat = (sid) => {
    const sp = snapPlan(automation.get().own)
    theaterManual.set(false)
    if (sp.collapse) closePane()
    try { host.openSession(sid, {}) } catch { /* older desktop */ }
  }
  const refreshCompletionMap = () => {
    if (!completionReady || completionBusy || isRetired()) return
    completionBusy = true
    Promise.resolve().then(() => host.request('session.active_list', {})).then((res) => {
      const next = {}, rows = (res && res.sessions) || []
      for (const r of rows) { const a = r && r.id, b = r && r.session_key; if (a && b) next[String(a)] = String(b) }
      completionMap = next; completion.set({ ...completion.get(), mapped: Object.keys(next).length, reason: 'ready' })
    }).catch(() => completion.set({ ...completion.get(), last: 'active_list unavailable', reason: 'unmapped' }))
      .then(() => { completionBusy = false })
  }
  const onTerminal = (ev) => {
    const on = !!settings.get().completionToasts
    const d = completionDecision(ev, { enabled: on, mapping: completionMap, focusedRuntime: caps.focusedRuntime ? host.state.focusedSessionId.get() : null,
      focusedStored: caps.focusedSession ? host.state.focusedStoredSessionId.get() : null })
    completion.set({ ...completion.get(), enabled: on, last: d.reason })
    if (!d.show) return
    const key = [ev.type, ev.session_id, ev.seq, ev.replayEpoch].join('|')
    if (key === completionLast) return
    completionLast = key
    try { host.notify({ kind: 'info', title: NAME, message: 'A chat finished', placement: 'bottom-right', action: { label: 'Open chat', onClick: () => snapToChat(d.storedId) } }) } catch { /* older desktop */ }
  }
  if (completionReady) {
    for (const t of TERMINAL_EVENTS) completionStops.push(ctx.onEvent(t, onTerminal))
    completionStops.push(ctx.onEvent('sessions.changed', refreshCompletionMap)); refreshCompletionMap()
  } else completion.set({ ...completion.get(), reason: 'needs newer Desktop' })
  return () => { for (const off of completionStops) { if (typeof off === 'function') off() } }
}
function bindSessions(caps) {
  const sessionStops = []
  if (caps.focusedSession) {
    sessionStops.push(host.state.focusedStoredSessionId.subscribe(() => focusedStored.set(host.state.focusedStoredSessionId.get())))
    focusedStored.set(host.state.focusedStoredSessionId.get())
  }
  return () => { for (const off of sessionStops) { if (typeof off === 'function') off() } }
}
// ----------------------------------------------------------------- registration
export default {
  id: ID, name: NAME, description: 'Paste any http(s) URL. Direct media files play with real controls; other pages load as a top-level guest.',
  defaultEnabled: false, register(ctx) {
    let retired = false
    settingsStore = ctx.storage
    osDoor = ctx.os || null
    settings.set(readSettings(ctx))
    cardSize.set(readSize(ctx.storage)); theaterRect = readTheaterSize(ctx.storage)
    progress.set(readProgress(ctx.storage))
    writeSize(ctx.storage, cardSize.get())
    const cfg = settings.get()
    const saved = readSession(ctx)
    if (cfg.restoreMode !== 'blank' && saved && typeof saved.raw === 'string' && saved.raw) {
      const parsed = parseMediaUrl(saved.raw)
      if (parsed.ok) applyParsed(parsed, saved.raw, false, cfg.restoreMode === 'playing')
    }
    pins.set(readPins(ctx))
    shelf.set(readPins(ctx, 'shelf', SHELF_MAX))
    visits.set(readVisits(ctx))
    picked.set(readPicked(ctx))
    // Only the address is restored. Placement is not: Close always reopens docked, and a
    // stored `floating` flag that nothing read was a claim the code did not keep.
    const persist = () => { writeSession(ctx, { raw: play.get().raw }) }
    const stopPersist = play.subscribe ? play.subscribe(() => persist()) : null
    const stopPins = pins.subscribe ? pins.subscribe((list) => writeList(ctx, 'pins', list, PIN_MAX)) : null
    const stopShelf = shelf.subscribe ? shelf.subscribe((list) => writeList(ctx, 'shelf', list, SHELF_MAX)) : null
    const stopVisits = visits.subscribe ? visits.subscribe((list) => writeList(ctx, 'visits', list, VISIT_MAX)) : null
    const stopPicked = picked.subscribe ? picked.subscribe((list) => writeList(ctx, 'pickedSessions', list, PICK_MAX)) : null
    const stopSettings = settings.subscribe ? settings.subscribe(() => writeSettings()) : null
    const caps = automationCaps(host, ctx)
    const stopTheater = bindTheater(caps)
    bindInput(ctx)
    const paneOp = (name, id) => {
      const fn = host && host[name]
      if (typeof fn !== 'function') return
      try { fn.call(host, id) } catch { /* older desktop */ }
    }
    const PANE_RENDER = () => {
      const render = () => jsx(MediaDock, { toggleFloat: () => toggleFloat(), onClose: () => closePane() })
      return render }
    const registerPane = ({ floating = false, open = true, reveal = false } = {}) => {
      if (retired) return
      play.set({ ...play.get(), floating })
      persist()
      const sz = cardSize.get(), RENDER = PANE_RENDER()
      const dataOf = (fl) => fl
        ? { placement: 'floating', anchor: 'top-right', lifecycleKeepAlive: true, uncloseable: true, width: sz.w + 'px', height: sz.h + 'px' }
        : { placement: 'right', dock: { pane: 'workspace', pos: 'right', enforce: true }, lifecycleKeepAlive: true, uncloseable: true, width: '480px' }
      // BOTH surfaces stay registered, exactly ONE enabled: flipping `placement` on a single id
      // could not evict what it left (old docked pane under new chrome), and `enabled: false`
      // drops a contribution from `registry.getArea`, so never adopted as a track, never floated.
      ctx.register({ id: 'card', area: PANES_AREA, title: NAME, enabled: open && !floating, data: dataOf(false), render: RENDER })
      ctx.register({ id: 'float', area: PANES_AREA, title: NAME, enabled: open && floating, data: dataOf(true), render: RENDER })
      const live = floating ? FLOAT_ID : PANE_ID
      // Evict the surface we are not on; Close evicts both: a disable-only close left the node
      // in the tree and the chip re-adopted it as a chrome-high strip with no address bar.
      if (!open) { paneOp('removePane', PANE_ID); paneOp('removePane', FLOAT_ID); return }
      paneOp('removePane', floating ? PANE_ID : FLOAT_ID)
      // undismissPane only forgets a persisted Close; a closed pane's zone stays collapsed.
      paneOp('undismissPane', live)
      if (reveal) paneOp('revealPane', live)
    }
    const closePane = () => { if (!retired) registerPane({ floating: play.get().floating, open: false }) }
    const toggleFloat = () => { if (!retired) registerPane({ floating: !play.get().floating, open: true, reveal: true }) }
    const openPane = () => { if (retired) return; registerPane({ floating: false, open: true, reveal: true }) }
    const stopCompletions = bindCompletions(ctx, caps, closePane, () => retired)
    const stopSessions = bindSessions(caps)
    ctx.registerSettingsPage({
      id: ID, title: NAME, icon: 'play', order: 55, render: () => jsx(SettingsFor, { page: 'overview' }),
      children: [ { id: 'playback', title: 'Playback', render: () => jsx(SettingsFor, { page: 'playback' }) }, { id: 'theater', title: 'Theater', render: () => jsx(SettingsTheater, {}) },
        { id: 'sessions', title: 'Sessions', render: () => jsx(SettingsFor, { page: 'sessions' }) }, { id: 'diagnostics', title: 'Diagnostics', render: () => jsx(SettingsDiagnostics, {}) }, ],
    })
    registerPane({ floating: false, open: false })
    const CONTRIBS = [ { id: 'chip', area: STATUS_RIGHT, order: 125, render: () => jsx(StatusChip, { onOpen: openPane }) },
      { id: 'open', area: PALETTE_AREA, data: { id: 'open', label: NAME, description: 'Open ' + NAME + '.', run: openPane } },
      { id: 'close', area: PALETTE_AREA, data: { id: 'close', label: 'Close ' + NAME, description: 'Hide ' + NAME + '. The plugin stays enabled.', run: () => { if (!retired) closePane() } } },
      ...COMMANDS.map((c) => ({ id: 'key-' + c.id, area: KEYBINDS_AREA, data: { id: 'media-dock.' + c.id, label: NAME + ': ' + c.label, category: NAME, defaults: c.keys, run: c.run } })),
      { id: 'key-pin', area: KEYBINDS_AREA, data: { id: 'media-dock.pin', label: NAME + ': Pin/Unpin this chat', category: NAME, defaults: [], run: () => pickSession(focusedStored.get()) } }, ]; for (const c of CONTRIBS) ctx.register(c)
    ctx.onDispose(() => {
      retired = true
      persist()
      for (const off of [stopPersist, stopPins, stopShelf, stopVisits, stopPicked, stopSettings]) { if (typeof off === 'function') off() }
      stopTheater()
      stopCompletions()
      stopSessions()
      settingsStore = null
      osDoor = null
      surfaces.clear()
      frontRoot = null
      dragState = null
    })
  }, }
