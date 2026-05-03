#pragma once
#include <JuceHeader.h>
#include <vector>
#include <functional>

// ─────────────────────────────────────────────────────────────────────────
// DIMClient — background thread that polls /api/esp32/state
// Thread-safe: getState() may be called from any thread.
// Listeners are called on the message thread.
// ─────────────────────────────────────────────────────────────────────────

struct DIMState {
    bool loaded  = false;
    bool playing = false;
    float bpm    = 120.f;
    int   bar    = 1;
    int   beat   = 1;
    juce::String sig     = "4/4";
    juce::String elapsed = "0:00";

    struct Lane {
        juce::String id, name, cue, badge;
        float bars   = 0.f;
        bool  ended   = false;
        bool  waiting = false;
    };
    std::vector<Lane> lanes;

    // Connection info
    juce::String serverUrl;   // e.g. "http://192.168.1.100:5003"
    bool connected = false;
};

// ─────────────────────────────────────────────────────────────────────────
class DIMClient : private juce::Thread
{
public:
    DIMClient();
    ~DIMClient() override;

    // ── Config ────────────────────────────────────────────────────────────
    void setCredentials(const juce::String& ip1, const juce::String& ip2);
    void forceRediscovery();

    // ── Commands (fire-and-forget, non-blocking) ──────────────────────────
    void postCommand(const juce::String& endpoint);  // e.g. "/api/cmd/advance"

    // ── State (thread-safe) ───────────────────────────────────────────────
    DIMState getState() const;

    // ── Listener — called on message thread ──────────────────────────────
    struct Listener {
        virtual ~Listener() = default;
        virtual void dimStateChanged(const DIMState&) = 0;
    };
    void addListener   (Listener* l);
    void removeListener(Listener* l);

private:
    void run() override;

    bool discoverServer();
    bool tryConnect(const juce::String& ip, int port);
    bool fetchOnce();
    void parseState(const juce::String& json);

    void notifyListeners();

    // ── State ─────────────────────────────────────────────────────────────
    mutable juce::CriticalSection stateLock;
    DIMState state;

    juce::String ip1 { "192.168.1.100" };
    juce::String ip2 { "192.168.1.1"   };

    int  failCount      = 0;
    bool needsDiscovery = true;

    // Commands queue (posted from UI thread, consumed in bg thread)
    juce::CriticalSection cmdLock;
    juce::StringArray      pendingCmds;

    juce::ListenerList<Listener> listeners;

    static constexpr int POLL_MS        = 200;
    static constexpr int HTTP_TIMEOUT   = 500;
    static constexpr int PORT_MIN       = 5000;
    static constexpr int PORT_MAX       = 5010;
    static constexpr int MAX_FAILS      = 15;   // ~3 s before re-discovery
};
