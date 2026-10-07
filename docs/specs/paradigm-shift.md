# paradigm-shift — los 3 giros de visión (2026-10-06)

> Estado: **nota `@architect` 2026-10-07, solo `docs/`**. No es contrato
> ejecutable: el contrato vigente sigue en `generic-dual-tier.md` (v3 + §12),
> `plan-ahead.md` (v4), `director-client.md` (v5) y `applied-refs.md` (P0/P1/P2).
> En conflicto, **AGENTS.md manda**. Cero literales normativos de app en este
> documento: los valores concretos de apps/personas que aparecen son
> **ejemplos no-normativos** (valores runtime aportados por el operador/S2,
> nunca defaults del repo). Sin keys ni secretos. Todos los payloads de
> ejemplo van **100% en inglés** por norma (calibración S1).

## 0. Por qué existe este documento

Tres mensajes de visión del operador (2026-10-06) reordenaron el proyecto en
48 h. Cada giro venía con autopsia medida y orden de trabajo; `@architect` los
convirtió en specs sin tocar código. Este archivo los fija en una página: qué
giro, qué rompió, qué quedó, qué falta. Trazabilidad: commits `a21d30e` →
`5c0f014` → `265ec25` → `d02cbe1` → `58db72b` → `6fc3a9a` + working tree v5.

## 1. Giro (a) — S2-director / S1-reflejo + Jev en inglés (v3, `a21d30e`)

**Fecha:** 2026-10-06 (visión) / implementado 2026-10-05.
**Spec:** `generic-dual-tier.md` v3 + `applied-refs.md` P0.

Antes, S1 y S2 discutían el plan a cada paso: S1 recibía instrucciones en
español, tabla pobre (`idx/id/label` sin flags), y el escalado S2 devolvía un
`hint` decorativo que nadie ejecutaba. El bootstrap adivinaba paquetes en el
loop.

Después:

- **S2-director, S1-reflejo** (v3 §2). S2 resuelve el paquete destino por
  conocimiento general en runtime y emite **comandos macro ejecutables**
  `OPEN_APP | TYPE | BACK | HINT` (§5.1–§5.2). S1 solo resuelve índices
  `0..253 + NONE` en ms, sin semántica inter-app.
- **Jev 100% inglés** (v3 §3). `state` + `questions` íntegramente en inglés
  (la calibración RLCD se entrenó en inglés; el español degrada `tau`).
  Preguntas en español en `jev_client.py` = bug contra contrato.
- **Tabla enriquecida** (v3 §4). Fila `[idx, class_short, flags, label]`
  con `flags = click|edit|foc|scroll`; `id`/`bounds` opacos quedan en `by_idx`
  del host para validación + ejecución (S1 nunca ve coordenadas).
- **Directivas S2 ejecutables + OPEN_APP bootstrap** (v3 §5.3). El loop hace
  `observe` → S2 → (`open_app(package)` + ~600 ms + re-`observe` fresco) →
  recién entonces S1. Sin dump fresco no hay S1 (`STALE_SNAPSHOT`). Sin key
  S2 en bootstrap → `S2_UNAVAILABLE` inmediato (nunca ciclar ni adivinar).
- **Refs clonados en `refs/` (ignorado).** `refs/android-jev` (FZ2000,
  adb+Jev) + `refs/mobile-jev` (droidrun, cloud+Jev), ignorados por
  `.gitignore`, nunca commiteados. Lo robado es **patrón**, no
  implementación (prohibido copiar `adb shell input text|clipboard|
  uiautomator`, endpoints, modelos o keys ajenas):

