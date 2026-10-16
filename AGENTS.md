# AGENTS.md — Jav

> Reglas vinculantes para cualquier agente o programador que toque este repo.
> Si una regla bloquea el trabajo, se enmienda aquí primero, no se rodea.
>
> Reparto de roles entre agentes OpenCode: ver `AGENTS-MULTIAGENT.md`
> (subordinado a este archivo). Hoja de ruta viva: `PLAN.md`.

## Estado Operativo Actual (v1.2.0)

| Área | Estado |
| --- | --- |
| Identidad | App **`Jav`**, paquete `dev.k4wai1.jav`; repo `github.com/k4wai1/jav` |
| Binario MCP | `cmd/jav` (Go, stdio JSON-RPC puro; logs solo a stderr) |
| Catálogo | **38 tools** en 4 grupos (`state`, `ui`, `native`, `resolve`) + fichas de 7 secciones bajo demanda (`android://tool/<name>`, `android://tools/<group>`, índice `android://tools/catalog`) |
| Seguridad | Token **AES-GCM/Keystore** · Lockout **5/60 s → 5 min** · **WSS tailnet** TOFU · **Audit Ring 500** · **Kill Switch** (QS tile + notificación) · **Shell Grant 1 cmd/5 min/30 min + denylist** |
| GUI (Android) | Icono 1000×1000 + launcher mipmaps + header con logo; colores semánticos `values`/`values-night` |

## 1. Filosofía

- **Jev decide, no ejecuta.** Interpreta estados, elige acciones, verifica.
  Nunca lee UI cruda, nunca mueve dedos, nunca genera texto libre.
- **Accesibilidad es la única fuente de lectura de UI.**
  Si un nodo no es visible por accesibilidad, se reporta `SELECTOR_NOT_FOUND`;
  el MCP no adivina ni inventa coordenadas.
- **Error honesto > alternativa silenciosa.** Todo fallo devuelve código
  + hint accionable. El MCP no pide confirmaciones; el agente decide.

## 2. Privilegios (app non-root)

1. **PROHIBIDO `su`.** Nada de `Runtime.exec("su")`, `su -c`,
   `ProcessBuilder("su")`. La puerta privilegiada es **solo Shizuku**.
2. Test de aceptación permanente:
   `grep -rn 'su -c\|exec(.*su\|ProcessBuilder(.*su' android-app/` → **vacío**.
3. Shizuku lo inicia el usuario. La app solo pide el permiso runtime `API_V23`.
4. Sin Shizuku: shell deshabilitado, UI viva, error `SHIZUKU_UNAVAILABLE`.
5. Sin accesibilidad: UI falla `ACCESSIBILITY_DISABLED`, `screencap` sigue vivo.
6. Shell OFF por defecto; cada ejecución requiere grant activo
   (notificación: 1 comando / 5 min / 30 min). Expira sola.
7. Shizuku lo arranca el usuario. La app solo pide permiso runtime y,
   si no corre, falla con `SHIZUKU_UNAVAILABLE` + hint accionable.
   Nunca intenta arrancarlo.
8. `shell` no se expone hasta Fase 6 (seguridad cerrada); el dispatcher
   lo rechaza con `METHOD_NOT_ALLOWED` explícito, no como desconocido.

## 3. Red y seguridad

1. Dos listeners: `127.0.0.1:38472` (WS) y la IP del tailnet
   (WSS, bind a la IP `100.64.x.x` autodetectada). **Nunca `0.0.0.0`**
   salvo override explícito del usuario, con advertencia y auditado.
2. Regla TLS por bind: `ws` **solo** en loopback; **WSS obligatorio**
   en cualquier bind no-loopback.
3. Token bearer (32+ bytes, base64url) en el frame `hello`, **nunca en URL**.
   Comparación en tiempo constante. **Token obligatorio en todos los binds,
   loopback incluido** (cualquier app del teléfono alcanza `127.0.0.1`).
   Sin token → cierre `UNAUTHORIZED`.
4. Scopes: `read` (dump_ui, screenshot) · `ui` (tap/type/scroll/back) ·
   `shell` (exec) · `admin` (rotar token, audit, settings).
5. Lockout: 5 fallos del mismo origen en 60 s → bloqueo 5 min, auditado.
6. Frame máximo **4 MiB**; rate limit 50 req/s (shell 5/s).
   `screenshot` que exceda → `PAYLOAD_TOO_LARGE` (hint: WebP q80).
