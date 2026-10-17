# TASK_HISTORY.md — tareas cerradas con números reales (v1.0.2)

> Fuente única del historial de corridas. El `README.md` resume y enlaza aquí;
> ante discrepancia, **este archivo manda**. Solo filas con forense citado
> (`logs/` o `mcp-server/logs/`) y/o tabla en `docs/TESTING.md §9–10`.
> Nada inventado. 100% genérico: goals en inglés genérico, paquetes solo como
> valores runtime del forense citado, payloads como `len`/`sha256`, sin texto
> sensible, sin keys.

## 1. Bucle S1/S2 en KJ5 (histórico, loop congelado)

Fuente: `docs/TESTING.md §9` + `PLAN.md` Fase v5.

| Tarea (genérica, EN) | Resultado | Tiempo | Costo | Forense |
|---|---|---|---|---|
| Send a short text to a known contact (text len 10, `sha256:0b894166…`) — mensajería-A | SENT, verificado en pantalla (25 steps) | ~84.9 s | ~$0.0038 | `mcp-server/logs/run-rupa-1791164922.jsonl` |
| Send a short text to a known contact (text len 10, `sha256:0b894166…`, STALE-retry `stale_recovered` ×1) — mensajería-B | SENT, verificado en pantalla (12 steps) | ~22 s | ~$0.0023 | `mcp-server/logs/run-1791243623.jsonl` |
| Open the clock app and list alarms (read-only) | OK, read verified | segundos | <$0.0001 | `mcp-server/logs/run-clock-alarms-1791164291.jsonl` (+ `…369`, `…417` re-taps `via=action_click`/`gesture`) |

## 2. Director v5 en A10 USB — Fossify 5/5 (solo no-destructivo)

Fuente: `docs/TESTING.md §9` + `docs/specs/fossify-random.md §2–3`
(finales v2; v1 con fallos honestos `STALE`/`NO_TARGET`/display erróneo
conservada como historial en los mismos directorios).

| Tarea | Resultado real leído | Tiempo | Costo | Forense final |
|---|---|---|---|---|
| Describe visible gallery folders (read-only, folder lens, no media opened) | OK | 2.3 s | $0 (sin Jev: open+read) | `logs/run-fossify-gallery-1791341893.jsonl` |
| List alarms (volatile screen, STALE-loop → text-tap fix) | OK | 5.7 s | ~$0.000054 | `logs/run-fossify-clock-1791341904.jsonl` |
| Navigate to Download and list items (incl. scroll; header 13, 2 folders + 9 files observed) | OK | 9.1 s | ~$0.000133 | `logs/run-fossify-files-1791341918.jsonl` |
| Compute a 3-digit × 2-digit product (label-guard vs `9`/`×` confusion, double-snap verified) | OK | 15.5 s | ~$0.000311 | `logs/run-fossify-calc-1791341959.jsonl` |
| List songs (permission dialog accepted, playback omitted, track lens only) | OK | 5.6 s | ~$0.000104 | `logs/run-fossify-music-1791341936.jsonl` |
| **Fossify 5/5 total** | **todo OK** | **~38 s** | **~$0.0006** | 5 jsonls v2 arriba |

## 3. Director v5 en A10 USB — batería, bloqueos honestos e intents

Fuente: `docs/TESTING.md §9–10` + `docs/BUILD.md §9`.

| Tarea (genérica, EN) | Resultado | Tiempo | Costo | Forense |
|---|---|---|---|---|
| Read battery level in system settings (level lens, `avg_tap_ms 84.6`) | OK | ~23.1 s total | ~$0.00067 | `logs/run-20261006-204303.jsonl` (`summary_b` + `end` `jev_cost 0.00067`) |
| Compute a division on stock calculator (redo; taps verificados por display) | **BLOQUEO por entorno** (`summary_b_redo ok_all: false`, `avg_tap_ms 69.7`, `avg_s1_ms 1589.5`) → B1 no certificable | n/a | $0 | `logs/run-20261006-204449-calc.jsonl` |
| Multi-app: copy a video link, paste into a downloader site, start download | **BLOQUEO honesto** (`verify_download ok: false`, `DOWNLOAD_NOT_STARTED`; `INPUT_UNFOCUSABLE` ×4 + `CLIPBOARD_EMPTY` + `CONVERT_UNRESPONSIVE` intermedios; 25 phases) | n/a | ~$0.0011 | `logs/run-20261007-yt-brave.jsonl` |
| Open a short video link via `open_url` without `package` (system resolution) | OK → chooser `ResolverActivity` (multi-handler, expected) | ~12.8 s total | $0 | `logs/run-intent-20261007-130650.jsonl` |
| Resolve the same chooser with two taps (select handler + `Once`) | Chooser persists after first tap (`via: gesture` ×2); no default changed (honest, no 1-hop claim) | ~16.0 s | $0 | mismo jsonl (`A2_*`) |
| Open a search URL via `send_intent` `VIEW` (no `package`) | OK → browser foreground, results hint + query present | ~13.2 s + re-poll 18.5 s | $0 | mismo jsonl (`testB_*`, `B2_*`) |
| Open a short video link via `open_url` with `package` set (explicit component, 1 hop) | OK `{ok:true, verified:true, via:"startActivity-package", latency_ms:130.3}`, foreground directo, no chooser | ~0.13 s call | $0 | `docs/BUILD.md §9` (manual WS, sin jsonl) |
| Open a short video link with unknown `package` | Honesto `PACKAGE_NOT_FOUND` | ms | $0 | `docs/BUILD.md §9` |
| Open a short video link with installed `package` without handler | Honesto `INTENT_UNRESOLVED` | ms | $0 | `docs/BUILD.md §9` |

