# D.I.M — Dawless Is More

> *A non-linear performance sequencer for human musicians.*
> The machine guides. The musician plays.

**D.I.M sequences the human, not the machine.**

It is not a DAW. It is not a MIDI sequencer. It does not control any instrument or plugin.
It guides the performer — what to play, when, what comes next, with conditional variations —
like a rally road book, but for a live music set.

---

## The Concept

Traditional setlists are linear. Live music is not.

D.I.M organizes a performance as **lanes** (instruments / performers),
**sections** (song parts: intro, verse, chorus, fill…) and **cues** (atomic actions).
Each cue carries an **instruction** — not just "play this", but also:

- `LOOP 4` — repeat 4 times then advance
- `JUMP chorus IF 1:2` — jump to the chorus every other pass
- `GOSUB fill-8bars` — play a fill section and come back
- `SKIP UNTIL 3:4` — skip this cue for the first 3 passes out of 4
- `REVERSE` — play the section's cues in reverse order
- `IF 50% THEN LOOP ELSE JUMP` — coin flip at the downbeat

**Tempo is king.** Everything is measured in bars and beats, not seconds.
D.I.M syncs with your setup via **Ableton Link**, **MIDI Clock**, or OSC.

---

## Features

### Core
- Non-linear performance sequencer — BASIC-inspired instruction set
- **Variable number of lanes: 1 to X** — one lane per instrument or performer, no upper limit
- Sections and cues with full control flow: `LOOP` `JUMP` `GOSUB` `IF` `SKIP` `REVERSE`
- Cross-lane jumps via a dedicated Conductor Lane
- Conditional logic: nth-pass, ratios, probability, manual trigger
- Playlist modes per section: all / nth / ratio / custom order

### Sync
- **Ableton Link** — peer-to-peer beat sync, auto-discovery on LAN (highest priority)
- **MIDI Clock** — receive or send (24 PPQN), DIN + USB
- **OSC** — native D.I.M protocol for multi-instance orchestration

### Interfaces
- **Web** — responsive, touch-optimized, no-brainer performance UI
- **TUI** — Textual terminal interface, works over SSH
- **ESP32 client** — lightweight display (TFT 320×240 or OLED 128×64), WiFi-connected

### Multi-instance Orchestration
- Multiple D.I.M instances on stage, one master coordinates all
- Auto-discovery via mDNS — zero config, plug in and it appears
- OSC broadcast for transport and sync
- WebSocket for real-time state reporting
- Compatible with TouchOSC, Lemur, Max/MSP, PureData, any OSC-capable tool

---

## Design Philosophy

**Teenage Engineering × Elektron.**

Every pixel has a purpose. The performance view must be readable in under 1 second,
under stage lighting, with wet hands. Touch targets ≥ 44px. High contrast.
Compact notation: `↺ 4` `↗ chorus` `⤵ fill` `? 1:2` `░ MUTE`.

One screen for performance. Zero navigation during play.

The lane layout adapts to the number of lanes: few lanes → all visible,
many lanes → scrollable with always-visible peek of adjacent lanes.
**Ergonomics drive the display, not an artificial cap.**

---

## Architecture

```
dim/
  core/          Pure Python — zero framework dependency
                 models · timing · instruction · condition · sequencer · playlist
                 tick() is a pure function — fully deterministic and testable

  network/       OSC · WebSocket · REST · mDNS · Ableton Link · MIDI Clock

  adapters/
    web/         Flask + Jinja2 + vanilla CSS — editor + performance view
    tui/         Textual — terminal UI, SSH accessible
    esp32/       MicroPython — WiFi client display

  tests/         pytest — > 80% coverage target
  docs/          Instruction set reference · JSON format spec · Design language
  formats/       example_project.json · schema_v1.json
```

**Core is platform-agnostic.** Web, TUI and ESP32 are adapters consuming the same `tick()`.

---

## Platforms

| Platform | Interface | Notes |
|---|---|---|
| macOS / Linux | Web + TUI | Full editor + performance |
| Raspberry Pi 4 + 7" screen | Web kiosk (Chromium) | Same web code, touch |
| Raspberry Pi headless | TUI via SSH | Performance or orchestrator view |
| iPad / tablet | Web responsive | Touch performance |
| iPhone / small phone | Web responsive | Single lane focus, swipe to switch |
| ESP32 + TFT 320×240 | MicroPython client | Current + next cue display |
| ESP32 + OLED 128×64 | MicroPython client | Current cue + beat counter |

---

## Quick Start

```bash
# From source
git clone https://github.com/obareau/dim && cd dim
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
./dim formats/example_project.json
# → http://localhost:5001

# pip install
pip install dim-sequencer
dim formats/my_show.json

# Docker
docker run -p 5001:5001 ghcr.io/obareau/dim:latest
```

See [`docs/quickstart.md`](docs/quickstart.md) for full setup instructions.

---

## Status

✅ **v0.5.0 — Beta**

All sprints 1–5 complete. 135 tests passing.

```bash
./dim test
# 135 passed, 1 skipped
```

---

## Roadmap

| Version | Focus | Status |
|---|---|---|
| v0.1 | Core — pure Python, full instruction set, CLI playback | ✅ |
| v0.2 | Web interface — editor + performance view | ✅ |
| v0.3 | Sync — Ableton Link, MIDI Clock, OSC | ✅ |
| v0.4 | TUI + debug launcher | ✅ |
| v0.5 | Network — mDNS, multi-instance orchestration, ESP32 client | ✅ |
| v1.0 | Packaging (pip + Docker), docs, public release | 🚧 |

---

## Relation to Robōtariis

D.I.M will be integrated as a **Lite module** inside the
[Robōtariis Sessions](https://github.com/obareau/robotariis-sessions) music session logger,
replacing and extending the current Dawless Prompter.

---

## License

MIT — Personal project, open source.

---

*Olivier Bareau — Scaër, Bretagne — 2026*
*"The machine does not lie. It deforms."*
