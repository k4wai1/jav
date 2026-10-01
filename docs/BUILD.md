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
- `apkanalyzer manifest print`: `package=dev.jev.android`, 2 servicios,
  `ShizukuProvider` (`dev.jev.android.shizuku` + `INTERACT_ACROSS_USERS_FULL`),
  permiso `moe.shizuku.manager.permission.API_V23` fusionado,
  `FOREGROUND_SERVICE_SPECIAL_USE`, property FGS ✓

## 4. Instalación y verificación en dispositivo (HECHA 2026-10-01)

El TECNO LG7n (target) se cayó del USB; se verificó en un **TECNO KJ5,
Android 13 (API 33)**, sin root, con Shizuku y Tailscale instalados
(equipo ideal para la ruta non-root + Shizuku).

```bash
adb install -r app/build/outputs/apk/debug/app-debug.apk   # Success
adb shell am start -n dev.jev.android/.MainActivity
adb shell 'dumpsys activity activities | grep -m1 mFocusedApp'
# mFocusedApp=ActivityRecord{… dev.jev.android/.MainActivity} ✓
```

`uiautomator dump` confirma el paquete en foreground con `android:id/content`
**vacío** (sin hijos): la pantalla gris es la Activity stub sin `setContentView()`,
comportamiento esperado de Fase 0. La UI real de onboarding llega en Fase 1.

Criterio Fase 0d: app instalada y en foreground ✓ + grep `su` vacío ✓ + este archivo ✓.
