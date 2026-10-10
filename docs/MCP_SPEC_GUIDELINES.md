# MCP_SPEC_GUIDELINES — estándar de diseño cognitivo de Jav

> Estado: **normativo v1 2026-10-07**. Redacta `@architect`,
> implementa `@coder`, certifica `@judge`. En conflicto, **AGENTS.md manda**.
>
> Alcance: **solo diseño** (qué debe entender un agente que consume a Jav
> por MCP, qué texto recibe y qué criterio rige cada capa). **Sin
> implementación, sin keys, sin literales de dominio.** 100% genérico:
> los valores concretos (paquetes, textos, URLs) solo existen en runtime,
> aportados por el operador o resueltos por conocimiento general; nunca
> en este documento ni en descripciones de tools.
>
> Fuentes normativas leídas para v1:
>
> - Servidor Go (raíz del repo): `cmd/jav/main.go` (stdio, logs solo a
>   stderr), `pkg/tools/register.go` (35 tools, descripciones ES de
>   5 secciones verbatim de Python), `pkg/tools/helpers.go` + `ui.go`
>   (validación client-side, envolvente, `readScreenState` sin
>   post-snapshot), `pkg/jam/jam.go` (`hintFor`, `Dial` + `hello`,
>   frame máximo 4 MiB).
> - `mcp-server/src/jev_mcp/server.py` — 35 tools + docstrings ES de
>   5 secciones (Descripcion / Parametros / Retorno / Permisos-Grants /
>   Errores-gotchas), inyectadas como descripción de tool en el LLM.
> - `PROTOCOL.md` — contrato WS app ↔ MCP (§§1–8: transporte, `hello`,
>   scopes, comandos, esquema de nodo, eventos, códigos de error,
>   seguridad operativa).
> - `docs/specs/go-migration-plan.md` — identidad `jav`, stdio primero,
>   `tools/list` idéntico Python ≡ Go, envolvente
>   `{ok, verified, evidence, hint}` como único `TextContent` JSON con
>   `isError = !ok`, `initialize + tools/list` sin Jam alcanzable.
> - Contratos vivos que este documento **no deroga**:
>   `docs/specs/generic-dual-tier.md` (S1/S2, `TAU = 0.70`, compuertas,
>   `planned:true` + `confirm:true`, forense JSONL) y `AGENTS.md §§1–9`
>   (Jev decide no ejecuta, accesibilidad como única lectura, error
>   honesto, sin `su`, sin `run_sequence`, sin teclado simulado).

## 0. Principio rector

Jav es un buen MCP cuando un agente que **no sabe qué es Jam,
`snapshot_id` o foco** actúa correctamente **al primer intento** sin
haber leído ningún otro documento. Todo lo que ese agente necesita
vive en exactly tres lugares, en este orden de lectura:

1. El bloque `instructions` del `initialize` (§1): el modelo mental
   mínimo (carriles, frescura, foco, confirmación).
2. La descripción de cada tool (§2): affordances positivas **y
   negativas** con ejemplo genérico.
3. El `hint` de cada error (§3): la instrucción de recuperación exacta.

Si una decisión correcta exige información fuera de esos tres lugares,
es un defecto de este estándar, no del agente. `@coder` lo corrige
editando texto (descripciones, `instructions`, hints), nunca añadiendo
tools nuevas sin enmienda aquí.

Convención de lengua (v1, congelada): `instructions` y payloads de
decisión van en **inglés** (los clientes son EN; la calibración de los
modelos decisores se entrena en inglés). Las descripciones de las 35
tools y los hints siguen en **español** (verbatim Python ≡ Go, spec de
migración §4). Cuando las descripciones migren a EN se hará por
enmienda con diff `tools/list` vacío en `name + schema`. Nunca mezclar
lenguas dentro del mismo campo.

## 1. Bloque `instructions` del `initialize`

### 1.1 Texto normativo EN (verbatim para `initialize`)

El servidor DEBE exponer en el `initialize` (campo `instructions` del
handshake MCP) el siguiente texto, verbatim salvo la versión:

