# generic-dual-tier — agente simple 100% general (S1 Jev + S2 GLM 5.3)

> Estado: **contrato vigente v3 2026-10-05**. Redacta `@architect`,
> implementa `@coder`, certifica `@judge`. En conflicto, **AGENTS.md §9
> (enmienda 2026-10-05) manda**.
>
> Sustituye operativamente a `docs/specs/tasks-generic.md` v2 para toda
> ejecución nueva. v2 queda como historia (contrato TaskProtocol por
> plugin); no se implementan plugins nuevos sobre v2. El directorio
> `tasks/` se elimina (ver §9). Cero paquetes/parámetros prefijados,
> nada de WhatsApp/contactos/`VERIFY_CHAT`/`WRONG_CHAT`/dry-run-de-chats.
>
> v3 = refinamiento compatible de la v2 (reasignación de roles
> S2-director vs S1-reflejo + payload S1 100% en inglés + tabla
> enriquecida + comandos S2 ejecutables + bootstrap): **no requiere
> enmienda en AGENTS.md**.
>
> > Addendum **2026-10-06 — autopsia 7 runs (parálisis por
> > indecisión)**: §12 normativo (S2-TAP-direct + `first_result` +
> > fail-fast entre corridas + clipboard multi-app genérico +
> > aceptación con corrida única). Refinamiento compatible de v3
> > (y de `plan-ahead.md` v4 donde solape): **no requiere enmienda
> > en AGENTS.md**. Cero literales de app en lo normativo; los
> > ejemplos con apps son no-normativos.

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
   Los paquetes que el dispositivo necesite los aporta **S2 en runtime**
   por conocimiento general (§5); nunca hay literales de app concreta
   en el contrato ni en `src/`. Los ejemplos con paquetes en este spec
   y en tests son **no-normativos** (valores de test aportados por el
   stub S2, no defaults del repo).
2. **Jev decide, no ejecuta** (AGENTS.md §1). El loop lee UI
   (`dump_ui` → normalizer → tabla numerada), pregunta, ejecuta
   (`tap_node`/`type`/`scroll`/`back`/`open_app`), verifica
   (`wait_for_node`/`dump_ui`).
3. **Sin acciones compuestas**: un paso = una primitiva. `run_sequence`
   prohibido (AGENTS.md §6). La única excepción es el **bootstrap
   OPEN_APP** (§5.3), que es pre-paso del loop, no decisión S1.
4. **Sin key → stub `{mock: true}`** honesto. Nunca inventar opciones.
5. Forense por corrida `logs/run-<ts>.jsonl` obligatorio (fase genérica,
   snapshot, opciones, respuestas con `conf`, acción, `verify`, `[COST]`).
6. Brecha que cierra v3 (estado real del código 2026-10-05):
   `mcp-server/src/jev_mcp/jev_client.py:ask_decision` pregunta hoy en
   **español**, `loop.py:escalate` solo deja un `s2_hint` decorativo sin
   comandos ejecutables, y `core/loop_helpers.py:build_table` calcula
   flags (`clickable/editable/focused/visible`) que **no viajan a Jev**
   (hoy solo va la tripla `idx/id/label`). v3 lo vuelve normativo:
   §3 + §4 + §5.

## 2. Roles: S2-director vs S1-reflejo (normativo v3)

### 2.1 S2 GLM 5.3 Flash = Director (lento, semántico, inter-app)

- Resuelve al inicio del goal el **paquete de la app destino por
  conocimiento general** (p.ej. ante "escribe a Rupa" sabe qué app de
  mensajería corresponde según el goal y el dispositivo). **Nunca
  hardcodeado en repo**: ni en `src/`, ni en este contrato como default,
  ni en prompts fijos. El paquete viaja solo como **valor runtime** en
  el comando S2 (§5).
- Emite **acciones macro EJECUTABLES** (no consejos decorativos):
  `{"command": "OPEN_APP"|"TYPE"|"BACK"|"HINT", "target"/"package",
  "text", "guidance_for_s1", "stop"}` (§5.1). El loop las ejecuta o las
  inyecta como `s2_guidance` + `text_payload` en el siguiente pass S1.
- **Provee todos los textos**: S1 nunca inventa texto. Todo `TYPE`
  consume `text_payload` de S2 vía `ACTION_SET_TEXT` (§5.4). Si S2 no
  da texto, el `TYPE` no se ejecuta (`S2 sin texto para TYPE` → escalate).
- **Desatasca**: emite `BACK` o replanifica (`HINT` con nuevo
  `screen_goal` + `guidance_for_s1`) ante `LOW_CONF`, `NO_TARGET`,
  pantalla sin candidato útil o app equivocada en foreground.
