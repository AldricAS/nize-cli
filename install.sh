#!/usr/bin/env bash
# install.sh — makes "nize" runnable as a global command anywhere in the terminal.
#
# Usage:
#   bash install.sh
#
# What it does:
#   1. Copies aicli.py to a folder that's on your $PATH, named "nize" (no .py).
#   2. Marks it executable.
#   3. Makes sure that folder is actually on PATH (adds it to your shell rc if not).
#
# Works on Termux and regular Linux/macOS.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$SCRIPT_DIR/aicli.py"

if [ ! -f "$SRC" ]; then
  echo "✖ Couldn't find aicli.py next to install.sh (looked in $SCRIPT_DIR)."
  exit 1
fi

# Pick an install directory that's already on PATH when possible.
if [ -n "$PREFIX" ] && [ -d "$PREFIX/bin" ]; then
  # Termux
  INSTALL_DIR="$PREFIX/bin"
else
  INSTALL_DIR="$HOME/.local/bin"
  mkdir -p "$INSTALL_DIR"
fi

DEST="$INSTALL_DIR/nize"
cp "$SRC" "$DEST"
chmod +x "$DEST"

echo "✔ Installed to $DEST"

# Make sure INSTALL_DIR is on PATH
case ":$PATH:" in
  *":$INSTALL_DIR:"*)
    echo "✔ $INSTALL_DIR is already on your PATH."
    ;;
  *)
    RC_FILE="$HOME/.bashrc"
    [ -n "$ZSH_VERSION" ] && RC_FILE="$HOME/.zshrc"
    echo "export PATH=\"$INSTALL_DIR:\$PATH\"" >> "$RC_FILE"
    echo "✔ Added $INSTALL_DIR to PATH in $RC_FILE"
    echo "  → Run: source $RC_FILE   (or just restart your terminal)"
    ;;
esac

echo
echo "Done! Set your API key once, then just type: nize"
echo "  export AICLI_API_KEY=\"your-key\""
echo "  nize"
