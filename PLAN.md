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

### Fase v5 — Director-cliente (loop congelado; solo docs + `set_clipboard`)
- [x] Contratos `@architect`: `docs/specs/paradigm-shift.md` (3 giros 2026-10-06),
  `docs/specs/director-client.md` v5, `README.es.md`/`README.en.md`.
- [ ] `@coder`: `resolve_element` ciego al goal (1 Choice + NONE, micro EN,
  anti-poisoning) + `set_clipboard` Jam/host con read-back (working tree sin
  commit: `tools/clipboard.py`, `PROTOCOL.md`, `docs/TESTING.md` §8);
  `loop.py`/`ask_decision`/`s2_client` congelados (solo bugfix con test).
- [ ] `@judge`: pytest verde antes y después + suite A10 en KJ5
  (batería + calculadora + clipboard round-trip; hoy `avg_tap_ms 69.7`,
  `avg_s1_ms 1589.5`, costo <$0.003, pero redo `ok_all: false` → B1
  bloqueado por entorno) + greps cero-acoplado + `ask_decision` ausente
  en path director.
- [ ] Pendientes P1/P2 (no se fingen cerrados): ranking por relevancia,
  firma anti-ticker, `assertFresh`, forense wire+timings por fase,
  recalibrar `TAU=0.70`/`FAST_TAU=0.85` con ≥20 goals. Enmienda AGENTS.md §1
  propuesta en `director-client.md` §11.4 (orquestador).

### Fase 6 — Shell con seguridad cerrada + hardening
- [ ] `shell` solo con denylist, grant (1 cmd SHA-256 exacto / 5 min / 30 min,
  bloqueo 60 s), audit ring 500 (`get_audit`), kill switch (tile + notificación).
- [ ] Grupo `adb` opt-in, push/pull solo bajo `/sdcard/Download/jev-mcp/`,
  docs y hardening finales.

## Próxima tarea (agente general `run_goal`, cero literales de dominio)

1. `@architect`: contrato `docs/specs/generic-dual-tier.md` (hecho 2026-10-05) —
   `run_goal(goal: str)`, S1/S2, poda 255 Choice, CostTracker, compuertas genéricas.
2. `@coder`: implementa el contrato, elimina `tasks/`, sube normalizer 60→254,
   reescribe `tests/test_guards.py` y `scripts/fase5_check.py` contra `run_goal`.
3. `@judge`: `uv run pytest` + `./gradlew :app:testDebugUnitTest` +
   `grep -rniE 'whatsapp|com\.whatsapp|contact_name|verify_chat|wrong_chat' src/` vacío +
   forense `logs/run-<ts>.jsonl` con `cost` por paso y líneas `[COST]`.
4. Explícito: **sin paquetes/contactos prefijados**; acción crítica/irreversible
   solo con preview + `confirm:true` del operador, auditada en forense.

## Deuda / anotaciones (AGENTS.md §9)
- Latencia IPC por nodo (2–3×): candidata a Fase 4+.
- `ConnectivityManager.NetworkCallback` para re-detección de IP tailnet.
- Ring buffer audit 500 entradas (`get_audit`, Fase 6).
- Fallback `monkey` en `open_app` (API 29, sin equipo de prueba).
