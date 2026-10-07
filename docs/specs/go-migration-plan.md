# go-migration-plan — servidor MCP Python → Go (identidad Jav)

> Estado: **spec de migración v1 2026-10-07**. Redacta `@architect`,
> implementa `@coder`, certifica `@judge`. En conflicto, **AGENTS.md manda**.
>
> Alcance: solo el **servidor MCP host** (`mcp-server/` → módulo Go).
> La app Android (`android-app/`, paquete `dev.jev.jam`), `PROTOCOL.md`,
> y el loop Python congelado **no se tocan** en esta migración.
> 100% genérico: cero paquetes concretos, cero literales de dominio,
> cero keys en este documento.

## 0. Fuentes normativas leídas

- `mcp-server/src/jev_mcp/server.py` — 35 tools + docstrings ES 5 secciones
  (Descripcion / Parametros / Retorno / Permisos-Grants / Errores-gotchas).
- `socket_client.py` — `JamClient`: `hello` + `dump_ui` + `tap` +
  `get_foreground` + `wait_for_node` + `press_back/home` + `open_app` /
  `force_stop` + `screenshot` + `set_clipboard`.
- `ui_normalizer.py` — cadena 500 raw → ≤254 candidatos; filtro decoración,
  contenedores mudos fuera, rank editable > clickable-con-texto > resto,
  `MAX_CANDIDATES=254`, `HOLDS_MAX=140`, `PASSWORD_MARKERS` por categoría.
- `core/loop_helpers.py` — `MAX_TABLE=254`, `zone_of` 3×3 EN + `unknown`,
  `build_table` / `serialize_table` `[idx,class_short,zone,flags,label]`,
  `first_result` (listas densas, `DENSE_LIST_MIN=3`), `validate_target`,
  `check_decision_json`, `SENSITIVE_VERBS` genéricos, `confirm_input`,
  `screen_fingerprint`, `run_signature`.
- `jev_client.py` — S1 `ask` batch + `ask_decision` single-pass;
  `Choice/Noul/Score`, `validateChoice` estricta (probs dict completa,
  suma ±0.025, argmax eps 1e-6, conf finita [0,1]); `DECISION_ACTIONS`
  7 valores; timeout ~3 s + 1 retry; stub `{mock:true}` sin key.
- `s2_client.py` — **S2 SOLO OpenRouter** con la misma `OPENROUTER_API_KEY`
  que S1; modelo por env `S2_MODEL` (alias `GLM_MODEL`),
  default `z-ai/glm-5.3-flash`; comandos `OPEN_APP|TYPE|TAP|BACK|HINT` +
  plan `EXECUTE_GOAL` + `verify_done {achieved, evidence}`; validación
  `parse_command` / `parse_execute_goal` (`S2BadCommand`), vacío tras
  reintento → `S2EmptyResponse`; máscara PII rachas ≥5 dígitos; S2 nunca
  toca el dispositivo. Histórica: el provider DeepSeek-direct se eliminó;
  no se contempla en Go.
- `cost_tracker.py` — `track(model, in/out tokens) → USD`, línea `[COST]`;
  Jev `$0.042 in / $0.00 out` por MTok (normativo); S2 tasa configurable
  vía env `GLM_RATE_IN` / `GLM_RATE_OUT` (default = placeholder ajustable,
  nunca verdad oficial); overrides `JEV_RATE_IN` / `JEV_RATE_OUT`;
  `provider_cost` directo si no hay tokens; stub → `usd=0.0`.
- `director.py` + `tools/*.py` (`app`, `device`, `native`, `ui`,
  `clipboard`, `_base.py`) — fachada director-cliente + envolvente
  `{ok, verified, evidence, hint}` + auto-`adb forward` + hints por código.
- Contratos vivos: `docs/specs/generic-dual-tier.md` (v3 + addendum
  2026-10-06), `docs/specs/director-client.md`, `AGENTS.md §§1–9`.

## 1. Identidad y dependencias (fijadas por el operador)

