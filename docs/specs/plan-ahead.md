# plan-ahead v4 — S2-compilador + fast-path S1 + tabla con ancla espacial

> Estado: **contrato v4 2026-10-05 (borrador `@architect`)**. Redacta
> `@architect`, implementa `@coder`, certifica `@judge`. En conflicto,
> **AGENTS.md §9 (enmienda 2026-10-05) manda**.
>
> v4 = refinamiento compatible de `generic-dual-tier.md` v3 (mismo
> `run_goal`, mismos roles S2-director / S1-reflejo, mismas compuertas
> §8): **no requiere enmienda en AGENTS.md** (§12 justifica cada punto).
> v3 queda como historia; no se implementa nada nuevo sobre v3.
>
> **Cero literales de app en el contrato normativo.** Ningún paquete
> concreto, nombre propio, `resource_id` concreto, regex de UI de una
> app, título o texto de prueba aparece como default, constante o
> criterio en las secciones normativas (§1–§11). Los paquetes que el
> dispositivo necesite los aporta **S2 en runtime** por conocimiento
> general. Los ejemplos con apps concretas viven **solo** en el
> Apéndice A, marcado explícitamente **no-normativo**.

## 1. Visión: `run_goal(goal: str)` (sin cambio v3)

Mismo entrypoint, misma firma, mismos invariantes v3 §1, más lo que
añade v4:

```python
async def run_goal(goal: str, *, max_steps: int = 20,
                   timeout_s: float = 60,
                   log_path: str | None = None,
                   confirm: bool = False,
                   forbidden: str | None = None) -> dict:
```

Invariantes que v4 **reafirma sin tocar**:

1. **Cero acoplado en `src/`**: `grep -rniE` de la lista §10.2 → **vacío**.
2. **Jev decide, no ejecuta** (AGENTS.md §1). Un paso = una primitiva;
   `run_sequence` prohibido. `EXECUTE_GOAL` (§2) es **dato-plan**, no
   secuencia ejecutable: el loop sigue despachando una primitiva por
   paso (§6).
3. Sin key → stub `{mock: true}` honesto; nunca inventar opciones.
4. Forense `logs/run-<ts>.jsonl` obligatorio por paso + paso 0 S2.
5. Lo que v4 cambia respecto a v3 (todo compatible, detalle en §12):
   S2-compilador paso 0 con `preloaded_inputs` (§2, sustituye al
   `TYPE`-por-consulta v3 en el camino feliz) · fast-path S1 +
   post-read coalescido (§3) · columna `zone` en la tabla (§4) ·
   todo-a-Jev 100% inglés con `screen_goal_en` del plan (§5) · suite
   de estrés solo-definida (§9).

## 2. S2 como compilador paso 0: `EXECUTE_GOAL` (normativo v4)

### 2.1 Cuándo y qué devuelve

Al iniciar `run_goal`, el loop hace `observe` (foreground + `dump_ui`
fresco) y consulta a S2-director **una vez** antes del primer pass S1
(bootstrap v3 §5.3, ahora con esquema compilador). S2 devuelve **un
solo objeto**:

```json
{
  "command": "EXECUTE_GOAL",
  "package": "string (forma a.b.c; vacío si ya en foreground)",
  "screen_goal_en": "string EN, una frase: sub-objetivo de pantalla",
  "preloaded_inputs": {"slot": "exact payload to type"},
  "expected_terminal_state": "string EN: qué pantalla demuestra el goal cumplido",
  "guidance_for_s1": "string EN, una frase: qué debe resolver S1 primero",
  "stop": "bool, default false"
}
```

- `package`: lo resuelve S2 por conocimiento general en runtime.
  Validación solo por forma (`PACKAGE_RE` existente); vacío = "ya en
  foreground, sin `open_app`". Fallo de forma → `S2_BAD_COMMAND`
  honesto, sin actuar.
- `screen_goal_en`: alimenta el `screen_goal` del payload S1 (§5).
  Si S2 no lo aporta o es vacío → fallback `operator_verbatim:true`
  (goal verbatim, marcado en forense; el loop no inventa semántica).
