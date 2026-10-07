# director-client v5 — el director es el cliente, Jev señala, el SO hace el resto

> Estado: **contrato v5 2026-10-07 (redacta `@architect`, solo `docs/`)**.
> Implementa `@coder`, certifica `@judge`. En conflicto, **AGENTS.md manda**.
>
> v5 **entierra la "Inception de Agentes"** (OpenCode → `loop.py` → S2/DeepSeek →
> Jev → Jam) y la sustituye por **director-cliente**: el director
> (OpenCode/operador) es el único planificador; Jev es resolver de elementos;
> el SO (intents/APIs/clipboard) está por encima de los dedos.
>
> v5 es refinamiento operativo de `generic-dual-tier.md` v3 + addendum §12 +
> `plan-ahead.md` v4 para **metas complejas/multi-app**. **No rompe lo que ya
> funciona**: el SENT simple bajo `loop.run_goal` sigue soportado con el loop
> **congelado** (§6). Cero literales de app en lo normativo de `src/`; los
> ejemplos con apps/personas en este doc son **no-normativos** (valores
> runtime aportados por el operador/S2, nunca defaults del repo).
>
> **Nota de trazabilidad AGENTS.md:** v5 invierte la máxima "Jev decide, no
> ejecuta" (AGENTS.md §1) en **"el director decide, Jev señala, Jam ejecuta"**
> para metas complejas. Esto **requerirá enmienda de AGENTS.md §1 en la
> próxima revisión** (propuesta en §11.4). Hasta entonces: el loop congelado
> (§6) sigue bajo la regla vieja; todo lo nuevo bajo v5 cita esta sección
> como divergencia documentada, no como enmienda silenciosa.

## 0. Estado actual leído (base factual, no propuesta)

Leído antes de redactar (working tree 2026-10-07):

- `mcp-server/src/jev_mcp/loop.py:1-44` — `run_goal(goal: str)` autónomo:
  bootstrap-compilador paso 0 (`s2_client.compile_goal` → `EXECUTE_GOAL` con
  `package/screen_goal_en/preloaded_inputs/expected_terminal_state`) → ciclo
  `observe→S1→mutate→verify(coalescido)`, un paso = una primitiva. S1 decide
  `[TAP,TYPE,SCROLL_DOWN,SCROLL_UP,BACK,DONE,ESCALATE] + target 0..253|NONE +
  needs_system_2 + conf`; fast-path `FAST_TAU=0.85`, `TAU=0.70`; `STALE×3 →
  UI_UNSTABLE`; `DONE`-gate S2; forense JSONL + `CostTracker`.
- `mcp-server/src/jev_mcp/jev_client.py:207-328` — `ask_decision(goal, table,
  snapshot_id, ...)` single-pass: lleva el **goal global** en
  `state.goal + screen_goal` + tabla `[idx,class_short,zone,flags,label]` +
  `current_app/focused_field/history/s2_guidance`; 3 preguntas cerradas
  (`action/target/needs_system_2`). Sin key → stub `{mock:true}`.
- `mcp-server/src/jev_mcp/s2_client.py:1-66` — S2 solo vía OpenRouter
  (misma `OPENROUTER_API_KEY` que S1, modelo por env `S2_MODEL`);
  comandos `OPEN_APP|TYPE|TAP|BACK|HINT` + plan `EXECUTE_GOAL` + `verify_done`;
  `S2EmptyResponse/S2BadCommand` honestos.
- `mcp-server/src/jev_mcp/tools/ui.py` — primitivas reales: `read_screen`
  (`dump_ui` + normalizer + `candidates/snapshot_id/first_result/zone/
  focused_field`), `tap_node` (`tap_node` Jam, hint "verifica con
  read_screen"), `type_text` (REPLACE vía `ACTION_SET_TEXT`, sin re-observe
  dentro), `tap_text` (legado, preferir `tap_node`), `scroll/press_back/
  press_home/wait_for_text/screenshot`. `screen_height/width` vía
  `adb shell wm size` cacheado (diagnóstico host, no acción).
