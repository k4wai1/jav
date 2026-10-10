# TESTING.md — verificación manual sin Android Studio (Fase 1)

Banco: TECNO KJ5, Android 13 (API 33), sin root. App: `dev.jev.jam` (Jam).

## 1. Tests JVM (sin dispositivo)

```bash
cd android-app
./gradlew :app:testDebugUnitTest
# Report: app/build/test-results/testDebugUnitTest/
```

Cubre: raíz nula → package `""`, `nodes []` (sin campo `secure`),
ids BFS contiguos, poda de invisibles,
tope 500 determinista, mapeo de campos/bounds, `snapshot_id`.
Estado: **6/6 en verde.**

## 2. Verificación en dispositivo (`dump_ui` vs `uiautomator`)

```bash
adb install -r app/build/outputs/apk/debug/app-debug.apk
# Orden importa: primero el master switch, luego la lista
adb shell settings put secure accessibility_enabled 1
adb shell settings put secure enabled_accessibility_services \
  dev.jev.jam/dev.jev.jam.service.JevAccessibilityService
adb shell 'dumpsys accessibility | grep -m1 "Enabled services"'
adb shell am start -n dev.jev.jam/.MainActivity
# Localizar el botón y pulsarlo (banco visual temporal hasta Fase 2)
adb shell uiautomator dump /sdcard/jam_ui.xml
adb shell cat /sdcard/jam_ui.xml | grep -oiE '<node[^>]*volcar[^>]*>'
adb shell input tap 200 450
adb logcat -d | grep JamUi
```

Resultado medido (2026-10-01, pantalla de onboarding):
`dump snapshot=1 nodes=13 ms=40` (sin campo `secure`: contrato vigente).
Comparación de anclas (`text` o `resource_id` no nulos):
**9/9 = 100%** (criterio: ≥95%). Latencia **40 ms** (criterio: < 100 ms).

## 2b. Verificación en árboles reales (2026-10-02, LG7n API 31)

Banco no-normativo: una app de mensajería comercial + Ajustes del sistema.
Procedimiento: receiver temporal `DUMP_*` (eliminado tras
verificar) + `uiautomator dump` + comparativa de anclas por script.

- **Mensajería (chat vivo, 124 nodos)**: anclas 73/86 = **84.9%** vs
  **piso de ruido uia-vs-uia = 80.2%** (el chat es vivo: timestamps y
  mensajes cambian entre dumps). Diferencia sistemática restante =
  nodos invisibles que uiautomator incluye y nosotros podamos por diseño.
  Latencia: **264 ms**.
- **Ajustes (estático, 66 nodos)**: anclas **26/26 = 100%**,
  0 nodos perdidos. Latencia: **106 ms**.
- **Escalado medido**: ~2 ms/nodo (IPC por nodo). El umbral < 100 ms
  vale para pantallas típicas (≤50 nodos); árboles grandes escalan lineal,
  con tope 500 (peor caso ~1 s). Sigue siendo 16× mejor que uiautomator.
- **Superficie protegida (contrato vigente)**: `FLAG_SECURE` no oculta
  el árbol de accesibilidad (TalkBack funciona en banca); solo bloquea
  capturas. Por eso `dump_ui` **no lleva campo `secure`** y
  `root == null` significa "sin ventana activa" (transitorio) →
  package `""`, `nodes []`, nunca "seguro". La semántica de superficie
  protegida vive solo en `screenshot` → `SECURE_SURFACE`
  (`AccessibilityWindowInfo.isSecure()` no existe en API 34).
  El cold-start de la app de banco devolvió `nodes=0` por timing,
  no por flag: reintentar en caliente.
- **Bug encontrado y corregido**: `snapshot_id` era campo de instancia;
  al recrearse el servicio se reiniciaba (visto: `snapshot=1` repetido).
  Ahora persiste en `SharedPreferences` (`jam.snapshot_id`) en cada dump.

## 2c. Broadcasts implícitos filtrados

`am broadcast -a <acción>` a un receiver de manifest **no llega** si el
paquete está en stopped o por restricciones de broadcasts implícitos.
Usar broadcast **explícito**: `am broadcast -a … -n pkg/.Clase`.
(Así se dispararon los dumps temporales de §2b.)

## 3. Fase 2 — bucle WS end-to-end (2026-10-02, LG7n API 31)

```bash
adb forward tcp:38472 tcp:38472
cd mcp-server && uv sync && uv run python scripts/fase2_check.py
```