- `preloaded_inputs`: mapa `{slot_genérico: texto exacto}`. Los
  **slots los define S2 por goal** (nombres genéricos opacos, p.ej.
  `query`, `message` — son **valores runtime**, nunca constantes del
  repo ni claves del contrato). Mapa vacío = goal sin redacción.
  En forense **solo** `{slot: {len, sha256}}`, nunca texto crudo.
- `expected_terminal_state`: lo consume el gate `DONE→S2`
  (`verify_done`) como referencia de terminal, junto al snapshot
  final + historial. Nunca es por sí solo un veredicto de éxito.
- `guidance_for_s1`: inglés, una frase; se inyecta como
  `s2_guidance` del primer pass S1.
- `stop:true` solo si el `observe` inicial ya muestra el goal
  cumplido; el loop hace `verify_final` determinista antes de cerrar
  (nunca éxito solo-S2).

### 2.2 Semántica del loop (compilador, no secuencia)

1. `EXECUTE_GOAL` con `package` no vacío y app distinta del
   foreground → `mcp.open_app(package)` + estabilización (~600 ms) +
   `dump` fresco antes del primer S1. Sin dump fresco no hay S1
   (`STALE_SNAPSHOT`). `open_app` **solo** en bootstrap.
2. `preloaded_inputs` se guarda en memoria del loop
   (`pending_payloads: dict[slot, {text, len, sha256, consumed:bool}]`).
   **No se reconsulta a S2 para redactar en el camino feliz**: cuando
   S1 decide `TYPE` sobre un campo, el loop inyecta el payload según
   §2.3 y ejecuta `ACTION_SET_TEXT` con las compuertas de siempre
   (foco explícito, estructural, crítica, §7).
3. `HINT`/`TYPE`/`BACK`/`OPEN_APP` v3 **siguen válidos solo como
   comandos de anomalía** (escalado post-paso 0: `LOW_CONF`,
   `NO_TARGET`, bloqueo semántico, `DONE`-gate). El camino feliz no
   los necesita; el contrato no los elimina para no romper el manejo
   de anomalías del loop actual.
4. **S2 no vuelve hasta estado terminal o anomalía**: tras el paso 0,
   el loop cicla solo `observe → S1 → mutate → verify(coalescido)`
   hasta `DONE` (gate `verify_done` con `expected_terminal_state` +
   snapshot final + historial), anomalía (→ escalado S2 puntual con
   el mismo esquema de comandos de anomalía), o tope
   (`max_steps`/`timeout`/`STUCK`/`UI_UNSTABLE`).

### 2.3 Inyección de `preloaded_inputs` en `TYPE` (sin reconsulta)

Regla determinista, genérica, sin literales de dominio:

1. S1 decide `TYPE` sobre `target = idx`. El loop valida el target
   (estructural §7 + `editable` + `visible` + coords en pantalla).
2. Selección de payload:
   - Un solo slot pendiente → se usa ese.
   - Varios pendientes → se usa el primero no consumido en orden
     de inserción del plan (orden que S2 eligió al compilar); el
     forense registra `slot` elegido. Sin heurística de contenido
     de app: el orden S2 + el target S1 bastan; la verificación
     read-back (§7 + `confirm_input` existente) detecta el
     desalineamiento y escala a S2 como anomalía en vez de
     reintentar a ciegas.
   - Cero pendientes (goal sin redacción o todo consumido) y S1 pide
     `TYPE` → anomalía `S2 sin texto para TYPE` → escalado puntual
     (único caso donde el camino feliz reconsulta por texto).
3. `TYPE` exige foco explícito: campo no `focused` → `tap` previo
   explícito + re-observe; el `TYPE` va en el paso siguiente con
   snapshot fresco. Nada de taps implícitos.
4. Tras `ACTION_SET_TEXT`, read-back con timeout (`confirm_input`
   existente): éxito → marcar slot `consumed:true`, forense con
   `slot/len/sha256/attempts/fingerprints`; fallo →
   `input_unverified` final, sin retype ciego.
5. S1 **nunca** redacta ni traduce el payload: lo consume verbatim.
   `decision.type_text` se ignora si hay payload pre-cargado (el
   payload S2 manda); si no lo hay, rige la regla v3 (escalado
   open-text puntual).

