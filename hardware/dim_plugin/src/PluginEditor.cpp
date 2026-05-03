#include "PluginEditor.h"

using namespace DIMColors;

// ─────────────────────────────────────────────────────────────────────────
// Constructor / Destructor
// ─────────────────────────────────────────────────────────────────────────
DIMEditor::DIMEditor(DIMProcessor& p)
    : AudioProcessorEditor(p), proc_(p)
{
    setSize(520, 340);
    setResizable(true, false);
    setResizeLimits(400, 260, 900, 700);

    // ── Wire buttons ──────────────────────────────────────────────────────
    btnPlay.onClick    = [this] { proc_.getClient().postCommand("/api/cmd/play_toggle"); };
    btnStop.onClick    = [this] { proc_.getClient().postCommand("/api/cmd/rewind"); };
    btnRewind.onClick  = [this] { proc_.getClient().postCommand("/api/cmd/rewind"); };
    btnAdvance.onClick = [this] { proc_.getClient().postCommand("/api/cmd/advance"); };
    btnAll.onClick     = [this] { proc_.getClient().postCommand("/api/cmd/advance_all"); };
    btnVeto.onClick    = [this] { proc_.getClient().postCommand("/api/cmd/veto"); };
    btnScan.onClick    = [this] { proc_.getClient().forceRediscovery(); };
    btnConfig.onClick  = [this] { showConfigOverlay(); };

    addAndMakeVisible(btnPlay);
    addAndMakeVisible(btnStop);
    addAndMakeVisible(btnRewind);
    addAndMakeVisible(btnAdvance);
    addAndMakeVisible(btnAll);
    addAndMakeVisible(btnVeto);
    addAndMakeVisible(btnScan);
    addAndMakeVisible(btnConfig);

    proc_.getClient().addListener(this);
    state_ = proc_.getClient().getState();

    startTimerHz(5);  // 5 Hz repaint timer (state arrives via listener)
}

DIMEditor::~DIMEditor()
{
    proc_.getClient().removeListener(this);
    stopTimer();
}

// ─────────────────────────────────────────────────────────────────────────
// Listener callback (message thread)
// ─────────────────────────────────────────────────────────────────────────
void DIMEditor::dimStateChanged(const DIMState& s)
{
    state_ = s;
    repaint();
}

void DIMEditor::timerCallback()
{
    // Expire flash messages
    if (flashMsg_.isNotEmpty() && juce::Time::getCurrentTime() > flashUntil_) {
        flashMsg_ = {};
        repaint();
    }
}

// ─────────────────────────────────────────────────────────────────────────
// Layout
// ─────────────────────────────────────────────────────────────────────────
void DIMEditor::resized()
{
    auto b = getLocalBounds();

    const int HEADER_H    = 36;
    const int SERVERBAR_H = 24;
    const int FOOTER_H    = 44;

    auto header    = b.removeFromTop(HEADER_H);
    auto serverBar = b.removeFromTop(SERVERBAR_H);
    auto footer    = b.removeFromBottom(FOOTER_H);
    // b is now the lanes area — no component to position, painted directly

    // Footer buttons
    auto fb = footer.reduced(4, 4);
    int bw = fb.getWidth() / 6 - 2;
    btnPlay   .setBounds(fb.removeFromLeft(bw).reduced(1, 0));
    btnStop   .setBounds(fb.removeFromLeft(bw).reduced(1, 0));
    btnRewind .setBounds(fb.removeFromLeft(bw).reduced(1, 0));
    btnAdvance.setBounds(fb.removeFromLeft(bw).reduced(1, 0));
    btnAll    .setBounds(fb.removeFromLeft(bw).reduced(1, 0));
    btnVeto   .setBounds(fb.removeFromLeft(bw).reduced(1, 0));

    // Server bar: SCAN + CONFIG on right
    auto sb = serverBar.reduced(4, 2);
    btnConfig.setBounds(sb.removeFromRight(22).reduced(0, 2));
    sb.removeFromRight(2);
    btnScan  .setBounds(sb.removeFromRight(42).reduced(0, 2));

    // Config overlay fills whole editor
    if (configOverlay_)
        configOverlay_->setBounds(getLocalBounds());
}

