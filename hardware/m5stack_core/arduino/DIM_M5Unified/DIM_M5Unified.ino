/**
 * D.I.M — M5Stack controller (unified)
 * ─────────────────────────────────────────────────────────────────────────
 * Fonctionne sur : M5Stack Core · Core2 · StickC Plus (auto-détecté)
 * Library        : M5Unified 0.2.x + ArduinoJson 7.x
 * Board (IDE)    : M5Core / M5Core2 / M5StickCPlus (selon la cible)
 *
 * Boutons
 *   Core / Core2   : BtnA = Advance · BtnB = All · BtnC = Veto
 *                    Hold A (2 s) = Play/Pause · Hold B (2 s) = Rewind
 *   StickC Plus    : BtnA = Advance / Hold = Play · BtnB = cycle (All→Veto→Rew)
 *
 * WiFi auto-discovery : fast-path (NVS) → scan ports 5000–5010 sur IP1 puis IP2
 * Config screen       : A+B maintenus au boot (ou A maintenu sur StickC)
 * ─────────────────────────────────────────────────────────────────────────
 */

#include <M5Unified.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>        // v7.x
#include <Preferences.h>

// ── Compile-time defaults ─────────────────────────────────────────────────
#define DEFAULT_WIFI_SSID   "YourSSID"
#define DEFAULT_WIFI_PASS   "YourPassword"
#define DEFAULT_IP1         "192.168.1.100"
#define DEFAULT_IP2         "192.168.1.1"

#define POLL_MS             200
#define HTTP_TIMEOUT_MS     400
#define PORT_MIN            5000
#define PORT_MAX            5010
#define HOLD_MS             2000UL
#define MAX_FAIL            15

// ── NVS ──────────────────────────────────────────────────────────────────
Preferences prefs;
struct Config { char ssid[64], pass[64], ip1[32], ip2[32]; uint16_t port; };
Config cfg;

// ── State ─────────────────────────────────────────────────────────────────
String serverBase;
bool   connected = false;
int    failCount = 0;

struct Lane { String name, cue, badge; float bars; bool ended, waiting; };
struct DimState {
  bool playing = false, loaded = false;
  float bpm = 120;
  int   bar = 1, beat = 1;
  String sig = "4/4", elapsed = "0:00";
  Lane  lanes[8]; int laneCount = 0;
};
DimState state, prev;
bool stateValid = false;

// ── Screen geometry (auto-sized) ──────────────────────────────────────────
int SW, SH;        // screen width / height
bool smallScreen;  // true = StickC Plus (135 px wide)

// ── Colors (M5GFX 24-bit) ─────────────────────────────────────────────────
#define C_BG      0x0A0A0A
#define C_HEADER  0x1A1A1A
#define C_ACCENT  0xE8C830
#define C_BLUE    0x55AAFF
#define C_TEXT    0xCCCCCC
#define C_DIM     0x555555
#define C_GREEN   0x00DD55
#define C_ORANGE  0xFF8800
#define C_RED     0xFF3344
#define C_GREY    0x333333

// ── Hold tracking ─────────────────────────────────────────────────────────
unsigned long holdA = 0, holdB = 0;
bool firedA = false, firedB = false;

// ── StickC cycle state ────────────────────────────────────────────────────
uint8_t stickCycle = 0;   // 0=All 1=Veto 2=Rew

// ── Forward decl ─────────────────────────────────────────────────────────
void loadCfg(); void saveCfg();
bool runDiscovery();
bool tryPort(const char* ip, uint16_t port);
bool discoverIP(const char* ip, uint16_t* found);
bool fetchState();
void postCmd(const String& ep);
void drawAll();
void drawHeader();
void drawLanes();
void drawFooter();
void runConfigScreen();
void drawMsg(const String& msg, uint32_t col = C_TEXT);