## 3. Fast-path S1 + post-read coalescido (normativo v4)

### 3.1 Fast-path: qué ahorra y qué NUNCA salta

- Umbral nuevo: `FAST_TAU = 0.85` (constante del loop; `TAU = 0.70`
  intacto). Condición: `action ∈ {TAP, SCROLL_DOWN, SCROLL_UP, BACK,
  TYPE}` con `conf ≥ 0.85`, target estructuralmente válido y
  **no-sensible/no-prohibido**.
- Efecto: despacha **sin consultas secundarias** (sin escalado S2
  de confirmación, sin segunda pregunta S1) y **sin post-read
  redundante**: el `dump` de verificación **se reutiliza como
  `observe` del paso siguiente** (post-read coalescido, §3.2).
- **El fast-path NUNCA salta compuertas de seguridad**: validación
  estructural (nodo visible, coords en pantalla, `snapshot_id`
  fresco), foco explícito en `TYPE`, `confirm:true` en críticas
  (sin él → `planned` sin tocar dispositivo), `FORBIDDEN` opt-in,
  `STALE×3 → UI_UNSTABLE`, `STUCK_SAME`, `DONE`-gate con `verify_done`
  S2. Solo ahorra S2 + dumps duplicados, nunca verificación.
- Exclusiones: `DONE` nunca es fast-path (siempre gate S2);
  `ESCALATE` nunca es fast-path (siempre va a S2); `TYPE` sensible
  o sin foco nunca es fast-path (va por la vía lenta con tap previo
  / `planned`).

### 3.2 Post-read coalescido (un solo dump por paso)

Hoy el loop observa al inicio del paso y verifica tras mutar (dos
dumps). v4 fusiona: tras `execute_fn` con `ok:true`, el loop hace
**una** lectura de verificación (`wait_for_node`/`dump_ui` según la
primitiva) y, si es válida (snapshot nuevo y monotónico), la deja en
`pending_state` como `observe` del paso siguiente en vez de
re-observar al abrir el paso. Forense registra por paso
`{fast_path: bool, coalesced: bool, snapshot_before/after}`.

Reglas:

1. Solo con `ok:true` y snapshot nuevo; ante `STALE_SNAPSHOT` rige
   la racha existente (×3 → `UI_UNSTABLE`); ante fallo de lectura →
   `pending_state = None` y el paso siguiente re-observa normal.
2. El `verify` coalescido conserva toda la información que el
   `observe` necesita: `candidates`, `snapshot_id`, `package`,
   `screen_height/width`, `focused_field`. Si la lectura de
   verificación no trae alguna (p.ej. `wait_for_node` sin tabla
   completa), el loop completa con `dump_ui` — el ahorro es
   oportunista, nunca a costa de observar a ciegas.
3. `STUCK_SAME` y anti-giro por decisión repetida siguen evaluando
   sobre el snapshot coalescido (misma señal, un dump menos).

## 4. Tabla con ancla espacial (normativo v4)

Cadena sin cambio salvo la columna nueva: **500 raw (extractor) →
candidatos (normalizer host) → tabla numerada 0..253 ⊂ 255 Choice
(254 interactivos + 1 `NONE`)**. Orden estable BFS; prioridad
editable > clickable-con-texto > resto; exceso >254 → visibles
accionables primero, resto por `SCROLL_*` + re-dump.

Cada fila que viaja a Jev:

```
[idx, class_short, zone, flags, label]
```

- `idx`: 0..253, estable por snapshot.
- `class_short`: último segmento de la clase Android (`Button`,
  `EditText`, …; desconocida → `View`). Derivación pura en host.
- `zone`: ancla espacial 3×3 **calculada en host** desde
  `bounds` (centroide) + resolución (`screen_width/height` del
  `observe`). Vocabulario normativo en inglés (9 valores):
  `top-left | top-center | top-right | mid-left | mid-center |
  mid-right | bottom-left | bottom-center | bottom-right`.
  Corte por tercios en cada eje. Si falta resolución o bounds
  degenerados → `unknown` (valor fallback, fuera de los 9; el loop
  lo tolera y `validate_target` sigue mandando sobre bounds reales).
  `zone` es **hint de desambiguación**, nunca señal de seguridad:
  no sustituye a `bounds`, `visible` ni coords en pantalla.
