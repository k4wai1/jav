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

## 2b. Verificación en árboles reales (2026-10-02, LG7n API 31)

Procedimiento: receiver temporal `DUMP_WA`/`DUMP_SELF` (eliminado tras
verificar) + `uiautomator dump` + comparativa de anclas por script.

- **WhatsApp (chat, 124 nodos)**: anclas 73/86 = **84.9%** vs
  **piso de ruido uia-vs-uia = 80.2%** (el chat es vivo: timestamps y
  mensajes cambian entre dumps). Diferencia sistemática restante =
  nodos invisibles que uiautomator incluye y nosotros podamos por diseño.
  Latencia: **264 ms**.
- **Ajustes (estático, 66 nodos)**: anclas **26/26 = 100%**,
  0 nodos perdidos. Latencia: **106 ms**.
- **Escalado medido**: ~2 ms/nodo (IPC por nodo). El umbral < 100 ms
  vale para pantallas típicas (≤50 nodos); árboles grandes escalan lineal,
  con tope 500 (peor caso ~1 s). Sigue siendo 16× mejor que uiautomator.
- **FLAG_SECURE**: `AccessibilityWindowInfo.isSecure()` **no existe**
  (verificado en `android.jar` API 34). Experimento con `FLAG_SECURE`
  en ventana propia: `rootInActiveWindow` devuelve el árbol completo
  (el sistema solo oculta ventanas seguras **ajenas**). Heurística final:
  `root == null → secure=true` (cubre ventanas ajenas seguras ycold-start),
  documentada en `dumpUiTree()`. El cold-start de WhatsApp devolvió
  `nodes=0, secure=true` por timing, no por flag: reintentar en caliente.
- **Bug encontrado y corregido**: `snapshot_id` era campo de instancia;
  al recrearse el servicio se reiniciaba (visto: `snapshot=1` repetido).
  Ahora persiste en `SharedPreferences` (`jam.snapshot_id`) en cada dump.

## 2c. Broadcasts implícitos filtrados

`am broadcast -a <acción>` a un receiver de manifest **no llega** si el
paquete está en stopped o por restricciones de broadcasts implícitos.
Usar broadcast **explícito**: `am broadcast -a … -n pkg/.Clase`.
(Así se dispararon los dumps temporales de §2b.)

## 3. Fase 2 — bucle WS end-to-end (2026-10-02, LG7n API 31)

```bash
adb forward tcp:38472 tcp:38472
cd mcp-server && uv sync && uv run python scripts/fase2_check.py
```

El script: token desde logcat (`JamWs token=…`), abre WhatsApp,
`hello` → `get_foreground` → `dump_ui` → `tap` (selector descubierto:
navegación "Atrás") → `tap_node` → `dump_ui` → check `STALE_SNAPSHOT`.

Medido: `hello` con scopes `['read','ui']`; `foreground` WhatsApp;
`dump1` 153 nodos; **`tap ok via=action_click`** (resource suffix
`whatsapp_toolbar_home`); `tap_node` con snapshot previo → `STALE_SNAPSHOT`
(correcto: el tap cambió la UI); `dump2` snapshot 11→13; snapshot viejo
rechazado con `STALE_SNAPSHOT`. **OK fase2.**

Fixes que salieron del propio test: `hello` debe responder **plano**
(PROTOCOL §2, sin envoltura `result`); `GestureResultCallback` es clase
**anidada** de `AccessibilityService` (no existe top-level en API 34);
`JsonArrayBuilder.add(String)` no resolvió → `JsonPrimitive` explícito.

## 3. Gotchas encontrados

- `settings put` del servicio **solo pega si `accessibility_enabled=1`
  se escribe antes**. Al revés, el `get` devuelve `null`.
- El serving de Shizuku reporta `OK (permiso)` aun siendo el clon
  Shizuku+ (`af.shizuku.plus.api`): `pingBinder()` + `checkSelfPermission()`
  responden. **No verificado con `newProcess` real** — queda para Fase 3,
  que instalará el oficial `moe.shizuku.privileged.api`.
- Tras renombrar el paquete hay que desinstalar el viejo
  (`adb uninstall dev.jev.android` puede fallar si ya no está; inocuo).
