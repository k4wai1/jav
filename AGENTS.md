# AGENTS.md — jev-android-mcp

> Reglas vinculantes para cualquier agente o programador que toque este repo.
> Si una regla bloquea el trabajo, se enmienda aquí primero, no se rodea.

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
   `/sdcard/Download/jev-mcp/`. Política de grant: `open_app` = `ui`
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

1. App = **Jam**, paquete `dev.jev.jam` (antes `dev.jev.android`).
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