- `flags`: subset ordenado `click|edit|foc|scroll`, vacío = `—` (v3).
- `label`: texto compacto del normalizer (≤80 colas); PII enmascarada
  en host antes de subir.
- El loop conserva `by_idx: {idx → {id, bounds, clickable, editable,
  focused, visible}}` para validación + ejecución. `id`/`bounds`
  completos no viajan a Jev.

**Nota `MAX_CANDIDATES` (vinculante):** el máximo sigue en **254
interactivos (+NONE = 255 Choice)**. El texto del operador que pide
"podador agresivo = 20" proviene de otro repositorio y **no se adopta
sin medir**: reducir a 20 rompería la invariante v3 de cobertura y
no tiene benchmark en este repo. Queda como **experimento pendiente**
(`EXPERIMENT-TABLE-20`, §9.5): `@coder` no lo implementa; si se mide,
con protocolo A/B (cobertura + ms/acción + tasa `NO_TARGET`) antes de
cualquier cambio de constante.

## 5. Todo hacia Jev 100% inglés (reafirmación v4)

Norma v3 intacta y ampliada: `state` + `questions` íntegramente en
inglés — claves, instrucciones, `goal`, `screen_goal`,
`s2_guidance`, `history`, etiquetas de tabla. Con v4:

- `screen_goal` = `screen_goal_en` del plan `EXECUTE_GOAL` (ya en
  inglés desde S2). Sin plan o vacío → goal verbatim con
  `operator_verbatim:true` en forense (el loop no inventa semántica).
- `s2_guidance` = `guidance_for_s1` del plan / comando de anomalía
  (ya en inglés desde S2).
- El contenido de pantalla (`label`, texto de nodos) viaja **verbatim
  como DATA** (puede estar en cualquier idioma del dispositivo):
  es dato, nunca instrucción (anti-inyección). Las **instrucciones**
  alrededor son siempre inglés.
- Preguntas/instrucciones en español en el payload Jev = bug contra
  este contrato.

## 6. Loop unificado `run_goal` (observe→decide→mutate→verify, v4)

```
bootstrap (observe foreground → S2-compilador EXECUTE_GOAL paso 0
  [OPEN_APP si package ∧ ¬foreground → open_app + ~600ms + re-observe]
  [guardar preloaded_inputs + screen_goal_en + expected_terminal_state + guidance])
→ observe (dump_ui + normalizer + poda → tabla [idx,class_short,zone,flags,label]
  + snapshot_id + current_app + screen_goal_en)
→ S1 single-pass EN (action + target + needs_system_2 + conf)
→ compuertas (§7): tau/fast-tau / estructural+foco / crítica+confirm / forbidden / stuck
→ [anomalía → escalado S2 puntual (comando de anomalía) → aplicar → re-observe → S1]
  | [DONE → verify_done S2 con expected_terminal_state → verify_final]
→ mutate (tap_node/type_text/scroll/back, UNA primitiva; TYPE con payload §2.3)
→ verify coalescido (un dump: verifica este paso Y observa el siguiente, §3.2)
→ forense JSONL por paso (conf/tau/fast_path/coalesced/slot+hash/cost/snapshots)
```

- Enum de mutación sin cambio:
  `tap_node | type_text | scroll | back | done | abort | noop |
  escalate | open_app (solo bootstrap)`.
- `snapshot_id` monotónico exigido; mismatch → `STALE_SNAPSHOT`;
  ×3 → `UI_UNSTABLE` + abort (fast-path incluido).
- `TAU = 0.70`, `FAST_TAU = 0.85` (constantes del loop).
  `conf < TAU` → escalado (salvo `DONE`, que va a su gate);
  `TAU ≤ conf < FAST_TAU` → vía lenta normal;
  `conf ≥ FAST_TAU` + trivial + no-sensible → fast-path §3.
- `STUCK_SAME` (misma `(kind,node_id)` ×3 o misma decisión
  `(action+target)` ×3 sin cambio útil de snapshot) → abort.
