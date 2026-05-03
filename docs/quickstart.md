# D.I.M — Quick Start

## Prerequisites

- Python 3.11+ (3.13 recommended)
- A project JSON file (use `formats/example_project.json` to start)

---

## Option 1 — From source (development)

```bash
git clone https://github.com/obareau/dim
cd dim

# Create a virtualenv
python3 -m venv .venv
source .venv/bin/activate         # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt   # optional: dev tools + tests

# Run the web interface
./dim formats/example_project.json
# → open http://localhost:5001
```

**Available commands via the `dim` launcher:**

```bash
./dim formats/example_project.json           # web server (default)
./dim cli play formats/example_project.json  # CLI playback (no UI)
./dim tui formats/example_project.json       # Textual TUI
./dim debug                                  # debug launcher (tests, Link scan…)
./dim test                                   # run test suite
```

---

## Option 2 — pip install

```bash
pip install dim-sequencer

# Start the web interface
dim formats/my_show.json --port 5001

# Other commands
dim tui my_show.json --play
dim version
```

> **Note:** Ableton Link support requires `aalink` which must be installed separately
> from source (not on PyPI). See [`docs/sync_protocols.md`](sync_protocols.md).

---

## Option 3 — Docker

```bash
# Pull & run (no project)
docker run -p 5001:5001 ghcr.io/obareau/dim:latest

# With a project file
docker run -p 5001:5001 \
  -v $(pwd)/formats/example_project.json:/project.json \
  ghcr.io/obareau/dim:latest /project.json

# Build locally
docker build -t dim:latest .
docker run -p 5001:5001 dim:latest
```

**docker compose:**

```bash
docker compose up
# → open http://localhost:5001
```

---

## Option 4 — Raspberry Pi kiosk

```bash
# On the Pi
pip install dim-sequencer

# Auto-start on boot (systemd)
sudo cp docs/dim.service /etc/systemd/system/
sudo systemctl enable dim
sudo systemctl start dim

# Chromium kiosk mode (add to /etc/xdg/lxsession/LXDE-pi/autostart)
@chromium-browser --kiosk --app=http://localhost:5001/performance
```

---

## Interfaces

| URL | Description |
|---|---|
| `http://localhost:5001/` | Home — load/manage projects |
| `http://localhost:5001/performance` | Performance view (stage use) |
| `http://localhost:5001/editor` | Project editor |
| `http://localhost:5001/api/state` | Live playback state (JSON) |
| `http://localhost:5001/api/esp32/state` | Minimal state for ESP32 clients |

---

## First project

Open `formats/example_project.json` in the editor to explore the instruction set.

The annotated example project demonstrates:
- 3 lanes: Synth, Bass, FX
- LOOP, JUMP, GOSUB, IF, SKIP, REVERSE instructions
- Conductor lane controlling cross-lane jumps
- Speed ratio (1/2x) on the FX lane

---

## Sync

D.I.M auto-detects sync sources in priority order:

| Priority | Source | Setup |
|---|---|---|
| 1 | **Ableton Link** | Install `aalink`, launch any Link-enabled app |
| 2 | **MIDI Clock** | Connect MIDI device, use `/api/sync/midi/start` |
| 3 | **OSC** | Use `/api/sync/osc/start` with your OSC tool |
| 4 | **Internal** | No external sync — D.I.M drives tempo |

See [`docs/sync_protocols.md`](sync_protocols.md) for full setup instructions.
