# Jav 🛠️ — full-control Android MCP runtime, no root

[![Moe Counter](https://count.getloli.com/get/@jav-k4wai1?name=jav-k4wai1&theme=rule34&padding=3&offset=0&align=top&scale=1&pixelated=1&darkmode=1)](https://github.com/k4wai1)
[![Support me on Ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/kwai1)
[![License: GPL-3.0](https://img.shields.io/badge/license-GPL--3.0-blue.svg)](LICENSE)

<p align="center"><img src="docs/assets/icon.png?v=1.2.2" width="140" alt="Jav logo" /></p>

> **English first, español después.** Normative detail lives in `AGENTS.md`,
> `PROTOCOL.md`, `ARCHITECTURE.md`, `PLAN.md` and `docs/specs/`.

---

# 🇬🇧 ENGLISH

## What is Jav

**Jav is a full-control Android MCP runtime without root.** An on-device app
(**Jav**, `dev.k4wai1.jav`) exposes the screen via `AccessibilityService` and
privileged actions via **Shizuku** (started by the user) to a Go MCP server on
the PC (`jav`, `cmd/jav`, stdio).

Two clearly separated roles:

| | **Jav** (this repo) | **Director** (external, not part of Jav) |
|---|---|---|
| What | Go MCP server (`cmd/jav`) + Android app `dev.k4wai1.jav` | OpenCode / Claude / Cursor / operator |
| Does | exposes 38 atomic MCP tools, runs no loops and no internal planner | reads each screen, picks one atomic tool per step, verifies the effect |
| Tactical help | serves **`resolve_element`** (blind S1 Jev resolver) | decides goals, gates, and approves previews |

Jav never loops, never plans and never invents coordinates. The Director holds
the loop; Jav holds the device.

## Quickstart

```bash
# 1. Install the Go server (PC)
curl -fsSL https://raw.githubusercontent.com/k4wai1/jav/master/install.sh | sh
#    or: VERSION=v1.2.2 sh install.sh

# 2. Install the companion APK (Releases) and enable accessibility (once)
#    download jav-companion.apk from the latest GitHub Release, then:
adb install -r jav-companion.apk
#    Settings → Accessibility → enable Jav; copy the token shown in the app.

# 3. Start Shizuku (the USER starts it; the app only requests API_V23)

# 4. Pair once — no .env, no restart (Auto-TOFU cert pinning included):
jav pair <PHONE-TAILNET-IP> <TOKEN>   # remote → wss://<ip>:38472/
#    over USB loopback:  jav pair usb <TOKEN>
#    writes ~/.config/jav/config.json (chmod 0600) and pins the cert.

# 5. Point your Director (OpenCode/Claude/Cursor) at `jav` over stdio:
#    { "command": ["jav"] }   # no environment block needed
```

From source instead of Releases:

```bash
make build                 # dist/jav-linux-amd64
cd android-app && ./gradlew :app:assembleDebug
```

## Tools — 38, in 4 groups

Every tool returns `{ok, verified, evidence, hint}`. `verified: true` only with
real post-verification, never on "command sent". `tools/list` carries a compact
1–2 line description per tool; the full 7-section spec loads **on demand** as an
MCP Resource (`android://tool/<name>`, `android://tools/<group>`, index
`android://tools/catalog`). Startup measured with a real tiktoken tokenizer:
**~1.8k tokens of cognitive load** (instructions + 38 compact descriptions) and
**~3.5k tokens total** (includes the fixed MCP schema for 38 tools, not reducible
without consolidating) — so ~8.8k before v1.2.0. See
[`docs/benchmarks/PERFORMANCE.md §9`](docs/benchmarks/PERFORMANCE.md).

| Group | Tools |
|---|---|
| **state** | `device_status`, `get_foreground`, `list_packages`, `get_battery`, `get_memory`, `get_storage`, `get_cpu`, `get_device_info`, `get_audit` |
| **ui** | `read_screen`, `tap_node`, `tap_text`, `type_text`, `scroll`, `press_back`, `press_home`, `wait_for_text`, `open_app`, `close_app`, `screenshot` |
| **native** | `settings_get`, `settings_put`, `open_url`, `send_intent`, `get_clipboard_device`, `get_app_usage`, `list_contacts`, `add_contact`, `list_events`, `create_event`, `list_notifications`, `reply_notification`, `media_state`, `media_control`, `get_location`, `take_photo`, `adb_shell` |
| **resolve** | `resolve_element` (blind S1 resolver: `screen_goal_en` + `tau` → `idx`/`node_id`/`conf`/`snapshot_id` or the Sovereign fallback) |

Lanes: **N0** native, no new grants · **N1** native with user grants
(advertised in `hello.caps`) · **N2** Shizuku/`shell`, gated by the irreversible
denylist + interactive grant (1 cmd / 5 min / 30 min).

Sensitive tools (`settings_put`, `send_intent`, `add_contact`, `create_event`,
`reply_notification`, `media_control`, `take_photo`, `adb_shell`) never run on
first call: they return `{planned:true, preview, hint}` with `verified:false`
and only execute after `confirm:true`.

## What changed in v1.2.2

- **New app icon (Android + lightning).** Refreshed `docs/assets/icon.png`
  (1000×1000) and regenerated all launcher mipmaps `ic_launcher[_round]`
  (mdpi 48 / hdpi 72 / xhdpi 96 / xxhdpi 144 / xxxhdpi 192; round with a
  circular alpha mask). The manifest (`android:icon`/`android:roundIcon`) and
  the in-app header logo (`@mipmap/ic_launcher_round`) pick it up automatically.
  No new dependencies; `versionName 1.2.2` / `versionCode 4`.

## What changed in v1.2.1

- **Frictionless pairing, no `.env`, no restart.** New **`jav pair
  <ip-or-url> <token>`** connects once (hello + `get_device_info`), performs
  **Auto-TOFU** on `wss://` (captures and pins the cert SHA-256) and writes
  `~/.config/jav/config.json` (`chmod 0600`). The MCP server re-reads the
  config **hot**, so registering `"command": ["jav"]` is enough. Priority per
  field: env (`JAV_*`) → `config.json` → default.
- **Persistent session: ~1.3 s → ~0.2 s per call.** `pkg/jam` keeps ONE
  shared WebSocket and serialises calls with a mutex, so a burst of tool calls
  yields a **single `hello`** (was 1 per call). Measured on a real TECNO over
  WSS/Tailnet: **989 ms → 320 ms** avg (light tools **~140 ms**), **0 extra
  `hello` frames** vs **11**. Automatic **1 reconnect + retry** on transport
  errors.
- **Graceful WebSocket close** (frame `close` + peer echo, ~500 ms bound)
  added to `Client.Close`: fixes the `4001: BUSY` seen with abrupt TCP closes
  (the phone kept its single-client slot until its ~2 min timeout).
- AI keys also live in `config.json` (`openrouter_api_key`, `ai_base_url`,
  `ai_api_key`, `ai_model`) with the same env → config priority.

## What changed in v1.2.0

- **~80% fewer startup tokens.** 38 compact descriptions in `tools/list` +
  full 7-section specs on demand as Resources (`android://tool/<name>`);
  compacted `initialize` instructions (≤220 words). New `audit-mcp` check
  `token-budget-startup` certifies the budget.
- **Per-session cost summary, no per-call spam.** `pkg/cost` is silent by
  default (`JAV_DEBUG_COST=1` to trace) and accumulates
  `{jev_cost_usd, s2_cost_usd, total_cost_usd, calls}` delivered in
  `evidence.cost` of `device_status` / `resolve_element`.
- **Identity consolidated** as **`Jav`** / `dev.k4wai1.jav` (v1.0.0), with the
  self-signed TLS cert unified to `CN=jav.local`.
- **Phase 2b** (WSS tailnet + cert + token in Keystore + lockout) and
  **Phase 6** (audit ring 500 + Kill Switch + shell grant/denylist + N2) shipped.
- **New icon (1000×1000) and native UI polish**: launcher mipmaps, header logo,
  semantic `values`/`values-night` colors — zero new dependencies.
- **Docs cleanup**: historical specs moved to `docs/specs/archive/`; live
  contract in `docs/specs/`.

## Real runs with numbers (summary)

> Benchmarks own the numbers:
> [`docs/benchmarks/PERFORMANCE.md`](docs/benchmarks/PERFORMANCE.md) (per-tool
> latencies on real hardware) and
> [`docs/benchmarks/TASK_HISTORY.md`](docs/benchmarks/TASK_HISTORY.md) (closed
> tasks with wall/cost/forensics). This table only summarizes.

| Area | Figure (measured) |
|---|---|
| Perception `dump_ui` | ~2 ms/node (13n/40 ms, 66n/106 ms, 124n/264 ms; ~1 s worst @500) |
| tap (`ACTION_CLICK` first) | ~70 ms |
| S1 Jev | ~1.6 s |
| N0 native (Go e2e) | ~50–190 ms/tool |
| Persistent session (v1.2.1, WSS/Tailnet) | **~140 ms** light / **~320 ms** avg per call; **1 `hello`** per burst |
| Cost ceiling | **<$0.003** per run |

Host: Debian, Go, MCP stdio; `dump_ui` is ~16× faster than `uiautomator dump`.

## Security

- **Scopes:** `read` (dump/screenshot) · `ui` (tap/type/scroll/back, grantless
  `open_app`) · `shell` (grant-gated, irreversible denylist + `confirm`) ·
  `admin` (token/audit/settings). Token mandatory on every bind (loopback
  included); lockout 5 fails/60 s → 5 min; 4 MiB frame; 50 req/s (shell 5/s).
- **Confirm:** messaging, paying, deleting, account/permission, photo, media
  stop and settings writes are critical: without `confirm:true` they are planned
  without executing (`planned:true` + `preview`).
- **Forensics:** `logs/run-<ts>.jsonl` per step (never raw sensitive text) plus
  fail-fast `run_signature`.
- **Kill switch:** Quick Settings tile + notification action (revoke tokens,
  stop the server). Push/pull only under `/sdcard/Download/jav-mcp/`.

## 👨‍💻 Developer

**[k4wai1](https://github.com/k4wai1)** — if Jav saved you time, consider
[buying a coffee](https://ko-fi.com/kwai1). Contributions via PRs welcome.

## 📜 License

This project is licensed under the **GNU General Public License v3.0** — see the
[LICENSE](LICENSE) file for details.

---

# 🇪🇸 ESPAÑOL

## Qué es Jav

**Jav es un runtime MCP de control integral de Android sin root.** Una app en el
dispositivo (**Jav**, `dev.k4wai1.jav`) expone la pantalla por
`AccessibilityService` y las acciones privilegiadas por **Shizuku** (lo arranca
el usuario) a un servidor MCP Go en el PC (`jav`, `cmd/jav`, stdio).

Dos roles separados:

| | **Jav** (este repo) | **Director** (externo, no es parte de Jav) |
|---|---|---|
| Qué es | servidor MCP Go (`cmd/jav`) + app Android `dev.k4wai1.jav` | OpenCode / Claude / Cursor / operador |
| Hace | expone 38 tools MCP atómicas; sin bucles ni planificador interno | lee cada pantalla, elige una tool atómica por paso, verifica el efecto |
| Ayuda táctica | sirve **`resolve_element`** (resolver ciego S1 Jev) | fija metas, compuertas y aprueba previews |

Jav no loopea, no planifica y nunca inventa coordenadas. El bucle lo lleva el
Director; el dispositivo lo lleva Jav.

## Quickstart

```bash
# 1. Instala el servidor Go (PC)
curl -fsSL https://raw.githubusercontent.com/k4wai1/jav/master/install.sh | sh
#    o: VERSION=v1.2.2 sh install.sh

# 2. Instala la APK companion (Releases) y activa accesibilidad (una vez)
#    descarga jav-companion.apk del último Release y:
adb install -r jav-companion.apk
#    Ajustes → Accesibilidad → activa Jav; copia el token que muestra la app.

# 3. Shizuku lo arranca el USUARIO (la app solo pide el permiso runtime API_V23)

# 4. Empareja una vez — sin .env, sin reiniciar (incluye Auto-TOFU del cert):
jav pair <IP-TAILNET-DEL-TELEFONO> <TOKEN>   # remoto → wss://<ip>:38472/
#    por USB loopback:  jav pair usb <TOKEN>
#    escribe ~/.config/jav/config.json (chmod 0600) y fija el certificado.

# 5. Apunta tu Director (OpenCode/Claude/Cursor) a `jav` por stdio:
#    { "command": ["jav"] }   # sin bloque environment
```

## Herramientas — 38 en 4 grupos

Toda tool devuelve `{ok, verified, evidence, hint}`. `tools/list` lleva una
descripción compacta de 1–2 líneas; la ficha completa de 7 secciones se carga
**bajo demanda** como Resource MCP (`android://tool/<name>`,
`android://tools/<group>`, índice `android://tools/catalog`). Arranque medido con
un tokenizer **tiktoken real**: **~1.8k tokens de carga cognitiva** (instructions
+ 38 descripciones compactas) y **~3.5k tokens totales** (incluye el esquema MCP
fijo de 38 tools, no reducible sin consolidar); antes ~8.8k en v1.2.0. Ver
[`docs/benchmarks/PERFORMANCE.md §9`](docs/benchmarks/PERFORMANCE.md).

| Grupo | Tools |
|---|---|
| **state** | `device_status`, `get_foreground`, `list_packages`, `get_battery`, `get_memory`, `get_storage`, `get_cpu`, `get_device_info`, `get_audit` |
| **ui** | `read_screen`, `tap_node`, `tap_text`, `type_text`, `scroll`, `press_back`, `press_home`, `wait_for_text`, `open_app`, `close_app`, `screenshot` |
| **native** | `settings_get`, `settings_put`, `open_url`, `send_intent`, `get_clipboard_device`, `get_app_usage`, `list_contacts`, `add_contact`, `list_events`, `create_event`, `list_notifications`, `reply_notification`, `media_state`, `media_control`, `get_location`, `take_photo`, `adb_shell` |
| **resolve** | `resolve_element` |

Carriles: **N0** nativo sin permisos nuevos · **N1** nativo con grants del
usuario · **N2** Shizuku/`shell`, con denylist de irreversibles + grant
interactivo (1 cmd / 5 min / 30 min).

## Qué cambió en v1.2.2

- **Nuevo icono de la app (Android + rayito).** `docs/assets/icon.png`
  (1000×1000) refrescado y mipmaps `ic_launcher[_round]` regenerados
  (mdpi 48 / hdpi 72 / xhdpi 96 / xxhdpi 144 / xxxhdpi 192; round con máscara
  circular y alfa). El manifest (`android:icon`/`android:roundIcon`) y el logo
  del header (`@mipmap/ic_launcher_round`) lo heredan automáticamente. Sin
  dependencias nuevas; `versionName 1.2.2` / `versionCode 4`.

## Qué cambió en v1.2.1

- **Vinculación sin fricción, sin `.env`, sin reiniciar.** Nuevo **`jav pair
  <ip-o-url> <token>`**: conecta una vez (hello + `get_device_info`), hace
  **Auto-TOFU** en `wss://` (captura y fija el SHA-256 del cert) y escribe
  `~/.config/jav/config.json` (`chmod 0600`). El servidor MCP relee la config
  **en caliente**, así que basta registrar `"command": ["jav"]`. Prioridad por
  campo: env (`JAV_*`) → `config.json` → default.
- **Sesión persistente: ~1.3 s → ~0.2 s por llamada.** `pkg/jam` mantiene UN
  WebSocket compartido y serializa las llamadas con un mutex: una ráfaga de
  tools produce **un solo `hello`** (antes 1 por llamada). Medido en un TECNO
  real por WSS/Tailnet: **989 ms → 320 ms** de media (tools ligeras **~140 ms**),
  **0 `hello` extra** frente a **11**. **1 reconexión + reintento** automáticos
  ante error de transporte.
- **Cierre WebSocket ordenado** (frame `close` + eco del peer, acotado ~500 ms)
  en `Client.Close`: corrige el `4001: BUSY` del cierre TCP abrupto (el teléfono
  retenía el slot single-client hasta su timeout de ~2 min).
- Las claves de IA también viven en `config.json` (`openrouter_api_key`,
  `ai_base_url`, `ai_api_key`, `ai_model`) con la misma prioridad env → config.

## Qué cambió en v1.2.0

- **~80% menos tokens de arranque**: descripciones compactas en `tools/list` +
  fichas completas bajo demanda como Resources; instructions ≤220 palabras.
- **Resumen de costo por sesión sin spam**: `pkg/cost` silencioso por defecto
  (`JAV_DEBUG_COST=1` para trazar) y `evidence.cost` con
  `{jev_cost_usd, s2_cost_usd, total_cost_usd, calls}` en `device_status` /
  `resolve_element`.
- **Identidad consolidada** (`Jav` / `dev.k4wai1.jav`) y cert TLS unificado a
  `CN=jav.local`.
- **Fase 2b** (WSS tailnet + cert + token en Keystore + lockout) y **Fase 6**
  (audit ring 500 + Kill Switch + shell grant/denylist + N2).
- **Icono nuevo (1000×1000) y pulido visual nativo** sin dependencias nuevas.
- **Poda documental**: specs históricos a `docs/specs/archive/`.

## Troubleshooting

### `UNAUTHORIZED` when connecting
The token is missing or wrong. Run `jav pair <ip> <token>` (or `jav pair` for
interactive mode). If you already paired, check `~/.config/jav/config.json`
(must be `0600`). After 5 failed `UNAUTHORIZED` from the same origin the phone
locks out for 5 min.

### `CONNECTION_FAILED` on loopback
No `adb forward` active. Run:
```bash
adb forward tcp:38472 tcp:38472
```
Then `jav pair usb <TOKEN>`.

### `SHIZUKU_UNAVAILABLE`
Shizuku isn't running. Open the Shizuku app and start it yourself (**Jav never
starts it**). Without Shizuku the N0 native lane still works, but `open_app` and
`screenshot` (API 29 fallback) fail.

### `ACCESSIBILITY_DISABLED`
Enable Jav in Settings → Accessibility. Without it, `read_screen` / `tap_node`
fail.

### `BUSY: 4001`
A previous client didn't close cleanly. Wait ~2 min or restart the Jav app.
v1.2.1's graceful close fixes this; if it persists, open an issue.

### WSS doesn't connect over Tailnet
Check the phone's address is `100.64.x.x` (Tailscale). Otherwise the WSS
listener doesn't come up (loopback only). Also verify the pinned fingerprint
(`cert_fingerprint` in the config) matches the app cert (`CN=jav.local`).

## Troubleshooting (ES)

### `UNAUTHORIZED` al conectar
Falta el token o es incorrecto. Ejecuta `jav pair <ip> <token>` (o `jav pair` en
modo interactivo). Si ya vinculaste, revisa `~/.config/jav/config.json` (debe ser
`0600`). Tras 5 fallos `UNAUTHORIZED` del mismo origen, el teléfono bloquea 5 min.

### `CONNECTION_FAILED` en loopback
No hay `adb forward` activo. Ejecuta:
```bash
adb forward tcp:38472 tcp:38472
```
Luego `jav pair usb <TOKEN>`.

### `SHIZUKU_UNAVAILABLE`
Shizuku no está corriendo. Abre la app Shizuku y arráncalo tú (**Jav nunca lo
inicia**). Sin Shizuku, el carril nativo N0 sigue vivo, pero `open_app` y
`screenshot` (fallback API 29) fallan.

### `ACCESSIBILITY_DISABLED`
Activa Jav en Ajustes → Accesibilidad. Sin esto, `read_screen` / `tap_node`
fallan.

### `BUSY: 4001`
Un cliente previo no cerró limpio. Espera ~2 min o reinicia la app Jav. El cierre
ordenado de v1.2.1 lo corrige; si persiste, abre un issue.

### WSS no conecta por Tailnet
Verifica que la IP del teléfono sea `100.64.x.x` (Tailscale). Si no, el listener
WSS no se levanta (solo loopback). Comprueba también que el fingerprint fijado
(`cert_fingerprint` en la config) coincide con el cert de la app (`CN=jav.local`).

## 👨‍💻 Desarrollador

**[k4wai1](https://github.com/k4wai1)** — si Jav te ahorró tiempo, considera
[invitar un café](https://ko-fi.com/kwai1). PRs bienvenidos.

## 📜 Licencia

Este proyecto está bajo la **GNU General Public License v3.0** — ver el archivo
[LICENSE](LICENSE) para el texto completo.
