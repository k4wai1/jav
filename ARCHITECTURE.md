# jev-android-mcp — ARCHITECTURE

> Documento vinculante. Toda decisión de implementación que contradiga este
> archivo requiere una enmienda explícita aquí antes de codear. Las reglas de
> `AGENTS.md` (manda) y el contrato exacto de `PROTOCOL.md` están por encima.
>
> Estado: **actualizado 2026-10-07** (era 2026-10-04; enmiendas pre-0b/pre-Fase-2
> y 2026-10-05 en `AGENTS.md §9`). Refleja el árbol real:
> **dual-tier v3** (`docs/specs/generic-dual-tier.md` + addendum §12),
> **plan-ahead v4** (`docs/specs/plan-ahead.md`),
> **director-client v5** (`docs/specs/director-client.md`, con `loop.py`
> congelado) y **carril nativo N0/N1/N2** (`docs/specs/native-apis.md`).
> Los specs son el contrato operativo; este archivo es el porqué y el mapa.
> Resume, no duplica. Cero literales normativos de app (los ejemplos con
> paquetes son no-normativos) y cero keys.

## 1. Visión

MCP genérico para controlar Android con lenguaje natural. Ninguna capacidad
del core conoce apps, paquetes, contactos, textos o flujos concretos: lo
específico lo aporta el runtime (el Director externo o S2 por conocimiento
general). El **Director es el cliente externo** (OpenCode/operador, nunca
parte de Jav): es el único planificador; **Jav es un servidor MCP Go delgado
(`cmd/jav` stdio, `pkg/tools`, sin bucles y sin S2 interno)** que expone 35
tools atómicas + `resolve_element` ciego. Tres carriles conviven, del más
determinista al más semántico:

1. **Carril nativo (APIs directas, sin Jev, sin UI).** Jam responde por
   framework Android / Shizuku: telemetría, settings, intents, clipboard,
   usage, contactos, calendario, notificaciones/media, ubicación, cámara.
   N0 (sin permisos nuevos) y N1 (con grant del usuario) implementados; N2
   (Shizuku/`shell` on-device) queda `METHOD_NOT_ALLOWED` hasta Fase 6.
   Detalle en `docs/specs/native-apis.md`.
2. **Director-cliente v5 (metas complejas/multi-app, vía activa).** Un único planificador
   **externo** —el director (OpenCode/operador, cliente de Jav, no módulo de Jav)—
   que ve cada pantalla, decide el plan paso
   a paso y usa Jev solo como **resolver de elementos** (una `Choice` de
   micro-intención, ciega al goal global). "El director decide, Jev señala,
   Jam ejecuta". Jav no loopea ni planifica dentro. Detalle en `docs/specs/director-client.md`.
3. **Dual-tier `run_goal` (histórico, congelado, no la vía activa).** El bucle
   autónomo S1 Jev + S2 LLM queda como referencia congelada
   (`docs/specs/generic-dual-tier.md` + `plan-ahead.md` v4): sin features nuevas,
   solo bugfixes de seguridad/regresión. El runtime activo no corre ese loop.

Arquitectura **Dual-Tier** histórica del carril 3 (congelada; detalle en §6):

- **Sistema 1 = Jev (TypeSafe, juicio discriminativo):** resuelve cada paso
  en una sola llamada single-pass (70–500 ms), sin texto libre. Primitivas
  `Choice` (≤255 opciones + confianza calibrada), `Score`, `Noul`. 0% errores
  estructurales por construcción, falible lógicamente ante context-rot.
- **Sistema 2 = LLM frontera (GLM-5.3):** planifica/diagnostica/redacta.
  Nunca toca el dispositivo; (v4) compila el plan paso 0 y solo vuelve ante
  anomalía o terminal. Bajo v5 el director humano/OpenCode asume el plan.

## 2. Decisiones congeladas

