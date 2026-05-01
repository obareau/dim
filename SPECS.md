# D.I.M — Dawless Is More
## Technical Specification — v0.1

> *"D.I.M sequences the human, not the machine."*
> Tempo is king. The machine guides. The musician plays.

---

## 1. Vision & Philosophy

### 1.1 Concept

D.I.M is a **performance sequencer for human musicians**.
It controls no instrument, no machine, no plugin.
It guides the performer: what to play, when, in what order, with what variations.

Analogy: the Paris-Dakar rally road book. The driver drives. The co-pilot reads and calls.
D.I.M is the co-pilot. The musician is the driver.

### 1.2 Core Principles

- **Tempo is king** — everything is expressed in bars/beats; seconds are derived
- **Non-linear by design** — a set is not a fixed audio file, it lives and breathes
- **Zero perceptible latency** — the display must never make the musician doubt
- **No-brainer** — readable in < 1 second, usable with wet hands, under stage lights
- **Multi-performer** — one instance per performer, one master to orchestrate all
- **Interoperable** — speaks standard protocols (Ableton Link, MIDI Clock, OSC)

### 1.3 What D.I.M Is NOT

- Not a MIDI/CV sequencer (it does not sequence machines)
- Not a DAW (no recording, no audio tracks)
- Not a simple prompter (structure is non-linear and conditional)
- Not a sample player

---

## 2. Core Concepts

### 2.1 Object Hierarchy

```
Project
  └── Lane(s)          — one instrument, one role, one performer
        └── Section(s) — structural block (intro, verse, chorus, fill...)
              └── Cue(s) — one atomic action to perform
```

### 2.2 The Cue — Atomic Unit

The cue is the indivisible unit. It represents **one action to perform**.
Examples: "Play patch VOID_01", "Cut the filter", "Improvise on D minor scale".

Cue attributes:
```
label           — short name, displayed large on screen
content         — detailed instructions (patch name, settings, notes)
duration_bars   — duration in bars (float: 0.5, 1, 2, 4, 8...)
repeat          — number of repetitions (1 = no repetition)
instruction     — PLAY | MUTE | LOOP | JUMP | GOSUB | SKIP | REVERSE | IF
condition       — 1:2 | 3:4 | 50% | MANUAL | ALWAYS | NEVER
jump_target     — cue_id or section_id (when instruction is JUMP or GOSUB)
jump_lane       — lane_id (for cross-lane jumps)
enabled         — boolean — checked/unchecked in the playlist
order_index     — reorderable position within the section
```

### 2.3 The Section — Structural Block

A grouping of cues. Represents a part of the performance.

Predefined types: `intro` `verse` `chorus` `bridge` `alternative`
                  `fill` `break` `outro` `end` + `custom` (free text)

Section attributes:
```
name, type, color
instruction     — same instruction set as cues
playlist        — cue selection mode (all / nth / ratio / custom)
```

### 2.4 The Lane — One Performer / One Instrument

A horizontal row representing one role in the set.

```
name            — "Main Synth" | "Bass" | "Drums" | "FX" | "Conductor"
color           — distinct color in the UI
speed_ratio     — "1:1" (default) | "2:1" | "4:1" | "1:2" | "1:4"
                  — always a multiple or sub-multiple of the master tempo
is_conductor    — if True, this lane can send commands to other lanes
sections        — ordered list of sections in this lane
```

**Speed ratio**: a lane at 2:1 plays twice as fast. Its bars are half as long.
Synchronization occurs on the global downbeat.

**Number of lanes: 1 to X — no hard upper limit.**
The UI adapts dynamically:
- Few lanes (1–4): all visible simultaneously
- More lanes: scrollable layout with always-visible peek of adjacent lanes
- Ergonomics and screen size drive the display strategy, not an artificial cap
- The Conductor Lane is always pinned to the top when present

### 2.5 The Global Arrangement

Each lane defines its own sequence of sections. An optional global arrangement
synchronizes transition points between lanes on shared downbeats.

---

## 3. The Instruction Set

Direct inspiration from BASIC and fundamental control flow structures.
Each cue AND each section carries **one instruction**.

### 3.1 Core Instructions

