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
- System 1 (MCP/local, determinista) ejecuta; System 2 (orquestador) planifica.

## Fases

### Fase 0 — Scaffold app + Shizuku + FGS
- [x] 0a/0b: app `dev.jev.jam`, Shizuku provider, FGS `specialUse`.
- [ ] 0c: permiso `FOREGROUND_SERVICE_SPECIAL_USE` (verificar en build release).

### Fase 1 — dump_ui (accesibilidad)
- [x] Recorrido BFS ≤500 nodos, `snapshot_id` monotónico, tests JVM 6/6.
- [x] Aceptación relajada: anclas ≥95%, latencia <100 ms (medido 100%, 40 ms).

### Fase 2 — Protocolo WS + single-client
- [x] Listener loopback + token bearer, rate limit, frame 4 MiB.
- [ ] 2b: WSS + certificado + Keystore (bind tailnet). **Pendiente.**

### Fase 3 — Acciones (Shizuku)
- [x] 3a: `open_app`, `force_stop`, `screenshot` (`takeScreenshot`, API 30+).
- [ ] Deuda: preferir `tap_node(id, snapshot_id)` sobre `tap(selector)`.

### Fase 4 — Normalización + mapeo tool↔método
- [x] `ui_normalizer.py` (filtrar nodos de decoración del sistema).
- [ ] Mapeo tool MCP ↔ método: `open_app`, `close_app`↔`force_stop`,
  `get_app_state`↔`dump_ui`+normalizar, `get_foreground_app`, `adb_shell`↔`shell`.
- [ ] Desacoplar `mcp-server/src/jev_mcp/tasks/whatsapp.py`: convertirlo en
  primitivas genéricas + contrato en `docs/specs/` (evitar optimizar solo WhatsApp).

### Fase 6 — Shell con seguridad cerrada
- [ ] `shell` no expuesto hasta cerrar denylist, grant (1 cmd/5 min/30 min) y audit.
- [ ] Dispatcher debe rechazar `shell` con `METHOD_NOT_ALLOWED` explícito.

## Próxima tarea

1. `@explorer`: mapear `mcp-server/src/jev_mcp/tasks/whatsapp.py` y `loop.py`
   (rutas + líneas + puntos de acoplamiento a la app).
2. `@architect`: contrato `docs/specs/tasks-generic.md` para desacoplar.
3. `@coder`: implementar el contrato.
4. `@judge`: `uv run pytest` + `./gradlew :app:testDebugUnitTest`.

## Deuda / anotaciones (AGENTS.md §9)
- Latencia IPC por nodo (2–3×): candidata a Fase 4+.
- `ConnectivityManager.NetworkCallback` para re-detección de IP tailnet.
- Ring buffer audit 500 entradas (`get_audit`, Fase 6).
- Fallback `monkey` en `open_app` (API 29, sin equipo de prueba).
