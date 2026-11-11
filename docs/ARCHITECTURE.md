# Media Dock: architecture

A standalone Hermes Desktop plugin. One renderer module, no agent tools, no HTTP
backend. The module is loaded from disk as ESM: a single `desktop/plugin.js` with three
import specifiers (`@hermes/plugin-sdk`, `react`, `react/jsx-runtime`), no build step,
evaluated uncompiled. It calls `jsx()`/`jsxs()` from `react/jsx-runtime`; JSX syntax
would not parse.

## One file, held by subtraction

The Desktop Plugin SDK evaluates a disk plugin from a blob URL and rewrites only those
three specifiers. A relative import cannot resolve against a blob base, so a sibling
file fails the load (confirmed in `contrib/runtime-loader.ts:339`).

The line cap is a self-imposed readability budget, not a platform limit. It has moved
1500 -> 1700 -> 1800 -> 1850, each time with the reason recorded in
`tests/render_gate.py`. The gate enforces 1850. The current file is 1,823 lines.
When it reaches the cap, subtract or compact before adding. Do not split it.

### Layout posture (locked)

The page guest sits in normal flow inside the stage. The stage carries `minHeight: 0`
and `overflow: hidden`, and the `.media-dock` root carries `overflow: hidden; minHeight: 0`.
Do not return the guest to `position: absolute; inset: 0` and do not restore a 220 px
stage floor. Those two let the page paint over the address bar and the footer. The gate
pins both with mutants ("guest back to absolute inset", "stage floor restored").

## Layers

| Layer | Owns | Code |
|---|---|---|
| Pure decisions | URL validation, media classification, geometry, density, chrome flags, theater plan and caps, queue/pin/visit math, autoplay and size stepping, error copy | exported functions in `desktop/plugin.js` |
| State | atoms: `play`, `pins`, `shelf`, `listMode`, `visits`, `settings`, `diag`, `net`, `immersive`, `cardSize`, `automation`, `completion`, `picked`, `focusedStored`, `captions`, `pageMedia`, `navState`, `navOffer`, `pageFault`, `theaterManual`, `progress` | module scope |
| Persistence | `ctx.storage` keys: `session`, `pins`, `shelf`, `visits`, `pickedSessions`, `settings`, `size`, `theaterSize`, `progress` | `read*` helpers, `writeList`, `writeSettings` |
| Playback surface | our own `<video>`/`<audio>`, one isolated top-level `<webview>` guest per page URL, named refusal wells | `NativePlayer`, `PageFrame`, `frameHint`, `Stage`, `Well` |
| Chrome | address bar, suggestions, queue and saved panel, footer, focus overlay, resize grips | `MediaDock`, `Queue`, `Suggestions`, `SizeReadout`, `EdgeGrips` |
| Contribution | two pane surfaces (docked and floating), status chip, palette (Open and Close only), keybinds, settings pages | `register(ctx)` |
| Automation | reactive theater controller: capability detection, atom subscriptions, change-driven plan, disposal | `bindTheater`, `automationCaps` |
| Completion toasts | event-driven other-chat turn detection, runtime-to-stored mapping, in-app toast, collapse and snap | `bindCompletions`, `completionDecision`, `TERMINAL_EVENTS` |
| Picked chats | durable-id allowlist, reactive gate over the still-mounted stage | `bindSessions`, `sessionDecision`, `PickedWell` |
| Verification | behavior and mutation battery, static contract, live driver | `tests/jscheck.py`, `tests/render_gate.py`, `tests/live.py` |

Two placements, one renderer. Docked-right and the floating card are separate
contribution ids (`media-dock:card`, `media-dock:float`) registered together with
exactly one enabled. See Dock and detach.

`surfaces` is a `Map` keyed by the root node each `MediaDock` publishes through its ref,
and `frontRoot` records the last root the user touched. Global commands (play/pause,
fullscreen, cycle size) resolve through `surfaceHandle()`. Each root owns its measured
width and its `ResizeObserver`, disconnected on unmount. `dragState` is the only
genuinely global handle: one pointer means one drag in flight.

## URL contract