| Patrón robado | Origen | Cae en |
|---|---|---|
| `focused.holds` (campo + contenido distingue escrito-no-enviado de enviado) | A2 | P0-1: `FocusedField{label,kind,holds}` en state S1 |
| `type-replace` + read-back (`input_unverified` sin retype ciego) | A3+M2 | P0-2: `ACTION_SET_TEXT` + `confirm_input` |
| `validateChoice` estricta + consumir solo la rama elegida | M1 | P0-3: distribución completa, `sum≈1 ±0.025`, argmax, `conf` finita |
| anti-giro por **firma de pantalla por contenido** (ignora tickers) | A4 | P1-5: `screen_fingerprint`, historial acotado a 8 |
| `assertFresh` + fingerprint before/after (mutación incierta nunca se reintenta) | M3 | P1-6 |
| forense **wire íntegro + timings por fase** + log-antes-de-observar | A5+M5 | P1-7: `logs/run-<ts>.jsonl` con `wire` + `timings{reading,deciding,acting,watching}` |
| tolerancia S2-vacío degradada ×1 (endurece `S2EmptyResponse`, sin origen en refs) | — | P0-4: 1 re-pregunta S1 conservadora, techo `STUCK_SAME×3` |

Forma del payload S1 v3 (solo forma, contenido ilustrativo en inglés):

```json
{
  "model": "typesafe/jev-1.13",
  "state": {
    "goal": "Send a short message to a contact",
    "screen_goal": "Message thread open, message input focused",
    "current_app": "dev.jev.jam",
    "snapshot_id": 42,
    "table": [[0, "EditText", "edit|foc", "Message"], [1, "Button", "click", "Send"]],
    "history": "tap_node:n_7; tap_node:n_3",
    "s2_guidance": "Thread is open. Tap the message input, then type the S2 text."
  },
  "questions": {
    "action": {"type": "choice", "instructions": "Pick ONE primitive to advance the goal."},
    "target": {"type": "choice", "instructions": "Target table row index. NONE if no useful candidate."},
    "needs_system_2": {"type": "noul", "instructions": "Does this step require open-text composition?"}
  }
}
```

## 2. Giro (b) — plan-ahead v4: S2-compilador paso 0 (v4, `265ec25`)

**Fecha:** 2026-10-06 (visión). **Spec:** `plan-ahead.md` v4.
Refinamiento compatible de v3 (sin enmienda AGENTS.md).

- **S2-compilador paso 0: `EXECUTE_GOAL` + `preloaded_inputs`** (v4 §2).
  Una sola consulta S2 al inicio devuelve plan-dato (no secuencia ejecutable):
  `{package, screen_goal_en, preloaded_inputs{slot: exact payload},
  expected_terminal_state, guidance_for_s1, stop}`. El camino feliz **no
  reconsulta a S2 para redactar**: cuando S1 decide `TYPE`, el loop inyecta
  el slot (único → ese; varios → orden de inserción S2 + read-back como
  detector) vía `ACTION_SET_TEXT`. `open_app` solo en bootstrap.
- **Fast-path `FAST_TAU = 0.85`** (v4 §3.1). `conf ≥ 0.85` + trivial +
  no-sensible → despacha sin consultas secundarias. **Nunca salta
  compuertas**: estructural, foco, `confirm:true`, `FORBIDDEN` opt-in,
  `STALE×3 → UI_UNSTABLE`, `DONE`-gate siguen evaluados.
- **Post-read coalescido** (v4 §3.2). Un solo dump por paso: el `verify`
  válido se reutiliza como `observe` siguiente (`{fast_path, coalesced,
  snapshot_before/after}` en forense). Oportunista, nunca a ciegas.
- **Zonas 3×3** (v4 §4). Columna `zone` calculada en host desde centroide +
  resolución (`top-left | top-center | … | bottom-right`, fallback `unknown`).
  Hint de desambiguación, nunca señal de seguridad. Fila v4:
  `[idx, class_short, zone, flags, label]`. `MAX_TABLE = 254` intacto
  (podador "agresivo = 20" de otro repo **rechazado sin medir**,
  `EXPERIMENT-TABLE-20` pendiente).
