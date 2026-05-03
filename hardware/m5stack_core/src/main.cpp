/**
 * D.I.M — M5Stack Core controller
 * ─────────────────────────────────────────────────────────────────────────
 * Hardware : M5Stack Core (black, 320×240 TFT, 3 buttons A/B/C)
 * Board    : M5Stack-Core-ESP32  (Arduino IDE → Board Manager → M5Stack)
 * Libraries: M5Stack, ArduinoJson 6.x, WiFi (built-in ESP32)
 *
 * Comportement
 *  • Connexion WiFi → pour chaque IP (1 puis 2) : balaie les ports 5000–5010
 *  • Si aucun serveur trouvé → config screen
 *  • Polling /api/esp32/state toutes les 200 ms
 *  • BtnA  ▶  Advance (première lane en MANUAL WAIT, ou lane focalisée)
 *  • BtnB  ▶▶ Advance ALL (toutes les lanes en attente)
 *  • BtnC  ✕  Veto JUMP (première lane active)
 *  • Hold BtnA + BtnC au démarrage → config screen forcée
 *
 * Config screen (sans écran tactile)
 *  • BtnA / BtnC  : valeur − / +
 *  • BtnB         : champ suivant (4 octets IP + port + WiFi SSID + pwd)
 *  • Hold BtnB 2s : sauvegarder en NVS et redémarrer
 * ─────────────────────────────────────────────────────────────────────────
 */

#include <M5Stack.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <Preferences.h>

// ── Compile-time defaults (overridable via config screen) ─────────────────
#define DEFAULT_WIFI_SSID   "YourSSID"
#define DEFAULT_WIFI_PASS   "YourPassword"
#define DEFAULT_IP1         "192.168.1.100"
#define DEFAULT_IP2         "192.168.1.1"
#define DISCOVERY_PORT_MIN  5000   // scan range for auto-discovery
#define DISCOVERY_PORT_MAX  5010
#define POLL_INTERVAL_MS    200
#define HTTP_TIMEOUT_MS     400
#define DISCOVERY_RETRIES   2

// ── NVS key names ─────────────────────────────────────────────────────────
#define NVS_NS    "dim"
#define NVS_SSID  "ssid"
#define NVS_PASS  "pass"
#define NVS_IP1   "ip1"
#define NVS_IP2   "ip2"
#define NVS_PORT  "port"   // last found/configured port (saved after discovery)

// ── Colors (565 RGB) ──────────────────────────────────────────────────────
#define C_BG      0x0000   // black
#define C_HEADER  0x2124   // dark grey
#define C_ACCENT  0xE4E6   // yellow ~#E8C830 → 565
#define C_ACCENT2 0x2B5F   // blue ~#55AAFF
#define C_TEXT    0xC618   // light grey
#define C_DIM     0x4208   // mid grey
#define C_RED     0xF800
#define C_GREEN   0x07E0
#define C_ORANGE  0xFD20
#define C_WAIT    0xFD20   // orange = MANUAL WAIT
#define C_PLAY    0x07E0   // green  = PLAYING
#define C_STOP    0x4208   // grey   = STOPPED

// ── Global state ──────────────────────────────────────────────────────────
Preferences prefs;

struct Config {
  char ssid[64];
  char pass[64];
  char ip1[32];
  char ip2[32];
  uint16_t port;   // last successfully connected port (0 = not yet discovered)
};

Config cfg;
String serverBase;  // "http://IP:PORT"
bool connected = false;

// Parsed display state
struct LaneInfo {
  char name[13];
  char cue[17];
  char badge[9];
  float bars;
  bool ended;
  bool waiting;
};

struct DimState {
  bool playing;
  float bpm;
  uint16_t bar;
  uint8_t beat;
  char sig[8];
  char elapsed[8];
  LaneInfo lanes[8];
  uint8_t laneCount;
  bool loaded;
};

DimState dimState;
DimState prevState;
bool stateValid = false;

// ── Button timing ─────────────────────────────────────────────────────────
unsigned long btnADown = 0, btnBDown = 0, btnCDown = 0;
bool btnAHeld = false, btnBHeld = false, btnCHeld = false;
#define HOLD_MS 2000

