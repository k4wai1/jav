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
- `apkanalyzer manifest print`: `package=dev.jev.jam`, 2 servicios,
  `ShizukuProvider` (`dev.jev.jam.shizuku` + `INTERACT_ACROSS_USERS_FULL`),
  permiso `moe.shizuku.manager.permission.API_V23` fusionado,
  `FOREGROUND_SERVICE_SPECIAL_USE`, property FGS ✓

## 4. Instalación y verificación en dispositivo (HECHA 2026-10-01)

El TECNO LG7n (target) se cayó del USB; se verificó en un **TECNO KJ5,
Android 13 (API 33)**, sin root, con Shizuku y Tailscale instalados
(equipo ideal para la ruta non-root + Shizuku).

```bash
adb install -r app/build/outputs/apk/debug/app-debug.apk   # Success
adb shell am start -n dev.jev.jam/.MainActivity
adb shell 'dumpsys activity activities | grep -m1 mFocusedApp'
# mFocusedApp=ActivityRecord{… dev.jev.jam/.MainActivity} ✓
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
./gradlew :app:testDebugUnitTest --tests "dev.jev.jam.ui.DisplayScaleTest" --tests "dev.jev.jam.ui.UiTreeExtractorTest"
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
./gradlew :app:testDebugUnitTest --tests "dev.jev.jam.nat.*" :app:assembleDebug
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
  hay que re-habilitar Jam en Ajustes → Accesibilidad y arrancar Shizuku.
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
./gradlew :app:testDebugUnitTest --tests "dev.jev.jam.nat.NatPoliciesTest" :app:assembleDebug
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
top hoy `org.fossify.math` 647.2 min / `dev.jev.jam` 144.1 min;
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
./gradlew :app:testDebugUnitTest --tests "dev.jev.jam.nat.NatPoliciesTest" --console=plain
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
verbatim y `NatPolicies.isCritical` (Jam) solo cubría formas plenas
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
  canonicaliza antes del frame WS (el gate `planned` lo pone Jam).
- Tests: JVM `NatPoliciesTest` 2 nuevos (canónica SEND/CALL/VIEW +
  cortas críticas); Go `sendintent_test.go` (misma matriz);
  Go `pkg/normalizer/replay_test.go`: paridad conductual Go vs Python.
- Cobertura replay real (no inventada): 70 `run-*.jsonl`
  (`mcp-server/logs/` + `logs/`) con **0 árboles crudos** (solo
  forense/conteos); replay sobre 2 dumps reales con árbol:
  `mcp-server/tests/fixtures/wa_home.json` (WhatsApp, 174→65) y
  `pkg/normalizer/testdata/jam_live_18.json` (Jam onboarding en e03638e5
  vía `dump_ui`, 18→10; token saneado a `TOKEN-REDACTED`). Esperado
  generado por Python (`normalize` + `build_table` + `serialize_table` +
  `zone_of`, 720x1440); Go da poda/índices/zonas 3×3 idénticos.
- Rutas Go en raíz (`pkg/`, `cmd/`, `go.mod`); `go-mcp/` no existe:
  solo queda la nota histórica en `docs/specs/go-migration-plan.md §2`
  (reubicación documentada, sin código que actualizar).

```bash
./gradlew :app:testDebugUnitTest --tests "dev.jev.jam.nat.NatPoliciesTest"  # 14/14 verdes
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
./gradlew :app:testDebugUnitTest --tests "dev.jev.jam.nat.NatPoliciesTest"  # 14/14 verdes
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
   lo deja OK. Procesos `dev.jev.jam:shell` antiguos (Shizuku) sobreviven
   al force-stop; no afectan (no escuchan WS).
3. Accesibilidad: hizo falta ciclo limpio (`settings delete` +
   `put` con `ComponentName` **plano**
   `dev.jev.jam/dev.jev.jam.service.JevAccessibilityService` — la forma
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
./gradlew :app:testDebugUnitTest --tests "dev.jev.jam.ui.SelectorResolverTest"
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