El script: token desde logcat (`JamWs token=…`), abre la app de banco
(`open_app` genérico), `hello` → `get_foreground` → `dump_ui` → `tap`
(selector descubierto: navegación "Atrás") → `tap_node` → `dump_ui` →
check `STALE_SNAPSHOT`.

Medido: `hello` con scopes `['read','ui']`; `foreground` = app de banco;
`dump1` 153 nodos; **`tap ok via=action_click`** (sufijo de resource
genérico de toolbar); `tap_node` con snapshot previo → `STALE_SNAPSHOT`
(correcto: el tap cambió la UI); `dump2` snapshot 11→13; snapshot viejo
rechazado con `STALE_SNAPSHOT`. **OK fase2.**

Fixes que salieron del propio test: `hello` debe responder **plano**
(PROTOCOL §2, sin envoltura `result`); `GestureResultCallback` es clase
**anidada** de `AccessibilityService` (no existe top-level en API 34);
`JsonArrayBuilder.add(String)` no resolvió → `JsonPrimitive` explícito.

## 4. Fase 3a — Shizuku + screenshot (LG7n, Shizuku oficial)

Pre-requisito (lo hace el usuario): Shizuku arrancado + permiso a Jam.
Pre-check del script: `pidof moe.shizuku.privileged.api` non-vacío;
si vacío → mensaje claro y exit 1 (eso también prueba `SHIZUKU_UNAVAILABLE`).

```bash
adb forward tcp:38472 tcp:38472
cd mcp-server && uv run python scripts/fase3_check.py
```

1. `force_stop(<pkg-banco>)` → `get_foreground` ya no es esa app.
2. `open_app(<pkg-banco>)` → `get_foreground` = `<pkg-banco>`.
3. `screenshot` → `img_base64` > 1000 chars, `w`/`h` > 0; comparar
   visualmente con `adb exec-out screencap -p`.
4. Superficie segura → `SECURE_SURFACE` (app bancaria si hay; si no,
   FLAG_SECURE temporal en Jam como en §2b).
5. `shell {command: "id"}` → `METHOD_NOT_ALLOWED` (no `INTERNAL_ERROR`).
6. Sin permiso Shizuku (denegar en pantalla) → `SHIZUKU_DENIED`.
7. Sin Shizuku corriendo (parar binder) → `SHIZUKU_UNAVAILABLE` + hint.

## 5. Fase 3a — resultados (2026-10-02, LG7n, Shizuku 13.6.0 oficial)

`uv run python scripts/fase3_check.py` → **OK fase3a**:
`open_app` lleva a la app de banco (verificado `HomeActivity`);
`force_stop` la saca; `open_app` devuelve package/activity;
`screenshot` 720×1640 vía `takeScreenshot`; `shell` y método
desconocido → `METHOD_NOT_ALLOWED`.

Hallazgos (todos con fix aplicado y verificado):
- **`Shizuku.newProcess` no es público en API 13.x**: el camino es
  UserService (AIDL `IShellService` + `bindUserService`). Y la clase
  UserService debe extender **el Stub directamente** (Shizuku la
  instancia vía app_process y la castea a `IBinder`; extender `Service`
  da `ClassCastException`). Sin entrada `<service>` en el manifest.
- `force_stop` **no exige accesibilidad**: movido a `ShellActions`
  (puro Shizuku); `open_app`/`screenshot` sí la requieren. Sin
  accesibilidad, `open_app` da `ACCESSIBILITY_DISABLED` (verificado).
- Pre-check: mirar el proceso **`shizuku_server`** (root), no el manager
  (aparece/desaparece). Sin Doze-whitelist el server muere:
  `dumpsys deviceidle whitelist +moe.shizuku.privileged.api`.
- **SECURE_SURFACE sin disparar**: con `FLAG_SECURE` en ventana
  **propia**, `takeScreenshot()` tiene éxito (el sistema exime al
  mismo UID, igual que con el árbol). Hace falta una ventana segura
  **ajena** (bancaria/APK de prueba). Mapeo según contrato API.

## 3. Gotchas encontrados

- `settings put` del servicio **solo pega si `accessibility_enabled=1`
  se escribe antes**. Al revés, el `get` devuelve `null`.
- El serving de Shizuku reporta `OK (permiso)` aun siendo el clon
  Shizuku+ (`af.shizuku.plus.api`): `pingBinder()` + `checkSelfPermission()`
  responden. **No verificado con `newProcess` real** — queda para Fase 3,
  que instalará el oficial `moe.shizuku.privileged.api`.
