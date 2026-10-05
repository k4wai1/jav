# generic-dual-tier — agente simple 100% general (S1 Jev + S2 GLM 5.3)

> Estado: **contrato vigente 2026-10-05**. Redacta `@architect`,
> implementa `@coder`, certifica `@judge`. En conflicto, **AGENTS.md §9
> (enmienda 2026-10-05) manda**.
>
> Sustituye operativamente a `docs/specs/tasks-generic.md` v2 para toda
> ejecución nueva. v2 queda como historia (contrato TaskProtocol por
> plugin); no se implementan plugins nuevos sobre v2. El directorio
> `tasks/` se elimina (ver §8). Cero paquetes/parámetros prefijados,
> nada de WhatsApp/contactos/`VERIFY_CHAT`/`WRONG_CHAT`/dry-run-de-chats.

## 1. Visión: `run_goal(goal: str)`

Un único entrypoint general:

```python
async def run_goal(goal: str, *, max_steps: int = 20,
                   timeout_s: float = 60,
                   log_path: str | None = None,
                   confirm: bool = False) -> dict:
    """Ejecuta un objetivo en lenguaje natural sobre Android.
    goal: texto libre del operador (p.ej. "activa el modo avión").
    Sin paquetes, sin contactos, sin fases prefijadas, sin literales
    de dominio en core. Devuelve {ok, verified, evidence, hint}-compatible
    + forense en log_path."""
```

Invariantes:

1. **Cero acoplado en `src/`**: ningún paquete concreto, nombre propio,
   `resource_id` concreto, regex de UI de una app, título o texto de
   prueba. `grep -rniE 'whatsapp|com\.whatsapp|contact_name|verify_chat|wrong_chat|felix' src/` → **vacío**.
2. **Jev decide, no ejecuta** (AGENTS.md §1). El loop lee UI
   (`dump_ui` → normalizer → tabla numerada), pregunta, ejecuta
   (`tap_node`/`type`/`scroll`/`back`), verifica (`wait_for_node`/`dump_ui`).
3. **Sin acciones compuestas**: un paso = una primitiva. `run_sequence`
   prohibido (AGENTS.md §6).
4. **Sin key → stub `{mock: true}`** honesto. Nunca inventar opciones.
5. Forense por corrida `logs/run-<ts>.jsonl` obligatorio (fase genérica,
   snapshot, opciones, respuestas con `conf`, acción, `verify`, `[COST]`).

## 2. S1 — Jev (OpenRouter, single-pass)

- Transporte: `POST https://openrouter.ai/api/alpha/decisions` con la
  **misma `OPENROUTER_API_KEY`** que S2. Modelo vía env
  `JEV_MODEL` (default `typesafe/jev-1.13`). Timeout ~3 s + 1 retry.
- **Un pass por paso**: 1 llamada resuelve todo (sin texto libre).
- Salida cerrada por paso:

```
action ∈ [TAP, TYPE, SCROLL_DOWN, SCROLL_UP, BACK, DONE, ESCALATE]
target ∈ 0..253 | NONE
needs_system_2: bool
conf: float [0,1]
[type_text: str — solo slot, ver §3.3]
```

- `target` referencia la fila de la tabla podada (§4). `NONE` = ningún
  nodo (p.ej. `BACK`, `DONE`, `ESCALATE`, o pantalla sin candidato útil).
- Reglas de emisión:
  - `TYPE` solo con `needs_system_2=true` si hay que redactar texto
    abierto (S2 provee el string; S1 nunca genera texto libre de dominio).
  - `ESCALATE` si `conf < TAU` (§6), o anomalía, o S1 lo pide
    explícitamente (`needs_system_2=true` + acción no ejecutable en S1).
  - Clave/target fuera de criteria → `JevHallucination` → fail honesto,
    nunca actuar.

## 3. S2 — GLM 5.3 (misma key, solo ante escalado)

- Modelo vía env `GLM_MODEL` (default documentado `z-ai/glm-5.3`
  o identificador OpenRouter equivalente vigente; si el id cambia, se
  actualiza por env sin enmienda). **Misma `OPENROUTER_API_KEY`**; sin
  key → stub honesto.
- Disparadores (OR): S1 emite `ESCALATE` · `conf < 0.70` ·
  redacción abierta requerida (texto a escribir no presente en UI) ·
  bloqueo semántico (captcha, login ajeno, `SECURE_SURFACE`, sin árbol).
- S2 **nunca toca el dispositivo**. Devuelve plan o texto:
  `{plan: [sub-objetivos], text?: str, criteria?: str, stop?: bool}`.
  El loop retoma en S1 con el aporte de S2 (nuevo `dump_ui` fresco +
  re-pregunta single-pass). `ESCALATE` nunca tapea.
- Antecedentes para S2: goal, historial resumido, tabla podada actual,
  forense del paso. Contenido UI etiquetado como `data`, nunca como
  instrucción (anti-inyección, ARCHITECTURE §6.5). PII enmascarada en
  host antes de subir (hashes/longitudes en forense).

