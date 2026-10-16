# BUILD.md — toolchain y builds reales (Fase 0)

Máquina: Debian 13, Celeron 847 (2 núcleos @ 1.1 GHz), 3.7 GiB RAM + 7.5 GiB swap.
Todo bajo `/home` (en `/` solo hay 11 GB libres). Fecha: 2026-09-30.

## 1. Toolchain (una vez)

```bash
mkdir -p ~/Android/Sdk/cmdline-tools
curl -L -o /tmp/cmdline-tools.zip \
  https://dl.google.com/android/repository/commandlinetools-linux-11076708_latest.zip  # 153 MB
unzip -q /tmp/cmdline-tools.zip -d ~/Android/Sdk/cmdline-tools
mv ~/Android/Sdk/cmdline-tools/cmdline-tools ~/Android/Sdk/cmdline-tools/latest
export ANDROID_HOME=$HOME/Android/Sdk ANDROID_SDK_ROOT=$HOME/Android/Sdk
export PATH=$ANDROID_HOME/cmdline-tools/latest/bin:$ANDROID_HOME/platform-tools:$PATH
yes | sdkmanager --licenses
sdkmanager "platform-tools" "platforms;android-34" "build-tools;34.0.0"
```

Instalado: `build-tools 34.0.0`, `platform-tools 37.0.1`, `platforms android-34`.
Persistido en `~/.zshrc` (`ANDROID_HOME`, `ANDROID_SDK_ROOT`, `PATH`).
Tamaños: `~/Android/Sdk` = 458 MB, `~/.gradle` (tras primer build) = ~1 GB.

Gradle: `gradle-8.7-bin.zip` (134 MB) en `~/opt/`, usado para generar el
wrapper. `gradle-wrapper.properties` apunta a la URL remota (portabilidad);
para evitar la re-descarga en esta máquina se puede apuntar temporalmente a
`file:///home/luis/opt/gradle-8.7-bin.zip` con `validateDistributionUrl=false`
(solo local, no commitear ese cambio).

## 2. Builds medidos (`./gradlew assembleDebug`)

| Build | Resultado | Tiempo (reportado por Gradle) | Notas |
|---|---|---|---|
| 1.º (caché frío, todas las deps) | FALLA en `mergeDebugJavaResource` | 25m 48s | Duplicado `META-INF/versions/9/OSGI-INF/MANIFEST.MF` en los 3 jars BC |
| 2.º (fix MANIFEST) | FALLA en `mergeDebugJavaResource` | 3m 29s | Siguiente duplicado: `META-INF/LICENSE.md` (misma familia BC) |
| 3.º (fix set completo) | **OK** | 4m 14s | APK debug 16 MB (sin minify; BC+deps pesan) |

RAM: sin OOM con `-Xmx1024m` + `workers.max=1` (swap activo; no se midió pico).

Fix aplicado en `app/build.gradle.kts` (bloque `packaging.resources.excludes`):
`META-INF/versions/9/OSGI-INF/MANIFEST.MF`, `META-INF/LICENSE*`,
`META-INF/NOTICE*`, `META-INF/*.SF|DSA|RSA`.

APK: `android-app/app/build/outputs/apk/debug/app-debug.apk` (16 MB).

## 3. Verificación sin dispositivo (hecha)

- `grep -rn 'su -c\|exec(.*su\|ProcessBuilder(.*su' app/src/` → **vacío** ✓
- `strings classes{,2,3,4,5}.dex | grep -c 'su -c'` → **0** ✓
- `apkanalyzer manifest print`: `package=dev.k4wai1.jav`, 2 servicios,
  `ShizukuProvider` (`dev.k4wai1.jav.shizuku` + `INTERACT_ACROSS_USERS_FULL`),
  permiso `moe.shizuku.manager.permission.API_V23` fusionado,
  `FOREGROUND_SERVICE_SPECIAL_USE`, property FGS ✓

## 4. Instalación y verificación en dispositivo (HECHA 2026-10-01)

El TECNO LG7n (target) se cayó del USB; se verificó en un **TECNO KJ5,
Android 13 (API 33)**, sin root, con Shizuku y Tailscale instalados
(equipo ideal para la ruta non-root + Shizuku).

```bash
adb install -r app/build/outputs/apk/debug/app-debug.apk   # Success
adb shell am start -n dev.k4wai1.jav/.MainActivity
adb shell 'dumpsys activity activities | grep -m1 mFocusedApp'
# mFocusedApp=ActivityRecord{… dev.k4wai1.jav/.MainActivity} ✓
```

`uiautomator dump` confirma el paquete en foreground con `android:id/content`
**vacío** (sin hijos): la pantalla gris es la Activity stub sin `setContentView()`,
comportamiento esperado de Fase 0. La UI real de onboarding llega en Fase 1.

Criterio Fase 0d: app instalada y en foreground ✓ + grep `su` vacío ✓ + este archivo ✓.

## 5. Fix escalado de gestos (2026-10-07, 5002E/Android 10 API 29, USB e03638e5)

Causa: `getBoundsInScreen` en espacio lógico (override 360x720) vs
`dispatchGesture` en píxeles físicos (panel 720x1440). Fix: `DisplayScale`
(`ui/DisplayScale.kt`) + proyección en `JevAccessibilityService`
(tap-gesto y scroll). Fórmula: `x_phys=(x_log*physW+logW/2)/logW`
(idem Y), clamp a físico-1; `bounds` de `dump_ui` queda en lógico.

```bash
./gradlew :app:testDebugUnitTest --tests "dev.k4wai1.jav.ui.DisplayScaleTest" --tests "dev.k4wai1.jav.ui.UiTreeExtractorTest"
./gradlew :app:assembleDebug
adb -s e03638e5 install -r app/build/outputs/apk/debug/app-debug.apk   # Success
```

| Build | Resultado | Tiempo Gradle | Notas |
|---|---|---|---|
| test (DisplayScale 5 tests, 1 fallo assertion propia) | FALLA 1 | 4m 19s | assertion `projectX(1)=1` errónea (real 2); corregida |
| test (DisplayScale 5 + Extractor 6) | **OK** | 3m 4s | 11 tests verdes |
| assembleDebug (fix gestos) | **OK** | 2m 22s (wall 144s) | APK debug 16 MB |

RAM: 3.7 GiB + swap; `free` durante build: ~2.9 GB usados / ~290 MB libres
+ 754 MB swap. `gradle.properties` conservador intacto (`workers.max=1`,
`Xmx1024m`, sin daemon, sin paralelo).

## 6. Catálogo native-apis N0+N1 (2026-10-07, 5002E/API 29, USB e03638e5)

Cambios: `nat/` nuevo (`NatPolicies`, `NativeDevice`, `NativeSensitive`,
`CameraCapture`), `JamNotificationListener`, 20 métodos en el dispatcher
+ params en `WsProtocol.kt`, 8 permisos N1 + servicio NL en el manifest,
onboarding de grants en `MainActivity`. Sin deps nuevas, sin `0.0.0.0`,
sin `su` (grep específico limpio; el match `exec(.*su` en
`ShizukuBridge.kt:118` es falso positivo pre-existente: `ExecResult`).

```bash
./gradlew :app:testDebugUnitTest --tests "dev.k4wai1.jav.nat.*" :app:assembleDebug
adb -s e03638e5 install -r app/build/outputs/apk/debug/app-debug.apk   # Success
```

| Build | Resultado | Tiempo Gradle | Notas |
|---|---|---|---|
| test NatPolicies (8 tests JVM) | **OK** | incl. abajo | reglas puras: intents críticos, paquetes, URLs, ventanas, settings, truncado |
| test+assembleDebug | **OK** | 3m 32s | APK debug 16 MB; 3 errores de compilación propios corregidos (paréntesis, RemoteInput framework, `CameraDevice.TEMPLATE_*`) |

Verificación hello + 25 llamadas WS en el equipo (token por `run-as`,
grants de test por adb-host: `pm grant` ×7, `appops` uso/WRITE_SETTINGS,
`allow_listener`): N0 todo OK; N2 (`settings_put` secure/global,
`detail=fine`) → `METHOD_NOT_ALLOWED`; críticas sin `confirm` →
`planned+preview`; `settings_put` System + `add_contact` + `create_event`
con `confirm:true` ejecutan y se revirtieron (contacto/evento de prueba
borrados, brillo restaurado); `take_photo` con `confirm` → JPEG 1280×720
real (21 KB b64); ubicación/Notificaciones honestas (ver §7).