```
parseMediaUrl(raw)
  -> validate http(s) only (coerce bare host text; punycode via new URL)
  -> classify by PATH extension (never hostname)
       media extension -> kind: 'native', media: 'video' | 'audio'
       .m3u8 / .mpd    -> { ok: false, error: 'manifest' }
       otherwise       -> kind: 'page'
  -> { ok: true, src, pageUrl, raw, title, hostname, kind, media, ext, error: null }
```

Zero host branches. No provider, id, or start extraction. Non-Latin domains work. A bare
11-character token is not assumed to be a video id; it is refused as `not-a-url`. A
colon followed by digits is treated as a port, so `localhost:3000` and
`example.com:8080/a.mp4` parse as hosts, not schemes.

## Transports

**native.** We own the DOM node, so every control is real. `onPlay` enters focus mode
when `immersiveOnPlay` is on. `onEnded` exits focus and, if Auto-advance is on and this
URL is in the queue, plays the next item. `applyNativeLevel` maps 0-100 to element
volume and 101-200 to a gain stage on the same element. A cross-origin source is
classified before any audio graph exists, because routing it through Web Audio silences
it permanently; boost is then a named refusal. Settings volume and speed are applied to
the open element, not only on the next load.

**page.** One generic top-level `<webview>` per pasted URL. `src` is the URL as-is,
`partition` is `persist:media-dock` (plugin-owned, written to this machine's
`Partitions/media-dock`, so sign-ins survive a restart and stay local). A webview is a
separate WebContents with a top-level document, not an iframe, so `X-Frame-Options` and
`frame-ancestors` do not apply. That is why no per-site rules are needed. The host's
`will-attach-webview` guard applies its preload and throttle only to
`persist:hermes-preview`; this partition is left alone.

No `allowpopups`, `nodeintegration`, or `webpreferences`, and no `preload`: the host
evaluates this module from a blob URL, so a relative preload path cannot resolve and the
attribute is silently dropped. The page agent (`AGENT_SRC`) is injected with
`executeJavaScript` on `dom-ready`. It exposes `window.__mdAgent.state()`, `.tracks()`,
and `.cmd(op, v)`. The host reads it on one 500 ms interval, cleared on detach, and sends
play, pause, toggle, seek, level, mute, rate, and track commands. The agent picks the
page's `<video>`/`<audio>` element by playing state, then by area. No selector and no
hostname.

A failed navigation still fires `did-finish-load` with Chromium's error document, so the
fault belongs to the failure event. `frameHint` appears only after a real load failure
(`errorCode` -3 is an aborted navigation and is ignored) and names the cause with a
Browser button. A working page has no overlay.

`GUEST_UA` is a desktop Chromium user-agent string. Electron's default token reads as an
unknown browser and live-streaming sites answered with their mobile pages. The value is
a compatibility literal; nothing branches on it, and `navigator.userAgent` is not read.

## Queue and saved shelf

One panel, two labeled views. `Queue` is a play order; `Saved` is a browse list. The
header line holds the view switch, the save action, the count, and the bulk actions.
Rows scroll under it, so the actions never scroll away.

| Action | Queue | Saved |
|---|---|---|
| Save | `Add current`, dedupe by URL, cap 12, no-op while the URL is already queued | `Save current`, dedupe by URL, cap 40, same no-op |
| Open | Click a row | Click a row |
| Remove | `x`, does not open the row | `x`, does not open the row |
| Reorder | Up and down arrows, persisted, ends are no-ops | Not offered: a shelf has no play order |
| Bulk | `Shuffle` (a permutation that always changes the order) and `Clear` | `Clear` |

Both lists use the same row shape and the same `readPins(ctx, key, max)` reader.
`nextInQueue`, `prevInQueue`, `movePin`, `upsertPin`, `removePin`, and `bumpVisit` are
pure; `clearPins`, `clearShelf`, and `shufflePins` are one-shot writers.

Next and Previous ignore Auto-advance. If the current URL is not in the queue, Next
starts at the first item and Previous at the last. Auto-advance fires only when a file we
own ends and only if that URL is in the queue. A page has no end event, so it never
auto-advances. Loop wraps both directions.

## Resume points

Storage key `progress`, shape `{ "<url>": <whole seconds> }`, capped at
`PROGRESS_MAX = 60` entries (oldest keys fall off). Written by `remember(url, t, d)`:
never under 3 s, and an entry inside the last 5 s is deleted so a finished item starts
over. Read by `resumeAt(node, url, d)`, which seeks only when the stored point is past
3 s, before `d - 5`, and the node has not already started.

