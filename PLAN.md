# PLAN.md — Hoja de ruta viva

> Custodiado por `plan` (Orquestador gratuito nativo) u `@orchestrator`
> (Orquestador de pago DeepSeek). Es el único archivo que el Orquestador edita.
> Fuente de verdad de las reglas: `AGENTS.md` (manda) y `ARCHITECTURE.md`.
> Estado: actualizar aquí, no en la conversación.

## Principios

- Accesibilidad = única fuente de lectura de UI. `screenshot` es evidencia/fallback.
- Tools MCP = primitivas agnósticas (`get_node_hierarchy`, `tap_node`, `tap_point`,
  `input_text`, `swipe`, `keyevent`, `launch_app`, `get_foreground`, `screenshot`).
- Cero lógica acoplada a apps concretas en los controladores de UI.
  `tasks/*` son solo plugins-ejemplo fuera del core (sin literales normativos).
- Dual-Tier genérico (ver `ARCHITECTURE.md §6`): System 1 (Jev, juicio
  discriminativo single-pass, Choice ≤255 / Score / Noul, poda ≤254+NONE,
  compuertas tau/críticas/Noul) ejecuta; System 2 (LLM frontera) solo
  planifica hitos, anomalías visuales, fallos persistentes y redacta texto.
- Stack y seguridad no negociables: Java-WebSocket (nunca Ktor/Netty/SSE/HTTP),
  binds `127.0.0.1:38472` + IP tailnet con WSS obligatorio (nunca `0.0.0.0`
  por defecto), token bearer en `hello` incluso en loopback,
  `shell` OFF hasta Fase 6 (`METHOD_NOT_ALLOWED`).

## Fases (por capacidades, ninguna menciona app concreta)

### Fase 0 — Scaffold app + Shizuku + FGS
- [x] 0a/0b: app `dev.jev.jam`, Shizuku provider, FGS `specialUse`.
- [ ] 0c: permiso `FOREGROUND_SERVICE_SPECIAL_USE` (verificar en build release).

### Fase 1 — Percepción por accesibilidad (`dump_ui`)
- [x] Recorrido BFS ≤500 nodos, `snapshot_id` monotónico, tests JVM 6/6.
- [x] Aceptación relajada: anclas ≥95%, latencia <100 ms en pantallas típicas
  (medido 100%, 40 ms; ~2 ms/nodo, peor caso ~1 s a 500 nodos).
- [x] Contrato: sin campo `secure` en `dump_ui` (`SECURE_SURFACE` solo en
  `screenshot`); `root == null` = sin ventana activa.

### Fase 2 — Transporte WS + single-client + handshake
- [x] Listeners loopback (WS) + tailnet (WSS) con token bearer, scopes
  `read`/`ui`/`shell`/`admin`, rate limit, frame 4 MiB, `BUSY` al 2.º cliente.
- [ ] 2b: WSS + certificado self-signed + token en Keystore (bind tailnet). **Pendiente.**

### Fase 3 — Ejecución (Shizuku + gestos + captura)
- [x] 3a: `open_app` (`am start` por Shizuku, fallback `monkey`),
  `force_stop`, `screenshot` (`takeScreenshot`, API 30+).
- [ ] Deuda: preferir `tap_node(id, snapshot_id)` sobre `tap(selector)`;
  `ACTION_CLICK` primero + `dispatchGesture` fallback + `via` verificado;
  `type` por `ACTION_SET_TEXT` con foco explícito.
- [ ] `shell` diferido a Fase 6; dispatcher lo rechaza con
  `METHOD_NOT_ALLOWED` explícito.

### Fase 4 — Normalización + Dual-Tier en el host
- [x] `ui_normalizer.py` (filtrar decoración del sistema; base de la poda §6.3).
- [ ] Completar poda determinista (cadena vigente 500 raw → 60 normalizer
  ⊂ 255 Choice; subir normalizer 60→254 **pendiente Fase 5**),
  tabla numerada con centroides, PII mask local, anti-prompt-injection
  (contenido UI = `data`, nunca instrucción).
- [ ] Mapeo tool MCP ↔ método: `open_app`, `close_app`↔`force_stop`,
  `get_app_state`↔`dump_ui`+normalizar, `get_foreground_app`,
  `adb_shell`↔`shell` (gateado).
- [x] Desacoplar ejemplo en `tasks/` (41f1d31, 2026-10-04): plugin fino sobre
  `core/` + contrato v2 en `docs/specs/tasks-generic.md` (tau, escalado,
  `text_match`/`guards`/`titles` parametrizados, forense).