## 4. Techo de costo

Costo por corrida **<$0.003** en todas las filas con LLM (las de director
puro/intents son $0). Tarifas: Jev `$0.042` in / `$0.00` out por MTok
(normativo); S2 por env (placeholder ajustable). Cada paso loguea `[COST]`.

## 5. Cotidiano 2026-10-10 en A10 USB (solo lectura + 1 tap omitido por bloqueo)

Fuente: `logs/run-20261010-011841-cotidiano.jsonl` (15 pasos) + reintentos
YouTube en stdout (`open_url` ×3 OK, `read` 34 nodos, resolves S1 ×4
`envelope S1 no-JSON`). Banco 5002E Android 10 USB `e03638e5`, binario Go
por stdio, pantalla ON, forward `tcp:38472`. Sin commits, sin push,
sin descargas, sin crear alarma/mensaje.

| Tarea (genérica, EN) | Resultado | Tiempo | Costo | Forense |
|---|---|---|---|---|
| Open a video link via `open_url` with explicit client `package` (1 hop, no chooser) | OK ×3 (`via: startActivity-package`, 73–199 ms; foreground morphe `MainActivity` en reintentos; primer intento cayó a `systemui` transitorio) | ~0.07–0.20 s/call | $0 | `logs/run-20261010-011841-cotidiano.jsonl` (`youtube/open_url`) |
| Resolve Play/Pause or Share button via Jev S1 on the player screen (34 nodes) | **BLOQUEO honesto** (`envelope S1 no-JSON` ×5, 408–1354 ms; endpoint OpenRouter 200 vacío en debug sintético n=2/10/34) → **sin tap ciego, sin descarga** | n/a (Jev 0.4–1.4 s) | $0 afectable | mismo jsonl (`youtube/resolve_element` FAIL) |
| Open the messages app and resolve a field via Jev S1 (read-only, no create) | OK resolve (`idx 0 conf 0.86`, 415 ms) + persistencia por re-`read` (162 ms); **NO tap/type, NO crear alarma/mensaje** | ~6 s (`open_app` 5546 ms poll + reads) | ~$0.00004 (`[COST]` S1) | mismo jsonl (`fossify/*`) |
| Verify a clean open-source APK is installed via `list_packages` (no install/uninstall) | OK (130 pkgs; fossify 8, morphe 2, rvx 1, seal 0; 104–115 ms) | ms | $0 | mismo jsonl (`paquetes/*`) |

## 6. Revancha 2026-10-15 en A10 USB — `resolve_element` (36.ª tool) + `ACTION_PASTE`

Cierra el bloque de 3 pasos (Paso 2a tool MCP, Paso 2b fallback paste).
Banco 5002E Android 10 API 29 `e03638e5`, APK debug reinstalada, accesibilidad
re-enlazada, Shizuku `shizuku_server` vivo, forward `tcp:38472`, `jav` por
stdio con `OPENROUTER_API_KEY` del `.env` (S1 real, sin `mock`). Sin commits,
sin push, sin acciones destructivas.