| # | Decisión | Implementación |
|---|---|---|
| 1 | Transporte | WebSocket RFC 6455. Listener A: `ws://127.0.0.1:38472` (loopback). Listener B (opt-in): `wss://<ip-tailnet>:38472`, bind a la IP del tailnet (`100.64.0.0/10`), **nunca `0.0.0.0` por defecto**. Single-client (`BUSY` al segundo). Frame 4 MiB |
| 2 | MCP | Go en el PC: binario **`jav`** (`cmd/jav`, stdio, `JAV_WS_URL`; `adb forward` para loopback). Harness Python `mcp-server/` congelado como referencia histórica, no runtime |
| 3 | Privilegios | **App non-root.** UI = AccessibilityService. Shell = Shizuku (UID 2000). **`su` prohibido en código** |
| 4 | TLS + token | Self-signed por instalación (BouncyCastle), pinning TOFU (QR). `ws` solo en loopback; **WSS obligatorio en no-loopback. Token obligatorio en todos los binds** |
| 5 | Token | Hand-rolled: AES-256 en AndroidKeyStore + AES/GCM, bearer en el frame `hello` (nunca en URL) |
| 6 | Jev | OpenRouter `typesafe/jev-1.13` por defecto; `jev_client` abstraído para swap a TypeSafe oficial |
| 7 | Shell | OFF por defecto. `shell` **bloquea hasta 60 s** esperando grant (1 comando = SHA-256 exacto / 5 min / 30 min). Expira sola. **Hasta Fase 6 el dispatcher lo rechaza con `METHOD_NOT_ALLOWED`** |
| 8 | minSdk | 29 (Android 10). `compileSdk/targetSdk 34`. Fallback `screencap` en API 29 (sin verificar: solo hay API 31/33) |
| 9 | Nombre y banco (2026-10-01) | App = **Jam** (`dev.jev.jam`). Bancos: TECNO KJ5 (API 33, sin root, loop Wi-Fi) + **A10 USB** (Android 10, 720×1440, director v5) + LG7n (API 31, Magisk) secundario |
| 10 | Latencia y `secure` (2026-10-02) | **≤300 ms para ≤150 nodos; ~2 ms/nodo; peor caso ~1 s a 500**. Bucle Jev ≈ 500–800 ms/paso. **`secure` fuera de `dump_ui`** (FLAG_SECURE no oculta el árbol); solo `screenshot` → `SECURE_SURFACE`. Acciones sin post-snapshot; `type` exige foco (`NOT_FOCUSED`) |
| 11 | Fase 3a (2026-10-02) | **`open_app`/`force_stop` vía Shizuku; `screenshot` vía `takeScreenshot()` (API 30+) sin Shizuku; `shell` diferido a Fase 6.** Shizuku lo arranca el usuario; sin él → `SHIZUKU_UNAVAILABLE` + hint |
| 12 | **plan-ahead v4 (2026-10-05)** | S2-compilador paso 0 `EXECUTE_GOAL` + `preloaded_inputs` (sin reconsulta en el camino feliz) · `FAST_TAU = 0.85` (TAU 0.70 intacto) · post-read **coalescido** (un dump/paso) · columna **`zone` 3×3** en la tabla · `MAX_TABLE = 254` (+`NONE`) · todo-a-Jev 100% inglés. Detalle en `docs/specs/plan-ahead.md` |
| 13 | **director-client v5 (2026-10-07)** | Director-cliente: OpenCode/operador dirige, **Jev = resolver ciego** (1 `Choice` de micro-intención EN, anti-poisoning), **`loop.py` congelado** para el SENT simple. Atajos nativos en 1 salto (SO antes que dedos). Detalle en `docs/specs/director-client.md` |
| 14 | **Carril nativo N0/N1 (2026-10-07)** | Telemetría (batería/RAM/storage/CPU/device), `settings` System get/put, intents/`open_url`, clipboard, usage, contactos, calendario, notificaciones/media (honesto), ubicación, cámara. **N2 = `METHOD_NOT_ALLOWED` hasta Fase 6.** Detalle en `docs/specs/native-apis.md` |
| 15 | **Escala física en gestos (2026-10-07)** | `DisplayScale`: `bounds` de `dump_ui` siguen en **espacio lógico** de accesibilidad; solo `dispatchGesture` proyecta a **píxeles físicos del panel**. Medido en banco: lógico 360×720 (`wm size override`) vs panel 720×1440 → factor **2.0** por eje (identidad si no hay override) |
| 16 | Separación de tools | De las **35 tools MCP** expuestas: **6** son primitivas del bucle Jev (`read_screen`, `tap_node`, `type_text`, `scroll`, `press_back`, `open_app`-bootstrap); **29** sirven al director / carril nativo / diagnóstico (§7) |