// ── Forward declarations ──────────────────────────────────────────────────
void loadConfig();
void saveConfig();
bool tryConnect(const char* ip, uint16_t port);
bool discoverServer(const char* ip, uint16_t* foundPort);
bool runDiscovery();   // full discovery with fast-path + scan, sets serverBase
void runConfigScreen();
void drawMainScreen();
void drawHeader();
void drawLanes();
void drawFooter();
void drawConnecting(const char* msg);
void drawError(const String& msg);   // accepts String or const char*
bool fetchState();
void postCmd(const char* endpoint);
String httpPost(const char* path, const char* body = "{}");
void flashFooterLabel(uint8_t btn, const char* label);

// ─────────────────────────────────────────────────────────────────────────
// SETUP
// ─────────────────────────────────────────────────────────────────────────
void setup() {
  M5.begin(true, true, true, false);  // lcd, sd, serial, i2s
  M5.Lcd.setTextColor(C_TEXT, C_BG);
  M5.Lcd.fillScreen(C_BG);

  loadConfig();

  // Hold BtnA + BtnC at startup → forced config
  M5.update();
  if (M5.BtnA.isPressed() && M5.BtnC.isPressed()) {
    runConfigScreen();
  }

  // ── WiFi ──────────────────────────────────────────────────────────────
  drawConnecting("Connecting WiFi...");
  drawConnecting(cfg.ssid);

  WiFi.mode(WIFI_STA);
  WiFi.begin(cfg.ssid, cfg.pass);

  unsigned long t0 = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - t0 < 15000) {
    delay(300);
    M5.Lcd.print(".");
  }

  if (WiFi.status() != WL_CONNECTED) {
    drawError("WiFi failed!\nCheck SSID/Pass\nHold A+C to config");
    delay(5000);
    runConfigScreen();
    return;
  }

  // ── Server discovery ──────────────────────────────────────────────────
  drawConnecting("WiFi OK\nFinding server...");

  if (!runDiscovery()) {
    drawError(
      "Server not found!\n"
      "Scanned ports 5000-5010 on:\n  " +
      String(cfg.ip1) + "\n  " + String(cfg.ip2) +
      "\nHold A+C to config"
    );
    delay(5000);
    runConfigScreen();
    return;
  }

  connected = true;
  drawConnecting(("Server: " + serverBase).c_str());
  delay(800);

  M5.Lcd.fillScreen(C_BG);
  drawMainScreen();
}

// ─────────────────────────────────────────────────────────────────────────
// MAIN LOOP
// ─────────────────────────────────────────────────────────────────────────
void loop() {
  if (!connected) { delay(1000); return; }

  M5.update();
  unsigned long now = millis();

  // ── Button A — Advance ────────────────────────────────────────────────
  if (M5.BtnA.wasPressed()) {
    postCmd("/api/cmd/advance");
    btnADown = now;
  }
  if (M5.BtnA.isPressed() && now - btnADown > HOLD_MS && !btnAHeld) {
    btnAHeld = true;
    // Hold A → play/toggle
    postCmd("/api/cmd/play_toggle");
    flashFooterLabel(0, "PLAY/STOP");
  }
  if (M5.BtnA.wasReleased()) { btnAHeld = false; }

  // ── Button B — Advance ALL ────────────────────────────────────────────
  if (M5.BtnB.wasPressed()) {
    postCmd("/api/cmd/advance_all");
    btnBDown = now;
  }
  if (M5.BtnB.isPressed() && now - btnBDown > HOLD_MS && !btnBHeld) {
    btnBHeld = true;
    // Hold B → rewind
    postCmd("/api/cmd/rewind");
    flashFooterLabel(1, "REWIND");
  }
  if (M5.BtnB.wasReleased()) { btnBHeld = false; }

  // ── Button C — Veto JUMP ──────────────────────────────────────────────
  if (M5.BtnC.wasPressed()) {
    postCmd("/api/cmd/veto");
    btnCDown = now;
  }
  if (M5.BtnC.isPressed() && now - btnCDown > HOLD_MS && !btnCHeld) {
    btnCHeld = true;
    // Hold C → config screen (saves & restarts)
    drawConnecting("Hold both A+C\nto enter config");
    delay(1500);
  }
  if (M5.BtnC.wasReleased()) { btnCHeld = false; }

  // ── Poll server ───────────────────────────────────────────────────────
  static unsigned long lastPoll = 0;
  if (now - lastPoll >= POLL_INTERVAL_MS) {
    lastPoll = now;
    if (fetchState()) {
      if (memcmp(&dimState, &prevState, sizeof(DimState)) != 0) {
        drawMainScreen();
        memcpy(&prevState, &dimState, sizeof(DimState));
      }
    } else {
      // Server unreachable — count consecutive failures
      static uint8_t failCount = 0;
      failCount++;
      if (failCount == 5) {
        // 5 × 200 ms = ~1 s without response: warn on screen
        drawError("Server unreachable\n" + serverBase + "\nRetrying...");
      }
      if (failCount >= 15) {
        // ~3 s without response: re-run full discovery
        failCount = 0;
        drawConnecting("Re-scanning server...");
        if (runDiscovery()) {
          drawMainScreen();  // back to normal
        } else {
          drawError(
            "Server lost!\n"
            "Scanned 5000-5010 on:\n  " +
            String(cfg.ip1) + "\n  " + String(cfg.ip2) +
            "\nWill retry..."
          );
          delay(3000);
          // Keep trying — don't lock into config screen mid-session
        }
      }
    }
  }
}