- `verify_final(state)` determinista (re-lee pantalla). Nunca
  solo-Jev. `DONE` nunca directo.
- Contenido UI hacia S2/Jev etiquetado como `data`, nunca
  instrucción; PII enmascarada en host.
- CostTracker en **todas** las llamadas LLM incluido el paso 0
  (`tier:s2, step:0`) con `[COST]` + forense (§8).

## 7. Seguridad genérica (sin cambio v3, el fast-path no la toca)

### 7.1 Validaciones estructurales — siempre, sin excepción

Antes de cada mutación (fast-path incluido): coordenadas dentro de
pantalla, nodo presente y `visible` en el snapshot vigente, JSON de
decisión válido contra el enum, `snapshot_id` fresco, comando S2 /
plan válido (`package` con forma, `TYPE`/slot con texto no vacío).
Fallo → abort/escalate honesto (`SELECTOR_NOT_FOUND`,
`STALE_SNAPSHOT`, `JEV_HALLUCINATION`, `S2_BAD_COMMAND`).
Taps: `ACTION_CLICK` primero si `clickable`, `dispatchGesture` como
fallback; siempre verificar y reportar `via`. Type: `ACTION_SET_TEXT`
con payload del plan.

### 7.2 Acciones críticas/irreversibles — confirmación explícita

Categorías genéricas (no exhaustivo; el operador puede ampliar por
goal): **enviar/comunicar a terceros, comprar/pagar, borrar/eliminar
datos, cambios de cuenta/seguridad/permisos, `shell`/adb**. Régimen
v3 intacto: el loop las marca `is_sensitive`; sin `confirm:true` se
**planean sin ejecutar** (`planned:true` + `preview` con
acción/target/hash + `needs_confirm:true`, `verified:false`); con
`confirm:true` → ejecución + verificación + auditoría. `shell`/adb
gateados por scope `shell` + grant activo y hasta Fase 6 el
dispatcher responde `METHOD_NOT_ALLOWED`.

### 7.3 FORBIDDEN opt-in por goal (nunca global)

Sin blacklist global en core. `is_forbidden(cand, pattern)` exige
`pattern` explícito del operador (`forbidden?: str`). Sin `pattern`
→ sin filtro. El fast-path evalúa `FORBIDDEN` igual que la vía
lenta.

## 8. CostTracker (sin cambio v3)

`track(model, in/out tokens) → USD`, log `[COST]`, `cost` por paso +
acumulado `jev_cost/s2_cost/total_cost` en el resultado. Tarifas:
**Jev `$0.042` in / `$0.00` out por MTok** (normativo); **GLM-5.3 con
tasa configurable vía env** (`GLM_RATE_IN`/`GLM_RATE_OUT`, default
documentado como placeholder ajustable, nunca hardcodeado como
verdad oficial); overrides análogos `JEV_RATE_IN`/`JEV_RATE_OUT`.
El paso 0 compilador también pasa por CostTracker (`tier:s2`,
`step:0`). Sin key (stub) → `usd=0.0, mock=true`.

## 9. Suite de estrés (solo definición, no ejecutar — normativo v4)

**Ninguna prueba de esta sección se ejecuta al implementar ni al
certificar salvo indicación explícita del operador.** Son definiciones
para correr en el futuro contra dispositivo real, con criterios de
pasa/no-pasa deterministas. El contrato nombra mecanismos genéricos;
las instanciaciones con apps concretas son **ejemplos no-normativos**
(Apéndice A) y nunca condicionan el pasa/no-pasa del mecanismo.

Harness genérico (todas): `run_goal(goal)` con `max_steps` y
`timeout_s` por prueba + forense JSONL; métrica base **ms/acción =
`duration_ms / steps_efectivos`** (pasos con mutación `ok:true`)
reportada desde el forense; `@judge` la verifica en el log, nunca a
ojo.

