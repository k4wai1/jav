# Protocolo Multi-Agente — jev-android-mcp

> Complemento de `AGENTS.md`. En caso de conflicto, **`AGENTS.md` manda** y se
> enmienda primero. Este documento solo describe cómo se reparten los roles
> entre agentes de OpenCode para aislar contexto y evitar sobreoptimizar para
> una sola app.
>
> Config local: `opencode.json` (`default_agent: plan`) + `.opencode/agents/*.md`.
> Doble orquestador: `plan` nativo = gratuito Zen; `orchestrator` = pago DeepSeek
> directo (sin Zen). Subagentes siempre gratuitos Zen. Sin proveedores de pago
> salvo el orquestador DeepSeek.

## 1. Roles declarados

| Rol | Agente | Mode | Modelo | Edita | Bash |
|---|---|---|---|---|---|
| Orquestador pago | `orchestrator` | primary | `deepseek/deepseek-flash` (API directa) | solo `PLAN.md` (convención, sin `permission`) | — |
| Orquestador gratis | `plan` (nativo) | primary | `opencode/muse-spark-1.3-contributor-free` | `PLAN.md` | deny |
| Arquitecto | `architect` | subagent | `opencode/space-bunny-free` | `docs/**`, `*.md` | deny |
| Auditor/Explorer | `explorer` | subagent | `opencode/nemotron-3.5-lightning-free` | ninguno | grep/git read-only |
| Constructor | `coder` | subagent | `opencode/ling-3.1-flash-free` | libre | `uv`, `./gradlew` |
| Juez | `judge` | subagent | `opencode/nemotron-3.5-lightning-free` | ninguno | tests/lint |

Notas de mapeo (la propuesta original nombraba modelos inexistentes):
- `opencode/muse-spark-1.3-free` **no existe**; se usa
  `opencode/muse-spark-1.3-contributor-free`.
- `deepseek/deepseek-chat` **no existe** en `opencode models`; el orquestador
  pago usa `deepseek/deepseek-flash` (barato, verificado) o
  `deepseek/deepseek-v4-pro` (más capaz). Auth en `~/.local/share/opencode/auth.json`, nunca en el repo.
- La clave de frontmatter del schema estable es **`permission`** (singular),
  no `permissions`. El `orchestrator` de pago **no lleva bloque `permission`**:
  va directo a DeepSeek y el sandbox de Zen lo marcaba como cliente externo.
- `default_agent: plan` es el arranque gratuito; `orchestrator` se invoca
  explícito con `opencode --agent orchestrator`.

## 2. Reglas de contexto

- El Orquestador **nunca** procesa buffers de código completos; pide resúmenes a
  `@explorer` (rutas + líneas + resumen).
- Toda modificación técnica va precedida por un contrato en `docs/specs/`
  redactado por `@architect` y validado por `@judge`.
- Prohibida la lógica acoplada a aplicaciones particulares (WhatsApp u otras)
  dentro de los controladores de UI. Las tools MCP operan solo sobre primitivas:
  `get_node_hierarchy`, `tap_node`, `tap_point`, `input_text`, `swipe`,
  `keyevent`, `launch_app`, `get_foreground`, `screenshot`.
- Lectura de UI = accesibilidad (Accessibility/UIAutomator XML). La visión
  (`screenshot`) es evidencia/fallback, nunca la fuente primaria de coordenadas.

## 3. System 1 vs System 2

- **System 1 (MCP/local, determinista):** acciones reactivas inmediatas sobre
  selectores/`bounds` ya resueltos. Si el elemento existe y coincide, el servidor
  actúa sin razonamiento extra (`tap_node`, esperar teclado, `swipe`).
- **System 2 (orquestador):** planificación cognitiva multi-paso (abrir app,
  buscar contacto, redactar, enviar) sujeta a las compuertas deterministas de
  `AGENTS.md §5.14` (verificación de identidad/precondiciones antes de enviar).

## 4. Flujo operativo

1. La sesión arranca en `plan` (`default_agent`, gratis). Para pago:
   `opencode --agent orchestrator` (DeepSeek directo).
2. El Orquestador (`plan` o `orchestrator`) lee `PLAN.md`, elige la siguiente tarea y redacta la directiva.
3. `@architect` diseña el contrato en `docs/specs/<tool>.md`.
4. `@coder` implementa exactamente ese contrato (sin improvisar arquitectura).
5. `@judge` corre tests/lint y certifica; si falla, reporta sin editar.
6. El Orquestador actualiza `PLAN.md` con el estado real.

Invocación manual: `@architect`, `@explorer`, `@coder`, `@judge` desde el prompt.
Persistencia: al reabrir, el Orquestador solo relee `PLAN.md` + `AGENTS.md`,
sin arrastrar los miles de tokens que generan las subsesiones.