## 3. Verdad del terreno (medido 2026-09-30…10-07)

**Host:** Debian 13, Celeron 847 (2 núcleos @ 1.1 GHz), 3.7 GiB RAM
(~1.7 libres) + 7.5 GiB swap, JDK 21, adb/uv/python/node/rust presentes.
Toolchain en `~/Android/Sdk`. `/home` 34 GB libres.

**Dispositivos:** TECNO KJ5 (Android 13/API 33, sin root, banco principal);
A10 USB (Android 10, 720×1440, `e03638e5`, banco director v5);
TECNO LG7n (Android 12/API 31, Magisk root — la app no lo usa).

**Latencias host→USB (incluyen ~63 ms de ida/vuelta ADB):**
`shell echo` 63 ms · `dumpsys window` 80 ms · `input tap` **151 ms**
· `pm list` 299 ms · `screencap` **1409 ms** · `uiautomator dump` **4353 ms**.

**Latencias in-app (`dump_ui`, medidas en dispositivo):**
13 nodos → 40 ms (5 ms en caliente) · 66 nodos → 106 ms ·
124 nodos → 264 ms. Escalado **~2 ms/nodo** (IPC por nodo; uiautomator
sigue siendo 16× más lento a igual carga).

**Pipeline medido (v3→v5):** tap ~70 ms (`ACTION_CLICK` primero, gesto
fallback) · S1 ~1.6 s · S2 ~1.9 s vs flash ~22 s por llamada (medido con
provider S2 directo, retirado 2026-10-07; S2 vive solo en OpenRouter) ·
`fast-path` ahorra 1 dump/paso. Coste por corrida < $0.003 (Jev
`$0.042` in / `$0.00` out por MTok normativo; GLM por env `GLM_RATE_IN/OUT`).
Conclusión: el cuello es **percepción**, no input; AccessibilityService es el
camino primario de percepción (árbol in-process).

## 4. Arquitectura

```
HOST Debian 13 (Director externo + Jav Go + Jam en teléfono)
┌───────────────────────────────────────────────────────────────┐
│ DIRECTOR EXTERNO (OpenCode/operador) — único planificador (v5) │
│  cliente de Jav, fuera de Jav; decide una primitiva por paso   │
│ JAV Go (cmd/jav, MCP stdio, sin bucles ni S2 interno)          │
│  tools/ device · app · ui · clipboard · native · jev-resolver  │
│  director/ (adaptadores pasivos paso a paso) · normalizer · cost│
│  (histórico Python loop.py/run_goal congelado, no activo)      │
└───────────────┬────────────────────────────┬──────────────────┘
  WS 127.0.0.1:38472 (adb forward) │ WSS <ip-tailnet>:38472 (opt-in)
                 ▼ USB / red                    ▼ tailnet
┌───────────────────────────────────────────────────────────────┐
│ Jam (dev.jev.jam, app non-root)                                │
│  ForegroundService ── 2 listeners WS (loopback + tailnet)      │
│  JevAccessibilityService ── UI tree + tap/type/scroll + gestos │
│  ShizukuBridge ── newProcess/UserService (UID shell):          │
│                   pm, am, settings, input, screencap           │
│  Native providers ── BatteryManager · UsageStats · Contacts ·  │
│                   Calendar · NotificationListener · Location · │
│                   Camera2 (FGS) · ClipboardManager             │
│  DisplayScale ── proyección lógico→físico para dispatchGesture │
│  MainActivity (solo onboarding: 3 estados + token + QR)        │
└───────────────────────────────────────────────────────────────┘
```

**Cascada de ejecución por operación (carril UI):**
percepción → AccessibilityService (obligatorio; `snapshot_id` anti-staleness) ·
tap: `ACTION_CLICK` si `clickable`, `dispatchGesture` si no, **siempre verificar**
(`via` reportado); el gesto se **proyecta** a físico con `DisplayScale` ·
type: `ACTION_SET_TEXT` con foco explícito previo ·
lifecycle/shell/settings → Shizuku (UID shell) ·
`open_app` → Shizuku `am start` (fallback `monkey`), nunca Intent desde
background ·
screenshot → `takeScreenshot()` (30+) → `screencap` vía Shizuku (API 29);
`FLAG_SECURE` → `SECURE_SURFACE` (solo screenshot; el árbol no se oculta).
**Carril nativo:** sin accesibilidad y sin gestos; Jam responde por API
directa (§7). Sin Shizuku, N0 sigue vivo.