7. Denylist shell (irreversibles): `rm -rf /`, `pm uninstall` de sistema,
   `reboot recovery`, `dd`, `wipe`, `settings put secure` crítico →
   scope `admin` **y** `confirm: true`. Push/pull solo bajo
   `/sdcard/Download/jav-mcp/`. Política de grant: `open_app` = `ui`
   sin grant; `force_stop` = `shell` sin grant; `grant_permission`
   y `shell` = `shell` **con grant**.
8. Audit log en dispositivo (ring buffer, **500 entradas**): método, scope,
   hash de args, resultado, timestamp, IP origen. Kill switch:
   Quick Settings tile + acción en la notificación (revoca tokens,
   detiene servidor).

## 4. Dependencias permitidas (app)

Solo estas (ver `ARCHITECTURE.md §8` para pins exactos):
`kotlinx-serialization-json`, `kotlinx-coroutines-android`,
`androidx.core:core-ktx`, `androidx.appcompat:appcompat`,
`dev.rikka.shizuku:api` + `:provider`, `Java-WebSocket`,
`bcprov-jdk18on` + `bcpkix-jdk18on`.

Prohibido sin enmienda: Compose, Hilt/Dagger, Room, Retrofit,
Ktor, Tink/security-crypto, SDK de Tailscale, KSP/KAPT, Espresso.
`minSdk 29`, `compileSdk/targetSdk 34`, Kotlin puro, R8 solo en release.

## 5. Gotchas Android (no negociables)

1. **Plugin de serialización obligatorio:**
   `org.jetbrains.kotlin.plugin.serialization` (misma versión que Kotlin)
   en `app/build.gradle.kts`. Sin él, kotlinx-serialization no compila.
2. **Provider de Shizuku en el manifest** (`ShizukuProvider` con su
   authority). Sin él, el permiso runtime nunca llega.
3. **BouncyCastle sin registro JCA global.** Usar `JcaX509v3CertificateBuilder`
   + `JcaContentSignerBuilder` con el provider pasado explícito
   (Android trae su BC recortado; registrarlo global colisiona).
4. **Package visibility:** `<queries>` con intent MAIN (o `QUERY_ALL_PACKAGES`,
   sideloaded) para `list_packages` / `open_app`.
5. **`open_app` por Shizuku** (`am start`): background activity start
   restringido desde Android 10, nunca Intent directo desde background.
   Fallback: `monkey -p <pkg> -c android.intent.category.LAUNCHER 1`.
6. **FGS target 34:** `foregroundServiceType="specialUse"` + property
   `PROPERTY_SPECIAL_USE_FGS_SUBTYPE` + permiso
   `FOREGROUND_SERVICE_SPECIAL_USE`.
7. **`takeScreenshot()` es API 30+:** en API 29, fallback `screencap`
   vía Shizuku. Dispositivo de referencia: TECNO API 31
   (el fallback 29 queda sin verificar hasta tener equipo).
8. **Recorrido del árbol iterativo** (stack/BFS), máx. 500 nodos/snapshot.
   Nunca bloquear `onAccessibilityEvent`; marcar `ui_dirty` y servir
   snapshot bajo demanda. `dump_ui` devuelve `snapshot_id` monotónico
   persistido; `tap_node`/`type` lo exigen (`STALE_SNAPSHOT` si cambió la UI).
9. Re-detección de IP tailnet con **`ConnectivityManager.NetworkCallback`**
   (el broadcast `CONNECTIVITY_CHANGE` está restringido desde Android 7)
   + override manual en ajustes.
10. **Nodos de decoración del sistema** (`statusBarBackground`,
    `navigationBarBackground`) aparecen en `dump_ui` pero nunca son
    target de acción: **filtrarlos en `ui_normalizer.py`** (Fase 4),
    no en el extractor.
11. **`FLAG_SECURE` no oculta el árbol de accesibilidad** (TalkBack
    funciona en banca); solo bloquea capturas. Por eso `dump_ui` no
    lleva campo `secure`: la semántica de superficie protegida vive
    solo en `screenshot` → `SECURE_SURFACE`. `root == null` significa
    "sin ventana activa" (típicamente transitorio), no "seguro".