## 7. Estado del banco 5002E tras la prueba (para el operador)

- Reboot intermedio: el servidor WS quedó sin escucha con proceso vivo
  (rancio tras `install -r` + `force_stop`); reboot lo dejó OK
  (`netstat` → `127.0.0.1:38472` LISTEN). Sin cambios de código por esto.
- Accesibilidad y Shizuku aparecen `false` en `hello.caps` tras el reboot:
  hay que re-habilitar Jav en Ajustes → Accesibilidad y arrancar Shizuku.
- `enabled_notification_listeners` acepta el componente por adb pero el
  sistema no lo enlaza; la pantalla de Ajustes dice "Esta característica
  no está disponible en este dispositivo": NL imposible en el 5002E
  (`list_notifications`/`reply`/`media_*` quedan en error honesto).
- Sin SIM/GPS interior: `get_location` → `LOCATION_TIMEOUT` honesto.
- Artefactos de prueba revertidos: contacto `JevTestDelete` y evento
  `JevTestDelete` borrados; `screen_brightness` restaurado a `10`.
- Suite MCP: 146 passed (incl. `test_native_tools.py`, 7 tests con stubs).

## 8. Ventana `today`/`week` en `get_app_usage` (2026-10-07, 5002E/API 29, USB e03638e5)

`get_app_usage` topaba en 24 h (`clampHours` 1..24, `INTERVAL_DAILY`).
Ahora acepta `window` opcional: `today` (medianoche local),
`week` (7 días) y `raw` (`hours` 1..168); sin `window` = comportamiento
previo `hours`. El cálculo de `begin` se factoriza a `NatPolicies.usageBegin`
(puro JVM, `Calendar` para medianoche local) y suma
`totalTimeInForeground` por paquete en el rango (top 50). MCP expone
`get_app_usage(hours=24, window=None)`.

```bash
./gradlew :app:testDebugUnitTest --tests "dev.k4wai1.jav.nat.NatPoliciesTest" :app:assembleDebug
adb -s e03638e5 install -r app/build/outputs/apk/debug/app-debug.apk   # Success
```

| Build | Resultado | Tiempo Gradle (wall) | Notas |
|---|---|---|---|
| test NatPolicies (11 tests JVM) + assembleDebug | **OK** | 4m 20s (261s) | APK debug 16 MB; 11/11 verdes (clamp raw 1..168, ventanas válidas, `usageBegin` today/week/raw) |

Verificación hello + uso real en el equipo (token sin cambios; scopes
`read`,`ui`; appop `GET_USAGE_STATS: allow`; accesibilidad re-habilitada
por `settings put secure`; `shizuku_server` ya corría): `get_battery`,
`get_memory`, `get_storage` y `get_app_usage(window=today|week)` con
valores reales (batería 100%, RAM disp. ~1.13 GB, libre ~12.8 GB;
top hoy `org.fossify.math` 647.2 min / `dev.k4wai1.jav` 144.1 min;
top semana `com.termux` 1214.1 min / `org.fossify.math` 647.2 min).
Suite MCP: **147 passed**.

## 9. `open_url` con `package` forzado + docstrings 5 secciones (2026-10-07, 5002E/API 29, USB e03638e5)

`open_url` aceptaba `{url}` y dejaba que el sistema resolviera; con >1
handler (medido: `youtu.be` con dos clientes YouTube instalados:
`app.morphe.android.youtube` y `app.rvx.android.youtube`) aparecía el
`ResolverActivity` (chooser). Ahora `open_url(url, package="")`:

- `package=""` → comportamiento previo (resolución del sistema; chooser
  si >1 handler).
- `package` no vacío → forma `a.b.c` validada (`NatPolicies.validPackage`);
  `getPackageInfo` (no instalado → `PACKAGE_NOT_FOUND`);
  `resolveActivity(MATCH_DEFAULT_ONLY)` y componente explícito
  (instalado sin handler → `INTENT_UNRESOLVED`); `via=
  startActivity-package`. Fallback Shizuku `am start -n pkg/activity`.

Cambios: `WsProtocol.OpenUrlParams.package`, `CommandDispatcher.openUrl`,
`NativeSensitive.openUrl(ctx, url, pkg)`, MCP `tools/native.py:open_url`
+ `server.py`; docstrings de las 35 tools reescritos al estándar de 5
secciones (Descripción / Parámetros / Retorno / Permisos-Grants /
Errores-gotchas). JVM: 2 asserts nuevos en `NatPoliciesTest`
(paquete forzado con forma válida). MCP: test de forwarding de `package`.

```bash
./gradlew :app:testDebugUnitTest --tests "dev.k4wai1.jav.nat.NatPoliciesTest" --console=plain
./gradlew :app:assembleDebug --console=plain
adb -s e03638e5 install -r app/build/outputs/apk/debug/app-debug.apk   # Success
```

| Build | Resultado | Tiempo Gradle (wall) | Notas |
|---|---|---|---|
| test NatPolicies (13 tests JVM) | **OK** | 7m 19s | incluye `open_url package forzado exige forma valida` |
| assembleDebug | **OK** | 4m 1s | APK debug 16 MB |
| install -r | **Success** | — | 5002E (Seoul, API 29) |

Prueba real en el equipo (token por `run-as`, WS en `127.0.0.1:38472`,
accesibilidad re-habilitada; `package` forzado, 1 salto):

```
resolve sin package → android/com.android.internal.app.ResolverActivity
resolve -p app.morphe.android.youtube → UrlActivity
resolve -p app.rvx.android.youtube   → UrlActivity

open_url(youtu.be, package=app.morphe.android.youtube)
  → {ok:true, verified:true, via:"startActivity-package", latency_ms:130.3}
get_foreground → app.morphe.android.youtube/MainActivity   (sin chooser)
open_url(youtu.be, package=com.no.existe.app)  → PACKAGE_NOT_FOUND
open_url(youtu.be, package=org.fossify.clock)  → INTENT_UNRESOLVED
open_url(youtu.be, package="") → foreground=android/ResolverActivity (chooser)
```

Suite MCP: **148 passed** (147 + test de forwarding). N2 y demás métodos
sin cambios. `grep -rniE 'whatsapp|contact_name|verify_chat|wrong_chat|
felix' mcp-server/src/` → **vacío** (el único `forward` es
`adb forward`/`ensure_forward` de `_base.py`, no la acción de reenvío).

## 10. P0 `send_intent`: canonicalización estricta + replay Go/Python (2026-10-09, 5002E/API 29, USB e03638e5, SOLO USB)

Deuda documentada en `cf66b7d`: `hSendIntent` (Go) pasaba `action`
verbatim y `NatPolicies.isCritical` (Jav) solo cubría formas plenas
`android.intent.action.*`; `SEND`/`CALL` cortos sin `confirm` daban `ok`
en vez de `planned` (bypass determinista del confirm).

Cambios:
- Kotlin `nat/NatPolicies.kt`: `canonicalizeAction` estricta (trim +
  uppercase; `SEND`/`ACTION_SEND`/`.SEND`/forma plena → forma canónica;
  igual CALL, VIEW, SENDTO, SEND_MULTIPLE, DIAL; desconocidas → trim sin
  inventar). `isCritical` canonicaliza antes de comparar; `sendIntent`
  (`NativeSensitive`) canonicaliza al entrar (preview, `Intent` y `am`
  usan la forma canónica; vacía → `VALIDATION_ERROR`).
- Go `pkg/tools/sendintent.go` (nuevo): espejo exacto
  (`CanonicalizeIntentAction` + `IsCriticalIntent`); `hSendIntent`
  canonicaliza antes del frame WS (el gate `planned` lo pone Jav).
- Tests: JVM `NatPoliciesTest` 2 nuevos (canónica SEND/CALL/VIEW +
  cortas críticas); Go `sendintent_test.go` (misma matriz);
  Go `pkg/normalizer/replay_test.go`: paridad conductual Go vs Python.