- Identidad: binario **`jav`**, módulo **`github.com/k4wai1/jav`**.
- Libs permitidas: **`github.com/mark3labs/mcp-go`** (marco MCP stdio)
  + **`gorilla/websocket`** (transporte Jam WS). Stdlib para el resto
  (`net/http` para OpenRouter, `encoding/json`, `log/slog` a stderr,
  `os/exec` para `adb`).
- Prohibido en Go igual que en Python: nada app-específico en core,
  nada de `run_sequence`, nada de teclado simulado (solo `ACTION_SET_TEXT`
  vía Jam), nada de `shell` en dispositivo antes de Fase 6
  (`METHOD_NOT_ALLOWED` explícito del dispatcher Jam, no del MCP).
- Versión: `client_version` del `hello` = versión del binario Go
  (inyectada por `-ldflags -X main.version=…`, default `0.1.0`).

## 2. Estructura exigida

```text
go-mcp/                        # raíz NUEVA, hermana de mcp-server/ (no la sustituye aún)
  go.mod                       # module github.com/k4wai1/jav
  go.sum
  Makefile                     # build-all estático (ver §7)
  .env.example                 # ver §8 (sin secretos)
  cmd/jav/main.go              # entrypoint stdio ÚNICO (sin daemon, sin flags mutantes)
  pkg/jam/                     # JamClient Go (equiv. socket_client.py + _base.py)
  pkg/normalizer/              # normalizer + tabla/zone (equiv. ui_normalizer.py + loop_helpers puros)
  pkg/tools/                   # 35 handlers 1:1 (equiv. tools/*.py + director.py fachada)
  pkg/jev/                     # S1 ask/ask_decision + validateChoice (equiv. jev_client.py)
  pkg/director/                # resolver ciego + tap_idx + clipboard host (equiv. director.py + core/director_resolve + tools/clipboard host)
  pkg/cost/                    # CostTracker (equiv. cost_tracker.py + core/cost.py)
```

Reglas:

1. `cmd/jav` es delgado: lee env, configura logger a **stderr**, arranca
   servidor stdio, nada más. Cero lógica de dominio.
2. `pkg/jam` es el ÚNICO que habla WS con Jam. Nadie más abre sockets.
3. `pkg/normalizer` es puro (sin I/O, sin red, sin env): entra dump crudo,
   sale tabla. Testeable sin dispositivo.
4. `pkg/tools` son handlers finos: validan args JSON → llaman `pkg/jam` /
   host `adb` → envuelven `{ok, verified, evidence, hint}`.
5. `pkg/jev` + `pkg/director` + `pkg/cost` no tocan el dispositivo;
   solo HTTP OpenRouter (jev/director-S2) o cómputo puro.
6. El loop Python congelado (`loop.py`, decisor con goal global) **no se
   porta**: en Go solo vive el path director-cliente paso a paso
   (resolver ciego + primitivas atómicas). `run_goal` general queda
   fuera de esta migración hasta spec posterior.

## 3. Transporte: stdio primero

1. **Solo stdio en v1.** El binario `jav` habla MCP por stdin/stdout
   vía `mcp-go`. Sin TCP, sin SSE, sin daemon.
2. **Logs SOLO a stderr.** Nada —ni logs, ni `[COST]`, ni `[S2]`— va a
   stdout. `[COST]` y `[S2]` se emiten a stderr + forense/resultado
   (el forense JSONL lo escribe el cliente/director, no el servidor).
3. `stdout corrupto` = fallo crítico: cualquier byte fuera del framing
   JSON-RPC en stdout invalida la aceptación (§11).
4. `JAV_WS_URL` / `JAV_TOKEN` se leen del env del proceso stdio
   (heredado del cliente MCP). Sin `JAV_TOKEN` → las tools que exigen
   Jam fallan honesto `UNAUTHORIZED-hint`, nunca cuelgan.
5. Frame WS máximo **4 MiB** (`gorilla/websocket` read-limit); `screenshot`
   que exceda → `PAYLOAD_TOO_LARGE` con hint WebP q80 (igual que Python).

## 4. Protocolo MCP en Go

