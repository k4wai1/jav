# applied-refs — plan de aplicación de `refs/android-jev` + `refs/mobile-jev` al loop `run_goal`

> Estado: **plan @architect 2026-10-05, solo `docs/`**. Implementa `@coder`,
> certifica `@judge`. En conflicto, **AGENTS.md §9 (enmienda 2026-10-05) y
> `docs/specs/generic-dual-tier.md` v3 mandan**.
>
> Alcance: qué patrón robar de cada ref, dónde cae en nuestro árbol, en qué
> orden, con qué test y con qué riesgo. **No es código**: es la orden de
> trabajo para `@coder`. Cero literales de app en `src/` (los ejemplos con
> paquetes/personas en este doc son **no-normativos**, valores de test
> aportados por el stub S2 en runtime, nunca defaults del repo).

## 0. Objetivo que desbloquea todo + estado asumido

**Desbloqueador:** `run_goal("envía 'hola mundo' a Rupa por WhatsApp")` en
**≤2 min, ≤20 pasos**, con `confirm:true` del operador para el envío
(genérico §8.2: enviar/comunicar = crítica, preview + hash, auditada).

**Estado asumido (v3 commit `a21d30e`):**

- Bootstrap `OPEN_APP` funciona (S2-director → `mcp.open_app(package)` +
  ~600 ms + re-observe antes del primer S1).
- S1 EN con tabla enriquecida `[idx,class_short,flags,label]`, `DONE→S2`
  (`verify_done`), anti-giro `STUCK_SAME×3` (decisión repetida + acción
  repetida), `CostTracker` con `[COST]`.
- Fallos abiertos que este plan cierra: **S2-flash intermitente con content
  vacío** (hoy aborta a `S2_UNAVAILABLE` al primer `S2EmptyResponse`);
  **S1 conf 0.45 a primera vista con 64 cands** (hoy `LOW_CONF → escalate`
  inmediato, sin `focused_field` que desambigüe); **`type` sin clear ni
  read-back** (escribe sin saber si cayó); **sin `focused.holds` en state
  S1** (escrito ≠ enviado indistinguibles).

## 1. Restricciones duras (no negociables)

1. **100% genérico:** `grep -rniE 'whatsapp|com\.whatsapp|contact_name|verify_chat|wrong_chat' src/` → vacío.
   Paquetes/textos solo como **valores runtime** del comando S2 o del goal
   del operador; jamás literales en `src/`, prompts fijos o defaults.
2. **Sin `adb` / `uiautomator` / `input text` en `src/`:** mandan
   **Shizuku (`am start`/`monkey` en `open_app`, `ACTION_SET_TEXT` en
   `type`) + Accessibility (`dump_ui`, foco real del teléfono)**.
   Lo robado que hable de `adb shell input text|clipboard|uiautomator`
   se **reinterpreta**, no se copia: clear = reemplazo vía
   `ACTION_SET_TEXT` (semántica replace), read-back = re-`dump_ui`, nunca
   shell.
3. **Sin copiar endpoints / modelos / keys ajenos:** endpoints Jev/S2,
   ids de modelo y keys solo por env (`OPENROUTER_API_KEY`, `JEV_MODEL`,
   `GLM_MODEL`). Lo robado aporta **forma de validación y de loop**, no
   URLs ni ids.
4. **Tarifas y modelos solo por env:** `JEV_RATE_IN/OUT` (defaults
   `0.042/0.0` normativos), `GLM_RATE_IN/OUT` (placeholder ajustable
   documentado, nunca verdad oficial), `JEV_MODEL`/`GLM_MODEL`. Prohibido
   hardcodear precios/modelos de las refs.
5. `@architect` no toca código: este doc + futuros `*.md` / `docs/**` son
   su única salida.

## 2. Qué se roba (patrón) y qué NO se roba (implementación ajena)

### 2.1 `refs/android-jev` (FZ2000, adb+Jev) — 5 patrones

