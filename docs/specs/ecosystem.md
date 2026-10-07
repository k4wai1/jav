# ecosystem — benchmarking del ecosistema Android computer-use + propuesta de rename

> Estado: **plan @architect 2026-10-07, solo `docs/`**. No es código, no se
> commitea, no se ejecuta nada. Implementa `@coder`, certifica `@judge`.
> En conflicto, **AGENTS.md (manda), ARCHITECTURE.md y
> `docs/specs/generic-dual-tier.md` v3 mandan**.
>
> Fuentes: `refs/scrcpy-mcp`, `refs/droidpilot`,
> `refs/android-uiautomator-mcp`, `refs/mobile-use` (árbol local) +
> `refs/android-jev` / `refs/mobile-jev` (ya aplicados vía
> `docs/specs/applied-refs.md`) + conocimiento público del resto
> (AppAgent/Mobile-Agent, AndroidWorld, DroidRun/streaming,
> AutoDroid/DroidBot — sin copiar código ajeno, solo forma).
> Estado del repo: `4d833f9` (docs sincronizadas PLAN/TESTING/paradigm-shift),
> `bd1f5a4` (35 tools MCP con docstrings 5-secciones), `68a5d01`
> (usage + build A10), 148 pytest en verde, `loop.py` congelado (v5),
> carril nativo N0/N1 vivo, N2/`shell` = `METHOD_NOT_ALLOWED` hasta Fase 6.
>
> Reglas del doc: **cero literales normativos de app** (ningún paquete,
> contacto, texto o flujo concreto como default; los ejemplos son
> no-normativos y van marcados), **cero keys/modelos/URLs** (todo por env).

## 1. Tabla comparativa

Columnas: **Arquitectura | Fortalezas | Cuellos/limitaciones | Qué adoptamos
(archivo destino)**. "Adoptamos" = forma/validación, nunca endpoints,
modelos, keys ni vía privilegiada ajena (AGENTS.md §4/§5: sin `adb`/`input
text`/`uiautomator` en `src/`; Shizuku + Accessibility + `ACTION_SET_TEXT`).