- Cobertura replay real (no inventada): 70 `run-*.jsonl`
  (`mcp-server/logs/` + `logs/`) con **0 árboles crudos** (solo
  forense/conteos); replay sobre 2 dumps reales con árbol:
  `mcp-server/tests/fixtures/wa_home.json` (WhatsApp, 174→65) y
  `pkg/normalizer/testdata/jam_live_18.json` (Jav onboarding en e03638e5
  vía `dump_ui`, 18→10; token saneado a `TOKEN-REDACTED`). Esperado
  generado por Python (`normalize` + `build_table` + `serialize_table` +
  `zone_of`, 720x1440); Go da poda/índices/zonas 3×3 idénticos.
- Rutas Go en raíz (`pkg/`, `cmd/`, `go.mod`); `go-mcp/` no existe:
  solo queda la nota histórica en `docs/specs/go-migration-plan.md §2`
  (reubicación documentada, sin código que actualizar).

```bash
./gradlew :app:testDebugUnitTest --tests "dev.k4wai1.jav.nat.NatPoliciesTest"  # 14/14 verdes
./gradlew :app:assembleDebug
adb -s e03638e5 install -r app/build/outputs/apk/debug/app-debug.apk   # Success
go build ./... && go vet ./... && go test ./...                          # 6 pkgs OK
uv run pytest tests/                                                     # 140 passed (mcp-server/)
```

| Build | Resultado | Tiempo Gradle (wall) | Notas |
|---|---|---|---|
| test NatPolicies (14 tests JVM) | **OK** | 2m 50s | 12 previos + canonicalize + cortas-críticas |
| assembleDebug | **OK** | 2m 33s (wall 155s) | APK debug 16 MB |
| install -r | **Success** | — | 5002E (USB e03638e5) |

Verificación hello + P0 en vivo (token del operador, sin exponer):
`hello{ok:true, proto:1, app:0.1.0, scopes:[read,ui]}`;
`SEND`/`ACTION_SEND`/`.SEND`/`CALL`/`action_call` sin `confirm` →
`planned:true` con `action` canónica; `VIEW https` → `startActivity`
(apertura, sin planned); `VIEW sms` → `planned:true`.

Nota: un `compileDebugKotlin` incremental intermedio falló con
`Unresolved reference: photoResult` (caché incremental rancia);
`--rerun-tasks` → SUCCESS sin cambios de código (pre-existente,
no relacionado al P0).

Sin commits (cierra @judge), sin push.

## 11. P0 bypass con punto `action.send`/`ACTION.SEND` (2026-10-09, 5002E/API 29, USB e03638e5, SOLO USB)

`@judge` frenó el commit: `canonicalizeAction` pelaba `ACTION_`
(guion-bajo) y `.` inicial, pero `action.send`→`ACTION.SEND` caía al
`else` y ejecutaba por `shizuku-am` sin `planned` (bypass del gate).
Igual `ACTION.SEND`.

Fix:
- Kotlin `nat/NatPolicies.kt`: strip secuencial — prefijo opcional
  `ANDROID.INTENT.` y luego `ACTION_`/`ACTION.`/`.` (case-insensitive).
  Cubre `SEND`, `ACTION_SEND`, `.SEND`, `action.send`, `ACTION.SEND`,
  familia CALL, `VIEW` libre, con/sin `android.intent.`.
- Go `pkg/tools/sendintent.go`: espejo exacto.
- Tests: JVM `NatPoliciesTest` (canónica + críticas con punto) y Go
  `sendintent_test.go` (misma matriz: SEND, ACTION_SEND, .SEND,
  action.send, ACTION.SEND, CALL y familia, VIEW libre con https).

```bash
./gradlew :app:testDebugUnitTest --tests "dev.k4wai1.jav.nat.NatPoliciesTest"  # 14/14 verdes
./gradlew :app:assembleDebug
adb -s e03638e5 install -r app/build/outputs/apk/debug/app-debug.apk   # Success
go test ./pkg/tools/ -run 'TestCanonicalize|TestIsCritical' -v
```

| Build | Resultado | Tiempo Gradle (wall) | Notas |
|---|---|---|---|
| test NatPolicies (14 tests JVM) | **OK** | 5m 6s | canónica + punto (`action.send`/`ACTION.SEND`/CALL/VIEW) |
| assembleDebug | **OK** | 3m 42s | APK debug 16 MB |
| install -r | **Success** | — | 5002E (USB e03638e5) |
| go test pkg/tools (canon+critical) | **OK** | <1s | matriz con punto en verde |

Sin commits (cierra @judge), sin push.

## 12. jam-ui-redesign: 4 tarjetas + cierre deuda token (2026-10-09, 5002E/API 29, USB e03638e5, SOLO USB)

Spec: `docs/specs/jam-ui-redesign.md` (propuesta @architect, sin código).
Alcance exacto §7: `activity_main.xml` (ScrollView + 4 tarjetas),
`res/drawable/card_bg.xml` (nuevo, shape transparente + corners 12dp +
stroke 1dp), `MainActivity.kt` (reescrita) + getters mínimos en
`JevForegroundService` (`startedAtMs`, `instance`, `clientCount/
clientAuthed/revokeClients`), `JamWsServer` (`clientCount`,
`clientAuthed`, `revokeAll` con `UNAUTHORIZED` limpio),
`CommandDispatcher` (contadores `AtomicLong` N0/N1/UI + `lastMethod/
lastResult/lastAtMs` + `recordSnapshot`, coste O(1)) y `AuthStore`
(`regenerateToken`, `masked` ••••+last4, `sha8`). Sin Compose/Hilt/
Material ni deps nuevas; `strings.xml` intacto; sin fragments/
ViewModel/LiveData/RecyclerView; sin polling (refresh en `onResume` +
listener Shizuku + resultado de permisos).

Deuda §5 cerrada: `MainActivity:93` (`Token: ${...}` en claro) →
máscara `••••abcd` + Copiar (clipboard, sin pegar en TextView) +
Regenerar (AlertDialog + gate cliente-autenticado); `JevForegroundService:33`
(`token=$token` en logcat) → `token_sha256=<8hex> len=<n>`.
`grep -rn 'token=\$\|Token: \$' app/src/main` → **vacío** ✓.
`grep su` → solo el falso positivo pre-existente
(`ShizukuBridge.kt:118` `ExecResult`, documentado en §6) ✓.
Shizuku: `getUid()` + `getVersion()` reales (API 13.1.5; sin PID
estable → no se inventa, se muestra `uid=… · v…`).
Batería: `PowerManager.isIgnoringBatteryOptimizations` con try/catch
→ "desconocida" honesta; botón con fallback a settings generales.

```bash
./gradlew :app:assembleDebug --console=plain   # 1 error propio (return en expression body, corregido)
adb -s e03638e5 install -r app/build/outputs/apk/debug/app-debug.apk   # Success
```

| Build | Resultado | Tiempo Gradle (wall) | Notas |
|---|---|---|---|
| assembleDebug (fallido, error propio) | FALLA 1 (`batteryState` return en expression-body) | 3m 24s | corregido a block-body, sin cambios de diseño |
| assembleDebug (reintento) | **OK** | 4m 47s (wall 4:49) | APK debug **16 464 665 bytes (16 MB)** ✓ ~16 MB |

> El "<2 min" de la spec es aspiracional en máquina de referencia;
> en esta máquina (Celeron 847, `workers.max=1`, sin daemon) los builds
> reales miden 2m22–7m19 (§§5–11); 4m47 documentado honesto.

Verificación en vivo (adb forward + cliente WS mínimo en stdlib, token
por `run-as`, sin exponerlo; uiautomator + screencap para píxeles):

- Tarjeta 1: `● ON`, `ws://127.0.0.1:38472/`, `clientes: 0 ·
  autenticado: —`, `protocolo v1`, `desde 22:16:50` (nodos + PNG).
- Tarjeta 2: `● Accesibilidad: OK` (tras re-bind limpio, ver abajo),
  `Shizuku: ● OK (permiso API_V23 concedido · uid=2000 · v13)`,
  `● Batería: optimizada…` + `PEDIR IGNORAR`,
  `Grants N1: uso=OK notif=no contactos=OK calendario=OK ubicación=OK cámara=OK`.