- `tools/list`: las 35 tools con **nombre, descripción y JSONSchema
  idénticos** a `server.py` (descripciones ES 5 secciones verbatim;
  ver §5). El operador difunde `tools/list` Python vs Go y exige
  igualdad de `name + schema` (descripciones: igualdad salvo formato).
- `tools/call → {content[], isError}`: cada handler devuelve la
  envolvente `{ok, verified, evidence, hint}` serializada como **un
  único `TextContent` JSON** en `content[0]`; `isError = !ok`.
  (`mcp-go`: `NewToolResultText(json) + IsError` según `ok`.)
- `initialize` + `tools/list` por stdio deben funcionar **sin Jam
  alcanzable** (sin `JAV_TOKEN`, sin `adb`): listan, no conectan.
  La conexión Jam es por llamada (dial + `hello` + método + close),
  con reintento único tras `adb forward` igual que `_base.py`.
- `hello` Jam: `{protocol_version:1, client_version:<jav>, token, client}`.
  Mismatch de protocolo → error claro con hint, nunca reintento mudo.
- Códigos de error Jam pasan intactos en `evidence.code`
  (`STALE_SNAPSHOT`, `NOT_FOCUSED`, `SELECTOR_NOT_FOUND`,
  `ACCESSIBILITY_DISABLED`, `SHIZUKU_UNAVAILABLE`, `TIMEOUT`,
  `SECURE_SURFACE`, `PAYLOAD_TOO_LARGE`, `METHOD_NOT_ALLOWED`, …)
  con el mismo mapa de hints que `_base.jam_fail`.

## 5. Mapeo 1:1 de las 35 tools (JSONSchema idéntico)

Tipos JSON: `string`, `integer`, `number`, `boolean`, `object`, `array`.
`required` = sin default en Python. Defaults entre paréntesis.