| Fila | Arquitectura | Fortalezas | Cuellos / limitaciones | Qué adoptamos (destino) |
|---|---|---|---|---|
| **AppAgent / Mobile-Agent (vision-only)** | VLM sobre screenshots; documento de conocimiento auto-explorado; acción por coordenadas | Cero integración on-device; funciona con cualquier app sin tocarla; buen techo en apps desconocidas | Token-cost altísimo (imagen por paso); coordenadas frágiles ante resolución/densidad; sin estado estructurado; reintentos ciegos | **Solo como fallback**: SoM-screenshot cuando `dump_ui` da 0 nodos (`mcp-server/src/jev_mcp/tools/ui.py`, rama fallback; `director.py` lo pide a S2/director, nunca al S1). Nada de grounding por coordenadas como vía primaria |
| **AndroidWorld (testbed)** | Benchmark con tareas parametrizadas + verificadores de estado del sistema (no del texto de UI) | Verificación por **estado**, no por "parece que funcionó"; corpus reproducible; anti-falso-éxito | Es harness de evaluación, no agente; sus tareas son sintéticas; no sirve en dispositivo real del operador | **Verificadores terminales por estado** (`mcp-server/src/jev_mcp/core/loop_helpers.py`: `verify_final`/terminal-checks: re-leer pantalla + estado — campo contiene valor, pantalla esperada visible — antes de declarar éxito; forense en `logs/run-<ts>.jsonl`). Patrón, no su código |
| **scrcpy / DroidRun (stream)** | H.264 por `scrcpy` + protocolo binario de control; input 10–50× vs ADB, screenshots ~33 ms | Latencia de percepción/input imbatible; streaming de vídeo/audio; clipboard que salta la restricción de Android 10+ vía canal scrcpy | Requiere binario + `adb` + red USB/WiFi; nada on-device; sin semántica (píxeles, no nodos); audio/vídeo = dependencias pesadas (ffmpeg) | **Clipboard con negativa tipada** (`mcp-server/src/jev_mcp/tools/clipboard.py`: error máquina-legible tipo `clipboard_read_refused` + hint, en vez de contenido basura/NULs — patrón visto en `refs/scrcpy-mcp/src/tools/clipboard.ts` `parseServiceCallParcel`/`parcelException`). **Streaming: NO** (coste ffplay/ffmpeg en Celeron + fuera de nuestro transporte WS; queda en roadmap P3) |
| **AutoDroid / DroidBot (grafos)** | Grafo de estados/acciones por exploración; transiciones UI→UI memorizadas | Reutilización entre corridas (el grafo aprende la app); detecta pantallas ya vistas; bueno para regresión | Construir el grafo cuesta una exploración completa; frágil ante rediseños; memoria pesada para "un goal, una vez" | **Memoria `recent` + `forbidden_paths`** (`mcp-server/src/jev_mcp/core/guards.py` o `loop_helpers.py`: historial acotado últimos N + lista opt-in por goal de caminos prohibidos; evita revisitar sin grafo completo). Grafo persistente entre corridas: NO (fuera de alcance) |
| **scrcpy-mcp (44 tools)** | MCP Node + `adb`/`scrcpy` utils; 44 tools (device/input/apps/UI/shell/files/clipboard/video/audio) | Catálogo más completo del ecosistema; degradación honesta adb↔scrcpy; `ui_find_element` → coordenadas; validación de nombres de paquete | Todo pasa por host+ADB (151 ms/tap, 4353 ms/`uiautomator dump` medidos en nuestro banco); sin snapshot-ids (coordenadas stale silenciosas); superficie enorme = superficie de ataque | **Top robables**: (a) clipboard negativa tipada → `tools/clipboard.py`; (b) `app_current` (foreground honesto) → `tools/app.py` (`get_foreground` ya existe: endurecer con `PACKAGE_NOT_FOUND`/sin-ventana honesto); (c) validación de insumos (nombres/entidades) → `tools/_base.py` validadores puros. **NO**: vía adb/scrcpy, audio/vídeo, 44-tools como superficie (nosotros: 35 tools, 6 del bucle) |
| **droidpilot (a11y+WS)** | APK con AccessibilityService + WebSocket WiFi; servidor MCP Node; 18 tools (`get_ui_tree`, `find_element`, `click_element`, `wait_for_element`, `get_focused`, `set_text`…) | El más cercano a nosotros: árbol nativo, sin ADB/USB, bajo costo de tokens, `click_element` (click OS antes que gesto), foco real | Sin token/scopes/audit (confía en la LAN); sin snapshot-ids (stale silencioso); `type_text` = append sin replace ni read-back; 18 tools sin telemetría/settings nativos | **Top robables**: (a) `wait_for_node` (espera con timeout sobre criterio, no sleep fijo) → `tools/ui.py` (ya esbozado: consolidar con `snapshot_id` fresco + test); (b) **walk-up clickable** (si el nodo no es clickable, subir al ancestro clickable más cercano antes de gesticular) → `ui_normalizer.py` o `tools/ui.py` helper puro + test; (c) `colapso contenedor-texto` (contenedor + único hijo texto → una fila) → `ui_normalizer.py`; (d) `get_focused` → ya cubierto por `focused_field` (P0-1 aplicado). **NO**: transporte sin auth, ausencia de scopes/forense |
| **uiautomator-mcp (FastMCP+snapshot)** | FastMCP Python + `uiautomator2`; snapshot cache con IDs `[e1]…` BFS; 3 modos de compresión XML (summary ~14×, compact ~10×, drill-down); multi-device por serial; acciones invalidan cache (read-act-read) | Compresión honesta para LLMs (14× medido); IDs estables **dentro** del snapshot; stateless por llamada; multi-device limpio | `uiautomator dump` = 4353 ms en nuestro banco (16× vs a11y in-process); XML 10–100 k chars sin comprimir; IDs mueren con el snapshot (stale si no se invalida); sin foco/tipo estructurado | **Top robables**: (a) **drift-check con `was`/`now`** (toda mutación declara contra qué snapshot iba; mismatch → `STALE_SNAPSHOT`, re-observar 1 vez, 2.º → `UI_UNSTABLE`) → `core/loop_helpers.py::assert_fresh` + `loop.py` (P1-6 aplicado: extender a `SCROLL/BACK` tolerante-1-stale); (b) **compresión por modos** (resumen solo-interactivos como default, árbol completo bajo demanda) → `ui_normalizer.py` (poda 60→254 pendiente + modo resumido); (c) **multi-device por serial**: NO ahora (single-client `BUSY` es decisión congelada §2.1; queda P3). **NO**: `uiautomator2` como vía (prohibido en `src/`) |
| **mobile-use (VLM jerárquico)** | Multi-agente: planner/operator/answer/reflector/progressor/note-taker (12 subagentes); reflexión jerárquica + exploración proactiva; 75% AndroidWorld screenshot-only | Mejor tasa publicada en benchmark abierto; reflexión que corrige planes, no solo pasos; progreso explícito multi-app | 12 agentes = 12 llamadas/paso (costo y latencia brutales en nuestro Celeron y presupuesto <$0.003/corrida); ADB-dependiente; prompts con apps concretas; sin compuertas de irreversibles | **Top robables**: (a) **verificador DONE-S2** (el éxito lo certifica un rol distinto al que actuó) → ya aplicado (`verify_done`, `18fd704`; consolidar en `loop.py` + `s2_client`); (b) **detect_stall determinista** (misma decisión/acción ×3 sin cambio útil de fingerprint → abort, sin LLM) → `core/guards.py::check_stuck_same` (ya existe: extender a firma-por-contenido P1-5, ignorando tickers); (c) **memoria `recent` acotada** (últimos 8) → `loop_helpers.py` (P1-5). **NO**: jerarquía multi-agente (nuestro v5 la sustituye por director único + Jev-resolver ciego), exploración proactiva (cada mutación cuesta y puede ser irreversible) |
| **NOSOTROS (dual-tier v3→v5 + N0/N1)** | Jam on-device (a11y + Shizuku + providers nativos) + WS/WSS con token+scopes + MCP 35 tools + S1 Jev Choice≤255 / S2-director o director humano + forense JSONL + CostTracker | Ver §2 (posición propia) | Ver §2 (posición propia) | — (somos la base; todo lo robado se reinterpreta a Shizuku+a11y+`ACTION_SET_TEXT`, nunca `adb`/`input text`/`clipboard-shell`) |

