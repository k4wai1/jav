# jev-android-mcp — ARCHITECTURE

> Documento vinculante. Toda decisión de implementación que contradiga este archivo
> requiere una enmienda explícita aquí antes de codear. Estado: **cerrada** (2026-09-30)
> + enmienda Dual-Tier genérico 2026-10-04 (§1, §6 reescritos; §9 y decisión 11
> desacoplados de app concreta; sin cambio de stack ni de seguridad).
> Enmiendas pre-0b y pre-Fase-2 registradas en `AGENTS.md §9`.

## 1. Visión

MCP genérico para controlar Android con un agente en lenguaje natural
("abre una app, localiza un elemento, introduce un texto, verifica el
resultado"). Ninguna capacidad del core conoce apps, paquetes, contactos,
textos o flujos concretos: todo lo específico vive en plugins de tarea
fuera del core (ver `docs/specs/tasks-generic.md`; como mucho se cita
una app comercial como ejemplo no-normativo en una línea).
Arquitectura **Dual-Tier** (detalle en §6):

- **Sistema 1 = Jev (TypeSafe, juicio discriminativo):** resuelve cada
  paso en una sola llamada single-pass (70–500 ms), sin texto libre.
  Primitivas: `Choice` (≤255 opciones + confianza calibrada),
  `Score` (2–10 niveles), `Noul` (pbooleano [0,1]). 0% errores
  estructurales por construcción, pero falible lógicamente ante
  context-rot o ambigüedad → compuertas en §6.
- **Sistema 2 = LLM frontera:** solo planifica hitos, diagnostica
  anomalías visuales, fallos persistentes y redacta texto semántico.
  Nunca toca el dispositivo directamente; emite planes que el S1
  ejecuta paso a paso con verificación determinista.

## 2. Decisiones congeladas

| # | Decisión | Implementación |
|---|---|---|
| 1 | Transporte | WebSocket RFC 6455. Listener A: `ws://127.0.0.1:38472` (loopback). Listener B (opt-in): `wss://<ip-tailnet>:38472`, bind a la IP del tailnet (rango `100.64.0.0/10`), **nunca `0.0.0.0` por defecto**. Single-client (`BUSY` al segundo). Frame 4 MiB |
| 2 | MCP | Python + `uv` en el PC (`JEV_WS_URL`; `adb forward` para loopback). Mismo protocolo sirve en Termux |
| 3 | Privilegios | **App non-root.** UI = AccessibilityService. Shell = Shizuku (UID 2000). **`su` prohibido en código** |
| 4 | TLS + token | Self-signed por instalación (BouncyCastle), pinning TOFU (QR). `ws` solo en loopback; **WSS obligatorio en no-loopback. Token obligatorio en todos los binds** |
| 5 | Token | Hand-rolled: AES-256 en AndroidKeyStore + AES/GCM, bearer en el frame `hello` (nunca en URL) |
| 6 | Jev | OpenRouter `typesafe/jev-1.13` por defecto; `jev_client` abstraído para swap a TypeSafe oficial |
| 7 | Shell | OFF por defecto. `shell` **bloquea hasta 60 s** esperando grant (notificación: 1 comando = SHA-256 exacto / 5 min / 30 min). Expira sola |
| 8 | minSdk | 29 (Android 10). `compileSdk/targetSdk 34`. Fallback `screencap` en API 29 (sin verificar: solo hay TECNO API 31) |
| 9 | Nombre y banco (2026-10-01) | App = **Jam** (`dev.jev.jam`). Banco principal = **TECNO KJ5 (API 33, sin root)**; LG7n (API 31, Magisk) secundario. Aceptación Fase 1: nodos con `text`/`resource_id` coinciden ≥95% con `uiautomator`, latencia in-app < 100 ms. KJ5 trae un clon **Shizuku+** (`af.shizuku.plus.api`), no el oficial: Fase 3 exige instalar `moe.shizuku.privileged.api` oficial |
| 10 | Latencia y `secure` (2026-10-02) | Criterio re-ratificado: **≤300 ms para ≤150 nodos; ~2 ms/nodo; peor caso ~1 s a 500**. Bucle Jev ≈ 500–800 ms/paso. **`secure` fuera de `dump_ui`** (FLAG_SECURE no oculta el árbol); solo `screenshot` → `SECURE_SURFACE`. Acciones sin post-snapshot; `type` exige foco (`NOT_FOCUSED`) |
| 11 | Fase 3a (2026-10-02) | **`open_app`/`force_stop` vía Shizuku; `screenshot` vía `takeScreenshot()` (API 30+) sin Shizuku; `shell` diferido a Fase 6.** Fase 2b (WSS/cert/Keystore) diferida a después de 3a. Shizuku lo arranca el usuario; sin él → `SHIZUKU_UNAVAILABLE` + hint. Banco: LG7n (Shizuku oficial). App de prueba: genérica (cualquier app instalada; ejemplo no-normativo anterior: app de mensajería) |

## 3. Verdad del terreno (medido 2026-09-30…10-02)

**Host:** Debian 13, Celeron 847 (2 núcleos @ 1.1 GHz), 3.7 GiB RAM
(~1.7 libres) + 7.5 GiB swap, JDK 21, adb/uv/python/node/rust presentes.
Toolchain en `~/Android/Sdk`. `/home` 34 GB libres.

**Dispositivos:** TECNO KJ5 (Android 13/API 33, sin root, banco principal);
TECNO LG7n (Android 12/API 31, Magisk root — la app no lo usa).

**Latencias host→USB (incluyen ~63 ms de ida/vuelta ADB):**
`shell echo` 63 ms · `dumpsys window` 80 ms · `input tap` **151 ms**
· `pm list` 299 ms · `screencap` **1409 ms** · `uiautomator dump` **4353 ms**.

**Latencias in-app (`dump_ui`, medidas en dispositivo):**
13 nodos → 40 ms (5 ms en caliente) · 66 nodos → 106 ms ·
124 nodos → 264 ms. Escalado **~2 ms/nodo** (IPC por nodo; uiautomator
sigue siendo 16× más lento a igual carga).

Conclusión: el cuello es **percepción**, no input. AccessibilityService
es el camino primario de percepción por el árbol in-process, no por el tap.

## 4. Arquitectura

```
HOST Debian 13 (agente + opencode)
┌──────────────────────────────────────────────────────────────┐
│ MCP SERVER (Python + uv, stdio)                              │
│  tools/ device · app · ui · jev · (system, adb: opt-in)      │
│  loop.py (observe→decide→mutate→verify)                      │
│  jev_client.py (OpenRouter / TypeSafe) · ui_normalizer.py    │
└───────────────┬────────────────────────────┬─────────────────┘
  WS 127.0.0.1:38472 (adb forward) │ WSS <ip-tailnet>:38472 (opt-in)
                 ▼ USB / red                    ▼ tailnet
┌──────────────────────────────────────────────────────────────┐
│ TECNO (Android 12/13, app non-root)                          │
│  ForegroundService ── 2 listeners WS (loopback + tailnet)    │
│  JevAccessibilityService ── UI tree + tap/type/scroll        │
│  ShizukuBridge ── newProcess/UserService (UID shell):        │
│                   pm, am, settings, input, screencap         │
│  MainActivity (solo onboarding: 3 estados + token + QR)      │
└──────────────────────────────────────────────────────────────┘
```

**Cascada de ejecución por operación:**
percepción → AccessibilityService (obligatorio; `snapshot_id` anti-staleness) ·
tap: `ACTION_CLICK` si `clickable`, `dispatchGesture` si no, **siempre verificar** (`via` reportado) ·
type: `ACTION_SET_TEXT` con foco explícito previo ·
lifecycle/shell/settings → Shizuku (UID shell) ·
`open_app` → Shizuku `am start` (fallback `monkey`), nunca Intent desde background ·
screenshot → `takeScreenshot()` (30+) → `screencap` vía Shizuku (API 29);
`FLAG_SECURE` → `SECURE_SURFACE` (solo screenshot; el árbol no se oculta).

## 5. Modelo de privilegios (app non-root)

```
App (UID normal)
├── AccessibilityService ── UI tree + gestos
│      (usuario lo habilita en Ajustes → Accesibilidad)
└── ShizukuBridge ── permiso runtime API_V23
       └── Shell UID 2000: pm, am, settings, input, screencap
           vía Shizuku.newProcess(...) / UserService AIDL (Fase 3)
```

1. Prohibido `Runtime.exec("su")`, `su -c`, `ProcessBuilder("su")`.
   Aceptación verificable: `grep -rn "su -c\|exec(.*su" android-app/` **vacío**.
2. Shizuku lo inicia el usuario (ADB o app de Shizuku). La app solo **pide permiso**.
3. Sin permiso Shizuku → grupo `shell` deshabilitado, UI sigue viva,
   error honesto `SHIZUKU_UNAVAILABLE` con hint.
4. Sin accesibilidad → UI falla `ACCESSIBILITY_DISABLED`;
   `screencap` vía Shizuku sigue disponible.

**Onboarding (única UI):** 3 indicadores (Accesibilidad ✓/✗, Shizuku ✓/✗,
Servidor ●), botón "Generar token" y QR con `{url, token, fingerprint}`.

**Red (Tailscale):** la app **no integra** SDK de Tailscale.
Bindea loopback o la IP del tailnet autodetectada, con re-detección vía
`ConnectivityManager.NetworkCallback` + override manual en ajustes.
`0.0.0.0` solo forzado, con advertencia en pantalla y auditado.
TLS self-signed + pinning es **defensa en profundidad**, no el único
mecanismo. Nunca activar Tailscale Funnel para este puerto.
Política de grant por método: `open_app` = `ui` sin grant;
`force_stop` = `shell` sin grant; `grant_permission` y `shell` = `shell` con grant.

## 6. Dual-Tier genérico (S1 Jev vs S2 LLM)

### 6.1 Reparto

| | Sistema 1 (Jev, TypeSafe) | Sistema 2 (LLM frontera) |
|---|---|---|
| Rol | Juicio discriminativo por paso: elige 1 operación entre candidatas | Planifica hitos, diagnostica anomalías, redacta texto semántico |
| Entrada | Tabla UI numerada (nodos podados, §6.3) + fase + historial resumido | Plan de tarea, forense `logs/run-<ts>.jsonl`, `screenshot` en fallback sin-árbol |
| Salida | 1 llamada → `{op: CLICK/TYPE/SCROLL/DONE/ESCALATE, target_id, needs_system_2, conf}` | Sub-objetivos, criterios de verificación, textos a escribir |
| Latencia/coste orientativo | 130–380 ms/paso, ~$0.0002/acción; ~80% de pasos por S1 | Solo en planificación/excepciones; ahorro >95% vs VLM puro |
| Texto libre | Nunca genera (lo provee S2 vía slot `needs_text`) | Único que redacta texto de dominio |

Patrón operativo: el MCP serializa la UI en **tabla numerada**;
Jev resuelve en **1 llamada** operación + `target_id` + `needs_system_2`.
El output es gratis → ramificación especulativa de coste ~0 (preguntas
`next_action`/`last_ok`/`progress` en el mismo batch). Sin key de Jev →
stub mock honesto (`{mock: true}`), nunca inventar opciones.

Endpoint por defecto: `POST https://openrouter.ai/api/alpha/decisions`
(`model: "typesafe/jev-1.13"`). Oficial (swap futuro):
`POST https://api.typesafe.ai/v1/systemone` (`model: "jev-latest"`).
Latencia 70–500 ms por llamada. Batch de preguntas en una sola llamada.

```json
{"model": "typesafe/jev-1.13",
 "state": {"package": "<paquete genérico>", "screen": "<actividad>",
           "elements": ["[n_0] Button \"…\"", "…"]},
 "questions": {
   "next_action": {"type": "choice", "instructions": "…",
                   "criteria": {"tap:n_3": "…", "type:n_5": "…",
                                "done": "…", "abort": "…"}},
   "ready":       {"type": "noul",   "instructions": "…",
                   "criteria": {"true": "…", "false": "…"}},
   "done":        {"type": "score",  "instructions": "…",
                   "criteria": ["no", "parcial", "sí"]}}}
→ {"answers": {…}, "model_version": "…"}
```

**Split con nuestro stack:** Jev decide, no ejecuta. El MCP lee UI
(`dump_ui` por WS con `hello`/token/scopes `read`+`ui`), normaliza a
estado semántico, pregunta, ejecuta (`tap_node`/`type`/`scroll`),
verifica (`wait_for_node`/`dump_ui`). Cuando Jev decide "escribir",
el MCP devuelve al agente principal
`{"needs_text": true, "slot": "…", "prompt": "…"}` y este provee el texto.

### 6.2 Compuertas (tau / críticas / Noul)

- **Confianza tau (~0.70):** `conf < tau` → `ESCALATE` a Sistema 2
  (re-planificar, pedir criterio o texto). Tau vive en el plugin de
  tarea, no en el core; el core solo aplica el umbral parametrizado.
- **Acciones críticas/destructivas** (enviar, borrar, pagar, conceder
  permisos, `shell`): siempre a Sistema 2 / humano; el core las marca
  `is_sensitive` → `dry_run` las planea sin ejecutar; sin compuerta
  verde (identidad estricta + precondiciones deterministas) no hay
  ejecución. `shell` además exige scope `shell` + grant activo y hasta
  Fase 6 el dispatcher lo rechaza con `METHOD_NOT_ALLOWED`.
- **Bloqueos semánticos** (captcha, login ajeno, superficie `SECURE_SURFACE`,
  `FORBIDDEN_TARGET`, `WRONG_CHAT` dentro de contexto ajeno): vía `Noul`
  → `ESCALATE`, nunca reintentar tapeando a ciegas.
- Mecanismo en core, datos en plugin: blacklist parametrizada
  (`FORBIDDEN_DEFAULT` en `core/guards.py`, el plugin aporta la suya),
  `title_matches_strict`, `require_verified`, `check_stuck_same`.

### 6.3 Poda determinista (cadena 500 → 60 ⊂ 255 Choice)

Cadena real: **500 raw (extractor Jam: poda invisibles + tope 500)
→ 60 candidatos (normalizer host: poda decoración/contenedores,
tope vigente `MAX_CANDIDATES=60`) ⊂ 255 Choice
(capacidad Jev: 254 interactivos + 1 `NONE`)**.
El tope 254+NONE es capacidad del `Choice`, no tope vigente del
normalizer (subir 60→254 pendiente Fase 5 si se quiere).

Poda semántica solo en normalizer; el extractor solo poda
invisibles + tope 500:

1. Extractor (app Jam): invisibles (`visible == false`) fuera;
   tope 500 nodos/snapshot (BFS, `snapshot_id` monotónico).
2. Normalizer (host): contenedores sin semántica (`text`/`content_desc`/
   `resource_id` nulos y sin hijos accionables) fuera.
3. Normalizer (host): nodos de decoración del sistema (`statusBarBackground`,
   `navigationBarBackground`) fuera (en `ui_normalizer.py`, Fase 4).
4. Topes: normalizer vigente `MAX_CANDIDATES=60` (editable > clickable-con-texto
   > resto, estable); capacidad `Choice` 254 interactivos + 1 `NONE` = 255
   opciones; exceso → priorizar visibles accionables en orden BFS, resto se
   alcanza por `scroll` + re-dump.
5. Cada fila lleva centroide de `bounds` para el gesto; el teclado IME
   **no mueve coordenadas lógicas** (los `bounds` son del árbol, no de
   pantalla física; re-dump tras IME si `ui_dirty`).

### 6.4 Ejecución y fallback sin-árbol

- Tap: `ACTION_CLICK` primero si `clickable` (apps filtran gestos
  sintéticos); si no es clickable o no se verifica → `dispatchGesture`
  al centro de `bounds`. Siempre verificar y reportar `via`.
- Type: `ACTION_SET_TEXT` con foco explícito previo (`NOT_FOCUSED`
  si no; el cliente tapea antes). Nunca teclado simulado.
- Acciones no devuelven snapshot (el servidor no dumpea tras actuar);
  el cliente verifica con `wait_for_node` / `dump_ui`.
- **Fallback Canvas/Flutter sin árbol** (`nodes == []` con ventana
  activa y sin `ui_dirty` pendiente): `screenshot` → Sistema 2
  diagnostica la anomalía visual; S1 no inventa coordenadas
  (`SELECTOR_NOT_FOUND` si no hay nodo).
- `FLAG_SECURE` no oculta el árbol; solo `screenshot` → `SECURE_SURFACE`.

### 6.5 Anti-inyección y PII

- Contenido de UI (textos de terceros, mensajes, webs) **nunca** entra
  como instrucción a S2: se etiqueta como `data`, se recorta a lo
  necesario y los prompts de tarea usan plantillas fijas con slots.
- **PII mask local:** antes de loguear/subir forense o pedir a S2,
  enmascarar en el host (números, identificadores, textos de dominio).
  El forense guarda hashes/longitudes salvo que el plugin declare
  explícitamente campos en claro para depuración.
- Sin excepciones por app: la política es del core; las listas de
  campos sensibles las parametriza cada plugin.

### 6.6 Divergencias rechazadas (AGENTS.md manda)

- **Ktor / Netty / SSE / HTTP como transporte: RECHAZADO.**
  El stack real es `Java-WebSocket` 1.5.7 (ver §8). Cualquier texto
  que presente Ktor como plan se documenta aquí como anti-patrón y
  no se implementa sin enmienda de AGENTS.md §4.
- **`0.0.0.0` como bind: RECHAZADO.** Binds: `127.0.0.1:38472` (WS)
  + IP tailnet `100.64.x.x` autodetectada (WSS obligatorio en
  no-loopback). `0.0.0.0` solo con override explícito del usuario,
  con advertencia en pantalla y auditado. Presentarlo como defecto
  es anti-patrón.
- Token bearer 32+ bytes base64url en frame `hello`, nunca en URL,
  tiempo constante, obligatorio incluso en loopback; scopes
  `read`/`ui`/`shell`/`admin`; lockout 5/60 s → 5 min; frame 4 MiB;
  audit ring 500. Sin atajos.

## 7. Árbol de herramientas MCP

Pocas tools por defecto, resto opt-in por config:

| Grupo | Tools | Default |
|---|---|---|
| `help` | `list_tools`, `describe_tool` (auto-documentación) | ✅ |
| `device` | `get_status`, `list_packages`, `get_foreground_app` | ✅ |
| `app` | `open_app`, `close_app`, `get_app_state` | ✅ |
| `ui` | `tap`, `type_text`, `scroll`, `press_back`, `press_home`, `wait_for` | ✅ |
| `jev` | `jev_decide`, `jev_next_action`, `jev_verify` | ✅ |
| `system` | `grant_permission`, `set_setting` | opt-in |
| `adb` | `adb_shell`, `adb_push/pull`, `adb_install/uninstall`, `adb_screencap` | opt-in |

Mapeo tool ↔ método: `close_app`↔`force_stop`, `adb_shell`↔`shell`,
`get_app_state`↔`dump_ui` (+normalizar), `get_foreground_app`↔`get_foreground`.

Toda tool devuelve `{ok, verified, evidence, hint}`.
Shell `adb_shell`/`shell`: denylist de irreversibles
(`rm -rf /`, `pm uninstall` de sistema, `reboot recovery`, `dd`, `wipe`)
→ requieren scope `admin` **y** `confirm: true`. Push/pull solo bajo
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
| 0d | APK vacío instalado | app visible en el TECNO + grep `su` vacío + `docs/BUILD.md` |
| 1 | AccessibilityService + `dump_ui` + onboarding | anclas ≥95% vs `uiautomator` (estático 100%); latencia §3 |
| 2 | WS loopback + `hello`/token/scopes + tap/type/scroll/back + cliente Python | cliente Python controla una app instalada genérica; sin token → rechazado |
| 2b | WSS tailnet + cert self-signed + token en Keystore *(después de 3a)* | remoto sin TLS → rechazado; pinning TOFU |
| 3a | Shizuku: `open_app`/`force_stop` + `screenshot` (`takeScreenshot`, API 30+). **Sin `shell`** | monkey/`am force-stop`/captura OK; sin Shizuku → degradación honesta |
| 3b | `shell` + audit log + kill switch *(Fase 6, seguridad cerrada)* | denylist operativa; auditoría consultable |
| 4 | MCP + normalizer + tools device/app/ui (+ optimización IPC) | agente abre una app genérica y lee pantalla |
| 5 | jev_client + loop + escalada de texto | tarea genérica con `dry_run` forense end-to-end (sin envíos reales) |
| 6 | grupo `adb`, audit log, kill switch, docs, hardening | denylist operativa; auditoría consultable |

## 10. Riesgos

- **Compilación en 2 núcleos:** mitigado con build cache + R8 solo en release.
  Plan B `-Xmx1536m`; plan C build en CI.
- **Java-WebSocket NIO en Android:** verificar en Fase 2; plan B servidor WS
  bloqueante propio (~200 líneas, 0 deps).
- **BC + Keystore:** firma SHA256withRSA OK desde API 23; sin registro JCA global.
- **API 29 sin verificar:** fallback `screencap` diseñado pero no probado.
- **USB inestable:** ambos TECNO se caen del bus cada minutos; mitigar con
  ventanas de comandos cortas y `adb connect` por Wi-Fi cuando sea posible.
- **Optimización IPC (~2 ms/nodo):** el coste está en las calls por nodo
  (`getChild`, `getBoundsInScreen`). Candidata a Fase 4+ si el bucle lo pide.
- **KJ5 corre Shizuku+ clon:** Fase 3 instala el oficial
  `moe.shizuku.privileged.api` (el LG7n ya lo trae).

## 11. Inspiración

- [docs.typesafe.ai — Jev API](https://docs.typesafe.ai/api) ·
  [introducción](https://docs.typesafe.ai/introduction) · [modelos](https://docs.typesafe.ai/models)
- [RikkaApps/Shizuku-API](https://github.com/RikkaApps/Shizuku-API)
- [NeuralBridge_mcp](https://github.com/dondetir/NeuralBridge_mcp) — latencias accesibilidad vs ADB
- [kaeawc/auto-mobile](https://github.com/kaeawc/auto-mobile) — AccessibilityService + socket
- `~/Mango-mcp` (propio): "Jev decide, no ejecuta", patrón `verified`, denylist