// ─────────────────────────────────────────────────────────────────────────
// CONFIG: Load / Save (NVS)
// ─────────────────────────────────────────────────────────────────────────
void loadConfig() {
  prefs.begin(NVS_NS, true);
  strlcpy(cfg.ssid, prefs.getString(NVS_SSID, DEFAULT_WIFI_SSID).c_str(), 64);
  strlcpy(cfg.pass, prefs.getString(NVS_PASS, DEFAULT_WIFI_PASS).c_str(), 64);
  strlcpy(cfg.ip1,  prefs.getString(NVS_IP1,  DEFAULT_IP1).c_str(), 32);
  strlcpy(cfg.ip2,  prefs.getString(NVS_IP2,  DEFAULT_IP2).c_str(), 32);
  // Port: use last found port from NVS, or 0 (= will be auto-discovered)
  cfg.port = prefs.getUShort(NVS_PORT, 0);
  prefs.end();
}

void saveConfig() {
  prefs.begin(NVS_NS, false);
  prefs.putString(NVS_SSID, cfg.ssid);
  prefs.putString(NVS_PASS, cfg.pass);
  prefs.putString(NVS_IP1,  cfg.ip1);
  prefs.putString(NVS_IP2,  cfg.ip2);
  prefs.putUShort(NVS_PORT, cfg.port);
  prefs.end();
}

// ─────────────────────────────────────────────────────────────────────────
// CONFIG SCREEN  (IP / WiFi editor — sans écran tactile)
//
// Champs : [ssid] [pass] [ip1 ×4] [ip2 ×4] [port]
// Navigation : BtnB = champ suivant / BtnA = val− / BtnC = val+
// Hold BtnB 2s = sauver et reboot
// ─────────────────────────────────────────────────────────────────────────
enum CfgField {
  F_SSID, F_PASS,
  F_IP1_0, F_IP1_1, F_IP1_2, F_IP1_3,
  F_IP2_0, F_IP2_1, F_IP2_2, F_IP2_3,
  F_PORT,
  F_SAVE,
  F_COUNT
};

// Parse IP string into 4 bytes
void parseIP(const char* s, uint8_t out[4]) {
  int a, b, c, d;
  if (sscanf(s, "%d.%d.%d.%d", &a, &b, &c, &d) == 4) {
    out[0] = a; out[1] = b; out[2] = c; out[3] = d;
  } else {
    out[0] = out[1] = out[2] = out[3] = 0;
  }
}

// Build IP string from 4 bytes
void buildIP(uint8_t in[4], char* out, size_t sz) {
  snprintf(out, sz, "%d.%d.%d.%d", in[0], in[1], in[2], in[3]);
}

