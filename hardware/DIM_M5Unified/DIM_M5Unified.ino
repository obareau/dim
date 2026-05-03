/**
 * D.I.M — M5Stack controller (unified)
 * ─────────────────────────────────────────────────────────────────────────
 * Targets : M5Stack Core · Core2 · StickC Plus  (auto-détecté)
 * Libs    : M5Unified 0.2.x  +  ArduinoJson 7.x
 *
 * Boutons (Core / Core2)
 *   BtnA        = Advance (première lane en attente)
 *   BtnB        = Advance ALL
 *   BtnC        = Veto prochain JUMP
 *   Hold A 2 s  = Play / Pause
 *   Hold B 2 s  = Rewind
 *
 * Boutons (StickC Plus)
 *   BtnA        = Advance
 *   Hold A 2 s  = Play / Pause
 *   BtnB        = cycle : Advance ALL → Veto → Rewind
 *
 * WiFi auto-discovery : fast-path (NVS) → scan ports 5000–5010 / IP1 puis IP2
 * Config screen  : maintenir A+B au boot (Core/Core2) ou A (StickC)
 *   → édite SSID · PASS · IP1 · IP2  caractère par caractère
 * ─────────────────────────────────────────────────────────────────────────
 */

#include <M5Unified.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>      // v7.x
#include <Preferences.h>

// ── Compile-time defaults (écrasés par NVS après 1ère config) ─────────────
#define DEFAULT_SSID  "Augustine-free"
#define DEFAULT_PASS  "14031972"
#define DEFAULT_IP1   "192.168.1.28"
#define DEFAULT_IP2   "192.168.1.1"

#define POLL_MS           200
#define HTTP_TIMEOUT_MS   400
#define PORT_MIN          5000
#define PORT_MAX          5010
#define HOLD_MS           2000UL
#define MAX_FAIL          15

// ── NVS ──────────────────────────────────────────────────────────────────
Preferences prefs;
struct Config {
  char     ssid[64], pass[64];
  char     ip1[32],  ip2[32];
  uint16_t port;
};
Config cfg;

void loadCfg() {
  prefs.begin("dim", true);
  strlcpy(cfg.ssid, prefs.getString("ssid", DEFAULT_SSID).c_str(), 64);
  strlcpy(cfg.pass, prefs.getString("pass", DEFAULT_PASS).c_str(), 64);
  strlcpy(cfg.ip1,  prefs.getString("ip1",  DEFAULT_IP1 ).c_str(), 32);
  strlcpy(cfg.ip2,  prefs.getString("ip2",  DEFAULT_IP2 ).c_str(), 32);
  cfg.port = prefs.getUShort("port", 0);
  prefs.end();
}
void saveCfg() {
  prefs.begin("dim", false);
  prefs.putString("ssid", cfg.ssid);
  prefs.putString("pass", cfg.pass);
  prefs.putString("ip1",  cfg.ip1);
  prefs.putString("ip2",  cfg.ip2);
  prefs.putUShort("port", cfg.port);
  prefs.end();
}

// ── Runtime state ─────────────────────────────────────────────────────────
String serverBase;
bool   connected = false;
int    failCount = 0;

struct Lane {
  String name, cue, badge;
  float  bars;
  bool   ended, waiting;
};
struct DimState {
  bool   loaded  = false, playing = false;
  float  bpm     = 120.0f;
  int    bar     = 1, beat = 1;
  String sig     = "4/4", elapsed = "0:00";
  Lane   lanes[8];
  int    laneCount = 0;
};
DimState state, prev;

// ── Screen geometry ───────────────────────────────────────────────────────
int  SW, SH;
bool smallScreen;   // true = StickC Plus (largeur ≤ 160 px)

// ── Colors ────────────────────────────────────────────────────────────────
#define C_BG     0x0A0A0A
#define C_HDR    0x1A1A1A
#define C_ACCENT 0xE8C830
#define C_BLUE   0x55AAFF
#define C_TEXT   0xCCCCCC
#define C_DIM    0x555555
#define C_GREEN  0x00DD55
#define C_ORANGE 0xFF8800
#define C_RED    0xFF3344
#define C_GREY   0x333333

// ── Hold tracking ─────────────────────────────────────────────────────────
unsigned long holdA = 0, holdB = 0;
bool firedA = false, firedB = false;
uint8_t stickCycle = 0;