| ID | Mecanismo bajo prueba (normativo) | Procedimiento | Pasa / No-pasa |
|----|-----------------------------------|---------------|----------------|
| S1 | Scroll profundo en lista larga del sistema | `run_goal` con goal de "alcanzar el elemento al final de una lista larga del sistema" (instanciación concreta: ver Apéndice A); `max_steps ≥ 30`; el loop debe avanzar por `SCROLL_*` + re-dump sin `STUCK_SAME` | Pasa: alcanza el elemento o lo declara `SELECTOR_NOT_FOUND` tras barrido completo sin alucinar targets ni `STUCK_SAME` prematuro; `STALE×3→UI_UNSTABLE` si aplica. No-pasa: `JEV_HALLUCINATION`, `STUCK_SAME` con pantalla aún avanzando, o actuación sobre nodo fuera de tabla |
| S2 | Diálogo modal de permiso del sistema (`needs_system_2`) | `run_goal` ante un modal de permiso del sistema; se espera `needs_system_2=true` o `ESCALATE` y escalado S2 puntual (anomalía), nunca tapeo ciego del modal | Pasa: el modal se trata como anomalía (escalado + `guidance` o `BACK` S2) o como crítica con `planned`+`needs_confirm` si concede permisos; forense con `escalated:true`. No-pasa: `TAP` sobre el modal con `conf < TAU`, o concesión de permiso sin `confirm:true` |
| S3 | Documento denso en motor web (`WebView`) masivo | `run_goal` con goal de "localizar un control al fondo de un documento web denso y largo" (instanciación concreta: ver Apéndice A); tabla >254 candidatos → poda + `SCROLL_*` + re-dump | Pasa: poda determinista 254+NONE estable por snapshot, `zone` presente en cada fila, avance por scroll sin `NO_TARGET` espurio ni reducción silenciosa a 20. No-pasa: tabla >254 enviada a Jev, `zone` ausente, o `target` fuera de tabla |
| S4 | Formulario multi-input con redacción S2 pre-cargada | `run_goal` con goal que exige ≥2 campos de texto (instanciación concreta: ver Apéndice A); el plan `EXECUTE_GOAL` precarga ≥2 slots; el loop los inyecta en sendos `TYPE` **sin reconsultar** a S2 entre ellos | Pasa: los N `TYPE` consumen los N slots (`consumed:true` en forense, solo `len/sha256`), cada uno con foco explícito + read-back `confirm_input ok:true`, cero consultas S2 entre `TYPE`s del camino feliz. No-pasa: reconsulta por texto entre campos, `TYPE` sin foco, o texto crudo en forense/log |
| B1 | Benchmark de latencia por acción | Cualquiera de S1–S4 (típicamente S4 por ser multi-paso corto) corrida en dispositivo reporta `duration_ms`, `steps_efectivos`, `ms/acción`; S1/S2 llamadas y `total_cost` desde forense | Pasa: números reportados en el log + forense completo (`conf/tau/fast_path/coalesced/cost` por paso). Sin umbral normativo de ms en v4 (el umbral se fija tras la primera corrida medida). No-pasa: corrida sin `ms/acción` o sin forense por paso |

### 9.5 Experimento pendiente (no-normativo, no implementar)

`EXPERIMENT-TABLE-20`: medir si podar a 20 candidatos baja
ms/acción sin perder cobertura. Protocolo futuro (A/B en S3):
cobertura (tasa de goal alcanzado), `ms/acción`, tasa `NO_TARGET` /
`ESCALATE` espurios. Hasta entonces, `MAX_TABLE = 254` intacto.

## 10. Aceptación verificable (`@judge`, sin editar)

Desde `mcp-server/`:

1. `uv run pytest` **verde** (tests reescritos por `@coder`: plan
   `EXECUTE_GOAL` paso 0 con `preloaded_inputs` + inyección sin
   reconsulta, fast-path + coalescido con un solo dump por paso,
   tabla `[idx,class_short,zone,flags,label]` con `zone` 3×3 en
   inglés, payload S1 100% inglés con `screen_goal_en`, comandos de
   anomalía intactos, CostTracker con env overrides, compuertas
   genéricas).
2. `grep -rniE` de literales de dominio en `src/` → **vacío**. Patrón
   de referencia heredado v3 (ajustar sin estrecharlo, y extender al
   vocabulario del Apéndice A sin copiar sus valores a esta sección):
   `whatsapp|com\.whatsapp|contact_name|verify_chat|wrong_chat|reenviar|forward|dry-run-de-chats|fase5_check|send_whatsapp`
   más cualquier término del Apéndice A que `@coder` tocara. Solo
   `docs/` e historia git pueden nombrarlos. Los paquetes en tests
   viajan como valores runtime aportados por el stub S2, nunca como
   literales en `src/`.