- Disparadores (OR, sin cambio v2): S1 `ESCALATE` · `conf < 0.70` ·
  redacción abierta · bloqueo semántico (captcha, login ajeno,
  `SECURE_SURFACE`, sin árbol) · **bootstrap de inicio** (§5.3) ·
  `DONE` (gate de verificación, `verify_done`).

### 2.2 S1 Jev = Actuador táctico intra-app (rápido, ms, sin semántica)

- Solo resuelve **índices 0..253 + NONE en ms**: un pass por paso,
  salida cerrada `action ∈ [TAP, TYPE, SCROLL_DOWN, SCROLL_UP, BACK,
  DONE, ESCALATE] + target + needs_system_2 + conf` (§3).
- No sabe de paquetes, no abre apps, no redacta, no planifica. Todo lo
  que reciba (state + questions + criteria) va **100% EN INGLÉS**
  (calibración RLCD entrenada en inglés; el español degrada `tau`).
  Preguntas/instrucciones en español en `jev_client.py` = bug contra
  este contrato; `@coder` las traduce (§11).
- Reglas de emisión (sin cambio): `TYPE` solo con texto presente en
  goal/UI o `text_payload` S2 (nunca texto inventado); `ESCALATE` si
  `conf < TAU`, anomalía o `needs_system_2=true`; clave/target fuera de
  criteria → `JevHallucination` → fail honesto, nunca actuar.

## 3. Payload S1 100% en inglés (normativo v3)

`ask_decision` construye `state` + `questions` **íntegramente en inglés**
— claves, instrucciones, `goal`, `history`, `s2_guidance`, etiquetas de
tabla. El `goal` original del operador se conserva en forense y en el
`screen_goal` se usa su traducción/condensado en inglés aportado por el
loop o S2 (el loop no inventa semántica: si no hay `screen_goal` S2, se
usa el goal verbatim marcado `operator_verbatim:true`).

Ejemplo normativo (forma, no contenido):

```json
{
  "model": "typesafe/jev-1.13",
  "state": {
    "goal": "Send a message to Rupa saying I am on my way",
    "screen_goal": "Message thread with Rupa open, message input focused",
    "current_app": "dev.jev.jam",
    "snapshot_id": 42,
    "table": [
      [0, "EditText", "edit|foc", "Message"],
      [1, "Button", "click", "Send"],
      [2, "ImageView", "click", "Back"]
    ],
    "history": "tap_node:n_7; tap_node:n_3",
    "s2_guidance": "Thread is open. Tap the message input, then type the S2 text."
  },
  "questions": {
    "action": {
      "type": "choice",
      "instructions": "Pick ONE primitive to advance the goal. TAP taps a node; TYPE types into a field (only with text already present in goal/UI or S2 text_payload, never invent text); SCROLL_* scrolls; BACK goes back; DONE only if the goal is already achieved on screen; ESCALATE on conf < 0.70, anomaly, or open-text need.",
      "criteria": {"TAP": "TAP", "TYPE": "TYPE", "SCROLL_DOWN": "SCROLL_DOWN", "SCROLL_UP": "SCROLL_UP", "BACK": "BACK", "DONE": "DONE", "ESCALATE": "ESCALATE"}
    },
    "target": {
      "type": "choice",
      "instructions": "Target table row index. NONE if the action needs no node (BACK/DONE/ESCALATE) or there is no useful candidate. Never invent indices outside the table.",
      "criteria": {"0": "0", "1": "1", "2": "2", "NONE": "NONE"}
    },
    "needs_system_2": {
      "type": "noul",
      "instructions": "Does this step require System-2 open-text composition or disambiguation (text to type not present)?"
    }
  }
}
```

Notas:

- `table` son las filas enriquecidas §4 serializadas como
  `[idx, class_short, flags, label]`. El `id` opaco (`node_id`,
  `bounds` completos) **no viaja a Jev**: queda en `by_idx` del loop
  para la validación estructural y la ejecución (§7). Ahorra tokens y
  evita que Jev alucine ids.
- `current_app` = foreground real (`get_foreground` / `dump_ui`),
  `screen_goal` = sub-objetivo de pantalla en inglés (S2 o fallback
  verbatim). Ambos en la cabecera del state, siempre.
- Transporte sin cambio: `POST .../openrouter.ai/api/alpha/decisions`
  con la misma `OPENROUTER_API_KEY`, `JEV_MODEL` por env, timeout ~3 s
  + 1 retry, `CostTracker` por llamada.