| # | tool | params (tipo, required) | notas Go |
|---|------|--------------------------|----------|
| 1 | `device_status` | — | `pkg/tools` → `jam.call("get_status"+foreground)`; scopes + app_version + foreground |
| 2 | `list_packages` | `filter:string ""` | host `adb shell pm list packages`; NO pasa por WS |
| 3 | `get_foreground` | — | `jam.call("get_foreground")` |
| 4 | `open_app` | `package:string REQ` | Shizuku `am start` + verify foreground; fallback `monkey`; nunca `su` |
| 5 | `close_app` | `package:string REQ` | `force_stop` + verify salida |
| 6 | `read_screen` | — | `dump_ui` + normalizer + tabla; `snapshot_id` monotónico; filtra decoración |
| 7 | `tap_text` | `text:string REQ` | atajo director (dump interno); preferir `tap_node` con snapshot fresco |
| 8 | `tap_node` | `node_id:string REQ, snapshot_id:integer REQ` | sin dump interno; `ACTION_CLICK` si clickable, si no gesture; sin post-snapshot |
| 9 | `type_text` | `node_id:string REQ, snapshot_id:integer REQ, text:string REQ` | `ACTION_SET_TEXT` REPLACE; exige foco (`NOT_FOCUSED` si no); sin taps implícitos |
| 10 | `scroll` | `direction:string "down" (up\|down\|left\|right), node_id:string\|null null` | sobre nodo scrollable opcional |
| 11 | `press_back` | — | `BACK` del enum |
| 12 | `press_home` | — | atajo director (no enum Jev) |
| 13 | `wait_for_text` | `text:string REQ, timeout_ms:integer 5000` | devuelve `node_id + snapshot_id` usable directo |
| 14 | `screenshot` | `fmt:string "png" (png\|webp), quality:integer 80 (0..100, solo webp)` | `takeScreenshot` API 30+ / `screencap`; `SECURE_SURFACE` ante `FLAG_SECURE` |
| 15 | `get_battery` | — | sin PII; `temp_c` opcional; `-1` si no reporta |
| 16 | `get_memory` | — | bytes |
| 17 | `get_storage` | `detail:string "basic" (basic\|fine)` | `fine` → `METHOD_NOT_ALLOWED` (N2) |
| 18 | `get_cpu` | `detail:string "basic" (basic\|fine)` | `usage_pct=-1` deliberado si SELinux; `fine` → N2 |
| 19 | `get_device_info` | — | sin IDs persistentes (nunca IMEI/MAC/serial/ANDROID_ID) |
| 20 | `settings_get` | `namespace:string "system" (system\|secure\|global), key:string REQ` | `FORBIDDEN` si restringida; `VALIDATION_ERROR` si ns/key mal |
| 21 | `settings_put` | `namespace:string "system", key:string REQ, value:string REQ, confirm:boolean REQ-sensible*` | sin confirm → `{planned:true, preview{value_sha256}}`; System exige `confirm:true` + scope admin; Secure/Global → N2 |
| 22 | `open_url` | `url:string REQ (://…), package:string ""` | `via=startActivity\|startActivity-package\|shizuku-am`; chooser si `package=""` y >1 handler |
| 23 | `send_intent` | `action:string REQ, uri:string "", package:string "", mime:string "", confirm:boolean false, extras:object[str,str] null` | crítica (SEND/CALL/…) sin confirm → `planned`; nunca finge envío headless |
| 24 | `get_clipboard_device` | — | nunca crudo: `{len, sha256, via}`; background/vacío → `CLIPBOARD_EMPTY` |
| 25 | `get_app_usage` | `hours:integer 24 (1..24, 1..168 con raw), window:string\|null null (today\|week\|raw\|None)` | solo agregados top 50, ms Unix |
| 26 | `list_contacts` | `query:string "", limit:integer 50 (1..100), offset:integer 0, with_phone:boolean false` | forense conteos/hashes, sin PII cruda |
| 27 | `add_contact` | `display_name:string REQ, phone:string "", email:string "", confirm:boolean false` | crítica: sin confirm → `planned` |
| 28 | `list_events` | `time_min:integer 0 (ms Unix, 0=ahora), time_max:integer 0 (0=min+7d), calendar_id:integer 0, include_location:boolean false` | ventana máx 7 días |
| 29 | `create_event` | `title:string REQ, start_ms:integer REQ, end_ms:integer REQ, calendar_id:integer 0, description:string "", confirm:boolean false` | crítica: sin confirm → `planned` con `title_sha256` |
| 30 | `list_notifications` | — | ≤50, título/texto ≤200 chars; `NOTIFICATION_LISTENER_DISABLED` si no hay listener |
| 31 | `reply_notification` | `key:string REQ, text:string REQ, confirm:boolean false` | crítica: sin confirm → `planned` con `text_sha256` |
| 32 | `media_state` | — | ≤10 sesiones; monta grant del listener |
| 33 | `media_control` | `action:string REQ (play\|pause\|next\|prev\|stop), package:string "", confirm:boolean false` | `stop` sin confirm → `planned` |
| 34 | `get_location` | `timeout_ms:integer 8000 (ms, ≤30000), max_age_s:integer 300 (s, ≤3600)` | ojo unidades mixtas; forense hash; nunca inventa |
| 35 | `take_photo` | `confirm:boolean false, camera:string "back" (back\|front)` | **siempre** exige `confirm:true`; sin ella → `planned`; FGS visible con indicador |

\* `confirm` es `false` por defecto en firma pero normativamente
obligatorio para ejecutar; el spec de cada tool (§5 filas 21/23/27/29/
31/33/35) define el régimen `planned:true, verified:false` sin confirm.

## 6. Paquetes Go (responsabilidades)

### 6.1 `pkg/jam` (equiv. `socket_client.py` + `tools/_base.py`)

- `Dial(url, token)`: WS con límite 4 MiB, `hello` plano
  (`protocol_version:1`), guarda `scopes` + `app_version`.
- Métodos 1:1: `DumpUI, Tap(selector), GetForeground, WaitForNode,
  PressBack, PressHome, OpenApp, ForceStop, Screenshot(fmt,q),
  SetClipboard, Call(method,params)` genérico para el carril native
  (batería/memoria/… pasan por `Call`, igual que `native._jam_call`).
- `EnsureForward()`: `adb forward tcp:38472 tcp:38472` + 1 reintento
  ante `connection refused` (solo si la URL es loopback).
