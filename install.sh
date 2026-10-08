#!/bin/sh
# jav installer — one-liner:
#   curl -fsSL https://raw.githubusercontent.com/k4wai1/jav/master/install.sh | sh
# Env: VERSION=v0.1.0 (default: latest), REPO=k4wai1/jav (override),
#      PREFIX=/custom (default: /usr/local/bin o ~/.local/bin), BIN=jav.
set -eu

REPO="${REPO:-k4wai1/jav}"
VERSION="${VERSION:-latest}"
BIN="${BIN:-jav}"

OS="$(uname -s)"
ARCH="$(uname -m)"

case "$OS" in
  Linux) GOOS="Linux" ;;
  Darwin) GOOS="Darwin" ;;
  MINGW*|MSYS*|CYGWIN*|Windows_NT) GOOS="Windows" ;;
  *) echo "jav: unsupported OS: $OS" >&2; exit 1 ;;
esac

case "$ARCH" in
  x86_64|amd64) GARCH="x86_64" ;;
  aarch64|arm64) GARCH="arm64" ;;
  *) echo "jav: unsupported arch: $ARCH" >&2; exit 1 ;;
esac

if [ "$GOOS" = "Windows" ]; then
  EXT="zip"
  ASSET="${BIN}_${GOOS}_${GARCH}.zip"
else
  EXT="tar.gz"
  ASSET="${BIN}_${GOOS}_${GARCH}.tar.gz"
fi

if [ "$VERSION" = "latest" ]; then
  URL="https://github.com/${REPO}/releases/latest/download/${ASSET}"
else
  URL="https://github.com/${REPO}/releases/download/${VERSION}/${ASSET}"
fi

# Destino: $PREFIX/bin > /usr/local/bin (si escribible) > ~/.local/bin.
if [ -n "${PREFIX:-}" ]; then
  DEST="${PREFIX}/bin"
elif [ -w "/usr/local/bin" ] 2>/dev/null; then
  DEST="/usr/local/bin"
else
  DEST="$HOME/.local/bin"
fi
mkdir -p "$DEST"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT INT TERM

echo "jav: downloading ${URL}" >&2
if command -v curl >/dev/null 2>&1; then
  curl -fsSL "$URL" -o "$TMP/pkg.$EXT"
elif command -v wget >/dev/null 2>&1; then
  wget -qO "$TMP/pkg.$EXT" "$URL"
else
  echo "jav: need curl or wget" >&2; exit 1
fi

if [ "$EXT" = "zip" ]; then
  (cd "$TMP" && unzip -q "pkg.$EXT")
else
  tar -xzf "$TMP/pkg.$EXT" -C "$TMP"
fi

# El binario puede venir en raíz o dentro de subdir según el archive.
SRC="$(find "$TMP" -maxdepth 2 -type f -name "${BIN}${EXE:-}" | head -n 1)"
if [ -z "$SRC" ]; then
  SRC="$(find "$TMP" -maxdepth 2 -type f -name "${BIN}.exe" | head -n 1)"
fi
if [ -z "$SRC" ]; then
  echo "jav: binary '$BIN' not found in $ASSET" >&2; exit 1
fi

install -m 0755 "$SRC" "$DEST/$BIN"
echo "jav: installed to $DEST/$BIN" >&2
case ":$PATH:" in
  *":$DEST:"*) ;;
  *) echo "jav: note: $DEST is not in PATH" >&2 ;;
esac