```text
You control an Android device through Jav, a bridge to the on-device
accessibility service (Jam). You never see pixels unless you ask for a
screenshot, and you never invent coordinates: every tap or type targets
a node id from a fresh screen snapshot.

LANE HIERARCHY — always prefer the cheapest lane that answers the need:
1. NATIVE first (direct device APIs: battery, memory, storage, cpu,
device_info, settings_get, clipboard metadata, usage aggregates,
contacts/calendar/notifications/media/location/photo). No UI, nolane
switch, no focus needed.
2. INTENTS second (open_url, send_intent): open or pre-fill the target
app. Intents never send, post, pay, or delete headlessly: at most they
open a pre-filled editor; the send happens in the destination UI or
through the UI lane with gates.
3. UI last (read_screen, tap_node, type_text, scroll, press_back,
wait_for_text): drive the screen node by node. Slow and stateful;
use only when lanes 1-2 cannot satisfy the goal.

FRESHNESS — read_screen returns a monotone snapshot_id. tap_node and
type_text REQUIRE the snapshot_id you just read; if the UI changed
since, they fail with STALE_SNAPSHOT. Never retry the same snapshot:
re-read and resolve the node again (one retry; a second STALE means
the screen is unstable — stop and report UI_UNSTABLE).

FOCUS — type_text only writes into the focused field (REPLACE
semantics via ACTION_SET_TEXT, no simulated keyboard, no append). If
the node is not focused you get NOT_FOCUSED: tap the field first,
re-read, then type. There are no implicit taps.

VERIFY — actions never return a snapshot. After every mutation,
verify with read_screen or wait_for_text and report what changed.
Prefer tap_node over tap-by-text when you already hold a fresh
snapshot (no internal re-dump). Prefer ACTION_CLICK paths (clickable
nodes) and expect the result field `via` telling which path executed.

CONFIRM — critical or irreversible effects (messaging third parties,
buying/paying, deleting data, account/security/permission changes,
photo capture, media stop, settings writes) NEVER execute on first
call: they answer {planned:true, preview, hint} with verified:false.
Repeat with confirm:true only after the operator approved the exact
preview. Previews carry lengths/hashes, never raw sensitive text.

PRIVACY — clipboard, contacts, calendar, notifications, and location
are minimal-projection: counts/hashes/lengths in logs, never raw
content beyond what the task strictly needs. Never log secrets,
tokens, or full message bodies.

ERRORS — every failure carries a machine code in evidence.code plus a
human recovery instruction in hint. Follow the hint literally; it is
part of the contract (see the per-tool Errors section for the catalog).
```

### 1.2 Versión corta ES (para docs, onboarding y QR)

> Controlas un Android vía Jav: primero APIs directas (batería, memoria,
> ajustes, portapapeles, contactos…), luego intents (abrir/pre-rellenar,
> nunca envían solos), y solo al final la UI nodo a nodo. La pantalla se
> lee con `read_screen` (da un `snapshot_id`); `tap_node`/`type_text` lo
> exigen y fallan `STALE_SNAPSHOT` si cambió (re-lee una vez; segundo
> fallo = pantalla inestable, para e informa). Escribir exige foco
> (`NOT_FOCUSED` → tapea el campo, re-lee, escribe; reemplaza, no añade).
> Las acciones no devuelven snapshot: verifica siempre después. Lo
> crítico/irreversible se planea sin ejecutar (`planned:true`) y solo se
> ejecuta repitiendo con `confirm:true` tras aprobación del operador.
> Todo error trae `code` + instrucción en `hint`: síguela literalmente.

### 1.3 Reglas de mantenimiento del bloque

1. Longitud máxima: el bloque EN no supera **400 palabras**. Si una
   adición lo supera, se compacta otra frase; nunca crece por acrescencia.
2. Prohibido en el bloque: nombres de paquetes, nombres de apps,
   literales de UI, regex de dominio, precios, keys, URLs concretas.
   Solo formas (`a.b.c`, `https?://`, `confirm:true`).
