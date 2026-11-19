#!/bin/sh
# jav installer — one-liner:
#   curl -fsSL https://raw.githubusercontent.com/k4wai1/jav/master/install.sh | sh
# Env: VERSION=v2.6.0 (default: latest), REPO=k4wai1/jav (override),
#      PREFIX=/custom (default: /usr/local/bin o ~/.local/bin), BIN=jav.
# Termux/Android: descarga jav_android_arm64.tar.gz e instala en $PREFIX/bin.
set -eu

REPO="${REPO:-k4wai1/jav}"
VERSION="${VERSION:-latest}"
BIN="${BIN:-jav}"

OS="$(uname -s)"
ARCH="$(uname -m)"

# Termux/Android: uname -s suele decir "Linux"; uname -o dice "Android".
IS_TERMUX=0
if [ -n "${TERMUX_VERSION:-}" ] || [ "$(uname -o 2>/dev/null || true)" = "Android" ]; then
  IS_TERMUX=1
fi

if [ "$IS_TERMUX" = "1" ]; then
  GOOS="android"
  GARCH="arm64"
else
  case "$OS" in
    Linux) GOOS="linux" ;;
    Darwin) GOOS="darwin" ;;
    MINGW*|MSYS*|CYGWIN*|Windows_NT) GOOS="windows" ;;
    *) echo "jav: unsupported OS: $OS" >&2; exit 1 ;;
  esac

  case "$ARCH" in
    x86_64|amd64) GARCH="amd64" ;;
    aarch64|arm64) GARCH="arm64" ;;
    *) echo "jav: unsupported arch: $ARCH" >&2; exit 1 ;;
  esac
fi

if [ "$GOOS" = "windows" ]; then
  EXT="zip"
else
  EXT="tar.gz"
fi

asset_url() {
  _asset="${BIN}_$1_$2.${EXT}"
  if [ "$VERSION" = "latest" ]; then
    echo "https://github.com/${REPO}/releases/latest/download/${_asset}"
  else
    echo "https://github.com/${REPO}/releases/download/${VERSION}/${_asset}"
  fi
}

fetch() {
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL "$1" -o "$2"
  elif command -v wget >/dev/null 2>&1; then
    wget -qO "$2" "$1"
  else
    echo "jav: need curl or wget" >&2; return 1
  fi
}

ASSET="${BIN}_${GOOS}_${GARCH}.${EXT}"
URL="$(asset_url "$GOOS" "$GARCH")"

# Destino: Termux $PREFIX/bin > $PREFIX/bin > /usr/local/bin (si escribible)
# > ~/.local/bin.
if [ "$IS_TERMUX" = "1" ] && [ -n "${PREFIX:-}" ]; then
  DEST="$PREFIX/bin"
elif [ -n "${PREFIX:-}" ]; then
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
if ! fetch "$URL" "$TMP/pkg.$EXT"; then
  if [ "$IS_TERMUX" = "1" ]; then
    # Fallback limpio para releases antiguos (sin android/arm64): el binario
    # Go estático linux/arm64 corre igual en Termux.
    GOOS="linux"
    ASSET="${BIN}_${GOOS}_${GARCH}.${EXT}"
    URL="$(asset_url "$GOOS" "$GARCH")"
    echo "jav: sin build android/arm64 en ${VERSION}; probando ${ASSET}" >&2
    echo "jav: downloading ${URL}" >&2
    fetch "$URL" "$TMP/pkg.$EXT" || { echo "jav: download failed: $URL" >&2; exit 1; }
  else
    echo "jav: download failed: $URL" >&2; exit 1
  fi
fi

if [ "$EXT" = "zip" ]; then
  (cd "$TMP" && unzip -q "pkg.$EXT")
else
  tar -xzf "$TMP/pkg.$EXT" -C "$TMP"
fi

# El binario puede venir en raíz o dentro de subdir según el archive.
SRC="$(find "$TMP" -maxdepth 2 -type f -name "${BIN}" | head -n 1)"
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

# --- Guía post-instalación (usuario nuevo) ---
cat <<EOF

✓ jav instalado en $DEST/$BIN
  versión: $VERSION

Próximos pasos:
  1. Descarga e instala la APK companion:
     https://github.com/${REPO}/releases/latest/download/jav-companion.apk
  2. Activa Accesibilidad en el teléfono (Ajustes → Accesibilidad → Jav)
  3. Arranca Shizuku (lo inicia la app Shizuku; Jav NUNCA lo arranca)
  4. Copia el token que muestra la app Jav (tarjeta 3)
  5. Vincula:
       jav pair <IP-TAILNET-DEL-TELEFONO> <TOKEN>   # por Tailnet (WSS)
       jav pair usb <TOKEN>                          # por USB (adb forward)
     o simplemente:  jav pair   (modo interactivo)

Guía completa: https://github.com/${REPO}#quickstart
EOF
