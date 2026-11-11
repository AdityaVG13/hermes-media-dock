# Changelog

## 0.1.0 — first public release

One pane beside the chat (or the same pane as a floating card) that holds whatever you are watching
or listening to. A standalone Hermes desktop plugin: `plugin.yaml` + `desktop/plugin.js`, no build
step, no Python, no server.

- **Any http(s) URL, one path.** A direct media file plays in the dock's own `<video>`/`<audio>`;
  every other URL loads as-is in one top-level `<webview>` on a plugin-owned local session
  (`persist:media-dock`). No per-site rules, no hostname branches, no embed catalog.
- **One transport rail for both sources.** Play/pause, queue previous/next, seek, `t / d`,
  0–200 % level through a real gain stage, mute, captions from the page's own tracks, translation
  of those cues, 0.5×–2× speed, fullscreen. A live element (`duration === Infinity`) shows `LIVE`
  and elapsed time instead of a seek bar.
- **Queue.** Add current, open a row, reorder, remove, shuffle, clear; a file that ends plays the
  next; capped at 12 rows, deduped by URL.
- **Two placements.** Detach floats a card with four size steps, drag and edge grips; Dock returns
  it to the rail; Theater pins the player over the window and restores it, including a dragged
  theater size that persists.
- **It remembers.** Last link, playback position per URL (60 entries), queue and page sign-ins
  survive closing the pane and restarting the app. All local; nothing is uploaded.
- **Named refusals.** HLS/DASH manifests, non-http(s) schemes, a guest that will not load and media
  errors each name the real cause and offer one way out.
- **Opt-in extras.** Focus mode, auto-theater while an agent works, other-chat completion toasts,
  picked-chats visibility — all off by default.
- **Proof, not adjectives.** `tests/render_gate.py`: 26 registrations, 63 handlers clicked,
  119 mutants, 0 survivors. Live checks: `tests/live.py`. Measurement: `tests/perf_probe.py`.

Not supported, and said so in the UI: DRM playback, HLS/DASH, downloads, and boosting a source that
sends no CORS header.