// ─────────────────────────────────────────────────────────────────────────
// HELPERS
// ─────────────────────────────────────────────────────────────────────────
void drawMsg(const String& msg, uint32_t col = C_TEXT) {
  M5.Display.fillScreen(C_BG);
  M5.Display.setTextSize(2);
  M5.Display.setTextColor(C_ACCENT, C_BG);
  M5.Display.setCursor(4, 4);
  M5.Display.print("D.I.M");
  M5.Display.setTextColor(col, C_BG);
  M5.Display.setCursor(4, 28);
  M5.Display.print(msg);
}

// ─────────────────────────────────────────────────────────────────────────
// NETWORK — Discovery
// ─────────────────────────────────────────────────────────────────────────
bool tryPort(const char* ip, uint16_t port) {
  HTTPClient h;
  String url = String("http://") + ip + ":" + port + "/api/esp32/state";
  h.begin(url);
  h.setTimeout(HTTP_TIMEOUT_MS);
  int code = h.GET();
  h.end();
  return code == 200;
}

bool discoverIP(const char* ip, uint16_t* found) {
  for (uint16_t p = PORT_MIN; p <= PORT_MAX; p++) {
    M5.Display.setTextSize(1);
    M5.Display.setTextColor(C_DIM, C_BG);
    M5.Display.setCursor(4, smallScreen ? 80 : 100);
    M5.Display.printf(":%d  ", p);
    if (tryPort(ip, p)) { *found = p; return true; }
  }
  return false;
}

bool runDiscovery() {
  const char* ips[2] = { cfg.ip1, cfg.ip2 };

  // Fast-path : dernier port connu en NVS
  if (cfg.port) {
    for (int i = 0; i < 2; i++) {
      if (tryPort(ips[i], cfg.port)) {
        serverBase = String("http://") + ips[i] + ":" + cfg.port;
        return true;
      }
    }
    // Port sauvegardé ne répond plus → scan complet
    M5.Display.setTextSize(1);
    M5.Display.setTextColor(C_ORANGE, C_BG);
    M5.Display.setCursor(4, 80);
    M5.Display.printf("Port %d absent, scan...", cfg.port);
  }

  // Scan complet 5000-5010
  for (int retry = 0; retry < 2; retry++) {
    uint16_t found = 0;
    for (int i = 0; i < 2; i++) {
      M5.Display.setTextSize(1);
      M5.Display.setTextColor(C_DIM, C_BG);
      M5.Display.setCursor(4, 65);
      M5.Display.printf("Scan %s   ", ips[i]);
      if (discoverIP(ips[i], &found)) {
        serverBase = String("http://") + ips[i] + ":" + found;
        cfg.port   = found;
        saveCfg();
        return true;
      }
    }
    delay(600);
  }
  return false;
}

// ─────────────────────────────────────────────────────────────────────────
// NETWORK — HTTP
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

  state.loaded = (int)(doc["loaded"] | 0) != 0;
  if (!state.loaded) {
    state.playing   = false;
    state.laneCount = 0;
    return true;
  }

  state.playing = (int)(doc["p"]   | 0) != 0;
  state.bpm     = doc["bpm"]  | 120.0f;
  state.bar     = doc["bar"]  | 1;
  state.beat    = doc["beat"] | 1;
  state.sig     = (const char*)(doc["sig"]  | "4/4");
  state.elapsed = (const char*)(doc["t"]    | "0:00");

  JsonArray la = doc["lanes"].as<JsonArray>();
  state.laneCount = min((int)la.size(), 8);
  for (int i = 0; i < state.laneCount; i++) {
    JsonObject lo = la[i];
    state.lanes[i].name    = (const char*)(lo["nm"]  | "");
    state.lanes[i].cue     = (const char*)(lo["cue"] | "—");
    state.lanes[i].badge   = (const char*)(lo["bdg"] | "");
    state.lanes[i].bars    = lo["br"]  | 0.0f;
    state.lanes[i].ended   = (int)(lo["end"] | 0) != 0;
    String bdg = state.lanes[i].badge;
    state.lanes[i].waiting = bdg.indexOf("MAN") >= 0 || bdg.indexOf("INF") >= 0;
  }
  return true;
}