## 5. Modelo de privilegios (app non-root)

```
App (UID normal)
├── AccessibilityService ── UI tree + gestos
│      (usuario lo habilita en Ajustes → Accesibilidad)
├── ShizukuBridge ── permiso runtime API_V23
│      └── Shell UID 2000: pm, am, settings, input, screencap
│          vía Shizuku.newProcess(...) / UserService AIDL (Fase 3)
└── Providers nativos (N0/N1): sin root; grants runtime/Ajustes (§7)
```

1. Prohibido `Runtime.exec("su")`, `su -c`, `ProcessBuilder("su")`.
   Aceptación verificable: `grep -rn "su -c\|exec(.*su" android-app/` **vacío**.
2. Shizuku lo inicia el usuario (ADB o app de Shizuku). La app solo **pide permiso**.
3. Sin permiso Shizuku → grupo `shell` deshabilitado, UI sigue viva,
   error honesto `SHIZUKU_UNAVAILABLE` con hint. **N0 sigue operativo.**
4. Sin accesibilidad → UI falla `ACCESSIBILITY_DISABLED`;
   `screencap` vía Shizuku y N0 siguen disponibles.

**Onboarding (única UI):** 3 indicadores (Accesibilidad ✓/✗, Shizuku ✓/✗,
Servidor ●), botón "Generar token" y QR con `{url, token, fingerprint}`;
estado de grants N1 en `hello.caps` (`usage_access`, `notification_listening`,
`contacts`, `calendar`, `location`, `camera`).

**Red (Tailscale):** la app **no integra** SDK de Tailscale.
Bindea loopback o la IP del tailnet autodetectada, con re-detección vía
`ConnectivityManager.NetworkCallback` + override manual en ajustes.
`0.0.0.0` solo forzado, con advertencia en pantalla y auditado.
TLS self-signed + pinning es **defensa en profundidad**, no el único
mecanismo. Nunca activar Tailscale Funnel para este puerto.
Política de grant por método: `open_app` = `ui` sin grant;
`force_stop` = `shell` sin grant; `grant_permission` y `shell` = `shell` con grant.

## 6. Inteligencia: dual-tier v3 → v4 (histórico congelado) → v5 (vía activa)

> Lectura v1.0.2: el runtime Jav **no corre loops ni S2 interno**. El único
> Sistema 2 es el **Director externo** (OpenCode/operador, cliente de Jav).
> S1 Jev actúa solo como resolver ciego por paso (`pkg/jev` + `pkg/director`,
> adaptadores pasivos). v3/v4 (`generic-dual-tier.md`, `plan-ahead.md`) quedan
> como historial congelado; v5 (`director-client.md`) es la vía activa.

### 6.1 Reparto dual-tier (v3 histórico, `generic-dual-tier.md`)

| | Sistema 1 (Jev, TypeSafe) | Sistema 2 (LLM frontera, GLM-5.3) |
|---|---|---|
| Rol | Juicio discriminativo por paso | Planifica/compila, diagnostica, redacta |
| Salida | `[TAP,TYPE,SCROLL_DOWN,SCROLL_UP,BACK,DONE,ESCALATE]` + `target 0..253|NONE` + `needs_system_2` + `conf` | Plan `EXECUTE_GOAL` (v4) o comando de anomalía `OPEN_APP|TYPE|TAP|BACK|HINT` |
| Texto | **Nunca genera** (lo aporta S2 vía slot/`text_payload`) | Único que redacta |
| Idioma | **100% inglés** (claves, instrucciones, tabla, `screen_goal`) | Único que produce inglés semántico |

Compuertas: `TAU = 0.70`; `conf < TAU` → `ESCALATE`; críticas/irreversibles
(enviar/comprar/borrar/permisos/`shell`) → preview + `confirm:true`
sin confirmar se **planean sin ejecutar** (`planned`, `needs_confirm`);
`FORBIDDEN` solo **opt-in por goal** (`forbidden?`), nunca global. Cadena de
poda **500 raw → candidatos normalizer → 0..253 ⊂ 255 Choice** (254 + `NONE`).

