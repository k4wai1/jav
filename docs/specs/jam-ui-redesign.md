# jam-ui-redesign — propuesta de UI moderna, limpia y ligera

> Estado: propuesta `@architect` · sin código · sin keys · 100% genérica.
> Alcance: solo `android-app/` vistas XML nativas + `docs/**`.
> Ejecuta `@coder`; este doc no compila nada.

## 0. Principios (vinculantes)

1. **Diagnóstico > estética.** Cada píxel responde "¿funciona?" en <3 s:
   servidor, permisos, token, último método. Nada decorativo sin fuente de verdad.
2. **Cero dependencias nuevas.** Permitido (AGENTS.md §4): `appcompat`,
   `core-ktx`, `kotlinx-serialization-json`, `coroutines-android`,
   `shizuku api+provider`, `Java-WebSocket`, `bcprov/bcpkix`. Prohibido sin
   enmienda: Compose, Hilt/Dagger, Room, Retrofit, Ktor, Material library,
   Tink/security-crypto, SDK Tailscale, KSP/KAPT, Espresso.
3. **Ligera de verdad:** build Gradle debug <2 min en máquina pequeña
   (`gradle.properties` actual: `-Xmx1024m`, sin daemon, `workers.max=1`,
   cache on — no tocar), APK ~16 MB, sin minify en debug / R8 solo release.
4. **Jam sigue servicio de fondo de bajo consumo.** La UI no observa en
   continuo: refresca en `onResume` + callbacks puntuales (listener Shizuku,
   resultado de permiso). Nada de polling, handlers periódicos, ni observers
   que mantengan el proceso despierto. El FGS (`JevForegroundService`,
   `specialUse`, `START_STICKY`) no cambia.
5. **Error honesto.** Todo estado degradado muestra código + hint accionable
   (`ACCESSIBILITY_DISABLED`, `SHIZUKU_UNAVAILABLE`, `SHIZUKU_DENIED`),
   nunca un "…" eterno ni un verde falso.

## 1. Estado actual (deuda que motiva el rediseño)

Fuente: `MainActivity.kt`, `activity_main.xml`, `JevForegroundService.kt`,
`CommandDispatcher.kt`, `JamWsServer.kt` (leídos 2026-10-09).

- Layout plano: un `LinearLayout` con 4 `TextView` de estado + 6 `Button`
  sueltos. Sin agrupación visual; el operador no distingue de un vistazo
  qué bloque falla.
- `tvServer` muestra **token en claro** (`MainActivity.refreshStatuses()`).
- `JevForegroundService.onCreate()` loguea **`token=<valor>`** en logcat.
  (`CommandDispatcher` solo loguea longitud — eso sí es aceptable.)
- Shizuku muestra solo trichotomía corre/sin-permiso/OK; sin PID/UID ni
  versión, inútil para diagnosticar "Shizuku corre pero bind falla".
- Sin distinción batería optimizada/ignorada (relevante: el SO mata el FGS).
- Sin visibilidad de clientes WS (single-client `BUSY` es invisible desde UI).
- Sin monitor de uso: N0/N1 vs acciones UI y último método no visibles.
- `dumpToLogcat` ("Volcar UI") es útil pero vive al mismo nivel que acciones
  críticas; merece sección diagnóstico separada.

## 2. Propuesta: 4 tarjetas + cabecera (XML nativo, sin CardView lib)

Sin `com.google.android.material` ni `androidx.cardview` (no están en §4).
"Tarjeta" = `LinearLayout` vertical con `background=@drawable/card_bg`
(shape con `solid` + `corners 12dp` + `stroke 1dp`), `padding 16dp`,
`marginTop 12dp`, cabecera `TextView` bold 14sp + cuerpo 13sp monoespaciado
para valores (`android:typeface="monospace"`). Scroll raíz: envolver en
`ScrollView` (el layout actual no scrollea en pantallas pequeñas). Colores:
solo `?attr/colorPrimary`, `android:textColorPrimary/Secondary` y un
punto de estado (`●` verde/rojo/ámbar como texto, sin drawables nuevos).
Tema: el actual `Theme.AppCompat.DayNight.NoActionBar` — respetar modo
oscuro sin trabajo extra.

Estructura (una sola `Activity`, sin fragments ni navigation):

```
ScrollView
└─ LinearLayout
   ├─ Header: "Jam" + versión (BuildConfig.VERSION_NAME) + subtítulo proceso
   ├─ Tarjeta 1: Servidor
   ├─ Tarjeta 2: Permisos
   ├─ Tarjeta 3: Token
   └─ Tarjeta 4: Monitor liviano + diagnóstico
```

## 3. Tarjeta 1 — Estado del servidor

Campos:

