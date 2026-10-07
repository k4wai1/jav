# jev-android-mcp — MCP Android genérico on-device + agente dual-tier (ES)

> `Jam` (`dev.jev.jam`) es una app Android sin root que expone la UI por
> accesibilidad y acciones por Shizuku a un servidor MCP en el PC. Un agente
> dual-tier (S1 Jev + S2 LLM) ejecuta objetivos en lenguaje natural con
> `run_goal(goal: str)`. Cero apps prefijadas en el core: lo específico viaja
> en runtime. Estado detallado: `PLAN.md`, `ARCHITECTURE.md`, `PROTOCOL.md`,
> `docs/specs/paradigm-shift.md`.

## Qué es

- **MCP Android genérico on-device.** La app Jam lee la pantalla por
  `AccessibilityService` (`dump_ui` con `snapshot_id`), tapea/escribe por
  gestos + `ACTION_SET_TEXT`, abre/cierra apps y captura por Shizuku. El
  servidor MCP (Python + `uv`) traduce eso a tools atómicas.
- **Dual-tier.** S1 Jev (TypeSafe, juicio discriminativo en ms, sin texto
  libre) resuelve cada paso; S2 (LLM frontera) planifica hitos, diagnostica y
  redacta. Todo objetivo entra por `run_goal(goal: str)`; para metas
  complejas el director (operador) dirige paso a paso con `resolve_element`
  ciego al goal + clipboard por API.
- **Seguro por diseño.** Sin root, sin `su`, `shell` OFF hasta Fase 6,
  confirmación explícita en críticas, forense JSONL por corrida.

## Arquitectura en 10 líneas (+ diagrama)

1. Jam expone 2 listeners WS: loopback `ws://127.0.0.1:38472` + IP tailnet WSS.
2. `hello` con token bearer + scopes (`read`/`ui`/`shell`/`admin`).
3. Percepción = árbol de accesibilidad (`dump_ui`, ≤500 nodos, ~2 ms/nodo).
4. Host normaliza y poda (decoración fuera) → tabla numerada 0..253 + NONE.
5. S1 Jev elige 1 primitiva (`TAP/TYPE/SCROLL/BACK/DONE/ESCALATE`) + target.
6. S2 compila (`EXECUTE_GOAL` + textos precargados) o dirige (v5: el operador).
7. Mutación atómica (`tap_node`/`type_text`/`open_app`) + verificación posterior.
8. Clipboard del SO antes que dedos (`get` por `dumpsys` host, `set` por API Jam).
9. Costos auditados (`[COST]` + `CostTracker`) y forense `logs/run-<ts>.jsonl`.
10. Sin key → stub `{mock:true}` honesto; nunca se inventan opciones.

```
PC (Debian, uv, MCP stdio)              TECNO (Jam, sin root)
┌─ server.py: device/app/ui/jev ─┐      ┌─ ForegroundService: WS×2 ─┐
│ run_goal / director + S1 + S2  │─WS──▶│ Accessibility: tree+gestos│
│ normalizer, guards, cost, logs │◀─WS──│ Shizuku: am/monkey/screencap│
└────────────────────────────────┘      └───────────────────────────┘
  adb forward tcp:38472 │  WSS tailnet (opt-in, pinning TOFU)
```

## Quickstart

```bash
# 1. Instala el APK y habilita accesibilidad (una vez, en el teléfono)
adb install -r app/build/outputs/apk/debug/app-debug.apk
# Ajustes → Accesibilidad → activa Jam; genera el token en la app (QR).

# 2. Shizuku lo arranca el USUARIO (la app solo pide permiso runtime API_V23)
# Instala moe.shizuku.privileged.api oficial, arráncalo, autoriza a Jam.

# 3. Forward + entorno (en el PC)
adb forward tcp:38472 tcp:38472
cd mcp-server && cp ../.env.example ../.env   # edita: JEV_TOKEN, OPENROUTER_API_KEY, modelos
uv sync

# 4. Chequeos sin Android Studio
uv run pytest -q                       # 127 verdes (v5 working tree)
cd ../android-app && ./gradlew :app:testDebugUnitTest

# 5a. run_goal general (caso simple)
cd ../mcp-server
JEV_TOKEN=... OPENROUTER_API_KEY=... uv run python scripts/run_goal_check.py --goal "..."

# 5b. Director paso a paso (meta compleja): por pantalla,
# read_screen_state → resolve_element("<micro EN de ESTA pantalla>")
# → tap_idx/type_text/open_app → read de verificación → get/set_clipboard
# → forense en logs/run-<ts>.jsonl. Ver docs/specs/director-client.md §9.4
# y Apéndice A para la narración exigida en el informe.
```

## Seguridad

- **Scopes:** `read` (dump/screenshot) · `ui` (tap/type/scroll/back, `open_app`
  sin grant) · `shell` (con grant, OFF hasta Fase 6 → `METHOD_NOT_ALLOWED`) ·
  `admin` (token/audit). Token obligatorio incluso en loopback; lockout
  5 fallos/60 s → 5 min; frame 4 MiB; rate 50 req/s (shell 5/s).
- **Confirm:** enviar/comunicar, comprar/pagar, borrar, cuenta/permisos,
  `shell`/adb son críticas: sin `confirm:true` se planean sin ejecutar
  (`planned:true` + `preview` + `needs_confirm`); con él, ejecución +
  auditoría. Sin blacklist global (`forbidden?` opt-in por goal).
- **Forense:** `logs/run-<ts>.jsonl` por paso (fase, snapshot, `conf`/`tau`,
  `wire`, `cost`, `via`, hashes; texto crudo jamás si sensible) + firma
  `run_signature` fail-fast (2 muertes iguales → no relanzar).
- **Kill switch:** tile de ajustes rápidos + acción en notificación (revoca
  tokens, detiene servidor). Push/pull solo bajo `/sdcard/Download/jev-mcp/`.

## Estado actual + roadmap

- **Hoy:** Fases 0–4 verdes; Fase 5 `run_goal` + v3/v4/§12 en working tree
  (127 pytest); v5 director-cliente en `docs/` + `set_clipboard` sin commit;
  suite A10 medida (batería `88 %`, calculadora con `avg_tap_ms 69.7`,
  `avg_s1_ms 1589.5`, costos <$0.003) pero calculadora-redo `ok_all: false`
  → B1 bloqueado por entorno.
- **Roadmap:** certificar A10 en KJ5 → cerrar `set_clipboard` Jam + wrapper →
  P1 (firma anti-ticker, `assertFresh`, forense wire+timings) → P2 (ranking
  por relevancia + recalibrar `tau` con ≥20 goals) → Fase 6 (`shell` con
  denylist + grant + audit 500 + kill switch) → WSS tailnet 2b.
  Detalle vivo en `PLAN.md`; giros en `docs/specs/paradigm-shift.md`.