| Instruction | Level | Behavior |
|---|---|---|
| `PLAY` | Cue + Section | Play normally, advance to next. **Default.** |
| `MUTE` | Cue + Section | Consume the time, nothing to do. Visual silence. |
| `LOOP n` | Cue + Section | Repeat n times then advance |
| `LOOP UNTIL cond` | Cue + Section | Repeat until condition is true |
| `JUMP target` | Cue + Section | Unconditional jump to cue or section |
| `JUMP target IF cond` | Cue + Section | Conditional jump |
| `GOSUB section` | Cue + Section | Call a section, **return here** after it ends |
| `SKIP` | Cue | Skip this cue (duration = 0) |
| `SKIP UNTIL cond` | Cue | Skip until condition is true |
| `REVERSE` | Section | Play cues in reverse order |
| `REVERSE UNTIL cond` | Section | Reverse until condition, then resume normal |
| `IF cond THEN inst` | Cue + Section | Simple branch |
| `IF cond THEN inst ELSE inst` | Cue + Section | Full branch |

### 3.2 Conditions

| Condition | Notation | Meaning |
|---|---|---|
| Always | `ALWAYS` | Unconditional |
| Never | `NEVER` | = MUTE / SKIP |
| Nth pass | `1:2` `1:4` `3:4` | 1 out of 2 / 3 out of 4 |
| Probabilistic | `50%` `25%` `75%` | Die rolled at each pass |
| Manual trigger | `MANUAL` | Wait for a performer tap/trigger |
| Counter | `AFTER 4` | After 4 passes through this section |

### 3.3 Cross-lane Jump

A cue in Lane A can trigger a jump in Lane B:
```json
{ "instruction": "JUMP", "target": "sec-chorus", "jump_lane": "lane-bass" }
```

The **Conductor Lane** is the recommended convention:
a lane dedicated to orchestrating the others, visible to the band leader.

### 3.4 GOSUB — Call Stack

GOSUB creates a subroutine structure: a section can be "called" from multiple points
and returns to the call site after execution.

Configurable maximum depth (default: 4 levels).
Stack overflow → forced `PLAY` + non-blocking visual alert.

### 3.5 Section Playlist

The playlist defines which cues to play and in what order within a section:

| Mode | Behavior |
|---|---|
| `all` | All enabled cues, in order |
| `nth:2` | 1 cue out of 2 |
| `ratio:3:4` | 3 cues out of 4 |
| `custom` | Free order and selection defined manually |

Each cue can be checked/unchecked (enabled) and reordered within the playlist.

---

## 4. Timing & Synchronization

### 4.1 Units

The primary unit is the **bar**. Seconds are derived.

```
beats_per_bar    = time signature numerator (4/4 → 4, 3/4 → 3, 7/8 → 7)
sec_per_beat     = 60 / tempo_bpm
sec_per_bar      = sec_per_beat × beats_per_bar
cue_duration_sec = cue.duration_bars × sec_per_bar
```

Supported time signatures: `4/4` `3/4` `6/8` `7/8` `5/4` `12/8` + free entry.

### 4.2 Ableton Link (Priority 1)

**Primary sync integration.** Ableton Link is a peer-to-peer protocol for tempo
and beat position synchronization on a local network (UDP multicast).

D.I.M behavior:
- D.I.M can **join** an existing Link session (Ableton, iOS apps, etc.)
- D.I.M can **be** the tempo source of a Link session
- Automatic synchronization as soon as a Link session is detected on the network
- No master/slave: symmetric protocol — all peers negotiate

Python library: `python-link` (official Ableton Link SDK binding).

### 4.3 MIDI Clock (Priority 2)

- **Receive**: D.I.M follows an external MIDI Clock (24 PPQN)
- **Send**: D.I.M emits MIDI Clock (to sync hardware)
- USB MIDI + DIN MIDI (via adapter)
- Messages: `CLOCK` (24/QN) `START` `STOP` `CONTINUE`

### 4.4 OSC (Priority 3)

- Native D.I.M protocol for inter-instance communication
- Compatible with Ableton (via OSC plugins), Max/MSP, PureData, SuperCollider, TouchOSC
- UDP — latency < 1ms on LAN

### 4.5 Internal Clock (Priority 4)

Standalone fallback. Used when no external sync source is detected.

### 4.6 Sync Source Priority

```
Priority (highest first):
  1. Ableton Link     (if a Link session is detected on the network)
  2. External MIDI Clock received
  3. D.I.M Master clock (OSC broadcast from master instance)
  4. Internal clock   (standalone)
```

Conflict resolution: highest-priority detected source wins.
Source change → tempo crossfade (no hard jump).