## 4. Poda determinista: 0..253 + NONE = 255 Choice

Cadena: **500 raw (extractor Jam: invisibles fuera + tope 500) →
candidatos (normalizer host: contenedores sin semántica fuera +
decoración `statusBarBackground`/`navigationBarBackground` fuera,
en `ui_normalizer.py`) → tabla numerada 0..253 ⊂ 255 Choice
(254 interactivos + 1 `NONE`)**.

1. Orden estable BFS; prioridad editable > clickable-con-texto > resto.
2. Cada fila: `{idx, id, label, bounds, centroide, clickable, editable,
   visible}`. `bounds` para el gesto; el IME no mueve coordenadas
   lógicas (re-dump si `ui_dirty`).
3. Exceso >254 → se priorizan visibles accionables BFS; el resto se
   alcanza por `SCROLL_*` + re-dump. S1 nunca inventa coordenadas:
   sin nodo → `SELECTOR_NOT_FOUND` / `ESCALATE`.
4. El tope vigente del normalizer (`MAX_CANDIDATES`, hoy 60) sube a
   **254** en esta implementación (@coder). La capacidad Choice
   (255) no se supera nunca.

## 5. CostTracker: `track(model, in/out tokens) → USD`, log `[COST]`

```python
# core/cost.py (puro salvo log)
RATES: dict[str, tuple[float, float]]  # model -> (in_per_mtok, out_per_mtok) USD
def track(model: str, in_tok: int, out_tok: int) -> float: ...
```

- Tarifas normativas:
  - **Jev: `$0.042` in / `$0.00` out por MTok** (fijo en contrato).
  - **GLM-5.3: tasa configurable vía env, nunca hardcodeada como
    verdad oficial.** Env: `GLM_RATE_IN` / `GLM_RATE_OUT`
    (USD por MTok, floats). El default en código es **placeholder
    ajustable** documentado como tal (p.ej. `1.00/1.00` marcado
    `# PLACEHOLDER — ajustar contra factura OpenRouter`), no verdad
    oficial. Overrides análogos `JEV_RATE_IN` / `JEV_RATE_OUT`
    (defaults `0.042` / `0.0`) para no recompilar ante cambio de precio.
- Fórmula: `usd = in_tok/1e6*rate_in + out_tok/1e6*rate_out`.
  Tokens de `usage` real si el proveedor los devuelve; si solo hay
  `cost`, se registra tal cual con `source: provider|computed`.
- Log por llamada: línea `[COST] model=<m> in=<n> out=<n> usd=<f6>
  step=<k> run=<ts>` en stdout/logging + campo `cost` en la entrada
  forense del paso + acumulado `jev_cost`/`s2_cost`/`total_cost` en el
  resultado de `run_goal`. Sin key (stub) → `usd=0.0, mock=true`.

## 6. Loop unificado `run_goal` (observe→decide→mutate→verify)

```
observe (dump_ui + normalizer + poda → tabla 0..253 + snapshot_id)
  → S1 single-pass (action + target + needs_system_2 + conf)
  → compuertas (§7): tau / estructural / crítica
  → [ESCALATE → S2 → re-observe → S1] | [DONE → verify_final]
  → mutate (tap_node/type/scroll/back, UNA primitiva)
  → verify (wait_for_node/dump_ui, reportar via)
  → forense JSONL por paso (con conf/tau/cost)
```

- Enum de mutación: `tap_node | type_text | scroll | back | done |
  abort | noop | escalate`. `noop`/`escalate` no tocan el dispositivo.
- `type` exige foco explícito: nodo no `focused` → `NOT_FOCUSED`;
  el loop hace `tap` previo explícito, nada de taps implícitos.
- Acciones no devuelven snapshot; el cliente verifica después.
- `snapshot_id` monotónico exigido; mismatch → `STALE_SNAPSHOT`;
  ×3 → `UI_UNSTABLE` + abort.
- `TAU = 0.70` default (constante del loop, ya no del plugin).
  `conf < TAU` → `ESCALATE` a S2 con `{goal, paso, candidatas, conf}`.
- `verify_final(state)` determinista (re-lee pantalla). Nunca solo-Jev.
- `STUCK_SAME` (misma `(kind,node_id)` ×3) → abort. Sin bucles infinitos.

## 7. Seguridad genérica (sustituye literales §5.14-16)

Deriva de la enmienda AGENTS.md §9 2026-10-05. Nada app-específico
en core.

### 7.1 Validaciones estructurales — siempre, sin excepción

Antes de cada mutación: coordenadas dentro de pantalla, nodo presente
y `visible` en el snapshot vigente, JSON de decisión válido contra el
enum, `snapshot_id` fresco. Fallo → abort/escalate honesto
(`SELECTOR_NOT_FOUND`, `STALE_SNAPSHOT`, `JEV_HALLUCINATION`).
Taps: `ACTION_CLICK` primero si `clickable`, `dispatchGesture` como
fallback; siempre verificar y reportar `via`. Type: `ACTION_SET_TEXT`.