## 2. Top robables → destino (consolidado, con estado)

Los 13 patrones que piden los informes explorer, cada uno con **destino
exacto y estado real** (aplicado / parcial / pendiente). Nada aquí introduce
literales de app ni keys.

| # | Patrón (origen) | Destino | Estado |
|---|---|---|---|
| 1 | **Clipboard con negativa tipada** (scrcpy-mcp `clipboard.ts`: `parcelException`/`CLIPBOARD_READ_REFUSED`) | `mcp-server/src/jev_mcp/tools/clipboard.py` (+ `director.py` fachada) | Parcial: `set_clipboard` Jam + `get_clipboard` host existen (v5); **pendiente** código máquina-legible `clipboard_read_refused` + `CLIPBOARD_UNSUPPORTED` con hint de degradación a `type_text` |
| 2 | **Walk-up clickable** (droidpilot `click_element`: ancestro clickable antes que gesto) | `mcp-server/src/jev_mcp/ui_normalizer.py` (helper puro `nearest_clickable`) + `tools/ui.py` | Pendiente (P1). Ya hacemos `ACTION_CLICK`-primero (AGENTS.md §6); falta subir al ancestro cuando el target no es clickable, con test |
| 3 | **`wait_for_node`** (droidpilot `wait_for_element` con timeout) | `mcp-server/src/jev_mcp/tools/ui.py` | Parcial: existe `wait_for_text`; **pendiente** generalizar a criterio (`text`/`resource_id` sufijo/`content_desc`/`class` + `snapshot_id` fresco + `STALE` honesto) |
| 4 | **Colapso contenedor-texto** (droidpilot/uiautomator-mcp: resumir nodos envoltorio) | `mcp-server/src/jev_mcp/ui_normalizer.py` | Pendiente (P1): contenedor no-clickable con único hijo texto → una fila; filtrar decoración del sistema ya existe (Fase 4) |
| 5 | **Drift-check con `was`/`now`** (uiautomator-mcp `StaleObservationError` + `expected`) | `mcp-server/src/jev_mcp/core/loop_helpers.py` (`assert_fresh`) + `loop.py` | **Aplicado** (P1-6: `TAP`/`TYPE` exigen snapshot vigente; `STALE×3→UI_UNSTABLE`). Pendiente: `SCROLL`/`BACK` toleran 1-stale sin contar racha |
| 6 | **`detect_stall` determinista** (mobile-use reflector → regla sin LLM) | `mcp-server/src/jev_mcp/core/guards.py` (`check_stuck_same`) | **Aplicado** base (`STUCK_SAME×3`); pendiente firma-por-contenido que ignore tickers (P1-5: regex de hora genérica solo en no-clickables) |
| 7 | **Verificador DONE-S2** (mobile-use answer-agent; android-jev `completion-noul`) | `mcp-server/src/jev_mcp/loop.py` (`verify_done`) + `s2_client` | **Aplicado** (`18fd704`: sin éxito con 0 acciones; `DONE` nunca fast-path). Pendiente: `verify_final` determinista re-lee pantalla (v4 §6.4) |
| 8 | **Memoria `recent` + `forbidden_paths`** (AutoDroid/DroidBot + A4 `RECENT_ACTIONS_KEPT=8`) | `mcp-server/src/jev_mcp/core/loop_helpers.py` + `core/guards.py` | Parcial: historial forense existe; **pendiente** ventana `recent:8` en el state S1 (ahorro tokens) + `forbidden?` opt-in por goal (ya en contrato v3, falta cablear en `run_goal`) |
| 9 | **Forense por evento** (mobile-jev `onAction`-antes-de-`observe` + A5 wire+timings) | `mcp-server/src/jev_mcp/loop.py` + `logs/run-<ts>.jsonl` | Parcial: JSONL por corrida existe; **pendiente** log-antes-de-observar + `wire` verbatim + `timings{reading,deciding,acting,watching}` por step (P1-7) |
| 10 | **`app_current`** (scrcpy-mcp + uiautomator-mcp `current_app`) | `mcp-server/src/jev_mcp/tools/app.py` (`get_foreground`) | Parcial: existe; **pendiente** endurecer (`root==null` transitorio vs sin-ventana, reintento 1 + error honesto con hint, sin inventar paquete) |
| 11 | **SoM-fallback solo si 0 nodos** (AppAgent/Mobile-Agent) | `mcp-server/src/jev_mcp/tools/ui.py` (rama fallback) + `director.py` | Pendiente (P2): si `dump_ui` da 0 nodos útiles → `screenshot` a S2/director con anotación; prohibido como vía primaria (accesibilidad manda, AGENTS.md §1) |
| 12 | **Verificadores terminales por estado** (AndroidWorld) | `mcp-server/src/jev_mcp/core/loop_helpers.py` | Pendiente (P2): `verify_final`: tras `DONE` de S2, re-leer y comprobar predicado de estado (campo contiene valor / pantalla esperada) antes de `ok:true`. Nunca éxito solo-Jev |
| 13 | **Shortcuts deterministas** (droidpilot `open_app`; uiautomator-mcp `launch_app`; nuestro v5 "SO antes que dedos") | `mcp-server/src/jev_mcp/director.py` + `tools/app.py`/`tools/native.py` | **Aplicado** base (v5 §6.3: `open_app` directo, clipboard por API, `ACTION_SET_TEXT`+read-back). Pendiente: tabla de atajos auditada (qué va por API vs qué exige dedos, con test) |