- [ ] Giro 2026-10-05 (contrato `docs/specs/generic-dual-tier.md`):
  `run_goal(goal: str)` general, S1 Jev + S2 GLM 5.3 (misma key),
  poda 0..253+NONE=255 Choice, CostTracker con RATES + env overrides.
  **`tasks/` se elimina** (whatsapp.py único acoplado); `FORBIDDEN_DEFAULT`
  muere con él (opt-in por goal). `tests/test_guards.py:2` y
  `scripts/fase5_check.py` los reescribe `@coder`.

### Fase 5 — Bucle Jev genérico + compuertas + forense
- [x] `gate_tau(conf, tau)` en `core/guards.py` (puro, genérico) + `TAU=0.70`
  parametrizable en plugin + `escalate` en enum de `loop.py` (como noop,
  sin tocar dispositivo) + `guarded_action` acepta `escalate` (código en
  working tree; falta end-to-end con Jev real).
- [ ] Pendiente explícito: subir normalizer 60→254; tau/escalate end-to-end
  con Jev real; forense con `conf`/`tau` por paso.
- [ ] `jev_client` (S1) + `s2_client` (GLM 5.3, misma key) + `run_goal`
  (`observe→decide→mutate→verify`, `[TAP,TYPE,SCROLL_DOWN,SCROLL_UP,BACK,
  DONE,ESCALATE]` + target 0..253+NONE + `needs_system_2`),
  sensible sin `confirm:true` → `planned` sin ejecutar, `STALE_SNAPSHOT×3→
  UI_UNSTABLE`, fallback sin-árbol → `screenshot` a S2, CostTracker `[COST]`.
- [ ] Compuertas obligatorias: tau ~0.70 → escalar; críticas →
  S2/humano; Noul (bloqueos semánticos) → escalar sin reintentos ciegos.
- [ ] Forense por corrida `logs/run-<ts>.jsonl` (fase, snapshot, opciones,
  respuestas con `conf`/`tau`, acción por paso). Sin forense no hay certificación.

### Fase v5 — Director-cliente (loop congelado; `resolve_element` + `set_clipboard`)
- [x] Contratos `@architect`: `docs/specs/paradigm-shift.md` (3 giros 2026-10-06),
  `docs/specs/director-client.md` v5, `README.es.md`/`README.en.md`.
- [x] `@coder`: `resolve_element` ciego al goal (1 Choice + NONE, micro EN,
  anti-poisoning) + `set_clipboard` Jam (`ClipboardManager.setPrimaryClip`,
  scope `ui`, sin Shizuku, sin grant) + wrapper host con read-back
  (commits `3944e15` + `7ee4058`; `loop.py`/`ask_decision`/`s2_client`
  congelados, solo bugfix con test).
- [x] `@judge`: **148 pytest en verde** (`mcp-server`: `uv run pytest -q`;
  127 en `6fc3a9a` → 139 tras `7ee4058` → **148 tras `bd1f5a4`**).
  Greps cero-acoplado en verde + `ask_decision` ausente en path director.
- [x] Bancos reales: **KJ5 (Wi-Fi)** para loop/S1-S2 + **A10 USB
  (serial `e03638e5`, Android 10, 720×1440)** para director v5.
  Suites medidas (solo metadatos; detalle en `docs/TESTING.md` §9 +
  `docs/specs/fossify-random.md`):
  mensajería-A SENT ~84.9 s (`mcp-server/logs/run-rupa-1791164922.jsonl`,
  25 steps, ~$0.0038) · mensajería-B SENT ~22 s
  (`mcp-server/logs/run-1791243623.jsonl`, 12 steps, ~$0.0023,
  `stale_recovered` ×1) · reloj/alarmas solo-lectura OK
  (`run-clock-alarms-*.jsonl`) · **Fossify 5/5** en A10
  (gallery 2.3 s $0 · clock 5.7 s · files 9.1 s · calc 15.5 s ·
  music 5.6 s; total ~$0.0006; `logs/run-fossify-*.jsonl` v2) ·
  multi-app YT→Brave **BLOQUEO honesto** `verify_download ok=false`
  (`DOWNLOAD_NOT_STARTED`; `logs/run-20261007-yt-brave.jsonl`, 25 fases,
  ~$0.0011) · calculadora A10 **bloqueada por entorno**
  (`logs/run-20261006-204449-calc.jsonl`, `summary_b_redo ok_all: false`;
  taps verificados por display pero resultado final no certificable → B1
  sigue bloqueado).
