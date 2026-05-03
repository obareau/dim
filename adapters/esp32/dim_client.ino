/*
  D.I.M — ESP32 Client
  dim_client.ino

  Polls /api/esp32/state from a DIM server on the LAN and renders
  playback state on a 240×135 TFT (Lilygo T-Display / TFT_eSPI).

  Dependencies (Arduino Library Manager):
    - TFT_eSPI       (Bodmer)
    - ArduinoJson    (Benoit Blanchon)
    - WiFi           (built-in ESP32)
    - HTTPClient     (built-in ESP32)

  Configure TFT_eSPI via User_Setup.h for your board before compiling.
*/

#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <TFT_eSPI.h>

// ── Config ────────────────────────────────────────────────────────────────────

const char* WIFI_SSID     = "YOUR_WIFI_SSID";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";
const char* DIM_HOST      = "192.168.1.100";   // DIM server IP
const int   DIM_PORT      = 5001;
const int   POLL_MS       = 200;               // poll interval

// ── TFT ───────────────────────────────────────────────────────────────────────

TFT_eSPI tft = TFT_eSPI();
TFT_eSprite spr = TFT_eSprite(&tft);

#define C_BG      0x0000   // black
#define C_TEXT    0xFFFF   // white
#define C_DIM     0x4208   // dark gray
#define C_GREEN   0x07E0   // play indicator
#define C_YELLOW  0xFFE0   // badge / warning
#define C_CYAN    0x07FF   // BPM / accent
#define C_RED     0xF800   // error

// ── State ─────────────────────────────────────────────────────────────────────

struct LaneState {
  String id;
  String name;
  String cue;
  String badge;
  float  bars_rem;
  bool   ended;
};

struct DimState {
  bool        playing;
  float       bpm;
  int         bar;
  int         beat;
  String      sig;
  String      elapsed;
  LaneState   lanes[4];
  int         lane_count;
  bool        loaded;
};

DimState state;
unsigned long last_poll = 0;
bool connected_to_dim   = false;

// ── WiFi ──────────────────────────────────────────────────────────────────────

void connect_wifi() {
  tft.fillScreen(C_BG);
  tft.setTextColor(C_DIM);
  tft.setCursor(4, 4);
  tft.print("D.I.M  connecting...");

  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  int tries = 0;
  while (WiFi.status() != WL_CONNECTED && tries < 20) {
    delay(500);
    tries++;
  }
  if (WiFi.status() == WL_CONNECTED) {
    tft.setTextColor(C_GREEN);
    tft.print(" OK");
  } else {
    tft.setTextColor(C_RED);
    tft.print(" FAILED");
    delay(2000);
  }
}

// ── HTTP poll ─────────────────────────────────────────────────────────────────

bool poll_state() {
  if (WiFi.status() != WL_CONNECTED) return false;

  HTTPClient http;
  String url = String("http://") + DIM_HOST + ":" + DIM_PORT + "/api/esp32/state";
  http.begin(url);
  http.setTimeout(500);
  int code = http.GET();

  if (code != 200) {
    http.end();
    return false;
  }

  String body = http.getString();
  http.end();

  StaticJsonDocument<2048> doc;
  if (deserializeJson(doc, body) != DeserializationError::Ok) return false;

  state.playing    = doc["p"] | 0;
  state.bpm        = doc["bpm"] | 120.0f;
  state.bar        = doc["bar"] | 1;
  state.beat       = doc["beat"] | 1;
  state.sig        = doc["sig"] | "4/4";
  state.elapsed    = doc["t"] | "0:00";
  state.loaded     = true;

  JsonArray lanes = doc["lanes"].as<JsonArray>();
  state.lane_count = min((int)lanes.size(), 4);
  for (int i = 0; i < state.lane_count; i++) {
    state.lanes[i].id       = lanes[i]["id"]  | "";
    state.lanes[i].name     = lanes[i]["nm"]  | "";
    state.lanes[i].cue      = lanes[i]["cue"] | "";
    state.lanes[i].badge    = lanes[i]["bdg"] | "";
    state.lanes[i].bars_rem = lanes[i]["br"]  | 0.0f;
    state.lanes[i].ended    = lanes[i]["end"] | 0;
  }
  return true;
}

// ── Render ────────────────────────────────────────────────────────────────────

void render() {
  spr.fillSprite(C_BG);

  if (!state.loaded) {
    spr.setTextColor(C_DIM);
    spr.setCursor(4, 60);
    spr.print("No project loaded");
    spr.pushSprite(0, 0);
    return;
  }

  // ── Transport bar ─────────────────────────────────────────────────────────
  // Play indicator
  spr.setTextSize(2);
  spr.setTextColor(state.playing ? C_GREEN : C_DIM);
  spr.setCursor(4, 4);
  spr.print(state.playing ? ">" : "||");

  // BPM
  spr.setTextColor(C_CYAN);
  spr.setCursor(30, 4);
  spr.print(state.bpm, 1);
  spr.setTextSize(1);
  spr.setTextColor(C_DIM);
  spr.print(" BPM");

  // Bar:beat
  spr.setTextSize(2);
  spr.setTextColor(C_TEXT);
  spr.setCursor(140, 4);
  spr.print(state.bar);
  spr.print(":");
  spr.print(state.beat);

  // Elapsed
  spr.setTextSize(1);
  spr.setTextColor(C_DIM);
  spr.setCursor(200, 10);
  spr.print(state.elapsed);

  // Divider
  spr.drawLine(0, 26, 240, 26, C_DIM);

  // ── Lane rows ─────────────────────────────────────────────────────────────
  int y = 30;
  int row_h = (135 - 30) / max(state.lane_count, 1);

  for (int i = 0; i < state.lane_count; i++) {
    LaneState& ln = state.lanes[i];

    // Name
    spr.setTextSize(1);
    spr.setTextColor(ln.ended ? C_DIM : C_TEXT);
    spr.setCursor(4, y);
    String nm = ln.name.substring(0, 10);
    spr.print(nm);

    // Cue
    spr.setTextColor(ln.ended ? C_DIM : C_CYAN);
    spr.setCursor(70, y);
    spr.print(ln.cue.substring(0, 14));

    // Badge
    spr.setTextColor(C_YELLOW);
    spr.setCursor(180, y);
    spr.print(ln.badge.substring(0, 8));

    // Progress bar
    if (!ln.ended && ln.bars_rem > 0) {
      float max_bars = 8.0f;
      int bar_w = (int)(120.0f * min(ln.bars_rem / max_bars, 1.0f));
      spr.fillRect(4, y + 10, bar_w, 3, C_CYAN);
      spr.drawRect(4, y + 10, 120, 3, C_DIM);
    }

    if (i < state.lane_count - 1)
      spr.drawLine(0, y + row_h - 2, 240, y + row_h - 2, C_DIM);

    y += row_h;
  }

  spr.pushSprite(0, 0);
}

// ── Setup / loop ──────────────────────────────────────────────────────────────

void setup() {
  Serial.begin(115200);
  tft.init();
  tft.setRotation(1);   // landscape
  tft.fillScreen(C_BG);
  tft.setTextColor(C_TEXT);

  spr.createSprite(240, 135);
  spr.setFreeFont(nullptr);
  spr.setTextSize(1);

  connect_wifi();
  delay(500);
}

void loop() {
  unsigned long now = millis();
  if (now - last_poll >= POLL_MS) {
    last_poll = now;
    bool ok = poll_state();
    if (!ok && state.loaded) {
      // lost connection — dim display
      state.loaded = false;
    }
    render();
  }
}