| Campo | Fuente de verdad | Formato |
|---|---|---|
| Estado | `JevForegroundService.serverOn` (+ `JamWsServer.running` si se expone) | `● ON` / `● DETENIDO` |
| Bind | constante `PORT = 38472`, host fijo | `ws://127.0.0.1:38472/` (texto, no clicable) |
| Clientes | `JamWsServer`: conexión activa (0/1) + autenticada sí/no | `clientes: 0` · `autenticado: —` |
| Protocolo | `CommandDispatcher.PROTOCOL_VERSION` | `protocolo v1` |
| Uptime / arranque | timestamp de `onCreate` del FGS (nuevo campo `startedAtMs`, volatile) | `desde HH:MM:SS` |

Reglas:

- Sin botón start/stop: el FGS arranca en `MainActivity.onCreate` y es
  `START_STICKY`. La tarjeta es lectura; si `serverOn == false` muestra hint
  ("reabre la app; si persiste revisa logcat tag JamWs").
- No exponer jamás el listener WSS tailnet aquí hasta Fase 2b; cuando llegue,
  segunda línea `wss://<ip>:<puerto>/` con regla TLS-por-bind (AGENTS §3.2).
- Conteo de clientes sin identidad: número + estado auth, nunca token ni IP
  completa en UI (la IP/origen queda en audit ring, no en pantalla).

## 4. Tarjeta 2 — Permisos (tiempo real en `onResume`)

Tres filas de estado + una fila de batería + botones contextuales:

| Fila | Check | Botón si falla |
|---|---|---|
| Accesibilidad | `Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES` contiene el `ComponentName` (método actual `isAccessibilityOn()`) | "Abrir ajustes" → `ACTION_ACCESSIBILITY_SETTINGS` |
| Shizuku | `ShizukuBridge.isRunning()` + `hasPermission()`; si OK mostrar **UID/PID si la API los expone** (`Shizuku.getUid()` / binder PID; si no disponible mostrar `permiso API_V23 concedido`) | "Pedir permiso" (visible solo si corre + sin permiso, como hoy) |
| Batería | `PowerManager.isIgnoringBatteryOptimizations(packageName)` en tiempo real | "Pedir ignorar" → `ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS` (con fallback a `ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS` si el intent directo es rechazado) |
| Grants N1 (colapsado) | los actuales `hasUsageAccess()`, `JamNotificationListener.isConnected()`, runtime `READ_CONTACTS/CALENDAR/LOCATION/CAMERA` | los 4 botones actuales se conservan pero agrupados bajo subtítulo "Accesos de catálogo (opcionales)" y con texto reducido |

Reglas:

- Refresco solo en `onResume` + callback `OnRequestPermissionResultListener`
  (registrado en `onResume`, retirado en `onPause` — mantener el fix de leak
  actual). Nada de `NetworkCallback` ni polling aquí.
- Shizuku: nunca intentar arrancarlo desde la app (AGENTS §2.7). Mensaje si
  no corre: "Shizuku no iniciado — ábrelo y arráncalo" (texto actual, conservar).
- Accesibilidad apagada no bloquea `force_stop`/`screenshot` degradado: la fila
  lo indica pero no pinta toda la tarjeta en rojo (el servidor sigue vivo).

## 5. Tarjeta 3 — Gestión de token (deuda de secreto a cerrar)

### 5.1 Deuda registrada (cerrar en esta misma tarea, prioridad alta)

1. `MainActivity.refreshStatuses()` compone `"Token: ${AuthStore...}"` en claro.
2. `JevForegroundService.onCreate()` loguea `"JamWs token=$token ..."`.
3. Riesgo: cualquier app con `READ_LOGS` (o un `adb logcat` olvidado, o una
   captura de pantalla de esta tarjeta) exfiltra el bearer completo; el token
   vive en `SharedPreferences` sin cifrar hasta Fase 2b (Keystore).

### 5.2 Comportamiento propuesto

- Mostrar **máscara fija**: `Token: ••••abcd` (últimos 4 chars) o `••••`
  si se prefiere cero fuga. Nunca longitud exacta ni prefijo (el prefijo
  facilita fuerza bruta si el resto se filtra).
- Botón **"Copiar"**: copia el valor completo al clipboard vía
  `ClipboardManager.setPrimaryClip` (misma API ya usada por `set_clipboard`,
  sin Shizuku) + `Toast` "copiado". No lo pega en ningún `TextView`.
- Botón **"Regenerar"** controlada: diálogo de confirmación nativo
  (`AlertDialog` de AppCompat, sin lib nueva) con texto "invalida el cliente
  actual"; al confirmar: sobrescribir `KEY` en `jam_auth`, `Toast` + refresco
  de máscara. Requiere que no haya cliente autenticado conectado (si
  `active != null && authed` → abortar con hint "desconecta el cliente antes").
  Este gate evita dejar al operador bloqueado a mitad de sesión.
- Logcat: sustituir ambos sitios por `token_sha256=<8 hex>` o
  `token_set=true len=<n>` (longitud sí, valor nunca). Mantener `JevLog`
  debug-only (ya es no-op en release).