// ─────────────────────────────────────────────────────────────────────────
// SETUP
// ─────────────────────────────────────────────────────────────────────────
void setup() {
  auto mcfg = M5.config();
  M5.begin(mcfg);

  SW = M5.Display.width();
  SH = M5.Display.height();
  smallScreen = (SW <= 160 || SH <= 160);

  M5.Display.setRotation(smallScreen ? 1 : 1);  // landscape on both
  SW = M5.Display.width();
  SH = M5.Display.height();

  M5.Display.fillScreen(C_BG);
  M5.Display.setTextColor(C_TEXT, C_BG);
  M5.Display.setTextSize(1);

  loadCfg();

  // ── Hold A+B (or just A on StickC) at boot → config screen ────────────
  M5.update();
  bool forceConfig = smallScreen ? M5.BtnA.isPressed()
                                 : (M5.BtnA.isPressed() && M5.BtnB.isPressed());
  if (forceConfig) { runConfigScreen(); }

  // ── WiFi ──────────────────────────────────────────────────────────────
  drawMsg("WiFi: " + String(cfg.ssid));
  WiFi.mode(WIFI_STA);
  WiFi.begin(cfg.ssid, cfg.pass);
  unsigned long t0 = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - t0 < 15000) {
    delay(300); M5.Display.print(".");
  }
  if (WiFi.status() != WL_CONNECTED) {
    drawMsg("WiFi FAIL\nCheck SSID/pass", C_RED);
    delay(4000);
    runConfigScreen();
    return;
  }

  // ── Discovery ─────────────────────────────────────────────────────────
  drawMsg("Scanning server...");
  if (!runDiscovery()) {
    drawMsg("Server not found!\n" + String(cfg.ip1) + "\n" + String(cfg.ip2)
            + "\nports " + PORT_MIN + "-" + PORT_MAX, C_RED);
    delay(5000);
    runConfigScreen();
    return;
  }

  connected = true;
  drawMsg("OK: " + serverBase, C_GREEN);
  delay(600);
  M5.Display.fillScreen(C_BG);
  drawAll();
}

// ─────────────────────────────────────────────────────────────────────────
// LOOP
// ─────────────────────────────────────────────────────────────────────────
void loop() {
  if (!connected) { delay(1000); return; }
  M5.update();

  unsigned long now = millis();

  if (smallScreen) {
    // ── StickC Plus: 2 buttons ──────────────────────────────────────────
    if (M5.BtnA.wasPressed()) { postCmd("/api/cmd/advance"); holdA = now; firedA = false; }
    if (M5.BtnA.isPressed() && !firedA && now - holdA > HOLD_MS) {
      firedA = true; postCmd("/api/cmd/play_toggle");
    }
    if (M5.BtnB.wasPressed()) {
      const char* cmds[] = { "/api/cmd/advance_all", "/api/cmd/veto", "/api/cmd/rewind" };
      postCmd(cmds[stickCycle % 3]);
      stickCycle++;
    }
  } else {
    // ── Core / Core2: 3 buttons ─────────────────────────────────────────
    if (M5.BtnA.wasPressed()) { postCmd("/api/cmd/advance");     holdA = now; firedA = false; }
    if (M5.BtnB.wasPressed()) { postCmd("/api/cmd/advance_all"); holdB = now; firedB = false; }
    if (M5.BtnC.wasPressed()) { postCmd("/api/cmd/veto"); }

    if (M5.BtnA.isPressed() && !firedA && now - holdA > HOLD_MS) {
      firedA = true; postCmd("/api/cmd/play_toggle");
    }
    if (M5.BtnB.isPressed() && !firedB && now - holdB > HOLD_MS) {
      firedB = true; postCmd("/api/cmd/rewind");
    }
  }

  // ── Poll ────────────────────────────────────────────────────────────
  static unsigned long lastPoll = 0;
  if (now - lastPoll >= POLL_MS) {
    lastPoll = now;
    if (fetchState()) {
      failCount = 0;
      if (memcmp(&state, &prev, sizeof(DimState))) {
        drawAll();
        memcpy(&prev, &state, sizeof(DimState));
      }
    } else {
      failCount++;
      if (failCount == 5)  drawMsg("Server unreachable\n" + serverBase + "\nRetrying...", C_ORANGE);
      if (failCount >= MAX_FAIL) {
        failCount = 0; connected = false;
        drawMsg("Re-scanning...");
        if (runDiscovery()) { connected = true; drawAll(); }
        else delay(3000);
      }
    }
  }
}