## 4. Tabla enriquecida (normativo v3)

Cadena: **500 raw (extractor Jam) → candidatos (normalizer host,
`ui_normalizer.py`) → tabla numerada 0..253 ⊂ 255 Choice
(254 interactivos + 1 `NONE`)**. Orden estable BFS; prioridad
editable > clickable-con-texto > resto. Exceso >254 → visibles
accionables primero; resto por `SCROLL_*` + re-dump.

Cada fila que viaja a Jev:

```
[idx, class_short, flags, label]
```

- `idx`: 0..253, estable por snapshot.
- `class_short`: último segmento de la clase Android
  (`Button`, `EditText`, `ImageView`, `TextView`, …; desconocida →
  `View`). Derivación pura en `loop_helpers`, sin literales de app.
- `flags`: subset ordenado y compacto, `|`-separado, vacío = `—`:
  `click` (clickable) · `edit` (editable) · `foc` (focused) ·
  `scroll` (scrollable). Hoy calculados pero no enviados; v3 los envía.
- `label`: texto compacto del normalizer (text/content-desc/resource
  recortado, ≤80 colas). Sin PII cruda fuera del dispositivo más allá
  de lo necesario (enmascarar en host antes de subir, §7).
- El loop conserva además `by_idx: {idx → {id, bounds, clickable,
  editable, focused, visible}}` para `validate_target` + ejecución.
  S1 nunca inventa coordenadas: sin nodo → `SELECTOR_NOT_FOUND` /
  `ESCALATE`.

## 5. Comandos S2 ejecutables + bootstrap (normativo v3)

### 5.1 Esquema del comando S2

```json
{
  "command": "OPEN_APP | TYPE | BACK | HINT",
  "package": "string (solo con OPEN_APP)",
  "target": "int 0..253 | NONE (solo TYPE/BACK contextual; default NONE)",
  "text": "string (solo TYPE: payload exacto a escribir)",
  "guidance_for_s1": "string EN (una frase, qué debe resolver S1 en el próximo pass)",
  "stop": "bool (default false; true solo si el goal ya está cumplido y verificado en pantalla)"
}
```

- `OPEN_APP`: `{command, package, guidance_for_s1, stop:false}`. El
  `package` lo resuelve S2 por conocimiento general en runtime. El
  contrato no lista paquetes; los valores concretos en tests/docs son
  ejemplos no-normativos.
- `TYPE`: `{command, text, target?, guidance_for_s1}`. `text` es el
  payload exacto (S1 nunca lo altera ni lo traduce).
- `BACK`: `{command, guidance_for_s1}` (desatasco).
- `HINT`: `{command, guidance_for_s1, stop?}` (replanificación sin
  mutación: nuevo `screen_goal` + guía; nunca toca el dispositivo).
- Respuesta S2 ante `verify_done` sin cambio:
  `{achieved: bool, evidence: str}`.

### 5.2 Semántica del loop ante cada comando

- `OPEN_APP` → `mcp.open_app(package)` (vía Shizuku `am start`,
  fallback `monkey`; AGENTS.md §5.5), estabilización, re-observe,
  `s2_guidance` actualizado, re-pregunta S1. Validación estructural del
  `package` (formato `a.b.c`, no vacío); fallo → `S2_BAD_COMMAND`
  honesto, sin actuar.
- `TYPE` → guarda `text_payload` + `guidance_for_s1`; el próximo `TYPE`
  S1 sobre el nodo enfocado ejecuta `ACTION_SET_TEXT(text_payload)` sin
  pasar por `type_text` de S1. Sin `text` → escalate, nunca escribir.
- `BACK` → `press_back()` + re-observe + S1.
- `HINT` → sin mutación: actualiza `screen_goal`/`s2_guidance`,
  re-observe + S1. `stop:true` → `verify_final` determinista antes de
  cerrar (nunca éxito solo-S2).

### 5.3 Bootstrap de inicio (normativo)

1. Al iniciar `run_goal`, el loop hace `observe` (foreground +
   `dump_ui` fresco) y consulta a S2-director con
   `{goal, current_app, table_lines}` **antes del primer pass S1**.
2. Si la app requerida no está en foreground, S2 emite `OPEN_APP`
   primero. El loop ejecuta `mcp.open_app(package)`, espera
   estabilización (**~600 ms**), hace `dump` fresco y **recién entonces
   invoca a S1**. Sin dump fresco no hay S1 (`STALE_SNAPSHOT`).
3. Si ya está en foreground, S2 emite `HINT` (screen_goal + guía) o
   `TYPE` (si el campo ya está visible) y el loop entra al ciclo
   normal §7.