### 6.2 plan-ahead v4 (histórico, `plan-ahead.md`)

- **S2-compilador paso 0:** una sola consulta al inicio devuelve
  `EXECUTE_GOAL{package, screen_goal_en, preloaded_inputs{slot: payload},
  expected_terminal_state, guidance_for_s1, stop}`. Los `TYPE` del camino
  feliz consumen los slots **sin reconsultar** a S2 (mapa `pending_payloads`
  con `consumed`); `open_app` solo en bootstrap. Detalle §2.1–§2.3.
- **Fast-path `FAST_TAU = 0.85`:** `conf ≥ 0.85` + trivial + no-sensible
  despacha sin consultas secundarias ni post-read redundante. **Nunca salta
  compuertas** (estructural, foco, `confirm`, `FORBIDDEN`, `STALE`, `STUCK`,
  `DONE`-gate). `DONE`/`ESCALATE` nunca son fast-path.
- **Post-read coalescido:** un solo `dump` por paso; el `verify` válido y con
  snapshot nuevo se reutiliza como `observe` siguiente (`coalesced:true`);
  si no es válido, se re-observa normal. Oportunista, nunca a ciegas.
- **`zone` 3×3:** columna calculada en host desde centroide + resolución
  (`top-left | … | bottom-right`, fallback `unknown`). Fila a Jev:
  `[idx, class_short, zone, flags, label]`; `id`/`bounds` quedan en host
  (`by_idx`) para validar/ejecutar. Hint, nunca señal de seguridad.

### 6.3 director-client v5 (vía activa, `director-client.md`)

> El Director es **cliente externo** (OpenCode/operador). Jav expone tools
> atómicas y el resolver ciego; no decide planes, no loopea, no hospeda S2.

La cadena histórica OpenCode → `loop.py` → S2 → Jev → Jam apilaba tres planificadores
sobre el mismo goal (poisoning por goal global, parálisis por indecisión,
dedos antes que APIs). v5 la sustituye para metas complejas:

1. **Un planificador externo:** el director (OpenCode/operador, cliente de Jav, fuera de Jav). Ve cada pantalla
   (`read_screen` + `screenshot` evidencial) y decide una primitiva por
   paso; `run_sequence` sigue prohibido.
2. **Jev = resolver de elementos** (`resolve_element`): **una sola `Choice`**
   sobre índices + `NONE`, con micro-intención EN de **la pantalla actual**
   (p.ej. `"Tap the Copy link row"`). Su `state` lleva solo
   `screen_goal + current_app + snapshot_id + table + first_result`: **nunca**
   el goal global, nombres propios ni paquetes (**anti-poisoning** auditable
   en test capturando el `state`). Jev devuelve `{idx, conf}`; la acción la
   decide el director.
3. **SO antes que dedos:** clipboard por API (leer host `dumpsys` +
   verificación por forma; escribir con `ClipboardManager.setPrimaryClip` en
   la propia Jam), `open_app` directo, `ACTION_SET_TEXT` + read-back. Sin
   método Jam → `CLIPBOARD_UNSUPPORTED` y degradación honesta a `type_text`.
4. **Loop histórico CONGELADO** (`mcp-server/loop.py`: `run_goal`, `ask_decision`, `s2_client`):
   sin features nuevas; referencia congelada, no runtime. **El runtime Go
   (`cmd/jav` + `pkg/`) no contiene loops ni S2 interno**: solo adaptadores
   pasivos paso a paso (`pkg/director`: "sin bucles, sin planificación macro").
   Todo lo nuevo vive fuera del loop, sin importar `run_goal`. `@judge`
   certifica con `go test ./...` verde (histórico Python: `pytest` al congelar).

### 6.4 Anti-giro y fail-fast (v3 §12 + v4)

- **`first_result`** (hint, nunca poda): índice del primer interactivo del
  contenedor principal, viaja a S1 en la cabecera y a S2 como
  `FIRST_RESULT: <idx>`; prior de atención, la tabla **nunca se recorta a 1**.
- **S2-TAP-direct** (`VALID_COMMANDS` incluye `TAP`): ante escalado en lista
  densa S2 elige el índice de la tabla vigente y el loop ejecuta `tap_node`
  sin re-preguntar a S1; exige `clickable` (si no, no muta), valida
  `visible`/bounds, respeta `FORBIDDEN`/crítica y hace **un** reintento por
  `STALE` (segundo → `UI_UNSTABLE`).
