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
