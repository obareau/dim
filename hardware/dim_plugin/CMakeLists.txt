cmake_minimum_required(VERSION 3.22)
project(DIMPlugin VERSION 0.1.0)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# ── JUCE via FetchContent ──────────────────────────────────────────────────
include(FetchContent)
FetchContent_Declare(JUCE
    GIT_REPOSITORY https://github.com/juce-framework/JUCE.git
    GIT_TAG        8.0.4
    GIT_SHALLOW    TRUE
)
FetchContent_MakeAvailable(JUCE)

# ── Plugin target ──────────────────────────────────────────────────────────
juce_add_plugin(DIMPlugin
    COMPANY_NAME            "Olivier Bareau"
    PLUGIN_MANUFACTURER_CODE Olbr
    PLUGIN_CODE             Dimp
    FORMATS                 VST3 AU
    PRODUCT_NAME            "D.I.M"
    BUNDLE_ID               "fr.bareau.dim-plugin"

    # No audio I/O — pure control surface
    IS_SYNTH                FALSE
    NEEDS_MIDI_INPUT        FALSE
    NEEDS_MIDI_OUTPUT       FALSE   # set TRUE later for MIDI clock out
    IS_MIDI_EFFECT          FALSE

    EDITOR_WANTS_KEYBOARD_FOCUS FALSE
    COPY_PLUGIN_AFTER_BUILD      TRUE   # installs to ~/Library/... after build
)

# ── Sources ────────────────────────────────────────────────────────────────
target_sources(DIMPlugin PRIVATE
    src/DIMClient.h
    src/DIMClient.cpp
    src/PluginProcessor.h
    src/PluginProcessor.cpp
    src/PluginEditor.h
    src/PluginEditor.cpp
)

target_include_directories(DIMPlugin PRIVATE src)

# Generate JuceHeader.h (aggregates all JUCE module headers)
juce_generate_juce_header(DIMPlugin)

# ── JUCE modules ──────────────────────────────────────────────────────────
target_compile_definitions(DIMPlugin PUBLIC
    JUCE_WEB_BROWSER=0
    JUCE_USE_CURL=0
    JUCE_VST3_CAN_REPLACE_VST2=0
    JUCE_DISPLAY_SPLASH_SCREEN=0
)

target_link_libraries(DIMPlugin PRIVATE
    juce::juce_audio_utils
    juce::juce_audio_processors
    juce::juce_gui_basics
    juce::juce_gui_extra
    PUBLIC
    juce::juce_recommended_config_flags
    juce::juce_recommended_lto_flags
    juce::juce_recommended_warning_flags
)