- **Suite de estrés definida, no ejecutada** (v4 §9): S1 scroll profundo, S2
  modal de permiso, S3 documento denso `WebView`, S4 formulario multi-input,
  B1 benchmark `ms/acción`. Solo-definición por orden del operador.
- **Benchmark calculadora bloqueado por entorno.** `logs/run-20261006-204449-calc.jsonl`
  (`summary_b_redo`): `ok_all: false`, `avg_tap_ms: 69.7`, `avg_s1_ms: 1589.5`;
  el display final no confirma el resultado esperado → medido pero no
  certificable como B1 (falla la app/entorno, no el mecanismo).

## 3. Giro (c) — director-cliente v5: muerte de la Inception (v5 + §12)

**Fecha:** 2026-10-06 (visión). **Specs:** `generic-dual-tier.md` §12
(2026-10-06) + `director-client.md` v5 (working tree, sin commit).

Autopsia §12 (7 runs): ante `conf < TAU` en pantallas densas, S1 dudaba → S2
devolvía `HINT` decorativo → S1 redudaba → giro sin mutación hasta
`STUCK`/`TIMEOUT`. Más el poisoning por goal global (el nombre propio y la
app destino sesgaban al resolver dentro de la app-origen) y "dedos antes que
APIs". Veredicto: **enterrar la Inception**
`OpenCode → loop.py → S2 → Jev → Jam` (tres planificadores sobre el mismo
goal) para metas complejas.

- **Muerte de la Inception, `loop.py` congelado** (v5 §6). `run_goal` queda
  congelado post-v4+§12 como modo legacy del caso simple (no recibe features;
  solo bugfixes de seguridad/regresión). Todo lo nuevo vive fuera, sin
  importarlo. `@judge` certifica con pytest verde **antes y después**.
- **Jev-resolver ciego al goal** (v5 §3). Vía nueva `resolve_element(
  screen_goal, table, snapshot_id)` con **1 sola pregunta Choice** sobre
  índices + `NONE`, micro-intención EN de **la pantalla actual**
  (p. ej. `"Tap the Copy link row"`), tabla con `zone`, `first_result` como
  hint. El goal global, nombres propios y paquetes **no existen en su
  `state`** (anti-poisoning auditable en test). La ACCIÓN la decide el
  director; Jev solo señala `{idx, conf}`.
- **Anti-entropía sin podar-a-1** (§12.2). Podar la tabla a 1 resultado
  **prohibido** (frágil: anuncios, reordenamientos). En su lugar hint
  `first_result` (primer interactivo del contenedor principal) como prior,
  y ante escalado en lista densa **S2 elige índice vía `TAP`-direct**
  (§12.1, `OPEN_APP | TYPE | TAP | BACK | HINT`) en vez de consejo.
- **Clipboard get/set por API** (v5 §4.1 + §12.4). Distinción vinculante:
  `shell` on-device = OFF hasta Fase 6 (`METHOD_NOT_ALLOWED`); adb-host =
  harness permitido. `get_clipboard` = host `adb shell dumpsys clipboard` +
  verificación por forma `https?://` → `CLIPBOARD_EMPTY` honesto;
  `set_clipboard` = método Jam `ClipboardManager.setPrimaryClip` (scope
  `ui`, sin Shizuku, sin grant) + read-back de forma. Prohibido `adb shell
  input text`, `service call clipboard` frágil, `shell` on-device. Sin método
  Jam → `CLIPBOARD_UNSUPPORTED(jam-api-missing)` y el director usa
  `type_text` directo (degradación, no emulación).
- **Yo-dirijo paso a paso estilo curl.** El director (operador) ve cada
  pantalla (`read_screen_state` + screenshot evidencial), resuelve
  (`resolve_element`), muta una primitiva (`tap_idx`/`type_text`/`open_app`),
  verifica (`read` posterior), audita forense con `decided_by: director`.
  Fail-fast entre corridas (§12.3): 2 muertes con igual `run_signature`
  → no relanzar; dif de forenses + informe.