- **STALE-retry en el bucle:** ante `STALE_SNAPSHOT` en `tap_node`/`type_text`
  el loop re-observa UNA vez, re-resuelve por `id` y reintenta UNA vez; racha
  `×3` → `UI_UNSTABLE`. El reintento vive en el loop, no en la app.
- **`run_signature` + fail-fast:** corrida que cierra `ok:false` emite firma
  (`code`, `stalled_step`, snapshots/fingerprints first/last, `progress`).
  Igual firma en 2 corridas seguidas → **no relanzar**: `diff` de forenses +
  informe (regla operativa, no daemon).
- **`STUCK_SAME`:** misma `(kind,node_id)` ×3, o misma decisión
  `(action+target)` ×3 sin cambio útil de snapshot → abort. `DONE` siempre
  con gate S2 (`verify_done` con `expected_terminal_state`); `verify_final`
  determinista re-lee pantalla. Nunca éxito solo-Jev.

### 6.5 Anti-inyección y PII

- Contenido de UI (textos de terceros, mensajes, webs) **nunca** entra
  como instrucción a S2/Jev: se etiqueta como `data`, se recorta y los
  prompts usan plantillas fijas con slots.
- **PII mask local:** antes de loguear/subir forense o pedir a S2, enmascarar
  en el host (números, identificadores, textos de dominio). El forense guarda
  hashes/longitudes; textos crudos jamás si `is_sensitive` (solo `len`+`sha256`).
- Sin excepciones por app: la política es del core; cada carril parametriza
  lo suyo.

### 6.6 Divergencias rechazadas (AGENTS.md manda)

- **Ktor / Netty / SSE / HTTP como transporte: RECHAZADO.** El stack real es
  `Java-WebSocket` 1.5.7 (§8). Anti-patrón sin enmienda de AGENTS.md §4.
- **`0.0.0.0` como bind: RECHAZADO.** Binds `127.0.0.1:38472` (WS) + IP
  tailnet `100.64.x.x` autodetectada (WSS obligatorio en no-loopback).
  `0.0.0.0` solo con override explícito, advertencia y auditado.
- Token bearer 32+ bytes base64url en frame `hello`, nunca en URL, tiempo
  constante, obligatorio incluso en loopback; scopes `read`/`ui`/`shell`/`admin`;
  lockout 5/60 s → 5 min; frame 4 MiB; audit ring 500. Sin atajos.
- **Podador "agresivo = 20" RECHAZADO sin medir:** `MAX_TABLE = 254` intacto;
  `EXPERIMENT-TABLE-20` queda como experimento pendiente (v4 §9.5).

## 7. Árbol de herramientas MCP (35 tools, runtime Go)

**Separación por carril (decisión §2.16):** 6 tools son atómicas de UI
(dirigidas paso a paso por el **Director externo**, no por un loop interno);
las otras 29 sirven al director, al carril nativo y al diagnóstico.
Implementación activa: `pkg/tools/` (Go). El histórico Python
(`mcp-server/src/jev_mcp/tools/`, `director.py`, `loop.py`) está congelado.

**6 — UI atómicas (vía activa = Director externo paso a paso):** `read_screen` (`dump_ui` +
normalizer + tabla + `snapshot_id` + `first_result`/`zone`/`focused_field`),
`tap_node`, `type_text`, `scroll`, `press_back`, `open_app` (solo bootstrap por el director).

**29 — director / nativo / diagnóstico:**

| Grupo | Tools |
|---|---|
| device/diag | `device_status`, `list_packages`, `get_foreground`, `close_app`, `press_home`, `wait_for_text`, `screenshot`, `tap_text` (legacy, preferir `tap_node`) |
| telemetría N0 | `get_battery`, `get_memory`, `get_storage`, `get_cpu`, `get_device_info` |
| settings/intents N0 | `settings_get`, `settings_put` (System; Secure/Global = N2), `open_url`, `send_intent` |
| clipboard | `get_clipboard_device` (Jam foreground; host prefiere `dumpsys`) |
| usage N1 | `get_app_usage` |
| PII N1 | `list_contacts`, `add_contact`, `list_events`, `create_event` |
| notif/media N1 | `list_notifications`, `reply_notification`, `media_state`, `media_control` |
| ubicación/cámara N1 | `get_location`, `take_photo` (FGS + confirm siempre) |

