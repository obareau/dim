# D.I.M — ESP32 Client

Lightweight HTTP polling client for ESP32 + TFT display.

## Endpoint

    GET /api/esp32/state

Returns a minimal JSON payload optimised for constrained devices:

```json
{
  "p": 1,          // playing (0|1)
  "bpm": 118.0,    // tempo
  "bar": 4,        // current bar
  "beat": 2,       // beat in bar
  "sig": "4/4",    // time signature
  "t": "0:42",     // elapsed time
  "lanes": [
    {
      "id": "lane-synth",
      "nm": "Synth",          // name (truncated to 12 chars)
      "cue": "Chorus A",      // current cue label
      "bdg": "↺ 4",           // instruction badge
      "br": 2.5,              // bars remaining
      "end": 0                // 1 if lane ended
    }
  ]
}
```

## Arduino sketch (ESP32 + TFT_eSPI)

See `adapters/esp32/dim_client.ino` for a reference implementation
that polls `/api/esp32/state` every 200ms and renders on a 240×135 TFT.