- **Casos verificados por dos vías** (commits `58db72b`, `6fc3a9a` + forense):
  caso mensajería simple ~84.9 s y caso similar ~22 s con `S2_PROVIDER=
  deepseek` (~1.9 s/llamada S2) frente a flash (~22 s/llamada), cada uno con
  forense JSONL + verificación de pantalla posterior (no solo log local).
  Valores concretos de personas/apps solo en runtime/forense, nunca en `src/`.

Contrato del resolver v5 (forma, inglés):

```json
{
  "state": {
    "screen_goal": "Tap the Copy link row",
    "current_app": "foreground package (runtime value)",
    "snapshot_id": 41,
    "first_result": 7,
    "table": [[7, "TextView", "mid-center", "click", "Copy link"]]
  },
  "questions": {
    "target": {"type": "choice", "instructions": "Pick the table row matching the screen goal. NONE if no useful candidate."}
  }
}
```

## 4. Tabla antes / después

| Dimensión | Antes (pre-v3, loop monolítico) | Después (v3 → v4 → v5) |
|---|---|---|
| Latencia por paso | `uiautomator` 4353 ms domina; Jev ES sin calibrar | tap ~70 ms; S1 ~1.6 s; S2 DeepSeek ~1.9 s vs flash ~22 s; `dump_ui` ~2 ms/nodo; fast-path ahorra 1 dump/paso |
| Llamadas S2 por corrida | S2 consultado por cada redacción/duda (giro HINT↔S1) | v4: 1 (compilador paso 0) + anomalías; v5-complejo: 0 LLM en loop (director humano) + Jev-resolver por pantalla |
| Rol de Jev | decisor con goal global + instrucciones ES (poisoning, `tau` degradado) | v3–v4: actuador táctico EN (acción+target+conf); v5: resolver ciego (1 Choice, micro-intención, anti-poisoning) |
| Quién abre apps | loop adivinaba / paseo por launcher | S2-director (v3 bootstrap) / S2-compilador (v4 `EXECUTE_GOAL.package`) / director `open_app` (v5); siempre `am start` Shizuku + verificación foreground |
| Quién provee texto | S1 podía inventar | solo S2-director/compilador (`text_payload`/`preloaded_inputs`) o director v5 (clipboard slot); sin texto → escalate, nunca inventar |
| Quién verifica | éxito declarado por quien actuó | `verify_final` determinista + `DONE→S2 verify_done` (v3–v4) / `verify` del director por `read` (v5); `verified=true` solo con lectura posterior |
| Forense | log local sin dueño | `logs/run-<ts>.jsonl` por paso + `wire` + `timings` + `cost [COST]` + `run_signature` fail-fast; `decided_by: director` en v5 |

## 5. Métricas reales (medido, no proyectado)

- **pytest:** 55 (v3 roles) → 80 (P0 applied-refs) → 103 (v4 plan-ahead) →
  105 (STALE-retry + caso 22 s) → **127 (§12 + v5 working tree)**. Todos en
  `mcp-server/`: `uv run pytest -q`.
- **Costos por corrida < $0.003.** Jev `$0.042` in / `$0.00` out por MTok
  (normativo); GLM-5.3 por env `GLM_RATE_IN/OUT` (placeholder ajustable,
  nunca verdad oficial). Ej.: `logs/run-20261006-204303.jsonl` (`end`):
  `jev_cost ≈ 0.00067, s2_cost = 0.0`. Cada llamada loguea `[COST]` +
  campo `cost` por paso.
- **Tap ~70 ms** (`avg_tap_ms: 69.7` calc-redo, `84.6` settings+batería).
  `ACTION_CLICK` primero si `clickable`, gesto fallback, siempre `via`.
- **S1 ~1.6 s** (`avg_s1_ms: 1589.5` calc-redo; pasos individuales
  1318–2158 ms en `logs/run-20261006-*.jsonl`).