- Tras renombrar el paquete hay que desinstalar el viejo
  (`adb uninstall dev.jev.jam` puede fallar si ya no está; inocuo).

## 6. ADB por Wi-Fi (canal estable, 2026-10-02)

El USB se cae cada minutos. Con el LG7n en la misma LAN que el PC:

```bash
adb tcpip 5555            # adbd pasa a TCP (requiere USB una vez)
adb connect 192.168.100.180:5555
# desenchufar el USB; queda solo el transporte Wi-Fi
adb devices               # 192.168.100.180:5555 device
```

Medido: shell `echo` 79–151 ms (vs 63 ms USB) — algo más lento pero
sin cortes. El puerto se pierde al reiniciar (repetir `tcpip` por USB).
Si hay 2 transportes, prefijar `-s 192.168.100.180:5555`.

## 7. Fase 4 — MCP server + normalizer (2026-10-02, LG7n por Wi-Fi)

`JEV_TOKEN=… uv run python scripts/fase4_check.py` → **OK fase4**.
Cliente MCP por stdio contra `server.py`: `device_status` →
`open_app(<pkg-banco>)` verificado → `read_screen` (58/134 candidatos,
sin decoración) → `tap_text("<texto-búsqueda>")` → `via=gesture`
(el campo no es clickable: cae al fallback, verificado en app real) →
`read_screen` (EditText de búsqueda enfocado) → `type_text("<texto-prueba>")`
→ `chars=N`.

Latencias reales por tool (Wi-Fi, incluyen forward):
`device_status` 1978 ms · `open_app` 3064 ms (poll de foreground) ·
`read_screen` 425 ms · `tap_text` 3192 ms (dump interno + gesto) ·
`type_text` 604 ms. El `tap` por selector paga un `dump_ui` interno:
en el bucle Jev preferir `tap_node` (AGENTS §5.13).

Fixes: `mcp>=1.8,<2` (v2 renombra FastMCP→MCPServer); `pytest.ini`
`pythonpath=["src"]`; import relativo en `tools/_base.py`.

## 8. v5 director-client — resolver ciego + clipboard (sin Android Studio)

Vía elegida para `set_clipboard` (§4.1): método Jam `set_clipboard`
(`ClipboardManager.setPrimaryClip` por la propia app, sin Shizuku, sin
grant, scope `ui`); lectura por host `adb shell dumpsys clipboard`.
Prohibido: `adb shell input text`, `service call clipboard` frágil,
`shell` on-device (sigue `METHOD_NOT_ALLOWED` hasta Fase 6). Mientras la
app no exponga el método, el wrapper host falla honesto
`CLIPBOARD_UNSUPPORTED(jam-api-missing)` y el director usa `type_text`.

```bash
cd mcp-server && uv run pytest -q
# 148 en verde (loop.py congelado + tests/test_director_*.py v5 +
# test de forwarding de `package` en `open_url` tras `bd1f5a4`)

# Greps de cero-acoplado (src/ debe dar vacío / exit 1):
grep -rniE 'whatsapp|contact_name|verify_chat|wrong_chat' src/ || true
grep -rn 'ask_decision' src/jev_mcp/tools/ src/jev_mcp/director.py || true
```

# Manual contra Jam (requiere forward + token; sin Android Studio):

```bash
adb forward tcp:38472 tcp:38472
JEV_TOKEN=... python3 -c "import json,websocket"  # o wscat
# hello -> {"id":"<uuid>","method":"hello","params":{"protocol_version":1,"client_version":"0.1.0","token":"<bearer>","client":"jev-mcp/0.1.0"}}
# set_clipboard -> {"id":"<uuid>","method":"set_clipboard","params":{"text":"https://example.com/n/abc"}}
# espera {"ok":true,"result":{"chars":N}}
# verifica: adb shell dumpsys clipboard | grep -m1 https
```

## 9. Corridas recientes v4–v5 (2026-10-05/07, solo metadatos)

Bancos: KJ5 por Wi-Fi (loop S1/S2) + A10 por USB (`e03638e5`, Android 10,
720×1440, solo USB) para director v5. Sin texto sensible: goals genéricos
en inglés, payloads como `len`/`sha256`, paquetes solo como valores
runtime del forense citado. Costos = S1 Jev (`$0.042` in / `$0.00` out
por MTok, normativo) + S2 vía OpenRouter (misma key);
cada llamada loguea `[COST]` + `cost_usd` por paso.