- Tarjeta 3: `Token: ••••D-D8` (máscara real); gate probado con cliente
  autenticado conectado → diálogo `Regenerar token / Invalida el cliente
  actual` → confirmar → aborta con hint `desconecta el cliente antes de
  regenerar`, token intacto (misma cola).
- Tarjeta 4: `N0 0 · N1 0 · UI 2 · clics 1 (sesión)`,
  `último: screenshot INTERNAL_ERROR 22:19:19`,
  `snapshot #830 · 30 nodos · 63 ms` (contadores/último/snapshot
  validados contra llamadas WS reales: hello no cuenta; dump_ui fallido
  sí cuenta + registra código).
- `hello{ok:true, proto:1, app:0.1.0, scopes:[read,ui]}` ✓;
  `dump_ui{ok:true, 30 nodos, snapshot #830}` ✓ (tras re-bind).
- `screenshot{png}` → `INTERNAL_ERROR` honesto (pre-existente, sin
  cambios aquí): `takeScreenshot` es API 30+, el 5002E es API 29
  (sin fallback hasta Fase 3c). Evidencia visual por uiautomator+
  screencap en su lugar.
- Logcat: token completo ausente ✓ (buffer del equipo retiene poco;
  la prueba decisiva es estática: ningún `JevLog`/UI compone el
  secreto — solo `sha8`/`len`/máscara).

Notas de banco (para el operador, sin cambios de código):

1. Primer frame tras cold-start puede mostrar `● DETENIDO` ~1 s: el
   `onResume` inicial corre antes de que `FGS.onCreate` arranque (async);
   por diseño no hay polling/observers — cualquier `onResume`
   posterior (HOME + reabrir) lo deja en `● ON`. Solo afecta al tout
   primer arranque en frío (con `START_STICKY` el servicio ya suele
   estar vivo). `am start` sobre la instancia en tope es no-op
   (`Activity not started… delivered to top-most instance`): para
   re-renderizar hay que pasar por HOME.
2. Tras `install -r`/`force_stop` el puerto puede quedar LISTEN en
   proceso rancio (ya visto en §7); `force-stop` + arranque en frío
   lo deja OK. Procesos `dev.k4wai1.jav:shell` antiguos (Shizuku) sobreviven
   al force-stop; no afectan (no escuchan WS).
3. Accesibilidad: hizo falta ciclo limpio (`settings delete` +
   `put` con `ComponentName` **plano**
   `dev.k4wai1.jav/dev.k4wai1.jav.service.JevAccessibilityService` — la forma
   corta `.service.…` no matchea el `== flat` de `isAccessibilityOn()`)
   para que el sistema re-enlazara en el proceso nuevo
   (`caps.accessibility: false→true`).
4. `input swipe/tap` en este banco usa el espacio lógico del override
   `360x720` (coords 180/…) — con coords físicas 720x1440 el gesto cae
   fuera y es no-op (misma causa raíz que el fix `DisplayScale` de §5).

Sin commits (cierra @judge), sin push. Sin keys.

## 13. Fallback Soberano + tap_text híbrido + APK en releases (2026-10-10, 5002E/API 29, USB e03638e5, SOLO USB)

Alcance `@coder` (Go + Kotlin + adb; nada de `su`; 100% genérico, sin keys):

- **Fallback Soberano** (`pkg/director/director.go`): `ResolveElement`/
  `ResolveElementWithTau` ya no devuelven error fatal de Go ante fallo
  Jev (red, envelope vacío, alucinación, `conf<tau`, `NONE`, sin key).
  Devuelven payload `{ok:false, idx:null, fallback_required:true,
  reason, recovery_instruction, snapshot_id}` con
  `recovery_instruction = "El Director examina candidates/render y
  ejecuta tap_node/tap_text directo"`. Éxito = `{ok:true, idx, conf,
  snapshot_id, fallback_required:false, usage, cost_usd}`. `tau<=0`
  → `normalizer.TAU (0.70)`. Tests nuevos en
  `pkg/director/director_test.go:TestResolveSovereignFallback`
  (red / envelope vacío / alucinación / `conf<tau` / `NONE` / control
  OK) + `aiproviders_test.go` actualizado a fallback sin key.
- **tap_text híbrido** (`android-app/.../ui/Selector.kt`):
  `textContains` matchea `text` Y `content-desc`, case-insensitive y
  parcial. `wait_for_node` lo hereda (mismo `SelectorResolver`).
  Tests JVM nuevos en `SelectorResolverTest` (icono sin texto,
  case-insensitive, parcial sobre desc).
- **Releases con APK** (`.github/workflows/release.yml` +
  `.goreleaser.yml`): job `build-apk` (JDK 17 temurin +
  `android-actions/setup-android@v3` + `:app:assembleDebug`) sube
  `jav-companion.apk` como artifact; job `release` (needs
  `build-apk`) lo descarga a `./jav-companion.apk` y GoReleaser lo
  adjunta vía `release.extra_files` junto a los binarios Go.
  YAML validado sintácticamente
  (`uv run --with pyyaml python -c "yaml.safe_load(...)"` → `YAML OK`).
  Sin tags creados (el próximo tag lo probará).

```bash
go build ./... && go vet ./... && go test ./...
./gradlew :app:testDebugUnitTest --tests "dev.k4wai1.jav.ui.SelectorResolverTest"
./gradlew :app:assembleDebug
adb -s e03638e5 install -r app/build/outputs/apk/debug/app-debug.apk
```

| Build / test | Resultado | Tiempo (wall) | Notas |
|---|---|---|---|
| `go build ./...` | **OK** | ~19 s | sin cambios fuera de `pkg/director` |
| `go vet ./...` | **OK** | ~4 s | limpio |
| `go test ./...` | **OK** | ~3 s | 6 pkgs (director con 5 tests incl. soberano) |
| Gradle `testDebugUnitTest` filtrado `SelectorResolverTest` | **OK 9/9** | 3m 59s | 6 previos + 3 híbridos nuevos |
| Gradle `:app:assembleDebug` | **OK** | 2m 41s | APK debug **16 562 777 bytes (~16 MB)** |
| `adb install -r` | **Success** | — | 5002E (USB e03638e5) |
| Gradle `testDebugUnitTest` completo | **OK 37/37** | 1m 55s | DisplayScale 5 + Extractor 6 + NatPolicies 14 + WsProtocol 3 + Selector 9 |
| `uv run pytest` | **N/A** | — | `mcp-server/tests/` sin tests propios (solo `__pycache__`); no aplica |

Prueba tap_text híbrido en vivo (WS `127.0.0.1:38472`, token por
`run-as`, sin exponerlo; YouTube `app.morphe.android.youtube` abierto
por `monkey` desde el host):

```
dump_ui → snapshot #833, 97 nodos, package app.morphe.android.youtube
n_65 | text='' | desc='Buscar' | cls=android.widget.ImageView | clickable=True   (1 hit)
tap {"text_contains": "Buscar"} → {ok:true, node_id:"n_65", via:"action_click"}
press_back + tap {"text_contains": "BUSCAR"} → {ok:true, via:"action_click"} (case-insensitive)
```

El icono sin texto solo vive en `content-desc`: con el `matches`
anterior (`text.contains` exacto) era `SELECTOR_NOT_FOUND`; con el
híbrido resuelve y tapea por `ACTION_CLICK`. Tras el primer tap la
UI rota (`STALE_SNAPSHOT` en el re-tap inmediato = honesto, no bug).
Banco dejado en YouTube con la búsqueda abierta; accesibilidad
re-habilitada por `settings put secure` con `ComponentName` plano
(igual que §12.3); tras `install -r` hizo falta `force-stop` +
arranque en frío (puerto sin LISTEN en proceso rancio, ya visto
en §7).

Sin commits (cierra @judge), sin push. Sin keys/tokens.

## 14. CI `build-apk`: sin `setup-android@v3` (pedía paquete obsoleto `tools`); se usa el SDK del runner + `sdkmanager --install "platforms;android-34" "build-tools;34.0.0"` (AGP 8.5.2 default, `compileSdk 34`).