---

## 5. Network Architecture

### 5.1 Topology

```
D.I.M MASTER (laptop / central RPi)
│
├── Ableton Link session (shared with DAW, iOS apps, etc.)
├── OSC broadcast → all D.I.M instances
├── WebSocket server → real-time state
├── REST API → project + instance management
│
├── D.I.M Instance 2  (RPi — Synth performer)
├── D.I.M Instance 3  (RPi — Drums performer)
├── D.I.M Instance 4  (ESP32 — FX monitor)
└── TouchOSC / Lemur  (control surface)
```

### 5.2 Protocols by Layer

| Layer | Protocol | Port | Target latency |
|---|---|---|---|
| Beat/tempo sync | Ableton Link (UDP multicast) | 20808 | < 1 ms |
| Transport sync | OSC / UDP | 7400 | < 1 ms |
| Real-time state | WebSocket | 7401 | < 10 ms |
| Management | REST HTTP | 5000 | < 100 ms |
| Human access | SSH + TUI | 22 | — |
| Discovery | mDNS / Bonjour | — | automatic |

### 5.3 OSC Address Space

```
# Transport
/dim/transport/play
/dim/transport/stop
/dim/transport/pause
/dim/transport/rewind
/dim/transport/tempo        f:120.0
/dim/transport/jump         s:"section-id"

# Hard sync
/dim/sync/beat              i:<beat>  i:<bar>  t:<timestamp>

# Lane control
/dim/lane/<id>/mute
/dim/lane/<id>/unmute
/dim/lane/<id>/jump         s:"section-id"
/dim/lane/<id>/speed        s:"2:1"

# Instance → Master (state reporting)
/dim/report/<name>/beat     i:<beat>  i:<bar>
/dim/report/<name>/state    s:<json>

# Orchestrator → instance
/dim/instance/<name>/play
/dim/instance/<name>/project  s:<json>
/dim/instance/all/sync
```

### 5.4 Auto-discovery

Each instance announces itself via **mDNS (Zeroconf/Bonjour)**:
```
dim-synth._dim._tcp.local   port 5000 (HTTP) + 7400 (OSC)
```
No manual IP configuration required. Plug in → automatically appears.
ESP32: mDNS via built-in ESP-IDF library.

---

## 6. Interfaces

### 6.1 UI Philosophy

**Design reference: Teenage Engineering × Elektron**

- Teenage Engineering: every pixel is intentional. Zero decoration. Functional = beautiful.
- Elektron: information density, compact notation, all critical info visible at once.

**Core rules:**
1. Readable in < 1 second under any lighting condition
2. Touch targets ≥ 44px (Apple HIG standard) — usable with fingers, not a stylus
3. High contrast — dark mode by default (stage = low light)
4. No gratuitous animation — animations carry semantic meaning only
5. One screen for performance — zero navigation while playing
6. Information priority: **current cue → next → position → time**

### 6.2 Web Interface (Primary Adapter)

Two distinct modes:

**Editor mode** (desktop + tablet landscape):
- Grid view: lanes as rows, sections as colored columns
- Contextual side panel: click section → cue list + instruction + playlist
- Drag & drop to reorder sections and cues
- Tempo panel at top: BPM, time signature, Link status, sync source

**Performance mode** (all devices, full screen):
- Lane(s) in focus: previous section (dim) | current section | next section (dim)
- Current cue displayed large at center
- Beat/bar countdown top-right
- Topbar: BPM | time signature | current bar | elapsed time | Link indicator
- Transport: ⏮ ⏹ ▶/⏸ — always accessible
- Instruction badges: `LOOP 4` `↗ chorus` `↺ 1:2` `GOSUB fill`

**Lane display strategy (performance mode):**

The number of lanes is variable (1 to X). The UI adapts:

| Visible lanes | Layout strategy |
|---|---|
| 1 | Full width, maximum content |
| 2–3 | Equal columns, all visible |
| 4–5 | Compact columns, all visible |
| 6–8 | Scrollable, active lane centered, adjacent peek |
| 9+ | Active lane full width, lane switcher panel |

The performer always sees their lane. The master always sees the Conductor Lane.
No lane is ever hidden without a visible indicator.

### 6.3 Responsive Breakpoints