| Goal (generic, EN) | Result | Wall | Cost | Forense |
|---|---|---|---|---|
| Send a short text to a known contact (text len 10, `sha256:0b894166…`) | SENT, verified on-screen | ~84.9 s | ~$0.0038 | `mcp-server/logs/run-rupa-1791164922.jsonl` (25 steps) |
| Send a short text to a known contact (text len 10, `sha256:0b894166…`, STALE-retry) | SENT, verified on-screen (`stale_recovered` ×1) | ~22 s | ~$0.0023 | `mcp-server/logs/run-1791243623.jsonl` (12 steps) |
| Open the clock app and list alarms (read-only) | OK, read verified | seconds | <$0.0001 | `mcp-server/logs/run-clock-alarms-1791164291.jsonl` (+ `…369`, `…417` re-taps `via=action_click`/`gesture`) |
| Describe visible gallery folders (read-only) | OK (folder lens only, no media opened) | 2.3 s | $0 | `logs/run-fossify-gallery-1791341893.jsonl` |
| List alarms (volatile screen, STALE-loop → text-tap fix) | OK | 5.7 s | ~$0.000054 | `logs/run-fossify-clock-1791341904.jsonl` |
| Navigate to Download and list items (incl. scroll) | OK (header lens 13, 2 folders + 9 files observed) | 9.1 s | ~$0.000133 | `logs/run-fossify-files-1791341918.jsonl` |
| Compute a 3-digit × 2-digit product (label-guard vs `9`/`×` confusion) | OK, double-snap verified (display lens 6) | 15.5 s | ~$0.000311 | `logs/run-fossify-calc-1791341959.jsonl` |
| List songs (permission dialog accepted, playback omitted) | OK (track lens only) | 5.6 s | ~$0.000104 | `logs/run-fossify-music-1791341936.jsonl` |
| Read battery level in system settings | OK (level lens 4, `avg_tap_ms 84.6`) | ~23.1 s total | ~$0.00067 | `logs/run-20261006-204303.jsonl` (`summary_b`) |
| Compute a division on stock calculator (redo) | BLOCKED by environment (`summary_b_redo ok_all: false`) | n/a | $0 | `logs/run-20261006-204449-calc.jsonl` (B1 no certificable) |
| Multi-app: copy a video link, paste into a downloader site, start download | BLOCKED honest (`verify_download ok: false`, `DOWNLOAD_NOT_STARTED`; `INPUT_UNFOCUSABLE` ×4 + `CLIPBOARD_EMPTY` + `CONVERT_UNRESPONSIVE` intermedios) | n/a | ~$0.0011 | `logs/run-20261007-yt-brave.jsonl` (25 phases) |

Notas: Fossify 5/5 total ~$0.0006 (v2 finales; v1 con fallos honestos
`STALE`/`NO_TARGET`/display erróneo conservados como historial).
Detalle por tarea en `docs/specs/fossify-random.md`. pytest vigente:
**148 en verde** (`cd mcp-server && uv run pytest -q`).

## 10. Intent 1-salto + `open_url` con `package` (2026-10-07, A10 USB, solo metadatos)

Banco: A10 por USB (serial runtime en forense, Android 10, 720×1440).
Sin texto sensible: goals genéricos en inglés, URLs como `host` +
`via` + `wall`, paquetes destino solo como valores runtime del forense
citado (nunca defaults del repo). `hello` request = objeto
`WsRequest{id, method, params}` con `protocol_version` + `client_version`;
respuesta plana `{ok, protocol_version, app_version, scopes}` (PROTOCOL
§2). Costo $0 (sin LLM, sin `[COST]` S1/S2).