| # | Patrón robado | Origen en la ref | Qué NO se roba |
|---|---|---|---|
| A1 | `completion-noul + auto-finish`: pregunta `noul` "¿goal ya logrado en pantalla?" por paso; `DONE` solo si el propio S1 dice logrado | `goal.py: Choice/completion`, `decisions.py: RecordingDecider` (el bug "finish aceptado mientras completion decía lo contrario") | Su endpoint Jev, su `adb.py`, su `uiautomator`/`screen.py` |
| A2 | `focused_field{label,holds}` en el state: el campo que recibiría typing **y lo que contiene** distingue escrito-no-enviado de enviado | `state.py: FocusedField{label,kind,holds,is_password} + the_focused_field()` (leído del foco real, password → `"a password, not read"`) | Su `adb`/`xml` dump; aquí la fuente es `dump_ui` Jam + Accessibility |
| A3 | `type-replace` con clear: reemplazar legible = valor exacto esperado; appends con cursor desconocido conservan otro modo | `text_entry.py` (clear + `input text` ASCII), `actions.mjs`-análogo en mobile | `input text`/`clipboard`/`keyevent`: aquí `ACTION_SET_TEXT` vía Shizuku/Jam + `type` con `clear:true` semántico |
| A4 | Anti-giro por **firma de pantalla por contenido** (no por `snapshot_id`/tiempo): `already_tried_here` scoped a pantalla, historial acotado `RECENT_ACTIONS_KEPT=8` | `state.py: already_tried_here`, `decisions.py: signature/repeated` | Su conteo de screenshots; aquí hash de tabla normalizada |
| A5 | Forense **wire íntegro + timings por fase**: `state` exacto enviado + respuesta exacta recibida, una línea por step apendeada al ocurrir, `Timings{reading,deciding,acting,settling,watching}` por step | `decisions.py: Exchange{state,options,choice,probabilities}`, `runs.py: Timings + decisions.jsonl + run.json` | Su carpeta `PHONE_CONTROL_RUNS`/JPGs; aquí `logs/run-<ts>.jsonl` existente + campos nuevos |

### 2.2 `refs/mobile-jev` (droidrun, cloud+Jev) — 5 patrones

| # | Patrón robado | Origen en la ref | Qué NO se roba |
|---|---|---|---|
| M1 | `validateChoice` estricta + **consumir solo la rama elegida**: `choice∈criteria`, `probs` completas (`len==ids`, toda id presente), finitas `0..1`, `sum≈1 ±0.025`, `argmax`, `conf` finita; el loop jamás lee ramas no elegidas como fallback | `policy.mjs: validateChoice()` + `policy.decide` una sola operación/target por request | Su `http.mjs`/`pooledRequest`, su catálogo `OPEN_APP/TAP/TYPE/SCROLL/BACK/HOME/ENTER/WAIT` |
| M2 | Texto **exact-span + read-back sin retype ciego**: `prepareInputVerification` (target por `resourceId` o `id+hint+bounds`, excluye password) + `confirmInput` (poll hasta `inputMatches`, timeout); fallo → `input_unverified` **sin reintentar a ciegas** | `input-verification.mjs: prepare/confirm/inputMatches` | Su `device.act({type:'type',clear:true})` vía adb; aquí `type_text` vía Jam `ACTION_SET_TEXT` |
| M3 | `assertFresh` por acción + `fingerprint before/after`: mutación solo contra `expected` observation; `StaleObservationError` nunca reintenta mutación incierta; `before/after fingerprint` + `screenChanged` en historial | `agent.mjs: device.act(action,{expected})`, `device.mjs: StaleObservationError`, `entry{before,screenChanged}` | Su transporte `device.mjs`; aquí `snapshot_id` monotónico Jam + `by_idx` |
| M4 | Candidatos mínimos + `open_app` contra inventario (apps ≠ foreground, top 200, como rama `OPEN_APP`, no paseo por launcher) | `actions.mjs: candidatesFor()` + `policy.mjs: buildQuestions(observation,texts,apps)` | Su inventario `listApps`/launcher; aquí **ya cubierto por bootstrap v3 §5.3** (S2 resuelve package por conocimiento general, sin inventario local) → **sin acción nueva**, solo se cita como convergencia |
| M5 | JSONL por evento + **log-antes-de-observar**: `onAction` (mutación ejecutada) se loguea **antes** de `observe()`; un read fallido jamás borra la acción ejecutada; `timings{model,action,observation,wait,modelCalls,wallMs}` | `agent.mjs: onStep/onAction/onObservation + timings` | Su `harness/cli`; aquí formato `logs/run-<ts>.jsonl` existente |

