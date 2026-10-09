# Jav 🛠️ — full-control Android MCP runtime, no root

[![Moe Counter](https://count.getloli.com/get/@jav-k4wai1?name=jav-k4wai1&theme=rule34&padding=3&offset=0&align=top&scale=1&pixelated=1&darkmode=1)](https://github.com/k4wai1)
[![Support me on Ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/kwai1)
[![License: GPL-3.0](https://img.shields.io/badge/license-GPL--3.0-blue.svg)](LICENSE)

> **English first, español después.** This is the definitive README. It replaces
> `README.en.md` / `README.es.md` (removed). Live detail: `PLAN.md`,
> `ARCHITECTURE.md`, `PROTOCOL.md`, `docs/TESTING.md`, `docs/specs/ecosystem.md`.

---

# 🇬🇧 ENGLISH

## What is Jav

**Jav is a full-control Android MCP runtime without root.** An on-device app
(**Jam**, `dev.jev.jam`) exposes the screen via `AccessibilityService` and
privileged actions via **Shizuku** (started by the user) to a Go MCP runtime
on the PC (`jav` binary, `cmd/jav`, stdio). The **Director is the external
client** (OpenCode/operator, never part of Jav): it sees each screen and
drives one atomic tool per step; Jav runs no loops and no internal S2.
Tactical judgment comes from **S1 Jev** (discriminative, single-pass, no free
text, blind `resolve_element`) through a single general entrypoint per step:

```python
resolve_element(screen_goal_en: str)   # e.g. resolve_element("Tap the Copy link row")
```

- **Generic core, zero hardcoded apps.** No package names, contacts, texts or
  flows in the core. Specifics travel at runtime (external Director or S2).
- **Three lanes:** native APIs (OS before fingers) · director-client v5
  (complex goals: the external Director directs, Jev resolves, Jam executes) ·
  historical autonomous `run_goal` (frozen, not the active path).
- **Secure by design.** Non-root app, `su` forbidden, `shell` OFF until
  Phase 6, bearer token + scopes on every bind, explicit confirm on critical
  actions, JSONL forensics per run.

## Architecture in 10 lines

1. Jam serves 2 WS listeners: loopback `ws://127.0.0.1:38472` + tailnet-IP WSS.
2. `hello` with bearer token + scopes (`read` / `ui` / `shell` / `admin`).
3. Perception = accessibility tree (`dump_ui`, ≤500 nodes, ~2 ms/node).
4. Jav normalizes and prunes (system decor filtered) → table `0..253` + `NONE`.
5. S1 Jev resolves 1 element (`resolve_element`, blind to the global goal) + `conf`.
6. The external Director (OpenCode/operator) decides one atomic primitive per step; Jav never loops nor plans internally.
7. Atomic mutation (`tap_node` / `type_text` / `open_app`) + post verification.
8. OS clipboard before fingers (`get` via host `dumpsys`, `set` via Jam API).
9. Audited costs (`[COST]` + `CostTracker`) and forensics `logs/run-<ts>.jsonl`.
10. No key → honest `{mock: true}` stub; options are never invented.

```
PC (Debian, Go, MCP stdio)                 Phone (Jam, non-root)
┌─ jav (cmd/jav): device/app/ui/native ─┐  ┌─ ForegroundService: 2×WS ─┐
│ atomic tools + resolve_element + cost  │─WS──▶│ Accessibility: tree+gest. │
│ normalizer, guards, logs (no loops)    │◀─WS──│ Shizuku: am/monkey/screen│
└────────────────────────────────────────┘  └───────────────────────────┘
  Director = EXTERNAL client (OpenCode) ──▶ jav (no S2/live loops inside)
  adb forward tcp:38472 │  WSS tailnet (opt-in, TOFU pinning)
```

## Tools — 35 total (6 Jev + 29 director/native)

Every tool returns `{ok, verified, evidence, hint}`. `verified: true` only
with real post-verification, never on "command sent".

**6 — UI atomic tools (driven step by step by the external Director; historical `loop.run_goal` frozen, not the active path):**

| Tool | What it does |
|---|---|
| `read_screen` | `dump_ui` + normalizer + table + `snapshot_id` + `first_result` / `zone` / `focused_field` |
| `tap_node` | `ACTION_CLICK` first if clickable, `dispatchGesture` fallback; reports `via`; requires fresh `snapshot_id` |
| `type_text` | `ACTION_SET_TEXT`; requires explicit focus or `NOT_FOCUSED` |
| `scroll` | Scroll at position / node |
| `press_back` | Back key |
| `open_app` | Bootstrap only in the loop; Shizuku `am start`, fallback `monkey` |

**29 — director / native / diagnostics:**

| Group | Tools |
|---|---|
| device / diag (8) | `device_status`, `list_packages`, `get_foreground`, `close_app`, `press_home`, `wait_for_text`, `screenshot`, `tap_text` (legacy, prefer `tap_node`) |
| telemetry N0 (5) | `get_battery`, `get_memory`, `get_storage`, `get_cpu`, `get_device_info` |
| settings / intents N0 (4) | `settings_get`, `settings_put` (System; Secure/Global = N2), `open_url`, `send_intent` |
| clipboard (1) | `get_clipboard_device` (Jam foreground; host prefers `dumpsys`) |
| usage N1 (1) | `get_app_usage` |
| PII N1 (4) | `list_contacts`, `add_contact`, `list_events`, `create_event` |
| notif / media N1 (4) | `list_notifications`, `reply_notification`, `media_state`, `media_control` |
| location / camera N1 (2) | `get_location`, `take_photo` (FGS + always confirm) |

Example payloads (English):

```json
{"goal": "List the alarms in the clock app"}
{"snapshot_id": 42, "node_id": 17}
{"text": "Buy milk", "slot": "message_body"}
{"url": "https://example.com/s/abc", "package": ""}
```

Native lanes: **N0** needs no new grants · **N1** needs user grants
(advertised in `hello.caps`) · **N2** (Shizuku/`shell` on-device) answers
`METHOD_NOT_ALLOWED` until Phase 6.

## Real runs with numbers (summary)

> Benchmarks own the numbers: [`docs/benchmarks/PERFORMANCE.md`](docs/benchmarks/PERFORMANCE.md)
> (per-tool latencies on real hardware) and
> [`docs/benchmarks/TASK_HISTORY.md`](docs/benchmarks/TASK_HISTORY.md)
> (closed tasks with wall/cost/forensics). This table only summarizes.

| Area | Figure (measured) |
|---|---|
| Perception `dump_ui` | ~2 ms/node (13n/40 ms, 66n/106 ms, 124n/264 ms; ~1 s worst @500) |
| tap (`ACTION_CLICK` first) | ~70 ms (`avg_tap_ms` 69.7–84.6) |
| S1 Jev | ~1.6 s (`avg_s1_ms` 1589.5) |
| S2 DeepSeek-direct (historical, retired) | ~1.9 s/call vs flash ~22 s/call |
| N0 native (Go e2e) | ~50–190 ms/tool (media 173 ms) |
| Intent 1-hop `open_url` + `package` | ~0.13 s (`latency_ms` 130.3) |
| Closed tasks | messaging-A SENT ~84.9 s (~$0.0038); messaging-B SENT ~22 s (~$0.0023); Fossify 5/5 ~38 s (~$0.0006); YT→Brave honest BLOCK (~$0.0011) |
| Cost ceiling | **<$0.003** per run |

Benches: TECNO KJ5 (API 33, Wi-Fi) + A10 USB (Android 10, 720×1440).
Host: Debian 13, Celeron 847. `dump_ui` 16× faster than `uiautomator dump`
(4353 ms). Full tables in `docs/benchmarks/`; forensics in `logs/` (Go) plus
historical `mcp-server/logs/` (frozen Python harness).

Runtime is 100% Go (`go test ./...`, `make build`); the Python `mcp-server`
harness is frozen history, not an active component.

## Current status + roadmap

- **Today:** runtime 100% Go (`cmd/jav` stdio, `pkg/tools` 35 tools,
  `go test ./...` green); Phases 0–4 green; v5 director-client vigente
  (**Director = external OpenCode/operator**, Jav = thin server with no loops
  and no internal S2: `resolve_element` blind resolver + `set_clipboard` +
  historical `loop.py` frozen); native lane N0/N1 live, N2 gated;
  35/35 docstrings at the 5-section standard.
- **Roadmap:** formal A10 suite close (battery + calculator + clipboard
  round-trip) → P1 (anti-ticker signature, `assertFresh`, wire+timings
  forensics) → P2 (relevance ranking + recalibrate `TAU` with ≥20 goals) →
  Phase 6 (`shell` with denylist + grant + 500-audit + kill switch) → tailnet
  WSS 2b. Live tracker: `PLAN.md`. Name: **Jav** = project/runtime,
  **Jev** = tactical backend (`JEV_MODEL`); rename migration deferred
  (`docs/specs/ecosystem.md` §4). Historical Python harness (`mcp-server`,
  148 pytest green at freeze) kept only as forensics reference.
- **Roadmap:** formal A10 suite close (battery + calculator + clipboard
  round-trip) → P1 (anti-ticker signature, `assertFresh`, wire+timings
  forensics) → P2 (relevance ranking + recalibrate `TAU` with ≥20 goals) →
  Phase 6 (`shell` with denylist + grant + 500-audit + kill switch) → tailnet
  WSS 2b. Live tracker: `PLAN.md`. Name: **Jav** = project/runtime,
  **Jev** = tactical backend (`JEV_MODEL`); rename migration deferred
  (`docs/specs/ecosystem.md` §4).

## Quickstart

```bash
# 1. Install the APK and enable accessibility (once, on the phone)
adb install -r app/build/outputs/apk/debug/app-debug.apk
# Settings → Accessibility → enable Jam; generate the token in the app (QR).

# 2. The USER starts Shizuku (the app only requests the API_V23 runtime permission)
# Install the official moe.shizuku.privileged.api, start it, authorize Jam.

# 3. Forward + environment (on the PC)
adb forward tcp:38472 tcp:38472
cp .env.example .env   # edit: JAV_TOKEN, OPENROUTER_API_KEY, models (chmod 600)

# 4. Checks without Android Studio
go build ./... && go vet ./... && go test ./...   # Go suite green
cd android-app && ./gradlew :app:testDebugUnitTest

# 5. Director step by step (the only active path; the Director is external):
# per screen, read_screen → resolve_element("<micro EN of THIS screen>")
# → tap_node / type_text / open_app → verification read → get/set_clipboard
# → forensics in logs/run-<ts>.jsonl. See docs/specs/director-client.md §9.4.
#
# Historical frozen loop (reference only, not runtime):
# mcp-server/ + uv + pytest (148 green at freeze).
```

## Security

- **Scopes:** `read` (dump/screenshot) · `ui` (tap/type/scroll/back,
  grantless `open_app`) · `shell` (grant-gated, OFF until Phase 6 →
  `METHOD_NOT_ALLOWED`) · `admin` (token/audit). Token mandatory even on
  loopback; lockout 5 fails/60 s → 5 min; 4 MiB frame; 50 req/s (shell 5/s).
- **Confirm:** sending/communicating, buying/paying, deleting,
  account/permission changes, `shell`/adb are critical: without
  `confirm: true` they are planned without executing (`planned: true` +
  `preview` + `needs_confirm`); with it, execution + audit. `forbidden?`
  patterns are opt-in per goal, never global.
- **Forensics:** `logs/run-<ts>.jsonl` per step (phase, snapshot, `conf` /
  `tau`, `wire`, `cost`, `via`, hashes; never raw text when sensitive) plus
  fail-fast `run_signature` (2 equal deaths → do not relaunch).
- **Kill switch:** quick-settings tile + notification action (revoke tokens,
  stop server). Push/pull only under `/sdcard/Download/jev-mcp/`.

## 👨‍💻 Developer

**[k4wai1](https://github.com/k4wai1)** — if Jav saved you time, consider
[buying a coffee](https://ko-fi.com/kwai1). Contributions via PRs welcome.

## 📜 License

This project is licensed under the **GNU General Public License v3.0** —
see the [LICENSE](LICENSE) file for details.

---

# 🇪🇸 ESPAÑOL

## Qué es Jav

**Jav es un runtime MCP de control integral de Android sin root.** Una app
en el dispositivo (**Jam**, `dev.jev.jam`) expone la pantalla por
`AccessibilityService` y las acciones privilegiadas por **Shizuku**
(lo arranca el usuario) a un runtime MCP Go en el PC (binario `jav`,
`cmd/jav`, stdio). El **Director es el cliente externo**
(OpenCode/operador, nunca parte de Jav): ve cada pantalla y dirige una
herramienta atómica por paso; Jav no corre bucles ni S2 interno.
El juicio táctico lo aporta **S1 Jev** (discriminativo, single-pass, sin
texto libre, `resolve_element` ciego) con un único punto de entrada general
por paso:

```python
resolve_element(screen_goal_en: str)   # p. ej. resolve_element("Tap the Copy link row")
```

- **Core genérico, cero apps prefijadas.** Sin paquetes, contactos, textos ni
  flujos en el core. Lo específico viaja en runtime (Director externo o S2).
- **Tres carriles:** APIs nativas (el SO antes que los dedos) ·
  director-cliente v5 (metas complejas: el Director externo dirige, Jev resuelve,
  Jam ejecuta) · `run_goal` autónomo histórico (congelado, no la vía activa).
- **Seguro por diseño.** App sin root, `su` prohibido, `shell` OFF hasta
  Fase 6, token bearer + scopes en cada bind, confirmación explícita en
  críticas, forense JSONL por corrida.

## Arquitectura en 10 líneas

1. Jam sirve 2 listeners WS: loopback `ws://127.0.0.1:38472` + WSS a IP tailnet.
2. `hello` con token bearer + scopes (`read` / `ui` / `shell` / `admin`).
3. Percepción = árbol de accesibilidad (`dump_ui`, ≤500 nodos, ~2 ms/nodo).
4. Jav normaliza y poda (decoración fuera) → tabla `0..253` + `NONE`.
5. S1 Jev resuelve 1 elemento (`resolve_element`, ciego al goal global) + `conf`.
6. El Director externo (OpenCode/operador) decide una primitiva atómica por paso; Jav no loopea ni planifica dentro.
7. Mutación atómica (`tap_node` / `type_text` / `open_app`) + verificación posterior.
8. Clipboard del SO antes que dedos (`get` por `dumpsys` host, `set` por API Jam).
9. Costos auditados (`[COST]` + `CostTracker`) y forense `logs/run-<ts>.jsonl`.
10. Sin key → stub honesto `{mock: true}`; nunca se inventan opciones.

```
PC (Debian, Go, MCP stdio)                 Teléfono (Jam, sin root)
┌─ jav (cmd/jav): device/app/ui/nativo ─┐  ┌─ ForegroundService: 2×WS ─┐
│ tools atómicas + resolve_element+costo │─WS──▶│ Accesibilidad: árbol+gest│
│ normalizer, guards, logs (sin bucles)  │◀─WS──│ Shizuku: am/monkey/pant. │
└────────────────────────────────────────┘  └───────────────────────────┘
  Director = cliente EXTERNO (OpenCode) ──▶ jav (sin S2 ni bucles dentro)
  adb forward tcp:38472 │  WSS tailnet (opt-in, pinning TOFU)
```

## Herramientas — 35 en total (6 Jev + 29 director/nativo)

Toda tool devuelve `{ok, verified, evidence, hint}`. `verified: true` solo con
verificación real posterior, nunca por "comando enviado".

**6 — herramientas UI atómicas (las dirige paso a paso el Director externo; `loop.run_goal` histórico congelado, no la vía activa):**

| Tool | Qué hace |
|---|---|
| `read_screen` | `dump_ui` + normalizer + tabla + `snapshot_id` + `first_result` / `zone` / `focused_field` |
| `tap_node` | `ACTION_CLICK` primero si clickable, fallback `dispatchGesture`; reporta `via`; exige `snapshot_id` fresco |
| `type_text` | `ACTION_SET_TEXT`; exige foco explícito o `NOT_FOCUSED` |
| `scroll` | Scroll en posición / nodo |
| `press_back` | Tecla atrás |
| `open_app` | Solo bootstrap en el bucle; `am start` por Shizuku, fallback `monkey` |

**29 — director / nativo / diagnóstico:**

| Grupo | Tools |
|---|---|
| device / diag (8) | `device_status`, `list_packages`, `get_foreground`, `close_app`, `press_home`, `wait_for_text`, `screenshot`, `tap_text` (legacy, preferir `tap_node`) |
| telemetría N0 (5) | `get_battery`, `get_memory`, `get_storage`, `get_cpu`, `get_device_info` |
| settings / intents N0 (4) | `settings_get`, `settings_put` (System; Secure/Global = N2), `open_url`, `send_intent` |
| clipboard (1) | `get_clipboard_device` (Jam en foreground; el host prefiere `dumpsys`) |
| usage N1 (1) | `get_app_usage` |
| PII N1 (4) | `list_contacts`, `add_contact`, `list_events`, `create_event` |
| notif / media N1 (4) | `list_notifications`, `reply_notification`, `media_state`, `media_control` |
| ubicación / cámara N1 (2) | `get_location`, `take_photo` (FGS + siempre confirm) |

Payloads ejemplo (en inglés):

```json
{"goal": "List the alarms in the clock app"}
{"snapshot_id": 42, "node_id": 17}
{"text": "Buy milk", "slot": "message_body"}
{"url": "https://example.com/s/abc", "package": ""}
```

Carriles nativos: **N0** sin permisos nuevos · **N1** con grants del usuario
(anunciados en `hello.caps`) · **N2** (Shizuku/`shell` on-device) responde
`METHOD_NOT_ALLOWED` hasta Fase 6.

## Pruebas reales con números (resumen)

> Los benchmarks mandan: [`docs/benchmarks/PERFORMANCE.md`](docs/benchmarks/PERFORMANCE.md)
> (latencias por herramienta en hardware real) y
> [`docs/benchmarks/TASK_HISTORY.md`](docs/benchmarks/TASK_HISTORY.md)
> (tareas cerradas con tiempo/costo/forense). Esta tabla solo resume.

| Área | Cifra (medida) |
|---|---|
| Percepción `dump_ui` | ~2 ms/nodo (13n/40 ms, 66n/106 ms, 124n/264 ms; ~1 s peor @500) |
| tap (`ACTION_CLICK` primero) | ~70 ms (`avg_tap_ms` 69.7–84.6) |
| S1 Jev | ~1.6 s (`avg_s1_ms` 1589.5) |
| S2 DeepSeek-direct (histórico, retirado) | ~1.9 s/llamada vs flash ~22 s/llamada |
| Nativo N0 (e2e Go) | ~50–190 ms/tool (media 173 ms) |
| Intent 1-salto `open_url` + `package` | ~0.13 s (`latency_ms` 130.3) |
| Tareas cerradas | mensajería-A SENT ~84.9 s (~$0.0038); mensajería-B SENT ~22 s (~$0.0023); Fossify 5/5 ~38 s (~$0.0006); YT→Brave BLOQUEO honesto (~$0.0011) |
| Techo de costo | **<$0.003** por corrida |

Bancos: TECNO KJ5 (API 33, Wi-Fi) + A10 USB (Android 10, 720×1440).
Host: Debian 13, Celeron 847. `dump_ui` 16× más rápido que `uiautomator dump`
(4353 ms). Tablas completas en `docs/benchmarks/`; forense en `logs/` (Go) más
histórico `mcp-server/logs/` (harness Python congelado).

Runtime 100% Go (`go test ./...`, `make build`); el harness Python
`mcp-server` es historia congelada, no un componente activo.

## Estado actual + roadmap

- **Hoy:** runtime 100% Go (`cmd/jav` stdio, `pkg/tools` 35 tools,
  `go test ./...` verde); Fases 0–4 verdes; v5 director-cliente vigente
  (**Director = OpenCode/operador externo**, Jav = servidor delgado sin bucles
  ni S2 interno: `resolve_element` ciego + `set_clipboard` + `loop.py`
  histórico congelado); carril nativo N0/N1 vivo, N2 gateado;
  35/35 docstrings al estándar de 5 secciones.
- **Roadmap:** cierre formal suite A10 (batería + calculadora + clipboard
  round-trip) → P1 (firma anti-ticker, `assertFresh`, forense wire+timings) →
  P2 (ranking por relevancia + recalibrar `TAU` con ≥20 goals) → Fase 6
  (`shell` con denylist + grant + audit 500 + kill switch) → WSS tailnet 2b.
  Tracker vivo: `PLAN.md`. Nombre: **Jav** = proyecto/runtime,
  **Jev** = backend táctico (`JEV_MODEL`); migración de rename diferida
  (`docs/specs/ecosystem.md` §4).

## Quickstart

```bash
# 1. Instala el APK y habilita accesibilidad (una vez, en el teléfono)
adb install -r app/build/outputs/apk/debug/app-debug.apk
# Ajustes → Accesibilidad → activa Jam; genera el token en la app (QR).

# 2. Shizuku lo arranca el USUARIO (la app solo pide el permiso runtime API_V23)
# Instala moe.shizuku.privileged.api oficial, arráncalo, autoriza a Jam.

# 3. Forward + entorno (en el PC)
adb forward tcp:38472 tcp:38472
cp .env.example .env   # edita: JAV_TOKEN, OPENROUTER_API_KEY, modelos (chmod 600)

# 4. Chequeos sin Android Studio
go build ./... && go vet ./... && go test ./...   # suite Go verde
cd android-app && ./gradlew :app:testDebugUnitTest

# 5. Director paso a paso (única vía activa; el Director es externo): por pantalla,
# read_screen → resolve_element("<micro EN de ESTA pantalla>")
# → tap_node / type_text / open_app → read de verificación → get/set_clipboard
# → forense en logs/run-<ts>.jsonl. Ver docs/specs/director-client.md §9.4.
#
# Bucle histórico congelado (solo referencia, no runtime):
# mcp-server/ + uv + pytest (148 en verde al congelar).
```

## Seguridad

- **Scopes:** `read` (dump/screenshot) · `ui` (tap/type/scroll/back,
  `open_app` sin grant) · `shell` (con grant, OFF hasta Fase 6 →
  `METHOD_NOT_ALLOWED`) · `admin` (token/audit). Token obligatorio incluso en
  loopback; lockout 5 fallos/60 s → 5 min; frame 4 MiB; 50 req/s (shell 5/s).
- **Confirm:** enviar/comunicar, comprar/pagar, borrar, cuenta/permisos,
  `shell`/adb son críticas: sin `confirm: true` se planean sin ejecutar
  (`planned: true` + `preview` + `needs_confirm`); con él, ejecución +
  auditoría. Patrones `forbidden?` opt-in por goal, nunca globales.
- **Forense:** `logs/run-<ts>.jsonl` por paso (fase, snapshot, `conf`/`tau`,
  `wire`, `cost`, `via`, hashes; texto crudo jamás si sensible) + firma
  `run_signature` fail-fast (2 muertes iguales → no relanzar).
- **Kill switch:** tile de ajustes rápidos + acción en notificación (revoca
  tokens, detiene servidor). Push/pull solo bajo `/sdcard/Download/jev-mcp/`.

## 👨‍💻 Desarrollador

**[k4wai1](https://github.com/k4wai1)** — si Jav te ahorró tiempo, considera
[invitar un café](https://ko-fi.com/kwai1). PRs bienvenidos.

## 📜 Licencia

Este proyecto está bajo la **GNU General Public License v3.0** — ver el
archivo [LICENSE](LICENSE) para el texto completo.
