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
privileged actions via **Shizuku** (started by the user) to an MCP server on
the PC (Python + `uv`). A dual-tier agent — **S1 Jev** (discriminative
judgment, single-pass, no free text) + **S2 frontier LLM** (planning,
diagnosis, composition) — executes natural-language goals through a single
general entrypoint:

```python
run_goal(goal: str)   # e.g. run_goal("List the alarms in the clock app")
```

- **Generic core, zero hardcoded apps.** No package names, contacts, texts or
  flows in the core. Specifics travel at runtime (operator or S2).
- **Three lanes:** native APIs (OS before fingers) · director-client v5
  (complex goals: operator directs, Jev resolves) · dual-tier `run_goal`
  (simple goals, frozen `loop.py`).
- **Secure by design.** Non-root app, `su` forbidden, `shell` OFF until
  Phase 6, bearer token + scopes on every bind, explicit confirm on critical
  actions, JSONL forensics per run.

## Architecture in 10 lines

1. Jam serves 2 WS listeners: loopback `ws://127.0.0.1:38472` + tailnet-IP WSS.
2. `hello` with bearer token + scopes (`read` / `ui` / `shell` / `admin`).
3. Perception = accessibility tree (`dump_ui`, ≤500 nodes, ~2 ms/node).
4. Host normalizes and prunes (system decor filtered) → table `0..253` + `NONE`.
5. S1 Jev picks 1 primitive (`TAP / TYPE / SCROLL_DOWN / SCROLL_UP / BACK / DONE / ESCALATE`) + target.
6. S2 compiles (`EXECUTE_GOAL` + preloaded inputs) or the v5 director drives step by step.
7. Atomic mutation (`tap_node` / `type_text` / `open_app`) + post verification.
8. OS clipboard before fingers (`get` via host `dumpsys`, `set` via Jam API).
9. Audited costs (`[COST]` + `CostTracker`) and forensics `logs/run-<ts>.jsonl`.
10. No key → honest `{mock: true}` stub; options are never invented.

```
PC (Debian, uv, MCP stdio)              Phone (Jam, non-root)
┌─ server.py: device/app/ui/jev ─┐      ┌─ ForegroundService: 2×WS ─┐
│ run_goal / director + S1 + S2  │─WS──▶│ Accessibility: tree+gest. │
│ normalizer, guards, cost, logs  │◀─WS──│ Shizuku: am/monkey/screen│
└────────────────────────────────┘      └───────────────────────────┘
  adb forward tcp:38472 │  WSS tailnet (opt-in, TOFU pinning)
```

## Tools — 35 total (6 Jev + 29 director/native)

Every tool returns `{ok, verified, evidence, hint}`. `verified: true` only
with real post-verification, never on "command sent".

**6 — Jev loop primitives (`loop.run_goal`, frozen):**

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

## Real runs with numbers

Benches: TECNO KJ5 (API 33, Wi-Fi) for S1/S2 loop + A10 USB (Android 10,
720×1440) for director v5. Host: Debian 13, Celeron 847, ~2 ms/node
(`dump_ui`), tap ~70 ms (`ACTION_CLICK` first), S1 ~1.6 s. Full tables in
`docs/TESTING.md` §9–10, forensics in `mcp-server/logs/run-*.jsonl`.

| Run | Result | Wall | Cost |
|---|---|---|---|
| Messaging-A SENT | SENT, verified on-screen (25 steps) | ~84.9 s | ~$0.0038 |
| Messaging-B SENT (`stale_recovered` ×1) | SENT, verified on-screen (12 steps) | ~22 s | ~$0.0023 |
| Clock alarms read-only | OK | seconds | <$0.0001 |
| Fossify gallery (folders lens) | OK | 2.3 s | $0 |
| Fossify clock (alarms) | OK | 5.7 s | ~$0.00005 |
| Fossify files (Download, incl. scroll) | OK | 9.1 s | ~$0.00013 |
| Fossify calculator (3-digit × 2-digit) | OK, double-snap verified | 15.5 s | ~$0.00031 |
| Fossify music (track lens) | OK | 5.6 s | ~$0.00010 |
| **Fossify 5/5 total** | **all OK** | **~38 s** | **~$0.0006** |
| Battery level in settings | OK (`avg_tap_ms 84.6`) | ~23.1 s | ~$0.00067 |
| Stock calculator redo | BLOCKED by environment (`ok_all: false`, honest) | n/a | $0 |
| Multi-app copy-link → downloader | Honest BLOCK (`DOWNLOAD_NOT_STARTED`) | 25 phases | ~$0.0011 |
| Intent 1-hop `open_url` with `package` | OK `via: startActivity-package` | ~0.13 s | $0 |
| Intent without `package` | Chooser `ResolverActivity` (expected) | ~13 s | $0 |

