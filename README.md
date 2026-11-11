# Media Dock

A pane in Hermes Desktop for whatever you're watching while you work. Paste a link, keep a few pages open, and queue up the files that should play next.

Recent addresses are remembered and offered as you type. The queue holds up to 12 links to play in order, and Saved keeps up to 40 links to browse.

## Install

Needs Hermes Desktop 0.22.2 or newer.

```bash
hermes plugins install AdityaVG13/hermes-media-dock
hermes plugins enable media-dock
```

Then open it with Ctrl+K (Cmd+K on macOS), the sidebar row, or the status chip. The same switch lives in Settings, Capabilities, Plugins. A fresh install arrives disabled.

## How it works

Paste any http(s) address into the bar at the top and press Enter.

If the address is a media file (.mp4, .webm, .mp3, .flac, .ogg), it plays in the dock's own player.

If the address is a page, the page loads in the pane and keeps its own local session. Sign in once and it stays signed in. When that page has a plain `<video>` or `<audio>` element, the dock's transport bar drives it, so YouTube, Twitch, podcasts and radio get the same seek, volume, speed and captions as a local file.

The last address, the playback position, the open pages, the queue and Saved links are saved. Closing the pane or restarting the app picks up where you left off.

## Controls

| Control | What it does |
|---|---|
| Address bar | Paste a link, then Enter or Go. It stays visible while a page is showing, and offers your recent addresses as you type (can be turned off in Settings). |
| Transport | Play, previous, next, seek, mute, speed, captions, fullscreen. |
| Level | The speaker button opens a 0 to 200% slider. Above 100% a gain node boosts the signal. A cross origin source without CORS stays at 100% and says why. |
| CC | Off, plus one chip per caption track the page provides. Translate captions to another language is optional and goes through a public endpoint. |
| Focus mode | Hides the chrome while a file plays. Escape, Exit focus or mod+alt+f brings it back. A page keeps its address bar. |
| Fullscreen | Real fullscreen for the dock, so the app rail goes away. Needs one click. |
| Queue | Up to 12 addresses. Add current pins the address bar. Click a row to load it, the arrows reorder, x removes, Shuffle and Clear do what they say. |
| Saved | Up to 40 links to browse rather than play in order. Switch the list to Saved, then Save current. Click a row to open it, x removes it. |
| Detach | Moves the pane into a floating card at its saved size. Dock puts it back on the right rail. Same page, same timestamp. |
| Card size | Floating card only. Click to step through the saved sizes and the frame resizes. |
| Drag to resize | Floating card only. Drag the bottom left grip, or the left and bottom edges. |

## Keybinds

| Keys | Action |
|---|---|
| mod+alt+p | Play or pause |
| mod+alt+shift+n | Previous |
| mod+alt+n | Next |
| mod+alt+f | Focus mode |
| mod+alt+Enter | Fullscreen |

## Settings

The plugin has its own settings page under Settings, Plugins, Media Dock, with five sections.

- Overview: what happens on reopen (last address, resume playing, start blank), autoplay, focus on play, queue visibility, other chat notifications.
- Playback: dock volume from 0 to 200%, saved per app, mute the dock, default speed, auto advance, loop queue, layout density.
- Theater: grows the floating card while an agent is working, then restores your saved size. Off by default.
- Sessions: show the dock in every chat, or only in the chats you pin.
- Diagnostics: live state for transport, source, errors, size, theater, sessions and the page guest.

## Privacy

The embedded page keeps its session in local app data on this machine. There is no server and nothing is uploaded. The one exception is caption translation: when you turn it on, each cue goes to a public translation endpoint and nothing is stored.

## What will not play

| You paste | What happens |
|---|---|
| A site that uses DRM, such as Netflix, Disney+, Prime Video, Max, Spotify Web, Apple Music, Tidal or Audible | The page opens and its player reports a protected content error. Electron ships no DRM module, so there is nothing for the dock to drive. Use a browser. |
| An HLS or DASH manifest (.m3u8, .mpd) | Refused by name, because Chromium has no native decoder for it. Paste the page that hosts the stream instead. |
| `file:`, `javascript:` or `data:` addresses | Refused. Only http(s) loads here. |
| A site that only works in its own app, or needs an extension | The page may load, but its player will not start. |
| An address that never answers | Named failure, with a Browser button. |

Pages that use a plain HTML5 player work: YouTube, Twitch, most news, music and talk video, podcasts and radio. PDFs and images render as documents and pictures.

Live streams show LIVE and elapsed time where a normal file shows a seek bar, because a seek bar over something that cannot seek is a dead control.

## Known limits

- No DRM playback.
- No HLS or DASH manifests, no per site embed rules, no cloud sync.
- Chromium will not start an unmuted player without a click. After loading a queue row you may have to press Play once, after which queue rows play on their own.
- A site can refuse to run inside an embedded pane. Those pages get a named message and a Browser button, not a blank frame.

## License

MIT. See LICENSE.