| Paso (genérico, EN) | Resultado | Evidencia |
|---|---|---|
| `read_screen` en Fossify Math | OK; `snapshot_id 1117`, `raw_count 42`, `candidates 24`, `screen_fingerprint a7e5ba17f555`, `tried_node_ids []` | tool MCP (JSON-RPC stdio) |
| `resolve_element{screen_goal_en:"Tap the number 7 button", tau:0.70}` | OK `verified:true`; `idx 7`, `node_id "n_26"`, `conf 0.88`, `snapshot_id 1118`, `fallback_required:false` | tool MCP (S1 real) |
| `tap_node{node_id:"n_26", snapshot_id:1118}` | OK `via:"action_click"` (no gesture) | tool MCP |
| `read_screen` (post-tap) | `snapshot_id 1119`; `diff_since_last.changed:true`, `prev_snapshot_id 1117`, `added_labels ["[n_16] TextView \"7\""]`, `removed_labels ["[n_16] TextView \"0\""]` → display 0→7 | tool MCP |
| `tap_node` sobre nodo **no-clickable** `n_16` (Label) + `read_screen` | OK `via:"gesture"`; `diff_since_last.changed:false`; `tried_node_ids ["n_16"]` → memoria de probados **por fingerprint** confirmada | tool MCP |

Nota: `tried_node_ids` es **fingerprint-scoped** — tras un tap que muta la UI
(0→7) el fingerprint cambia y la lista arranca limpia; solo se puebla mientras
el fingerprint es estable (fila 5). `resolve_element` dumpea internamente
(`snapshot 1118`) pero **no** alimenta `uitrack` (no observa): el diff de la
fila 4 compara contra la última `read_screen` (1117), que es lo correcto.

Verificación de suites tras el hito: `gofmt -l cmd/ pkg/` vacío ·
`go test ./...` verde · `./gradlew :app:testDebugUnitTest` **59/59** ·
`go run ./cmd/audit-mcp` **11/11** (`tools-count-36`).


## 7. Fase 6a 2026-10-16 en A10 USB — `get_audit` (37.ª tool) + Kill Switch

Auditoría en dispositivo y parada dura del servidor (AGENTS §3.8). Sin LLM,
sin Shizuku, sin acciones destructivas (a11y apagada). El Kill Switch **no**
se dispara aquí: rotaría el token del operador a mitad de sesión.

| Paso (WS directo, `adb forward tcp:38472`) | Resultado | Evidencia |
|---|---|---|
| `hello{protocol_version:1, token}` | `ok:true`, `scopes ["read","ui","admin"]` | respuesta plano (sin `id`) |
| `get_battery` / `get_device_info` | `ok:true` (carril nativo N0) | tool MCP |
| `get_foreground` (a11y apagada) | `ok:false` `ACCESSIBILITY_DISABLED` (honesto) | tool MCP |
| `get_audit{limit:50, since_seq:0}` | `total_buffered 4`, `returned 4` | ring en vivo |

Entradas devueltas (`args_sha256` = 16 hex, `origin` `loopback`):

| seq | method | scope | result |
|---|---|---|---|
| 1 | `hello` | `auth` | `OK` |
| 2 | `get_battery` | `n0` | `OK` |
| 3 | `get_device_info` | `n0` | `OK` |
| 4 | `get_foreground` | `read` | `ACCESSIBILITY_DISABLED` |

Sanity: el token no aparece en el JSON de `get_audit` y los 4 `args_sha256`
miden 16; `get_audit` **no** se auto-incluye (se registra tras responder).
Kill Switch: tile registrado con `BIND_QUICK_SETTINGS_TILE` (`dumpsys
package`) y notificación `id=1` con `actions=1` → `"Kill Switch"`
`PendingIntent startService` (`dumpsys notification`); disparo en vivo
queda como prueba manual del operador.

Verificación de suites tras el hito: `gofmt -l cmd/ pkg/` vacío ·
`go test ./...` verde · `./gradlew :app:testDebugUnitTest` **64/64** ·
`go run ./cmd/audit-mcp --bin dist/jav-linux-amd64` **11/11** (`tools-count-37`).

## 8. Fase 6b 2026-10-16 en A10 USB — `shell`+grant+N2 + `adb_shell` (38.ª tool)

Cierre de Fase 6 (AGENTS §3.6/§3.7): `shell` ya no es `METHOD_NOT_ALLOWED`;
se ejecuta por Shizuku (UID `shell`) con rate 5/s, denylist de irreversibles
y grant interactivo del operador; N2 (`settings_put` secure/global,
`get_storage`/`get_cpu` `detail=fine`) vivo. Sin LLM. La denylist detuvo
`rm -rf /` antes de tocar el dispositivo; el grant en vivo requiere tap
humano en la notificación (no automatizado).