// ─────────────────────────────────────────────────────────────────────────
// DISPLAY
// ─────────────────────────────────────────────────────────────────────────
void drawHeader() {
  int hh = smallScreen ? 32 : 42;
  M5.Display.fillRect(0, 0, SW, hh, C_HDR);
  M5.Display.drawFastHLine(0, hh, SW, C_ACCENT);

  M5.Display.setTextSize(2);
  M5.Display.setTextColor(C_ACCENT, C_HDR);
  M5.Display.setCursor(2, 2);
  M5.Display.print("D.I.M");

  if (!state.loaded) {
    M5.Display.setTextColor(C_DIM, C_HDR);
    M5.Display.setCursor(66, 6);
    M5.Display.print("no project");
    return;
  }

  // PLAY / STOP badge
  M5.Display.setTextColor(state.playing ? C_GREEN : C_GREY, C_HDR);
  M5.Display.setCursor(66, 6);
  M5.Display.print(state.playing ? "PLAY" : "STOP");

  if (!smallScreen) {
    // BPM en grand
    M5.Display.setTextSize(3);
    M5.Display.setTextColor(C_ACCENT, C_HDR);
    M5.Display.setCursor(128, 2);
    M5.Display.printf("%.0f", state.bpm);
    // Labels
    M5.Display.setTextSize(1);
    M5.Display.setTextColor(C_DIM, C_HDR);
    M5.Display.setCursor(196, 8);
    M5.Display.print("BPM");
    // Sig + Bar.Beat + elapsed
    M5.Display.setTextSize(2);
    M5.Display.setTextColor(C_TEXT, C_HDR);
    M5.Display.setCursor(224, 2);
    M5.Display.print(state.sig);
    M5.Display.setCursor(278, 2);
    M5.Display.printf("B%02d", state.bar);
    M5.Display.setTextSize(1);
    M5.Display.setTextColor(C_DIM, C_HDR);
    M5.Display.setCursor(SW - 32, 28);
    M5.Display.print(state.elapsed);
  } else {
    // StickC : tout sur 2 lignes
    M5.Display.setTextSize(2);
    M5.Display.setTextColor(C_ACCENT, C_HDR);
    M5.Display.setCursor(2, 16);
    M5.Display.printf("%.0f", state.bpm);
    M5.Display.setTextSize(1);
    M5.Display.setTextColor(C_TEXT, C_HDR);
    M5.Display.setCursor(46, 20);
    M5.Display.printf("B%02d.%d %s", state.bar, state.beat, state.elapsed.c_str());
  }
}

void drawLanes() {
  int hh = smallScreen ? 32 : 42;
  int fh = smallScreen ? 16 : 22;
  int lStart = hh + 2;
  int lEnd   = SH - fh;
  int avail  = lEnd - lStart;
  int n      = max(1, state.laneCount);
  int rowH   = avail / n;

  if (!state.loaded || state.laneCount == 0) {
    M5.Display.setTextSize(2);
    M5.Display.setTextColor(C_DIM, C_BG);
    M5.Display.setCursor(4, lStart + avail / 2 - 8);
    M5.Display.print("No project");
    return;
  }

  for (int i = 0; i < state.laneCount; i++) {
    Lane& ln = state.lanes[i];
    int y = lStart + i * rowH;

    uint32_t bg = (i % 2 == 0) ? 0x111111 : C_BG;
    M5.Display.fillRect(0, y, SW, rowH - 1, bg);

    // Stripe colorée à gauche
    uint32_t sc = ln.ended   ? C_GREY
                : ln.waiting ? C_ORANGE
                : state.playing ? C_GREEN
                : C_GREY;
    M5.Display.fillRect(0, y, 4, rowH - 1, sc);

    M5.Display.setTextSize(2);

    // Numéro lane
    M5.Display.setTextColor(C_DIM, bg);
    M5.Display.setCursor(6, y + 4);
    M5.Display.printf("%d", i + 1);

    // Nom lane
    M5.Display.setTextColor(ln.waiting ? C_ORANGE : C_TEXT, bg);
    M5.Display.setCursor(22, y + 4);
    int nameLen = smallScreen ? 5 : 9;
    M5.Display.print(ln.name.substring(0, nameLen));

    if (!smallScreen) {
      // Cue label
      M5.Display.setTextColor(C_BLUE, bg);
      M5.Display.setCursor(100, y + 4);
      M5.Display.print(ln.cue.substring(0, 10));

      // Badge (MAN / INF / etc.)
      if (ln.badge.length()) {
        M5.Display.setTextColor(ln.waiting ? C_ORANGE : C_DIM, bg);
        M5.Display.setCursor(SW - 54, y + 4);
        M5.Display.print(ln.badge.substring(0, 5));
      }
    } else {
      M5.Display.setTextColor(C_BLUE, bg);
      M5.Display.setCursor(64, y + 4);
      M5.Display.print(ln.cue.substring(0, 6));
    }

    // Barre de progression (si rowH assez grand)
    if (!ln.ended && rowH >= 24) {
      int pbY = y + rowH - 5;
      M5.Display.fillRect(4, pbY, SW - 4, 4, C_GREY);
      float pct = 1.f - min(1.f, ln.bars / 8.f);
      M5.Display.fillRect(4, pbY, (int)((SW - 4) * pct), 4, sc);
    }

    M5.Display.drawFastHLine(0, y + rowH - 1, SW, C_GREY);
  }
}