Per-run cost **<$0.003**. pytest suite **148 green**
(`cd mcp-server && uv run pytest -q`).

## Current status + roadmap

- **Today:** Phases 0–4 green; Phase 5 `run_goal` + plan-ahead v4 + §12 in
  tree; v5 director-client (`resolve_element` blind resolver + `set_clipboard`
  + frozen `loop.py`) in `docs/` + code; native lane N0/N1 live, N2 gated;
  35/35 MCP docstrings at the 5-section standard.
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
cd mcp-server && cp ../.env.example ../.env   # edit: JEV_TOKEN, OPENROUTER_API_KEY, models
uv sync

# 4. Checks without Android Studio
uv run pytest -q                       # 148 green
cd ../android-app && ./gradlew :app:testDebugUnitTest

# 5a. Generic run_goal (simple goal)
cd ../mcp-server
JEV_TOKEN=... OPENROUTER_API_KEY=... uv run python scripts/run_goal_check.py \
  --goal "List the alarms in the clock app"

# 5b. Step-by-step director (complex goal): per screen,
# read_screen_state → resolve_element("<micro EN of THIS screen>")
# → tap_idx / type_text / open_app → verification read → get/set_clipboard
# → forensics in logs/run-<ts>.jsonl. See docs/specs/director-client.md §9.4.
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
(lo arranca el usuario) a un servidor MCP en el PC (Python + `uv`). Un agente
dual-tier — **S1 Jev** (juicio discriminativo, single-pass, sin texto libre)
+ **S2 LLM frontera** (planifica, diagnostica, redacta) — ejecuta objetivos
en lenguaje natural con un único punto de entrada general:

```python
run_goal(goal: str)   # p. ej. run_goal("List the alarms in the clock app")
```

- **Core genérico, cero apps prefijadas.** Sin paquetes, contactos, textos ni
  flujos en el core. Lo específico viaja en runtime (operador o S2).
- **Tres carriles:** APIs nativas (el SO antes que los dedos) ·
  director-cliente v5 (metas complejas: el operador dirige, Jev resuelve) ·
  dual-tier `run_goal` (metas simples, `loop.py` congelado).
- **Seguro por diseño.** App sin root, `su` prohibido, `shell` OFF hasta
  Fase 6, token bearer + scopes en cada bind, confirmación explícita en
  críticas, forense JSONL por corrida.

## Arquitectura en 10 líneas

1. Jam sirve 2 listeners WS: loopback `ws://127.0.0.1:38472` + WSS a IP tailnet.
2. `hello` con token bearer + scopes (`read` / `ui` / `shell` / `admin`).
3. Percepción = árbol de accesibilidad (`dump_ui`, ≤500 nodos, ~2 ms/nodo).
4. El host normaliza y poda (decoración fuera) → tabla `0..253` + `NONE`.
5. S1 Jev elige 1 primitiva (`TAP / TYPE / SCROLL_DOWN / SCROLL_UP / BACK / DONE / ESCALATE`) + target.
6. S2 compila (`EXECUTE_GOAL` + inputs precargados) o el director v5 dirige paso a paso.
7. Mutación atómica (`tap_node` / `type_text` / `open_app`) + verificación posterior.
8. Clipboard del SO antes que dedos (`get` por `dumpsys` host, `set` por API Jam).
9. Costos auditados (`[COST]` + `CostTracker`) y forense `logs/run-<ts>.jsonl`.
10. Sin key → stub honesto `{mock: true}`; nunca se inventan opciones.