**Mapa a este plan:** A2→P0-1 · A3+M2→P0-2 · M1→P0-3 · tolerancia S2-vacío→P0-4 (endurece el `S2EmptyResponse` de `297e6b1`, no existe en refs, se pide explícito) · A4→P1-5 · M3→P1-6 · A5+M5→P1-7 · A1→ya cubierto por gate `DONE→S2 verify_done` (`18fd704`; solo se añade `completion-noul` como señal auxiliar en P2, sin auto-finish ciego) · M4→ya cubierto por bootstrap v3 (sin acción).

## 3. P0 — desbloquean el envío (orden de implementación)

### P0-1 `focused_field{label,holds}` en state S1 + normalizer (distinguir escrito vs enviado)

- **Por qué desbloquea:** hoy S1 ve 64 labels sin saber si "hola mundo"
  ya está en el campo (conf 0.45 → escalate eterno). Con `holds`, el pass
  "campo contiene el texto" sube a `TAP(Send)`/`DONE` y el pass "campo
  vacío" baja a `TAP(campo)→TYPE`; es la causa medida en la ref (0.42–0.47
  vs 0.51 inseparables sin `holds`).
- **Archivo(s) a tocar:**
  `mcp-server/src/jev_mcp/state.py` (+ `ui_normalizer.py`, `tools/ui.py`,
  `core/loop_helpers.py`, `jev_client.py`) — solo host, sin app Jam en P0.
- **Cambio exacto:**
  1. `state.py`: nuevo `@dataclass FocusedField{label,kind,holds,is_password}` +
     `as_view() -> {label,kind,holds}` donde password → `holds="a password, not read"`
     (nunca viaja valor secreta) y `NormalizedState.focused_field: FocusedField|None = None`.
  2. `ui_normalizer.py`: `the_focused_field(nodes)`: editables del dump;
     elegido = focuseado real si hay, si no el primero editable; `holds = text`
     recortado ≤140; password por marcadores `password|passwd|passcode|pin|credential`
     en `class/resource_id/hint/desc`. No inventa foco desde layout.
  3. `tools/ui.py:read_screen()`: expone `focused_field` (vista, sin secreto)
     + `screen_height` ya existente.
  4. `core/loop_helpers.py:build_table()`: propaga `focused_field` sin alterar
     filas (las filas ya llevan `foc` en `flags`; el objeto va aparte).
  5. `jev_client.py:ask_decision()`: añade al `state` EN
     `"focused_field": {"label":…,"holds":…|"empty"|"a password, not read"}`
     (clave EN, valor `empty` si `None`). 100% EN; sin literales de app.
- **Test que lo cubre (debe crear `@coder`):**
  `mcp-server/tests/test_normalizer.py::test_focused_holds_written_vs_sent`
  (campo con `text="hola mundo",focused=true` → `holds="hola mundo"`;
  tras envío simulado `text=""` → `holds="empty"`) +
  `test_loop.py::test_s1_state_carries_focused_field_en`
  (captura `state` enviado a `ask_decision`, aserta clave `focused_field`
  EN + `holds`, cero español, password enmascarada).
- **Riesgo:** bajo. Solo lectura + payload; si `dump_ui` no marca foco,
  `holds` cae a primer editable (ruido menor, no mutación). Mitiga:
  password nunca sale del host (forense guarda `holds_hash`, no valor).

### P0-2 `type_text` = clear-antes-de-escribir + verificación read-back (`input_unverified` sin retype ciego)

- **Por qué desbloquea:** hoy `type` escribe sin saber si cayó; el loop
  avanza a `TAP(Send)` con campo vacío o retypea a ciegas duplicando texto.