void drawFooter() {
  int fh = smallScreen ? 16 : 22;
  int y  = SH - fh;
  M5.Display.fillRect(0, y, SW, fh, C_HDR);
  M5.Display.drawFastHLine(0, y, SW, C_DIM);
  M5.Display.setTextSize(1);
  M5.Display.setTextColor(C_DIM, C_HDR);

  if (smallScreen) {
    const char* labels[] = { "ALL", "VTO", "REW" };
    M5.Display.setCursor(2, y + 4);
    M5.Display.printf("[A]ADV [B]%s", labels[stickCycle % 3]);
  } else {
    M5.Display.setCursor(2, y + 5);
    M5.Display.print("[A]ADV [B]ALL [C]VTO | holdA=PLAY holdB=REW");
  }
}

void drawAll() {
  M5.Display.fillScreen(C_BG);
  drawHeader();
  drawLanes();
  drawFooter();
}

// ─────────────────────────────────────────────────────────────────────────
// CONFIG SCREEN — SSID · PASS · IP1 · IP2 · SAVE
// ─────────────────────────────────────────────────────────────────────────
// Charset pour SSID / mot de passe
static const char CHARSET[] =
  " !\"#$%&'()*+,-./0123456789:;<=>?@"
  "ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_`"
  "abcdefghijklmnopqrstuvwxyz{|}~";
static const int CHARSET_LEN = sizeof(CHARSET) - 1;

int charIdx(char c) {
  for (int i = 0; i < CHARSET_LEN; i++) if (CHARSET[i] == c) return i;
  return 0;
}