4. Sin key S2 (stub) en bootstrap → `S2_UNAVAILABLE` inmediato (nunca
   ciclar en giro ni adivinar paquetes en el loop).

### 5.4 TYPE vía `text_payload` (normativo)

El texto a escribir viaja S2 → loop (`text_payload`) → `ACTION_SET_TEXT`,
nunca S1 → teclado. Foco explícito exigible: sin `focused` → tap previo
explícito y re-observe; el `TYPE` va en el paso siguiente con snapshot
fresco. `s2_text_len` y `text_payload_hash` (no el texto crudo) en forense.

## 6. CostTracker: `track(model, in/out tokens) → USD`, log `[COST]`

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
    ajustable** documentado como tal (`0.15/0.50` verificado
    2026-10-05 contra tarifa post-promo documentada, marcado
    `# PLACEHOLDER verificable 2026-10-05, override por
    GLM_RATE_IN/OUT`), no verdad
    oficial. Overrides análogos `JEV_RATE_IN` / `JEV_RATE_OUT`
    (defaults `0.042` / `0.0`) para no recompilar ante cambio de precio.
- Fórmula: `usd = in_tok/1e6*rate_in + out_tok/1e6*rate_out`.
  Tokens de `usage` real si el proveedor los devuelve; si solo hay
  `cost`, se registra tal cual con `source: provider|computed`.
- Log por llamada: línea `[COST] model=<m> in=<n> out=<n> usd=<f6>
  step=<k> run=<ts>` en stdout/logging + campo `cost` en la entrada
  forense del paso + acumulado `jev_cost`/`s2_cost`/`total_cost` en el
  resultado de `run_goal`. Sin key (stub) → `usd=0.0, mock=true`.
- El bootstrap S2 (§5.3) también pasa por CostTracker (`tier: s2`,
  `step: 0`) con su `[COST]` y forense propios.

## 7. Loop unificado `run_goal` (observe→decide→mutate→verify)

```
bootstrap (observe foreground → S2-director → [OPEN_APP → open_app + 600ms + re-observe] | [HINT/TYPE → s2_guidance/text_payload])
  → observe (dump_ui + normalizer + poda → tabla [idx,class_short,flags,label] + snapshot_id + current_app + screen_goal)
  → S1 single-pass EN (action + target + needs_system_2 + conf)
  → compuertas (§8): tau / estructural / crítica
  → [ESCALATE → S2 comando ejecutable → aplicar §5.2 → re-observe → S1] | [DONE → verify_done S2 → verify_final]
  → mutate (tap_node/type(open_app solo en bootstrap)/scroll/back, UNA primitiva)
  → verify (wait_for_node/dump_ui, reportar via)
  → forense JSONL por paso (con conf/tau/cost + s2_command + text_payload_hash)
```

- Enum de mutación: `tap_node | type_text | scroll | back | done |
  abort | noop | escalate | open_app (solo bootstrap)`.
  `noop`/`escalate`/`hint` no tocan el dispositivo.
- `type` exige foco explícito: nodo no `focused` → `NOT_FOCUSED`;
  el loop hace `tap` previo explícito, nada de taps implícitos.
- Acciones no devuelven snapshot; el cliente verifica después.
- `snapshot_id` monotónico exigido; mismatch → `STALE_SNAPSHOT`;
  ×3 → `UI_UNSTABLE` + abort.
- `TAU = 0.70` default (constante del loop, ya no del plugin).
  `conf < TAU` → `ESCALATE` a S2 con `{goal, paso, candidatas, conf}`.
- `verify_final(state)` determinista (re-lee pantalla). Nunca solo-Jev.
  `DONE` nunca directo: gate `DONE→S2` (`verify_done`) con snapshot
  final + historial; `achieved=true` → ok; rechazo → sigue el loop.
- `STUCK_SAME` (misma `(kind,node_id)` ×3, o misma decisión
  `(action+target)` ×3 sin cambio de snapshot) → abort.
- Contenido UI hacia S2/Jev etiquetado como `data`, nunca instrucción
  (anti-inyección, ARCHITECTURE §6.5). PII enmascarada en host.

## 8. Seguridad genérica (sustituye literales §5.14-16)

Deriva de la enmienda AGENTS.md §9 2026-10-05. Nada app-específico
en core.

### 8.1 Validaciones estructurales — siempre, sin excepción

