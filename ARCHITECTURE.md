# jev-android-mcp — ARCHITECTURE

> Documento vinculante. Toda decisión de implementación que contradiga este archivo
> requiere una enmienda explícita aquí antes de codear. Estado: **cerrada** (2026-09-30).
> Enmiendas pre-0b y pre-Fase-2 registradas en `AGENTS.md §9`.

## 1. Visión

MCP definitivo para controlar Android con un agente en lenguaje natural
("entra a mi WhatsApp, busca a Juan y dile que voy pronto").
Arquitectura de **dos modelos**:

- **Agente principal (LLM, vía MCP):** lenguaje natural, todo el texto,
  tareas de alto nivel, recuperación de errores.
- **Jev (TypeSafe System One, bucle interno):** decide *qué elemento tocar*,
  *qué acción sigue*, *¿terminó?*, *¿se verificó?*. Nunca genera texto ni coordenadas.

La app Android es un **compañero headless non-root**: expone percepción
(AccessibilityService) y ejecución (gestos + shell UID 2000 vía Shizuku)
por WebSocket. El MCP Python traduce tools → comandos y orquesta el bucle
`observe → decide → mutate → verify`.

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

## 6. Jev — contrato y split de modelos

Endpoint por defecto: `POST https://openrouter.ai/api/alpha/decisions`
(`model: "typesafe/jev-1.13"`). Oficial (swap futuro):
`POST https://api.typesafe.ai/v1/systemone` (`model: "jev-latest"`).
Latencia 70–500 ms por llamada. Batch de preguntas en una sola llamada.

```json
{"model": "typesafe/jev-1.13",
 "state": {"package": "…", "screen": "…", "elements": […]},
 "questions": {
   "next_action": {"type": "choice", "instructions": "…",
                   "criteria": {"buscar": "…", "enviar": "…"}},
   "ready":       {"type": "noul",   "instructions": "…",
                   "criteria": {"true": "…", "false": "…"}},
   "done":        {"type": "score",  "instructions": "…",
                   "criteria": ["no", "parcial", "sí"]}}}
→ {"answers": {…}, "model_version": "…"}
```

**Split:** Jev decide, no ejecuta. El MCP lee UI (accesibilidad),
normaliza a estado semántico, pregunta, ejecuta, verifica.
Cuando Jev decide "escribir", el MCP devuelve al agente principal
`{"needs_text": true, "slot": "…", "prompt": "…"}` y este provee el texto.
Sin key → **stub mock honesto** (`{mock: true, …}`), nunca inventar.

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
| 2 | WS loopback + `hello`/token/scopes + tap/type/scroll/back + cliente Python | cliente Python controla WhatsApp real; sin token → rechazado |
| 2b | WSS tailnet + cert self-signed + token en Keystore | remoto sin TLS → rechazado; pinning TOFU |
| 3 | Shizuku + open_app/force_stop/grant/shell (+ `screenshot` fallback) | `pm grant`, `am start`, `screencap` OK; sin Shizuku → degradación honesta |
| 4 | MCP + normalizer + tools device/app/ui (+ optimización IPC) | agente abre WhatsApp y lee pantalla |
| 5 | jev_client + loop + escalada de texto | "escribe a Juan: voy pronto" end-to-end |
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