| Context | Viewport | Mode | Lane strategy |
|---|---|---|---|
| Desktop | > 1200px | Editor + Performance | All lanes, scrollable |
| Tablet landscape | 1024px | Performance + light edit | Up to ~5 lanes visible |
| Tablet portrait / RPi 7" | 768px | Performance | 2–3 lanes, scrollable |
| Phone / RPi 3.5" | 480px | Performance, 1 lane focus | Swipe to switch lane |
| ESP32 TFT 320×240 | 320px | Current cue + next | 1 assigned lane |
| ESP32 OLED 128×64 | 128px | Current cue only | 1 assigned lane |

The number of visible lanes is a **display constraint**, never a data model constraint.
A project with 12 lanes is valid; the UI scrolls to show them.

### 6.4 TUI — Terminal User Interface

Implemented with **Textual** (Python).

Accessible via:
- Local terminal
- SSH (`.bashrc` → auto-launches TUI)
- Tmux/screen for persistent sessions

Two views:
- **Performance**: same information as web, rendered in Unicode/ASCII
- **Orchestrator**: grid of all known instances, real-time state

```
┌─ D.I.M ──────────────────── ▶ 118 BPM  4/4  ♩32  02:14 ─┐
│ CONDUCTOR │░░░░████████░░│ CHORUS        VERSE 2          │
├───────────┼──────────────┼──────────────────────────────── ┤
│ SYNTH 1:1 │ [LOOP 2]     │ ▶ pad-void    ↺ 1:2           │
├───────────┼──────────────┼──────────────────────────────── ┤
│ BASS  2:1 │ MUTE ░░░░░░░ │ ▶ sub-bass    SKIP 2:4        │
└───────────┴──────────────┴──────────────────────────────── ┘
 [SPC] next  [←][→] nav  [M] mute  [L] loop  [S] stop  [?]
```

### 6.5 ESP32 — Display Client

The ESP32 is a **read-only display client**. It runs no sequencing logic.
It receives the current state from the D.I.M server via WiFi (WebSocket or HTTP polling).
It is assigned one specific lane to display.

**TFT 320×240 (ILI9341)**:
- Current cue (large) + next cue (small)
- Beat progress bar
- Instruction badge
- Touch buttons: next / prev / stop

**OLED 128×64 (SSD1306)**:
- Current cue only
- Beat counter
- Minimal wrist-watch display

Connection: WiFi → WebSocket → subscribe to assigned lane state.

---

## 7. Technical Architecture

### 7.1 Project Structure

```
dim/
  core/                        # Pure Python — zero framework dependency
    models.py                  # Dataclasses: Project, Lane, Section, Cue, Instruction
    timing.py                  # BPM/bars/sec, speed_ratio, downbeat, conversions
    instruction.py             # Instruction evaluation (PLAY/LOOP/GOSUB/JUMP...)
    condition.py               # Condition evaluation (1:2, 50%, MANUAL...)
    sequencer.py               # Pure tick(), multi-lane cursor, GOSUB stack
    playlist.py                # Cue queue construction within a section
    serializer.py              # JSON ↔ models (versioned canonical format)
    validator.py               # Project validation (cycles, invalid jumps, stack depth)

  network/
    osc/
      server.py                # UDP OSC receiver, handler dispatch
      client.py                # OSC emitter (unicast + broadcast)
      messages.py              # Address patterns, types, encode/decode
      handlers.py              # /dim/transport/*, /dim/lane/*, etc.
    websocket/
      server.py                # Flask-SocketIO
      events.py                # Events: state_update, beat, sync, instance_list
    rest/
      blueprint.py             # CRUD projects, instances, config
      schema.py                # Request/response validation
    discovery/
      mdns.py                  # Zeroconf — announce + browse
      registry.py              # Known instances, state, timestamps
    orchestrator/
      master.py                # Master logic — instance management
      sync.py                  # Multi-instance beat synchronization algorithm
      proxy.py                 # InstanceProxy — remote instance abstraction
    link/
      link_session.py          # Ableton Link integration (python-link)
      link_bridge.py           # Bridge: Link ↔ D.I.M OSC
    midi/
      clock_receiver.py        # MIDI Clock reception (24 PPQN)
      clock_sender.py          # MIDI Clock emission
      midi_bridge.py           # Bridge: MIDI Clock ↔ D.I.M sequencer

  adapters/
    web/
      app.py                   # Flask application factory
      blueprints/              # Routes by domain
      templates/               # Jinja2 — Editor + Performance
      static/                  # Vanilla CSS + lightweight JS (no framework)
    tui/
      app.py                   # Textual Application
      screens/
        performance.py         # Stage view
        orchestrator.py        # Master view
      widgets/                 # Textual components
    esp32/
      main.py                  # MicroPython entry point
      wifi_sync.py             # WiFi connection + WebSocket client
      display_tft.py           # ILI9341 320×240
      display_oled.py          # SSD1306 128×64
      micro_models.py          # Model subset (dataclasses → dicts for MicroPython)

  tests/
    test_timing.py
    test_instruction.py
    test_condition.py
    test_sequencer.py          # Full scenarios (GOSUB, cross-lane, sync)
    test_playlist.py
    test_serializer.py

  docs/
    instruction_set.md         # Complete instruction + condition reference
    format_v1.md               # Versioned canonical JSON spec
    design_language.md         # UI rules (TE/Elektron)
    sync_protocols.md          # Ableton Link, MIDI Clock, OSC integration guide
    osc_address_space.md       # Complete OSC reference

  formats/
    example_project.json       # Annotated example project
    schema_v1.json             # JSON Schema for validation

  requirements.txt
  requirements-dev.txt
  .gitignore
  LICENSE
  README.md
  SPECS.md
  CHANGELOG.md
```