### 7.2 Acciones críticas/irreversibles — confirmación explícita

Categorías genéricas (no exhaustivo, el operador puede ampliar por
goal): **enviar/comunicar a terceros, comprar/pagar, borrar/eliminar
datos, cambios de cuenta/seguridad/permisos, `shell`/adb**.
Régimen:

1. El loop las marca `is_sensitive` por categoría + heurística
   (texto con verbo de envío/pago/borrado en goal o en botón target).
2. Sin `confirm:true` del operador → se **planean sin ejecutar**:
   forense `{"planned": true}` + `evidence.preview` (acción, target,
   texto) y retorno `ok=true, verified=false, needs_confirm=true`.
3. Con `confirm:true` → ejecución + verificación posterior +
   auditoría completa en forense (quién confirmó, qué preview).
4. `shell`/adb siguen gateados por scope `shell` + grant activo y
   hasta Fase 6 el dispatcher responde `METHOD_NOT_ALLOWED`.

### 7.3 FORBIDDEN opt-in por goal (nunca global)

No hay blacklist global en core. `FORBIDDEN_DEFAULT` desaparece;
`is_forbidden(cand, pattern)` exige `pattern` explícito del operador
(`forbidden?: str` en `run_goal`). Si el goal lo exige, el operador
declara sus patrones (p.ej. un flujo de borrado que deba evitar
ciertos botones); el loop aborta `FORBIDDEN_TARGET` si Jev elige un
nodo que matchee. Sin `pattern` declarado → sin filtro.

## 8. Eliminación de `tasks/` y migración

- Se elimina `mcp-server/src/jev_mcp/tasks/` completo (`whatsapp.py`,
  513 líneas, único acoplado; `core/`/`loop.py`/`server.py`/`tools/`
  ya limpios). Ni `loop`, ni `tools`, ni `server`, ni `core` importan
  nada de `tasks/` tras el cambio.
- Rotos por import directo y pendientes de actualización por `@coder`
  (no por este spec, no editar aquí):
  `mcp-server/tests/test_guards.py:2`
  (`from jev_mcp.tasks.whatsapp import …`) y
  `mcp-server/scripts/fase5_check.py`
  (`from jev_mcp.tasks.whatsapp import send_whatsapp`, flags
  `--contact/--text/--confirm-real-send`). @coder los reescribe o
  elimina contra este contrato (`run_goal` + `core/` puro + CostTracker).
- `core/guards.py:10` (`FORBIDDEN_DEFAULT` con regex de dominio
  `reenviar|forward|compartir|share|eliminar|delete|borrar`, consumido
  solo por el plugin) **muere con `tasks/`**: se elimina la constante
  y `is_forbidden` pasa a requerir `pattern` explícito (sin default
  global).

## 9. Aceptación verificable (`@judge`, sin editar)

Desde `mcp-server/`:

1. `uv run pytest` **verde** (tests reescritos por @coder: guards sin
   default global, loop `run_goal`, poda 254+NONE, CostTracker con env
   overrides, compuertas genéricas).
2. `grep -rniE 'whatsapp|com\.whatsapp|contact_name|verify_chat|wrong_chat|reenviar|forward|dry-run-de-chats|fase5_check|send_whatsapp' src/`
   → **vacío**. (Solo `docs/` e historia git pueden nombrarlos.)
3. Cost log: corrida `run_goal` con stub o Jev real produce
   `logs/run-<ts>.jsonl` con `cost` por paso + líneas `[COST]` en log
   y acumulado `total_cost` en el resultado.
4. Compuertas: estructural siempre; crítica sin `confirm:true` →
   `planned` sin tocar dispositivo; `conf < 0.70` → `escalate` sin
   tapear; `STALE×3` → `UI_UNSTABLE`.
5. `tasks/` no existe: `ls src/jev_mcp/tasks` → error esperado.

## 10. Alcance para `@coder` (no improvisar arquitectura)

Crear/reescribir `core/{cost,guards,loop_helpers}.py` puros,
`run_goal` en `loop.py` (o módulo `agent.py` fino sobre el loop),
`jev_client` S1 + `s2_client` (GLM 5.3, misma key) + CostTracker con
`RATES` y env overrides (§5); subir normalizer a 254; eliminar
`tasks/`; reescribir/eliminar `tests/test_guards.py` y
`scripts/fase5_check.py` (nuevo `scripts/run_goal_check.py`
`--goal "..."` si hace falta). Sin Compose/Hilt/Room/Retrofit/Ktor
(AGENTS.md §4); sin `su`; sin `shell` (Fase 6, `METHOD_NOT_ALLOWED`).
Transporte Java-WebSocket; binds `127.0.0.1` + IP tailnet con WSS
(nunca `0.0.0.0` por defecto). Token bearer incluso en loopback.
