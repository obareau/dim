#!/usr/bin/env bash
# D.I.M — M5Stack Core build + flash
# ─────────────────────────────────────────────────────────────────────────
# Usage:
#   ./flash.sh           → compile uniquement (génère le .bin)
#   ./flash.sh flash     → compile + flash via USB (auto-détecte le port)
#   ./flash.sh flash /dev/cu.usbserial-XXXX  → port explicite
#   ./flash.sh bin       → compile + copie le .bin dans ./dist/ (pour M5Burner)
#
# Prérequis : PlatformIO Core (pip install platformio)
#             ou installer via : https://docs.platformio.org/en/latest/core/installation/
# ─────────────────────────────────────────────────────────────────────────

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# PlatformIO installé via Homebrew Python 3.13
export PATH="/opt/homebrew/bin:$PATH"
BUILD_DIR="$SCRIPT_DIR/.pio/build/m5stack-core-esp32"
BIN_SRC="$BUILD_DIR/firmware.bin"
DIST_DIR="$SCRIPT_DIR/dist"

# ── Check PlatformIO ───────────────────────────────────────────────────────
if ! command -v pio &>/dev/null; then
  echo "❌  PlatformIO introuvable."
  echo "    Installer : pip install platformio"
  echo "    Ou via :    https://docs.platformio.org/en/latest/core/installation/"
  exit 1
fi

MODE="${1:-build}"
PORT="${2:-}"

# ── Compile ────────────────────────────────────────────────────────────────
echo "🔨  Compilation..."
pio run --project-dir "$SCRIPT_DIR"
echo "✅  Binaire : $BIN_SRC"

# ── Flash via USB ──────────────────────────────────────────────────────────
if [[ "$MODE" == "flash" ]]; then
  if [[ -n "$PORT" ]]; then
    echo "⚡  Flash → $PORT"
    pio run --project-dir "$SCRIPT_DIR" -t upload --upload-port "$PORT"
  else
    echo "⚡  Flash (auto-détection du port)..."
    pio run --project-dir "$SCRIPT_DIR" -t upload
  fi
  echo "✅  Flash terminé"
fi

# ── Export .bin pour M5Burner / esptool manuel ─────────────────────────────
if [[ "$MODE" == "bin" ]]; then
  mkdir -p "$DIST_DIR"
  DEST="$DIST_DIR/DIM_M5Core_$(date +%Y%m%d_%H%M).bin"
  cp "$BIN_SRC" "$DEST"
  echo "📦  Binaire copié : $DEST"
  echo ""
  echo "    ┌─ Flash manuel avec esptool ──────────────────────────────────┐"
  echo "    │  esptool.py --chip esp32 --port /dev/cu.usbserial-XXXX      │"
  echo "    │    --baud 921600 write_flash -z 0x10000 $DEST               │"
  echo "    └──────────────────────────────────────────────────────────────┘"
  echo ""
  echo "    ┌─ Flash avec M5Burner (custom firmware) ──────────────────────┐"
  echo "    │  1. Ouvrir M5Burner                                          │"
  echo "    │  2. Onglet 'Custom' ou bouton '+' selon la version           │"
  echo "    │  3. Sélectionner le .bin ci-dessus                           │"
  echo "    │  4. Adresse flash : 0x10000                                  │"
  echo "    │  5. Flash                                                     │"
  echo "    └──────────────────────────────────────────────────────────────┘"
fi