Antes de cada mutación: coordenadas dentro de pantalla, nodo presente
y `visible` en el snapshot vigente, JSON de decisión válido contra el
enum, `snapshot_id` fresco, comando S2 válido contra §5.1 (`package`
con forma, `text` no vacío en `TYPE`). Fallo → abort/escalate honesto
(`SELECTOR_NOT_FOUND`, `STALE_SNAPSHOT`, `JEV_HALLUCINATION`,
`S2_BAD_COMMAND`). Taps: `ACTION_CLICK` primero si `clickable`,
`dispatchGesture` como fallback; siempre verificar y reportar `via`.
Type: `ACTION_SET_TEXT` con `text_payload` S2.

### 8.2 Acciones críticas/irreversibles — confirmación explícita

Categorías genéricas (no exhaustivo, el operador puede ampliar por
goal): **enviar/comunicar a terceros, comprar/pagar, borrar/eliminar
datos, cambios de cuenta/seguridad/permisos, `shell`/adb**.
Régimen:

1. El loop las marca `is_sensitive` por categoría + heurística
   (texto con verbo de envío/pago/borrado en goal o en botón target).
2. Sin `confirm:true` del operador → se **planean sin ejecutar**:
   forense `{"planned": true}` + `evidence.preview` (acción, target,
   texto-hash) y retorno `ok=true, verified=false, needs_confirm=true`.
3. Con `confirm:true` → ejecución + verificación posterior +
   auditoría completa en forense (quién confirmó, qué preview).
4. `shell`/adb siguen gateados por scope `shell` + grant activo y
   hasta Fase 6 el dispatcher responde `METHOD_NOT_ALLOWED`.

### 8.3 FORBIDDEN opt-in por goal (nunca global)

No hay blacklist global en core. `FORBIDDEN_DEFAULT` desaparece;
`is_forbidden(cand, pattern)` exige `pattern` explícito del operador
(`forbidden?: str` en `run_goal`). Si el goal lo exige, el operador
declara sus patrones; el loop aborta `FORBIDDEN_TARGET` si Jev elige un
nodo que matchee. Sin `pattern` declarado → sin filtro.

## 9. Eliminación de `tasks/` y migración

