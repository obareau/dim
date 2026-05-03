#include "DIMClient.h"

DIMClient::DIMClient() : juce::Thread("DIMClient")
{
    startThread();
}

DIMClient::~DIMClient()
{
    stopThread(2000);
}

// ─────────────────────────────────────────────────────────────────────────
// Config
// ─────────────────────────────────────────────────────────────────────────
void DIMClient::setCredentials(const juce::String& a, const juce::String& b)
{
    ip1 = a;
    ip2 = b;
    forceRediscovery();
}

void DIMClient::forceRediscovery()
{
    juce::ScopedLock sl(stateLock);
    state.connected = false;
    state.serverUrl = {};
    needsDiscovery  = true;
    failCount       = 0;
}

// ─────────────────────────────────────────────────────────────────────────
// State access
// ─────────────────────────────────────────────────────────────────────────
DIMState DIMClient::getState() const
{
    juce::ScopedLock sl(stateLock);
    return state;
}

// ─────────────────────────────────────────────────────────────────────────
// Commands
// ─────────────────────────────────────────────────────────────────────────
void DIMClient::postCommand(const juce::String& endpoint)
{
    juce::ScopedLock sl(cmdLock);
    pendingCmds.add(endpoint);
}

// ─────────────────────────────────────────────────────────────────────────
// Listeners
// ─────────────────────────────────────────────────────────────────────────
void DIMClient::addListener(Listener* l)    { listeners.add(l); }
void DIMClient::removeListener(Listener* l) { listeners.remove(l); }

void DIMClient::notifyListeners()
{
    DIMState snap = getState();
    juce::MessageManager::callAsync([this, snap]() {
        listeners.call([&snap](Listener& l) { l.dimStateChanged(snap); });
    });
}

// ─────────────────────────────────────────────────────────────────────────
// HTTP helpers
// ─────────────────────────────────────────────────────────────────────────
static juce::String httpGet(const juce::String& url, int timeoutMs = 500)
{
    juce::URL u(url);
    auto opts = juce::URL::InputStreamOptions(juce::URL::ParameterHandling::inAddress)
                    .withConnectionTimeoutMs(timeoutMs)
                    .withNumRedirectsToFollow(0);
    if (auto stream = u.createInputStream(opts))
        return stream->readEntireStreamAsString();
    return {};
}

static void httpPost(const juce::String& url, int timeoutMs = 500)
{
    juce::URL u(url);
    auto opts = juce::URL::InputStreamOptions(juce::URL::ParameterHandling::inAddress)
                    .withConnectionTimeoutMs(timeoutMs)
                    .withExtraHeaders("Content-Type: application/json")
                    .withNumRedirectsToFollow(0);
    // POST with empty body
    u.withPOSTData("{}").createInputStream(opts);
}

// ─────────────────────────────────────────────────────────────────────────
// Discovery
// ─────────────────────────────────────────────────────────────────────────
bool DIMClient::tryConnect(const juce::String& ip, int port)
{
    auto url  = "http://" + ip + ":" + juce::String(port) + "/api/esp32/state";
    auto body = httpGet(url, HTTP_TIMEOUT);
    if (body.isEmpty()) return false;

    auto json = juce::JSON::parse(body);
    if (!json.isObject()) return false;

    // Valid D.I.M response contains "p" or "loaded"
    return json.hasProperty("p") || json.hasProperty("loaded");
}

bool DIMClient::discoverServer()
{
    const juce::String ips[2] = { ip1, ip2 };

    // ── Fast path: try saved port first ──────────────────────────────────
    {
        juce::ScopedLock sl(stateLock);
        if (!state.serverUrl.isEmpty()) {
            // serverUrl already set = try it directly
            auto body = httpGet(state.serverUrl + "/api/esp32/state", HTTP_TIMEOUT);
            if (body.isNotEmpty()) return true;  // still alive
            state.serverUrl = {};  // stale, fall through to full scan
        }
    }

    // ── Full port scan 5000–5010 ──────────────────────────────────────────
    for (const auto& ip : ips) {
        if (ip.isEmpty()) continue;
        for (int port = PORT_MIN; port <= PORT_MAX; port++) {
            if (threadShouldExit()) return false;
            if (tryConnect(ip, port)) {
                juce::ScopedLock sl(stateLock);
                state.serverUrl = "http://" + ip + ":" + juce::String(port);
                state.connected = true;
                needsDiscovery  = false;
                failCount       = 0;
                DBG("DIMClient: found server at " << state.serverUrl);
                return true;
            }
        }
    }
    return false;
}