### Incompatibles (qué NO se roba, con motivo)

1. **Vía `adb`/`uiautomator`/`input text`/clipboard-shell en `src/`**
   (scrcpy-mcp, uiautomator-mcp, mobile-use, android-jev-ref). Motivo: AGENTS.md
   §5.2 + applied-refs §1.2 — mandan Shizuku + Accessibility; `uiautomator
   dump` es 16× más lento que nuestro `dump_ui` (§3 medido).
2. **Endpoints/modelos/keys/URLs de las refs.** Motivo: todo por env
   (`OPENROUTER_API_KEY`, `JEV_MODEL`, `GLM_MODEL`, `*_RATE_*`); prohibido
   hardcodear (applied-refs §1.3–1.4).
3. **Streaming A/V scrcpy + audio** (scrcpy-mcp `video.ts`/`audio.ts`, ffmpeg).
   Motivo: dependencias pesadas en host Celeron 2-núcleos; nuestro transporte
   es WS con frame 4 MiB; `screenshot` evidencial basta (P3, solo si hay banco
   que lo pida).
4. **Multi-device simultáneo** (uiautomator-mcp `DevicePool`). Motivo:
   single-client `BUSY` es decisión congelada (ARCHITECTURE §2.1); dos bancos
   (KJ5 + A10) se usan en serie, no en paralelo (P3).