12. **`takeScreenshot()` es asíncrono con callback**: usar `CountDownLatch`
    + timeout; `ERROR_TAKE_SCREENSHOT_SECURE_WINDOW` → `SECURE_SURFACE`.
    El `HardwareBuffer` **debe copiarse** (`wrapHardwareBuffer` + `copy`
    a `ARGB_8888`) **antes de `close()`**, o el bitmap sale corrupto.
    En API 30+, WebP = `WEBP_LOSSY` (`WEBP` deprecado).
13. **Preferir `tap_node(id, snapshot_id)` sobre `tap(selector)`**
    cuando el cliente ya tiene snapshot fresco: el primero no dumpea
    internamente (el `tap` por selector sí).
14. **Precondiciones deterministas obligatorias** (bucle Jev): cada fase
    que pueda enviar verifica en código (título del chat, texto en input,
    botón real). Jev elige el target; la compuerta la pone el código.
    Sin compuerta verde no hay acción sensible.
15. **Blacklist de acciones** (`reenviar|forward|compartir|share|
    eliminar|delete`): filtrar en criterios y abortar si Jev lo elige
    (`FORBIDDEN_TARGET`). Nunca tapear dentro de un chat ajeno buscando
    reintentos (abre UIs de selección/reenvío).
16. **Forense por corrida**: `logs/run-<ts>.jsonl` con fase, snapshot,
    opciones, respuestas y acción por paso. Sin forense, un incidente
    es indiagnosticable.

## 6. Protocolo y tools

- Contrato exacto en `PROTOCOL.md`. `protocol_version` en el handshake;
  mismatch → cierre con error claro.
- Respuestas de tools MCP: `{ok, verified, evidence, hint}`.
- Taps: si el nodo es `clickable` → **`performAction(ACTION_CLICK)`
  primero** (varias apps filtran gestos sintéticos); si no es clickable
  o no se verifica → `dispatchGesture` al centro de `bounds`.
  **Siempre verificar** (`wait_for_node`/`dump_ui`) y reportar `via`.
  `ACTION_SET_TEXT` para type (nunca teclado simulado).
- Acciones **no devuelven snapshot**: el servidor no dumpea tras actuar
  (latencia incondicional por un ahorro condicional). El cliente verifica
  con `wait_for_node` / `dump_ui` cuando le importa.
- `type` **exige foco explícito**: si el nodo no está `focused` →
  `NOT_FOCUSED`. El cliente hace `tap` previo; nada de taps implícitos.
- Sin key de Jev → stub `{mock: true}`. Jev nunca inventa opciones.
- Acciones compuestas (`run_sequence`) prohibidas: granularidad para el loop.
- Política single-client: un solo cliente WS activo; el segundo → `BUSY`.
- Mapeo tool MCP ↔ método: `open_app`↔`open_app`,
  `close_app`↔`force_stop`, `get_app_state`↔`dump_ui` (+normalizar),
  `get_foreground_app`↔`get_foreground`, `adb_shell`↔`shell`.

## 7. Build en esta máquina

- SDK y caches en `~/Android/Sdk` y `~/.gradle` (**jamás en `/`**).
- `gradle.properties` conservador + `org.gradle.caching=true`
  + `org.gradle.workers.max=1`. Builds serializados (`-j1` mentalidad).
- `local.properties` con `sdk.dir`. Debug sin minify; release con R8.
- Documentar cada build real en `docs/BUILD.md` (comando, tiempo, RAM).

## 8. Entregables por fase

Código compilable + `README.md` en `android-app/` + `docs/PROTOCOL.md`
actualizado + `docs/TESTING.md` con comandos manuales (adb/nc/wscat,
sin Android Studio). Sin código sin documentación.

## 9. Enmiendas (trazabilidad)

**2026-09-30 — revisión pre-0b, 8 enmiendas aplicadas:**

1. Frame máximo 1 → **4 MiB**; `screenshot` > 4 MiB → `PAYLOAD_TOO_LARGE`
   (hint WebP q80). *(PROTOCOL §1, §4)*
2. **Token obligatorio en todos los binds, loopback incluido.**
   Reversión de "loopback sin token → read+ui": cualquier app del teléfono
   alcanza `127.0.0.1`. *(PROTOCOL §3, AGENTS §3.3)*
3. Esquema de `selector` definido: `{text, text_contains, resource_id
   (sufijo), content_desc, class, clickable, index}`, AND, primer match
   BFS, determinista. *(PROTOCOL §4.0)*