3. Cada sustantivo operativo del bloque (`snapshot_id`, `STALE_SNAPSHOT`,
   `NOT_FOCUSED`, `planned:true`, `via`) existe verbatim en al menos una
   descripción de tool (§2) y en la tabla de errores (§3). Término sin
   ancla = término prohibido.
4. La versión ES es informativa; ante divergencia manda la EN.

## 2. Docstrings con affordances negativas (formato exigible por tool)

### 2.1 Estado actual y delta normativo

Las 35 tools ya tienen 5 secciones (Descripcion / Parametros / Retorno /
Permisos-Grants / Errores-gotchas), idénticas Python ≡ Go. Este
estándar **no las reescribe**: define el **delta exigible** a partir de
v1 para toda tool nueva o re-descripción:

- **Sección 6 — `Cuándo NO usar`** (obligatoria): 1–3 líneas, cada una
  con forma `NO <abuso> → usa <alternativa>`. Nombra la tool
  alternativa exacta. Cero jerga interna sin enlace (si menciona
  `snapshot_id`, explica de dónde sale en la misma línea).
- **Sección 7 — `Ejemplo`** (obligatoria): una llamada mínima con
  valores **genéricos de forma** (`a.b.c`, `<text>`, `down`, `png`) más
  la forma del `evidence` esperado. Nunca paquetes reales, nunca PII,
  nunca URLs reales.

Plantilla (orden fijo, 7 secciones):

```text
<Primera línea: qué hace en una frase, verbo + objeto.>

Descripcion: <qué hace + carril (nativo/intent/UI) + efecto observable>.
Parametros: <nombre (tipo): forma y default; obligatorio marcado REQ>.
Retorno: {ok, verified, evidence, hint}; evidence = {<forma>}.
Permisos/Grants: <scope + grant de usuario si exige; "sin grant" explícito si no>.
Errores/gotchas: <códigos que emite + condición de cada uno>.
Cuándo NO usar: <NO abuso → usa alternativa; ...>.
Ejemplo: <llamada genérica> → <evidence de forma>.
```

### 2.2 Reglas transversales

1. La primera línea decide el enrutado: contiene el carril
   (`directa|intent|pantalla`) y si muta o solo lee. El agente elige
   carril sin leer más.
2. Toda tool que mute exige sección `Cuándo NO` que cite la vía de
   verificación (`read_screen` / `wait_for_text`) y recuerde que la
   acción **no devuelve snapshot**.
3. Toda tool con régimen `planned:true` lo declara en `Retorno` con la
   frase canónica: `sin confirm → {planned:true, preview, hint},
   verified:false; con confirm → ejecuta y verifica`. La palabra
   `preview` aparece solo en tools con `confirm`.
4. Unidades siempre explícitas donde el contrato mezcla (`timeout_ms`
   en MILISEGUNDOS, `max_age_s` en SEGUNDOS, bytes vs %, PX lógicos).
   La ambigüedad de unidades es defecto bloqueante en revisión.
5. PII: ninguna descripción promete texto crudo donde el contrato
   devuelve hash/longitud (`get_clipboard_device`, `list_contacts`,
   `list_events`, `reply_notification`, `create_event`, `get_location`,
   `take_photo`). Si la tool devuelve crudo (p.ej. `read_screen`
   `label`), la descripción lo dice y ordena enmascarar antes de subir
   a modelos externos.
6. Ejemplos 100% genéricos: `package: a.b.c`, `url: https://<forma>`,
   `text: <texto del operador>`. Un ejemplo con valor real de dominio
   invalida la aceptación (§6).

### 2.3 `Cuándo NO` canónico por grupo (verbatim mínima exigible)

- `read_screen`: `NO sondear en bucle → usa wait_for_text con timeout;
  NO actuar sobre su salida sin snapshot_id → tap_node/type_text lo exigen.`
- `tap_text` (atajo director): `NO usar con snapshot fresco → usa
  tap_node (evita dump interno); NO es acción del enum decisor.`
- `tap_node`: `NO reutilizar snapshot tras cualquier evento/mutación →
  re-lee; NO esperar snapshot en su respuesta → verifica después.`