5. **Jerarquía de 12 subagentes + exploración proactiva** (mobile-use).
   Motivo: costo por paso incompatible con `<$0.003`/corrida; v5 ya la
   sustituye por director único; cada mutación proactiva puede ser
   irreversible (§5.14-16 no se derogan).
6. **Podador "agresivo = 20" / tabla recortada a 1 / auto-finish ciego.**
   Motivo: rechazados sin medir (ARCHITECTURE §6.6; applied-refs A1: la propia
   ref prohíbe aceptar `finish` contra `completion`).
7. **Superficie de 44 tools tal cual.** Motivo: la nuestra (35, 6 del bucle)
   es decisión de separación por carril (§2.16); importar sin poda rompería el
   contrato `{ok, verified, evidence, hint}` + scopes.

## 3. Posición propia (honesta)

### Dónde estamos por encima

- **Seguridad on-device real.** Token bearer obligatorio incluso en loopback
  + scopes (`read`/`ui`/`shell`/`admin`) + lockout + frame 4 MiB + audit ring
  500 + kill switch. droidpilot confía en la LAN; scrcpy-mcp confía en el
  host; uiautomator-mcp/SSE expone HTTP sin auth propia. Ninguno audita por
  método con hash de args.
- **Jev 0% estructural.** `Choice≤255` + `validateChoice` estricta (P0-3) +
  `Score`/`Noul` + 100% inglés al S1: el S1 no puede inventar JSON. Los
  vision-only y los multi-agente aceptan texto libre del actor en cada paso.
- **N0/N1: SO antes que dedos.** Telemetría, settings, intents con `package`,
  clipboard por API, usage/contactos/calendario/notifs/ubicación/cámara con
  grants en `hello.caps`. Ninguna ref tiene carril nativo con grants
  declarados; todas gesticulan para lo que una API resuelve en 1 salto.
- **Forense + costos por paso.** JSONL por corrida con `conf`/`tau`,
  `snapshot`/`fingerprint`, `[COST]` USD con tarifas por env. mobile-use
  loguea trayectoria pero sin costo; scrcpy-mcp/droidpilot no forensean.
- **Anti-staleness.** `snapshot_id` monotónico + `STALE_SNAPSHOT` + reintento
  ×1 en el bucle + `UI_UNSTABLE` ×3. uiautomator-mcp invalida cache pero sin
  error tipado de carrera; droidpilot/scrcpy-mcp actúan sobre coordenadas sin
  frescura.
- **Latencia de percepción.** `dump_ui` in-process ~2 ms/nodo (13n/40 ms,
  124n/264 ms) vs `uiautomator dump` 4353 ms y vs screenshot-por-paso de los
  vision-only. El cuello nuestro es el LLM (~1.6 s S1), no la percepción.

### Dónde estamos por debajo

- **Firmas anti-ticker.** Nuestra `STUCK_SAME` aún usa decisión/snapshot;
  scrcpy-mcp y uiautomator-mcp no lo resuelven tampoco, pero mobile-use
  (reflector) y AndroidWorld (verificadores) sí distinguen cambio peor caso
  ~1 s a 500 nodos; la poda 60→254 y la optimización IPC (2–3×) siguen
  pendientes (Fase 4+).