// ─────────────────────────────────────────────────────────────────────────
// NVS Config
// ─────────────────────────────────────────────────────────────────────────
void loadCfg() {
  prefs.begin("dim", true);
  strlcpy(cfg.ssid, prefs.getString("ssid", DEFAULT_WIFI_SSID).c_str(), 64);
  strlcpy(cfg.pass, prefs.getString("pass", DEFAULT_WIFI_PASS).c_str(), 64);
  strlcpy(cfg.ip1,  prefs.getString("ip1",  DEFAULT_IP1).c_str(), 32);
  strlcpy(cfg.ip2,  prefs.getString("ip2",  DEFAULT_IP2).c_str(), 32);
  cfg.port = prefs.getUShort("port", 0);
  prefs.end();
}
void saveCfg() {
  prefs.begin("dim", false);
  prefs.putString("ssid", cfg.ssid); prefs.putString("pass", cfg.pass);
  prefs.putString("ip1",  cfg.ip1);  prefs.putString("ip2",  cfg.ip2);
  prefs.putUShort("port", cfg.port);
  prefs.end();
}

// ─────────────────────────────────────────────────────────────────────────
// Discovery
// ─────────────────────────────────────────────────────────────────────────
bool tryPort(const char* ip, uint16_t port) {
  HTTPClient h;
  h.begin("http://" + String(ip) + ":" + port + "/api/esp32/state");
  h.setTimeout(HTTP_TIMEOUT_MS);
  int code = h.GET();
  h.end();
  return code == 200;
}

bool discoverIP(const char* ip, uint16_t* found) {
  for (uint16_t p = PORT_MIN; p <= PORT_MAX; p++) {
    M5.Display.setCursor(smallScreen ? 0 : 4, smallScreen ? 60 : 80);
    M5.Display.setTextColor(C_DIM, C_BG);
    M5.Display.printf(":%d  ", p);
    if (tryPort(ip, p)) { *found = p; return true; }
  }
  return false;
}

bool runDiscovery() {
  const char* ips[2] = { cfg.ip1, cfg.ip2 };

  // Fast-path: try last known port
  if (cfg.port) {
    for (int i = 0; i < 2; i++) {
      if (tryPort(ips[i], cfg.port)) {
        serverBase = "http://" + String(ips[i]) + ":" + cfg.port;
        return true;
      }
    }
  }

  // Full scan
  for (int retry = 0; retry < 2; retry++) {
    uint16_t found = 0;
    for (int i = 0; i < 2; i++) {
      M5.Display.setCursor(0, 50);
      M5.Display.setTextColor(C_DIM, C_BG);
      M5.Display.printf("Scan %s ", ips[i]);
      if (discoverIP(ips[i], &found)) {
        serverBase = "http://" + String(ips[i]) + ":" + found;
        cfg.port = found;
        saveCfg();
        return true;
      }
    }
    delay(600);
  }
  return false;
}

// ─────────────────────────────────────────────────────────────────────────
// HTTP
// ─────────────────────────────────────────────────────────────────────────
void postCmd(const String& ep) {
  HTTPClient h;
  h.begin(serverBase + ep);
  h.addHeader("Content-Type", "application/json");
  h.setTimeout(HTTP_TIMEOUT_MS);
  h.POST("{}");
  h.end();
}

bool fetchState() {
  HTTPClient h;
  h.begin(serverBase + "/api/esp32/state");
  h.setTimeout(HTTP_TIMEOUT_MS);
  if (h.GET() != 200) { h.end(); return false; }
  String body = h.getString();
  h.end();

  JsonDocument doc;
  if (deserializeJson(doc, body)) return false;

  state.loaded  = doc["loaded"] | 0;
  if (!state.loaded) { state.playing = false; state.laneCount = 0; return true; }

  state.playing = (int)(doc["p"] | 0);
  state.bpm     = doc["bpm"] | 120.0f;
  state.bar     = doc["bar"] | 1;
  state.beat    = doc["beat"] | 1;
  state.sig     = doc["sig"] | "4/4";
  state.elapsed = doc["t"] | "0:00";

  JsonArray la = doc["lanes"].as<JsonArray>();
  state.laneCount = min((int)la.size(), 8);
  for (int i = 0; i < state.laneCount; i++) {
    JsonObject lo = la[i];
    state.lanes[i] = {
      lo["nm"]  | "",
      lo["cue"] | "—",
      lo["bdg"] | "",
      lo["br"]  | 0.0f,
      (int)(lo["end"] | 0) != 0,
      false
    };
    String bdg = state.lanes[i].badge;
    state.lanes[i].waiting = bdg.indexOf("MAN") >= 0 || bdg.indexOf("INF") >= 0;
  }
  return true;
}