- **S2 DeepSeek ~1.9 s vs flash ~22 s** por llamada (medido en las corridas
  de validación 2026-10-05/06; DeepSeek vía `S2_PROVIDER=deepseek`, misma
  key que S1). Flash intermitente con contenido vacío → `S2EmptyResponse`
  → tolerancia degradada ×1 (P0-4), nunca giro.
- **Casos:** mensajería simple ~84.9 s y ~22 s, verificados por dos vías
  (aserción en pantalla + entrada forense). Batería en Ajustes leída
  (`88 %`) y calculadora `1540/4` con taps verificados por display pero
  **resultado final no certificable** (`ok_all: false` en redo) → B1
  bloqueado por entorno, citado como tal.
- **Percepción:** `dump_ui` ~2 ms/nodo (13n/40 ms, 66n/106 ms, 124n/264 ms;
  peor caso ~1 s a 500). 16× mejor que `uiautomator`.

## 7. Apéndice post-redacción (2026-10-06/07, commits `7ee4058` → `9dd7658`)

Lo posterior a la nota `@architect` 2026-10-07, medido (sin proyección):

- **STALE-retry en el bucle** (`58db72b`). Ante `STALE_SNAPSHOT`, el loop
  re-dumpea y reintenta el mismo paso una vez (`stale_retry: true`,
  `stale_attempt: 1/2`, `stale_recovered: true` en forense) en vez de
  abortar. Evidencia: mensajería-B SENT ~22 s con `stale_recovered` ×1
  (`mcp-server/logs/run-1791243623.jsonl`); reloj/alarmas re-taps
  `via=action_click`/`gesture` (`run-clock-alarms-…`).
- **S2-TAP-direct + `first_result`** (`6fc3a9a`, §12.1). Ante escalado en
  lista densa, S2 elige índice vía comando `TAP` ejecutable (no `HINT`
  decorativo); el host expone `first_result` como prior sin podar-a-1.
  `run_signature` + fail-fast entre corridas (§12.3): 2 muertes con igual
  firma → no relanzar.
- **Clipboard por API** (`6fc3a9a` wrapper + `7ee4058` método Jam).
  `set_clipboard` = la propia Jam ejecuta `ClipboardManager.setPrimaryClip`
  (scope `ui`, sin Shizuku, sin grant); lectura por host `dumpsys` +
  read-back de forma. Sin método Jam → `CLIPBOARD_UNSUPPORTED` honesto y
  el director usa `type_text`. Prohibido `shell` on-device (Fase 6),
  `adb shell input text` y `service call clipboard`. Tests
  `test_director_clipboard.py` + `test_director_resolve.py` en verde.
- **Suite Fossify 5/5** (`9dd7658`, `docs/specs/fossify-random.md`).
  Director v5 en A10 USB, solo no-destructivo: gallery 2.3 s ($0),
  clock 5.7 s, files 9.1 s (incl. scroll), calc 15.5 s (guarda de etiqueta
  vs confusión `9`/`×`, doble-snap), music 5.6 s (permiso media aceptado,
  playback omitido). Total ~$0.0006; v1 con fallos honestos conservada.
- **Métricas nuevas.** pytest **139 en verde** (127 en `6fc3a9a` → 139
  tras `7ee4058`). Bancos: KJ5 Wi-Fi (loop) + A10 USB (director).
  Bloqueos honestos: multi-app YT→Brave `verify_download ok: false`
  (`DOWNLOAD_NOT_STARTED`, ~$0.0011) y calculadora stock
  (`summary_b_redo ok_all: false` → B1 sigue bloqueado por entorno).
  Detalle tabular en `docs/TESTING.md` §9.

## 8. Apéndice `bd1f5a4` (2026-10-07: docstrings + `open_url` + ARCHITECTURE)

Posterior a §7, medido (sin proyección). Solo `docs/` + código ya
commiteado; este apéndice lo fija:

- **Docstrings MCP 35/35 al estándar 5-secciones** (`mcp-server/src/
  jev_mcp/server.py` + `tools/*.py`). Secciones: Descripción /
  Parámetros / Retorno / Permisos-Grants / Errores-gotchas; payloads
  ejemplo 100% en inglés. Sin cambio de comportamiento, solo contrato
  legible por el director/S2.
- **`open_url(url, package="")` con componente explícito** (PROTOCOL §4
  + `docs/BUILD.md` §9). Sin `package` = resolución del sistema
  (chooser `ResolverActivity` si >1 handler, verificado en
  `logs/run-intent-20261007-130650.jsonl`); con `package` se valida
  forma, se fija componente y es **1 salto sin chooser**
  (`via: startActivity-package`, ~130 ms en A10 USB). No instalado →
  `PACKAGE_NOT_FOUND`; instalado sin handler → `INTENT_UNRESOLVED`;
  fallback Shizuku `am start -n pkg/activity`. Test de forwarding MCP
  en verde.
- **pytest 139 → 148 en verde** (`cd mcp-server && uv run pytest -q`;
  147 en `docs/BUILD.md` §8 + 1 test `package`). JVM
  `NatPoliciesTest` 13 tests OK (incl. forma válida de `package`
  forzado). Grep cero-acoplado en `mcp-server/src/` vacío.
- **ARCHITECTURE sincronizado a v4/v5/nativo** (era 2026-10-04):
  dual-tier v3 + plan-ahead v4 (`FAST_TAU`, `zone` 3×3) +
  director-client v5 (`loop.py` congelado) + carril nativo N0/N1
  (`METHOD_NOT_ALLOWED` en N2 hasta Fase 6); escala física en gestos
  (lógico vs píxeles, factor 2.0 medido); 35 tools = 6 primitivas Jev +
  29 director/nativo/diagnóstico.
- **Contratos ratificados (sin cambio):** `hello` request = objeto
  `WsRequest{id, method, params}` con `protocol_version` +
  `client_version`, respuesta plana `{ok, protocol_version,
  app_version, scopes}`; app = `dev.jev.jam` (Jam); `dump_ui` sin
  campo `secure` (`SECURE_SURFACE` solo en `screenshot`).
- **Deuda honesta nueva:** token bearer en claro en logcat
  (`JevForegroundService.kt:33` `JamWs token=$token`); enmascarar
  (`<redacted>`) + rotar antes de release. Backlog 2b intacto (WSS +
  cert self-signed + Keystore).

## 6. Lo pendiente (no se finge cerrado)

1. **Ranking por relevancia** (P2-8). S1 a primera vista duda (conf ~0.45
   con 64 candidatos). Experimento: rank `text_match` sobre
   `label+flags` (editables con `holds` vacío primero) antes de podar a
   254. Solo con protocolo ≥20 goals ×3 corridas; sin número mágico.
2. **Firma anti-ticker** (P1-5). `screen_fingerprint` por contenido que
   ignore hora/batería/notificaciones; `STUCK_SAME` sobre firma, no sobre
   `snapshot_id`. Pendiente de implementación por `@coder`.
3. **Timings por fase** (P1-7). `timings{reading,deciding,acting,watching}`
   por step + `wire` íntegro + log-antes-de-observar en cada entrada JSONL.
4. **Recalibrar `tau`** (P2-8). `TAU = 0.70` y `FAST_TAU = 0.85` son
   constantes hasta medir P10-step-1 vs tasa de éxito; si procede,
   `tau_step1` menor o `HINT`-sin-mutación en step 1, con enmienda e
   intervalos.
5. **Suite A10 formal.** Método Jam + wrapper host con read-back
  comprometidos (`7ee4058`); certificar con suite A10 formal
  (batería + calculadora + clipboard round-trip) en banco USB antes de
  dar v5 por cerrada. Enmienda AGENTS.md §1 propuesta en
  `director-client.md` §11.4 (director decide / Jev señala / Jam ejecuta)
  pendiente del orquestador.