3. Cost log: corrida `run_goal` con stub o modelos reales produce
   `logs/run-<ts>.jsonl` con `cost` por paso (incluido paso 0 S2) +
   líneas `[COST]` y acumulado `total_cost` en el resultado.
4. Compuertas: estructural siempre; crítica sin `confirm:true` →
   `planned` sin tocar dispositivo; `conf < 0.70` → escalado sin
   tapear; `STALE×3` → `UI_UNSTABLE`; `DONE` siempre con gate S2
   (fast-path jamás cierra un goal).
5. Bootstrap compilador en test: stub S2 emite `EXECUTE_GOAL` con
   `package` runtime + `preloaded_inputs` + `screen_goal_en` +
   `expected_terminal_state`; el loop despacha `mcp.open_app(package)`
   + ~600 ms + re-observe antes del primer S1, y los `TYPE`
   posteriores consumen los slots sin nueva llamada S2 (mock de
   `open_app` + conteo de llamadas S2 lo verifica).
6. Payload S1 en inglés: el test captura `state`/`questions` y aserta
   cero instrucciones en español + tabla con forma
   `[idx, class_short, zone, flags, label]` + cabecera con
   `current_app` y `screen_goal_en`.
7. Fast-path en test: decisión `conf ≥ 0.85` trivial + mock de
   `observe`/`execute` verifica un solo dump de verify-reusado
   (`coalesced:true`, `pending_state` consumido en el paso
   siguiente) y que `STALE`/foco/`confirm`/`STUCK` siguen evaluados.
8. Benchmark **solo si se corre en dispositivo** (no bloquea el
   verde sin dispositivo): corrida B1 reporta `ms/acción` en log +
   forense; `@judge` lo adjunta, no lo inventa. Sin dispositivo, la
   suite §9 se certifica como "definida, no ejecutada".

## 11. Alcance para `@coder` (no improvisar arquitectura)

- `s2_client`: parsear + validar `EXECUTE_GOAL` (§2.1) con misma
  `OPENROUTER_API_KEY` (y proveedor alterno existente); mantener
  comandos de anomalía v3; `verify_done` acepta
  `expected_terminal_state` como contexto; forense/log solo
  `len/sha256` por slot; `S2_BAD_COMMAND` / `S2EmptyResponse` /
  stub-`mock` con la semántica actual (nunca ciclar ni tapear).
- `loop.run_goal`: paso 0 compilador (§2.2) + `pending_payloads` con
  inyección §2.3 (orden de inserción, `consumed`, sin reconsulta en
  camino feliz); fast-path `FAST_TAU = 0.85` + post-read coalescido
  (§3, `pending_state` desde el verify); `open_app` solo en
  bootstrap; `TYPE` con `ACTION_SET_TEXT` + foco explícito +
  read-back; forense con `fast_path/coalesced/slot+hash/cost` +
  `screen_goal_en/expected_terminal_state` (hash si sensible).
- `core/loop_helpers`: fila con `zone` (`zone_of(bounds, w, h)` pura,
  §4) + `serialize_table` de 5 columnas; `MAX_TABLE = 254` intacto;
  `check_decision_json` / `validate_target` / `is_sensitive` sin
  cambio salvo exponer lo que el fast-path necesita.
- `jev_client.ask_decision`: `state` + `questions` 100% inglés (§5)
  con tabla de 5 columnas + `current_app` + `screen_goal_en`;
  `id`/`bounds` fuera del payload (quedan en `by_idx`).
- Sin nuevas dependencias (AGENTS.md §4); sin `su`; sin `shell`
  (Fase 6, `METHOD_NOT_ALLOWED`); transporte y binds/token sin cambio.
- Tests + scripts contra este contrato (reusar patrón stub-S2 +
  mock-`open_app`; literales de app solo como valores runtime en
  tests, nunca en `src/`).

## 12. Divergencias documentadas (operador → v4, y v3 → v4)