- `mcp-server/src/jev_mcp/tools/app.py` — `open_app(package)` (Shizuku
  `am start` + `get_foreground` de verificación) y `close_app` (`force_stop`
  + verificación). Tal cual AGENTS.md §5.5.
- `mcp-server/src/jev_mcp/tools/clipboard.py:1-120` — **solo-lectura**:
  `read_clipboard()` en **host adb** (`adb shell dumpsys clipboard` +
  `parse_dumpsys_clipboard` + verificación por forma `https?://` →
  `CLIPBOARD_EMPTY` honesto), fallback `paste-readback` inyectable, slot
  opaco `clipboard {text,len,sha256,consumed}`. Docstring explícito: "nunca
  shell en el dispositivo". **No existe `set_clipboard`.**
- `mcp-server/src/jev_mcp/tools/_base.py` — `jam_client()` con auto-forward
  `adb forward tcp:38472`, envolvente `{ok,verified,evidence,hint}`.

## 1. Autopsia: por qué se entierra la Inception

La cadena OpenCode → `loop.py` → S2 (OpenRouter) → Jev → Jam apila **tres
planificadores** (operador + S2-compilador/director + S1-decisor) sobre el
mismo goal global. Fallos medidos que la condenan:

1. **Poisoning por goal global.** `ask_decision` recibe el goal completo
   ("…a Luis por WhatsApp…") **en cada pantalla**, también dentro de YouTube.
   El nombre propio y la app destino sesgan el resolver hacia nodos que los
   mencionan (comentarios, sugerencias, historial) en vez del control de la
   pantalla actual (compartir, copiar, buscar). El defecto no es de `tau`:
   es de **alcance del contexto**.
2. **Parálisis por indecisión** (`generic-dual-tier.md` §12, autopsia 7 runs):
   S1 duda → S2 devuelve `HINT` decorativo → S1 vuelve a dudar → giro sin
   mutación. El parche `TAP`-direct (§12.1) alivia el giro pero mantiene dos
   cerebros discutiendo el plan.
3. **Dedos antes que APIs.** El flujo "compartir → copiar → leer clipboard →
   inyectar" (§12.4) ya demostró que la vía robusta es el **SO**, no navegar
   menús frágiles de share con taps. Pero el loop autónomo no tiene juicio
   inter-app para preferirla: solo ejecuta el comando que le toca.
4. **Forense sin dueño.** Con tres decisores, `logs/run-<ts>.jsonl` registra
   `conf/tau/s2_command` pero la pregunta "¿quién decidió el plan?" no tiene
   respuesta única auditable.

**Veredicto:** para metas complejas/multi-app, el loop deja de ser agente
autónomo con LLM embebido. Un solo planificador con contexto completo (el
director-cliente) + un resolver ciego al goal (Jev) + herramientas atómicas
honestas. El loop autónomo se **congela** (§6), no se extiende.

## 2. Visión: el director es el cliente

```
director (OpenCode/operador, único que razona con contexto completo)
  │  ve cada pantalla (read_screen_state + screenshot evidencial)
  │  decide el plan paso a paso (abrir, resolver, tapear, escribir, pegar, verificar)
  ├──→ resolve_element(micro-intención EN de LA pantalla actual) → Jev-resolver → {idx, conf}
  ├──→ tap_idx / type_text / scroll / back / open_app (una primitiva por paso)
  ├──→ get_clipboard / set_clipboard (SO antes que dedos, §4)
  └──→ forense por paso (quién decidió = director, auditado, §8)
```

Invariantes:

1. **Un planificador.** Solo el director planifica, secuencia y replanifica.
   Ni S2 ni S1 ni `loop.py` planifican metas complejas bajo v5.
2. **Un paso = una herramienta atómica** (§5). `run_sequence` sigue prohibido
   (AGENTS.md §6). El director invoca, observa el efecto (`read_screen_state`
   / `wait_for_node`), y recién entonces decide el paso siguiente.
3. **El director ve cada pantalla.** Sin paso ciego: tras cada mutación hay
   lectura de verificación; el snapshot coalescido se reutiliza como observe
   siguiente (patrón v4 §3.2, ahora a mano del director).