- `type_text`: `NO escribir sin foco → tap + re-lee primero; NO añadir:
  es REPLACE del contenido final; NO inventar texto: solo goal/UI o
  payload del nivel superior.`
- `scroll`: `NO insistir >2 veces sin cambio de snapshot → usa
  wait_for_text o BACK; NO asumir fin de lista sin re-leer.`
- `wait_for_text`: `NO usar como lectura general → es espera bloqueante
  con timeout; su snapshot_id sirve directo solo sin cambios intermedios.`
- `screenshot`: `NO usar para localizar nodos → usa read_screen (el
  árbol sigue visible bajo FLAG_SECURE); NO png gigante → webp q80 ante
  PAYLOAD_TOO_LARGE.`
- `open_app` / `close_app`: `NO abrir por intent directo desde fondo →
  es Shizuku am start + verify foreground; NO asumir éxito sin
  get_foreground/read_screen.`
- `open_url`: `NO usar para enviar/comunicar → eso es send_intent +
  carril UI con compuertas; NO fijar package salvo 1 salto determinista.`
- `send_intent`: `NO esperar envío headless → como máximo abre editor
  pre-rellenado; crítica sin confirm → planned, nunca ejecuta.`
- Nativas de lectura (`get_battery/memory/storage/cpu/device_info`,
  `settings_get`, `get_app_usage`, `list_contacts/events/notifications`,
  `media_state`, `get_location`): `NO ir a la UI para este dato → carril
  nativo primero; NO pedir detail=fine donde es N2 → METHOD_NOT_ALLOWED.`
- Críticas con `confirm` (`settings_put`, `add_contact`,
  `create_event`, `reply_notification`, `media_control stop`,
  `take_photo`): `NO ejecutar sin preview aprobado → primera llamada
  planea; NO reenviar preview distinto con el confirm anterior.`

## 3. Errores accionables: todo error lleva `recovery_instruction`

### 3.1 Norma de envolvente

Todo fallo devuelve la envolvente `{ok:false, verified:false,
evidence:{code, error}, hint}` donde `hint` **es** la
`recovery_instruction`: imperativa, en una frase, ejecutable sin leer
otro documento. `code` es estable y programático (mayúsculas con
`_`); `error` es el detalle humano libre. Origen del código:

- **Jam** (dispatcher/extractora en dispositivo, vía `PROTOCOL.md §7`).
- **MCP** (validación client-side o transporte host antes de dial).
- **Loop** (síntesis del cliente tras patrón, p.ej. `UI_UNSTABLE`;
  nunca inventada por el servidor).

Prohibido: `ok:false` sin `code`; `hint` vacío; `hint` que repita el
error sin ordenar acción; reintento mudo del mismo payload ante
`METHOD_NOT_ALLOWED` o `VALIDATION_ERROR`.

### 3.2 Tabla código → instrucción (canónica v1)