- [x] Intent/`open_url` en A10 USB (`e03638e5`, Android 10): 1-salto con
  `package` verificado (~130 ms, sin chooser), `PACKAGE_NOT_FOUND` /
  `INTENT_UNRESOLVED` honestos, chooser `ResolverActivity` sin `package`;
  detalle tabular en `docs/TESTING.md` §10 + `logs/run-intent-*.jsonl`
  (costo $0, sin LLM) + `docs/BUILD.md` §9.
- [x] `bd1f5a4` (2026-10-07, docstrings + `open_url` + ARCHITECTURE):
  docstrings MCP **35/35 al estándar 5-secciones** (Descripción /
  Parámetros / Retorno / Permisos-Grants / Errores-gotchas, payloads
  ejemplo en inglés); `open_url(url, package="")` con componente
  explícito (**1 salto, sin chooser**, `via: startActivity-package`,
  ~130 ms en banco; no instalado → `PACKAGE_NOT_FOUND`, instalado sin
  handler → `INTENT_UNRESOLVED`); `ARCHITECTURE.md` sincronizado a
  **v4/v5/nativo** (dual-tier v3 + plan-ahead v4 + director-client v5 +
  carril nativo N0/N1, `METHOD_NOT_ALLOWED` en N2); `PROTOCOL.md`
  `open_url` + `PACKAGE_NOT_FOUND`; `docs/BUILD.md` §9 con tabla
  build + prueba real en equipo.
- [ ] Pendientes honestos P1/P2 (no se fingen cerrados): ranking por
  relevancia, firma anti-ticker, `assertFresh`, forense wire+timings por
  fase, recalibrar `TAU=0.70`/`FAST_TAU=0.85` con ≥20 goals. Enmienda
  AGENTS.md §1 propuesta en `director-client.md` §11.4 (orquestador).
  Suite A10 (batería + calculadora + clipboard round-trip) pendiente de
  cierre formal por `@judge` antes de dar v5 por cerrada.

### Fase 6 — Shell con seguridad cerrada + hardening
- [ ] `shell` solo con denylist, grant (1 cmd SHA-256 exacto / 5 min / 30 min,
  bloqueo 60 s), audit ring 500 (`get_audit`), kill switch (tile + notificación).
- [ ] Grupo `adb` opt-in, push/pull solo bajo `/sdcard/Download/jev-mcp/`,
  docs y hardening finales.

## Próxima tarea (director v5 vigente; loop congelado)

1. `@judge`: cierre formal v5 — `uv run pytest -q` (148 en verde) +
   suite A10 en banco USB (batería + calculadora + clipboard round-trip) +
   greps cero-acoplado + forense `logs/run-<ts>.jsonl` con `cost` por paso.
2. `@coder` (solo bugfix con test o P1/P2 con protocolo ≥20 goals ×3):
   ranking por relevancia, firma anti-ticker, `assertFresh`,
   timings por fase, recalibrado de `TAU`/`FAST_TAU`. Sin features en `loop.py`.
3. Orquestador: enmienda AGENTS.md §1 propuesta en `director-client.md`
   §11.4 (director decide / Jev señala / Jam ejecuta).
4. Explícito: **sin paquetes/contactos prefijados**; acción crítica/irreversible
   solo con preview + `confirm:true` del operador, auditada en forense.

## Deuda / anotaciones (AGENTS.md §9)
- Seguridad P0: **enmascarar token en logcat**
  (`android-app/.../service/JevForegroundService.kt:33` loguea
  `JamWs token=$token url=…` en claro; rotar token expuesto + pasar a
  `token=<redacted>` o hash corto). Sin esto no hay release.
- Backlog 2b (no se finge cerrado): WSS + certificado self-signed +
  token en Keystore (bind tailnet). Transporte actual = WS loopback
  + `adb forward`; `hello` objeto `WsRequest{id,method,params}` con
  `protocol_version` + `client_version`, respuesta plana
  `{ok, protocol_version, app_version, scopes}` (PROTOCOL §2).
- Latencia IPC por nodo (2–3×): candidata a Fase 4+.
- `ConnectivityManager.NetworkCallback` para re-detección de IP tailnet.
- Ring buffer audit 500 entradas (`get_audit`, Fase 6).
- Fallback `monkey` en `open_app` (API 29, sin equipo de prueba).