4. **Sin key de Jev → stub `{mock:true}` honesto** (plomería, nunca éxito
   inventado). Sin `OPENROUTER_API_KEY` no hay demo real (§9).
5. **Lo simple sigue funcionando.** El SENT simple bajo `loop.run_goal`
   congelado (§6) no se toca ni se rompe. v5 solo rige metas complejas y
   herramientas nuevas.

## 3. Jev = resolver de elementos, nunca planificador (normativo)

### 3.1 Contrato del resolver

```python
async def resolve_element(screen_goal: str, table: list, snapshot_id: int, *,
                          current_app: str = "",
                          first_result: int | None = None) -> dict:
    """Devuelve {idx: int | "NONE", conf: float, snapshot_id, usage}.
    Pregunta única Choice sobre índices (+ NONE). Sin acción, sin plan."""
```

- **Entrada — micro-intención de la pantalla actual, en inglés, una frase.**
  `screen_goal` describe **solo** lo visible-ahora, p.ej. `"Click the search
  icon"`, `"Tap the Share button"`, `"Tap the Copy link row"`,
  `"Tap the message input field"`. **NUNCA el goal global.**
- **Anti-poisoning (vinculante).** Cuando el director está en YouTube, el
  resolver **no recibe** ni `Luis`, ni `WhatsApp`, ni el objetivo final, ni
  el historial del goal, ni `s2_guidance` con semántica global. Esos tokens
  no existen en su `state`. Violación = bug contra este contrato (se detecta
  capturando el `state` en test, igual que `generic-dual-tier.md` §10.7).
- **Tabla con zona.** Las filas viajan como
  `[idx, class_short, zone, flags, label]` (v4 §4: `zone` 3×3 en inglés,
  `unknown` como fallback; `id`/`bounds` opacos quedan en el host para
  `validate_target` + ejecución). Tabla completa 0..253 + NONE; **prohibido
  podar a 1** (§12.2 ratificado: el `first_result` viaja como hint
  `FIRST_RESULT: <idx>`, nunca como recorte).
- **Pregunta única Choice.** `criteria = {0..253 en tabla, NONE}`. `NONE` =
  "ningún candidato útil en esta pantalla" (el director entonces hace
  `scroll` / `back` / re-observa, nunca tapea a ciegas). Clave fuera de
  criteria → `JevHallucination`, nunca actuar (patrón M1, P0-3 intacto).
- **Salida.** `{idx, conf}` con `conf` finita en `[0,1]`. Umbrales los aplica
  el **director** (`conf < 0.70` → no actuar: re-observar, reformular la
  micro-intención, `scroll`, o `escalate` al operador; `conf ≥ 0.85` +
  trivial + no-sensible → vía rápida a mano del director). Jev no decide
  umbrales ni acciones.
- **La ACCIÓN la decide el director; Jev solo señala.** El resolver no emite
  `TAP/TYPE/SCROLL/BACK/DONE`, no redacta texto, no abre apps, no verifica
  goals. Todo `TYPE` consume texto aportado por el director (vía
  `set_clipboard`/slot/`text_payload`), nunca texto inventado por Jev.
- **Contenido UI = `data`, nunca instrucción** (anti-inyección,
  ARCHITECTURE §6.5). PII enmascarada en host antes de subir; forense con
  hashes/longitudes.

### 3.2 Diferencia con `ask_decision` (para `@coder`)

`ask_decision(goal, ...)` con sus 3 preguntas (`action/target/needs_system_2`)
**no se reutiliza** para el path director: lleva el goal global y decide
acción. El resolver v5 es una vía nueva y mínima sobre `ask(state,
questions)` con **una sola pregunta Choice** y `state.screen_goal` =
micro-intención (§3.1). `ask_decision` queda congelado con `loop.py` (§6);
no se modifica ni se elimina.

## 4. APIs del SO sobre dedos (normativo)

El director prefiere **intents/APIs del SO** a navegar menús frágiles. Orden
de preferencia ante "llevar un enlace de la app-origen a la app-destino":

1. **Copiar vía UI mínima → clipboard del SO → verificar → inyectar.**
   Un solo tap sobre el nodo de copiar (resuelto por §3), luego todo por API.
   No pasear por sheets de share con N taps.
