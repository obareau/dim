#!/usr/bin/env bash
# D.I.M — VST3/AU plugin build script
# ──────────��──────────────────────────────────────────────────────────────
# Usage:
#   ./build.sh           → configure + build (Release)
#   ./build.sh debug     → build Debug
#   ./build.sh clean     → rm -rf build/
#
# First build: downloads JUCE from GitHub (~200 MB) — takes a few minutes.
# Subsequent builds: incremental, ~5-10 s.
#
# Output:
#   VST3 → build/DIMPlugin_artefacts/Release/VST3/D.I.M.vst3
#   AU   → build/DIMPlugin_artefacts/Release/AU/D.I.M.component
#   Both auto-installed to ~/Library/... if COPY_PLUGIN_AFTER_BUILD=TRUE
# ─────────────────────────────────────────────────────���───────────────────
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BUILD_DIR="$SCRIPT_DIR/build"
CONFIG="${1:-Release}"

if [[ "$1" == "clean" ]]; then
  echo "🧹  Cleaning build directory..."
  rm -rf "$BUILD_DIR"
  echo "✅  Done"
  exit 0
fi

[[ "$1" == "debug" ]] && CONFIG="Debug"

# ── Configure (first time or after clean) ────────────────────────────────
if [[ ! -f "$BUILD_DIR/CMakeCache.txt" ]]; then
  echo "🔧  Configuring (first time — downloads JUCE ~200 MB)..."
  cmake -S "$SCRIPT_DIR" -B "$BUILD_DIR" \
    -DCMAKE_BUILD_TYPE="$CONFIG" \
    -DCMAKE_OSX_ARCHITECTURES="arm64;x86_64"   # Universal Binary
fi

# ── Build ───────────────────────────���─────────────────────────────���───────
echo "🔨  Building $CONFIG..."
cmake --build "$BUILD_DIR" --config "$CONFIG" --parallel

# ── Report ────────────────────────────────────────────────────────────────
VST3="$BUILD_DIR/DIMPlugin_artefacts/$CONFIG/VST3/D.I.M.vst3"
AU="$BUILD_DIR/DIMPlugin_artefacts/$CONFIG/AU/D.I.M.component"

echo ""
echo "✅  Build complete"
[[ -e "$VST3" ]] && echo "   VST3 → $VST3"
[[ -e "$AU"   ]] && echo "   AU   → $AU"
echo ""
echo "   Installed to:"
echo "   VST3 → ~/Library/Audio/Plug-Ins/VST3/D.I.M.vst3"
echo "   AU   → ~/Library/Audio/Plug-Ins/Components/D.I.M.component"
echo ""
echo "   After install, rescan in your DAW:"
echo "   • Ableton Live : Preferences → Plug-Ins → Rescan"
echo "   • Logic Pro    : redémarre Logic (AU auto-scanné)"
echo "   • Reaper       : Options → Preferences → Plug-ins → Re-scan"