// ─────────────────────────────────────────────────────────────────────────
// Paint
// ─────────────────────────────────────────────────────────────────────────
void DIMEditor::paint(juce::Graphics& g)
{
    g.fillAll(BG);

    auto b = getLocalBounds();
    const int HEADER_H    = 36;
    const int SERVERBAR_H = 24;
    const int FOOTER_H    = 44;

    auto headerR    = b.removeFromTop(HEADER_H);
    auto serverBarR = b.removeFromTop(SERVERBAR_H);
    auto footerR    = b.removeFromBottom(FOOTER_H);
    auto lanesR     = b;

    paintHeader   (g, headerR);
    paintServerBar(g, serverBarR);
    paintLanes    (g, lanesR);
    paintFooter   (g, footerR);
}

// ─────────────────────────────────────────────────────────────────────────
// Header
// ─────────────────────────────────────────────────────────────────────────
void DIMEditor::paintHeader(juce::Graphics& g, juce::Rectangle<int> r)
{
    g.setColour(HEADER);
    g.fillRect(r);
    g.setColour(ACCENT);
    g.drawLine(r.getX(), r.getBottom(), r.getRight(), r.getBottom(), 1.f);

    auto row = r.reduced(8, 0);

    // Logo
    g.setFont(juce::Font("Courier New", 13.f, juce::Font::bold));
    g.setColour(ACCENT);
    g.drawText("D.I.M", row.removeFromLeft(40), juce::Justification::centredLeft);

    // Status badge
    bool playing   = state_.playing;
    bool connected = state_.connected;
    juce::String statusTxt = !connected ? "NO SERVER"
                           : !state_.loaded ? "NO PROJECT"
                           : playing ? "PLAY" : "STOP";
    juce::Colour statusCol = !connected ? RED
                           : !state_.loaded ? DIM_C
                           : playing ? GREEN : GREY;

    auto statusBox = row.removeFromLeft(72);
    g.setColour(statusCol.withAlpha(0.15f));
    g.fillRoundedRectangle(statusBox.reduced(2, 6).toFloat(), 2.f);
    g.setColour(statusCol);
    g.setFont(juce::Font("Courier New", 10.f, juce::Font::plain));
    g.drawText(statusTxt, statusBox, juce::Justification::centred);

    if (!state_.loaded) return;

    // BPM — large
    row.removeFromLeft(4);
    g.setFont(juce::Font("Courier New", 20.f, juce::Font::bold));
    g.setColour(ACCENT);
    g.drawText(juce::String(state_.bpm, 1), row.removeFromLeft(60),
               juce::Justification::centredLeft);
    g.setFont(juce::Font("Courier New", 9.f, juce::Font::plain));
    g.setColour(DIM_C);
    g.drawText("BPM", row.removeFromLeft(24), juce::Justification::centredLeft);

    // Sig
    g.setFont(juce::Font("Courier New", 11.f, juce::Font::plain));
    g.setColour(TEXT);
    g.drawText(state_.sig, row.removeFromLeft(30), juce::Justification::centred);

    // Bar / Beat
    g.setColour(TEXT);
    g.drawText("BAR " + juce::String(state_.bar).paddedLeft('0', 2)
               + "  B" + juce::String(state_.beat),
               row.removeFromLeft(80), juce::Justification::centred);

    // Elapsed — right side
    g.setColour(DIM_C);
    g.drawText(state_.elapsed, r.removeFromRight(46).reduced(4, 0),
               juce::Justification::centredRight);
}

// ─────────────────────────────────────────────────────────────────────────
// Server bar
// ─────────────────────────────────────────────────────────────────────────
void DIMEditor::paintServerBar(juce::Graphics& g, juce::Rectangle<int> r)
{
    g.setColour(PANEL);
    g.fillRect(r);
    g.setColour(BORDER);
    g.drawLine(r.getX(), r.getBottom(), r.getRight(), r.getBottom(), 1.f);

    auto row = r.reduced(8, 0);
    row.removeFromRight(70);  // leave space for buttons

    g.setFont(juce::Font("Courier New", 9.f, juce::Font::plain));

    if (!state_.connected) {
        g.setColour(RED.withAlpha(0.8f));
        g.drawText("Scanning " + proc_.getIP1() + " / " + proc_.getIP2()
                   + "  ports 5000–5010...", row, juce::Justification::centredLeft);
    } else {
        g.setColour(DIM_C);
        g.drawText("▶ " + state_.serverUrl, row, juce::Justification::centredLeft);
    }

    // Flash message overlay
    if (flashMsg_.isNotEmpty()) {
        g.setColour(ACCENT);
        g.drawText(flashMsg_, row, juce::Justification::centredRight);
    }
}

