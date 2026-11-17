#!/usr/bin/env bash
# audit-bundle.sh — paquete de auditoría externa de Jav.
#
# Genera en la raíz del repo:
#   jav-audit.zip  → ZIP SIN compresión (zip -0 -X) con código + docs + configs.
#                    Incluye AUDIT-MANIFEST.txt (versión, commit, fecha, sha256
#                    por archivo y exclusiones justificadas).
#   jav-audit.txt  → volcado en texto plano concatenado del MISMO conjunto de
#                    archivos (para auditores que no abren ZIP). Cada archivo va
#                    precedido por "===== <ruta> =====".
#   jav-tree.txt   → árbol completo del proyecto (tree -a -h) con cabecera.
#
# Reglas:
#   - Solo texto/código: fuera binarios (*.png|svg|jar|apk|pdf…), build, dist,
#     node_modules, logs y artefactos.
#   - Fuera secretos (.env, local.properties, google-services.json,
#     *.keystore|jks|p12). Si alguno llega a la lista final, ABORTA.
#   - Los artefactos generados están en .gitignore: nunca se commitean.
#
# Uso: bash .opencode/skills/audit-bundle/audit-bundle.sh

set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

ZIP="$ROOT/jav-audit.zip"
TREE_OUT="$ROOT/jav-tree.txt"
DUMP="$ROOT/jav-audit.txt"

# --- Dependencias -----------------------------------------------------------
for bin in git zip unzip tree sha256sum; do
  if ! command -v "$bin" >/dev/null 2>&1; then
    echo "ERROR: falta '$bin' en PATH." >&2
    exit 1
  fi
done