Sources: native `onPause`, native `onTimeUpdate` roughly every 5 s, and the page poll
while the guest element is paused. Restore happens once per document through the
`guestResumed` latch, reset on `did-start-loading` and `did-navigate`. Purely local.

## Card geometry (source-verified)

No host API resizes a pane. The floating card is the host's `[data-floating-pane]`
element with inline width and height from registration data. React rewrites only changed
style props, so a direct DOM write survives re-renders while chrome size is unchanged.
Re-registering remounts, drops pointer capture, and restarts the media element.

```
startResize(axis, ev, root, theater) -> refuse unless the target is the floating frame
                                        (or the root itself while theater is active)
onPointerMove(ev)    -> sizeAt(from, dx, dy, vpW, vpH, edges) -> paintSize(target)
onPointerUp/cancel   -> commitSize (clamped), paint or unpaint, clear dragState; no register()
cycleSize(root)      -> nextLadder -> commitSize
                        floating: paint the frame, width and height only
                        docked:   change the label only, never paint the pane
registerPane()       -> reads cardSize into data.width/height on every mount
```

`CARD_ANCHOR = 'top-right'`, so the free corner is bottom-left. Dragging it grows width
as `w0 - dx` and height as `h0 + dy`, and rewrites `left` to keep the right edge fixed.
`clampSize` enforces `CARD_MIN` and `viewport - 24`. Theater pins left and top, so its
free corner is bottom-right and its edges are the opposite.

Grips carry `data-floating-no-drag="true"` so the host pane drag does not eat the
pointer, and sit at `zIndex: 9` above the `6` chrome bands; at 5 the transparent footer
ate the corner pointerdown. All pointer listeners go through `ctx.addEventListener`.

The size ladder is `480x460`, `640x520`, `820x620`, `1024x720`. `nextLadder` steps
forward from an off-ladder size (a drag or a clamp) instead of sticking on the first
preset. The readout is labeled `Card <w>x<h>` and appears only on the floating card.
Docked, a click on it only steps the label: it is a saved preset, not a pane resize, and
painting the dock there was the one-shot repair that made later clicks look dead.

`layoutFor(paneW, override)` returns `{ tier, rail, wrap, roomy, captions, tags, detail }`
from a positive `ROOMY` set. Geometry (`rail`, `wrap`) is never overridable. Width buys
detail, never controls. `chromeFor(immersive, layout, kind)` decides which chrome
survives; a page keeps its address bar even in focus mode.

## Dock and detach

Two registered surfaces, one live at a time:

```
card   area=PANES_AREA  data.placement='right'     width 480px  enabled = open && !floating
float  area=PANES_AREA  data.placement='floating'  width  sz.w    enabled = open && floating
```

`registerPane({ floating, open, reveal })` registers both on every call and enables
exactly one. `enabled: false` drops a contribution out of `registry.getArea`, so the dead
surface is neither adopted as a docked track nor listed as a floating card.

- `Detach` / `Dock` is `toggleFloat`: flip the flag, remove the idle id, undismiss the
  live id, reveal it.
- `Close` is the same call with `open: false`: both disabled, both ids removed. The
  status chip `Open Media Dock` re-registers the docked pane and reveals it. Close does
  not remember a floating placement; reopening is always docked.
- `paneOp` swallows a missing host method rather than throwing, so an older desktop loses
  the reveal, not the pane.
- The docked hint carries `enforce: true` (`workspace`/`right`): adoption runs once per
  pane lifetime and the committed tree wins afterwards.
- `play.floating` names which surface is live. The chrome reads that atom only, so the
  label and the surface showing it cannot disagree.

## Focus and fullscreen

Focus hides the address bar, suggestions, queue, and footer; `transport` always
survives. A page keeps its address bar. `fullscreenRequest(el)` calls
`el.requestFullscreen()` on our own root, a user-gesture door with no core patching.
`fullscreenToggle(el)` exits when `document.fullscreenElement` is set, otherwise
requests, so the same control leaves. Esc and exit focus also call `fullscreenExit`.
Auto-fullscreen on `onPlay` is not attempted: the browser refuses fullscreen without a
gesture, so `onPlay` enters focus mode instead.