| code | significado | recovery_instruction (`hint` verbatim ES) | reintento |
|---|---|---|---|
| `STALE_SNAPSHOT` | el `snapshot_id` ya no es vigente | `re-haz read_screen y usa el snapshot nuevo (un reintento; segundo STALE = UI_UNSTABLE, para)` | 1× con re-observe |
| `NOT_FOCUSED` | el nodo no tiene foco para escribir | `haz tap sobre el campo antes de type_text (luego re-lee y escribe)` | sí, tras tap + re-lee |
| `SELECTOR_NOT_FOUND` | ningún nodo matchea | `re-haz read_screen; el selector no matchea (no inventes ids ni coordenadas)` | sí, tras re-lee |
| `TIMEOUT` | `wait_for_node` / grant / fix sin resultado | `reintenta o sube el timeout; si se repite ×3 sin cambio, para (fail-fast)` | sí, con backoff |
| `ACCESSIBILITY_DISABLED` | servicio Jam no conectado | `habilita Jam en Ajustes → Accesibilidad y reintenta` | no (hasta grant) |
| `SHIZUKU_UNAVAILABLE` | Shizuku no corre o sin permiso | `arranca Shizuku (lo hace el usuario) y reintenta; sin él solo vive el carril lectura/UI` | no (hasta Shizuku) |
| `SHIZUKU_DENIED` | permiso runtime Shizuku denegado | `concede el permiso runtime de Shizuku a Jam y reintenta` | no (hasta grant) |
| `UNAUTHORIZED` | sin token o token inválido (cualquier bind, loopback incluido) | `revisa JAV_TOKEN en el entorno del servidor (nunca viaja en URL)` | no (config) |
| `FORBIDDEN` | sin scope o clave sensible denegada | `pide scope/permiso correspondiente; no reintentes el mismo payload` | no |
| `METHOD_NOT_ALLOWED` | método gateado a fase posterior (shell, N2 `secure`/`global`/`fine`) | `metodo no disponible en esta fase; no reintentes igual (usa el carril permitido)` | **nunca** |
| `VALIDATION_ERROR` | args con forma inválida | `revisa los parametros de la tool (forma, enum, rangos, unidades)` | sí, corrigiendo |
| `SECURE_SURFACE` | ventana con `FLAG_SECURE` (solo `screenshot`) | `la ventana tiene FLAG_SECURE; usa dump_ui (read_screen), no screenshot` | no (cambia de vía) |
| `PAYLOAD_TOO_LARGE` | frame > 4 MiB | `reintenta con fmt webp y quality 80` | sí, degradando |
| `INTENT_UNRESOLVED` | paquete instalado pero sin handler del intent/URL | `elige otra app destino o abre sin package (chooser) y verifica` | sí, cambiando target |
| `PACKAGE_NOT_FOUND` | paquete no instalado | `verifica el paquete con list_packages; el paquete lo aporta el operador, no lo adivines` | no (hasta dato) |
| `CLIPBOARD_EMPTY` | portapapeles vacío o 2.º plano (Android 10+) | `copia primero en la app-origen y re-lee (host dumpsys o pegado-readback); no inventes contenido` | sí, tras copiar |
| `UI_UNSTABLE` | síntesis loop: `STALE`×3 o snapshot/fingerprint sin progreso | `para: dif de forenses + informe (firma igual en 2 corridas = no relanzar)` | **nunca** a ciegas |
| `VERIFY_FAILED` | `open_app`/`close_app` sin efecto en foreground | `confirma con get_foreground/read_screen; si no llegó, un reintento y luego informe` | 1× |
| `CONNECTION_FAILED` | WS/host inalcanzable (MCP) | `revisa adb forward + dispositivo conectado; reintenta una vez tras forward` | 1× tras forward |
| `RATE_LIMITED` / `BUSY` | límite o single-client ocupado | `espera y reintenta con backoff; segundo cliente recibe BUSY` | sí, con espera |
| `SHELL_DENIED` / `SHELL_DENYLIST` | grant shell denegado o comando en denylist | `pide grant en el dispositivo (1 comando/5 min/30 min); denylist exige admin + confirm:true` | no (hasta grant) |
| N1 sin grant (`USAGE_ACCESS_DISABLED`, `CONTACTS_PERMISSION_DENIED`, `CALENDAR_PERMISSION_DENIED`, `NOTIFICATION_LISTENER_DISABLED`, `MEDIA_SESSIONS_UNAVAILABLE`, `LOCATION_PERMISSION_DENIED`, `CAMERA_DENIED`, `WRITE_SETTINGS_DISABLED`, …) | permiso/grant de usuario ausente | `concede el acceso en el dispositivo (estado visible en hello.caps) y reintenta; sin grant, error honesto` | no (hasta grant) |
| Transitorios destino (`NOTIFICATION_GONE`, `NO_REMOTE_INPUT`, `REPLY_FAILED`, `MEDIA_SESSION_GONE`, `MEDIA_CONTROL_FAILED`, `LOCATION_UNAVAILABLE`, `LOCATION_TIMEOUT`, `CAMERA_UNAVAILABLE`, `CAMERA_FAILED`, `SETTINGS_PUT_FAILED`, `CALENDAR_UNAVAILABLE`, `INTENT_FAILED`) | estado del destino, no del agente | `re-observe el destino (lista/sesiones/permiso) y decide de nuevo; nunca inventes el efecto` | 1× tras re-observe |