void drawCfgScreen(CfgField field, uint8_t ip1[4], uint8_t ip2[4]) {
  M5.Lcd.fillScreen(C_BG);
  M5.Lcd.setTextSize(1);

  // Title
  M5.Lcd.setTextColor(C_ACCENT, C_BG);
  M5.Lcd.setCursor(4, 4);
  M5.Lcd.print("D.I.M  CONFIG");

  M5.Lcd.setTextColor(C_DIM, C_BG);
  M5.Lcd.setCursor(4, 18);
  M5.Lcd.print("A:dec  B:next  C:inc  HoldB:save");

  int y = 36;
  auto drawField = [&](const char* label, const char* val, CfgField f) {
    bool active = (field == f);
    M5.Lcd.setTextColor(active ? C_ACCENT : C_DIM, active ? C_HEADER : C_BG);
    char buf[64];
    snprintf(buf, sizeof(buf), " %-6s  %s ", label, val);
    M5.Lcd.setCursor(4, y);
    M5.Lcd.print(buf);
    y += 14;
  };

  drawField("SSID",   cfg.ssid,  F_SSID);
  drawField("PASS",   "****",    F_PASS);  // don't show password

  char tmp[32];
  snprintf(tmp, sizeof(tmp), "%d", ip1[0]); drawField("IP1.0", tmp, F_IP1_0);
  snprintf(tmp, sizeof(tmp), "%d", ip1[1]); drawField("IP1.1", tmp, F_IP1_1);
  snprintf(tmp, sizeof(tmp), "%d", ip1[2]); drawField("IP1.2", tmp, F_IP1_2);
  snprintf(tmp, sizeof(tmp), "%d", ip1[3]); drawField("IP1.3", tmp, F_IP1_3);
  snprintf(tmp, sizeof(tmp), "%d", ip2[0]); drawField("IP2.0", tmp, F_IP2_0);
  snprintf(tmp, sizeof(tmp), "%d", ip2[1]); drawField("IP2.1", tmp, F_IP2_1);
  snprintf(tmp, sizeof(tmp), "%d", ip2[2]); drawField("IP2.2", tmp, F_IP2_2);
  snprintf(tmp, sizeof(tmp), "%d", ip2[3]); drawField("IP2.3", tmp, F_IP2_3);
  snprintf(tmp, sizeof(tmp), "%d", cfg.port); drawField("PORT", tmp, F_PORT);

  // SAVE button
  bool saveSel = (field == F_SAVE);
  M5.Lcd.setTextColor(saveSel ? C_BG : C_GREEN, saveSel ? C_GREEN : C_BG);
  M5.Lcd.setCursor(4, y + 2);
  M5.Lcd.print(saveSel ? " >> HOLD B TO SAVE & REBOOT << " : " [ SAVE & REBOOT ]           ");

  // Footer
  M5.Lcd.setTextColor(C_DIM, C_BG);
  M5.Lcd.setCursor(0, 228);
  M5.Lcd.print("  [A] -1       [B] NEXT      [C] +1  ");
}