A webview owns its keyboard. The page agent reports `__md:tab-out`, `__md:tab-back`, and
`__md:escape` on console, the one channel a webview exposes without a preload. An
unconsumed Escape hands focus back to the address bar.

## Theater (opt-in, OS-agnostic)

Theater is an overlay of the player, not a resized dock. The host exposes only
`revealPane`, `removePane`, `undismissPane`, and `paneVisibility`, so a docked rail
cannot be grown. The plugin pins the pane's own root to the window instead, which works
from either placement and leaves the layout tree untouched. No native fullscreen (macOS
opens a new Space) and no second window.

```
THEATER_CFG = { inset: 24, z: 2147482000 }
applyTheaterPlan(plan, el, cfg, rect)
  own:   save the inline style it borrows, position fixed, inset 24 (or the dragged rect),
         z, radius, border, background
  !own:  restore every saved inline property verbatim (CSS names translated first)
```

`theaterSaved` holds the borrowed inline style and the element it belongs to.
`theaterRect` holds a dragged box and is persisted as `theaterSize`, clamped to the
window. `THEATER_KEYS` is the exact property list restored on exit.

```
automationCaps(host, ctx) -> trust only real atoms and functions; older Desktop gets a named refusal
theaterDecision(s)        -> off | normal | theater
theaterPlan(prev, s)      -> { own, changed, mode }  // unchanged tick means zero DOM work
autoTick()                -> subscribed to busy, viewport, busyBySession, play, settings, theaterManual
```

`autoTheater` defaults false. `theaterScope` is `focused` (`host.state.busy`) or `any`
(`host.state.busyBySession`). `theaterPersist` is `agent` (shrink when idle) or `window`
(latch across chat switches; named in `THEATER_PERSIST`). The latch requires `prev.own`
and cannot open from cold idle. A manual exit (`theaterManual === false`) lasts one turn,
then hands control back to the switch.

A docked shell clips the pinned surface, so entering theater from dock re-registers the
player as the floating surface (`theaterPlace`); exiting re-docks it. Theater state is
mirrored in the `automation` atom, including a measured `cover` flag, because a
transformed ancestor would contain a fixed overlay and the honest answer is measured,
not assumed.

## Completion toasts (opt-in, event-driven)

The terminal pair is source-verified, not guessed: `TERMINAL_EVENTS` is the frozen
`['message.complete', 'error']` used by the shipped group-turn tracking. `GatewayEvent`
carries `session_id` (runtime id), `type`, `seq`, `replay_epoch`, and `replayed`.
`session.active_list` returns rows with `id` (runtime) and `session_key` (stored id);
that is the mapping.

```
completionDecision(ev, s) -> { show, reason, storedId? }
                             reasons: disabled | replayed | not-terminal | no-session |
                                      focused | unmapped | other-chat
refreshCompletionMap()    -> host.request('session.active_list', {}), one in-flight guard
onTerminal(ev)            -> decision; dedup on type|session_id|seq|replayEpoch;
                             host.notify({ title, message, placement, action })
snapToChat(storedId)      -> close the pane, then host.openSession(storedId, {})
```

Invariants: an unmapped event is a named refusal, never a toast with a dead action. The
focused chat never toasts, checked by both runtime and stored id. Replayed frames are
ignored. Reactive only, with no timers: `ctx.onEvent` for both terminal types plus
`sessions.changed`. All disposers retire in `ctx.onDispose`. One in-flight refresh, one
dedup key, one toast per event. `completionToasts` defaults false and is validated by
`settingsWithDefaults`.

`host.notify` is in-app on purpose. `ctx.os.notify` fires only while Hermes is
backgrounded, so it would be suppressed while the user is watching media.
`host.openSession` wants a stored id; passing the runtime id is a defect the gate pins.

## Picked chats (opt-in)

The pane is global, one registration per window, so there is no host door for "show only
in these sessions". Driving the host layout tree on every chat switch would fight the
persisted layout. The plugin therefore gates its own rendered content.

```
sessionDecision(scope, focusedStored, picked) -> { show, reason, storedId? }
                                                 all | picked | no-focused | not-picked
host.state.focusedStoredSessionId -> focusedStored atom (durable id)
ctx.storage['pickedSessions']     -> picked atom (bounded PICK_MAX = 32, strings)
pickSession(sid)                  -> toggle, persisted by picked.subscribe
Show here / Show everywhere       -> pin the chat / reset the scope to all
```