2. **`open_app(package)` directo** (Shizuku `am start`, fallback `monkey`)
   en vez de navegar por launcher/home/recientes.
3. **`ACTION_SET_TEXT` + read-back** en vez de teclado simulado o
   `adb input text` (prohibido en `src/`: solo Shizuku+Accessibility).

### 4.1 Vía exacta de clipboard (vinculante)

Distinción que v5 hace explícita (AGENTS.md §3 + §5):

- **`shell` on-device = OFF hasta Fase 6.** El método `shell` del dispatcher
  Jam sigue respondiendo `METHOD_NOT_ALLOWED` explícito. Nada en v5 lo toca,
  lo rodea ni lo pide. Amenaza: cualquier cliente WS con scope `shell`
  ejecutaría comandos privilegiados **en el teléfono, remoto, sin presencia
  física**.
- **adb-host = diagnóstico permitido.** `adb shell dumpsys clipboard`,
  `adb shell wm size`, `adb forward` corren **en la máquina del operador**
  (acceso físico, depuración USB, harness de pruebas), no exponen superficie
  remota en el teléfono. Ya en uso: `tools/ui.py:screen_height`
  (`wm size`), `_base.py:ensure_forward`, `tools/clipboard.py:
  read_clipboard` (`dumpsys`). v5 los ratifica como vía de harness, no como
  `shell` on-device.

Contrato:

| Herramienta | Vía primaria | Fallback | Prohibido |
|---|---|---|---|
| `get_clipboard` | host `adb shell dumpsys clipboard` parseado en host (`VIA_DUMPSYS`, existe en `tools/clipboard.py:read_clipboard`); verificación por forma `https?://`, sin literales de dominio; vacío/sin-forma → `CLIPBOARD_EMPTY` honesto | pegado-en-campo-efímero + read-back del `text` del nodo enfocado (`VIA_PASTE_READBACK`, hook inyectable existente; nunca `ACTION_SET_TEXT` para leer) | método `shell` on-device; inventar contenido; avanzar al destino sin forma verificada |
| `set_clipboard` (nueva, la implementa `@coder`) | **API del SO sin shell**: método Jam `set_clipboard` vía `ClipboardManager.setPrimaryClip` ejecutado **por la propia app Jam** (foreground service, sin Shizuku, sin grant de shell; es la misma clase de API que `takeScreenshot`/`ACTION_SET_TEXT`, no un exec) | mientras el método Jam no exista: el director **no emula** clipboard con taps ni con `adb input text`; usa `type_text` directo con el texto ya verificado en host (el texto viaja host→Jam como parámetro `type`, igual que hoy) | `adb shell input text`, `service call clipboard` frágil, `shell` on-device, escribir sin verificación previa |

Forense de clipboard (ambas): `clipboard_len + clipboard_sha256 + via`
(`dumpsys | paste-readback | jam-api`); texto crudo solo si el goal no es
sensible, y nunca en log si `is_sensitive` (§7). El contenido verificado
entra como slot opaco `clipboard {len,sha256,consumed}` a `pending_payloads`
/ parámetro `type_text`, con read-back `confirm_input` en destino.

### 4.2 Nota de permisos honesta (para `@coder`, no asumir)

Lectura de clipboard en Android 10+ está restringida a app en foreground /
IME por defecto. Por eso la primaria de **lectura** es el host `dumpsys`
(fuera del sandbox de la app) y la primaria de **escritura** es la propia
Jam (`setPrimaryClip` permitido a la app que lo invoca). Si en el banco
(TECNO KJ5, API 33) alguna vía falla por política OEM, `@coder` lo reporta
como `CLIPBOARD_UNSUPPORTED(via, api=33, oem)` honesto con evidencia, no lo
rodea con shell ni con servicios frágiles.

## 5. Herramientas atómicas del contrato v5

Cada una devuelve `{ok, verified, evidence, hint}`. `verified=true` solo con
verificación real posterior, nunca por "comando enviado".