```
PC (Debian, uv, MCP stdio)              Teléfono (Jam, sin root)
┌─ server.py: device/app/ui/jev ─┐      ┌─ ForegroundService: 2×WS ─┐
│ run_goal / director + S1 + S2  │─WS──▶│ Accesibilidad: árbol+gest│
│ normalizer, guards, cost, logs │◀─WS──│ Shizuku: am/monkey/pant. │
└────────────────────────────────┘      └───────────────────────────┘
  adb forward tcp:38472 │  WSS tailnet (opt-in, pinning TOFU)
```

## Herramientas — 35 en total (6 Jev + 29 director/nativo)

Toda tool devuelve `{ok, verified, evidence, hint}`. `verified: true` solo con
verificación real posterior, nunca por "comando enviado".

**6 — primitivas del bucle Jev (`loop.run_goal`, congelado):**

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

## Pruebas reales con números

Bancos: TECNO KJ5 (API 33, Wi-Fi) para bucle S1/S2 + A10 USB (Android 10,
720×1440) para director v5. Host: Debian 13, Celeron 847, ~2 ms/nodo
(`dump_ui`), tap ~70 ms (`ACTION_CLICK` primero), S1 ~1.6 s. Tablas completas
en `docs/TESTING.md` §9–10, forense en `mcp-server/logs/run-*.jsonl`.

| Corrida | Resultado | Tiempo | Costo |
|---|---|---|---|
| Mensajería-A SENT | SENT, verificado en pantalla (25 pasos) | ~84.9 s | ~$0.0038 |
| Mensajería-B SENT (`stale_recovered` ×1) | SENT, verificado en pantalla (12 pasos) | ~22 s | ~$0.0023 |
| Alarmas del reloj solo-lectura | OK | segundos | <$0.0001 |
| Fossify galería (lente de carpetas) | OK | 2.3 s | $0 |
| Fossify reloj (alarmas) | OK | 5.7 s | ~$0.00005 |
| Fossify archivos (Download, con scroll) | OK | 9.1 s | ~$0.00013 |
| Fossify calculadora (3 dígitos × 2 dígitos) | OK, doble snapshot verificado | 15.5 s | ~$0.00031 |
| Fossify música (lente de pistas) | OK | 5.6 s | ~$0.00010 |
| **Fossify 5/5 total** | **todo OK** | **~38 s** | **~$0.0006** |
| Batería en ajustes | OK (`avg_tap_ms 84.6`) | ~23.1 s | ~$0.00067 |
| Calculadora stock redo | BLOQUEO por entorno (`ok_all: false`, honesto) | n/a | $0 |
| Multi-app copiar-link → descargador | BLOQUEO honesto (`DOWNLOAD_NOT_STARTED`) | 25 fases | ~$0.0011 |
| Intent 1-salto `open_url` con `package` | OK `via: startActivity-package` | ~0.13 s | $0 |
| Intent sin `package` | Chooser `ResolverActivity` (esperado) | ~13 s | $0 |

Costo por corrida **<$0.003**. Suite pytest **148 en verde**
(`cd mcp-server && uv run pytest -q`).

## Estado actual + roadmap

- **Hoy:** Fases 0–4 verdes; Fase 5 `run_goal` + plan-ahead v4 + §12 en el
  árbol; v5 director-cliente (`resolve_element` ciego + `set_clipboard` +
  `loop.py` congelado) en `docs/` + código; carril nativo N0/N1 vivo, N2
  gateado; 35/35 docstrings MCP al estándar de 5 secciones.
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
cd mcp-server && cp ../.env.example ../.env   # edita: JEV_TOKEN, OPENROUTER_API_KEY, modelos
uv sync

# 4. Chequeos sin Android Studio
uv run pytest -q                       # 148 en verde
cd ../android-app && ./gradlew :app:testDebugUnitTest

# 5a. run_goal general (caso simple)
cd ../mcp-server
JEV_TOKEN=... OPENROUTER_API_KEY=... uv run python scripts/run_goal_check.py \
  --goal "List the alarms in the clock app"

# 5b. Director paso a paso (meta compleja): por pantalla,
# read_screen_state → resolve_element("<micro EN de ESTA pantalla>")
# → tap_idx / type_text / open_app → read de verificación → get/set_clipboard
# → forense en logs/run-<ts>.jsonl. Ver docs/specs/director-client.md §9.4.
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