// ─────────────────────────────────────────────────────────────────────────
// Lanes
// ─────────────────────────────────────────────────────────────────────────
void DIMEditor::paintLanes(juce::Graphics& g, juce::Rectangle<int> r)
{
    g.setColour(BG);
    g.fillRect(r);

    if (!state_.loaded || state_.lanes.empty()) {
        g.setFont(juce::Font("Courier New", 11.f, juce::Font::plain));
        g.setColour(DIM_C);
        g.drawText("No project loaded.", r, juce::Justification::centred);
        return;
    }

    int n = (int)state_.lanes.size();
    int rowH = r.getHeight() / n;

    for (int i = 0; i < n; i++) {
        auto row = r.withHeight(rowH).withY(r.getY() + i * rowH);
        paintLaneRow(g, row, state_.lanes[i], i, state_.playing);
    }
}

void DIMEditor::paintLaneRow(juce::Graphics& g, juce::Rectangle<int> r,
                              const DIMState::Lane& lane, int idx, bool playing)
{
    // Background (subtle alternation)
    g.setColour(idx % 2 == 0 ? HEADER.withAlpha(0.4f) : BG);
    g.fillRect(r);

    // Status color
    juce::Colour stCol = lane.ended   ? GREY
                       : lane.waiting ? ORANGE
                       : playing      ? GREEN
                       :                GREY;

    // Left accent stripe
    g.setColour(stCol);
    g.fillRect(r.withWidth(3));

    // Separator
    g.setColour(BORDER);
    g.drawLine(r.getX(), r.getBottom(), r.getRight(), r.getBottom(), 1.f);

    auto inner = r.withTrimmedLeft(8).reduced(0, 2);
    int  mid   = inner.getCentreY();

    g.setFont(juce::Font("Courier New", 9.f, juce::Font::plain));

    // Lane index
    g.setColour(DIM_C);
    g.drawText(juce::String(idx + 1), inner.removeFromLeft(14),
               juce::Justification::centredLeft);

    // Lane name (up to 12 chars)
    g.setFont(juce::Font("Courier New", 10.f, juce::Font::plain));
    g.setColour(TEXT);
    g.drawText(lane.name.substring(0, 12).toUpperCase(),
               inner.removeFromLeft(90), juce::Justification::centredLeft);

    // Cue label
    g.setColour(ACCENT2);
    g.drawText(lane.cue.substring(0, 18),
               inner.removeFromLeft(130), juce::Justification::centredLeft);

    // Badge
    if (lane.badge.isNotEmpty()) {
        g.setColour(lane.waiting ? ORANGE : DIM_C);
        g.drawText("[" + lane.badge + "]",
                   inner.removeFromLeft(80), juce::Justification::centredLeft);
    }

    // Bars remaining
    if (!lane.ended) {
        auto barArea = inner.removeFromRight(50);
        g.setFont(juce::Font("Courier New", 9.f, juce::Font::plain));
        g.setColour(DIM_C);
        g.drawText(juce::String(lane.bars, 1) + " br", barArea,
                   juce::Justification::centredRight);

        // Progress bar
        if (r.getHeight() > 20) {
            auto pb = juce::Rectangle<int>(r.getX() + 3, r.getBottom() - 4,
                                           r.getWidth() - 3, 3);
            g.setColour(BORDER);
            g.fillRect(pb);
            float pct = 1.f - juce::jmin(1.f, lane.bars / 8.f);
            g.setColour(stCol.withAlpha(0.7f));
            g.fillRect(pb.withWidth((int)(pb.getWidth() * pct)));
        }
    }
}

// ─────────────────────────────────────────────────────────────────────────
// Footer (buttons are components, we just paint the background + labels)
// ─────────────────────────────────────────────────────────────────────────
void DIMEditor::paintFooter(juce::Graphics& g, juce::Rectangle<int> r)
{
    g.setColour(HEADER);
    g.fillRect(r);
    g.setColour(ACCENT);
    g.drawLine(r.getX(), r.getY(), r.getRight(), r.getY(), 1.f);
}