Mapeo tool ↔ método (PROTOCOL.md §4/§4.1): `close_app`↔`force_stop`,
`get_app_state`↔`dump_ui`+normalizar, `get_foreground_app`↔`get_foreground`.
Toda tool devuelve `{ok, verified, evidence, hint}`; `verified=true` solo con
verificación real posterior, nunca por "comando enviado".

**Carril nativo (resumen; detalle en `docs/specs/native-apis.md`):**

- **N0 (sin permisos nuevos):** `get_battery`, `get_memory`, `get_storage`
  (básico), `get_cpu`, `get_device_info`, `settings_get` (System),
  `open_url`/`send_intent` (apertura), `set_clipboard` (ya en protocolo).
- **N1 (grant del usuario, estado en `hello.caps`):** `get_app_usage`,
  `list_contacts`/`add_contact`, `list_events`/`create_event`,
  `list_notifications`/`reply_notification`, `media_state`/`media_control`,
  `get_location`, `take_photo`. Proyección mínima; lectura sensible auditada;
  escritura/crítica → `confirm:true` + preview.
- **N2 (Shizuku/`shell` on-device):** `settings_put` Secure/Global,
  `get_storage`/`get_cpu` `detail=fine`, `dumpsys` fino, `grant_permission`,
  `shell`. **El dispatcher responde `METHOD_NOT_ALLOWED` hasta Fase 6.**
- **Honestidad (no se promete lo imposible):** escritura `Secure`/`Global`
  directa sin Shizuku, `MEDIA_CONTENT_CONTROL` directo, clipboard en segundo
  plano (Android 10+), cámara silenciosa y "envío directo" headless a apps de
  terceros **no existen** para una app non-root; llevan error honesto
  (`*_UNAVAILABLE` / `METHOD_NOT_ALLOWED`) + hint.

Tools nueva incorporación v5 (§2.13): `resolve_element` (resolver ciego),
`set_clipboard` (Jam `ClipboardManager`, sin Shizuku/garant), `get_clipboard`
(host `dumpsys`). `shell`/`adb_shell`: denylist de irreversibles
(`rm -rf /`, `pm uninstall` de sistema, `reboot recovery`, `dd`, `wipe`) →
scope `admin` **y** `confirm: true`. Push/pull solo bajo
`/sdcard/Download/jev-mcp/`.

## 8. Pins de versiones (verificados contra repos)

| Dep | Pin | Nota |
|---|---|---|
| AGP / Gradle | 8.5.2 / 8.7 | JDK 21 para Gradle, `jvmTarget 17` |
| Kotlin KGP + plugin serialization | **1.9.24** | conservador; K2 posterior |
| kotlinx-serialization-json | **1.6.3** | obligado por Kotlin 1.9.x |
| kotlinx-coroutines-android | **1.8.1** | compatible 1.9.24 |
| androidx.core:core-ktx | **1.13.1** | último sin exigir compileSdk 35 |
| androidx.appcompat:appcompat | **1.7.0** | idem |
| dev.rikka.shizuku:api + :provider | **13.1.5** | verificar en primer build |
| org.java-websocket:Java-WebSocket | **1.5.7** | API estable |
| bcprov-jdk18on + bcpkix-jdk18on | **1.86** | fallback 1.78.1 |
| junit (tests) | 4.13.2 | `testImplementation`, sin Robolectric |

Sin Compose/Hilt/Room/Retrofit/Ktor/Tink/SDK Tailscale.
`minSdk 29`, `compileSdk/targetSdk 34`, R8 solo en release, `allowBackup=false`.

`gradle.properties` (Celeron): `-Xmx1024m -XX:MaxMetaspaceSize=256m`,
`daemon=false`, `parallel=false`, `configureondemand=false`,
`org.gradle.workers.max=1`, **`org.gradle.caching=true`**,
`android.useAndroidX=true`, `android.enableJetifier=false`,
`android.nonTransitiveRClass=true`.

## 9. Roadmap