## 15. Robustez P4/P5/P6 + S2 JAV_AI_* + E2E en banco (2026-10-15, 5002E/API 29, USB e03638e5, SOLO USB)

Alcance ejecutado por el orquestador (subagentes con permisos rotos en
runtime): cierre **P4** (§9, memoria de estado), **P6** (§10, reanclaje de
nodo vivo + fallback `screencap`), **P5** (§11, enmascarado de secretos en
`candidates`/`render`) y cableado **S2 `JAV_AI_*`** (`pkg/director/s2.go`,
`docs/specs/ai-providers.md` §2.2).

```bash
cd android-app && ./gradlew :app:testDebugUnitTest :app:assembleDebug --console=plain   # OK 56/56, APK OK
adb -s e03638e5 install -r android-app/app/build/outputs/apk/debug/app-debug.apk        # Success
go test ./... && go run ./cmd/audit-mcp                                                 # verdes, 11/11 PASS
go run ./cmd/jav-e2e -serial e03638e5                                                   # ok=31 planned/dry-run=8 error=12
```

### 15.1 Bug cazado en vivo: `WEBP_LOSSY` en API 29

`screenshot{format:webp}` devolvía `INTERNAL_ERROR` ("error interno" =
`Throwable` no-`JamError` en `JamWsServer`). Causa: `Bitmap.CompressFormat.WEBP_LOSSY`
es **API 30+**; en API 29 el `getstatic` lanza `NoSuchFieldError` (es un
`Error`, no una excepción capturada). El camino `png` sí funcionaba
(`via:"screencap"`). Fix en `JevAccessibilityService.webpOrPng()`: `WEBP_LOSSY`
solo en `SDK_INT >= R`; `WEBP` (deprecado) en API 29, referencia aislada en
`webpLossy()`/`webpLegacy()` para que la línea de API 30 no se ejecute en 29.

### 15.2 `screenshot` en vivo (API 29, Shizuku activo)

Shizuku no estaba corriendo (caps.shizuku=false → `SHIZUKU_UNAVAILABLE`,
honesto). Arrancado por el operador con el comando que muestra la app
Shizuku (`adb shell /data/app/moe.shizuku.privileged.api-…/lib/arm/libshizuku.so`;
la app **nunca** lo arranca, AGENTS §2.7). Tras conceder/heredar API_V23:

```
caps = {"accessibility": true, "shizuku": true, "shell_grant": false, ...}
screenshot {format:png,  quality:80} → {ok:true, w:360, h:720, via:"screencap"}
screenshot {format:webp, quality:80} → {ok:true, w:360, h:720, via:"screencap"}  (antes del fix: INTERNAL_ERROR)
```

### 15.3 P5 — secretos fuera de `candidates`/`render`

`pkg/normalizer`: `isPasswordNode` (editable + propiedad nativa
`password`/`is_password` o marcadores) marca `Candidate.Secret`; `Compact()`
enmascara (etiqueta de content_desc/resource_id/id o `••••`), `SafeText()`
sustituye el `text` en `evidence.candidates` (`pkg/tools/helpers.go`). Gate
`editable` evita el falso positivo `pin_indicator` de `wa_home.json` →
**paridad Python exacta intacta** (`TestReplayPythonParity`). §11 del spec.

### 15.4 Banco

Accesibilidad re-habilitada por `settings put secure` con `ComponentName`
plano (misma nota que §12.3); tras `install -r`/`force-stop` el ciclo
`delete`+`put`+`enabled=1` vuelve a enlazar (`Bound services: Jav`).
Sin commits (cierra @judge), sin push. Sin keys/tokens expuestos.

## 16. Benchmark sintético de tools en A10 (2026-10-15, API 29, USB e03638e5)

Prueba **real** del MCP contra el dispositivo (no unit tests fáciles): cliente
WS `127.0.0.1:38472`, token del `.env`, `n=20–30` por método, sin LLM.
Comando y tablas crudas en `docs/TESTING.md §12`; síntesis en
`docs/benchmarks/PERFORMANCE.md §5`.

| Grupo | p50 destacado |
|---|---|
| Lectura accesibilidad | `get_foreground` 26 ms · `dump_ui` (30 n) 74 ms |
| Captura | webp q80 1037 ms (20 KB) · png q80 1101 ms (60 KB) |
| Native N0 | 7–12 ms (`get_cpu` 131 ms) |
| Cross-app `dump_ui` | `~15 ms + ~1.4 ms/nodo` (14–117 n) |
| Ruta ADB `uiautomator dump` | ~2280 ms (≈30× más lento que Jav) |

`caps` observado: `accessibility:true, shizuku:true, shell_grant:false`. API 29
usa `screencap` (via WS/Shizuku) para `screenshot`; `WEBP_LOSSY` corregido
(§15.1). `open_app` con poll de foreground = 1.9–5.3 s (no es coste nativo).

**Experiencia (subjetiva del operador/orquestador):**
- El `hello` responde **sin campo `id`**; un cliente que espere `id` se cuelga
  (me pasó hasta leer `PROTOCOL §2`). `caps` viene en el hello.
- `dump_ui` es consistente (p90≈max, jitter bajo) → apto para loops.
- `screenshot` domina el presupuesto (~1 s): es evidencia, no primaria
  (coherente con `AGENTS §1`). WebP q80 recorta el payload ~3×.
- Native N0 es instantáneo salvo `get_cpu`; sirve para *probes* baratos.
- La ruta ADB/uiautomator (`android_ui_dump`) es **inviable** para el loop
  (~2.3 s/dump); confirma por qué la accesibilidad in-process manda.

Sin commits (cierra @judge), sin push. Sin keys/tokens expuestos.

## 17. Revancha en vivo `resolve_element` + `ACTION_PASTE` (2026-10-15, A10 API 29)

Cierre del bloque de 3 pasos: (1) higiene `gofmt` + commit del hito
`a6aaba8`/`a76ba65`; (2) `resolve_element` como **36.ª tool MCP** y fallback
`ACTION_PASTE` en Jav; (3) revancha en vivo. Banco `e03638e5` (Android 10 /
API 29, USB), sin commits ni push.

**Qué cambió**
- Go: `pkg/tools/resolve.go` (`hResolveElement`, envuelve
  `director.ResolveElementWithTau` con `tried_node_ids` vigentes de
  `pkg/uitrack`), `register.go` (`toolDefs` como var de paquete, `numProp`),
  `helpers.go` (`getFloat`); `cmd/audit-mcp` con `tools-count-36`.
- Kotlin: `A11yNode.performPaste()` (Real+Fake), `ui/TextEntry.kt` (puro,
  JVM-testeable); `JevAccessibilityService.typeNode` usa `TextEntry.write` y
  `setClipboardText` (`ClipboardManager.setPrimaryClip`), `INTERNAL_ERROR`
  honesto si `SET_TEXT` **y** `PASTE` fallan.

**Verificación**
```
gofmt -l cmd/ pkg/                 # vacío
go test ./...                      # verde
cd android-app && ./gradlew :app:testDebugUnitTest   # 59/59 (antes 56; +3 TextEntry)
go run ./cmd/audit-mcp             # 11/11 PASS, tools-count-36
```
En vivo (Fossify Math, stdio JSON-RPC, S1 real): `read_screen` → 1117 (24
cands) · `resolve_element "Tap the number 7 button"` → `idx 7 / node_id n_26 /
conf 0.88` · `tap_node` → `via action_click` · `read_screen` → 1119,
`diff.changed:true` (`7` reemplaza `0`). Segundo caso: tap sobre nodo
no-clickable → `via gesture`, `diff.changed:false`, `tried_node_ids ["n_16"]`
(memoria por fingerprint). Tabla completa en `docs/benchmarks/TASK_HISTORY.md §6`.

Reactivación: mismo ciclo `delete`+`put`+`enabled=1` de §15 (Accesibilidad)
tras `install -r`; Shizuku lo arranca el operador, la app nunca lo inicia
(`AGENTS §2.7`). Sin `su`, sin literales de app, sin keys/tokens en claro.