Notas:

1. Los hints ya implementados en `pkg/jam/jam.go:hintFor` son el núcleo
   canónico; `@coder` extiende el mapa con las filas restantes **sin
   cambiar** los existentes (compatibilidad forense).
2. `UI_UNSTABLE` no la emite Jam ni el servidor: la sintetiza el cliente
   (loop/director) tras el patrón §3.2 y la registra en la firma de
   corrida (`run_signature`). El servidor nunca la inventa.
3. `CLIPBOARD_EMPTY` distingue honestamente vacío vs 2.º plano solo si
   la plataforma lo permite; en caso contrario el hint genérico de la
   tabla basta (no sondear de más).

## 4. Tres capas: Resources vs Prompts vs Tools (diseño + criterios)

### 4.1 Criterio general (qué SÍ va en cada capa)

- **Tools** = lo único que **actúa o lee fresco**. Mutaciones atómicas
  (una primitiva por llamada, sin `run_sequence`) y lecturas con
  estado vigente (`snapshot_id`, foreground, sensores). Toda tool es
  verificable después y auditable en forense. Si algo toca el
  dispositivo o devuelve estado que caduca en segundos, es Tool.
- **Resources** = vistas **de solo lectura, cacheables, sin parámetros
  sensibles y sin efectos**. Un Resource nunca muta, nunca exige
  `confirm`, nunca devuelve PII cruda ni blobs > marco razonable, y su
  contenido puede servirse minutos después sin inducir a actuar sobre
  ids caducados. Todo Resource declara `stale_after` y advierte que sus
  ids no son accionables directos (hay que re-leer por Tool).
- **Prompts** = flujos **multi-paso guiados que componen Tools** (y
  citan Resources como contexto), sin ejecutar nada por sí mismos. Un
  Prompt nunca toca el dispositivo; produce un plan con compuertas
  (`verify`, `confirm`, `planned:true`) que el operador/agente ejecuta
  paso a paso por Tools. Si el flujo necesita una decisión con texto
  abierto, escala al nivel superior con el texto ya redactado como
  payload opaco.

Lo que NO va en cada capa: nada que mute en Resources; ningún paso
ejecutable directo en Prompts (solo guía + plantillas de verificación);
ninguna secuencia compuesta en Tools (granularidad para el loop).

### 4.2 Resources (solo diseño)

- `android://device/telemetry` — **SÍ**: agregados lentos y sin PII
  (batería, memoria, almacenamiento `basic`, cpu `basic`, info de
  dispositivo sin IDs persistentes, estado de grants `caps`). Lectura
  idempotente, cacheable ~60 s, cero parámetros. **NO**: desglose
  `fine` (N2), series por proceso, identificadores persistentes,
  clipboard crudo, contactos/calendario/notificaciones (son Tools con
  proyección mínima + forense, no snapshot cacheable).
- `android://screen/current_summary` — **SÍ**: resumen estabilizado de
  la pantalla (paquete foreground, conteo de candidatos, campo con
  foco como vista, `first_result` como hint, marca temporal +
  `stale_after` corto en segundos). Texto compacto, sin `node_id`
  accionables (o marcados explícitamente `no-actionable`). **NO**:
  snapshot completo con ids (eso es `read_screen` Tool), píxeles,
  jerarquía cruda de 500 nodos, contenido sensible íntegro.

Ambos Resources llevan advertencia canónica: `snapshot decorativo —
para actuar, lee por Tool y usa su snapshot_id vigente`.

### 4.3 Prompts (solo diseño)

- `troubleshoot_app` — **SÍ**: guía de diagnóstico por carril (1.
  `device_status` + `get_foreground`, 2. nativas que descarten entorno,
  3. `read_screen` + `wait_for_text`, 4. matriz síntoma→código de la §3).
  Produce informe + próximo experimento único, nunca auto-reintento.
  **NO**: abrir/cerrar apps por sí mismo, cambiar ajustes, ni prometer
  causa sin `verify`.