| Fase | Entregable | Aceptación medible |
|---|---|---|
| 0a | `ARCHITECTURE.md`, `AGENTS.md`, `PROTOCOL.md` | revisión del auditor |
| 0b | Toolchain en `~/Android/Sdk` | `sdkmanager --list_installed` OK |
| 0c | Scaffold + manifest + onboarding stub | `assembleDebug` compila |
| 0d | APK vacío instalado | app visible + grep `su` vacío + `docs/BUILD.md` |
| 1 | AccessibilityService + `dump_ui` + onboarding | anclas ≥95% vs `uiautomator`; latencia §3 |
| 2 | WS loopback + `hello`/token/scopes + tap/type/scroll/back | cliente genérico controla app genérica; sin token → rechazado |
| 2b | WSS tailnet + cert self-signed + token en Keystore | **pendiente** |
| 3a | Shizuku `open_app`/`force_stop` + `screenshot` | OK; sin Shizuku → degradación honesta |
| 3b | `shell` + audit log + kill switch *(Fase 6)* | denylist operativa; auditoría consultable |
| 4 | MCP Go + normalizer + tools device/app/ui | director externo lee pantalla (`go test ./...`) |
| 5 | dual-tier S1/S2 `run_goal` + compuertas + forense *(histórico congelado)* | goal genérico e2e; `planned` sin `confirm` |
| v4 | S2-compilador `EXECUTE_GOAL` + fast-path + coalescido + `zone` *(histórico)* | suite verde; forense `fast_path`/`coalesced` |
| v5 | director-cliente externo + `resolve_element` + `set_clipboard`, sin loops ni S2 en Jav | `go test ./...` verde; anti-poisoning en test |
| **N0** | Carril nativo sin permisos nuevos | latencia p50/p95; UI degradada pero N0 viva |
| **N1** | Carril nativo con grant del usuario | grants en `hello.caps`; críticas 100% con `confirm`; cero PII cruda |
| **N2** | Shizuku-only (diseño ahora, código Fase 6+) | `METHOD_NOT_ALLOWED` vigente |
| 6 | grupo `adb`, audit log, kill switch, docs, hardening | denylist operativa; auditoría consultable |

## 10. Riesgos

- **Compilación en 2 núcleos:** mitigado con build cache + R8 solo en release.
  Plan B `-Xmx1536m`; plan C build en CI.
- **Java-WebSocket NIO en Android:** verificar; plan B servidor WS bloqueante
  propio (~200 líneas, 0 deps).
- **BC + Keystore:** firma SHA256withRSA OK desde API 23; sin registro JCA global.
- **API 29 sin verificar:** fallback `screencap` diseñado pero no probado en banco.
- **USB inestable:** ambos TECNO se caen del bus a ratos; mitigar con ventanas
  de comandos cortas y `adb connect` por Wi-Fi (KJ5 loop va por Wi-Fi).
- **Optimización IPC (~2 ms/nodo):** el coste está en las calls por nodo
  (`getChild`, `getBoundsInScreen`). Candidata a Fase 4+.
- **Escala física en gestos (medido):** `bounds` en espacio lógico (a11y) vs
  píxeles físicos del panel; sin `DisplayScale` los gestos caen a la mitad del
  recorrido (banco A10: 360×720 lógico vs 720×1440 físico → factor 2.0).
  Corregido; identidad cuando no hay override.
- **`open_url` sin `package` cae en `ResolverActivity` si hay >1 handler
  (medido):** no garantiza abrir la app esperada; `send_intent` con `package`
  salta directo al handler. Uso normal: pasar `package` cuando se conozca.
- **KJ5 corre Shizuku+ clon:** Fase 3 exige instalar el oficial
  `moe.shizuku.privileged.api` (el LG7n ya lo trae).

## 11. Inspiración

- [docs.typesafe.ai — Jev API](https://docs.typesafe.ai/api) ·
  [introducción](https://docs.typesafe.ai/introduction) · [modelos](https://docs.typesafe.ai/models)
- [RikkaApps/Shizuku-API](https://github.com/RikkaApps/Shizuku-API)
- [NeuralBridge_mcp](https://github.com/dondetir/NeuralBridge_mcp) — latencias accesibilidad vs ADB
- [kaeawc/auto-mobile](https://github.com/kaeawc/auto-mobile) — AccessibilityService + socket
- `~/Mango-mcp` (propio): "Jev decide, no ejecuta", patrón `verified`, denylist