4. Flujo de grant de `shell`: **bloquea hasta 60 s**; 1-comando = SHA-256
   exacto del string; 5/30 min = ventana; evento `shell_grant` con
   `sha256`. *(PROTOCOL §4, §6)*
5. Taps: **`ACTION_CLICK` primero** si `clickable` (apps filtran gestos);
   `dispatchGesture` como fallback; **siempre verificar + `via`**.
   *(AGENTS §6)*
6. `snapshot_id` monotónico en `dump_ui`; `tap_node`/`type` lo exigen;
   mismatch → `STALE_SNAPSHOT`. *(PROTOCOL §4, §5, §7)*
7. `screenshot` en `FLAG_SECURE` → error `SECURE_SURFACE`
   (no imagen negra silenciosa). *(PROTOCOL §4)*
8. `hello`: `app_version_expected` → **`client_version`** (el cliente no
   puede saber la versión de la app antes de conectar). *(PROTOCOL §2)*

No bloqueantes anotados (resolver en su fase): ring buffer 500
(`get_audit`, Fase 6); mapeo tool↔método (Fase 4);
`ConnectivityManager.NetworkCallback` (Fase 2);
single-client `BUSY` (Fase 2); permiso `FOREGROUND_SERVICE_SPECIAL_USE`
(Fase 0c); fallback `monkey` en `open_app` (Fase 3); `nodes` array plano
(Fase 1); política de grant por método (Fase 3, confirmada en §3.7).

**2026-10-01 — arranque Fase 1:**

1. App (nombre de arranque) = `Jam`, paquete `dev.jev.jam` (antes
   `dev.jev.android`); consolidado a **Jav** / `dev.k4wai1.jav` el
   2026-10-16 (ver enmienda de consolidación de identidad).
2. Banco principal = TECNO KJ5 (API 33, non-root); LG7n secundario.
3. Aceptación Fase 1 relajada: match ≥95% en nodos con `text`/`resource_id`
   vs `uiautomator` + latencia < 100 ms (no identidad total de árboles).
4. `distributionUrl` del wrapper vuelve a URL remota (portabilidad);
   el zip local solo como truco no-commiteado (ver `docs/BUILD.md`).
5. KJ5 corre el clon Shizuku+ (`af.shizuku.plus.api`): no usar como
   referencia; Fase 3 instalará el oficial `moe.shizuku.privileged.api`.
6. Onboarding UI mínima entra en Fase 1 (banco visual del `dump_ui`).

**2026-10-02 — pre-Fase 2, latencia y `secure` re-ratificados:**

1. Criterio de latencia: **≤300 ms para ≤150 nodos; ~2 ms/nodo;
   peor caso ~1 s a 500 nodos** (medido: 13n/40 ms, 66n/106 ms,
   124n/264 ms). El "~30 ms" de `ARCHITECTURE §3` era teórico.
   Optimización del IPC por nodo (2–3×): candidata a Fase 4+.
2. **`secure` eliminado de `dump_ui`**: `FLAG_SECURE` no oculta el árbol
   (TalkBack); `root == null` = sin ventana activa (transitorio).
   Superficie protegida solo en `screenshot` → `SECURE_SURFACE`.
   (`AccessibilityWindowInfo.isSecure()` no existe en API 34.)
3. Contrato de acciones: **sin post-snapshot** en respuestas
   (el servidor no dumpea tras actuar); **`type` exige foco**
   (`NOT_FOCUSED` si no; el cliente tapea explícito antes).

**2026-10-02 — Fase 3a parcial antes de 2b:**

1. Alcance 3a: `open_app` + `force_stop` (Shizuku) + `screenshot`
   (`takeScreenshot`, API 30+). **`shell` diferido a Fase 6** con
   seguridad cerrada; el dispatcher lo rechaza explícito.
2. Fase 2b (WSS/cert/Keystore) diferida a después de 3a.
   Sin API 29 fallback (no hay dispositivo API 29).
3. Shizuku lo arranca el usuario; sin él → `SHIZUKU_UNAVAILABLE` + hint.
   Banco 3a: LG7n (Shizuku oficial). Contacto de prueba: Felix.
4. Deuda Fase 2 (antes de Fase 4): preferir `tap_node` sobre
   `tap(selector)`; el `snapshot_id` del `wait_for_node` es usable
   directo si no hubo evento; reintento `STALE_SNAPSHOT` en el bucle,
   no en la app.