| # | Herramienta | Garantías deterministas | Errores honestos |
|---|---|---|---|
| 1 | `open_app(package)` (existe: `tools/app.py:open_app`) | Shizuku `am start`, fallback `monkey` (AGENTS.md §5.5); verifica `get_foreground == package` antes de `ok`; estabilización ~600 ms a cargo del director antes del primer `read` | `SHIZUKU_UNAVAILABLE` + hint (arrancar Shizuku); `VERIFY_FAILED` (no llegó a foreground); `S2_BAD_COMMAND`/`BAD_PACKAGE` si forma `a.b.c` inválida |
| 2 | `resolve_element(description)` (nueva, §3; la implementa `@coder` sobre `jev_client.ask`) | micro-intención EN + tabla con `zone`; Choice única sobre índices + NONE; `id`/`bounds` nunca viajan a Jev; `conf` finita; sin key → `{mock:true}` | `JEV_HALLUCINATION` (clave fuera de criteria); `NO_TARGET` (NONE o `conf < tau` a criterio del director); `STALE_SNAPSHOT` (resolver contra snapshot viejo) |
| 3 | `tap_idx(idx, snapshot_id)` (existe como `tools/ui.py:tap_node`) | resuelve `by_idx[idx]` vigente; `ACTION_CLICK` primero si `clickable`, `dispatchGesture` fallback; reporta `via`; **no devuelve snapshot** (el director verifica) | `SELECTOR_NOT_FOUND` (idx fuera de tabla / no `visible` / bounds fuera de pantalla); `STALE_SNAPSHOT` (re-hacer `read` y re-resolver, 1 reintento en el director, no en la app); `FORBIDDEN_TARGET` (solo con `forbidden?` opt-in) |
| 4 | `type_text(node_id, snapshot_id, text)` (existe: `tools/ui.py:type_text`) | REPLACE vía `ACTION_SET_TEXT` (clear semántico, sin append); **exige foco explícito**: sin `focused` → no escribe; read-back `confirm_input` a cargo del director | `NOT_FOCUSED` (el director hace `tap` previo explícito, nada implícito); `STALE_SNAPSHOT`; `input_unverified` (enviado pero no confirmado: inspeccionar, nunca retype ciego) |
| 5 | `read_screen_state()` (existe: `tools/ui.py:read_screen`) | `dump_ui` fresco + normalizer (filtra decoración; tope 500 raw) + tabla 0..253 + NONE + `snapshot_id` monotónico + `current_app` + `zone/first_result/focused_field/screen_w/h` | `ACCESSIBILITY_DISABLED`; `SECURE_SURFACE` solo vía `screenshot`, nunca en `dump_ui` (AGENTS.md enmienda 2026-10-02: `root == null` = sin ventana activa, transitorio); `TIMEOUT` |
| 6 | `get_clipboard()` (existe: `tools/clipboard.py:read_clipboard`) | vía §4.1; verificación por forma; slot opaco | `CLIPBOARD_EMPTY` (copiar primero, no inventar); `CLIPBOARD_UNSUPPORTED` (vía + API + OEM) |
| 7 | `set_clipboard(text)` (nueva, §4.1) | vía Jam `ClipboardManager` (sin shell); verifica con `get_clipboard` read-back de forma | `CLIPBOARD_UNSUPPORTED`; `METHOD_NOT_ALLOWED` si alguien la pide vía `shell` on-device (ese camino no existe) |
| — | `scroll(direction, node_id?)`, `press_back()`, `wait_for_text`, `screenshot` (existen) | sin cambio; `screenshot` > 4 MiB → `PAYLOAD_TOO_LARGE` (hint WebP q80); `FLAG_SECURE` → `SECURE_SURFACE` | los vigentes en `_base.jam_fail` |

## 6. Decisión sobre `loop.py`: CONGELADO (no stepper, no borrado)

**Decisión `@architect`: `loop.py:run_goal` se congela en estado
post-v4+§12.** Fundamento:

- **Prohibido romper lo que funciona.** El SENT simple (un campo, un envío,
  camino feliz con `EXECUTE_GOAL` + `TYPE` + `confirm`) está verificado y
  cubierto por tests. Borrarlo o reutilizarlo como stepper del director
  (inyectándole micro-intenciones por la fuerza) rompería su invariante
  "un goal global → un plan S2 → N passes S1" y sus tests.
