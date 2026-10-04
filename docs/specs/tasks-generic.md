# tasks-generic — desacoplar core MCP del ejemplo WhatsApp

> Contrato Fase 4 (PLAN.md). Redacta `@architect`, implementa `@coder`,
> certifica `@judge`. En conflicto, **AGENTS.md manda** (§5.14-16,
> forense, System1 vs System2 en AGENTS-MULTIAGENT.md §2-3).
> Estado actual verificado por `@explorer`: core ya genérico
> (`loop.py`, `server.py`, `tools/*.py`, `state.py`, `ui_normalizer.py`
> sin literales de app); acoplamiento solo en
> `mcp-server/src/jev_mcp/tasks/whatsapp.py:20` (`WA`, `PHASES`,
> predicados, `find_chat_title`, `ensure_open`/`go_home`/`send_whatsapp`).

## 1. Principio: primitivas agnósticas

1. El MCP expone **solo primitivas agnósticas** (nombres MCP ↔ método Jam):
   `open_app(package)`↔`open_app`, `close_app`↔`force_stop`,
   `read_screen`↔`dump_ui`+normalizar (`get_app_state`),
   `get_foreground`↔`get_foreground`, `tap_node`↔`tap_node`,
   `tap_text`↔`tap` (legado, preferir `tap_node`), `type_text`↔`type`,
   `scroll`↔`scroll`, `press_back`/`press_home`, `wait_for_text`↔`wait_for_node`,
   `screenshot`↔`screenshot`, `list_packages`, `device_status`.
   Equivalencia conceptual con el vocabulario de PLAN.md §Principios:
   `get_node_hierarchy`=`read_screen`, `tap_point`≈`tap_text`,
   `input_text`=`type_text`, `swipe`=`scroll`, `keyevent`=`press_back/home`,
   `launch_app`=`open_app`.
2. **Cero literales de app en core.** Prohibido en
   `loop.py`, `server.py`, `tools/`, `state.py`, `ui_normalizer.py`,
   `core/` (nuevo, §3): nombres de paquete (`com.whatsapp`, …),
   nombres de contacto (`Felix`, …), `resource_id` concretos
   (`contact_name`, `conversation_*`, `entry`, …), regex de UI
   (`busca|mensaje|enviar|send`, …), títulos, textos de prueba.
3. Regla de fallo: **si una prueba falla en una app, se cuestiona
   arquitectura o gestión de Jev (preguntas/criterios/compuertas),
   nunca se hardcodea la app en core.** El fix vive en el plugin
   de tarea (`tasks/<app>.py`) o en un helper genérico parametrizado.
4. System1 vs System2 (AGENTS-MULTIAGENT.md §3): System1 (MCP/local,
   determinista) = `core/` + Jam (filtros, guards, verificación).
   System2 (orquestador/Jev) = planifica dentro de `questions`/`criteria`.
   Las compuertas de envío (§5.14-16: identidad estricta, blacklist,
   precondiciones deterministas, `VERIFY_CHAT`, dry-run, forense
   `logs/run-<ts>.jsonl`) son **obligatorias** y viven mitad en core
   (mecanismo) mitad en plugin (datos).

## 2. TaskProtocol (lo que `loop.run` exige)

El loop (`loop.py`: `observe→questions→ask→interpret→_execute→verify_final`,
enum `tap_node|type_text|scroll|done|abort|noop`, `dry_run` + `is_sensitive`,
`STALE_SNAPSHOT×3→UI_UNSTABLE`, forense JSONL por paso) solo acepta
tareas que implementen este protocolo. Firmas exactas:

```python
class TaskProtocol:
    PHASES: tuple[str, ...]   # p.ej. ("SEARCH", "PICK", "VERIFY_CHAT", ...)
    phase: int                # índice actual en PHASES; el avance lo decide
                              # la tarea en interpret(), el loop solo lo lee
                              # para el forense (asked vs self.phase, §5.14.3)

    async def observe(self) -> dict:
        """Estado fresco: {package, activity, snapshot_id, candidates[],
        screen_height, [error, error_text]}. Sin mutar dispositivo salvo
        reintentos de lectura."""

    def questions(self, state: dict, history: list) -> dict:
        """Preguntas Jev para la fase actual (+ base last_ok/progress).
        Solo describe; no actúa."""

    def interpret(self, answers: dict, state: dict, history: list) -> dict:
        """Jev→acción cerrada: {kind: tap_node|type_text|scroll|done|abort|noop, ...}.
        Aquí viven el avance de fase y las compuertas deterministas.
        Clave fuera de criteria → JevHallucination."""

    async def verify_final(self, state: dict) -> tuple[bool, dict]:
        """Verificación final determinista (re-lee pantalla). Nunca solo-Jev.
        (ok, evidence)."""

    def is_sensitive(self, action: dict) -> bool:
        """True = dry_run la planea sin ejecutar (p.ej. tap de enviar)."""
```

Invariantes (AGENTS.md §5.13-16, ya en `loop.py`, no redefinir):
`noop` para fases de solo-verificación; `type` exige foco (`NOT_FOCUSED`
si no, tap previo explícito del cliente); acciones no devuelven snapshot
(el cliente verifica con `read_screen`/`wait_for_text`); `snapshot_id`
monotónico exigido en `tap_node`/`type_text`.

## 3. Helpers genéricos a extraer a `core/` (sin rastro de app)

Nuevo paquete `mcp-server/src/jev_mcp/core/` (puro, sin I/O salvo
lo indicado). Todo parametrizado; **nada de `com.whatsapp` ni `Felix`**:

```python
# core/text_match.py
def norm(s: str) -> str: ...            # NFKD→ascii→lower
def skeleton(s: str) -> str: ...        # norm sin [aeiou\s]
def name_hit(needle: str, cand: dict) -> bool:
    """Tolerante (Felix≈Félex/FELIX/felex): palabra len>2 en norm(text+desc)
    o skeleton len>=3 contenido. `needle` y `cand` son parámetros."""
def title_matches_strict(expected: str, title: str) -> bool:
    """Igualdad norm, o expected+apellido-simple / expected+(paréntesis).
    Ante la duda False."""

# core/guards.py
FORBIDDEN_DEFAULT: str  # r"reenviar|forward|compartir|share|eliminar|delete|borrar"
def is_forbidden(cand: dict, pattern: str = FORBIDDEN_DEFAULT) -> bool: ...
def check_stuck_same(action: dict, history: list, n: int = 2) -> dict | None:
    """Si (kind,node_id) == últimas n → abort STUCK_SAME. Puro."""
def require_verified(verified: bool, key: str, code: str) -> dict | None:
    """Si no verificado → abort {code} (NO_VERIFY/SEND_UNSAFE/...). Puro."""
def guarded_action(key: str, cands: dict, snap: int, *,
                   forbidden: bool) -> dict | None:
    """Valida clave tap:/type:/done/abort contra cands+snapshot.
    FORBIDDEN_TARGET / JevHallucination. Puro."""

# core/titles.py
def find_title(state: dict, expected: str, *,
               rid_keys: tuple[str, ...], top_frac: float = 0.15) -> dict | None:
    """Título que matchea estricto: 1º por rid_keys (sufijos), 2º por
    franja superior (bounds.top < screen_height*top_frac). El plugin pasa
    sus rid_keys; core no conoce ninguno."""
def has_any_title(state: dict, *,
                  rid_keys: tuple[str, ...], top_frac: float = 0.15) -> bool: ...
```

Zona gris resuelta: `norm`/`skeleton`, guard `STUCK_SAME`, `find_title`
(`rid_keys`, `top_frac`), `_action_for` (compuertas) **sí van a core**
como mecanismos parametrizados. Los **datos** (lista `rid_keys` de cada
app, regex de cada predicado, `PACKAGE`, `PHASES`) quedan en el plugin.

## 4. `tasks/whatsapp.py` → plugin de ejemplo

- Implementa `TaskProtocol` (`SendWhatsappTask(contact, text)`), sin
  cambiar su comportamiento externo: `PHASES`, `ensure_open`/`go_home`/
  `send_whatsapp(contact, text, dry_run, log_path)` idénticos vistos
  desde fuera; internamente delega en `core.text_match/guards/titles`.
- Todo lo específico vive aquí: `PACKAGE = "com.whatsapp"`,
  `RES_KEYS = ("contact_name", "conversation_name", "conversation_contact",
  "title", "toolbar_title", "conversacion")`, predicados
  (`is_search_trigger`, `is_msg_box`, `is_send` + regex propias),
  `FORBIDDEN` propio (puede reutilizar `FORBIDDEN_DEFAULT`),
  `PHASES = (SEARCH, TYPE_CONTACT, PICK, VERIFY_CHAT, FOCUS_MSG,
  TYPE_MSG, SEND, VERIFY)`, `is_sensitive` = tap en `SEND`,
  compuerta `SEND` (chat verificado + texto en input + botón real),
  `verify_final` (texto fuera del input), `go_home` por `press_back`.
- Prohibido importar `WA`/constantes del plugin desde `loop`, `tools`,
  `core` o `server`. Dependencia en un solo sentido: plugin → core.
- Futura app = nuevo `tasks/<app>.py` que implementa `TaskProtocol`
  + llama a `loop.run(task, dry_run, log_path)`; core intacto.

## 5. Aceptación verificable (`@judge`, sin editar)

1. **Cero acoplamiento en core** (desde `mcp-server/`):
   `grep -rniE 'whatsapp|com\.whatsapp|felix|wa[^a-z]' src/jev_mcp/loop.py
   src/jev_mcp/server.py src/jev_mcp/tools/ src/jev_mcp/state.py
   src/jev_mcp/ui_normalizer.py src/jev_mcp/core/ --include='*.py'` → **vacío**.
   (Solo `tasks/whatsapp.py`, `tests/` y `docs/` pueden nombrarlos.)
2. **Tests verdes**: `uv run pytest` (incluye `test_guards.py`,
   `test_loop.py`, `test_normalizer.py` + nuevos `test_core_*.py` del
   contrato) y `./gradlew :app:testDebugUnitTest` (Fase 1 intacta).
3. **Dry-run forense Fase 5**: corrida `send_whatsapp(..., dry_run=True)`
   con stub Jev produce `logs/run-<ts>.jsonl` con fase, snapshot,
   opciones, respuestas y acción por paso; el paso sensible queda
   `{"planned": true, "evidence": {"dry_run": true, ...}}` sin tocar
   el dispositivo.
4. **Compuertas intactas**: `VERIFY_CHAT` título estricto, blacklist
   → `FORBIDDEN_TARGET`, reintentos VERIFY solo fuera de chats
   (`WRONG_CHAT` dentro sin tapear), avance por `asked`, `STALE×3` →
   `UI_UNSTABLE`.

## 6. Alcance para `@coder` (no improvisar arquitectura)

Crear `core/{text_match,guards,titles}.py` + `tests/test_core_*.py`;
reescribir `tasks/whatsapp.py` como plugin fino sobre core
(misma API pública, mismo `PHASES`/compuertas); ni `loop.py` ni `tools/`
ni `server.py` cambian salvo imports. Sin Compose/Hilt/Room/Retrofit/Ktor
(AGENTS.md §4); sin `su`; sin `shell` (Fase 6, `METHOD_NOT_ALLOWED`).