- Fuera de alcance de esta tarjeta (anotar, no hacer): cifrado Keystore
  (Fase 2b), rotación con `admin` scope vía WS, audit de regeneración
  (cuando exista el ring de 500 entradas de Fase 6).

## 6. Tarjeta 4 — Monitor liviano + diagnóstico

Contadores en memoria, sin persistencia, sin Room, coste O(1) por request:

| Métrica | Cómo (sin IPC extra) |
|---|---|
| `N0` (métodos sin permisos nuevos) | contador `AtomicLong` en `CommandDispatcher.dispatch` por grupo |
| `N1` (métodos con grant de usuario) | idem |
| `UI` (dump/tap/type/scroll/back/wait/foreground/screenshot/… ) | idem (o `UI = total − N0 − N1`) |
| `clics UI locales` | contador incrementado en cada `OnClickListener` de la Activity (diagnóstico "¿el operador toca o solo mira?") |
| `último método` | `volatile String lastMethod + lastResult(code)` + hora; se actualiza en `dispatch` (éxito o código `JamError`) |
| `snapshot` | `lastSnapshotId + nodes + ms` del último `dumpUiTree()` (ya se mide en `dumpToLogcat`) |

UI: 3 líneas monoespaciadas (`N0 12 · N1 3 · UI 40 · clics 5`,
`último: tap_node OK 12:04:31`, `snapshot #812 · 66 nodos · 106 ms`) +
botón "Volcar UI (logcat)" (el actual, renombrado a "Diagnóstico: volcar UI")
que conserva su `Toast` con conteo. Sin gráficos, sin historial, sin sparkline.

Límites: los contadores se resetean al morir el proceso (documentarlo en la
tarjeta con "sesión"); no se exponen por WS en esta fase (evita superficie);
`MAX 500 nodos/snapshot` y latencia ≤300 ms / ≤150 nodos se mantienen como
criterio Fase 1 y se muestran implícitamente vía la línea de snapshot.

## 7. Restricciones de implementación (para `@coder`)

- Solo `android-app/app/src/main/res/layout/activity_main.xml`,
  `@drawable/card_bg.xml` (nuevo, shape), `strings.xml` y `MainActivity.kt`
  (+ getters mínimos `volatile`/`AtomicLong` en `JevForegroundService`,
  `JamWsServer`, `CommandDispatcher` si la tarjeta los necesita; nada más).
- Sin fragments, sin ViewModel/LiveData, sin RecyclerView: `findViewById` +
  `refreshStatuses()` en `onResume` como hoy.
- Acceso a batería: `getSystemService(PowerManager::class.java)` con
  `try/catch` (algunos OEM devuelven null) → estado "desconocido" honesto.
- Shizuku PID/UID: usar solo lo que `api:13.1.5` expone sin permiso extra;
  si no hay API estable, mostrar `permiso concedido (API_V23)` y no inventar.
- Clipboard "Copiar": requiere API 33+ nota — `setPrimaryClip` desde
  foreground está permitido; no usar `getPrimaryClip` (restringido Android 10+).
- Regeneración de token: invalidar también `authedScopes` del servidor
  (desconectar al cliente con `UNAUTHORIZED` limpio) — detallarlo en el diff.
- `android:allowBackup="false"` ya protege el token de backups; no añadir
  `android:exported` ni intents nuevos salvo los 3 de ajustes citados.

## 8. Criterios de aceptación

1. `grep -rn 'su -c\|exec(.*su\|ProcessBuilder(.*su' android-app/` → vacío
   (test permanente §2, no regresa).
2. `grep -rn 'token=\$\|Token: \$' android-app/app/src/main` → vacío
   (deuda §5 cerrada: ni UI ni logcat muestran el secreto).
3. Build `cd android-app && ./gradlew assembleDebug` <2 min y APK debug
   ±16 MB (documentar cifras reales en `docs/BUILD.md`).
4. Recorrido manual en banco (TECNO KJ5 API 33): abrir app → 4 tarjetas
   legibles en modo claro/oscuro; apagar accesibilidad → fila ámbar + hint;
   parar Shizuku → `SHIZUKU_UNAVAILABLE`; conectar cliente WS → `clientes: 1`;
   copiar token → pega fuera; regenerar con cliente conectado → aborta con hint.
5. `docs/PROTOCOL.md` y `docs/TESTING.md` actualizados solo si cambia
   superficie visible (nuevo `startedAtMs`/`lastMethod` son locales; si se
   exponen por WS lo anota `@architect` primero).
6. Sin commits (los hace el operador). Sin keys ni secretos en el diff.

## 9. No-objetivos explícitos

- WSS tailnet / Keystore / audit ring / `shell` (Fases 2b y 6).
- Filtros `statusBarBackground`/`navigationBarBackground` (viven en
  `ui_normalizer.py`, Fase 4, no en esta UI).
- Gráficas de uso, historial persistente, multi-idioma, onboarding animado.
- Nada app-específico (paquetes, chats, contactos): esta spec es 100% genérica.