- `navigate_and_copy` — **SÍ**: flujo portapapeles multi-pantalla
  genérico (tocar copiar → read-back en host por `dumpsys` o
  pegado-readback → verificar forma `https?://` → inyectar como payload
  opaco con `len`+hash en forense). Cita compuerta crítica si el destino
  comunica a terceros. **NO**: inventar contenido ante
  `CLIPBOARD_EMPTY`, ni transportar crudo sensible en el plan.
- `send_verified` — **SÍ**: flujo canónico de acción crítica
  (pre-rellenar por intent o UI → mostrar `preview` → exigir
  `confirm:true` del operador → ejecutar → verificar con lectura
  posterior → auditar quién confirmó qué). **NO**: ejecutar sin preview
  aprobado, ni reutilizar un `confirm` para un preview distinto, ni
  éxito declarado solo por el decisor (siempre `verify_final`
  determinista).

Ningún Prompt expone `shell`, coordenadas, ni atajos que salten
compuertas. Los tres citan la tabla §3 en su texto.

### 4.4 Stepper Canónico (el bucle de 4 pasos del carril UI)

El carril UI no es una secuencia libre de tools: es un **stepper de cuatro
pasos** que se repite hasta `DONE`, hasta un error honesto, o hasta escalar.
La secuencia es `1 → 2 → 3 → 4 → (1 | DONE | ESCALATE)`; el paso 1 nunca es
opcional tras un paso 4, porque la lectura del paso 4 *es* la observación del
siguiente paso 1.

1. **Observación Estructurada.** Tool `read_screen` (o `wait_for_text`).
   Entrega `{snapshot_id, tabla de candidatos}`. Nunca se actúa sin
   `snapshot_id` vigente; la tabla es la única representación que el modelo
   razona (los píxeles de `screenshot` son evidencia, no entrada de decisión).

2. **Vía rápida vs táctica.** `tap_text` (rápida: texto exacto e inequívoco,
   un dump interno) o el adaptador táctico del director `resolve_element`
   (**no** es una tool MCP: es `pkg/director.ResolveElement`, una `Choice`
   ciega sobre índices de la tabla). Si `resolve_element` cae en Fallback
   Soberano (`{ok:false, fallback_required:true, reason,
   recovery_instruction}`, error de Go nil), no se inventa el nodo: se vuelve
   al paso 1.

3. **Ejecución y Fallback Soberano.** `tap_node(node_id, snapshot_id)`,
   `type_text`, `scroll`, `press_back`. Exigen el `snapshot_id` del paso 1.
   `via` informa el camino ejecutado: `action_click` (preferida),
   `click_ancestor` (el clickable es un ancestro del nodo elegido), `gesture`
   (centro del nodo). `type_text` exige foco explícito (`NOT_FOCUSED`).

4. **Verificación de Estado.** `read_screen` o `wait_for_text`. Ninguna
   acción devuelve snapshot (AGENTS.md §6); un paso 4 sin el efecto esperado
   es verificación fallida, no un paso más: re-lee o escala. Cierre en `DONE`
   solo cuando el goal está cumplido y verificado; si no, `ESCALATE` con
   contexto.

**Nota de implementación (capa adaptadora).** El enriquecimiento de **glifos
confusables** (sufijo de rol para etiquetas de un solo carácter ambiguo:
dígitos que compiten con símbolos, signos, punto decimal) vive en una **capa
adaptadora del servidor** que se invoca al **componer la tabla que se envía
al modelo** —en `AskDecision` y `BuildResolveState`—, y **nunca** dentro del
serializador canónico de la tabla, que tiene paridad de bytes verificada por
golden (`pkg/normalizer/replay_expected.json`). Los índices **no** se
renumeran: la fila `k` sigue siendo la fila `k`. Ver
`docs/specs/tactical-robustness-p1p2.md §4`.

## 5. Modelo mental: las 5 preguntas del LLM (respuesta estándar)

