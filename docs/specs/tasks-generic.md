# tasks-generic v2 — contrato Dual-Tier genérico (core vs plugins-ejemplo)

> Contrato Fase 4–5 (PLAN.md). Redacta `@architect`, implementa `@coder`,
> certifica `@judge`. En conflicto, **AGENTS.md manda** (§5.14-16, forense,
> System1 vs System2). `ARCHITECTURE.md §6` es la referencia Dual-Tier.
> Ejemplo no-normativo (único permitido): un plugin de mensajería fuera del core.
> Estado: v2 dual-tier 2026-10-04 (sin literales normativos de app).

## 1. Principio: core genérico, plugins-ejemplo fuera

1. El MCP expone **solo primitivas agnósticas** (nombres MCP ↔ método Jam):
   `open_app(package)`↔`open_app`, `close_app`↔`force_stop`,
   `read_screen`↔`dump_ui`+normalizar (`get_app_state`),
   `get_foreground`↔`get_foreground`, `tap_node`↔`tap_node`,
   `tap_text`↔`tap` (legado, preferir `tap_node`), `type_text`↔`type`,
   `scroll`↔`scroll`, `press_back`/`press_home`, `wait_for_text`↔`wait_for_node`,
   `screenshot`↔`screenshot`, `list_packages`, `device_status`.
   Equivalencia con PLAN.md §Principios: `get_node_hierarchy`=`read_screen`,
   `tap_point`≈`tap_text`, `input_text`=`type_text`, `swipe`=`scroll`,
   `keyevent`=`press_back/home`, `launch_app`=`open_app`.
   System1 ejecuta / System2 planifica (ARCHITECTURE §6).
2. **Cero literales de dominio en core.** Prohibido en `loop.py`, `server.py`,
   `tools/`, `state.py`, `ui_normalizer.py`, `core/`: nombres de paquete
   concretos, nombres propios de personas/contactos, `resource_id` concretos,
   regex de UI de una app, títulos o textos de prueba. Todo eso es **dato
   del plugin** (`tasks/<dominio>.py`), nunca mecanismo del core.
3. Regla de fallo: **si una prueba falla en un dominio, se cuestiona
   arquitectura o gestión de Jev (preguntas/criterios/compuertas),
   nunca se hardcodea el dominio en core.** El fix vive en el plugin
   o en un helper genérico parametrizado.
4. Split S1/S2: S1 (Jev + core determinista + Jam) = filtros, poda §6.3,
   guards, verificación. S2 (orquestador/LLM frontera) = planifica hitos,
   diagnostica anomalías, redacta texto semántico. Las compuertas (§4)
   son **obligatorias** y viven mitad en core (mecanismo) mitad en plugin
   (datos y umbrales).

## 2. TaskProtocol v2 (lo que `loop.run` exige)

El loop (`observe→questions→ask→interpret→_execute→verify_final`,
enum `tap_node|type_text|scroll|done|abort|noop|escalate`, `dry_run` +
`is_sensitive`, `STALE_SNAPSHOT×3→UI_UNSTABLE`, forense JSONL por paso)
solo acepta tareas que implementen este protocolo. Firmas exactas:

```python
class TaskProtocol:
    PHASES: tuple[str, ...]   # fases genéricas, p.ej. ("LOCATE", "FOCUS",
                              # "VERIFY_CONTEXT", "ACT", "VERIFY")
    phase: int                # índice actual; el avance lo decide la tarea
                              # en interpret(), el loop solo lo lee para el
                              # forense (asked vs self.phase)

    TAU: float = 0.70         # umbral de confianza parametrizado por plugin;
                              # conf < TAU → escalate (ver §4)

    async def observe(self) -> dict:
        """Estado fresco: {package, activity, snapshot_id, candidates[],
        screen_height, [error, error_text]}. Sin mutar dispositivo salvo
        reintentos de lectura. candidates[] ya podado (≤60 vigente,
        ⊂ 255 Choice 254+NONE, §5)."""

    def questions(self, state: dict, history: list) -> dict:
        """Preguntas Jev para la fase actual (+ base last_ok/progress
        en el mismo batch single-pass). Solo describe; no actúa.
        next_action: Choice(CLICK/TYPE/SCROLL/DONE/ESCALATE + target_id
        + needs_system_2); last_ok: Noul; progress: Score."""

    def interpret(self, answers: dict, state: dict, history: list) -> dict:
        """Jev→acción cerrada: {kind: tap_node|type_text|scroll|done|abort|
        noop|escalate, ...}. Aquí viven el avance de fase, el gate tau
        y las compuertas deterministas. Clave fuera de criteria →
        JevHallucination; conf < TAU → escalate."""

    async def verify_final(self, state: dict) -> tuple[bool, dict]:
        """Verificación final determinista (re-lee pantalla). Nunca solo-Jev.
        (ok, evidence)."""

    def is_sensitive(self, action: dict) -> bool:
        """True = dry_run la planea sin ejecutar (toda acción crítica /
        destructiva / con efectos externos)."""
```