**2026-10-02 — post-incidente, compuertas antes de envíos:**

1. Envío real a chat equivocado en pruebas: causas = sin compuerta
   de identidad + verificación solo-local + sin precondiciones.
   Respuesta: `VERIFY_CHAT` con título estricto, blacklist, dry-run
   por defecto, forense JSONL por corrida. (§5.14–16)
2. `noop` entra al enum del loop (fases de solo-verificación;
   se loguea, no toca el dispositivo).
3. Avance de fase sobre fase que PREGUNTÓ (no la avanzada):
   la acción se rige por `asked`, no por `self.phase` post-salto.
   (Bug cazado por forense: el gate de SEND nunca disparaba.)
4. Reintentos VERIFY solo fuera de chats; dentro → `WRONG_CHAT`
   sin tapear (evita UIs de selección/reenvío).
5. `screen_height` vía `adb shell wm size` (cacheado) para el
   fallback posicional del título; `bounds` expuesto en `read_screen`.
6. Dry-run ×N antes de cualquier envío real; `--confirm-real-send`
   explícito para desactivarlo.

**2026-10-05 — giro a agente simple 100% general (dual-tier S1+S2):**

1. Visión vinculante: agente simple y general `run_goal(goal: str)`,
   cero paquetes/parámetros prefijados. Nada de WhatsApp/contactos/
   `VERIFY_CHAT`/`WRONG_CHAT` de chats/dry-run-de-chats como mecanismo
   del core. Contrato en `docs/specs/generic-dual-tier.md` (sustituye
   operativamente a `docs/specs/tasks-generic.md` v2).