- **Archivo(s) a tocar:** `mcp-server/src/jev_mcp/tools/ui.py` (`type_text`),
  `mcp-server/src/jev_mcp/loop.py` (rama `TYPE`), `mcp-server/src/jev_mcp/core/loop_helpers.py`
  (helpers puros `prepare_input_verification/input_matches`).
- **Cambio exacto:**
  1. `tools/ui.py:type_text(node_id,snapshot_id,text)`: semántica **replace**
     (clear-antes-de-escribir vía `ACTION_SET_TEXT` Jam; sin `adb input text`).
     Devuelve `{ok, chars, snapshot_id_post}` sin re-observar dentro (el
     loop verifica; respeta "acciones no devuelven snapshot").
  2. `core/loop_helpers.py`: `prepare_input_verification(row, text)` → `None`
     si no-editable/password/texto vacío; si no `{target:{id,resource_id,hint,bounds},text}`.
     `input_matches(candidates, verification)` → exact-span: mismo `resourceId`
     (o `id+hint+bounds` si sin rid estable) **y** `text==verification.text`
     en exactamente 1 candidato.
  3. `loop.py` rama `TYPE`: tras `execute_fn(type_text)` → `observe()` fresco
     + `confirm_input(initial, verification, observe, timeout_ms=2500, poll_ms=60)`
     (constantes nombradas `INPUT_TIMEOUT_MS/POLL_MS`, testeables por inyección).
     Éxito → sigue; fallo → `finish('input_unverified', {…reason:"Text was sent, but its complete value could not be confirmed…Inspect before retrying"})`
     **sin retype**, con `before/after fingerprint` en forense. Foco sigue
     exigible (`NOT_FOCUSED` → tap previo explícito, sin cambio).
- **Test que lo cubre:** `tests/test_loop.py::test_type_replace_then_readback_ok`
  (stub `observe` devuelve campo con texto exacto → `verified`) +
  `::test_type_mismatch_yields_input_unverified_without_retype`
  (campo con texto parcial → `code=input_unverified`, aserta `execute` llamado
  **1 vez**, sin segundo `type_text`) + unit
  `test_core_*::test_input_matches_exact_span` (rid estable vs fallback
  `id+hint+bounds`, password → `None`).
- **Riesgo:** medio-bajo. Poll 2.5 s añade latencia solo en `TYPE`
  (≤2 por envío); timeout mal calibrado → `input_unverified` falso. Mitiga:
  timeout/poll por constantes inyectables + P1-7 mide `watching_the_result`.

### P0-3 `validateChoice` estricta + consumir solo la rama elegida

- **Por qué desbloquea:** hoy `_norm()` acepta `choice∈criteria` con
  `p=confidence` aunque `probabilities` venga incompleta; un S1 a 0.45 con
  64 cands puede colar target fuera de tabla como `conf` válida. La ref
  demuestra que el bug vive en la interfaz Jev, no en el outcome.
- **Archivo(s) a tocar:** `mcp-server/src/jev_mcp/jev_client.py` (`_norm`/`ask`),
  `mcp-server/src/jev_mcp/core/loop_helpers.py` (`check_decision_json` como
  segunda red, sin duplicar lógica de ramas).
- **Cambio exacto:** `_norm(name,q,ans)` pasa a `validate_choice(answer,criteria)`:
  `answer.type=="choice"` ∧ `choice∈criteria` ∧ `probabilities` es dict no-lista
  ∧ `len(probs)==len(criteria)` ∧ toda id de criteria presente en probs ∧
  todo `[confidence,*probs.values()]` finito en `[0,1]` ∧ `|sum(probs)-1|≤0.025`
  ∧ `probs[choice]+1e-6 ≥ max(probs.values())`. Fallo → `JevHallucination("TypeSafe returned an invalid choice distribution.")`.
  `ask_decision`: `conf = min(action.confidence, target.confidence)` (ya existe;
  se añade `finite` check) y **consume solo** `action.key/target.key/noul.key`;
  prohíbe leer otras entradas de `probs` como fallback (comentario normativo).
  `check_decision_json` se mantiene como red de forma (enum/rango), no de
  distribución.