## 18. Pulido de producción: `via` en `type`, race de `audit-mcp`, `dist/` (2026-10-15)

Cierre del hito #36. Tres frentes:

1. **`via` en `type_text`**: `JevAccessibilityService.typeNode` devuelve
   `TypeResult(chars, via)` (`action_set_text`|`action_paste`);
   `CommandDispatcher.type` añade `put("via", …)`; `pkg/tools/ui.go` lo
   reenvía en `evidence`. Contrato en `PROTOCOL §4`. Verificado en vivo
   (Fossify Filemanager, campo "Buscar"): `type_text` →
   `evidence {"chars":9,"via":"action_set_text"}`.
2. **Race de `cmd/audit-mcp`**: el harness volcaba las 6 peticiones a un
   `bytes.Buffer` y cerraba stdin (EOF); el shutdown de `ServeStdio` podía
   abortar las tool calls en vuelo (id 3/4/5) → `error-isError-id{3,4,5}`
   flaky (≈1/5). Ahora usa `io.Pipe` + lectura incremental y **mantiene el
   stdin abierto** hasta reunir las 5 respuestas (como un cliente MCP real).
   Estabilidad medida: **15/15**.
3. **`dist/` + README + jav-e2e**: `make build` → `dist/jav-linux-amd64`
   (binario de `opencode.json`); `README.md` (EN+ES) y `cmd/jav-e2e` a
   **36 tools**; `cmd/jav-e2e` añade `resolve_element` con `goal` vacío
   (`VALIDATION_ERROR` sin gastar saldo ni tocar UI).

```
gofmt -l cmd/ pkg/                                   # vacío
go test ./...                                        # verde
cd android-app && ./gradlew :app:testDebugUnitTest :app:assembleDebug  # 59/59
make build                                           # dist/jav-linux-amd64
go run ./cmd/audit-mcp --bin dist/jav-linux-amd64    # 11/11 PASS (tools-count-36)
```
APK reinstalada en `e03638e5` (Accesibilidad re-enlazada, Shizuku vivo).

## 19. Fase 6a — audit ring 500 + Kill Switch + tool #37 `get_audit` (2026-10-16)

Primer bloque de Fase 6 (AGENTS §3.8 / ARCHITECTURE §9): auditoría en
dispositivo consultable y parada dura del servidor. Banco `e03638e5`
(Android 10 / API 29, USB).

**Qué cambió**
- **Kotlin `socket/AuditLog.kt`** (puro JVM, `object`): ring de
  `MAX_ENTRIES=500` sobre `ArrayDeque` con lock. `AuditEntry` serializable
  `{seq, ts, method, scope, args_sha256, result, origin}`; `args_sha256` =
  primeros **16 hex** del SHA-256 de `params.toString()` (jamás el texto en
  claro). API: `record/list(limit, sinceSeq)/clear/size`.
- **`CommandDispatcher`**: `hello(req, origin)` y `dispatch(req, scopes,
  origin)` propagan el origen y registran cada intento (OK o `code`) con
  `scopeOf(method)` (`read|ui|n0|n1|auth|admin`). Set `read` para lecturas
  puras (`dump_ui`/`wait_for_node`/`get_foreground`/`screenshot`). Nuevo
  método WS **`get_audit`** (`limit` 1..200, `since_seq`) → `{total_buffered,
  returned, entries[]}`. El token bearer único habilita además `admin` en
  `hello.scopes`.
- **`JamWsServer`**: `originOf(conn)` sanitiza a `loopback` o IP (sin puerto).
- **Kill Switch** (`service/JevForegroundService.kt`):
  `ACTION_KILL_SWITCH="dev.k4wai1.jav.action.KILL_SWITCH"` en `onStartCommand`;
  `triggerKillSwitch(ctx)` rota el token (`AuthStore.regenerateToken`),
  registra `kill_switch` (scope admin) y `revokeAll()` + `shutdown()` +
  `stopForeground(STOP_FOREGROUND_REMOVE)` + `stopSelf()`. Botón "Kill
  Switch" en la notificación (`PendingIntent.getService`,
  `FLAG_IMMUTABLE`).
- **`service/JamKillSwitchTile.kt`** (`TileService`, API 24+): refleja
  `serverOn` (`STATE_ACTIVE`/`LABEL "Jav ON|OFF"`) y dispara el kill en
  `onClick`. Manifest: `BIND_QUICK_SETTINGS_TILE` + `exported="true"` +
  `QS_TILE`; icono propio `res/drawable/ic_jam_kill.xml` (sin depender de
  recursos de sistema ocultos).
- **Go tool #37 `get_audit`**: `pkg/jam.GetAudit(limit, sinceSeq)`,
  `pkg/tools/audit.go` (clamp 1..200, `since_seq<0`→0), `register.go`
  (`titleOf "since_seq"`), docstring de 7 secciones. Contadores a **37**
  (`register_test`, `spec_test`, `cmd/audit-mcp tools-count-37`,
  `cmd/jav-e2e` + `get_audit` live), README/ARCHITECTURE/MCP_SPEC_GUIDELINES.

**Verificación**
```
gofmt -l cmd/ pkg/                                   # vacío
go test ./...                                        # verde (pkg/tools 37)
cd android-app && ./gradlew :app:testDebugUnitTest :app:assembleDebug  # 64/64
make build                                           # dist/jav-linux-amd64
go run ./cmd/audit-mcp --bin dist/jav-linux-amd64    # 11/11 PASS (tools-count-37)
```
Gate `su` (AGENTS §2.2): `grep -rn 'su -c\|exec(.*su\|ProcessBuilder(.*su'
android-app/app/src/` → **1 hit** preexistente (`shell/ShizukuBridge.kt:118`,
falso positivo `Re**su**lt`); sin hits nuevos.

**En vivo (`get_audit`, WS directo + `adb forward tcp:38472`)**: tras
`hello` + `get_battery`/`get_device_info`/`get_foreground` (a11y apagada):
```
seq=1 hello        scope=auth result=OK   origin=loopback args_sha256=16 hex
seq=2 get_battery  scope=n0   result=OK   origin=loopback
seq=3 get_device_info scope=n0 result=OK  origin=loopback
seq=4 get_foreground scope=read result=ACCESSIBILITY_DISABLED origin=loopback
```
Sin fuga: el token no aparece en el JSON y todos los `args_sha256` miden 16.
`get_audit` no se auto-incluye (se registra tras responder). Kill Switch
verificado por composición: tile registrado con `BIND_QUICK_SETTINGS_TILE`
(`dumpsys package`) y notificación `id=1` con `actions=1` → `"Kill Switch"`
`PendingIntent startService` (`dumpsys notification`). **No se disparó en
vivo** a propósito: rotaría el token del operador a mitad de sesión; queda
como prueba manual del operador (tile o botón de notificación).

## 20. Fase 6b — `shell` con denylist + grant interactivo + N2 + tool #38 `adb_shell` (2026-10-16)

Cierre de Fase 6 (AGENTS §2.7/§3.6/§3.7/§6): `shell` deja de ser
`METHOD_NOT_ALLOWED` y pasa a ejecutarse por Shizuku (UID `shell`) con
rate limit, denylist de irreversibles y grant del operador; el carril N2
(`settings_put` secure/global, `get_storage`/`get_cpu` `detail=fine`)
queda vivo. Banco `e03638e5` (Android 10 / API 29, USB).

**Qué cambió**
- **Kotlin `shell/ShellPolicy.kt`** (puro JVM, `object`): `enum
  PolicyVerdict {ALLOWED, NEEDS_CONFIRM, FORBIDDEN_SELF}`; denylist de
  irreversibles (`rm -rf /`|`*`, `pm uninstall`, `cmd package uninstall`,
  `reboot recovery|bootloader|fastboot`, `dd … of=`, `mkfs`, `wipe`,
  `settings put secure|global <clave crítica>`); `isSelfHarm` (matar/
  desinstalar `dev.k4wai1.jav`) → `FORBIDDEN_SELF`; `sha256Hex`,
  `previewPrefix` (≤80), `SlidingWindowRateLimiter(5, 1000)` → `RATE`
  para el rate **5 req/s** de shell (independiente del 50 req/s general).