Todo agente que dude debe poder responderse con exactamente estas
cinco, en orden. Si su situación no encaja, escala (`ESCALATE` /
pregunta al operador) en vez de improvisar.

1. **¿Dónde estoy y qué puedo usar sin tocar la pantalla?**
   Respuesta estándar: `device_status + get_foreground` primero; luego
   el carril nativo que responda al dato (batería, memoria,
   almacenamiento, ajustes, portapapeles-metadata, uso agregado…).
   La UI es el último recurso, no el primero.
2. **¿Mi vista está fresca?**
   Respuesta estándar: solo `read_screen` / `wait_for_text` dan
   `snapshot_id` vigente. Cualquier evento, mutación o espera lo
   caduca. `tap_node`/`type_text` con id viejo → `STALE_SNAPSHOT` →
   re-leo una vez y re-resuelvo; segundo fallo → `UI_UNSTABLE`, paro e
   informo con firma.
3. **¿Cómo toco sin romper nada?**
   Respuesta estándar: un paso = una primitiva sobre `node_id` vigente
   (`tap_node`), `ACTION_CLICK` si es clickable (el campo `via` lo
   confirma), gesto como fallback; `scroll` como máximo 2× sin cambio;
   después siempre verifico (`read_screen`/`wait_for_text`). Nunca
   coordenadas inventadas, nunca secuencias compuestas.
4. **¿Cómo escribo sin inventar?**
   Respuesta estándar: `type_text` es `REPLACE` sobre campo con foco
   vía `ACTION_SET_TEXT`. Sin foco → `NOT_FOCUSED` → tap, re-leo,
   escribo. El texto solo viene del goal, de la UI visible o del
   payload del nivel superior; sin texto dado, no escribo y escalo.
5. **¿Y si es crítico, falla o dudo?**
   Respuesta estándar: si es crítico/irreversible, la primera llamada
   planea (`planned:true, preview`) y solo ejecuto repitiendo con
   `confirm:true` tras aprobación explícita del operador sobre ese
   preview exacto. Si falla, sigo el `hint` literal (tabla §3). Si
   dudo (confianza baja, pantalla sin candidato útil, anomalía),
   no actúo: escalo con contexto (goal, pantalla, opciones, confianza)
   y espero guía. Dos corridas con igual firma terminal = no relanzo:
   dif de forenses + informe.

## 6. Aceptación (`@judge`, sin editar código)

1. El fichero existe en `docs/MCP_SPEC_GUIDELINES.md`, 100% genérico y
   sin keys: greps → vacío (salvo la línea histórica que documenta la
   prohibición):
   `grep -rniE 'whatsapp|contact_name|verify_chat|wrong_chat|api[_-]?key|sk-|su -c|exec\(.*su' docs/MCP_SPEC_GUIDELINES.md` → vacío
   (o solo la línea del presente punto).
2. Bloque §1 EN ≤ 400 palabras, sin paquetes/URLs/regex de dominio.
3. Toda tool citada en §2.3 nombra una alternativa exacta y ninguna
   promesa contradice `PROTOCOL.md` (sin post-snapshot, foco explícito,
   `planned:true`, 4 MiB, `SECURE_SURFACE` solo `screenshot`).
4. Todo código de `PROTOCOL.md §7` + los 10 de la consigna
   (`STALE_SNAPSHOT`, `NOT_FOCUSED`, `SHIZUKU_UNAVAILABLE`,
   `UNAUTHORIZED`, `METHOD_NOT_ALLOWED`, `INTENT_UNRESOLVED`,
   `PACKAGE_NOT_FOUND`, `CLIPBOARD_EMPTY`, `SELECTOR_NOT_FOUND`,
   `UI_UNSTABLE`) tiene fila en §3.2 con `hint` imperativo y política
   de reintento explícita.
5. §4 no implementa nada: ningún handler, URI registrada en código, ni
   schema nuevo; solo criterios SÍ/NO por capa para los 2 Resources y
   3 Prompts nombrados.
6. `tools/list` Python ≡ Go sigue idéntico (este documento es solo
   texto; no toca `mcp-server/` ni `cmd/`/`pkg/`).