void runConfigScreen() {
  connected = false;

  uint8_t ip1[4], ip2[4];
  parseIP(cfg.ip1, ip1);
  parseIP(cfg.ip2, ip2);

  CfgField field = F_IP1_0;  // start on first useful field
  drawCfgScreen(field, ip1, ip2);

  unsigned long bHoldStart = 0;
  bool bHolding = false;

  while (true) {
    M5.update();
    unsigned long now = millis();

    auto getFieldVal = [&]() -> int {
      switch (field) {
        case F_IP1_0: return ip1[0]; case F_IP1_1: return ip1[1];
        case F_IP1_2: return ip1[2]; case F_IP1_3: return ip1[3];
        case F_IP2_0: return ip2[0]; case F_IP2_1: return ip2[1];
        case F_IP2_2: return ip2[2]; case F_IP2_3: return ip2[3];
        case F_PORT:  return cfg.port;
        default: return 0;
      }
    };

    auto setFieldVal = [&](int v) {
      switch (field) {
        case F_IP1_0: ip1[0] = v; break; case F_IP1_1: ip1[1] = v; break;
        case F_IP1_2: ip1[2] = v; break; case F_IP1_3: ip1[3] = v; break;
        case F_IP2_0: ip2[0] = v; break; case F_IP2_1: ip2[1] = v; break;
        case F_IP2_2: ip2[2] = v; break; case F_IP2_3: ip2[3] = v; break;
        case F_PORT:  cfg.port = (uint16_t)constrain(v, 1, 65535); break;
        default: break;
      }
    };

    // BtnA — decrement
    if (M5.BtnA.wasPressed()) {
      if (field >= F_IP1_0 && field <= F_IP2_3) {
        setFieldVal(constrain(getFieldVal() - 1, 0, 255));
      } else if (field == F_PORT) {
        cfg.port = max(1, (int)cfg.port - 1);
      } else {
        field = (CfgField)((int)field == 0 ? F_COUNT - 1 : (int)field - 1);
      }
      drawCfgScreen(field, ip1, ip2);
    }

    // BtnC — increment
    if (M5.BtnC.wasPressed()) {
      if (field >= F_IP1_0 && field <= F_IP2_3) {
        setFieldVal(constrain(getFieldVal() + 1, 0, 255));
      } else if (field == F_PORT) {
        cfg.port = min(65535, (int)cfg.port + 1);
      } else {
        field = (CfgField)(((int)field + 1) % F_COUNT);
      }
      drawCfgScreen(field, ip1, ip2);
    }

    // BtnB — next field / hold to save
    if (M5.BtnB.wasPressed()) {
      bHoldStart = now;
      bHolding = true;
      field = (CfgField)(((int)field + 1) % F_COUNT);
      drawCfgScreen(field, ip1, ip2);
    }
    if (M5.BtnB.isPressed() && bHolding && field == F_SAVE) {
      if (now - bHoldStart >= HOLD_MS) {
        // SAVE!
        buildIP(ip1, cfg.ip1, 32);
        buildIP(ip2, cfg.ip2, 32);
        saveConfig();
        drawConnecting("Config saved!\nRebooting...");
        delay(1500);
        ESP.restart();
      }
      // Show hold progress
      int pct = min(100, (int)((now - bHoldStart) * 100 / HOLD_MS));
      M5.Lcd.fillRect(0, 220, pct * 3, 4, C_GREEN);
    }
    if (M5.BtnB.wasReleased()) { bHolding = false; }

    delay(20);
  }
}

// ─────────────────────────────────────────────────────────────────────────
// DISCOVERY: Full discovery — fast-path then full scan
//
// Strategy:
//   1. If cfg.port != 0: try that port first on IP1 then IP2 (fast path,
//      avoids re-scanning when the port hasn't changed between sessions)
//   2. If fast-path fails: full scan of ports 5000–5010 on IP1 then IP2
//   On success: sets serverBase, updates cfg.port, saves to NVS.
// ─────────────────────────────────────────────────────────────────────────
bool runDiscovery() {
  const char* ips[2] = { cfg.ip1, cfg.ip2 };

  // ── Fast path: try last known port first ──────────────────────────────
  if (cfg.port != 0) {
    for (int i = 0; i < 2; i++) {
      M5.Lcd.setCursor(0, 50); M5.Lcd.setTextColor(C_DIM, C_BG);
      M5.Lcd.printf("  Fast: %s:%d", ips[i], cfg.port);
      if (tryConnect(ips[i], cfg.port)) {
        serverBase = String("http://") + ips[i] + ":" + cfg.port;
        // Port unchanged, no need to resave
        return true;
      }
    }
    // Fast path failed → port has changed, fall through to full scan
    M5.Lcd.setCursor(0, 64); M5.Lcd.setTextColor(C_DIM, C_BG);
    M5.Lcd.printf("  Port %d gone, scanning...", cfg.port);
    delay(400);
  }

  // ── Full scan: 5000–5010 on each IP ───────────────────────────────────
  for (int attempt = 0; attempt < DISCOVERY_RETRIES; attempt++) {
    uint16_t foundPort = 0;
    for (int i = 0; i < 2; i++) {
      M5.Lcd.setCursor(0, 78); M5.Lcd.setTextColor(C_DIM, C_BG);
      M5.Lcd.printf("  Scan %s ...", ips[i]);
      if (discoverServer(ips[i], &foundPort)) {
        serverBase = String("http://") + ips[i] + ":" + foundPort;
        cfg.port = foundPort;
        saveConfig();   // persist the new port
        return true;
      }
    }
    if (attempt < DISCOVERY_RETRIES - 1) {
      M5.Lcd.setCursor(0, 92); M5.Lcd.printf("  Retry %d/%d ...", attempt + 2, DISCOVERY_RETRIES);
      delay(800);
    }
  }
  return false;
}