// Édite une chaîne char par char avec les boutons.
// Core/Core2 : A=prev · C=next · B=avance curseur · holdB@fin=valider
// StickC      : A=avance curseur · B=prev/next (toggle) · holdA@fin=valider
void editString(char* buf, int maxLen, const char* title, bool hidden = false) {
  int len = strlen(buf);
  int cur = len > 0 ? 0 : 0;   // curseur sur premier char
  if (len == 0) { buf[0] = CHARSET[0]; buf[1] = 0; len = 1; }

  unsigned long bHold = 0;
  bool bDir = true;  // StickC : B toggle direction

  auto redraw = [&]() {
    M5.Display.fillScreen(C_BG);
    M5.Display.setTextSize(2);
    M5.Display.setTextColor(C_ACCENT, C_BG);
    M5.Display.setCursor(2, 2);
    M5.Display.print(title);
    M5.Display.drawFastHLine(0, 22, SW, C_ACCENT);

    // Contenu
    M5.Display.setTextSize(2);
    M5.Display.setCursor(2, 30);
    M5.Display.setTextColor(C_TEXT, C_BG);
    String disp = "";
    for (int i = 0; i < len; i++) disp += (hidden && i != cur) ? '*' : buf[i];
    M5.Display.print(disp);

    // Curseur souligné
    int cx = 2 + cur * 12;
    M5.Display.drawFastHLine(cx, 48, 12, C_ACCENT);

    // Longueur / aide
    M5.Display.setTextSize(1);
    M5.Display.setTextColor(C_DIM, C_BG);
    M5.Display.setCursor(2, 60);
    if (!smallScreen)
      M5.Display.print("A:prev C:next B:cur>  holdB fin=BACK/SAVE");
    else
      M5.Display.print("B:+/-  A:cur>  holdA fin");
    M5.Display.setCursor(2, 72);
    M5.Display.printf("len=%d  cur=%d", len, cur);
  };
  redraw();

  while (true) {
    M5.update();
    unsigned long now = millis();

    if (!smallScreen) {
      // ── Core / Core2 ────────────────────────────────────────────────
      if (M5.BtnA.wasPressed()) {
        int idx = charIdx(buf[cur]);
        buf[cur] = CHARSET[(idx - 1 + CHARSET_LEN) % CHARSET_LEN];
        redraw();
      }
      if (M5.BtnC.wasPressed()) {
        int idx = charIdx(buf[cur]);
        buf[cur] = CHARSET[(idx + 1) % CHARSET_LEN];
        redraw();
      }
      if (M5.BtnB.wasPressed()) {
        bHold = now;
        cur++;
        if (cur >= len && len < maxLen - 1) {
          buf[len] = CHARSET[0]; buf[len + 1] = 0; len++;
        }
        if (cur >= len) cur = len - 1;
        redraw();
      }
      if (M5.BtnB.isPressed() && cur == len - 1 && now - bHold > HOLD_MS) {
        // Trim trailing spaces
        while (len > 0 && buf[len - 1] == ' ') { buf[--len] = 0; }
        return;
      }
      // Progress bar sur hold
      if (M5.BtnB.isPressed() && cur == len - 1) {
        int pct = min(100UL, (now - bHold) * 100 / HOLD_MS);
        M5.Display.fillRect(0, SH - 4, pct * SW / 100, 4, C_GREEN);
      }
    } else {
      // ── StickC Plus ──────────────────────────────────────────────────
      if (M5.BtnB.wasPressed()) {
        int idx = charIdx(buf[cur]);
        buf[cur] = CHARSET[(idx + (bDir ? 1 : -1) + CHARSET_LEN) % CHARSET_LEN];
        bDir = !bDir;
        redraw();
      }
      if (M5.BtnA.wasPressed()) {
        bHold = now;
        cur++;
        if (cur >= len && len < maxLen - 1) {
          buf[len] = CHARSET[0]; buf[len + 1] = 0; len++;
        }
        if (cur >= len) cur = len - 1;
        redraw();
      }
      if (M5.BtnA.isPressed() && cur == len - 1 && now - bHold > HOLD_MS) {
        while (len > 0 && buf[len - 1] == ' ') { buf[--len] = 0; }
        return;
      }
    }
    delay(20);
  }
}

