# D.I.M — Sync Protocols

D.I.M supports four sync sources, evaluated in priority order.
Only the highest-priority active source drives the tempo.

---

## Priority

```
Ableton Link  >  MIDI Clock  >  OSC  >  Internal
```

If Link is active (peers detected), it always wins.
If Link drops, D.I.M falls back to MIDI Clock, then OSC, then its own clock.

---

## 1. Ableton Link

Peer-to-peer beat clock that works over WiFi/Ethernet, zero config.
Compatible with Ableton Live, Traktor, Elektron devices, iOS apps (Koala, Loopy, etc.).

### Install

`aalink` is not on PyPI. Install from source:

```bash
git clone https://github.com/gndl/aalink
cd aalink
pip install .
```

### Activate

Link is enabled automatically when `aalink` is installed and D.I.M detects peers.
The `SyncManager` uses Link as the primary source as soon as any peer joins.

**Via TUI:** press `L` in the performance screen to toggle Link.

**Via API:**
```bash
curl -X POST http://localhost:5001/api/sync/link/start \
     -H "Content-Type: application/json" \
     -d '{"quantum": 4}'
```

### Quantum

The quantum is the number of beats in one Link phase cycle.
For 4/4 music, use `4` (default). For 6/8, use `6`.

---

## 2. MIDI Clock

Receives MIDI timing clock (F8 messages, 24 PPQN) from a master device —
a drum machine, DAW, or dedicated clock generator.

Also outputs MIDI clock when D.I.M is the master, so your hardware follows it.

### Requirements

```bash
pip install python-rtmidi
```

### List available ports

```bash
curl http://localhost:5001/api/sync/midi/ports
# → {"inputs": ["IAC Driver Bus 1", "Elektron Analog Rytm"], "outputs": [...]}
```

### Start MIDI input (follow external clock)

```bash
curl -X POST http://localhost:5001/api/sync/midi/start \
     -H "Content-Type: application/json" \
     -d '{"input_port": "Elektron Analog Rytm"}'
```

### Start MIDI output (send clock to hardware)

```bash
curl -X POST http://localhost:5001/api/sync/midi/start \
     -H "Content-Type: application/json" \
     -d '{"output_port": "IAC Driver Bus 1"}'
```

### Both simultaneously

```bash
curl -X POST http://localhost:5001/api/sync/midi/start \
     -H "Content-Type: application/json" \
     -d '{"input_port": "Clock In", "output_port": "Clock Out"}'
```

---

## 3. OSC

Open Sound Control — works with Max/MSP, SuperCollider, PureData, TouchOSC, Lemur,
and any OSC-capable tool.

### Protocol

D.I.M sends (broadcast) and receives on configurable ports.

**Incoming messages (D.I.M listens):**

| Address | Args | Description |
|---|---|---|
| `/dim/tempo` | `float bpm` | Set tempo |
| `/dim/play` | — | Start playback |
| `/dim/stop` | — | Stop playback |
| `/dim/beat` | `float position` | Beat position update |

**Outgoing messages (D.I.M broadcasts):**

| Address | Args | Description |
|---|---|---|
| `/dim/tempo` | `float bpm` | Tempo changed |
| `/dim/beat` | `float position` | Each tick |

### Start OSC sync

```bash
curl -X POST http://localhost:5001/api/sync/osc/start \
     -H "Content-Type: application/json" \
     -d '{"rx_port": 57120, "tx_port": 57121, "tx_host": "255.255.255.255"}'
```

---

## 4. Internal clock

No configuration needed. D.I.M uses its own tempo when no external source is active.
Set the tempo via:

- The web performance view (BPM tap/drag)
- `PUT /api/transport/tempo {"bpm": 120}`
- SocketIO event `set_tempo {"bpm": 120}`
- TUI: `↑` / `↓` (±1 BPM), or type a value

---

## Status

Check which source is active:

```bash
curl http://localhost:5001/api/sync/status
```

```json
{
  "active_source": "link",
  "link": {"available": true, "peer_count": 2, "tempo": 118.0},
  "midi": {"input_port": null, "output_port": null},
  "osc":  {"rx_port": null}
}
```