- **Stepper contaminaría.** Reusar `run_goal` como "stepper" del director
  arrastraría S2-compilador, `preloaded_inputs`, `FAST_TAU`, `DONE`-gate y
  `CostTracker` dual al path director, reintroduciendo la Inception por la
  puerta trasera. El director no necesita un stepper con LLM dentro:
  necesita las herramientas §5 + `core/loop_helpers` puros
  (`build_table/validate_target/confirm_input/screen_fingerprint/
  CostTracker`) como **librería sin LLM**, que ya son importables sin
  `run_goal`.
- **Régimen de congelado (vinculante):**
  1. `loop.py`, `jev_client.ask_decision`, `s2_client` (comandos +
     `EXECUTE_GOAL`) y sus tests **no reciben features nuevas**.
  2. Solo se aceptan bugfixes de seguridad/regresión con test que demuestre
     que el SENT simple sigue verde.
  3. Todo desarrollo nuevo (resolver §3, `set_clipboard` §4.1, herramientas
     §5) vive **fuera** de `run_goal`, sin importarlo.
  4. `@judge` certifica el congelado con: `uv run pytest` verde **antes y
     después** de cualquier cambio v5 + grep §9.2.

## 7. Seguridad intacta (estructurales siempre + críticas con confirm)

Deriva de AGENTS.md §3 + §5.14-16 + enmienda 2026-10-05 (genérica, sin
literales de dominio en `src/`). v5 no deroga nada en silencio:

### 7.1 Estructurales — siempre, sin excepción, también en vía rápida

Antes de cada mutación que ordene el director: nodo presente y `visible` en
el snapshot vigente, bounds/coords en pantalla, JSON válido contra el enum,
`snapshot_id` fresco, `resolve_element` contra la tabla vigente (mismatch →
`STALE_SNAPSHOT`, re-observar + re-resolver una vez; segundo `STALE` →
`UI_UNSTABLE`). Taps: `ACTION_CLICK` primero si `clickable`, gesto fallback,
siempre `via`. Type: foco explícito + `ACTION_SET_TEXT` + read-back. Sin
nodo → `SELECTOR_NOT_FOUND` / `NONE`, nunca coordenadas inventadas.

### 7.2 Críticas/irreversibles — preview + `confirm:true` del operador

Categorías genéricas (no exhaustivo; el operador amplía por goal):
**enviar/comunicar a terceros, comprar/pagar, borrar datos, cambios de
cuenta/seguridad/permisos, `shell`/adb**. Régimen: el director las marca
`is_sensitive`; sin `confirm:true` se **planean sin ejecutar**
(`planned:true` + `preview {acción,target,label-hash,text-len/sha256,
snapshot}` + `needs_confirm:true`, `verified:false`); con `confirm:true` →
ejecución + verificación + auditoría. `shell`/adb gateados por scope `shell`
+ grant activo; on-device sigue `METHOD_NOT_ALLOWED` (Fase 6). El default
`FORBIDDEN` no existe: `forbidden?` opt-in por goal, nunca global.

## 8. Forense por paso: quién decidió = el director (auditado)

`logs/run-<ts>.jsonl` por corrida del director, una entrada por paso con:

```json
{
  "step": 3, "phase": "director_resolve_tap",
  "decided_by": "director",
  "director_goal": "hash del goal global (nunca crudo si sensible)",
  "screen_goal": "Tap the Copy link row",
  "current_app": "app en foreground (valor runtime)",
  "snapshot": 41, "snapshot_after": 42,
  "table_fp": "sha256 de la tabla enviada",
  "first_result": 7,
  "jev": {"idx": 7, "conf": 0.91, "mock": false},
  "action": {"kind": "tap_node", "node_id": "n_7"},
  "via": "action_click",
  "verify": {"ok": true},
  "clipboard": {"len": 43, "sha256": "…", "via": "dumpsys"},
  "cost": {"model": "…", "in": 0, "out": 0, "usd": 0.0},
  "error": null
}
```