// ─────────────────────────────────────────────────────────────────────────
// DISCOVERY: Probe one IP:port
// ─────────────────────────────────────────────────────────────────────────
bool tryConnect(const char* ip, uint16_t port) {
  HTTPClient http;
  String url = String("http://") + ip + ":" + port + "/api/esp32/state";
  http.begin(url);
  http.setTimeout(HTTP_TIMEOUT_MS);
  int code = http.GET();
  http.end();
  return (code == 200);
}

// Scan ports DISCOVERY_PORT_MIN..DISCOVERY_PORT_MAX on a given IP.
// On success, writes the found port into *foundPort and returns true.
// Shows port progress on screen.
bool discoverServer(const char* ip, uint16_t* foundPort) {
  for (uint16_t port = DISCOVERY_PORT_MIN; port <= DISCOVERY_PORT_MAX; port++) {
    // Live progress: update port number on screen
    M5.Lcd.setCursor(200, 60);
    M5.Lcd.setTextColor(C_DIM, C_BG);
    M5.Lcd.printf(":%-5d", port);

    if (tryConnect(ip, port)) {
      *foundPort = port;
      return true;
    }
  }
  return false;
}

// ─────────────────────────────────────────────────────────────────────────
// STATE FETCH
// ─────────────────────────────────────────────────────────────────────────
bool fetchState() {
  HTTPClient http;
  http.begin(serverBase + "/api/esp32/state");
  http.setTimeout(HTTP_TIMEOUT_MS);
  int code = http.GET();
  if (code != 200) { http.end(); return false; }

  String body = http.getString();
  http.end();

  StaticJsonDocument<2048> doc;
  if (deserializeJson(doc, body) != DeserializationError::Ok) return false;

  dimState.loaded  = doc["loaded"] | 0;
  if (!dimState.loaded) {
    dimState.playing = false;
    dimState.laneCount = 0;
    stateValid = true;
    return true;
  }

  dimState.playing = doc["p"] | 0;
  dimState.bpm     = doc["bpm"] | 120.0f;
  dimState.bar     = doc["bar"] | 1;
  dimState.beat    = doc["beat"] | 1;
  strlcpy(dimState.sig,     doc["sig"] | "4/4",  sizeof(dimState.sig));
  strlcpy(dimState.elapsed, doc["t"]   | "0:00", sizeof(dimState.elapsed));

  JsonArray la = doc["lanes"].as<JsonArray>();
  dimState.laneCount = min((uint8_t)la.size(), (uint8_t)8);
  for (uint8_t i = 0; i < dimState.laneCount; i++) {
    JsonObject lo = la[i];
    strlcpy(dimState.lanes[i].name,  lo["nm"]  | "",    sizeof(dimState.lanes[i].name));
    strlcpy(dimState.lanes[i].cue,   lo["cue"] | "—",   sizeof(dimState.lanes[i].cue));
    strlcpy(dimState.lanes[i].badge, lo["bdg"] | "",    sizeof(dimState.lanes[i].badge));
    dimState.lanes[i].bars    = lo["br"] | 0.0f;
    dimState.lanes[i].ended   = lo["end"] | 0;
    // Infer waiting from badge (LOOP MANUAL = waiting)
    String bdg = lo["bdg"] | "";
    dimState.lanes[i].waiting = bdg.indexOf("MAN") >= 0 || bdg.indexOf("∞") >= 0;
  }

  stateValid = true;
  return true;
}

// ─────────────────────────────────────────────────────────────────────────
// HTTP POST command (fire-and-forget)
// ─────────────────────────────────────────────────────────────────────────
void postCmd(const char* endpoint) {
  HTTPClient http;
  http.begin(serverBase + endpoint);
  http.addHeader("Content-Type", "application/json");
  http.setTimeout(HTTP_TIMEOUT_MS);
  http.POST("{}");
  http.end();
}

String httpPost(const char* path, const char* body) {
  HTTPClient http;
  http.begin(serverBase + path);
  http.addHeader("Content-Type", "application/json");
  http.setTimeout(HTTP_TIMEOUT_MS);
  int code = http.POST(body);
  String res = (code > 0) ? http.getString() : "";
  http.end();
  return res;
}