// ─────────────────────────────────────────────────────────────────────────
// CONFIG SCREEN — menu principal
// ─────────────────────────────────────────────────────────────────────────
void runConfigScreen() {
  connected = false;

  uint8_t ip1[4], ip2[4];
  auto parseIP = [](const char* s, uint8_t out[4]) {
    int a, b, c, d;
    if (sscanf(s, "%d.%d.%d.%d", &a, &b, &c, &d) == 4)
      { out[0]=a; out[1]=b; out[2]=c; out[3]=d; }
    else { out[0]=out[1]=out[2]=out[3]=0; }
  };
  auto buildIP = [](uint8_t in[4], char* out, int sz) {
    snprintf(out, sz, "%d.%d.%d.%d", in[0], in[1], in[2], in[3]);
  };
  parseIP(cfg.ip1, ip1);
  parseIP(cfg.ip2, ip2);

  // Menu : 0=SSID 1=PASS 2=IP1 3=IP2 4=SAVE
  int sel = 0;

  auto drawMenu = [&]() {
    M5.Display.fillScreen(C_BG);
    M5.Display.setTextSize(2);
    M5.Display.setTextColor(C_ACCENT, C_BG);
    M5.Display.setCursor(2, 2);
    M5.Display.print("D.I.M CONFIG");
    M5.Display.drawFastHLine(0, 22, SW, C_ACCENT);

    const char* items[] = { "SSID", "PASS", "IP1", "IP2", "SAVE & REBOOT" };
    const char* values[] = { cfg.ssid, "***", cfg.ip1, cfg.ip2, "" };
    char ip1s[32], ip2s[32];
    buildIP(ip1, ip1s, 32); buildIP(ip2, ip2s, 32);
    values[2] = ip1s; values[3] = ip2s;

    for (int i = 0; i < 5; i++) {
      bool active = (sel == i);
      uint32_t bg2 = active ? C_HDR : C_BG;
      M5.Display.fillRect(0, 28 + i * 22, SW, 20, bg2);
      M5.Display.setTextColor(active ? C_ACCENT : C_TEXT, bg2);
      M5.Display.setTextSize(active ? 2 : 1);
      M5.Display.setCursor(4, 30 + i * 22);
      if (i < 4)
        M5.Display.printf("%-5s %s", items[i], values[i]);
      else
        M5.Display.print(items[i]);
    }
    M5.Display.setTextSize(1);
    M5.Display.setTextColor(C_DIM, C_BG);
    M5.Display.setCursor(2, SH - 12);
    if (!smallScreen)
      M5.Display.print("[A]up  [C]down  [B]select");
    else
      M5.Display.print("[A]select  [B]next");
  };
  drawMenu();

  unsigned long bHold = 0;

  while (true) {
    M5.update();
    unsigned long now = millis();

    if (!smallScreen) {
      // Core/Core2 : A=haut C=bas B=sélectionner
      if (M5.BtnA.wasPressed()) { sel = (sel - 1 + 5) % 5; drawMenu(); }
      if (M5.BtnC.wasPressed()) { sel = (sel + 1) % 5;      drawMenu(); }
      if (M5.BtnB.wasPressed()) {
        if (sel == 0) { editString(cfg.ssid, 64, "SSID", false); drawMenu(); }
        else if (sel == 1) { editString(cfg.pass, 64, "PASS", true); drawMenu(); }
        else if (sel == 2) {
          // Édit IP1 octet par octet
          for (int f = 0; f < 4; f++) {
            // Réutilise logique simple
            M5.Display.fillScreen(C_BG);
            M5.Display.setTextSize(2);
            M5.Display.setTextColor(C_ACCENT, C_BG);
            M5.Display.setCursor(2, 2);
            M5.Display.printf("IP1.%d", f);
            M5.Display.setCursor(2, 30);
            M5.Display.setTextColor(C_TEXT, C_BG);
            M5.Display.printf("%d", ip1[f]);
            M5.Display.setTextSize(1);
            M5.Display.setTextColor(C_DIM, C_BG);
            M5.Display.setCursor(2, 60);
            M5.Display.print("[A]- [C]+ [B]next");
            bool done = false;
            while (!done) {
              M5.update();
              if (M5.BtnA.wasPressed()) {
                ip1[f] = (ip1[f] == 0) ? 255 : ip1[f] - 1;
                M5.Display.fillRect(2, 30, SW - 2, 24, C_BG);
                M5.Display.setTextSize(2); M5.Display.setTextColor(C_TEXT, C_BG);
                M5.Display.setCursor(2, 30); M5.Display.printf("%d  ", ip1[f]);
              }
              if (M5.BtnC.wasPressed()) {
                ip1[f] = (ip1[f] == 255) ? 0 : ip1[f] + 1;
                M5.Display.fillRect(2, 30, SW - 2, 24, C_BG);
                M5.Display.setTextSize(2); M5.Display.setTextColor(C_TEXT, C_BG);
                M5.Display.setCursor(2, 30); M5.Display.printf("%d  ", ip1[f]);
              }
              if (M5.BtnB.wasPressed()) done = true;
              delay(20);
            }
          }
          buildIP(ip1, cfg.ip1, 32); drawMenu();
        }
        else if (sel == 3) {
          for (int f = 0; f < 4; f++) {
            M5.Display.fillScreen(C_BG);
            M5.Display.setTextSize(2);
            M5.Display.setTextColor(C_ACCENT, C_BG);
            M5.Display.setCursor(2, 2); M5.Display.printf("IP2.%d", f);
            M5.Display.setCursor(2, 30);
            M5.Display.setTextColor(C_TEXT, C_BG); M5.Display.printf("%d", ip2[f]);
            M5.Display.setTextSize(1); M5.Display.setTextColor(C_DIM, C_BG);
            M5.Display.setCursor(2, 60); M5.Display.print("[A]- [C]+ [B]next");
            bool done = false;
            while (!done) {
              M5.update();
              if (M5.BtnA.wasPressed()) {
                ip2[f] = (ip2[f] == 0) ? 255 : ip2[f] - 1;
                M5.Display.fillRect(2, 30, SW - 2, 24, C_BG);
                M5.Display.setTextSize(2); M5.Display.setTextColor(C_TEXT, C_BG);
                M5.Display.setCursor(2, 30); M5.Display.printf("%d  ", ip2[f]);
              }
              if (M5.BtnC.wasPressed()) {
                ip2[f] = (ip2[f] == 255) ? 0 : ip2[f] + 1;
                M5.Display.fillRect(2, 30, SW - 2, 24, C_BG);
                M5.Display.setTextSize(2); M5.Display.setTextColor(C_TEXT, C_BG);
                M5.Display.setCursor(2, 30); M5.Display.printf("%d  ", ip2[f]);
              }
              if (M5.BtnB.wasPressed()) done = true;
              delay(20);
            }
          }
          buildIP(ip2, cfg.ip2, 32); drawMenu();
        }
        else if (sel == 4) {
          buildIP(ip1, cfg.ip1, 32);
          buildIP(ip2, cfg.ip2, 32);
          saveCfg();
          drawMsg("Sauvegardé!\nReboot...", C_GREEN);
          delay(1500);
          ESP.restart();
        }
      }
    } else {
      // StickC Plus : A=select B=next
      if (M5.BtnB.wasPressed()) { sel = (sel + 1) % 5; drawMenu(); }
      if (M5.BtnA.wasPressed()) {
        bHold = now;
        // Même logique simplifiée (saut direct dans editString pour SSID/PASS)
        if (sel == 0) { editString(cfg.ssid, 64, "SSID", false); drawMenu(); }
        else if (sel == 1) { editString(cfg.pass, 64, "PASS", true); drawMenu(); }
        else if (sel == 4) {
          buildIP(ip1, cfg.ip1, 32); buildIP(ip2, cfg.ip2, 32);
          saveCfg(); drawMsg("Sauvegardé!", C_GREEN); delay(1500); ESP.restart();
        }
        // IP editing on StickC : B=+1 A=cursor  (simplified)
        // TODO : même boucle octet que Core
      }
    }
    delay(20);
  }
}

