#include "PluginProcessor.h"
#include "PluginEditor.h"

DIMProcessor::DIMProcessor()
    : AudioProcessor(BusesProperties())  // no buses = no audio I/O
{}

DIMProcessor::~DIMProcessor() {}

// ─────────────────────────────────────────────────────────────────────────
juce::AudioProcessorEditor* DIMProcessor::createEditor()
{
    return new DIMEditor(*this);
}

// ─────────────────────────────────────────────────────────────────────────
void DIMProcessor::setIPs(const juce::String& a, const juce::String& b)
{
    ip1 = a;
    ip2 = b;
    client.setCredentials(ip1, ip2);
}

// ─────────────────────────────────────────────────────────────────────────
// Persist IPs across DAW sessions
// ─────────────────────────────────────────────────────────────────────────
void DIMProcessor::getStateInformation(juce::MemoryBlock& dest)
{
    juce::ValueTree state("DIMState");
    state.setProperty("ip1", ip1, nullptr);
    state.setProperty("ip2", ip2, nullptr);
    juce::MemoryOutputStream out(dest, true);
    state.writeToStream(out);
}

void DIMProcessor::setStateInformation(const void* data, int size)
{
    auto state = juce::ValueTree::readFromData(data, (size_t)size);
    if (state.isValid()) {
        ip1 = state.getProperty("ip1", ip1).toString();
        ip2 = state.getProperty("ip2", ip2).toString();
        client.setCredentials(ip1, ip2);
    }
}

// ─────────────────────────────────────────────────────────────────────────
// Plugin entry point
// ─────────────────────────────────────────────────────────────────────────
juce::AudioProcessor* JUCE_CALLTYPE createPluginFilter()
{
    return new DIMProcessor();
}