// ─────────────────────────────────────────────────────────────────────────
// Config overlay
// ─────────────────────────────────────────────────────────────────────────
void DIMEditor::showConfigOverlay()
{
    configOverlay_ = std::make_unique<juce::Component>();
    configOverlay_->setOpaque(false);

    auto* overlay = configOverlay_.get();
    int w = getWidth(), h = getHeight();

    // Background
    overlay->setSize(w, h);

    // IP fields + buttons — built inline
    edIP1_ = std::make_unique<juce::TextEditor>("ip1");
    edIP2_ = std::make_unique<juce::TextEditor>("ip2");
    btnSaveConfig_   = std::make_unique<juce::TextButton>("SAVE");
    btnCancelConfig_ = std::make_unique<juce::TextButton>("CANCEL");

    auto setupEd = [](juce::TextEditor* ed, const juce::String& v) {
        ed->setFont(juce::Font("Courier New", 12.f, juce::Font::plain));
        ed->setColour(juce::TextEditor::backgroundColourId, juce::Colour(0xff1a1a1a));
        ed->setColour(juce::TextEditor::textColourId, DIMColors::TEXT);
        ed->setColour(juce::TextEditor::outlineColourId, DIMColors::BORDER);
        ed->setColour(juce::TextEditor::focusedOutlineColourId, DIMColors::ACCENT);
        ed->setText(v, false);
    };

    setupEd(edIP1_.get(), proc_.getIP1());
    setupEd(edIP2_.get(), proc_.getIP2());

    overlay->addAndMakeVisible(edIP1_.get());
    overlay->addAndMakeVisible(edIP2_.get());
    overlay->addAndMakeVisible(btnSaveConfig_.get());
    overlay->addAndMakeVisible(btnCancelConfig_.get());

    // Layout inside a centred panel
    int pw = 300, ph = 140;
    int px = (w - pw) / 2, py = (h - ph) / 2;

    edIP1_->setBounds(px, py + 28, pw, 24);
    edIP2_->setBounds(px, py + 62, pw, 24);
    btnSaveConfig_  ->setBounds(px,          py + 100, 140, 28);
    btnCancelConfig_->setBounds(px + pw - 140, py + 100, 140, 28);

    btnSaveConfig_->onClick = [this] {
        proc_.setIPs(edIP1_->getText(), edIP2_->getText());
        hideConfigOverlay();
    };
    btnCancelConfig_->onClick = [this] { hideConfigOverlay(); };

    // Custom paint for panel background
    overlay->setPaintingIsUnclipped(false);

    // We need a painting component — wrap with a lambda-painted component
    struct OverlayBg : public juce::Component {
        void paint(juce::Graphics& g) override {
            g.fillAll(juce::Colour(0xcc000000));
            auto p = getLocalBounds().withSizeKeepingCentre(300, 140).toFloat();
            g.setColour(juce::Colour(0xff1a1a1a));
            g.fillRoundedRectangle(p, 4.f);
            g.setColour(DIMColors::ACCENT);
            g.drawRoundedRectangle(p, 4.f, 1.f);

            g.setFont(juce::Font("Courier New", 10.f, juce::Font::plain));
            g.setColour(DIMColors::ACCENT);
            g.drawText("SERVER IPs  (ports 5000-5010 auto-scanned)",
                       p.withHeight(24).translated(0, 4),
                       juce::Justification::centred);
            g.setColour(DIMColors::DIM_C);
            int lx = (int)p.getX();
            g.drawText("IP 1", juce::Rectangle<int>(lx, (int)p.getY() + 26, 32, 10),
                       juce::Justification::centredLeft);
            g.drawText("IP 2", juce::Rectangle<int>(lx, (int)p.getY() + 60, 32, 10),
                       juce::Justification::centredLeft);
        }
    };
    auto* bg = new OverlayBg();
    bg->setBounds(0, 0, w, h);
    overlay->addAndMakeVisible(bg, -1);  // behind other components

    addAndMakeVisible(configOverlay_.get());
    configOverlay_->setBounds(getLocalBounds());
    configOverlay_->toFront(true);
    edIP1_->grabKeyboardFocus();
}

void DIMEditor::hideConfigOverlay()
{
    if (configOverlay_) {
        removeChildComponent(configOverlay_.get());
        configOverlay_.reset();
        edIP1_.reset();
        edIP2_.reset();
        btnSaveConfig_.reset();
        btnCancelConfig_.reset();
    }
}