// ═════════════════════════════════════════════════════════════════════════
// SETUP
// ═════════════════════════════════════════════════════════════════════════
void setup() {
  auto mcfg = M5.config();
  M5.begin(mcfg);

  SW = M5.Display.width();
  SH = M5.Display.height();
  smallScreen = (SW <= 160 || SH <= 160);
  M5.Display.setRotation(1);
  SW = M5.Display.width();
  SH = M5.Display.height();

  M5.Display.fillScreen(C_BG);
  M5.Display.setTextColor(C_TEXT, C_BG);

  loadCfg();

  // Config screen si A+B tenus au boot (Core/Core2) ou A (StickC)
  M5.update();
  bool forceConfig = smallScreen
    ? M5.BtnA.isPressed()
    : (M5.BtnA.isPressed() && M5.BtnB.isPressed());
  if (forceConfig) runConfigScreen();

  // WiFi
  drawMsg("WiFi: " + String(cfg.ssid));
  WiFi.mode(WIFI_STA);
  WiFi.begin(cfg.ssid, cfg.pass);
  unsigned long t0 = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - t0 < 15000) {
    delay(300);
    M5.Display.print(".");
  }
  if (WiFi.status() != WL_CONNECTED) {
    drawMsg("WiFi FAIL!\nSSID: " + String(cfg.ssid) + "\nConfig: hold A+B", C_RED);
    delay(5000);
    runConfigScreen();
    return;
  }

  drawMsg("Scan serveur...");
  if (!runDiscovery()) {
    drawMsg(String("Introuvable!\n") + cfg.ip1 + "\n" + cfg.ip2
            + "\nports " + PORT_MIN + "-" + PORT_MAX, C_RED);
    delay(5000);
    runConfigScreen();
    return;
  }

  connected = true;
  drawMsg("OK: " + serverBase, C_GREEN);
  delay(600);
  drawAll();
}

// ═════════════════════════════════════════════════════════════════════════
// LOOP
// ═════════════════════════════════════════════════════════════════════════
void loop() {
  if (!connected) { delay(1000); return; }
  M5.update();
  unsigned long now = millis();

  if (smallScreen) {
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
      if (failCount == 5)
        drawMsg("Injoignable:\n" + serverBase, C_ORANGE);
      if (failCount >= MAX_FAIL) {
        failCount = 0; connected = false;
        drawMsg("Re-scan...");
        if (runDiscovery()) { connected = true; drawAll(); }
        else delay(3000);
      }
    }
  }
}
