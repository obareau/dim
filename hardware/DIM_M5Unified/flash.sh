#!/usr/bin/env bash
# D.I.M — M5Stack build + flash (PlatformIO)
# ─────────────────────────────────────────────────────────────────────────
# Usage:
#   ./flash.sh                        → build tous les envs
#   ./flash.sh build core             → build m5stack_core seulement
#   ./flash.sh build core2            → build m5stack_core2
#   ./flash.sh build stickc           → build m5stickc_plus
#   ./flash.sh flash core             → build + flash Core (auto-port)
#   ./flash.sh flash core2 /dev/cu.X  → flash Core2 sur port explicite
#   ./flash.sh bin                    → build tous + export dist/ (M5Burner)
#   ./flash.sh clean                  → rm .pio/
# ─────────────────────────────────────────────────────────────────────────
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
export PATH="/opt/homebrew/bin:$PATH"

if ! command -v pio &>/dev/null; then
  echo "❌  PlatformIO introuvable — pip install platformio"
  exit 1
fi

declare -A ENVS=( [core]="m5stack_core" [core2]="m5stack_core2" [stickc]="m5stickc_plus" )

MODE="${1:-build}"
TARGET="${2:-all}"
PORT="${3:-}"

env_name() { echo "${ENVS[$1]:-$1}"; }

case "$MODE" in
  clean)
    echo "🧹  Cleaning .pio/ ..."
    pio run --project-dir "$DIR" -t clean --silent
    echo "✅  Done"
    ;;

  build)
    if [[ "$TARGET" == "all" ]]; then
      echo "🔨  Building all envs..."
      pio run --project-dir "$DIR"
    else
      ENV=$(env_name "$TARGET")
      echo "🔨  Building $ENV ..."
      pio run --project-dir "$DIR" -e "$ENV"
    fi
    echo "✅  Build done"
    ;;

  flash)
    ENV=$(env_name "$TARGET")
    echo "🔨  Building $ENV ..."
    pio run --project-dir "$DIR" -e "$ENV"
    if [[ -n "$PORT" ]]; then
      echo "⚡  Flash → $PORT"
      pio run --project-dir "$DIR" -e "$ENV" -t upload --upload-port "$PORT"
    else
      echo "⚡  Flash (auto-port)..."
      pio run --project-dir "$DIR" -e "$ENV" -t upload
    fi
    echo "✅  Flash done"
    ;;

  bin)
    echo "🔨  Building all envs for M5Burner export..."
    pio run --project-dir "$DIR"
    mkdir -p "$DIR/dist"
    DATE=$(date +%Y%m%d)
    for key in core core2 stickc; do
      ENV=$(env_name "$key")
      SRC="$DIR/.pio/build/$ENV/firmware.bin"
      if [[ -f "$SRC" ]]; then
        DEST="$DIR/dist/DIM_M5Unified_${key}_${DATE}.bin"
        cp "$SRC" "$DEST"
        echo "📦  $key → dist/$(basename "$DEST")"
      fi
    done
    echo ""
    echo "  Flash via M5Burner : sélectionner le .bin · adresse 0x10000"
    echo "  Flash via esptool  :"
    echo "    esptool.py --chip esp32 --port /dev/cu.usbserial-XXXX \\"
    echo "      --baud 921600 write_flash -z 0x10000 dist/DIM_M5Unified_core_${DATE}.bin"
    ;;

  *)
    echo "Usage: $0 {build|flash|bin|clean} [core|core2|stickc] [port]"
    exit 1
    ;;
esac
