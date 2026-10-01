# TESTING.md — verificación manual sin Android Studio (Fase 1)

Banco: TECNO KJ5, Android 13 (API 33), sin root. App: `dev.jev.jam` (Jam).

## 1. Tests JVM (sin dispositivo)

```bash
cd android-app
./gradlew :app:testDebugUnitTest
# Report: app/build/test-results/testDebugUnitTest/
```

Cubre: raíz nula → `secure`, ids BFS contiguos, poda de invisibles,
tope 500 determinista, mapeo de campos/bounds, `snapshot_id`.
Estado: **6/6 en verde.**

## 2. Verificación en dispositivo (`dump_ui` vs `uiautomator`)

```bash
adb install -r app/build/outputs/apk/debug/app-debug.apk
# Orden importa: primero el master switch, luego la lista
adb shell settings put secure accessibility_enabled 1
adb shell settings put secure enabled_accessibility_services \
  dev.jev.jam/dev.jev.jam.service.JevAccessibilityService
adb shell 'dumpsys accessibility | grep -m1 "Enabled services"'
adb shell am start -n dev.jev.jam/.MainActivity
# Localizar el botón y pulsarlo (banco visual temporal hasta Fase 2)
adb shell uiautomator dump /sdcard/jam_ui.xml
adb shell cat /sdcard/jam_ui.xml | grep -oiE '<node[^>]*volcar[^>]*>'
adb shell input tap 200 450
adb logcat -d | grep JamUi
```

Resultado medido (2026-10-01, pantalla de onboarding):
`dump snapshot=1 nodes=13 ms=40 secure=false`.
Comparación de anclas (`text` o `resource_id` no nulos):
**9/9 = 100%** (criterio: ≥95%). Latencia **40 ms** (criterio: < 100 ms).

## 3. Gotchas encontrados

- `settings put` del servicio **solo pega si `accessibility_enabled=1`
  se escribe antes**. Al revés, el `get` devuelve `null`.
- El serving de Shizuku reporta `OK (permiso)` aun siendo el clon
  Shizuku+ (`af.shizuku.plus.api`): `pingBinder()` + `checkSelfPermission()`
  responden. **No verificado con `newProcess` real** — queda para Fase 3,
  que instalará el oficial `moe.shizuku.privileged.api`.
- Tras renombrar el paquete hay que desinstalar el viejo
  (`adb uninstall dev.jev.android` puede fallar si ya no está; inocuo).