// ─────────────────────────────────────────────────────────────────────────
// DISPLAY
// ─────────────────────────────────────────────────────────────────────────
void drawConnecting(const char* msg) {
  M5.Lcd.fillScreen(C_BG);
  M5.Lcd.setTextColor(C_ACCENT, C_BG);
  M5.Lcd.setTextSize(1);
  M5.Lcd.setCursor(4, 4);
  M5.Lcd.print("D.I.M");
  M5.Lcd.setTextColor(C_TEXT, C_BG);
  M5.Lcd.setCursor(8, 30);
  M5.Lcd.print(msg);
}

void drawError(const String& msg) {
  M5.Lcd.fillScreen(C_BG);
  M5.Lcd.setTextColor(C_RED, C_BG);
  M5.Lcd.setTextSize(1);
  M5.Lcd.setCursor(4, 4);
  M5.Lcd.print("D.I.M  ERROR");
  M5.Lcd.setTextColor(C_TEXT, C_BG);
  M5.Lcd.setCursor(8, 24);
  M5.Lcd.print(msg);
}

// ── Main screen ───────────────────────────────────────────────────────────
//
// Layout 320×240:
//  [0..31]   Header  — logo | BPM | sig | bar/beat | elapsed | status
//  [32..207] Lanes   — adaptive height per lane (max 8 lanes)
//  [208..239] Footer — [A] ADVANCE  [B] ALL  [C] VETO

void drawMainScreen() {
  M5.Lcd.fillScreen(C_BG);
  drawHeader();
  drawLanes();
  drawFooter();
}

void drawHeader() {
  // Background bar
  M5.Lcd.fillRect(0, 0, 320, 32, C_HEADER);

  // Logo
  M5.Lcd.setTextColor(C_ACCENT, C_HEADER);
  M5.Lcd.setTextSize(1);
  M5.Lcd.setCursor(4, 4);
  M5.Lcd.print("D.I.M");

  // Playing indicator
  if (dimState.loaded) {
    M5.Lcd.setTextColor(dimState.playing ? C_GREEN : C_STOP, C_HEADER);
    M5.Lcd.setCursor(50, 4);
    M5.Lcd.print(dimState.playing ? "PLAY" : "STOP");
  } else {
    M5.Lcd.setTextColor(C_DIM, C_HEADER);
    M5.Lcd.setCursor(50, 4);
    M5.Lcd.print("NO PROJECT");
    return;
  }

  // BPM
  M5.Lcd.setTextColor(C_ACCENT, C_HEADER);
  M5.Lcd.setTextSize(2);
  char bpmStr[16];
  snprintf(bpmStr, sizeof(bpmStr), "%.0f", dimState.bpm);
  M5.Lcd.setCursor(100, 2);
  M5.Lcd.print(bpmStr);
  M5.Lcd.setTextSize(1);
  M5.Lcd.setTextColor(C_DIM, C_HEADER);
  M5.Lcd.setCursor(148, 8);
  M5.Lcd.print("BPM");

  // Sig
  M5.Lcd.setTextColor(C_TEXT, C_HEADER);
  M5.Lcd.setCursor(176, 4);
  M5.Lcd.print(dimState.sig);

  // Bar / beat
  char bb[16];
  snprintf(bb, sizeof(bb), "BAR %02d B%d", dimState.bar, dimState.beat);
  M5.Lcd.setCursor(210, 4);
  M5.Lcd.print(bb);

  // Elapsed (right side)
  M5.Lcd.setTextColor(C_DIM, C_HEADER);
  M5.Lcd.setCursor(284, 4);
  M5.Lcd.print(dimState.elapsed);

  // Separator line
  M5.Lcd.drawFastHLine(0, 32, 320, C_ACCENT);
}