- **Kotlin `shell/ShellGrantManager.kt`** (`object`, en memoria): ventanas
  `once`/5 min/30 min, `CountDownLatch` bloqueante hasta **60 s**;
  notificación de alta importancia `jam_shell_grant` con prefijo ≤80 +
  **8 hex** del SHA-256 y 4 botones (`1 cmd`/`5 min`/`30 min`/`Denegar`)
  vía `PendingIntent.getService`. `resolve` emite evento `shell_grant`
  (`{mode, sha256}`) por `JamWsServer.broadcastEvent`; timeout/denegar →
  `SHELL_DENIED`; Kill Switch → `revoke()`.
- **`CommandDispatcher`**: ruta `"shell"` → `shell(req)` (valida `cmd`,
  `RATE_LIMITED` >5/s, `SHELL_DENYLIST` para self-harm, `planned` para
  irreversible sin `confirm`, `requestGrantBlocking` → `SHELL_DENIED`,
  `ShizukuBridge.exec(listOf("sh","-c",cmd))`); `settingsPut` N2 para
  `secure`/`global` (clave crítica → `FORBIDDEN`, sin confirm → `planned`,
  con confirm → Shizuku, `{namespace,key,written:true,via:"shizuku"}`);
  `caps["shell_grant"]=ShellGrantManager.hasActiveGrant()`.
- **`nat/NativeDevice.kt`**: `get_storage`/`get_cpu` con `detail="fine"`
  → `df -k` / `top -b -n 1 -m 10` por Shizuku, devuelven base + `{via,
  cmd, exit_code, entries[]/processes[], raw}`.
- **Go tool #38 `adb_shell`**: `pkg/jam.Shell(cmd, timeoutMs, confirm)`
  (`CallTimeout`, `read = timeout+65s`), `pkg/tools/shell.go` (clamp
  500..60000, `cmd` vacío → `VALIDATION_ERROR`), `register.go`
  (`dAdbShell` 7 secciones + `titleOf "cmd"`), `dGetCPU` N2. Contadores a
  **38** (`register_test`, `spec_test` 37 descs, `cmd/audit-mcp
  tools-count-38` + `sensitive["adb_shell"]`, `cmd/jav-e2e`), docs.

**Verificación**
```
gofmt -l cmd/ pkg/                                   # vacío
go test ./...                                        # verde (pkg/tools 38)
cd android-app && ./gradlew :app:testDebugUnitTest :app:assembleDebug  # 73/73
make build                                           # dist/jav-linux-amd64
go run ./cmd/audit-mcp --bin dist/jav-linux-amd64    # 11/11 PASS (tools-count-38)
```
Gate `su` (AGENTS §2.2): sigue en **1 hit** preexistente
(`shell/ShizukuBridge.kt:118`, falso positivo `Re**su**lt`); sin hits nuevos.

**En vivo (WS vía `adb forward tcp:38472`, a11y re-enlazada)**:
```
get_storage detail=fine → ok verified via=shizuku exit=0 entries=2
get_cpu     detail=fine → ok verified processors=4 via=shizuku exit=0 procs=10
settings_put global airplane_mode_on confirm=false → planned:true (value_sha256)
adb_shell   "rm -rf /" confirm=false   → planned:true preview reason=denylist_irreversible
adb_shell   "pm uninstall dev.k4wai1.jav" → SHELL_DENYLIST (no se toca el dispositivo)
adb_shell   ""                         → VALIDATION_ERROR
get_foreground / read_screen           → ok tras re-enlazar accesibilidad
```
El grant interactivo se aprueba en el dispositivo (notificación) y emite
`shell_grant` por WS; no se automatizó el tap del operador (rotaría la
sesión / requiere interacción humana). `rm -rf /` **nunca** tocó el
dispositivo (se detuvo en la compuerta `planned`).

## 21. Fase 2b — WSS tailnet + cert self-signed + token en Keystore (2026-10-16)

Cierre del backlog 2b (`ARCHITECTURE.md §9`): el transporte sale del
loopback+`adb forward` y añade un segundo listener **WSS** atado a la IP del
tailnet, con token cifrado en reposo y pinning TOFU en el cliente Go.

**Android (Kotlin)**
- `socket/AuthLockout.kt`: lockout por `origin` — 5 fallos `UNAUTHORIZED` en
  60 s → bloqueo 300 s (`isLocked`/`retryAfterMs`/`recordFailure`/
  `recordSuccess`). `hello` bloqueado → `UNAUTHORIZED` + audit.
  `AuthLockoutTest.kt` (7 tests).
- `socket/AuthStore.kt`: token **AES-GCM/256** en `AndroidKeyStore`
  (alias `jam_token_key`), almacenado como `ws_token_enc` (`iv(12)||ct`
  Base64). **Migración suave**: si existe el plano `ws_token` se cifra el
  mismo valor y se borra el plano → el `.env` del operador sigue válido.
  `regenerateToken` guarda cifrado.
- `socket/TlsCertStore.kt`: `TlsCertStore` (AndroidKeyStore) + `TlsCertFactory`
  (JVM puro). Cert **X.509v3 autofirmado** `CN=jav.local`, RSA-2048, 10 años,
  con BouncyCastle **local** (nunca registro JCA global, AGENTS §5.3);
  PKCS#12 cifrado en `filesDir` (`jam_tls.p12.enc`); expone `sslContext()`
  y `fingerprintSha256()`. `TlsCertStoreTest.kt` (5 tests).
- `net/TailnetDetector.kt`: `isTailnetIpv4` (CGNAT `100.64.0.0/10`) +
  `ConnectivityManager.NetworkCallback` para re-detección.
- `socket/JamWsServer.kt`: `ClientRegistry` compartida (single-client global),
  bind/SSL/label configurables; `setWebSocketFactory(DefaultSSLWebSocketServerFactory)`
  cuando hay `sslContext`.
- `service/JevForegroundService.kt`: loopback WS + 2.º listener **WSS** en la
  IP tailnet (nunca `0.0.0.0`), `tailnetUrl()`/`certFingerprint()`; `onDestroy`
  cierra ambos y desregistra el callback.
- `MainActivity` Tarjeta 1/3: estado tailnet (`wss://<ip>:38472/` o
  `tailnet: no detectada`) + primeros 16 hex del `cert_sha256` (TOFU).

**Go (`pkg/jam`)**
- `dialOnce`: si la URL es `wss://`, `tls.Config` con **pinning TOFU** —
  `policy: JAV_CERT_FINGERPRINT` (fallback `JEV_CERT_FINGERPRINT`), comparación
  SHA-256 en tiempo constante; mismatch → `CERT_MISMATCH` (hint honesto).
  `tls_test.go`: normalización del pin + TOFU (sin pin / pin ok / pin mal /
  sin certificado).

**Verificación**
```
gofmt -l cmd/ pkg/                                   # vacío
go test ./...                                        # verde (pkg/jam += tls_test)
cd android-app && ./gradlew :app:testDebugUnitTest :app:assembleDebug  # 88/88
make build                                           # dist/jav-linux-amd64
go run ./cmd/audit-mcp --bin dist/jav-linux-amd64    # 11/11 PASS (tools-count-38)
```
Gate `su` (AGENTS §2.2): sigue en **1 hit** preexistente
(`shell/ShizukuBridge.kt:118`, falso positivo `Re**su**lt`); sin hits nuevos.

**En vivo (`e03638e5`, WS vía `adb forward`)**:
```
shared_prefs/jam_auth.xml   → ws_token_enc (antes ws_token plano); migración suave OK
hello                       → ok app=0.1.0 scopes=[read ui admin] (token del .env intacto)
get_audit limit=5           → ok total=1 returned=1
```
`logcat` está deshabilitado en esta ROM (`logcat -d` → 0 líneas), así que la
traza `JamWs` no es legible; la verificación se hizo por efecto observable
(`hello`/`get_audit` + `shared_prefs`).

**Límite honesto:** el banco no tiene IP `100.64.0.0/10` (solo
`192.168.100.11`), por lo que el **listener WSS y el pinning end-to-end no se
probaron en vivo**; se cubren por tests JVM del `TlsCertFactory`, por el test
Go del pinning y por la prueba de que el camino AES de `AndroidKeyStore`
funciona (migración del token). Bindear el WSS a la LAN violaría AGENTS §3.1
(nunca fuera del tailnet), así que no se forzó.

