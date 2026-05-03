# CHANGELOG — D.I.M — Dawless Is More

---

## v0.8.0 — 2026-05-03 — Hardware controllers (M5Stack + VST3/AU plugin)

### Added — REST command endpoints
- `POST /api/cmd/play_toggle` — toggle play/pause (hardware-friendly, no SocketIO)
- `POST /api/cmd/rewind` — rewind + stop
- `POST /api/cmd/advance` — advance first lane in MANUAL WAIT (or `lane_id` in body)
- `POST /api/cmd/advance_all` — advance all waiting lanes
- `POST /api/cmd/veto` — veto next JUMP on first active lane (or `lane_id`)

### Added — M5Stack Core firmware (`hardware/m5stack_core/`)
- `src/main.cpp` — Arduino firmware for M5Stack Core (320×240 TFT, 3 buttons)
- `platformio.ini` — PlatformIO build config (board: `m5stack-core-esp32`, libs: M5Stack + ArduinoJson 6.x)
- `flash.sh` — compile + flash via USB or export `.bin` for M5Burner
- `dist/` — pre-built `.bin` for M5Burner custom flash (address `0x10000`)
- Auto-discovery: fast-path (last known port from NVS) → full scan ports 5000–5010 on IP1 then IP2
- Mid-session re-discovery: automatic re-scan after ~3 s without server response
- Config screen (no touchscreen): edit IP1/IP2 via BtnA−/BtnC+/BtnB-next, hold BtnB 2 s to save in NVS
- Button mapping: A = Advance · A hold = Play/Pause · B = Advance ALL · B hold = Rewind · C = Veto JUMP
- Display: header (BPM ×2, sig, bar/beat, elapsed), adaptive lane rows (progress bar, badge, status stripe), footer hints
- `README.md` — Arduino IDE setup, M5Burner flash instructions, button reference

### Added — JUCE VST3/AU plugin (`hardware/dim_plugin/`)
- `CMakeLists.txt` — JUCE 8.0.4 via FetchContent, VST3 + AU Universal Binary (arm64/x86_64)
- `src/DIMClient.h/cpp` — background polling thread, same auto-discovery as M5Stack (fast-path + scan 5000–5010), mid-session re-discovery, command queue (fire-and-forget POST)
- `src/PluginProcessor.h/cpp` — `AudioProcessor` (0 audio in/out), IPs persisted via `getStateInformation`
- `src/PluginEditor.h/cpp` — custom JUCE GUI: header bar, server bar, adaptive lane rows, footer transport/control buttons, ⚙ config overlay
- `build.sh` — `cmake` configure + build, auto-installs to `~/Library/Audio/Plug-Ins/`
- Installed to `~/Library/Audio/Plug-Ins/VST3/D.I.M.vst3` (Ableton, Reaper, Bitwig)
- Installed to `~/Library/Audio/Plug-Ins/Components/D.I.M.component` (Logic Pro, GarageBand)

### Changed
- `adapters/web/app.py` — bumped version to `0.8.0`; added 5 REST `/api/cmd/*` endpoints

---

## v0.5.0 — 2026-05-02 — Network layer + packaging

### Added
- `network/discovery/mdns.py` — mDNS peer discovery via zeroconf (`_dim._tcp.local.`)
  - `MdnsAnnouncer` — announce presence, listen for peers, callbacks on add/remove
  - `DimPeer` dataclass with `url` / `ws_url` computed properties
  - `get_announcer()` module-level singleton
- `network/websocket/client.py` — `DimClient` SocketIO client
  - Callbacks: `on_state`, `on_event`, `on_connect`, `on_disconnect`
  - Commands: `send_play`, `send_stop`, `send_rewind`, `send_tempo`
- `network/orchestrator/master.py` — `MasterOrchestrator`
  - Auto-connects to all mDNS-discovered slaves
  - Broadcasts transport/tempo to all connected clients
  - Aggregates slave state with `get_status()`
  - `on_peers_changed` / `on_slave_state` callbacks
  - `auto_connect=False` for testing (peers tracked, not connected)
- `adapters/web/app.py` — new REST endpoints:
  - `GET  /api/network/status` — mDNS + orchestrator status
  - `POST /api/network/announce` — announce this instance on mDNS
  - `POST /api/network/orchestrate` — become master
  - `GET  /api/network/peers` — list discovered peers
  - `GET  /api/esp32/state` — minimal JSON for ESP32 TFT clients
- `adapters/esp32/dim_client.ino` — Arduino sketch: ESP32 + TFT_eSPI HTTP polling client
- `adapters/esp32/README.md` — ESP32 endpoint documentation
- `orch_engine_hook()` in `app.py` — wires engine transport → orchestrator broadcast
- `pyproject.toml` — pip-installable package (`dim-sequencer`)
- `dim_pkg/` — Python package with `__main__.py` entry point
- `Dockerfile` + `docker-compose.yml` — multi-stage Docker image
- `docs/quickstart.md` — installation and usage guide
- `docs/sync_protocols.md` — Ableton Link, MIDI Clock, OSC setup reference
- `docs/dim.service` — systemd unit for Raspberry Pi auto-start
- `tests/test_network.py` — 19 tests covering all network components

### Fixed
- `network/orchestrator/master.py` — `_on_peer_added` now always tracks peers in
  `_clients` regardless of `auto_connect`; connection thread only starts when `auto_connect=True`
- `adapters/web/engine.py` — `set_tempo` missing `global _project` declaration
  (caused `UnboundLocalError` on tempo changes after project load)