2. Dual-tier: **S1 Jev (OpenRouter)** decide en un pass
   `[TAP,TYPE,SCROLL_DOWN,SCROLL_UP,BACK,DONE,ESCALATE] + target
   0..253+NONE + needs_system_2**; **S2 GLM 5.3 (misma
   `OPENROUTER_API_KEY`)** ante `ESCALATE` / `conf<0.70` / redacción
   abierta. Poda **0..253+NONE = 255 Choice**. `CostTracker:
   track(model, in/out tokens) → USD`, log `[COST]`.
3. Tarifas: **Jev $0.042 in / $0.00 out por MTok** (normativo);
   **GLM-5.3 con tasa configurable vía env** (default documentado como
   placeholder ajustable, p.ej. `GLM_RATE_IN`/`GLM_RATE_OUT`, nunca
   hardcodear como verdad oficial).
4. Seguridad: §5.14-16 y §6 nacieron de un envío real a chat
   equivocado y **no se derogan en silencio**. Se retiran los
   **literales app-específicos** (`com.whatsapp`, `contact_name`,
   `VERIFY_CHAT`/`WRONG_CHAT` de chats, dry-run-de-chats, regex
   `reenviar|forward|compartir|share|eliminar|delete|borrar` como
   default global) y se sustituyen por política **genérica**:
   validaciones estructurales siempre (coords en pantalla, nodo
   visible, JSON válido, snapshot fresco) + confirmación explícita
   para acciones críticas/irreversibles (enviar/comprar/borrar/cuenta)
   con preview + `confirm:true` del operador, auditadas en forense.
   El default `FORBIDDEN` pasa a **opt-in por goal** (el operador
   declara sus patrones si el goal lo exige), nunca global.
5. `tasks/` se elimina (`whatsapp.py`, único acoplado; `core`/`loop`/
   `server`/`tools` ya limpios). `core/guards.py:10`
   (`FORBIDDEN_DEFAULT`, consumido solo por el plugin) muere con él.
   `tests/test_guards.py:2` y `scripts/fase5_check.py` que lo importan
   quedan rotos a propósito y **los actualiza `@coder`** (fuera del
   alcance de `@architect`, que no toca código).

**2026-10-15 — 36.ª tool `resolve_element` + fallback `ACTION_PASTE`:**

1. `resolve_element` (resolver ciego S1) se registra como **tool MCP oficial**
   (antes solo invocable desde Go interno). Params `screen_goal_en` (req) +
   `tau` (number, default 0.70). Envuelve `director.ResolveElementWithTau` con
   los `tried_node_ids` vigentes (`pkg/uitrack`) y devuelve `{ok, verified,
   evidence, hint}` con `idx`/`node_id`/`conf`/`snapshot_id` o el Fallback
   Soberano (`fallback_required`, `top_candidates`, `recovery_instruction`).
   El árbol pasa de 35 a **36 tools** (6 UI atómicas + 30 director/nativo).
   `cmd/audit-mcp` verifica `tools-count-36` (11/11 PASS).
2. `type_text` en Jav: si el nodo está enfocado pero `ACTION_SET_TEXT` falla
   (típico de inputs en WebView), **fallback `ACTION_PASTE`** vía
   `ClipboardManager.setPrimaryClip` + `performPaste()`; si ambos fallan,
   `INTERNAL_ERROR` honesto. La respuesta ahora incluye `via`
   (`action_set_text`|`action_paste`), igual que `tap_node`, para trazabilidad
   del Director/forense (PROTOCOL §4).
3. `cmd/audit-mcp` deja de tener el race de stdin: mantiene el pipe abierto y
   lee incremental hasta reunir las 5 respuestas (cerrar stdin → EOF disparaba
   el shutdown de `ServeStdio` y podía perder las tool calls en vuelo; hacía
   flaky `error-isError-id{3,4,5}`). 15/15 estable. `README.md`, `cmd/jav-e2e`
   y `dist/` sincronizados a 36 tools.

**2026-10-16 — Fase 6a: audit ring 500 + Kill Switch + 37.ª tool `get_audit`:**

1. **Audit en dispositivo** (`AGENTS §3.8`): `socket/AuditLog.kt` (puro JVM,
   ring **500** entradas, `ArrayDeque`+lock). `AuditEntry = {seq, ts, method,
   scope, args_sha256, result, origin}`; `args_sha256` = **16 hex** del
   SHA-256 de `params.toString()` (**nunca** args/token en claro); `origin`
   = `loopback` | IP. `CommandDispatcher.hello/dispatch` reciben `origin` y
   registran cada intento (OK o `code`) con `scopeOf` =
   `read|ui|n0|n1|auth|admin`. Método WS **`get_audit`** (`limit` 1..200
   default 50, `since_seq` default 0) → `{total_buffered, returned,
   entries[]}`. El token bearer único habilita `admin` en `hello.scopes`.
2. **Kill Switch** (`AGENTS §3.8`):
   `ACTION_KILL_SWITCH="dev.k4wai1.jav.action.KILL_SWITCH"`; rota token
   (`AuthStore.regenerateToken`), audita `kill_switch`, `revokeAll()` +
   `shutdown()` + `stopForeground(REMOVE)` + `stopSelf()`. Botón en la
   notificación (`PendingIntent.getService`, `FLAG_IMMUTABLE`) y
   `service/JamKillSwitchTile.kt` (`TileService`, `BIND_QUICK_SETTINGS_TILE`,
   `exported=true`). El árbol pasa de 36 a **37 tools**; `cmd/audit-mcp`
   verifica `tools-count-37` (11/11 PASS). Kotlin **64/64**.

**2026-10-16 — Fase 6b: `shell` con denylist + grant + N2 + 38.ª tool `adb_shell`:**

1. `shell/ShellPolicy.kt` (JVM puro): denylist de irreversibles
   (`rm -rf /`, `pm uninstall`, `reboot recovery`, `dd`, `mkfs`, `wipe`,
   `settings put secure/global` crítico) + self-harm (`SELF`), rate 5 req/s,
   `sha256Hex`. `ShellGrantManager.kt`: notificación con botones
   `1 cmd`/`5 min`/`30 min`/`Denegar`, bloqueo 60 s, evento WS `shell_grant`.
   N2 vivo (`get_storage`/`get_cpu` fine, `settings_put`). 38.ª tool
   `adb_shell` (`pkg/jam.Shell`, `pkg/tools/shell.go`). `cmd/audit-mcp`
   `tools-count-38` (11/11). Kotlin **73/73**. `BUILD.md §20`.

**2026-10-16 — Fase 2b: WSS tailnet + cert self-signed + token en Keystore + lockout:**

1. `socket/AuthLockout.kt` (JVM puro): 5 fallos `UNAUTHORIZED` del mismo
   `origin` en 60 s → bloqueo 300 s; `hello` bloqueado → `UNAUTHORIZED` +
   audit. `socket/AuthStore.kt`: token **AES-GCM/256** en `AndroidKeyStore`
   (`ws_token_enc`, migración suave del plano). `socket/TlsCertStore.kt`:
   cert X.509v3 autofirmado `CN=jav.local` (BC **local**, sin registro JCA
   global) con PKCS#12 cifrado en `filesDir`; 2.º listener WSS bindeado a la
   IP tailnet (`100.64.0.0/10`) vía `net/TailnetDetector.kt` (`NetworkCallback`),
   **nunca `0.0.0.0`**. Go: `wss://` + pinning TOFU
   (`JAV_CERT_FINGERPRINT`/`JEV_CERT_FINGERPRINT`, tiempo constante,
   `CERT_MISMATCH`). Kotlin **88/88**. `BUILD.md §21`; cierra el 100 % del
   roadmap `ARCHITECTURE.md §9`.