// ─────────────────────────────────────────────────────────────────────────
// DISPLAY — adaptive layout (320×240 ou 135×240)
// ─────────────────────────────────────────────────────────────────────────
void drawMsg(const String& msg, uint32_t col) {
  M5.Display.fillScreen(C_BG);
  M5.Display.setTextColor(C_ACCENT, C_BG);
  M5.Display.setTextSize(1);
  M5.Display.setCursor(4, 4); M5.Display.print("D.I.M");
  M5.Display.setTextColor(col, C_BG);
  M5.Display.setCursor(4, 20); M5.Display.print(msg);
}

void drawAll() {
  M5.Display.fillScreen(C_BG);
  drawHeader();
  const int FOOTER_H = smallScreen ? 14 : 20;
  const int HEADER_H = smallScreen ? 28 : 36;
  int lanesY = HEADER_H + (smallScreen ? 10 : 14);
  int lanesH = SH - lanesY - FOOTER_H;

  drawLanes();
  drawFooter();
}

void drawHeader() {
  int hh = smallScreen ? 28 : 36;
  M5.Display.fillRect(0, 0, SW, hh, C_HEADER);
  M5.Display.drawFastHLine(0, hh, SW, C_ACCENT);

  M5.Display.setTextSize(1);
  M5.Display.setTextColor(C_ACCENT, C_HEADER);
  M5.Display.setCursor(2, 2);
  M5.Display.print("D.I.M");

  if (!state.loaded) {
    M5.Display.setTextColor(C_DIM, C_HEADER);
    M5.Display.setCursor(44, 2);
    M5.Display.print("no project");
    return;
  }

  // Status
  M5.Display.setTextColor(state.playing ? C_GREEN : C_GREY, C_HEADER);
  M5.Display.setCursor(44, 2);
  M5.Display.print(state.playing ? "PLAY" : "STOP");

  // BPM
  M5.Display.setTextColor(C_ACCENT, C_HEADER);
  if (!smallScreen) {
    M5.Display.setTextSize(2);
    M5.Display.setCursor(86, 2);
    M5.Display.printf("%.0f", state.bpm);
    M5.Display.setTextSize(1);
    M5.Display.setTextColor(C_DIM, C_HEADER);
    M5.Display.setCursor(130, 8); M5.Display.print("BPM");
    M5.Display.setTextColor(C_TEXT, C_HEADER);
    M5.Display.setCursor(158, 4); M5.Display.print(state.sig);
    M5.Display.setCursor(192, 4);
    M5.Display.printf("B%02d.%d", state.bar, state.beat);
    M5.Display.setTextColor(C_DIM, C_HEADER);
    M5.Display.setCursor(SW - 36, 4); M5.Display.print(state.elapsed);
  } else {
    M5.Display.setCursor(86, 2);
    M5.Display.printf("%.0fBPM", state.bpm);
    M5.Display.setTextColor(C_TEXT, C_HEADER);
    M5.Display.setCursor(2, 14);
    M5.Display.printf("%s B%02d.%d %s", state.sig.c_str(), state.bar, state.beat, state.elapsed.c_str());
  }
}