- **Test que lo cubre:** `tests/test_jev_validate.py` (nuevo, osuite en
  `test_loop.py` si `@coder` prefiere): probs incompletas → hallucination;
  suma 0.5 → hallucination; no-argmax → hallucination; `conf=NaN/Inf` →
  hallucination; rama no elegida con p alta ignorada (solo `choice` actúa).
- **Riesgo:** medio. Si el proveedor real no devuelve `probabilities`
  completas, todo S1 fallaría. Mitiga: si tras medir (P2) el proveedor no
  cumple el contrato, `@coder` propone enmienda a este spec (relajar a
  `choice∈criteria + conf finita` con `probabilities` opcional) — **no
  relaja en silencio**: test + doc.

### P0-4 Tolerancia S2-vacío degradada y acotada (1 re-pregunta S1 conservadora, techo `STUCK_SAME×3`)

- **Por qué desbloquea:** hoy `S2EmptyResponse` (flash intermitente, content
  vacío tras reintento) aborta a `S2_UNAVAILABLE` aunque S1 tuviera un paso
  útil (p.ej. `TAP(campo)` con conf 0.8). El envío muere por un transitorio
  de S2.
- **Archivo(s) a tocar:** `mcp-server/src/jev_mcp/loop.py` (4 sitios:
  `bootstrap`, `escalate()`, rama `TYPE/open-text`, gate `DONE/verify_done`).
- **Cambio exacto:** ante `S2EmptyResponse`, **no abortar de inmediato**:
  1. log forense `{s2_empty:true, attempt}` + `CostTracker` sin cargo extra;
  2. **1 sola** re-pregunta S1 **conservadora** con `s2_guidance` temporal EN
     `"System-2 unavailable (empty response). Proceed conservatively: only TAP a visible field, BACK, or ESCALATE; never TYPE without text_payload, never DONE."`
     + `need_text=false` forzado;
  3. si el S1 resultante es `ESCALATE/BACK/TAP-visible/DONE-rechazado` se
     ejecuta con compuertas normales; si es `TYPE` sin `text_payload` →
     `planned`/`escalate` (nunca escribir inventado); si el siguiente S2
     vuelve a vaciar → abort `S2_UNAVAILABLE` honesto.
  Contador `s2_empty_streak` (máx 1 por escalado, reset al avanzar snapshot);
  **techo invariante `STUCK_SAME×3`** (decisión idéntica sin cambio útil de
  fingerprint → abort) y `MAX_STALE_STREAK=3` intactos.
- **Por qué NO reintroduce el giro de 25 pasos:** el giro histórico nació de
  reintentar S2/mutaciones sin techo ni cambio de fingerprint. Aquí: (a) una
  sola degradación por incidente, (b) sin mutación irreversible (TYPE/DONE
  gateados), (c) el `same_dec_streak` y `repeated{ fingerprint:action }`
  siguen contando durante la degradación, (d) `DONE` sigue exigiendo
  `verify_done` S2 real (sin S2 no hay éxito). Peor caso: 1 paso S1 extra
  antes del mismo abort honesto.
- **Test que lo cubre:** `tests/test_loop.py::test_s2_empty_degrades_once_then_aborts`
  (`advise` = `S2EmptyResponse` ×2, `decide` = TAP-visible conf 0.8 → aserta
  1 `tap_node` ejecutado + segundo vacío → `S2_UNAVAILABLE`) +
  `::test_s2_empty_never_types_without_payload`
  (S1=`TYPE` sin payload durante degradación → no hay `type_text`, solo
  `planned`/`escalate`).
- **Riesgo:** bajo-medio. Riesgo de ocultar caída S2 real como "paso
  conservador". Mitiga: forense marca `s2_empty:true` + `degraded:true` y el
  acumulado `s2_calls` cuenta el intento; `@judge` puede alertar si
  `s2_empty` > tasa acordada en P2.

## 4. P1 — robustez (después de que P0 esté verde)

### P1-5 Firma de pantalla anti-giro por contenido (ignorar tickers)

- **Archivos:** `core/loop_helpers.py` (`screen_fingerprint(rows, focused_holds)`),
  `core/guards.py` (`check_stuck_same` extendido o nuevo `check_screen_stuck`),
  `loop.py` (sustituir/complementar `snapshot==prev_snapshot` por firma).