- Mapeo `JamError{code} → hint` idéntico a `jam_fail`.
- Sin `su`, sin shell al dispositivo; `shell` ni siquiera existe como
  método (el dispatcher Jam lo rechaza; el MCP no lo expone).

### 6.2 `pkg/normalizer` (equiv. `ui_normalizer.py` + `loop_helpers.py` puro)

- Constantes idénticas: `MaxCandidates=254`, `MaxTable=254`,
  `DecorSubstr=(statusBarBackground, navigationBarBackground)`,
  set de contenedores, `PasswordMarkers` por categoría,
  `HoldsMax=140`, `DenseListMin=3`, `ZoneValues` 9 EN + `unknown`,
  `FastActions`, `SensitiveVerbs` genéricos, `InputTimeout/Poll`,
  `ProbSumTol=0.025`, `ArgmaxEps=1e-6`, `TAU=0.70` (el TAU vive aquí
  como constante documentada; el loop futuro la consume).
- Funciones puras: `Normalize(dump, limit, w, h)`, `BuildTable`,
  `SerializeTable → [idx,class_short,zone,flags,label]`, `ZoneOf`,
  `FirstResult`, `ValidateTarget`, `CheckDecisionJSON`,
  `FocusedFieldView`, `PrepareInputVerification`, `InputMatches`,
  `ScreenFingerprint`, `BuildRunSignature/SameSignature`, `IsSensitive`.
- La decoración del sistema se filtra aquí, no en el extractor (§5.10).

### 6.3 `pkg/tools` (equiv. `tools/*.py` + `server.py` registro)

- Un handler por tool (§5). Validación de args en Go antes de dial
  (enums `direction/fmt/detail/action/camera`, rangos `quality/hours/
  timeout_ms/max_age_s/limit/offset`, forma `package a.b.c`, forma
  `url ://`, ventana calendario ≤7 días).
- `read_screen` expone `package, activity, snapshot_id, raw_count,
  screen_height/width (cache `wm size`), focused_field, first_result,
  candidates[], render`.
- Acciones no devuelven snapshot; `tap_node/type_text` exigen
  `snapshot_id` (`STALE_SNAPSHOT` si rotó).
- `list_packages` y clipboard-host (`dumpsys`) corren `adb` en el
  **host**, nunca vía Shizuku-`shell`.

### 6.4 `pkg/jev` (equiv. `jev_client.py`)

- `Ask(state, questions) → (answers, usage)`: `POST
  https://openrouter.ai/api/alpha/decisions`, modelo por env `JEV_MODEL`
  (default `typesafe/jev-1.13`), timeout ~3 s + 1 retry, headers
  `Authorization: Bearer` + `HTTP-Referer` + `X-Title: jam-loop`.
- `AskDecision(goal, table, snapshotID, …)` single-pass EN con las 3
  preguntas cerradas (`action` 7 valores, `target` 0..253+NONE, `noul`
  `needs_system_2`); tabla serializada `[idx,class_short,zone,flags,
  label]`; cabecera `current_app + screen_goal (+operator_verbatim) +
  first_result + focused_field{label,holds} + history + s2_guidance`.
- `ValidateChoice` estricta idéntica (dict, choice ∈ criteria, probs
  dict completa, conf/probs finitas [0,1], suma ±0.025, argmax);
  `conf = min(action.conf, target.conf)` finita o hallucination.
- Sin key → stub `{mock:true}` (primera fila si TAP), nunca actuar con
  clave fuera de criteria (`JevHallucination`).

### 6.5 `pkg/director` (equiv. `director.py` + `core/director_resolve.py` + clipboard host)

- `ResolveElement(descriptionEN, table, snapshotID, …)`: UNA Choice
  ciega al goal global (solo `screen_goal + current_app + snapshot +
  table + first_result`); anti-poisoning: el goal global jamás entra.
- `TapIdx(idx, snapshotID, candidates)`: `by_idx[idx] → node_id` +
  `validate_target` + `tap_node`; sin candidates re-observa UNA vez y
  exige snapshot igual o `STALE_SNAPSHOT`.