void drawLanes() {
  int hh = smallScreen ? 28 : 36;
  int fh = smallScreen ? 14 : 20;
  int lStart = hh + 1;
  int lEnd   = SH - fh;
  int avail  = lEnd - lStart;
  int n = max(1, state.laneCount);
  int rowH = avail / n;

  M5.Display.setTextSize(1);
  if (!state.loaded || state.laneCount == 0) {
    M5.Display.setTextColor(C_DIM, C_BG);
    M5.Display.setCursor(4, lStart + avail / 2 - 4);
    M5.Display.print("No project");
    return;
  }

  for (int i = 0; i < state.laneCount; i++) {
    Lane& ln = state.lanes[i];
    int y = lStart + i * rowH;

    // Row bg
    uint32_t bg = (i % 2 == 0) ? 0x101010 : C_BG;
    M5.Display.fillRect(0, y, SW, rowH - 1, bg);

    // Status stripe
    uint32_t sc = ln.ended ? C_GREY : ln.waiting ? C_ORANGE
                : state.playing ? C_GREEN : C_GREY;
    M5.Display.fillRect(0, y, 3, rowH - 1, sc);

    M5.Display.setTextColor(C_DIM, bg);
    M5.Display.setCursor(5, y + 2);
    M5.Display.printf("%d", i + 1);

    M5.Display.setTextColor(C_TEXT, bg);
    M5.Display.setCursor(15, y + 2);
    int nameLen = smallScreen ? 7 : 10;
    M5.Display.print(ln.name.substring(0, nameLen));

    if (!smallScreen) {
      M5.Display.setTextColor(C_BLUE, bg);
      M5.Display.setCursor(96, y + 2);
      M5.Display.print(ln.cue.substring(0, 14));
      if (ln.badge.length()) {
        M5.Display.setTextColor(ln.waiting ? C_ORANGE : C_DIM, bg);
        M5.Display.setCursor(216, y + 2);
        M5.Display.print(ln.badge.substring(0, 6));
      }
    } else {
      // Small: show cue after name
      M5.Display.setTextColor(C_BLUE, bg);
      M5.Display.setCursor(62, y + 2);
      M5.Display.print(ln.cue.substring(0, 9));
    }

    // Bars remaining
    if (!ln.ended && rowH >= 16) {
      M5.Display.setTextColor(C_DIM, bg);
      M5.Display.setCursor(SW - 28, y + 2);
      M5.Display.printf("%.1f", ln.bars);
      // Progress bar
      int pbY = y + rowH - 4;
      M5.Display.fillRect(3, pbY, SW - 3, 3, C_GREY);
      float pct = 1.f - min(1.f, ln.bars / 8.f);
      M5.Display.fillRect(3, pbY, (int)((SW - 3) * pct), 3, sc);
    }

    M5.Display.drawFastHLine(0, y + rowH - 1, SW, C_GREY);
  }
}

void drawFooter() {
  int fh = smallScreen ? 14 : 20;
  int y  = SH - fh;
  M5.Display.fillRect(0, y, SW, fh, C_HEADER);
  M5.Display.drawFastHLine(0, y, SW, C_DIM);
  M5.Display.setTextColor(C_DIM, C_HEADER);
  M5.Display.setTextSize(1);

  if (smallScreen) {
    M5.Display.setCursor(2, y + 3);
    M5.Display.print("[A]ADV [B]");
    const char* labels[] = { "ALL", "VTO", "REW" };
    M5.Display.setTextColor(C_ACCENT, C_HEADER);
    M5.Display.print(labels[stickCycle % 3]);
  } else {
    M5.Display.setCursor(2, y + 4);
    M5.Display.print("[A]ADV  [B]ALL  [C]VTO | hold A=PLAY  B=REW");
  }
}