- Se elimina `mcp-server/src/jev_mcp/tasks/` completo (`whatsapp.py`,
  513 líneas, único acoplado; `core/`/`loop.py`/`server.py`/`tools`
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

## 10. Aceptación verificable (`@judge`, sin editar)

Desde `mcp-server/`:

1. `uv run pytest` **verde** (tests reescritos por @coder: guards sin
   default global, loop `run_goal` con bootstrap S2-director, payload S1
   100% inglés, poda 254+NONE con fila `[idx,class_short,flags,label]`,
   comandos S2 ejecutables, CostTracker con env overrides, compuertas
   genéricas).
2. `grep -rniE 'whatsapp|com\.whatsapp|contact_name|verify_chat|wrong_chat|reenviar|forward|dry-run-de-chats|fase5_check|send_whatsapp' src/`
   → **vacío**. (Solo `docs/` e historia git pueden nombrarlos. Los
   paquetes en tests viajan como valores runtime aportados por el stub
   S2, nunca como literales en `src/`.)
3. Cost log: corrida `run_goal` con stub o Jev real produce
   `logs/run-<ts>.jsonl` con `cost` por paso + líneas `[COST]` en log
   y acumulado `total_cost` en el resultado (incluido el bootstrap
   `step 0` S2).
4. Compuertas: estructural siempre; crítica sin `confirm:true` →
   `planned` sin tocar dispositivo; `conf < 0.70` → `escalate` sin
   tapear; `STALE×3` → `UI_UNSTABLE`.
5. `tasks/` no existe: `ls src/jev_mcp/tasks` → error esperado.
6. **Bootstrap a nivel de loop en test**: goal de mensajería a una
   persona (p.ej. "Rupa" en el test, valor no-normativo) con app no en
   foreground → el stub S2 emite `OPEN_APP` con el paquete aportado en
   runtime (p.ej. el valor de test `com.whatsapp`) y el loop despacha
   `mcp.open_app(package)` + espera ~600 ms + re-observe antes del
   primer pass S1. `@judge` lo verifica por test (mock de `open_app`
   + aserción del paquete despachado), nunca por literal en `src/`.
7. Payload S1 en inglés: el test captura el `state`/`questions`
   enviados a Jev y aserta cero instrucciones en español + tabla con
   forma `[idx, class_short, flags, label]` + cabecera con
   `current_app` y `screen_goal`.

## 11. Alcance para `@coder` (no improvisar arquitectura)

- `jev_client.ask_decision`: state + questions **100% en inglés** (§3);
  tabla como `[idx, class_short, flags, label]`; `id`/`bounds` fuera
  del payload Jev (quedan en `by_idx` del loop); `s2_hint` →
  `s2_guidance` en inglés.
- `core/loop_helpers.build_table`: fila enriquecida
  `{idx, class_short, flags, label, id, bounds, clickable, editable,
  focused, scrollable, visible}` + serialización corta para Jev;
  `MAX_TABLE = 254`; derivación pura de `class_short`/`flags`.
- `s2_client`: parsear comando ejecutable §5.1 (`OPEN_APP/TYPE/BACK/
  HINT`), validación (`S2_BAD_COMMAND`), `verify_done` sin cambio de
  forma; misma `OPENROUTER_API_KEY`.
- `loop.run_goal`: bootstrap §5.3 (`observe → S2 → open_app + 600 ms +
  re-observe → S1`); `open_app` solo en bootstrap; `TYPE` con
  `text_payload` S2 vía `ACTION_SET_TEXT` (§5.4); forense con
  `s2_command` + `text_payload_hash`; `CostTracker` también en step 0.
- Eliminar `tasks/`; reescribir/eliminar `tests/test_guards.py` y
  `scripts/fase5_check.py` (nuevo `scripts/run_goal_check.py`
  `--goal "..."` si hace falta; el test de bootstrap §10.6 usa stub
  S2 + mock `open_app`, sin literales en `src/`). Sin
  Compose/Hilt/Room/Retrofit/Ktor (AGENTS.md §4); sin `su`; sin `shell`
  (Fase 6, `METHOD_NOT_ALLOWED`). Transporte Java-WebSocket; binds
  `127.0.0.1` + IP tailnet con WSS (nunca `0.0.0.0` por defecto).
  Token bearer incluso en loopback.

## 12. Addendum 2026-10-06 — autopsia 7 runs, parálisis por indecisión (normativo)

Causa raíz observada: ante `conf < TAU` en pantallas densas, el loop
escalaba a S2, S2 devolvía solo `HINT`/consejo, el loop re-preguntaba
a S1, S1 volvía a dudar → giro sin mutación hasta `STUCK`/`TIMEOUT`.
Los tres correctivos (§12.1–§12.3) + flujo clipboard (§12.4) rompen
ese ciclo: S2 puede **resolver el índice y ejecutar directo**, el
host le marca **dónde mirar primero**, y el operador **no relanza a
ciegas** lo que ya murió igual. Todo compatible con v3 §§5/7/8 y con
`plan-ahead.md` v4 (compilador paso 0, fast-path, `zone`): ningún
punto salta compuertas. Sin literales de app en lo normativo.

### 12.1 S2-TAP ejecutable (extiende §5.1–§5.2; mismo patrón que OPEN_APP/TYPE-direct)

`VALID_COMMANDS` pasa a
`OPEN_APP | TYPE | TAP | BACK | HINT` (`TAP` nuevo; `BACK` ya
ejecutable, se re-ratifica bajo el mismo patrón directo).

Esquema (solo forma, sin literales):

```json
{
  "command": "TAP",
  "target": "int 0..253 (obligatorio, sin NONE)",
  "guidance_for_s1": "string EN (qué debe resolver S1 tras el tap)",
  "stop": "bool (default false; true solo con goal ya cumplido y verificado en pantalla)"
}
```

S2 **ve la misma tabla** que S1 (`table_lines` + `first_result`
§12.2 + `history_summary` + `screen_goal`); el `target` es índice de
esa tabla vigente, nunca coordenadas ni `node_id` opaco.

Semántica del loop ante `TAP` (sin re-preguntar a S1):

1. Resolver `by_idx[target]`. `target` fuera de la tabla vigente o
   `NONE` → `S2_BAD_COMMAND` honesto, sin actuar (S2 alucinó índice).
2. Validación estructural con `validate_target(row, screen_h)`:
   presente + `visible` + bounds en pantalla. Fallo →
   `SELECTOR_NOT_FOUND` honesto, sin tocar el dispositivo.
3. Exigir `clickable`: si no es clickable → **no mutar**
   (igual que `TYPE` sin foco §5.4): guardar `guidance_for_s1`,
   re-observe + S1. Nunca `dispatchGesture` ciego desde S2-direct.
4. Chequear `is_forbidden` opt-in (§8.3) y crítica/confirm (§8.2):
   `FORBIDDEN_TARGET` → abort; sensible sin `confirm:true` →
   `planned` + `preview` + `needs_confirm`, sin ejecutar.
5. Ejecutar `tap_node(id, snapshot_id)` + post-read coalescido
   (reutilizado como observe siguiente) + verificación
   (`wait_for_node`/`dump_ui`, reportar `via`, `ACTION_CLICK`
   primero por AGENTS.md §6).
6. `STALE_SNAPSHOT` → **un reintento en el bucle, no en la app**
   (deuda AGENTS.md 2026-10-02, mismo patrón que TYPE-direct en
   `loop.py:apply_s2`): re-observe una vez, re-resolver por `id`,
   reintentar una vez; segundo `STALE` → `UI_UNSTABLE`.
7. Forense (`phase: s2_direct_tap`): `s2_command` redactado +
   `target`/`node_id` + `result` + `via` + `snapshot`/`snapshot_after`
   + `cost_s2`. `stop:true` solo cierra tras `verify_final`
   determinista (nunca éxito solo-S2).

`BACK` re-ratificado: misma vía directa ya existente §5.2 (sin
target; con `guidance_for_s1`); forense `phase: s2_direct_back`.
Nada más cambia: `TYPE` sigue exigiendo foco + `text_payload`,
`OPEN_APP` solo en bootstrap/compilador, `HINT` nunca muta.

Alcance `@coder`: `s2_client.parse_command` acepta `TAP` (target
int obligatorio, rechaza `NONE`); `loop.apply_s2` rama `TAP`
con los 7 pasos; `s2_client.advise` system-prompt anuncia `TAP`
como macro ejecutable junto a `OPEN_APP/TYPE/BACK/HINT`;
tests: TAP-direct con mock `tap_node` + aserción sin segunda
pregunta S1; TAP con idx rotado → `S2_BAD_COMMAND`; TAP no
visible → `SELECTOR_NOT_FOUND`; TAP no-clickable → sin mutación.

### 12.2 Anti-entropía en listas densas: hint `first_result` (no podado-a-1)

**Rechazado: podar a 1 resultado.** Podar la tabla al primer match
es frágil y se prohíbe como estrategia: el primer item suele ser
anuncio/contenido irrelevante o inestable entre snapshots; con un
solo candidato S1/S2 no puede desambiguar, no hay verificación
cruzada, y cualquier reordenamiento convierte el paso en
`STALE`/`WRONG_TARGET` silencioso. La tabla sigue 0..253 + NONE
(§4); **nunca se recorta a 1 por heurística de contenido**.

En su lugar, el host marca un **hint estructurado** que S1 y S2
consumen como prior, no como orden:

- `first_result: int | None` en el observe/state: índice del
  **primer interactivo del contenedor principal mid-list**
  (lista densa = contenedor scrollable con N hermanos misma
  clase/`zone`; el host elige el primer `visible` + `clickable`
  con etiqueta no vacía; si no hay contenedor claro → `None`,
  nunca inventar).
- Viaja a **S1** en la cabecera del state (`first_result`) y a
  **S2** como línea `FIRST_RESULT: <idx>` sobre `table_lines`
  (misma tabla, sin recorte). Derivación pura en
  `loop_helpers`/`ui_normalizer`, sin literales de app.
- Semántica: prior de atención, no selección forzada. S1 lo pondera
  en su pass; **ante escalado en lista densa, S2 elige el índice
  (normalmente el marcado) vía `TAP`-direct §12.1** en vez de
  devolver `HINT` decorativo. Si el marcado no sirve (no visible /
  anuncio), S2 elige otro índice visible de la misma tabla y lo
  deja en `guidance_for_s1` el porqué en una frase.
- Forense: `first_result` en cada entrada de paso + `s2_command`
  con el `target` elegido (trazable si S2 siguió o ignoró el hint).

Alcance `@coder`: `build_table`/`read_screen` exponen
`first_result`; `jev_client.ask_decision` lo incluye en el state
EN; `_table_lines` antepone `FIRST_RESULT: n`; tests con tabla
densa sintética (stub) asertan el marcado, nunca con literales.

### 12.3 Fail-fast entre corridas: firma + regla operativa (formato, no daemon)

Si 2 corridas consecutivas mueren con **igual firma**, el
operador/subagente **NO relanza**: dif de forenses + informe.
Esto es regla operativa + formato forense; **no es daemon ni
watchdog en código** (el loop solo expone la firma).

Firma (`run_signature`, objeto JSON en la entrada final del
`logs/run-<ts>.jsonl` y en el resultado de `run_goal`):

```json
{
  "code": "STUCK_SAME | STUCK | TIMEOUT | S2_UNAVAILABLE | UI_UNSTABLE | input_unverified | ...",
  "stalled_step": "action+target sin progreso (p.ej. TAP:12, o ESCALATE-loop)",
  "snapshot_first": 0, "snapshot_last": 0,
  "fingerprint_first": "sha256", "fingerprint_last": "sha256",
  "progress": false
}
```

- `code` = código terminal honesto del resultado.
- `stalled_step` = decisión/acción que se repite sin efecto
  (misma `(action+target)` ×3, o `ESCALATE`→`HINT` sin mutación).
- `snapshot-estancado` = `snapshot_last == snapshot_first` (o
  `fingerprint_first == fingerprint_last`: mismo contenido
  id+texto ordenado, `screen_fingerprint` existente) → `progress:
  false`.
- Igual firma = mismo `code` **y** (mismo `stalled_step` **o**
  mismo par fingerprint estancado) en 2 corridas consecutivas del
  mismo goal.

Convención de log: `logs/run-<ts>.jsonl` (existente §7) + campo
`run_signature` obligatorio en la entrada final (`final` o la
última de paso con `error`). Comparar firmas = `diff` de las dos
entradas finales + informe (qué paso se estancó, qué pantalla no
cambió, hipótesis y próximo experimento único, no relanzamiento).

Alcance `@coder`: emitir `run_signature` siempre al cerrar con
`ok:false` (puro en `loop_helpers`, consumido en `run_goal`);
tests asertan el campo y su determinismo ante mismo historial.
Ningún auto-reintento en código.

### 12.4 Flujo portapapeles multi-app (genérico, sin nombres de apps)

Caso: la app-origen expone **Compartir → Copiar** y el enlace queda
en el clipboard del SO; el loop lo lee para verificar y lo inyecta
como `text_payload` en la app-destino. Contrato genérico, sin
paquetes ni títulos en lo normativo.

Protocolo (primitivas existentes, orden normativo):

1. `TAP`-direct o S1/`TAP` sobre el nodo de copiar (validado §8.1).
2. **Read-back del clipboard en host** por una de dos vías
   (la que el harness exponga, sin preferencia normativa):
   `adb shell dumpsys clipboard` parseado en host, o
   pegado-en-campo-efímero + read-back (`ACTION_SET_TEXT` no;
   pegado + lectura del `text` del nodo enfocado).
3. Verificación: contenido no vacío con forma genérica de enlace
   (`https?://`, validación solo por forma, sin literales de
   dominio). Vacío o sin forma → `CLIPBOARD_EMPTY` honesto, sin
   inventar URL, sin avanzar al destino.
4. Inyección: el contenido verificado entra como `text_payload`
   (slot opaco `clipboard`, solo `len`+`sha256` en forense, nunca
   crudo si el goal es sensible) y el `TYPE` destino lo escribe
   vía `ACTION_SET_TEXT` con read-back `confirm_input` (§5.4).
5. Forense: `clipboard_len` + `clipboard_sha256` + vía de lectura
   (`dumpsys` | `paste-readback`); compuerta crítica §8.2 si el
   goal implica comunicar a terceros (preview + `confirm:true`).

Alcance `@coder`: helper de harness `read_clipboard()` (adb-host,
fuera de `src/` de la app; en `mcp-server/tools` o scripts) +
slot `clipboard` en `pending_payloads`; tests con stub de
clipboard (vacío / con forma / sin forma). Sin `shell` en el
dispositivo antes de Fase 6 (`METHOD_NOT_ALLOWED` vigente);
el `dumpsys` corre en el **host adb**, no vía Shizuku-`shell`.

### 12.5 Aceptación `@judge` (certifica, sin editar)

Desde `mcp-server/`, además de §10.1–§10.7 (pytest verde, greps
vacíos, CostTracker, compuertas, bootstrap, payload EN):

1. `uv run pytest` verde con los tests §12.1–§12.4 (TAP-direct,
   `first_result`, `run_signature`, slot `clipboard` con stub).
2. Greps §10.2 extendidos a los nuevos símbolos, sin falsos
   positivos de contrato: siguen **vacíos en `src/`** para
   literales de app; `first_result`/`run_signature`/`clipboard`
   son vocabulario genérico permitido.
3. **UNA corrida KJ5** del goal de validación (instancia
   no-normativa: compartir vídeo de app-origen → persona en
   app-destino; valores aportados en runtime por S2/operador,
   nunca en `src/`): si la búsqueda **no pasa al 2º intento**,
   abortar y analizar el `logs/run-<ts>.jsonl` (fail-fast §12.3:
   dif de firmas + informe). Prohibido relanzar a ciegas la misma
   firma. Forense + `[COST]` exigidos igual que §10.3.