**2026-10-16 — Consolidación de identidad: `Jav` / `dev.k4wai1.jav` (vinculante):**

1. **App = `Jav`**, paquete `dev.k4wai1.jav` (namespace + `applicationId`);
   árbol `java/`+`aidl/` movido a `dev/k4wai1/jav`; `SELF_PACKAGE`/`SELF` y
   `ACTION_*` = `dev.k4wai1.jav.*`; label/canal/notificaciones visibles `Jav`.
   Repo = `github.com/k4wai1/jav`; `rootProject.name = "jav-android"`.
2. **Identificadores internos que NO se renombran** (no son nombre de
   proyecto): paquete Go `pkg/jam` (+ tipos `jam.Envelope`/`JamError`), modelo
   `pkg/jev` (`JEV_MODEL`, S1) y clases Kotlin `Jev*`/`Jam*`-técnicas
   (`JevForegroundService`, `JamWsServer`, `JamKillSwitchTile`, …). Solo
   cambia el **texto visible** (`Jav`) y el **paquete** (`dev.k4wai1.jav`).
3. **Migración de token en el dispositivo:** la app nueva no hereda el
   Keystore; se conserva el token sembrando el `ws_token` plano del `.env`
   antes del primer arranque → migración suave a `ws_token_enc` (evita
   re-generar token y romper `.env`). `logs/run-*.jsonl`,
   `pkg/normalizer/testdata/` y `mcp-server/` conservan el nombre viejo como
   evidencia forense (no se reescriben).

**2026-10-16 — v1.2.0: eficiencia de tokens, costo silencioso, icono/UI y poda documental:**

1. **`tools/list` compacto + fichas bajo demanda:** las 38 tools conservan su
   nombre/schema y pasan a una descripción de 1-2 líneas
   (`CompactDesc`, `pkg/tools/catalog.go`). El contrato cognitivo de 7 secciones
   se conserva íntegro en `FullToolDocs` y se sirve bajo demanda por Resource
   (`android://tool/{name}`, `android://tools/<group>`, `android://tools/catalog`).
   Se retiran los `title` redundantes por propiedad del schema. La carga
   cognitiva de arranque (instructions + descripciones) baja de ~8.8k a ~1.6k
   tokens; `cmd/audit-mcp` añade el check `token-budget-startup` (≤3000 tokens de
   carga) y `initialize-instructions` se acota a ≤220 palabras. 12/12 PASS.
2. **CostTracker silencioso:** `pkg/cost.Track` deja de imprimir a stderr por
   llamada (solo bajo `JAV_DEBUG_COST=1`) y acumula un resumen global de sesión
   (`SessionSummary()` → `{jev_cost_usd, s2_cost_usd, total_cost_usd, calls}`)
   que viaja en `evidence.cost` de `device_status` y `resolve_element`.
3. **Identidad de certificado unificada** a `CN=jav.local` (código, tests y
   docs), y barrido de gazapos post-rename (`Javás` → `Jamás`).
4. **Icono 1000×1000** (`docs/assets/icon.png`) + mipmaps de launcher
   (`ic_launcher[_round]` mdpi..xxxhdpi), `android:icon`/`android:roundIcon` en
   el manifest, header con logo y colores semánticos
   `values`/`values-night` (+ `dimens.xml`) sin dependencias nuevas.
   `versionName 1.2.0` / `versionCode 2`.
5. **Poda documental:** specs históricos movidos a `docs/specs/archive/`
   (marcados `> ARCHIVED`); vigentes en `docs/specs/`. Tabla de estado en este
   archivo y `README.md` reescrito (Quickstart, 4 grupos, `What changed in v1.2.0`).