- **Cambio exacto:** `fingerprint = sha256(sorted[(class_short,label,flags,focused,holds_hash)])`
  sobre filas visibles **excluyendo** nodos ticker (hora, batería, notificaciones
  con `resource_id` de decoración ya filtrada + `text` que cambia cada segundo:
  se excluyen por `DECOR_SUBSTR` del normalizer + regex de hora `^\d{1,2}:\d{2}$`
  **genérica**, sin literales de app). `repeated.add(f"{fingerprint}:{action}")`;
  misma firma + misma acción ×3 → `STUCK_SAME`. `snapshot_id` deja de ser señal
  de cambio (solo es frescura). `RECENT(history)` acotado a últimos 8 para el
  prompt (ahorro tokens, convergencia con A4).
- **Test:** `test_stuck_signature_ignores_ticker` (dos observes que difieren
  solo en `"12:01"`→`"12:02"` + mismo TAP ×3 → `STUCK_SAME`; con cambio real
  de lista → no aborta).
- **Riesgo:** bajo. Regex de hora demasiado amplia podría ignorar un código
  real; se limita a nodos no-clickables/no-editables.

### P1-6 `assertFresh` por tipo de acción + `fingerprint before/after`

- **Archivos:** `core/loop_helpers.py` (`assert_fresh(action_kind, snapshot, current_snapshot)`),
  `loop.py` (`_execute`/`device.act` con `{expected}`), `tools/ui.py` (propagar
  `STALE_SNAPSHOT` Jam sin reintentar mutación).
- **Cambio exacto:** `TAP/TYPE` exigen `snapshot==current` (si no →
  `STALE_SNAPSHOT`, re-observe, `stale_streak++`, ×3 → `UI_UNSTABLE`);
  `SCROLL/BACK` toleran 1-stale (re-observe silencioso, no cuentan como
  `stale_streak`); **mutación incierta nunca se reintenta** (excepción →
  abort, no retry). Historial `entry{before:fingerprint, after:fingerprint,
  screenChanged:bool}`.
- **Test:** `test_stale_tap_reobserves_once` + `test_stale_type_never_retries_blind`
  (inyección `execute_fn` que devuelve `STALE_SNAPSHOT` → aserta 0 doble-typing).
- **Riesgo:** bajo. Añade 1 re-observe por carrera real (ms); evita el doble-envío,
  que es el incidente que originó §5.14-16.

### P1-7 Forense wire íntegro + timings por fase + log-antes-de-observar

- **Archivos:** `loop.py` (`log(entry)` + `run_goal` timings), opcional
  `scripts/run_goal_check.py` (volcado legible, ya previsto en v3 §11).
- **Cambio exacto:** cada entrada JSONL lleva `{step, phase, goal_hash,
  snapshot, fingerprint_before/after, state_sent (tabla+focusholds+screen_goal, sin PII cruda),
  wire:{request,response} verbatim, decision{action,target,conf,tau},
  s2_command_redacted, text_payload_hash+len (nunca texto),
  cost{[COST]}, timings{reading,deciding,acting,watching,total}, error?}`.
  **Orden:** `history.append + log(onAction)` **antes** de `observe()` post-mutación
  (un read fallido jamás borra la acción). `Timings` por step (no solo total),
  con `performance.now()`-equivalente `time.perf_counter()`.
- **Test:** `test_forensics_wire_and_timings` (corrida con stubs → cada línea
  parsea JSON, tiene `wire` + `timings` con claves exactas, `text` crudo ausente,
  acción presente aunque `observe` post-falle).
- **Riesgo:** mínimo. Solo I/O append + `hash`; coste µs/KBs. PII: enmascara
  `mask_pii` S2 ya existente + `holds_hash` para foco.

## 5. P2 — calibración (medir antes de fijar; prohibido fijar números sin medir)

**P2-8 Experimento conf-media-a-1ª-vista vs tabla EN enriquecida; decidir `tau` o rank-por-relevancia.**