void drawLanes() {
  if (!dimState.loaded || dimState.laneCount == 0) {
    M5.Lcd.setTextColor(C_DIM, C_BG);
    M5.Lcd.setCursor(80, 120);
    M5.Lcd.print("No project loaded.");
    return;
  }

  const int LANE_AREA_H = 176;  // 32..207
  const int laneH = LANE_AREA_H / dimState.laneCount;

  for (uint8_t i = 0; i < dimState.laneCount; i++) {
    LaneInfo& ln = dimState.lanes[i];
    int y = 33 + i * laneH;

    // Lane background (subtle alternation)
    uint16_t bg = (i % 2 == 0) ? 0x0821 : C_BG;
    M5.Lcd.fillRect(0, y, 320, laneH - 1, bg);

    // Status color
    uint16_t stColor = ln.ended ? C_DIM : (ln.waiting ? C_WAIT : (dimState.playing ? C_PLAY : C_STOP));

    // Left stripe
    M5.Lcd.fillRect(0, y, 3, laneH - 1, stColor);

    // Lane number
    M5.Lcd.setTextSize(1);
    M5.Lcd.setTextColor(C_DIM, bg);
    M5.Lcd.setCursor(6, y + 2);
    M5.Lcd.printf("%d", i + 1);

    // Lane name (up to 12 chars)
    M5.Lcd.setTextColor(C_TEXT, bg);
    M5.Lcd.setCursor(16, y + 2);
    M5.Lcd.print(ln.name);

    // Cue label (right-aligned area)
    M5.Lcd.setTextColor(C_ACCENT2, bg);
    M5.Lcd.setCursor(136, y + 2);
    M5.Lcd.print(ln.cue);

    // Badge
    if (ln.badge[0]) {
      M5.Lcd.setTextColor(ln.waiting ? C_WAIT : C_DIM, bg);
      M5.Lcd.setCursor(264, y + 2);
      M5.Lcd.print(ln.badge);
    }

    // Progress bar (bars remaining)
    if (!ln.ended && laneH >= 20) {
      int barY = y + laneH - 8;
      M5.Lcd.fillRect(0, barY, 316, 6, 0x1082);
      // Assume max ~16 bars; fill proportionally (inverse: more filled = less remaining)
      float pct = 1.0f - min(1.0f, ln.bars / 8.0f);
      int barW = (int)(316.0f * pct);
      M5.Lcd.fillRect(0, barY, barW, 6, stColor);
      // Bars remaining label
      if (laneH >= 24) {
        M5.Lcd.setTextColor(C_DIM, bg);
        char brStr[12];
        snprintf(brStr, sizeof(brStr), "%.1f", ln.bars);
        M5.Lcd.setCursor(290, barY - 10);
        M5.Lcd.print(brStr);
      }
    }

    // Separator
    M5.Lcd.drawFastHLine(0, y + laneH - 1, 320, 0x1082);
  }
}

void drawFooter() {
  M5.Lcd.fillRect(0, 208, 320, 32, C_HEADER);
  M5.Lcd.drawFastHLine(0, 208, 320, C_DIM);

  M5.Lcd.setTextSize(1);
  M5.Lcd.setTextColor(C_TEXT, C_HEADER);

  // BtnA label
  M5.Lcd.setCursor(4, 216);
  M5.Lcd.setTextColor(C_ACCENT, C_HEADER);
  M5.Lcd.print("[A]");
  M5.Lcd.setTextColor(C_TEXT, C_HEADER);
  M5.Lcd.print(" ADV");

  // BtnB label
  M5.Lcd.setCursor(108, 216);
  M5.Lcd.setTextColor(C_ACCENT, C_HEADER);
  M5.Lcd.print("[B]");
  M5.Lcd.setTextColor(C_TEXT, C_HEADER);
  M5.Lcd.print(" ALL");

  // BtnC label
  M5.Lcd.setCursor(214, 216);
  M5.Lcd.setTextColor(C_ACCENT, C_HEADER);
  M5.Lcd.print("[C]");
  M5.Lcd.setTextColor(C_TEXT, C_HEADER);
  M5.Lcd.print(" VETO");

  // Hold hints
  M5.Lcd.setTextColor(C_DIM, C_HEADER);
  M5.Lcd.setCursor(4, 228);
  M5.Lcd.print("Hold:");
  M5.Lcd.setCursor(40, 228);
  M5.Lcd.print("A=PLAY  B=REW  A+C=CFG");
}

void flashFooterLabel(uint8_t btn, const char* label) {
  // Flash the footer label for the pressed button
  int x = (btn == 0) ? 4 : (btn == 1) ? 108 : 214;
  M5.Lcd.setTextColor(C_GREEN, C_HEADER);
  M5.Lcd.setCursor(x, 216);
  M5.Lcd.print("       ");  // clear
  M5.Lcd.setCursor(x, 216);
  M5.Lcd.print(label);
  delay(300);
  drawFooter();
}