| Paso (WS directo, `adb forward tcp:38472`) | Resultado | Evidencia |
|---|---|---|
| `get_storage{detail:"fine"}` | `ok:true verified:true` | `fine.via=shizuku exit=0 entries=2` |
| `get_cpu{detail:"fine"}` | `ok:true verified:true` | `processors=4 fine.via=shizuku exit=0 procs=10` |
| `settings_put{global, airplane_mode_on, "0", confirm:false}` | `ok:true verified:false` | `planned:true`, `value_sha256` |
| `adb_shell{cmd:"rm -rf /", confirm:false}` | `ok:true verified:true` | `planned:true`, `preview.reason=denylist_irreversible`, `cmd_sha256` |
| `adb_shell{cmd:"pm uninstall dev.k4wai1.jav"}` | `ok:false` `SHELL_DENYLIST` | sin tocar el dispositivo |
| `adb_shell{cmd:""}` | `ok:false` `VALIDATION_ERROR` | `cmd vacío` |
| `get_foreground` / `read_screen` | `ok:true` (tras re-enlazar a11y) | tool MCP |

Sanity: `rm -rf /` se detiene en la compuerta `planned` (el operador no
aprobó confirm); el self-harm se rechaza por política (`SHELL_DENYLIST`)
antes de abrir shell; el grant bloquea hasta 60 s y emite `shell_grant`
por WS al aprobar.

Verificación de suites tras el hito: `gofmt -l cmd/ pkg/` vacío ·
`go test ./...` verde (`pkg/tools` 38) · `./gradlew :app:testDebugUnitTest`
**73/73** · `go run ./cmd/audit-mcp --bin dist/jav-linux-amd64` **11/11**
(`tools-count-38`).

## 9. Fase 2b 2026-10-16 en A10 USB — WSS tailnet + cert self-signed + token en Keystore

Cierre del backlog 2b. Token del operador cifrado en reposo (AES-GCM/256 en
`AndroidKeyStore`, con migración suave desde el `ws_token` plano), lockout
5 fallos/60 s → 5 min por `origin`, certificado X.509v3 autofirmado
(`CN=jav.local`, RSA-2048, BouncyCastle local) servido en un 2.º listener
**WSS** atado a la IP tailnet (`100.64.0.0/10`, `ConnectivityManager.NetworkCallback`),
y pinning TOFU en el cliente Go (`JAV_CERT_FINGERPRINT`, tiempo constante,
`CERT_MISMATCH` honesto).

En vivo (`e03638e5`, WS vía `adb forward`): `shared_prefs/jam_auth.xml` pasó
de `ws_token` a `ws_token_enc` (mismo token, `.env` intacto); `hello` →
`ok` `scopes=[read ui admin]`; `get_audit(limit=5)` → `total=1 returned=1`.
`logcat` de la ROM viene vacío (`logcat -d` → 0 líneas), así que la
verificación se hizo por efecto observable. El banco no tiene IP tailnet, así
que el listener WSS no se probó en vivo (se cubre por tests JVM + test Go del
pinning); no se bindeó a la LAN por AGENTS §3.1.

Verificación de suites tras el hito: `gofmt -l cmd/ pkg/` vacío ·
`go test ./...` verde (`pkg/jam` += `tls_test.go`, `live_test.go` gated) ·
`./gradlew :app:testDebugUnitTest` **88/88** (antes 73; +7 `AuthLockoutTest`,
+5 `TlsCertStoreTest`, +3 `TailnetDetectorTest`) ·
`go run ./cmd/audit-mcp --bin dist/jav-linux-amd64` **11/11** (`tools-count-38`).

## 10. Prueba de campo v1.2.1 — `jav pair` + sesión persistente (2026-10-16)

Primer dogfooding **remoto sin USB** del binario v1.2.1: VPS
`racknerd-54f9d67` (`100.77.106.123`) → **TECNO Pova 4**
(`100.105.124.102`) por `wss://…:38472/` (Tailnet, `tailscale ping` ≈ 176 ms).

| Tarea | Resultado | Números | Evidencia |
|---|---|---|---|
| `jav pair 100.105.124.102 <token>` (hello + `get_device_info` + Auto-TOFU) | OK: **TECNO LG7n (SDK 31)**, `cert_fingerprint 036898d996256f8e…`, `~/.config/jav/config.json` `0600` | **~0.98 s** | `~/.config/jav/config.json` |
| Ráfaga n=10 mixta (sesión persistente) | **0 `BUSY`**, 0 errores, `hello` único para la sesión | avg **320 ms** (min 132, max 875) | `get_audit` (`origin` VPS) |
| 20× tools ligeras | `get_battery` estable | avg **142 ms** | medido en vivo |
| `device_status` ×10 consecutivos | **0 `BUSY`**, `isError=0` | avg **336 ms** | `get_audit` |
| Antes/después | persistente vs `dial`+`hello` por llamada | **989 ms → 320 ms** (`hello` 11 → **0**) | `PERFORMANCE.md §8` |
| Auditoría | todas las entradas `origin=100.77.106.123`, **nunca** loopback | scopes `auth/n0/ui/read/admin` | `get_audit` |