- **No es un cambio de valor:** `@coder` **no baja `TAU=0.70` ni reordena
  la poda** en este paso. Entrega instrumentación + informe medido; el
  cambio de umbral/rank, si procede, va en enmienda posterior con números.
- **Archivos:** `loop.py` (ya emite `conf/tau/n_cands` por paso; añadir
  `conf_step1, n_cands_step1` al resultado), `scripts/run_goal_check.py`
  (`--goal` ×N con stub/S1 real, vuelca CSV `step1_conf,n_cands,holds_present`),
  `docs/BUILD.md`-análogo o `logs/` informe (no en `src/`).
- **Protocolo:**
  1. Corpus ≥20 goals genéricos (sin app prefijada; Rupa/WhatsApp solo como
     1 caso no-normativo) × 3 corridas, S1 real, tabla EN enriquecida actual.
  2. Métricas: media/p50/p10 de `conf` en step 1, correlación `conf vs n_cands`,
     tasa `LOW_CONF-escalate` en step 1, tasa de éxito ≤20 pasos.
  3. Brazo B (mismo corpus): rank por relevancia al goal (`text_match` existente
     sobre `label+flags`, editables con `holds` vacío primero) antes de podar a
     254, sin tocar `tau`; compara misma métrica.
  4. Decisión: si P10 step-1 < `tau` pero éxito con 1 escalado es alto →
     propone `tau_step1` menor **o** `escalate→HINT-sin-mutación` en step 1;
     si rank-B sube `conf` ≥+0.15 con mismo éxito → propone rank; si no,
     mantiene `0.70`. Todo con intervalos, sin "número mágico".
- **Test:** `test_calibration_harness_runs_offline` (el script corre con stubs
  y produce CSV con columnas exactas; no aserta ningún umbral).
- **Riesgo:** cero en producción (solo medición). Riesgo metodológico: medir
  con stub en vez de S1 real invalida; el protocolo exige S1 real salvo el
  test offline.

## 6. Orden de implementación para `@coder` + aceptación por tramo

1. **P0-1 → P0-3 → P0-2 → P0-4** (estado → validación → escritura verificada →
   tolerancia). Cada uno con su test en el mismo commit; `uv run pytest` verde.
2. **P1-5 → P1-6 → P1-7** (firma → frescura → forense que lo demuestra).
3. **P2-8** instrumentación + informe, sin cambio de umbral.

**Aceptación `@judge` (además de `generic-dual-tier.md` §10):**

- `uv run pytest` verde (tests nuevos P0–P1 presentes por nombre).
- `grep -rniE 'adb shell|uiautomator|input text|clipboard' src/` → vacío
  (Shizuku+Accessibility; `wm size` heredado en `tools/ui.py:screen_height`
  se permite solo como cache de altura o se sustituye por `dump_ui`, con
  comentario; nunca como vía de acción).
- `grep -rniE 'openrouter\.ai/api/(alpha/decisions|v1/chat)' src/` solo en los
  dos clientes existentes (`jev_client/s2_client`), con modelos por env;
  ninguna URL/modelo/key de las refs.
- Corrida `run_goal` con stubs reproduce `focused_field`, `input_unverified`
  sin doble-type, `validateChoice` rechazos, `s2_empty→degraded×1→abort`,
  `fingerprint before/after`, `wire+timings`, `[COST]` por paso.
- E2E desbloqueador (con keys + Jam + `confirm:true`): "hola mundo" visible
  en campo (read-back `verified`) y `preview` de envío auditado, ≤2 min.

## 7. Trazabilidad ref → plan (para revisión)

- A1 completion-noul → ya en `DONE→S2 verify_done`; P2 la añade como señal
  auxiliar, sin auto-finish ciego (la ref prohíbe aceptar `finish` contra
  `completion`).
- A2 `focused_field.holds` → P0-1. A3 clear → P0-2 (vía `ACTION_SET_TEXT`).
  A4 firma → P1-5. A5 wire+timings → P1-7.
- M1 strict + una rama → P0-3. M2 exact-span+read-back → P0-2.
  M3 assertFresh+fingerprint → P1-6. M4 inventario → ya en bootstrap v3
  (convergencia, sin código). M5 log-antes → P1-7.