Reglas: `decided_by` obligatorio (`director` | `operator-confirm` en críticas;
nunca `jev`/`s2` como decisor bajo v5); `screen_goal` en claro (micro,
no sensible por construcción anti-poisoning); goal global solo como hash si
sensible; textos crudos jamás si `is_sensitive` (solo `len/sha256`); `wire`
íntegro del resolver (request/response) + `cost [COST]` por llamada Jev. Sin
forense, un incidente es indiagnosticable.

## 9. Aceptación verificable (`@judge`, sin editar)

Desde `mcp-server/`:

1. **pytest verde antes y después** (congelado §6): `uv run pytest` verde con
   los tests v3/v4/§12 existentes (bootstrap, payload EN, `TAP`-direct,
   `first_result`, `run_signature`, slot `clipboard`). Ningún test de
   `run_goal` se rompe ni se reescribe para v5; los nuevos tests v5 viven en
   `tests/test_director_*.py` (resolver + herramientas, con stubs).
2. **Greps de cero-acoplado + anti-poisoning** (en `src/` → **vacío** para
   literales de dominio; permitido en `docs/` y tests como valores runtime):
   `whatsapp|com\.whatsapp|contact_name|verify_chat|wrong_chat|reenviar|
   dry-run-de-chats|fase5_check|send_whatsapp` — y extendido al vocabulario
   de la demo §9.4 como valores en tests/docs, nunca en `src/`. Además:
   `grep -rn 'ask_decision' src/jev_mcp/tools/ src/jev_mcp/director*` →
   **vacío** (el path director nunca llama al decisor con goal global).
3. **Resolver ciego al goal en test.** El test captura el `state` enviado al
   resolver y aserta: una sola pregunta Choice sobre índices + NONE; cero
   instrucciones en español; tabla con forma
   `[idx, class_short, zone, flags, label]`; **ausencia** del goal global,
   nombres propios y paquetes en el `state` (solo micro-intención +
   `current_app` + tabla).
4. **Demo dirigida por el director (instancia no-normativa YouTube→Luis).**
   Con dispositivo + keys, el director (operador) ejecuta por pasos el goal
   de validación — llevar un enlace de vídeo de la app-origen a la persona
   destino en la app de mensajería (valores concretos aportados en runtime
   por el operador, nunca en `src/`) — narrada en el informe del director:
   cada pantalla con `read_screen_state`, cada tap precedido por
   `resolve_element("…")` con micro-intención citada, el traspaso por
   `get_clipboard` (`CLIPBOARD_EMPTY` si se olvidó copiar, sin inventar URL),
   el envío final solo con `confirm:true` + preview auditada, y forense +
   `[COST]` completos. Si la búsqueda no pasa al 2º intento o 2 corridas
   mueren con igual `run_signature`, fail-fast §12.3: dif de forenses +
   informe, prohibido relanzar a ciegas.
5. **Compuertas.** Estructural siempre; crítica sin `confirm:true` →
   `planned` sin tocar dispositivo; `conf < 0.70` del resolver → sin actuar;
   `STALE×3` → `UI_UNSTABLE`; `shell` on-device → `METHOD_NOT_ALLOWED`.

## 10. Alcance para `@coder` (no improvisar arquitectura)

- **Nuevo `resolve_element`** (host, sin tocar `ask_decision` ni `loop.py`):
  construye `state {screen_goal (micro EN), current_app, snapshot_id, table,
  first_result}` + **una** pregunta `choice {idx…|NONE}` sobre
  `jev_client.ask`; valida con `validate_choice` estricta (M1/P0-3);
  devuelve `{idx, conf, usage}` + `CostTracker`; forense §8. Tests
  `test_director_resolve_*` (resuelve, NONE, hallucination, anti-poisoning
  §9.3).
- **Nuevo `set_clipboard`** (host + Jam): método Jam `set_clipboard` vía
  `ClipboardManager.setPrimaryClip` (app, sin shell — ver §4.1) + wrapper
  host en `tools/clipboard.py` con read-back de forma + `CLIPBOARD_EMPTY /
  CLIPBOARD_UNSUPPORTED` honestos. Mientras la app no lo exponga: wrapper
  host que falla honesto `CLIPBOARD_UNSUPPORTED(jam-api-missing)` y el
  director usa `type_text` directo (degradación documentada, no emulación
  con taps/`input text`). Tests con stubs (vacío / con forma / sin forma /
  unsupported).
