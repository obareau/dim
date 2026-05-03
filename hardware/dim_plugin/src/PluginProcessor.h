#pragma once
#include <JuceHeader.h>
#include "DIMClient.h"

// ─────────────────────────────────────────────────────────────────────────
// DIMProcessor — AudioProcessor with no audio I/O.
// Holds the DIMClient and persists settings via AudioProcessorValueTreeState.
// ─────────────────────────────────────────────────────────────────────────
class DIMProcessor : public juce::AudioProcessor
{
public:
    DIMProcessor();
    ~DIMProcessor() override;

    // ── Standard AudioProcessor interface ────────────────────────────────
    void prepareToPlay(double, int) override {}
    void releaseResources() override {}
    void processBlock(juce::AudioBuffer<float>&, juce::MidiBuffer&) override {}

    juce::AudioProcessorEditor* createEditor() override;
    bool hasEditor() const override { return true; }

    const juce::String getName() const override { return "D.I.M"; }
    bool   acceptsMidi()  const override { return false; }
    bool   producesMidi() const override { return false; }
    bool   isMidiEffect() const override { return false; }
    double getTailLengthSeconds() const override { return 0.0; }

    int  getNumPrograms()   override { return 1; }
    int  getCurrentProgram() override { return 0; }
    void setCurrentProgram(int) override {}
    const juce::String getProgramName(int) override { return {}; }
    void changeProgramName(int, const juce::String&) override {}

    void getStateInformation(juce::MemoryBlock& dest) override;
    void setStateInformation(const void* data, int size) override;

    // ── DIM interface ─────────────────────────────────────────────────────
    DIMClient& getClient() { return client; }

    juce::String getIP1() const { return ip1; }
    juce::String getIP2() const { return ip2; }
    void setIPs(const juce::String& a, const juce::String& b);

private:
    DIMClient client;
    juce::String ip1 { "192.168.1.100" };
    juce::String ip2 { "192.168.1.1"   };

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR(DIMProcessor)
};