---

## 22. v1.2.0 — tools/list compacto, costo silencioso, icono/UI y poda documental

Build de cierre de release. Cambios de código y de documento, con verificación
Go completa en esta máquina y **límite honesto** en el lado Android (sin JDK/SDK
en el entorno del agente, ver más abajo).

**Go (`pkg/tools`, `pkg/cost`, `cmd/jav`, `cmd/audit-mcp`)**
- `catalog.go` (nuevo): clasificación de las 38 tools en 4 grupos
  (`state` 9, `ui` 11, `native` 17, `resolve` 1), `FullToolDocs` (ficha de 7
  secciones íntegra por tool) y `CompactDesc` (1-2 líneas para `tools/list`).
- `resources.go`: `RegisterSpecResources` publica `android://tools/catalog`
  (índice JSON), `android://tools/<group>` (fichas completas) y la plantilla
  `android://tool/{name}` (ficha individual).
- `register.go`: se retiran los `title` redundantes por propiedad del schema;
  `tools/list` viaja con `CompactDesc`.
- `cmd/jav/main.go`: `instructions` compactado a **218 palabras** (tokens
  obligatorios intactos) + línea de specs bajo demanda; `version = "1.2.0"`.
- `pkg/cost/cost.go`: `Track` **silencioso** por defecto (`JAV_DEBUG_COST=1`
  para trazar) + acumulador global `SessionSummary()`
  (`{jev_cost_usd, s2_cost_usd, total_cost_usd, calls}`); `pkg/tools` lo
  adjunta en `evidence.cost` de `device_status` y `resolve_element`.
- `cmd/audit-mcp/main.go`: `tools-affordances` ahora certifica la descripción
  compacta en vivo + las 38 fichas completas leídas por Resource + la
  plantilla; **nuevo check `token-budget-startup`**.

**Verificación (Go)**
```
gofmt -l cmd/ pkg/                                   # vacío
go vet ./...                                         # 0
go test ./...                                        # verde salvo el
                                                     #   preexistente pkg/normalizer
                                                     #   (depende de logs/run-*.jsonl,
                                                     #   gitignored: sin fixtures)
make build                                           # dist/jav-linux-amd64
go run ./cmd/audit-mcp --bin dist/jav-linux-amd64    # 12/12 PASS
```
`token-budget-startup`: carga cognitiva (instructions + 38 descripciones)
**6525 bytes ≈ 1631 tokens** (≤3000), frente a ~8800 tokens previos
(**~81 % de ahorro**). Respuestas JSON completas `initialize + tools/list`:
15078 bytes (incluye el esquema MCP fijo, no reducible sin romper el contrato).
`tools-count-38` y `tools-affordances` en verde.

**Android (`android-app`)**
- Icono `docs/assets/icon.png` (1000×1000) + mipmaps `ic_launcher[_round]`
  (mdpi 48 / hdpi 72 / xhdpi 96 / xxhdpi 144 / xxxhdpi 192, round con máscara
  circular y alfa). `android:icon`/`android:roundIcon` en el manifest.
- `values`/`values-night` `colors.xml` (`status_ok|warn|fail`, `card_bg_fill`,
  `card_stroke`, `divider_color`), `dimens.xml`, `card_bg.xml` semántico,
  header con logo en `activity_main.xml`, `MainActivity.kt` con
  `ContextCompat.getColor(...)`. `versionName 1.2.0` / `versionCode 2`.
- Comprobaciones locales: 9/9 XML bien formados, mipmaps presentes,
  gate `su` (AGENTS §2.2) **sin hits nuevos** (1 preexistente:
  `shell/ShizukuBridge.kt:118`, falso positivo `Re**su**lt`).

**Límite honesto:** este entorno de agente **no tiene JDK ni Android SDK**
(`java`, `gradle`, `~/Android/Sdk` ausentes) y el dispositivo `e03638e5` no está
conectado por USB, por lo que **no se pudo** ejecutar
`./gradlew :app:testDebugUnitTest :app:assembleDebug` ni el e2e en vivo. Los
cambios Android quedan validados por revisión estática (XML + recursos) y por el
workflow de release (JDK 17 temurin en CI). Pendiente de certificar en hardware
real (`e03638e5`) antes/junto al tag `v1.2.0`.

## 23. v1.2.1 — sesión persistente + `jav pair` + Auto-TOFU (2026-10-16, VPS → TECNO por WSS/Tailnet)

Cierre de la deuda de latencia/UX detectada en la prueba de campo sobre el
TECNO. **Go, sin dependencias nuevas.** `versionName 1.2.1` / `versionCode 3`.

**Cambios de código**
- `pkg/jam/jam.go`: **sesión persistente compartida** (`sharedMu`,
  `sharedClient`, `sharedCfg`). `Dial()` devuelve la sesión compartida
  (la abre/renueva si cambió `url|token|fp`); `Call`/`CallTimeout` la
  serializan y, ante error de transporte, cierran + **1 reconexión + reintento**.
  `Close()` es no-op sobre la sesión compartida; `resetShared()` la cierra.
  Cierre ordenado generalizado en `closeConn()` (frame `close` + eco,
  `closeTimeout` 500 ms) — corrige el `4001: BUSY` del cierre abrupto.
- `pkg/jam/config.go` (nuevo): `Config` + `LoadConfig`/`SaveConfig`
  (atómico, `0600`) + `UpdateConfig`; prioridad **env → `config.json` →
  default**; accessors de IA (`OpenRouterAPIKey`, `AIModel`, `AIBaseURL`,
  `AIAPIKey`). `JAV_CONFIG` permite otra ruta (tests).
- `pkg/jam/pair.go` (nuevo): `NormalizeAddr` + `Pair` (hello +
  `get_device_info` + Auto-TOFU + escritura de config).
- `pkg/jam/jam.go`: **Auto-TOFU** (`pinnedTLSConfigCapture`): en `wss://` sin
  pin, captura el SHA-256 del cert, lo acepta y lo persiste; con pin, comparación
  en tiempo constante (`CERT_MISMATCH`).
- `cmd/jav/pair.go` (nuevo) + `cmd/jav/main.go`: subcomando `jav pair
  <ip-o-url> <token> [openrouter_key]` (sin args → servidor MCP stdio igual que
  antes). `cmd/audit-mcp` excluye `cmd/jav/pair.go` del scan `no-stdout-statico`
  (es contrato CLI, no framing MCP).
- `pkg/jev` + `pkg/director/s2.go`: consumen la config de IA (env → config),
  sin `.env` obligatorio.
- Hints `UNAUTHORIZED`/`CONNECTION_FAILED` ahora sugieren `jav pair …`.

**Prueba en vivo (VPS → TECNO Pova 4, WSS/Tailnet)**
```
jav pair 100.105.124.102 <token>
✓ Vinculado con TECNO TECNO LG7n (SDK 31) en wss://100.105.124.102:38472/
  [TOFU sha256: 036898d996256f8e…]   (~0.98 s)
```
Ráfaga n=10: avg **320 ms** (vs **989 ms** con `dial`+`hello` por llamada),
`hello` **0** extra (vs 11), `device_status` ×10 con **0 `BUSY`**.

**Verificación (Go)**
```
gofmt -l cmd/ pkg/                                   # vacío
go vet ./...                                         # 0
go test ./...                                        # verde salvo el
                                                     #   preexistente pkg/normalizer
                                                     #   (logs/ gitignored)
make build                                           # dist/jav-linux-amd64
go run ./cmd/audit-mcp --bin dist/jav-linux-amd64    # 12/12 PASS
```
`token-budget-startup` sigue en **≈1631 tokens ≤ 3000**;
`tools-count-38`, `tools-schema`, `no-stdout-statico` en verde.

**Android (`android-app`)** — solo `versionName 1.2.1` / `versionCode 3`; sin
cambios de código Kotlin. `./gradlew :app:testDebugUnitTest` (88/88) y
`assembleDebug` siguen a cargo del workflow CI (JDK 17 temurin), como en §22.