- `ReadScreenState / GetClipboard(host dumpsys + forma https?://) /
  SetClipboard(Jam ClipboardManager + read-back de forma)`.
- `Advise/CompileGoal/VerifyDone` (forma S2 §5.1 + plan + verify) viven
  aquí o en `pkg/jev` —el spec fija que compartan `OPENROUTER_API_KEY`
  y `S2_MODEL`/`GLM_MODEL`; la ubicación interna la elige `@coder`
  siempre que `tools/list` no cambie. Solo OpenRouter; sin provider
  alternativo en v1.

### 6.6 `pkg/cost` (equiv. `cost_tracker.py`)

- `Track(model, inTok, outTok, step?, tier s1|s2, providerCost?) → USD`;
  fórmula `in/1e6*rate_in + out/1e6*rate_out`; `provider_cost` si el
  proveedor devolvió coste sin tokens (`source=provider|computed`).
- Tarifas: Jev `0.042/0.0` normativo con overrides `JEV_RATE_IN/OUT`;
  S2 **solo** vía `GLM_RATE_IN/OUT` (defaults = placeholder ajustable
  contra factura, nunca verdad oficial); `rates_for(model)` resuelve
  en vivo; `RATES` inicial solo foto a import-time.
- Línea `[COST] provider=openrouter model=… in=… out=… usd=… step=…
  run=… src=…` a **stderr** (no stdout), más acumulado
  `jev_cost/s2_cost/total_cost/steps`.

## 7. Makefile build-all estático

- Target `build-all`: `CGO_ENABLED=0 go build -trimpath
  -ldflags "-s -w -X main.version=<ver>"` para
  `linux/amd64`, `linux/arm64`, `darwin/arm64`, `windows/amd64`
  (`.exe` en windows). Salida `dist/jav-<os>-<arch>[.exe]`.
- Targets `build` (host), `test` (`go test ./...`), `vet`,
  `tools-list-diff` (compara `tools/list` Go vs Python, ver §11).
- Toolchain Go fijada en `go.mod` (`go >= 1.22`); `go.sum` commiteado;
  sin `cgo`, sin tags exóticos. Documentar cada build real en
  `docs/BUILD.md` (comando, tiempo, RAM) según `AGENTS.md §7`.

## 8. `.env.example` (sin secretos, solo forma)

```text
# Transporte MCP → Jam
JAV_WS_URL=ws://127.0.0.1:38472/
# Remoto opt-in (WSS obligatorio fuera de loopback):
# JAV_WS_URL=wss://100.64.x.x:38472/
JAV_TOKEN=
# S1 + S2 (misma key OpenRouter):
OPENROUTER_API_KEY=
JEV_MODEL=typesafe/jev-1.13
S2_MODEL=z-ai/glm-5.3-flash
# Tasas S2 (placeholder ajustable contra factura, nunca oficial):
# GLM_RATE_IN=0.15
# GLM_RATE_OUT=0.50
# Overrides S1 (defaults 0.042 / 0.0):
# JEV_RATE_IN=0.042
# JEV_RATE_OUT=0.0
# Forense del director (lo escribe el cliente, no el servidor):
JAV_LOG_DIR=logs/
```

Notas: `JAV_*` sustituye a `JEV_WS_URL/JEV_TOKEN` heredados (el Go lee
`JAV_WS_URL` con fallback `JEV_WS_URL`; `JAV_TOKEN` con fallback
`JEV_TOKEN`); `OPENROUTER_MODEL`/`TYPESAFE_*`/`JEV_CERT_FINGERPRINT`
heredados **no** se portan (TLS tailnet = fase posterior); `S2_MODEL`
manda sobre `GLM_MODEL`.

## 9. Ejemplos de registro MCP (clientes)

`opencode.json` (host Linux, stdio):

```json
{
  "mcp": {
    "jav": {
      "type": "local",
      "command": ["$HOME/jev-android-mcp/go-mcp/dist/jav-linux-amd64"],
      "enabled": true,
      "environment": {
        "JAV_WS_URL": "ws://127.0.0.1:38472/",
        "JAV_TOKEN": "",
        "OPENROUTER_API_KEY": "",
        "JEV_MODEL": "typesafe/jev-1.13",
        "S2_MODEL": "z-ai/glm-5.3-flash",
        "JAV_LOG_DIR": "logs/"
      }
    }
  }
}
```

`claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "jav": {
      "command": "/home/user/jev-android-mcp/go-mcp/dist/jav-linux-amd64",
      "env": {
        "JAV_WS_URL": "ws://127.0.0.1:38472/",
        "JAV_TOKEN": "",
        "OPENROUTER_API_KEY": "",
        "S2_MODEL": "z-ai/glm-5.3-flash"
      }
    }
  }
}
```

Cursor (`~/.cursor/mcp.json` o `.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "jav": {
      "command": "/home/user/jev-android-mcp/go-mcp/dist/jav-linux-amd64",
      "env": {
        "JAV_WS_URL": "ws://127.0.0.1:38472/",
        "JAV_TOKEN": "",
        "OPENROUTER_API_KEY": "",
        "JEV_MODEL": "typesafe/jev-1.13",
        "S2_MODEL": "z-ai/glm-5.3-flash",
        "JAV_LOG_DIR": "logs/"
      }
    }
  }
}
```

Todos con valores vacíos donde va secreto; el operador rellena en su
fichero local (nunca commiteado, `chmod 600`).

## 10. Convivencia Python intacto hasta el reemplazo

1. `mcp-server/` **no se modifica** en esta migración (ni código, ni
   `pyproject`, ni tests). El loop Python congelado no se toca.
2. `go-mcp/` es directorio **nuevo y hermano**; cero imports cruzados.
3. Durante la convivencia solo **un** servidor está registrado como
   `jav`/`jam` en cada cliente; el otro queda deshabilitado o con
   nombre distinto (`jam-py` vs `jav-go`) para el diff `tools/list`.
4. El reemplazo se declara solo cuando §11 está verde; hasta entonces
   Python sigue siendo el servidor de referencia y Go el candidato.
5. `tasks/` sigue eliminado; `scripts/fase5_check.py` y
   `tests/test_guards.py` rotos siguen siendo deuda de `@coder` en
   Python y no entran en Go.

## 11. Aceptación (`@judge`, sin editar)

Desde `go-mcp/` (+ referencia `mcp-server/`):

1. `go build ./...` limpio + `go vet ./...` limpio, sin warnings.
2. `initialize + tools/list` por stdio con stdout puro JSON-RPC:
   captura stdout a fichero y `jq` lo parsea sin errores; **cero
   líneas de log en stdout** (todo log en stderr).
3. `tools/list` Go ≡ Python: mismo set de 35 nombres + mismos
   `required` y tipos por tool (script `tools-list-diff`, diff vacío).
4. `uv run pytest` en `mcp-server/` sigue **verde** (Go no rompió Python).
5. Smoke `device_status` sin Jam → `{ok:false,…}` honesto con hint
   (no cuelgue, no pánico, exit del servidor limpio).
6. Greps en `go-mcp/`: nada app-específico, nada de keys, nada de `su`
   (`grep -rniE 'whatsapp|contact_name|verify_chat|wrong_chat|api[_-]?key|sk-|su -c|exec(.*su' --include='*.go' .` → vacío salvo la línea
   histórica de este spec que documenta la eliminación de DeepSeek-direct).

## 12. No-objetivos explícitos

- Sin `run_goal` en Go (solo primitivas + resolver director).
- Sin WSS/tailnet/cert-pinning en v1 (solo loopback `ws://`); el bind
  no-loopback con `WSS obligatorio` queda para fase posterior.
- Sin `shell` al dispositivo, sin `su`, sin `ROOM/Compose/Hilt`
  (esto último es app Android, no Go, y sigue prohibido).
- Sin daemon, sin `run_sequence`, sin teclado simulado, sin reintento
  `STALE_SNAPSHOT` dentro de la app (el reintento vive en el
  director/loop, una sola vez).
- Sin telemetría, sin IDs persistentes, sin PII cruda en logs
  (hashes/conteos/longitudes como en Python).