### 7.2 Python Dependencies

```
# Core runtime
python >= 3.11

# Web + network
flask >= 3.0
flask-socketio >= 5.0
python-osc >= 1.8            # OSC server + client
zeroconf >= 0.80             # mDNS discovery

# TUI
textual >= 0.50

# Sync protocols
python-link >= 0.0.1         # Ableton Link SDK binding
python-rtmidi >= 1.5         # MIDI Clock

# Dev + tests
pytest
pytest-asyncio
black
ruff
```

### 7.3 Canonical JSON Format

```json
{
  "dim_version": "1.0",
  "project": {
    "id": "uuid",
    "name": "Robōtariis Live Set 2026",
    "tempo_bpm": 118.0,
    "time_signature": "4/4",
    "gosub_stack_limit": 4,
    "lanes": [
      {
        "id": "lane-conductor",
        "name": "Conductor",
        "color": "#888888",
        "speed_ratio": "1:1",
        "is_conductor": true,
        "sections": []
      },
      {
        "id": "lane-synth",
        "name": "Main Synth",
        "color": "#FF4D26",
        "speed_ratio": "1:1",
        "is_conductor": false,
        "sections": [
          {
            "id": "sec-intro",
            "name": "Opening Drone",
            "type": "intro",
            "color": "#2A2A2A",
            "instruction": { "op": "LOOP", "loop_count": 2 },
            "playlist": { "mode": "all" },
            "cues": [
              {
                "id": "cue-001",
                "label": "Deep Drone",
                "content": "Patch VOID_01 — filter closed, cutoff 40% — reverb max",
                "duration_bars": 8.0,
                "repeat": 1,
                "instruction": { "op": "PLAY" },
                "enabled": true,
                "order_index": 0
              }
            ]
          }
        ]
      }
    ],
    "arrangement": ["sec-intro", "sec-verse", "sec-chorus"]
  }
}
```

### 7.4 The tick() Principle

The golden rule: `tick()` is a **pure function**.

```python
def tick(
    cursor: PlaybackCursor,
    delta_beats: float,
    project: Project
) -> tuple[PlaybackCursor, list[Event]]:
    """
    Advance the cursor by delta_beats.
    Returns the new cursor and the list of events produced.
    No side effects. Fully deterministic and testable.
    """
```

All side effects (display, OSC sending, alerts) are handled by adapters
consuming the returned event list.

---

## 8. Ergonomics & Design Language

### 8.1 Color and Typography

- **Background**: near-black `#0D0D0D` (performance) / `#111111` (editor)
- **Primary text**: `#E8E4DC` (warm white)
- **Lane accent**: per-lane color, saturated, ≥ 4.5:1 contrast on background
- **Muted**: `#555555`
- **Danger / Urgent**: `#FF4D26`
- **Typography**: IBM Plex Mono (labels, codes) + IBM Plex Sans (body)
- **Current cue size**: ≥ 24px on mobile, ≥ 32px on desktop

### 8.2 Compact Notation (Elektron-style)

