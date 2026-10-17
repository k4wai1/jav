# tool-consolidation-experiment — medir antes de consolidar 38 → ~24 tools

> Estado: **spec de experimento 2026-10-16** (no implementa nada). Redacta
> `@architect`, ejecuta el corpus `@coder`, certifica `@judge`. En conflicto,
> **AGENTS.md manda**.
>
> Fuentes leídas: `cmd/jav-tokens/main.go` (medición con tiktoken real),
> `cmd/audit-mcp/main.go` (checks `tools-count-38`, `tools-schema`,
> `tools-affordances`, `token-budget-startup`), `pkg/tools/catalog.go`
> (`CompactDesc`/`FullToolDocs`), `pkg/tools/register.go`,
> `docs/benchmarks/PERFORMANCE.md §9`, `docs/BUILD.md §25`, `AGENTS.md`
> (enmienda v1.2.2 + "no consolidar sin el experimento medido").
>
> 100 % genérico: cero paquetes concretos, cero literales de dominio.

## 0. Contexto y verdad operativa

`cmd/jav-tokens` (v1.2.2) mide el arranque con un tokenizer **real**
(`tiktoken`, `cl100k_base`), no con el proxy `bytes/4` de `cmd/audit-mcp`:

| Plano | Tokens (real) |
|---|---|
| `instructions` | 385 |
| `tools/list` (38 tools, payload completo) | 3 166 |
| **carga cognitiva** (instructions + Σ descripciones) | **1 783** |
| **total arranque** (instructions + tools/list) | **3 551** |

**Hecho que motiva este experimento:** 38 tools ya cuestan **3 551 tokens** de
payload en `tools/list` (esquema MCP fijo incluido). La hipótesis de consolidar
a ~24 tools con `kind`/`action` **podría** bajar tokens, pero:

1. **Renombrar/consolidar tools rompe contratos vivos** (§1): `audit-mcp`,
   forenses históricos, README, PROTOCOL, descripciones y `jav-e2e`.
2. **Consolidar empeora la precisión de selección** en al menos un caso
   conocido: un subcomando dentro de un schema (p. ej. `settings(kind=…)`) es
   más ambiguo para el modelo que una tool separada con nombre propio.
3. `bytes/4` **no es** la métrica de decisión: hay que medir tokens reales
   (`jav-tokens`) **y** precisión de selección (cliente MCP real).

**Regla vinculante:** este documento **no autoriza** ninguna consolidación. Solo
autoriza medir. La consolidación se implementa **únicamente** si el §6 da
resultado positivo, y **solo** en los grupos que ganen.

## 1. Alcance y blast radius

### 1.1 Lo que el experimento NO toca
- **Nombres de tools existentes** (renombrar es el costo dominante, ver 1.2).
- `loop.py` / Director: **congelado por diseño** (AGENTS v1.2.2). Ni se abre.
- No se añaden tools nuevas (`verify_state`, `tap_point`, …) en esta fase.

### 1.2 Costo de consolidar (a cuantificar, no a minimizar)
Si un grupo se consolida `X_get`+`X_put` → `X(kind)`, se rompen, como mínimo:

| Superficie | Qué cambia | Verificable en |
|---|---|---|
| `audit-mcp` | `tools-count-38` | `cmd/audit-mcp/main.go` |
| `audit-mcp` | `tools-schema`, `tools-affordances` (≤3 palabras en desc) | idem |
| `PROTOCOL.md` | mapeo tool↔método WS | `PROTOCOL.md` |
| `README.md` | tabla de grupos + "38 tools" (EN/ES) | `README.md` |
| `pkg/tools/catalog.go` | `CompactDesc` + `FullToolDocs` | `pkg/tools/` |
| `jav-e2e` | llamadas por nombre | `cmd/jav-e2e/main.go` |
| Forenses `logs/run-*.jsonl` | nombres históricos (no se reescriben) | `docs/benchmarks/TASK_HISTORY.md` |

El experimento **debe reportar** este costo por grupo antes de cualquier decisión.

## 2. Corpus (≥20 goals genéricos, sin apps concretas)

Los goals describen **intención**, nunca una app ni un contacto. El corpus es
fijo y versionado con el spec.

| # | Goal | Carril / tool esperada (brazo A) |
|---|---|---|
| 1 | What is the battery level? | N0 `get_battery` |
| 2 | Open the settings app | N0 `open_app` |
| 3 | Read the current screen | UI `read_screen` |
| 4 | Take a screenshot and save it | UI `screenshot` |
| 5 | Send a short text to a contact | UI `type_text`/`tap_text` |
| 6 | Set the screen brightness to 50% | N1 `settings_put` |
| 7 | Read the current screen brightness | N1 `settings_get` |
| 8 | List installed packages containing 'firefox' | N0 `list_packages` |
| 9 | What app is in the foreground? | N0 `get_foreground` |
| 10 | Copy the current URL to the clipboard | N0 `get_clipboard_device` |
| 11 | List the last 5 notifications | N1 `list_notifications` |
| 12 | How much storage is free? | N0 `get_storage` |
| 13 | How much memory is in use? | N0 `get_memory` |
| 14 | What is the CPU load? | N0 `get_cpu` |
| 15 | Which Android/SDK version is this device? | N0 `get_device_info` |
| 16 | Open this URL | N1 `open_url` |
| 17 | Pause the currently playing media | N1 `media_control` |
| 18 | What media is playing? | N1 `media_state` |
| 19 | Add a calendar event for tomorrow 10am | N1 `create_event` |
| 20 | List my upcoming events | N1 `list_events` |
| 21 | Add a contact named 'Alex' | N1 `add_contact` |
| 22 | Find the search icon on the current screen | UI `resolve_element` |
| 23 | Scroll down one page | UI `scroll` |
| 24 | Go back | UI `press_back` |
| 25 | Reopen the last audit entries | admin `get_audit` |
| 26 | Run the shell command `id` | N2 `adb_shell` (grant) |