Invariantes (AGENTS.md §5.13-16, ya en `loop.py`, no redefinir):
`noop` para fases de solo-verificación; `type` exige foco (`NOT_FOCUSED`
si no, tap previo explícito del cliente); acciones no devuelven snapshot
(el cliente verifica con `read_screen`/`wait_for_text`); `snapshot_id`
monotónico exigido en `tap_node`/`type_text`; `escalate` nunca tapea.

## 3. Helpers genéricos en `core/` (parametrizados, sin dominio)

Nuevo paquete `mcp-server/src/jev_mcp/core/` (puro, sin I/O salvo
lo indicado). Todo parametrizado:

```python
# core/text_match.py
def norm(s: str) -> str: ...            # NFKD→ascii→lower
def skeleton(s: str) -> str: ...        # norm sin [aeiou\s]
def name_hit(needle: str, cand: dict) -> bool:
    """Match tolerante parametrizado: palabra len>2 en norm(text+desc)
    o skeleton len>=3 contenido. needle y cand son parámetros."""
def title_matches_strict(expected: str, title: str) -> bool:
    """Igualdad norm, o expected+apellido-simple / expected+(paréntesis).
    Ante la duda False. expected/title son parámetros."""

# core/guards.py
FORBIDDEN_DEFAULT: str  # p.ej. r"reenviar|forward|compartir|share|eliminar|delete|borrar"
def is_forbidden(cand: dict, pattern: str = FORBIDDEN_DEFAULT) -> bool: ...
def check_stuck_same(action: dict, history: list, n: int = 2) -> dict | None:
    """Si (kind,node_id) == últimas n → abort STUCK_SAME. Puro."""
def require_verified(verified: bool, key: str, code: str) -> dict | None:
    """Si no verificado → abort {code} (NO_VERIFY/ACT_UNSAFE/...). Puro."""
def guarded_action(key: str, cands: dict, snap: int, *,
                   forbidden: bool) -> dict | None:
    """Valida clave tap:/type:/done/abort/escalate contra cands+snapshot.
    FORBIDDEN_TARGET / JevHallucination. Puro."""
def gate_tau(conf: float, tau: float) -> dict | None:
    """Si conf < tau → {kind: escalate, reason: LOW_CONF}. Puro."""

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
(`rid_keys`, `top_frac`), `_action_for` (compuertas) y `gate_tau`
**sí van a core** como mecanismos parametrizados. Los **datos**
(lista `rid_keys` de cada dominio, regex de cada predicado, `PACKAGE`,
`PHASES`, valor de `TAU`) quedan en el plugin.

## 4. Umbrales tau y política de escalado

| Señal | Umbral / condición | Acción del loop |
|---|---|---|
| `conf` de `next_action` (Choice) | `< TAU` (default 0.70, el plugin puede subirlo en dominios críticos) | `escalate` a S2 con `{fase, candidatas, conf}`; S2 re-planifica o aporta criterio/texto; sin tapear |
| Acción crítica/destructiva (`is_sensitive`) | siempre, con o sin conf alta | `dry_run` la planea sin ejecutar; ejecución solo con compuerta verde (identidad estricta + precondiciones deterministas + verificación posterior) |
| `Noul` de bloqueo semántico (captcha, login ajeno, `SECURE_SURFACE`, contexto ajeno) | `true` = bloqueado | `escalate`; reintentos solo fuera del contexto ajeno; dentro → código `WRONG_CONTEXT` sin tapear |
| `Score` de progreso estancado (2 lecturas sin avance) | configurable, default 2 | `escalate` con forense; nunca bucle infinito de taps |
| `STALE_SNAPSHOT` ×3 | fijo | `abort UI_UNSTABLE`, forense completo |

TAU es dato del plugin, no constante del core. Subirlo encarece (más S2),
bajarlo arriesga (más S1 autónomo). El forense debe registrar `conf`,
`tau` y la decisión por paso para calibrar.

## 5. Poda, anti-inyección, PII, IME (core la aplica, plugin la parametriza)

- **Poda** (ARCHITECTURE §6.3, cadena real `500 raw (extractor,
  invisibles) → 60 candidatos (normalizer, decoración/contenedores)
  ⊂ 255 Choice (límite Jev, 254+N ONE)`): poda semántica solo en
  normalizer; el extractor solo poda invisibles + tope 500. El tope
  254+NONE es capacidad Choice, no tope vigente del normalizer
  (vigente `MAX_CANDIDATES=60`; subir a 254 pendiente Fase 5).
  El plugin solo aporta predicados de candidatura; el tope lo impone core.
- **Anti-prompt-injection:** todo `text`/`content_desc` de UI se etiqueta
  `data` y nunca se concatena como instrucción en `questions`; plantillas
  fijas con slots. El plugin no construye prompts con f-strings de UI cruda.
- **PII mask local:** antes de forense/S2, enmascarar identificadores y
  textos de dominio en el host; el forense guarda hashes/longitudes salvo
  declaración explícita del plugin para depuración.
- **IME:** el teclado en pantalla no mueve coordenadas lógicas; si
  `ui_dirty` tras IME, re-dump antes de actuar.
- **Fallback sin-árbol** (Canvas/Flutter, `nodes == []` con ventana activa):
  `screenshot` → S2 diagnostica; S1 devuelve `ESCALATE`, nunca coordenadas
  inventadas (`SELECTOR_NOT_FOUND` si no hay nodo).

## 6. `tasks/<dominio>.py` → plugin-ejemplo (contrato, no código)

- Cada plugin implementa `TaskProtocol` con sus `PHASES` genéricas
  (p.ej. localizar → enfocar → verificar-contexto → actuar → verificar),
  sus predicados, sus `rid_keys`, su `PACKAGE`, su `TAU` y su
  `is_sensitive` (toda acción con efectos externos = sensible).
- API pública mínima: `ensure_open` / `go_home` / `run(dry_run, log_path)`
  delegando en `core.text_match/guards/titles`; compuerta de actuación
  (contexto verificado + texto en input + control real) y `verify_final`
  (re-lee pantalla, nunca solo-Jev).
- Prohibido importar constantes del plugin desde `loop`, `tools`,
  `core` o `server`. Dependencia en un solo sentido: plugin → core.
- Nuevo dominio = nuevo `tasks/<dominio>.py` + `loop.run(task, …)`;
  core intacto.

## 7. Forense por corrida (`logs/run-<ts>.jsonl`)

Un JSON por paso con: `fase_asked`, `fase_self`, `snapshot_id`,
`candidates` (ids podados), `questions`, `answers` (`conf`, `tau`),
`action` (`kind`, `target`, `planned` si dry-run), `verify`
(`ok`, `via`, `evidence`), `error` si hay. El paso sensible en dry-run
queda `{"planned": true, "evidence": {"dry_run": true}}` sin tocar el
dispositivo. Sin forense, un incidente es indiagnosticable (AGENTS §5.16).

## 8. Aceptación verificable (`@judge`, sin editar)

1. **Cero acoplamiento en core** (desde `mcp-server/`):
   `grep -rniE '<paquete-concreto>|<nombre-propio>|<resource-id-concreto>'`
   `src/jev_mcp/loop.py src/jev_mcp/server.py src/jev_mcp/tools/`
   `src/jev_mcp/state.py src/jev_mcp/ui_normalizer.py src/jev_mcp/core/`
   → **vacío**. (Solo `tasks/<dominio>.py`, `tests/` y `docs/` como
   ejemplo no-normativo pueden nombrarlos.)
2. **Tests verdes**: `uv run pytest` (incluye `test_guards.py`,
   `test_loop.py`, `test_normalizer.py` + nuevos `test_core_*.py` del
   contrato) y `./gradlew :app:testDebugUnitTest` (Fase 1 intacta).
3. **Dry-run forense**: corrida del plugin-ejemplo con `dry_run=True`
   y stub Jev produce `logs/run-<ts>.jsonl` con fase, snapshot,
   opciones, respuestas (`conf`/`tau`) y acción por paso; el paso
   sensible queda planeado sin ejecutar.
4. **Compuertas intactas**: contexto verificado por título estricto,
   blacklist → `FORBIDDEN_TARGET`, reintentos solo fuera de contexto
   ajeno (`WRONG_CONTEXT` dentro sin tapear), avance por `asked`,
   `STALE×3` → `UI_UNSTABLE`, `conf < TAU` → `escalate`.

## 9. Alcance para `@coder` (no improvisar arquitectura)

Crear `core/{text_match,guards,titles}.py` + `tests/test_core_*.py`
(+ `gate_tau` en guards); adelgazar `tasks/` a plugin-ejemplo fino sobre
core (misma API pública, mismas compuertas, TAU parametrizado); ni
`loop.py` ni `tools/` ni `server.py` cambian salvo imports. Sin
Compose/Hilt/Room/Retrofit/Ktor (AGENTS.md §4); sin `su`; sin `shell`
(Fase 6, `METHOD_NOT_ALLOWED`). Transporte siempre Java-WebSocket;
binds `127.0.0.1` + IP tailnet con WSS (nunca `0.0.0.0` por defecto).