| Instruction | Badge |
|---|---|
| `LOOP 4` | `↺ 4` |
| `JUMP chorus` | `↗ chorus` |
| `GOSUB fill` | `⤵ fill` |
| `MUTE` | `░ MUTE` |
| `SKIP UNTIL 1:4` | `⇥ 1:4` |
| `IF 1:2 THEN JUMP` | `? 1:2 ↗` |
| `REVERSE` | `⇐ REV` |
| `50%` | `⚄ 50%` |

### 8.3 Visual States

- **Current cue**: strong background, maximum text size, instruction badge prominent
- **Next cue**: 55% opacity, slight offset
- **Previous cue**: 30% opacity
- **Muted section**: hatched background `░`, grayed text
- **Beat counter**: progress bar in beats (not seconds)
- **Link sync**: discrete indicator in topbar — green if connected, absent if solo
- **GOSUB stack overflow**: non-blocking red flash, 2 seconds, no interruption

### 8.4 Touch Interactions

- Swipe left/right: next/previous cue
- Tap bottom zone: stop
- Long press on section: quick instruction access
- Pinch: font zoom (40% to 250%)
- All buttons: ≥ 44×44px
- Haptic feedback on critical transitions (where available)

---

## 9. Target Platforms

| Platform | Interface | Notes |
|---|---|---|
| macOS / Linux desktop | Web (Flask) + TUI | Full editor + performance |
| Windows | Web (Flask) | TUI possible via WSL |
| Raspberry Pi 4 + 7" screen | Web kiosk (Chromium) | Same web code, CSS responsive |
| Raspberry Pi Zero 2 + 3.5" | Web kiosk | Compact layout, large text |
| Raspberry Pi headless | TUI via SSH | Performance or orchestrator |
| ESP32 + TFT ILI9341 320×240 | MicroPython client | Current cue + next + beat |
| ESP32 + OLED SSD1306 128×64 | MicroPython client | Current cue + beat counter |
| iPad / tablet | Web responsive | Full touch performance |
| iPhone | Web responsive | Single lane focus, swipe to switch |

---

## 10. Architectural Decisions

| Topic | Decision |
|---|---|
| Name | **D.I.M — Dawless Is More** |
| Paradigm | Sequence the human, not the machine |
| Primary unit | Bars (beats) — seconds are derived |
| Number of lanes | **1 to X — no upper limit** — display adapts dynamically |
| Sync priority | Ableton Link > MIDI Clock > OSC Master > internal clock |
| Inter-instance sync | OSC UDP (transport) + WebSocket (state) |
| Discovery | mDNS / Bonjour — zero config |
| Control flow | BASIC-inspired: 11 instructions, 6 condition types, GOSUB stack, cross-lane |
| Cross-lane | JUMP / GOSUB inter-lane via Conductor Lane convention |
| ESP32 | Read-only display client — receives state from Flask server |
| TUI | Textual (Python) — local + SSH |
| Web | Flask + vanilla CSS — no JS framework |
| Tests | pytest — `tick()` is pure, fully deterministic |
| Data format | Versioned canonical JSON (`dim_version`) |
| Design | Teenage Engineering × Elektron — dense, functional, < 1s readability |

---

## 11. Out of Scope (explicitly excluded from v1)

- MIDI/CV sequencing of instruments
- Audio recording
- Mixing
- Audio effects
- Sample playback
- Music notation / sheet music
- Video synchronization
- User account management (v1 = single-user / trusted local network)

---

## 12. Roadmap

```
v0.1 — Pure Core (Sprint 1)
  Complete core/: models, timing, instruction, condition, sequencer, playlist
  CLI-testable: python -m dim.cli play formats/example_project.json
  Test coverage > 80%

v0.2 — Web Interface (Sprint 2)
  Flask + basic project editor
  Responsive performance view
  JSON export/import

v0.3 — Sync (Sprint 3)
  Ableton Link (python-link)
  MIDI Clock reception + emission
  Basic OSC inter-instance

v0.4 — TUI + SSH (Sprint 4)
  Textual performance view
  TUI orchestrator (multi-instance)

v0.5 — Full Network (Sprint 5)
  mDNS discovery
  WebSocket state broadcast
  Master orchestrator
  ESP32 client (TFT)

v1.0 — Public Release
  Complete documentation
  Example projects
  Packaging (pip install dim)
  Docker image
```

---

*D.I.M — Dawless Is More*
*"The machine does not lie. It deforms."*

*Specification v0.1 — May 2026 — Olivier Bareau, Scaër, Bretagne*