### Tests
- **135 passed, 1 skipped** (full suite)

---

## v0.4.0 — 2026-05-02 — TUI + debug launcher

### Added
- `adapters/tui/` — Textual TUI (≥0.50)
  - `widgets/transport_bar.py` — play indicator, BPM, bar:beat, beat pips, sync badge
  - `widgets/lane_panel.py` — LanePanel, CueRow, CueProgress (prev/current/next cue)
  - `screens/performance.py` — live performance screen, 20 Hz poll
  - `app.py` — `DimTuiApp`, `run_tui()` entry point
- `run_tui.py` — CLI entry point (`--play`, `--link` flags)
- `adapters/debug/` — Textual debug launcher
  - `commands.py` — 8 async generator commands: pytest, Link scan, Link tempo sequence,
    MIDI ports, project validate, CLI playback, OSC loopback test, system info
  - `link_scanner.py` — `scan_peers()` with multicast socket (SO_REUSEADDR + SO_REUSEPORT),
    parallel DNS resolution, SDK peer count
- `run_debug.py` — `DebugLauncher` Textual app, `./dim debug`
- `dim` launcher — added `tui` and `debug` sub-commands

### Keyboard bindings (TUI performance screen)
| Key | Action |
|---|---|
| `Space` | Play / Pause |
| `R` | Rewind |
| `S` | Stop |
| `↑` / `↓` | BPM ±1 |
| `L` | Toggle Ableton Link |
| `Q` / `Esc` | Quit |

---

## v0.3.0 — 2026-05-02 — Sync layer

### Added
- `adapters/sync/base.py` — `SyncSource` ABC, `SyncState` frozen dataclass
- `adapters/sync/midi_clock.py` — `MidiClockInput` (24 PPQN → BPM), `MidiClockOutput`
- `adapters/sync/link_sync.py` — `LinkSyncSource` with dedicated asyncio event loop thread
  - `aalink` peer discovery, tempo callback, start/stop sync
  - `LinkSyncStub` no-op fallback when `aalink` not installed
  - `make_link_source()` factory
- `adapters/sync/osc_sync.py` — `OscSyncSource` (rx/tx, `/dim/tempo` `/dim/beat`)
- `adapters/sync/manager.py` — `SyncManager`
  - Priority: Link > MIDI > OSC > Internal
  - `on_engine_tick()` hook called from engine loop
  - `get_status()` introspection
- `adapters/web/engine.py` — sync manager hook in `_tick_loop`
- REST endpoints: `/api/sync/status`, `/api/sync/midi/ports`,
  `/api/sync/midi/start`, `/api/sync/osc/start`, `/api/sync/link/start`
- `tests/test_sync.py` — 22 tests (21 pass, 1 skip without `aalink`)
- `tests/test_link_live.py` — live LAN test with tempo jump sequence

### Fixed
- `adapters/sync/osc_sync.py` — wrong import `pythonosc.server` → `pythonosc.osc_server`
- `adapters/sync/manager.py` — Link priority check used `peer_count > 0` (race condition)
  → now uses `s.is_available`

---

## v0.2.0 — 2026-05-01 — Web interface

### Added
- `adapters/web/app.py` — Flask application factory + SocketIO
- `adapters/web/engine.py` — sequencer engine: background tick thread, thread-safe state
- `adapters/web/templates/` — index, editor, performance views
- `adapters/web/static/` — vanilla CSS, vanilla JS (no framework)
- REST API: project CRUD, transport, state, validate
- SocketIO: `state_update`, `transport_state`, `connect` events
- `run_web.py` — entry point
- `formats/schema_v1.json` — JSON schema for project validation

---

## v0.1.0 — 2026-05-01 — Core engine

### Added
- `core/models.py` — `Project`, `Lane`, `Section`, `Cue`, `Instruction`, `Condition`
- `core/timing.py` — bars/beats/BPM conversion, `parse_speed_ratio`
- `core/instruction.py` — `InstructionOp` enum, instruction evaluation
- `core/condition.py` — condition parsing and evaluation (nth-pass, ratio, %, MANUAL, AFTER)
- `core/playlist.py` — playlist modes (all, nth, ratio, custom)
- `core/sequencer.py` — `PlaybackCursor`, `LaneCursor`, pure `tick()` function + events
- `core/serializer.py` — JSON → dataclass round-trip
- `core/validator.py` — structural validation with error levels
- `cli.py` — CLI playback runner
- `formats/example_project.json` — annotated example with 3 lanes
- `docs/instruction_set.md` — full instruction set reference
- `SPECS.md` — complete technical specification
- `tests/` — test_sequencer, test_condition, test_playlist, test_timing, test_serializer

---

## v0.1.0-spec — 2026-05-01 — Specification

- Full technical specification written (SPECS.md)
- Instruction set defined: PLAY, MUTE, LOOP, JUMP, GOSUB, SKIP, REVERSE, IF
- Data model: Project / Lane / Section / Cue / Instruction / Condition
- Lane count: variable 1 to X — no hard upper limit — display adapts dynamically
- Modular architecture: core / network / adapters
- Sync protocols: Ableton Link (priority 1), MIDI Clock, OSC, internal
- Multi-instance network topology defined
- Design language: Teenage Engineering × Elektron
- Target platforms: Web, TUI/SSH, RPi kiosk, ESP32 (TFT + OLED)
- Annotated example project JSON
- Instruction set reference documentation
- Project structure initialized
- GitHub repository created: https://github.com/obareau/dim