- **Streaming.** scrcpy-mcp entrega vídeo ~33 ms + audio; nosotros, `screenshot`
  bajo demanda (1409 ms vía `screencap`; `takeScreenshot` 30+ más rápido pero
  sin stream). Para un director humano mirando en vivo, vamos detrás.
- **Madurez de benchmark.** mobile-use publica 75% AndroidWorld; nosotros
  medimos por goal propio (Fossify 5/5, mensajería-A/B, YT→Brave bloqueo
  honesto) sin corpus ≥20 goals ni intervalos (P2-8 pendiente). Sin números
  comparables, "mejor" es opinión.
- **Multi-device.** uiautomator-mcp maneja N seriales en paralelo; nosotros,
  single-client `BUSY` (decisión consciente, pero inferior en flotas).
- **Robustez sin accesibilidad.** Sin el servicio habilitado, nuestra UI muere
  (`ACCESSIBILITY_DISABLED`); los ADB-puros siguen operando degradados. N0
  mitiga (sigue vivo), pero no actúa UI.
- **Onboarding/UX.** droidpilot/scrcpy-mcp se instalan y conectan en minutos
  desde cliente estándar; nosotros exigimos operador entrenado (grants N1,
  Shizuku por usuario, QR+TOFU, `confirm:true`). Potencia a cambio de fricción.

## 4. Rename: el proyecto ya no es "agente Android con Jev"

El árbol real: MCP completo (35 tools) + app on-device non-root (a11y +
Shizuku + providers N0/N1) + tres carriles (nativo / director-cliente v5 /
dual-tier congelado) donde Jev es **un** resolver (ciego al goal en v5), no el
proyecto. `jev-android-mcp` + `dev.jev.jam` + "Jam" nombran al proveedor de un
componente, no al sistema; además fijan marca ajena en nuestro paquete.

### Candidatos

| # | Nombre (repo + app) | Justificación | Contras |
|---|---|---|---|
| A | **`droidmcp`** — repo `droidmcp`, app `DroidMCP` (`dev.droidmcp.agent`) | Dice exactamente qué es: MCP de uso de Android. Sin marca de proveedor; extensible a N dispositivos; nombre corto para `uvx`/docs | Genérico hasta lo anodino; colisión parcial con `droidpilot`/`droidrun` en búsquedas |
| B | **`jamboree`→`jamlink`** — repo `jamlink`, app **Jam** conservada (`dev.jamlink.agent`) | Conserva el capital existente (Jam ya instalada en 2 bancos, docs/BUILD/TESTING la citan); "link" = puente host↔dispositivo, que es lo que el WS hace | "Jam" no significa nada para un tercero; mantiene sílaba opaca; el paquete cambia igual (migración inevitable) |
| C | **`unroot`** — repo `unroot-mcp`, app `Unroot` (`dev.unroot.agent`) | Nombra la restricción que nos distingue (non-root como feature, no como carencia); memorable; dice seguridad sin decir "secure" | Puede leerse como herramienta de rooteo (lo contrario); limita si Fase 6+ añade `shell` con Shizuku (ya no "sin privilegios" puros) |

### Implicaciones de migrar (cualquiera de los tres)

1. **Repo/remote:** renombrar en forja + `git remote set-url`; redirección del
   nombre viejo; `refs/` ignorados no se tocan.
2. **Paquete Android:** `dev.jev.jam` → nuevo `applicationId`; exige
   desinstalar/reinstalar en KJ5 + A10 + LG7n, re-habilitar accesibilidad y
   re-generar token (el Keystore no migra); `ShizukuProvider` authority cambia.
3. **Docs/specs:** `AGENTS.md` §9 (nombre y banco), `ARCHITECTURE.md` §2.9 +
   diagrama §4, `PLAN.md` Fase 0, `PROTOCOL.md` (`hello` `app_version`),
   `docs/BUILD.md`, `docs/TESTING.md`, `README.es/en.md`, los 8 specs que
   citan Jam/Jev-mcp. Estimación: ~40 menciones, mecanizable con sustitución
   + revisión.