# --- Metadatos --------------------------------------------------------------
VERSION="$(sed -n 's/^[[:space:]]*var version[[:space:]]*=[[:space:]]*"\([^"]*\)".*/\1/p' cmd/jav/main.go | head -n1)"
VERSION="${VERSION:-desconocida}"
COMMIT="$(git rev-parse --short HEAD)"
if git status --porcelain | grep -q .; then DIRTY="sí"; else DIRTY="no"; fi
STAMP="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# --- Política de inclusión --------------------------------------------------
# Rutas excluidas por prefijo/ruta exacta.
EXCLUDE_RE='^(\.git/|\.opencode/(node_modules|skills)/|dist/|logs/|android-app/\.gradle/|android-app/.*/build/|docs/diagrams/|jav-audit\.zip$|jav-tree\.txt$|jav_context\.txt$)'
# Extensiones binarias / media / artefactos.
EXCLUDE_EXT_RE='\.(png|jpe?g|gif|webp|ico|svg|jar|keystore|jks|p12|apk|aab|ap_|zip|pdf|so|exe|bin|woff2?|ttf)$'
# Compuerta anti-secreto (se evalúa sobre la lista final).
SECRET_RE='(^|/)\.env$|(^|/)\.env\.[^e]|(^|/)local\.properties$|(^|/)google-services\.json$|\.(keystore|jks|p12)$'

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

FILES=()
while IFS= read -r -d '' p; do
  [[ $p =~ $EXCLUDE_RE ]] && continue
  [[ $p =~ $EXCLUDE_EXT_RE ]] && continue
  [[ -f $p ]] || continue
  FILES+=("$p")
done < <(git ls-files -z --cached --others --exclude-standard | sort -z)

if (( ${#FILES[@]} < 50 )); then
  echo "ERROR: solo ${#FILES[@]} archivos seleccionados; ¿estás en el repo correcto?" >&2
  exit 1
fi

LEAKS=()
for p in "${FILES[@]}"; do
  [[ $p =~ $SECRET_RE ]] && LEAKS+=("$p")
done
if (( ${#LEAKS[@]} > 0 )); then
  echo "ERROR: la lista contiene posibles secretos; no se genera nada:" >&2
  printf '  %s\n' "${LEAKS[@]}" >&2
  exit 2
fi

TOTAL_BYTES=0
for p in "${FILES[@]}"; do
  TOTAL_BYTES=$(( TOTAL_BYTES + $(stat -c%s -- "$p") ))
done

# --- Manifiesto -------------------------------------------------------------
MANIFEST="$TMP/AUDIT-MANIFEST.txt"
{
  echo "JAV — AUDIT BUNDLE MANIFEST"
  echo "==========================="
  echo "Generated   : $STAMP"
  echo "App version : $VERSION"
  echo "Commit      : $COMMIT (dirty: $DIRTY)"
  echo "Files       : ${#FILES[@]}"
  echo "Total bytes : $TOTAL_BYTES"
  echo "Archive     : jav-audit.zip (sin compresión: zip -0 -X)"
  echo "Text dump   : jav-audit.txt (concatenación, mismo conjunto)"
  echo
  echo "Exclusiones deliberadas"
  echo "-----------------------"
  echo ".git/ · dist/ · logs/ · .opencode/node_modules · .opencode/skills"
  echo "android-app/.gradle/ · android-app/**/build/"
  echo "Secretos: .env · .env.* · local.properties · google-services.json · *.keystore|jks|p12"
  echo "Binarios/media: *.png|jpg|gif|webp|ico|svg|jar|apk|aab|pdf|so|exe|bin|woff*|ttf"
  echo "Generados: docs/diagrams/*.html · jav_context.txt · jav-audit.zip · jav-audit.txt · jav-tree.txt"
  echo
  echo "SHA-256 (ordenado por ruta)"
  echo "---------------------------"
  for p in "${FILES[@]}"; do
    sha256sum -- "$p"
  done
} > "$MANIFEST"

# --- ZIP sin compresión -----------------------------------------------------
rm -f "$ZIP"
printf '%s\n' "${FILES[@]}" > "$TMP/files.txt"
( cd "$ROOT" && zip -0 -X -q "$ZIP" -@ < "$TMP/files.txt" )
( cd "$TMP" && zip -0 -X -q "$ZIP" AUDIT-MANIFEST.txt )

# --- TEXTO CONCATENADO (auditores que no abren ZIP) -------------------------
rm -f "$DUMP"
DUMP_SECTIONS=0
{
  echo "JAV — AUDIT TEXT DUMP"
  echo "====================="
  echo "Generated   : $STAMP"
  echo "App version : $VERSION"
  echo "Commit      : $COMMIT (dirty: $DIRTY)"
  echo "Files       : ${#FILES[@]}"
  echo "Total bytes : $TOTAL_BYTES"
  echo "Mismo conjunto de archivos que jav-audit.zip."
  echo
  echo "Formato: texto plano concatenado; cada archivo va precedido por una"
  echo "línea '===== <ruta> ====='. Sin numeración de línea: el contenido es"
  echo "literal y copiable."
  echo
  for p in "${FILES[@]}"; do
    echo "===== $p ====="
    cat -- "$p"
    echo
    DUMP_SECTIONS=$(( DUMP_SECTIONS + 1 ))
  done
  echo "===== AUDIT-MANIFEST.txt ====="
  cat "$MANIFEST"
  echo
  DUMP_SECTIONS=$(( DUMP_SECTIONS + 1 ))
} > "$DUMP"

# --- TREE -------------------------------------------------------------------
EXCLUDE_TREE='.git|node_modules|.gradle|build|dist|logs|__pycache__|.idea|.vscode|jav-audit.zip|jav-audit.txt|jav-tree.txt|jav_context.txt'
{
  echo "JAV — PROJECT TREE"
  echo "=================="
  echo "Generated   : $STAMP"
  echo "App version : $VERSION"
  echo "Commit      : $COMMIT (dirty: $DIRTY)"
  echo "Excluidos del árbol (solo ruido/artefactos): .git, node_modules, .gradle,"
  echo "build, dist, logs, __pycache__, .idea, .vscode, jav-audit.zip, jav-tree.txt,"
  echo "jav_context.txt. Nombres de archivos ignorados (p.ej. local.properties) SÍ"
  echo "aparecen; su contenido no está en el ZIP."
  echo
  tree -a -h --dirsfirst --charset ascii -I "$EXCLUDE_TREE" .
} > "$TREE_OUT"

# --- Verificación -----------------------------------------------------------
ENTRIES="$(unzip -Z1 "$ZIP" | wc -l)"
EXPECTED=$(( ${#FILES[@]} + 1 ))
if (( ENTRIES != EXPECTED )); then
  echo "ERROR: el ZIP tiene $ENTRIES entradas; esperadas $EXPECTED." >&2
  exit 3
fi
if unzip -Z1 "$ZIP" | grep -Eq "$SECRET_RE"; then
  echo "ERROR: patrón de secreto detectado dentro del ZIP." >&2
  exit 4
fi
if (( DUMP_SECTIONS != EXPECTED )); then
  echo "ERROR: el dump tiene $DUMP_SECTIONS secciones; esperadas $EXPECTED." >&2
  exit 5
fi

echo "OK  jav-audit.zip  $(du -h "$ZIP" | cut -f1)  ${#FILES[@]} archivos  sha256:$(sha256sum "$ZIP" | cut -d' ' -f1)"
echo "OK  jav-audit.txt  $(du -h "$DUMP" | cut -f1)  $(wc -l < "$DUMP") líneas   sha256:$(sha256sum "$DUMP" | cut -d' ' -f1)"
echo "OK  jav-tree.txt   $(du -h "$TREE_OUT" | cut -f1)  $(wc -l < "$TREE_OUT") líneas   sha256:$(sha256sum "$TREE_OUT" | cut -d' ' -f1)"