- **Mover/reatar `get_clipboard`**: sin cambio de semántica
  (`read_clipboard` intacto); exponerlo como herramienta MCP junto a las
  §5 con envolvente `{ok,verified,evidence,hint}`.
- **Prohibido**: tocar `loop.py`/`ask_decision`/`s2_client` salvo bugfix de
  regresión §6.2; `su`; `shell` on-device; nuevas dependencias fuera de
  AGENTS.md §4; `0.0.0.0`; token en URL; coordenadas inventadas.
- **Docs que sí puede tocar `@coder`**: `README.md` en `android-app/` si
  añade el método Jam + `docs/PROTOCOL.md` + `docs/TESTING.md` con comandos
  manuales (AGENTS.md §8: sin Android Studio). Este spec no lo edita.

## 11. Divergencias documentadas (operador → v5)

1. **Inception enterrada.** El operador pide director-cliente y enterrar
   OpenCode→loop→S2→Jev→Jam. v5 lo adopta para metas complejas y congela el
   loop (§6) en vez de borrarlo: borrar rompería el SENT simple verificado.
2. **Jev pierde la acción.** El operador pide "pregunta única Choice sobre
   índices". v5 elimina `action/needs_system_2` del resolver: la acción vive
   en el director, que tiene el contexto completo. `DONE/ESCALATE` del S1
   mueren con `ask_decision`; el cierre bajo v5 lo decide el director con
   `verify_final` determinista (re-lee pantalla, nunca solo-Jev).
3. **`set_clipboard` sin shell.** El operador pide `get/set_clipboard` con
   shell on-device OFF. v5 fija la vía §4.1 (host-`dumpsys` para leer, Jam
   `ClipboardManager` para escribir) y declara la distinción adb-host vs
   shell on-device como norma, no como truco: el primero es harness con
   presencia física, el segundo superficie remota.
4. **Enmienda AGENTS.md §1 propuesta (no aplicada aquí).** Texto candidato:
   *"El director (cliente) decide el plan; Jev resuelve elementos de la
   pantalla actual con micro-intención ciega al goal global; Jam ejecuta
   primitivas. `loop.run_goal` queda congelado como modo legacy para el
   SENT simple."* `@architect` no enmienda AGENTS.md (fuera de su alcance
   en esta tarea); lo deja anotado para el orquestador.

## Apéndice A — esqueleto de la demo YouTube→Luis (no-normativo, para el informe del director)

> Instancia concreta del §9.4. Valores reales en runtime; este esqueleto
> solo fija la **narración exigida** en el informe, no el contenido.

1. `read_screen_state` → foreground real; `open_app(<paquete-origen>)` solo
   si no está en foreground (+ ~600 ms + re-`read`).
2. Por pantalla: `resolve_element("<micro EN de ESTA pantalla>")` citado
   verbatim (p.ej. `"Click the search icon"`, `"Tap the Share button"`,
   `"Tap the Copy link row"`) → `{idx, conf}` → `tap_idx` → `read` de
   verificación. Jamás el goal global en el resolver.
3. Tras copiar: `get_clipboard` → forma `https?://` verificada
   (`clipboard_len/sha256/via` en forense). Vacío → `CLIPBOARD_EMPTY`: el
   director informa y reintenta el tap de copiar, no inventa URL.
4. `open_app(<paquete-destino>)` → resolver campo/hilo con micro-intención
   (`"Tap the message input field"`) → `type_text` o `set_clipboard` +
   pegar según §4.1 → read-back.
5. Envío: compuerta crítica §7.2 — preview + `confirm:true` explícito del
   operador, auditado. Sin confirm no hay envío (`planned` + forense).
6. Cierre: `verify_final` del director (re-lee pantalla) + `run_signature`
   si `ok:false`. Informe con cada paso numerado, cada `screen_goal`, cada
   `{idx, conf}`, cada `via`, y líneas `[COST]`.