4. **Servidor:** `mcp-server/src/jev_mcp/` (paquete Python) + `server.json` +
   `.env.example` (`JEV_*` → prefijo nuevo; mantener alias 1 versión) +
   `opencode.json` + rutas `/sdcard/Download/jev-mcp/`.
5. **Forense/logs:** `logs/run-*.jsonl` históricos quedan con el nombre viejo
   (no se reescriben; se anota el corte en `PLAN.md`).

### Recomendación

**`droidmcp` (opción A).** Es el único que describe el sistema completo a un
tercero sin explicar nada ("MCP para usar Android"), no lleva marca de
proveedor (Jev pasa a ser un backend declarado en `JEV_MODEL`, que es lo que
ya es en v5), y sobrevive a que el S1/S2 cambien. Costo de migración medio
(§4.2–4.4), pero cada mes que pasa el costo sube (más bancos, más forense con
el nombre viejo). **El rename lo decide el operador; aquí no se ejecuta.**

## 5. Roadmap de adopción priorizado (costo / beneficio)

Ordenado por ratio beneficio-costo; cada ítem cabe en 1 commit `@coder` + su
test `@judge`; `loop.py` sigue congelado (solo bugfix con test) y lo nuevo
vive en `core/`/`tools/`/`director.py` o specs.

| Prioridad | Ítem (§2) | Beneficio | Costo | Aceptación |
|---|---|---|---|---|
| **P1a** | 1 clipboard negativa tipada + 10 `app_current` honesto | Acaba con la peor clase de bug silencioso (contenido basura tratado como real) | Bajo: 2 errores tipados + tests | `get_clipboard` sobre app en 2.º plano → `clipboard_read_refused` + hint; `get_foreground` sin ventana → error honesto, nunca paquete inventado |
| **P1b** | 3 `wait_for_node` + 5 drift `SCROLL`/`BACK` tolerante | Elimina sleeps fijos y carreras en navegación (causa medida de flakes) | Bajo: generalizar `wait_for_text` + flag tolerante | Espera con timeout sobre criterio; `SCROLL` stale ×1 no cuenta racha |
| **P1c** | 2 walk-up clickable + 4 colapso contenedor-texto | Sube `conf` S1 en 1.ª vista (menos `ESCALATE` espurios) y recorta tabla | Medio-bajo: 2 helpers puros en `ui_normalizer.py` + tests | Tabla con filas colapsadas; tap sobre no-clickable resuelve ancestro y reporta `via: ancestor-click` |
| **P2a** | 8 memoria `recent:8` + `forbidden?` cableado | −tokens/paso + anti-revisita sin grafo; `FORBIDDEN` ya es contrato v3 | Medio: state S1 + `guards.py` + 2 tests | State lleva `recent` acotado; goal con `forbidden?` aborta con `FORBIDDEN_TARGET` |
| **P2b** | 6 firma-por-contenido anti-ticker + 9 forense por evento | `STUCK_SAME` deja de falsar por relojes; incidente diagnosticable en 1 JSONL | Medio: `screen_fingerprint` + orden log-antes + `wire`/`timings` | Test ticker (`12:01`→`12:02` no rompe firma); cada línea con `wire`+`timings`, PII enmascarada |
| **P2c** | 12 verificadores terminales + 7 `verify_final` determinista | Cero falsos-éxitos (el incidente que originó §5.14-16 no puede repetirse por construcción) | Medio: predicados de estado + re-lectura | `DONE` exige `verify_done` S2 **y** `verify_final` verde; si no, `ok:false` honesto |
| **P3** | 11 SoM-fallback + streaming + multi-device + tabla 254 + recalibración TAU | Techo de robustez y números publicables | Alto: cada uno ≥1 fase; TAU exige corpus ≥20 goals ×3 (P2-8) | Solo con operador explícito; streaming únicamente si hay banco que lo pida; multi-device exige enmienda de §2.1 (`BUSY`) |

Secuencia propuesta: **P1a → P1b → P1c** (una ventana de trabajo), luego
**P2a → P2b → P2c**, P3 solo bajo demanda. Nada de P3 entra sin que P2 esté
verde y medido.