`sessionScope` (`all` by default, or `picked`) is validated; `SESSION_SCOPES` is frozen.
The Sessions page holds the Show in choice and the picked-id list. A diagnostics row
shows scope, picked count, and the live decision reason.

Invariants: durable stored ids only, because runtime ids rotate on compression. A
missing focused id fails open with a named reason, never a blank pane. The gate is an
overlay, so the video, audio, or webview element stays mounted: no remount, no playback
restart. One atom subscription, retired on dispose; zero timers. Fully opt-in, so the
default changes nothing for existing users.

## Error model

Every refusal is `{ ok: false, error: <named> }` or a `play.error` string, rendered by
`errorCopy` or `mediaErrorCopy` with the real cause and a Browser button where one would
help. No silent empty payload, no generic "loading", no fabricated frames or
capabilities. A guest load failure, a media element error, a dead translation endpoint,
and a source that cannot be boosted each have a named message.

Caption translation sends one cue at a time to a public, keyless endpoint, falls back to
a second endpoint, caches per `lang|target|text`, and aborts a request after 15 s so the
in-flight latch is released. Cue text leaves the machine; nothing is stored.

## Ownership and ordering

- There is no backend. The renderer is the truthful surface; a Python router is not
  mounted.
- `register()` reads persisted state before the first `registerPane`, so restore mode is
  honored at cold start. `ctx.onDispose` retires every subscription and clears the
  module-scope doors.
- `scripts/deploy.py` keeps three views in sync by sha256: source, installed junction,
  and published renderer copy. It does not enable the plugin or reload the running
  module.

## Repository layout

`desktop/plugin.js` is the entire renderer. `plugin.yaml` sits next to it because the
Plugins page joins a package by folder name. `scripts/deploy.py` is the only publish
path. `docs/` is public. `internal/` (`HANDOFF.md`, `PLAN.md`, `DEMO.md`,
`DEVELOPING.md`) and agent scaffolding are local-only and gitignored. No build step, no
generated source, no per-site embed catalog.

## Verification

```
python tests/jscheck.py desktop/plugin.js        # ESM parse
python tests/render_gate.py                      # behavior, static contract, mutants
python tests/perf_probe.py --runs 25 --iter 3000 # p50/p95/p99/max, heap, CPU profile, golden
python tests/live.py queue|rails|autoadvance     # live, self-asserting
```

`render_gate.py` loads the real module against a stateful stub SDK, drives `register()`,
renders every contribution, clicks every handler, and runs the mutant battery. Every
mutant must fail the gate; a skipped anchor also fails. The static contract forbids
OS-specific probes, hardcoded colors, per-site literals, a preload, a second interval,
and a file over 1850 lines. Current: exit 0, 26 registrations, 67 handlers, 122 mutants, 0 survivors, 0 skipped anchors.

`perf_probe.py` measures plugin-side CPU only. Host-side React reconciliation is out of
scope. Live smoothness is not proven by this probe.

## Debugging entry point

`Settings -> Plugins -> Media Dock -> Diagnostics` reads the live atoms, including the
theater, automation, completion, and session rows. Then run `jscheck`, `render_gate`,
and, for a hot-path claim, `perf_probe`. A green harness is not live playback evidence.

## No-claim boundaries

- No per-site embed catalog, no loopback wrapper, no hostname-based rewriter.
- No HLS or DASH playback: Chromium has no decoder and no shippable hls.js.
- No DRM playback: stock Electron ships no Widevine CDM.
- The guest session is local and persistent; nothing is synced or uploaded.
- A site that requires sign-in, refuses embedding, or only works in its own app may
  still fail. The dock names the failure instead of showing a blank frame.
- Generic guest playback was exercised live against well-known sites; it is not proven
  for every pasted URL.
- Auto-fullscreen without a gesture is not attempted.
- Theater grow and shrink were watched live (2026-11-10), including size and position
  restoration. The persistence latch across a chat switch is harness-proven only.
- Completion toasts and picked chats are harness-proven, not live-proven.
- The saved shelf is gate-proven, not yet live-checked.
- `ubs` exits 2 on this Windows host with a temp-path failure. That is a tooling failure,
  not a scanner pass.