**Causa raíz del `4001: BUSY`:** cierre TCP abrupto (solo FIN, sin frame
`close`); el teléfono (single-client) no dispara `onClose` hasta su timeout de
conexión perdida (~2 min) y deja el slot ocupado. **Fix:** `Client.Close` con
handshake de cierre ordenado (frame `close` + eco, `closeTimeout` 500 ms); el
slot se libera de inmediato (verificado 10/10 sin `BUSY`).

**Verificación de suites tras el hito:** `gofmt -l cmd/ pkg/` vacío ·
`go vet ./...` limpio · `go test ./...` verde (salvo el preexistente
`pkg/normalizer`, dependiente de `logs/run-*.jsonl` gitignored) · `make build` ·
`go run ./cmd/audit-mcp --bin dist/jav-linux-amd64` **12/12 PASS**.
Tests Go nuevos en `pkg/jam`: `TestPersistentReusesOneHello`,
`TestReconnectAfterServerDrop`, `TestResetSharedSendsCloseFrame`
(harness WS single-client en `close_test.go`).

## 11. Certificación viva 38/38 + micro-opt clipboard + fix `planned` (2026-10-17)

Sprint post-v1.2.5 sobre **TECNO LG7n** (app v1.2.5 CI en foreground, Shizuku
root, accesibilidad activa, **sin USB**): certificación de las 38 tools desde
el binario stdio local (`dist/jav-linux-amd64`) por WSS/Tailnet, micro-opt de
`get_clipboard_device` y hallazgo de contrato en `adb_shell`.

| Tarea | Resultado | Números | Evidencia |
|---|---|---|---|
| Certificación 38/38 (stdio→WSS) | 40 llamadas: **29 OK + 11 compuertas honestas**, 0 timeouts, 0 colgues | ligeras **32–33 ms** calientes | tablas `PERFORMANCE.md §10` |
| `planned:true` sin ejecutar | 8 tools críticas devuelven `preview` y no actúan | `settings_put` 480 · `add_contact` 182 · `create_event` 92 · `reply` 31 · `media_control` 28 · `take_photo` 77 · `adb_shell rm -rf /` 982/19 ms | payloads crudos |
| `adb_shell` hostil | self-harm → `SHELL_DENYLIST` (461 ms, sin grant); `rm -rf /` + confirm → **60.4 s** de bloqueo → `SHELL_DENIED` | 1ª vez que el grant bloquea de verdad con un cliente stdio | forense `get_audit` |
| Recursos + prompts | 6/6 resources + 3/3 prompts OK | 966–18 018 chars | `resources/read`, `prompts/get` |
| `resolve_element` S1 en vivo | `idx`+`conf` con coste real | 3 052 ms · **$0.000053** | `evidence.cost` |
| **Fix de contrato** | `jamCall` devolvía `verified:true` con `planned:true` (solo `jamCallLatency` lo mapeaba) → corregido | retest: `ok:true verified:false planned:true` | `pkg/tools/helpers.go` |
| Micro-opt clipboard (Kotlin) | `appops` + `apkPath` cacheados (`@Volatile`); build 94/94 + APK OK; **instalado por USB** y remedido | pre-opt **2 168–2 679 ms** → post-opt caliente **avg 1 858 ms** (min 1 650; primera de ráfaga 3.3–3.9 s); clip sobrevive (0 `Clearing clipboard`) | `docs/BUILD.md §31` |
| Cierre del `ADB_FAILED` | `list_packages` con USB reconectado | **347 ms**, 3 pkgs (`*whatsapp*`) | certificación 38/38 sin errores de entorno |
| Diagramas + README | Archify 4/4 gates ×2 + SVG pastel XML-validados embebidos | `docs/diagrams/*.html`, `docs/assets/*.svg` | commit del sprint |

**Nota honesta**: `list_packages` falló `ADB_FAILED` porque usa el adb del
host por diseño y el cable estaba desconectado; `list_notifications`,
`media_state` y `get_location` devolvieron sus caps ausentes con hint — cero
errores fingidos.