**Aceptación del corpus:** ≥20 goals (aquí 26). Ningún goal fija una app como
**target de acción** (p. ej. nunca "abre WhatsApp"); los strings de búsqueda
(p. ej. `'firefox'` en #8) son **datos de la consulta**, no un objetivo de
manipulación. `@judge` verifica que no hay literales de dominio accionables.

## 3. Brazos

| Brazo | Configuración | Tools en `tools/list` |
|---|---|---|
| **A (actual)** | 38 tools separadas | 38 |
| **B (consolidado)** | grupos candidatos con `kind`/`action` | ~24 |

### 3.1 Agrupaciones candidatas (hipótesis, no decisión)

| Grupo candidato | Desde | Hacia (ejemplo) |
|---|---|---|
| settings | `settings_get`, `settings_put` | `settings(kind=get\|put)` |
| contacts | `list_contacts`, `add_contact` | `contacts(kind=list\|add)` |
| calendar | `list_events`, `create_event` | `calendar(kind=list\|create)` |
| media | `media_state`, `media_control` | `media(kind=state\|control)` |
| device stats | `get_battery`, `get_memory`, `get_storage`, `get_cpu` | `device_stats(kind=…)` |

**No** se consolidan (candidatos a **mantener separadas** por riesgo de
precisión): las UI críticas (`read_screen`, `tap_node`, `type_text`) y las de
efecto sensible (`take_photo`, `adb_shell`, `reply_notification`) — su nombre
propio es parte de la compuerta de seguridad.

## 4. Métricas

1. **Tokens (real):** tokens del `tools/list` de cada brazo, con
   `cmd/jav-tokens` (`cl100k_base`). Se reportan la **carga cognitiva** y el
   **total arranque** por separado.
2. **Precisión de selección (1 intento):** para cada goal del §2, ¿el cliente
   MCP real (OpenCode) elige la tool correcta **en el primer intento**, sin
   correcciones? Se mide sobre el brazo A y el brazo B por separado.
   - Correcto = la primera `tool_call` corresponde al carril/tool esperado del §2
     (para B, vale la tool consolidada con el `kind` correcto).
   - Se exige registrar el `tool_call` crudo (nombre + args) por goal.
3. **Latencia de la primera tool call:** ms hasta la primera llamada emitida por
   el modelo (proxy de "facilidad de elección").

## 5. Protocolo reproducible

```bash
make build                                     # binario jav v1.2.2
make tokens                                    # arm A: carga cognitiva/total
# Brazo B (cuando exista un build de prueba, fuera de este spec):
#   make tokens con el binario consolidado
```

- **Precisión:** correr el corpus §2 contra OpenCode apuntando al `jav` de cada
  brazo, **N=3 repeticiones** por goal; reportar aciertos en 1 intento.
- **Aislamiento:** fijar modelo, versión de cliente y temperatura; un solo
  cambio entre brazos (el `tools/list`).
- **Evidencia:** tabla por goal (tool elegida, correcto sí/no, latencia_ms) +
  resumen. Sin PII: nunca contenido de UI/contactos; solo nombres de tool y
  args estructurales.

## 6. Criterio de decisión (vinculante)

Comparando **B** contra **A**, sobre **el mismo corpus y cliente**:

| Resultado | Decisión |
|---|---|
| Tokens bajan **>30 %** **y** precisión cae **≤5 %** | **Consolidar** (solo los grupos que aporten) |
| Tokens bajan **<15 %** **o** precisión cae **>10 %** | **No consolidar** |
| Cualquier otro caso (zona intermedia / empate) | **Mantener A** |

- Se decide **por grupo**, no en bloque: consolidar `settings` no obliga a tocar
  `calendar`.
- **Política de tokens (fijada):** el objetivo histórico **≤3000 tokens** aplica
  a la **carga cognitiva** (instructions + Σ descripciones), que es lo que el
  modelo "lee" antes de decidir. El **total con esquema MCP fijo** (3 551 hoy)
  es overhead estructural y **no** cuenta contra el objetivo.

## 7. Entregables y aceptación (`@judge`)

1. Tabla de tokens (A vs B, carga cognitiva y total) medida con `jav-tokens`.
2. Tabla de precisión de selección (A vs B, ≥20 goals, N=3).
3. Tabla de latencia de la primera tool call (A vs B).
4. **Decisión motivada** por grupo (§6) + costo de migración (§1.2) si aplica.
5. Corpus §2 sin literales de dominio accionables (grep-verificado).

**Aceptación:** corpus ≥20 goals; métricas **medidas, no estimadas** (`@judge`
re-ejecuta `make tokens` y revisa la evidencia de precisión); decisión explícita.
**Nada de código de consolidación** en este entregable.