| Goal (generic, EN) | Result | Wall | Cost | Forense |
|---|---|---|---|---|
| Open a short video link via `open_url` without `package` (system resolution) | OK `via: startActivity` → chooser `ResolverActivity` (multi-handler, expected) | ~12.8 s total (poll foreground) | $0 | `logs/run-intent-20261007-130650.jsonl` (`testA_open_url` + `testA_verify`) |
| Resolve the same chooser with two taps (select handler + `Once`) | Chooser persists after first tap (`via: gesture` ×2); no default changed (honest, no 1-hop claim) | ~16.0 s | $0 | same jsonl (`A2_*`: `chooser` 25 nodes, `tap n_23` + `tap n_14`) |
| Open a search URL via `send_intent` `VIEW` (no `package`) | OK `via: startActivity` → browser foreground, results hint + query present (`has_resultado: true`) | ~13.2 s + re-poll 18.5 s | $0 | same jsonl (`testB_*`, `B2_*`: 40→500 nodes capped) |
| Open a short video link via `open_url` with `package` set (explicit component, 1 hop) | OK `{ok:true, verified:true, via:"startActivity-package", latency_ms:130.3}`, foreground = target app directly, no chooser | ~0.13 s call | $0 | `docs/BUILD.md` §9 (manual WS `127.0.0.1:38472`, token vía `run-as`; sin jsonl, latencia del `result`) |
| Open a short video link with unknown `package` | Honest `PACKAGE_NOT_FOUND` (shape validated, `getPackageInfo` miss) | ms | $0 | `docs/BUILD.md` §9 |
| Open a short video link with installed `package` without handler | Honest `INTENT_UNRESOLVED` (`resolveActivity` miss) | ms | $0 | `docs/BUILD.md` §9 |
| Open a short video link with `package=""` (prior behavior) | Foreground = `android/ResolverActivity` (chooser, expected) | s | $0 | `docs/BUILD.md` §9 |

Notas: `open_url(url, package="")` = resolución del sistema (chooser si
>1 handler); con `package` no vacío se valida forma `a.b.c`, se fija
componente explícito y el fallback Shizuku usa `am start -n
pkg/activity` (`via: shizuku-am`). Docstrings MCP 35/35 al estándar
5-secciones tras `bd1f5a4` (payloads ejemplo en inglés). App bajo
prueba: `dev.jev.jam` (Jam); `dump_ui` sin campo `secure` (contrato
vigente: superficie protegida solo como `SECURE_SURFACE` en
`screenshot`).

## 11. Robustez táctica P1+P2 en A10 (`e03638e5`, Android 10, 2026-10-10)

Banco: A10 USB `e03638e5`, Android 10 (SDK 29), 720×1440. APK debug
reconstruido con el fix e instalado (`adb install -r`); accesibilidad
activa; forward `tcp:38472`; token vía `run-as`
(`shared_prefs/jam_auth.xml` → `ws_token`). Sonda temporal (cliente `pkg/jam`):

1. `hello` → scopes `[read ui]`.
2. Para cada muestra: `dump_ui` (S_i) → esperar 3.5 s (ticks de reloj) →
   `type_text` sobre un nodo no enfocado. `NOT_FOCUSED` = snapshot fresco
   (el fix funciona); `STALE_SNAPSHOT` = caducado (bug).

| Build | Pantalla | Fresco | STALE |
|---|---|---|---|
| sin fix (filtro SystemUI) | Jam MainActivity (estática) | 3/3 | 0/3 |
| sin fix | Fossify Clock (viva) | 0/3 | 3/3 |
| fix SystemUI-only | Fossify Clock (viva) | 0/3 | 3/3 |
| **fix content-changed** | Fossify Clock (viva) | **3/3** | 0/3 |
| fix content-changed | Fossify Clock + `press_back` | 0/1 | 1/1 (control) |

**Hallazgo:** el reloj de la barra de estado (avanza por minuto) **no**
reproduce el fallo; el reloj con segundos de la **app** (Fossify Clock) sí,
y el filtro SystemUI-only **no** lo arregla. La corrección real es ignorar
`TYPE_WINDOW_CONTENT_CHANGED` en `onAccessibilityEvent` (ruido cosmético de
sistema y app) y confiar en `verifySame` como compuerta fina. El control de
cambio real (navegación) sigue dando `STALE_SNAPSHOT`.

**Calculadora (Fossify Math, rejilla densa `9`/`×`/`C`/`.`):** secuencia
`9 × 9 =` por `tap_node` con snapshot fresco por paso. Botones resueltos por
`via=action_click` (los propios nodos son clickables; el walk-up no se
ejercita aquí). El tap de `×` tras cambiar el display dio `STALE_SNAPSHOT`
(control correcto: el display cambió por un evento distinto de
content-changed). Walk-up y glifos quedan cubiertos por tests unitarios
(`ClickAncestorTest`, `TestFormatCandidateLabel`).

Estado de suites: `go test ./...` verde · `./gradlew testDebugUnitTest` 49
tests verde · `make audit-mcp` **11/11 PASS** (35 tools, 0 diffs de schema).