// ─────────────────────────────────────────────────────────────────────────
// State parsing
// ─────────────────────────────────────────────────────────────────────────
void DIMClient::parseState(const juce::String& jsonStr)
{
    auto json = juce::JSON::parse(jsonStr);
    if (!json.isObject()) return;

    juce::ScopedLock sl(stateLock);

    state.loaded = (int)json["loaded"] != 0 || json.hasProperty("p");

    if (!state.loaded) {
        state.playing = false;
        state.lanes.clear();
        return;
    }

    state.playing = (int)json["p"] != 0;
    state.bpm     = (float)json["bpm"];
    state.bar     = (int)json["bar"];
    state.beat    = (int)json["beat"];
    state.sig     = json["sig"].toString();
    state.elapsed = json["t"].toString();

    state.lanes.clear();
    if (auto* arr = json["lanes"].getArray()) {
        for (const auto& lo : *arr) {
            DIMState::Lane lane;
            lane.id    = lo["id"].toString();
            lane.name  = lo["nm"].toString();
            lane.cue   = lo["cue"].toString();
            lane.badge = lo["bdg"].toString();
            lane.bars  = (float)lo["br"];
            lane.ended = (int)lo["end"] != 0;
            // Infer waiting from badge
            lane.waiting = lane.badge.containsIgnoreCase("MAN")
                        || lane.badge.contains("∞");
            state.lanes.push_back(lane);
        }
    }
}

// ─────────────────────────────────────────────────────────────────────────
// Fetch one state update
// ─────────────────────────────────────────────────────────────────────────
bool DIMClient::fetchOnce()
{
    juce::String serverUrl;
    {
        juce::ScopedLock sl(stateLock);
        serverUrl = state.serverUrl;
    }
    if (serverUrl.isEmpty()) return false;

    auto body = httpGet(serverUrl + "/api/esp32/state", HTTP_TIMEOUT);
    if (body.isEmpty()) return false;

    DIMState prev = getState();
    parseState(body);
    DIMState next = getState();

    // Only notify if something changed
    if (next.playing  != prev.playing  ||
        next.bpm      != prev.bpm      ||
        next.bar      != prev.bar      ||
        next.beat     != prev.beat     ||
        next.lanes.size() != prev.lanes.size() ||
        next.elapsed  != prev.elapsed)
    {
        notifyListeners();
    }
    return true;
}

// ─────────────────────────────────────────────────────────────────────────
// Background thread
// ─────────────────────────────────────────────────────────────────────────
void DIMClient::run()
{
    while (!threadShouldExit())
    {
        // ── Drain command queue ───────────────────────────────────────────
        juce::StringArray cmds;
        {
            juce::ScopedLock sl(cmdLock);
            cmds.swapWith(pendingCmds);
        }
        for (const auto& ep : cmds) {
            juce::String url;
            { juce::ScopedLock sl(stateLock); url = state.serverUrl; }
            if (url.isNotEmpty())
                httpPost(url + ep, HTTP_TIMEOUT);
        }

        // ── Discovery if needed ───────────────────────────────────────────
        if (needsDiscovery || state.serverUrl.isEmpty()) {
            if (!discoverServer()) {
                {
                    juce::ScopedLock sl(stateLock);
                    state.connected = false;
                }
                notifyListeners();
                wait(2000);  // wait longer between discovery attempts
                continue;
            }
            notifyListeners();
        }

        // ── Poll ──────────────────────────────────────────────────────────
        if (!fetchOnce()) {
            failCount++;
            if (failCount >= MAX_FAILS) {
                DBG("DIMClient: lost server, re-discovering...");
                forceRediscovery();
            }
        } else {
            failCount = 0;
        }

        wait(POLL_MS);
    }
}