1. **S2-compilador vs comandos por paso.** El operador pide S2 que
   "no vuelve hasta terminal o anomalía" con todo precargado. v4 lo
   adopta para el camino feliz (§2) pero **conserva** los comandos
   v3 (`OPEN_APP/TYPE/BACK/HINT`) como vía de anomalía: eliminarlos
   dejaría al loop sin desatasco ante `LOW_CONF`/`NO_TARGET`/pantalla
   sin candidato/app equivocada, y rompería código ya verificado.
   La reconsulta por texto sobrevive solo como fallback de anomalía
   (§2.3.2, tercer guion). Sin violación AGENTS.md: sigue una
   primitiva por paso, sin `run_sequence`.
2. **Inyección multi-slot.** El operador ("el loop los inyecta cuando
   S1 decide TYPE sobre el campo correspondiente") no define cómo se
   corresponde campo↔slot sin literales. v4 fija regla determinista
   genérica (slot único → ese; varios → orden de inserción S2 +
   read-back como detector de desalineación, §2.3.2). Alternativa
   descartada: `target_hint` por slot con matching de labels — más
   expresiva pero introduce acoplado de contenido al contrato; queda
   como extensión futura si S4 la exige con datos medidos.
3. **Fast-path sin post-read.** El operador pide "sin post-read
   redundante: el dump de verificación SE REUSA". v4 lo adopta como
   **coalescido oportunista** (§3.2), no como eliminación del
   verify: si la lectura de verificación no trae tabla completa, se
   completa con `dump_ui`. Eliminar el verify violaría AGENTS.md §6
   ("siempre verificar + `via`" en taps, foco en type). El ahorro es
   un dump por paso, nunca la verificación.
4. **`zone` normalizada a 3×3.** El operador mezcla `top-bar /
   mid-list / bottom-nav / bottom-right / ...` (nombres de layout,
   no celdas 3×3 puras). v4 norma 9 celdas por tercios (§4) e
   interpreta `top-bar ≈ top-center`, `bottom-nav ≈ bottom-center`
   como alias informales: los nombres de layout dependen de la app
   y no son computables solo con bounds+resolución.
5. **Podador "agresivo = 20" rechazado.** Proviene de otro repo sin
   medición aquí; v4 mantiene 254+NONE y deja `EXPERIMENT-TABLE-20`
   (§9.5). Reducirlo a ciegas violaría la invariante de cobertura v3
   y la filosofía "evidencia antes que síntesis".
6. **Todo-inglés reafirmado.** Ya norma v3; v4 solo añade que
   `screen_goal_en` y `guidance_for_s1` llegan en inglés desde el
   plan S2 (§5). Sin cambio AGENTS.md.
7. **Estrés y aceptación.** La suite §9 es solo-definición (el
   operador lo exige así); B1 no fija umbral de ms (sin primera
   medición no hay número honesto). La aceptación §10 añade el
   `grep` de los ejemplos del Apéndice A para que el "cero
   literales" cubra también los nuevos ejemplos no-normativos.

## Apéndice A — ejemplos no-normativos (informativos, nunca contrato)

> Todo este apéndice es **ejemplo**. Ningún valor aquí es default,
> constante, regex o criterio. Si un test necesita un paquete, el
> stub S2 lo aporta como valor runtime.

- Mensajería (p.ej. app de mensajería instalada; valores de test
  tipo `com.whatsapp` / contacto "Rupa"/"Felix" solo como datos del
  stub): `EXECUTE_GOAL{screen_goal_en: "Message thread open, input
  focused", preloaded_inputs: {"message": "<text>"}}`.
- Video (p.ej. app de video; valor de test tipo paquete de YouTube
  solo como dato del stub): `preloaded_inputs: {"query": "<text>"}`.
- Cálculo/benchmark (p.ej. app de calculadora; expresión ejemplo
  `1540/4` solo dato de prueba): dos slots
  `{"operand_a": "1540", "operation": "/4..."}` o un slot único
  según compile S2; B1 mide `ms/acción` sobre esta corrida corta.
- Sistema (lista de ajustes del sistema, modal de permiso, página
  larga en navegador con `WebView`): instanciaciones de S1/S2/S3.
