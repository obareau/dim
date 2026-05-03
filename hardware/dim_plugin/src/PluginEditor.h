#pragma once
#include <JuceHeader.h>
#include "PluginProcessor.h"
#include "DIMClient.h"

// ─────────────────────────────────────────────────────────────────────────
// DIM color palette
// ─────────────────────────────────────────────────────────────────────────
namespace DIMColors {
    const juce::Colour BG      { 0xff0a0a0a };
    const juce::Colour HEADER  { 0xff1a1a1a };
    const juce::Colour PANEL   { 0xff121212 };
    const juce::Colour BORDER  { 0xff222222 };
    const juce::Colour ACCENT  { 0xffe8c830 };   // yellow
    const juce::Colour ACCENT2 { 0xff55aaff };   // blue
    const juce::Colour TEXT    { 0xffcccccc };
    const juce::Colour DIM_C   { 0xff555555 };
    const juce::Colour GREEN   { 0xff00dd55 };
    const juce::Colour ORANGE  { 0xffff8800 };
    const juce::Colour RED     { 0xffff3344 };
    const juce::Colour GREY    { 0xff333333 };
}

// ─────────────────────────────────────────────────────────────────────────
// Small command button with D.I.M look
// ─────────────────────────────────────────────────────────────────────────
class DIMButton : public juce::Component
{
public:
    std::function<void()> onClick;

    DIMButton(const juce::String& label, juce::Colour accent = DIMColors::ACCENT)
        : label_(label), accent_(accent) {}

    void paint(juce::Graphics& g) override
    {
        auto b = getLocalBounds().toFloat().reduced(1.f);
        g.setColour(hover_ ? accent_.withAlpha(0.15f) : DIMColors::HEADER);
        g.fillRoundedRectangle(b, 2.f);
        g.setColour(hover_ ? accent_ : DIMColors::BORDER);
        g.drawRoundedRectangle(b, 2.f, 1.f);
        g.setFont(juce::Font("Courier New", 10.f, juce::Font::plain));
        g.setColour(hover_ ? accent_ : DIMColors::DIM_C);
        g.drawText(label_, getLocalBounds(), juce::Justification::centred);
    }

    void mouseEnter(const juce::MouseEvent&) override { hover_ = true;  repaint(); }
    void mouseExit (const juce::MouseEvent&) override { hover_ = false; repaint(); }
    void mouseDown (const juce::MouseEvent&) override { if (onClick) onClick(); repaint(); }

private:
    juce::String label_;
    juce::Colour accent_;
    bool hover_ = false;
};

// ─────────────────────────────────────────────────────────────────────────
// DIMEditor — plugin window
// Layout (520 × 340 default, resizable):
//   [0..34]   Header bar  — logo | status | BPM | sig | bar | elapsed
//   [35..59]  Server bar  — URL | SCAN button
//   [60..295] Lanes area  — adaptive rows
//   [296..339] Footer     — transport + advance + veto buttons
// ─────────────────────────────────────────────────────────────────────────
class DIMEditor : public juce::AudioProcessorEditor,
                  public DIMClient::Listener,
                  private juce::Timer
{
public:
    explicit DIMEditor(DIMProcessor&);
    ~DIMEditor() override;

    void paint(juce::Graphics&) override;
    void resized() override;

    // DIMClient::Listener
    void dimStateChanged(const DIMState&) override;

private:
    void timerCallback() override;

    // Sub-painters
    void paintHeader  (juce::Graphics&, juce::Rectangle<int>);
    void paintServerBar(juce::Graphics&, juce::Rectangle<int>);
    void paintLanes   (juce::Graphics&, juce::Rectangle<int>);
    void paintFooter  (juce::Graphics&, juce::Rectangle<int>);

    void paintLaneRow (juce::Graphics&, juce::Rectangle<int>,
                       const DIMState::Lane&, int idx, bool playing);

    // Config overlay
    void showConfigOverlay();
    void hideConfigOverlay();

    // ── State ──────────────────────────────────────────────────────────
    DIMProcessor& proc_;
    DIMState      state_;
    juce::String  flashMsg_;
    juce::Time    flashUntil_;

    // ── Buttons ────────────────────────────────────────────────────────
    DIMButton btnPlay    { "▶  PLAY",    DIMColors::GREEN  };
    DIMButton btnStop    { "⏹  STOP",   DIMColors::DIM_C  };
    DIMButton btnRewind  { "⏮  REW",    DIMColors::DIM_C  };
    DIMButton btnAdvance { "↵  ADV",     DIMColors::ACCENT };
    DIMButton btnAll     { "↵↵ ALL",    DIMColors::ACCENT };
    DIMButton btnVeto    { "✕  VETO",   DIMColors::RED    };
    DIMButton btnScan    { "SCAN",       DIMColors::ACCENT2};
    DIMButton btnConfig  { "⚙",         DIMColors::DIM_C  };

    // Config overlay widgets
    std::unique_ptr<juce::Component>  configOverlay_;
    std::unique_ptr<juce::TextEditor> edIP1_, edIP2_;
    std::unique_ptr<juce::TextButton> btnSaveConfig_;
    std::unique_ptr<juce::TextButton> btnCancelConfig_;

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR(DIMEditor)
};