// ─────────────────────────────────────────────────────────────────────────
// CONFIG SCREEN — A+B hold au boot (Core/Core2)  ou  A hold (StickC)
// Édite IP1 octet par octet (A = -, BtnC/B = +, B/BtnA = next)
// Hold B 2s sur [SAVE] = sauvegarde et reboot
// ─────────────────────────────────────────────────────────────────────────
void runConfigScreen() {
  connected = false;

  uint8_t ip1[4], ip2[4];
  auto parseIP = [](const char* s, uint8_t out[4]) {
    int a,b,c,d;
    if (sscanf(s,"%d.%d.%d.%d",&a,&b,&c,&d)==4){out[0]=a;out[1]=b;out[2]=c;out[3]=d;}
    else {out[0]=out[1]=out[2]=out[3]=0;}
  };
  auto buildIP = [](uint8_t in[4], char* out, int sz) {
    snprintf(out,sz,"%d.%d.%d.%d",in[0],in[1],in[2],in[3]);
  };

  parseIP(cfg.ip1, ip1); parseIP(cfg.ip2, ip2);

  // Fields: 0-3 = ip1 octets, 4-7 = ip2 octets, 8 = SAVE
  int field = 0;

  auto getVal = [&]() -> int {
    if (field < 4) return ip1[field];
    if (field < 8) return ip2[field-4];
    return -1;
  };
  auto setVal = [&](int v) {
    if (field < 4) ip1[field] = constrain(v, 0, 255);
    else if (field < 8) ip2[field-4] = constrain(v, 0, 255);
  };

  auto drawCfg = [&]() {
    M5.Display.fillScreen(C_BG);
    M5.Display.setTextColor(C_ACCENT, C_BG);
    M5.Display.setCursor(2, 2); M5.Display.print("D.I.M CONFIG");
    M5.Display.setTextColor(C_DIM, C_BG);
    int tw = smallScreen ? SW : SW;
    if (!smallScreen) {
      M5.Display.setCursor(2, 14); M5.Display.print("A:- | C:+ | B:next | holdB=save");
    } else {
      M5.Display.setCursor(2, 14); M5.Display.print("A:- | B:+/next | holdA=save");
    }

    auto drawField = [&](int f, const char* label, const char* val, int y) {
      bool active = (field == f);
      M5.Display.setTextColor(active ? C_ACCENT : C_DIM, active ? C_HEADER : C_BG);
      if (active) M5.Display.fillRect(0, y, SW, 12, C_HEADER);
      M5.Display.setCursor(2, y);
      M5.Display.printf("%-5s %s", label, val);
    };

    char tmp[8];
    int y0 = 28;
    int step = smallScreen ? 11 : 13;
    for (int i = 0; i < 4; i++) {
      snprintf(tmp, sizeof(tmp), "%d", ip1[i]);
      char lbl[8]; snprintf(lbl,8,"IP1.%d",i);
      drawField(i, lbl, tmp, y0 + i*step);
    }
    for (int i = 0; i < 4; i++) {
      snprintf(tmp, sizeof(tmp), "%d", ip2[i]);
      char lbl[8]; snprintf(lbl,8,"IP2.%d",i);
      drawField(i+4, lbl, tmp, y0 + (i+4)*step);
    }
    bool saveSel = (field == 8);
    M5.Display.setTextColor(saveSel ? C_BG : C_GREEN, saveSel ? C_GREEN : C_BG);
    M5.Display.setCursor(2, y0 + 8*step);
    M5.Display.print(saveSel ? ">SAVE<" : "SAVE");
  };

  drawCfg();

  unsigned long bHoldStart = 0;

  while (true) {
    M5.update();
    unsigned long now = millis();

    if (!smallScreen) {
      // Core/Core2: A=-, C=+, B=next
      if (M5.BtnA.wasPressed()) { setVal(getVal()-1); drawCfg(); }
      if (M5.BtnC.wasPressed()) { setVal(getVal()+1); drawCfg(); }
      if (M5.BtnB.wasPressed()) {
        field = (field + 1) % 9; bHoldStart = now; drawCfg();
      }
      if (M5.BtnB.isPressed() && field == 8 && now - bHoldStart > HOLD_MS) {
        buildIP(ip1, cfg.ip1, 32); buildIP(ip2, cfg.ip2, 32);
        saveCfg();
        drawMsg("Saved! Rebooting...", C_GREEN); delay(1500); ESP.restart();
      }
      // Progress bar for save
      if (M5.BtnB.isPressed() && field == 8) {
        int pct = min(100UL, (now - bHoldStart) * 100 / HOLD_MS);
        M5.Display.fillRect(0, SH-4, pct * SW / 100, 4, C_GREEN);
      }
    } else {
      // StickC Plus: A=decrement+hold=save, B=increment+next
      if (M5.BtnA.wasPressed()) { holdA = now; firedA = false; setVal(getVal()-1); drawCfg(); }
      if (M5.BtnA.isPressed() && !firedA && now - holdA > HOLD_MS && field == 8) {
        firedA = true;
        buildIP(ip1, cfg.ip1, 32); buildIP(ip2, cfg.ip2, 32);
        saveCfg(); drawMsg("Saved!", C_GREEN); delay(1500); ESP.restart();
      }
      if (M5.BtnB.wasPressed()) {
        if (getVal() >= 0) { setVal(getVal()+1); }
        field = (field + 1) % 9; drawCfg();
      }
    }
    delay(20);
  }
}
