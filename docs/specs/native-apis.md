# native-apis — catálogo de herramientas MCP NATIVAS (carril APIs directas, sin Jev)

> Estado: **spec v1 2026-10-07**. Redacta `@architect` (solo `docs/**`).
> No toca código. En conflicto, **AGENTS.md manda** (scopes, shell OFF
> hasta Fase 6, sin `su`, token obligatorio, audit 500).
>
> Alcance: carril **APIs directas** — lo que Jam puede responder por
> llamada a framework Android / Shizuku sin que Jev interprete UI ni
> mueva dedos. El carril Jev (dual-tier `run_goal`, `generic-dual-tier.md`)
> sigue siendo el único que toca UI por accesibilidad.
>
> **Cero literales normativos de app.** Los paquetes/URIs concretos que
> aparecen abajo son **ejemplos no-normativos** (aportados en runtime por
> S2/operador, nunca defaults del contrato ni de `src/`). Sin keys,
> sin tokens, sin contactos en este documento.

## 0. Base ya expuesta (verificada en código)

Fuente: `android-app/app/src/main/java/dev/jev/jam/socket/CommandDispatcher.kt`
+ `PROTOCOL.md §4`. Lo que Jam ya sirve hoy:

| Método | Scope | Grant | Notas |
|---|---|---|---|
| `dump_ui` | `read` | no | snapshot monotónico, máx. 500 nodos |
| `tap` / `tap_node` | `ui` | no | `ACTION_CLICK` primero si clickable; `snapshot_id` exigido en `tap_node`/`type` |
| `type` | `ui` | no | `ACTION_SET_TEXT`; exige foco (`NOT_FOCUSED` si no) |
| `scroll`, `press_back`, `press_home`, `wait_for_node` | `ui` | no | verificación en cliente |
| `get_foreground` | `read` | no | `{package, activity}` |
| `open_app` | `ui` | **sin grant** | Shizuku `am start`; fallback `monkey`; verificar con `get_foreground` |
| `force_stop` | `shell` | **sin grant** | no necesita accesibilidad |
| `screenshot` | `read` | no | `takeScreenshot` API 30+; `SECURE_SURFACE`; >4 MiB → `PAYLOAD_TOO_LARGE` |
| `set_clipboard` | `ui` | **sin grant** | la propia Jam hace `setPrimaryClip`; sin Shizuku |
| `shell` | `shell` | con grant | **hasta Fase 6: `METHOD_NOT_ALLOWED` explícito** (AGENTS.md §2.8) |
| `list_packages`, `grant_permission`, `get_audit` | según `PROTOCOL.md` | `grant_permission` = `shell` **con grant** | `get_audit` = `admin`, ring 500 |

Todo método nuevo abajo **reutiliza** esta envoltura (`{id,method,params}` →
`{id,ok,result|error,code}`), el handshake `hello` con token bearer en
**todos los binds** (loopback incluido), lockout 5/60 s → 5 min, frame
máx. 4 MiB, rate 50 req/s (shell 5/s), y entra al **audit ring 500**
(método, scope, hash de args, resultado, timestamp, IP origen).

### Principios transversales del catálogo

1. **Sin `su` en ningún camino.** Puerta privilegiada = solo Shizuku
   (`grep su` → vacío, test permanente AGENTS.md §2.2).
2. **`minSdk 29`, `targetSdk 34`.** Todo lo que pida API 30+ lleva
   fallback o se marca (gotchas §5.6–5.7: `takeScreenshot` API 30+,
   FGS `specialUse` en 34).
3. **Dependencias permitidas** (AGENTS.md §4): nada de Retrofit/Ktor/Room/
   Compose/Hilt para exponer estas tools. Framework puro + Shizuku API.
4. **Lectura PII ≠ lectura técnica.** Batería/RAM/Build son `read` sin
   fricción; notificaciones/contactos/calendario/ubicación son `read`
   **sensible**: se auditan, se minimizan (proyección de columnas, sin
   volcado crudo a forense salvo hash/longitud) y su activación requiere
   opt-in del usuario en el dispositivo.
5. **Escritura/irreversible → `confirm: true` del operador + scope
   elevado.** Patrón heredado del shell-denylist (`admin` + `confirm`):
   se generaliza a `settings put`, borrados, envíos a terceros,
   cambios de cuenta/pagos. Sin `confirm` → se planea sin ejecutar
   (`planned: true` + `preview`), igual que el gate crítico de
   `generic-dual-tier.md §8.2`.
6. **Sin `run_sequence`.** Cada tool nativa = una primitiva. El loop
   compone; la app no encadena.

### Clasificación de fases usada en cada ficha

- **P0** — sin permisos nuevos. Solo manifest normal o sin permiso.
  Entra primero.
- **P1** — con grant del usuario (runtime `requestPermissions` o acceso
  especial en Ajustes). Requiere onboarding UI (Fase 1 ya la inició).
- **P2** — Shizuku-only (shell `settings`/`appops`/`dumpsys`/`am`).
  Hereda todo el régimen shell: scope `shell`, grant activo
  (1 comando / 5 / 30 min, bloqueo hasta 60 s), y hasta Fase 6 el
  dispatcher lo rechaza con `METHOD_NOT_ALLOWED` — estas fichas son
  **diseño para Fase 6+**, no para implementar antes.
- **IMPOSIBLE** — non-root no lo permite (firma/sistema) o la plataforma
  lo bloquea por privacidad. Se documenta para no prometerlo.

---

## 1. Batería — `get_battery`

- **Fuente API exacta:** `BatteryManager` (`BATTERY_PROPERTY_CAPACITY`,
  `BATTERY_PROPERTY_CHARGE_COUNTER`, `EXTRA_STATUS`, `EXTRA_PLUGGED`,
  `EXTRA_TEMPERATURE` vía `ACTION_BATTERY_CHANGED` sticky) +
  `PowerManager.isPowerSaveMode()`.
- **Permiso:** ninguno (lectura de sticky broadcast + `BatteryManager`;
  `BATTERY_STATS` solo para histórico fino, no necesario).
- **Cómo se obtiene:** n/a. **P0.**
- **Scope MCP:** `read`.
- **Riesgos + compuerta:** nulo. Sin PII. Sin `confirm`.
- **Fase: P0.** Respuesta `{level_pct, charging, plugged, temp_c, saver}`.
- **Medir:** latencia p50 < 20 ms; parish: un `dump_ui` cuesta más.

## 2. RAM / almacenamiento / CPU — `get_memory`, `get_storage`, `get_cpu`

- **Fuente API exacta:**
  - RAM: `ActivityManager.getMemoryInfo()` (`availMem`, `totalMem`,
    `lowMemory`, `threshold`).
  - Almacenamiento: `StatFs(Environment.getDataDirectory().path)` +
    `StorageManager`/`StorageStatsManager` para desglose por app.
  - CPU: `Runtime.availableProcessors()` + lectura de
    `/proc/stat` (anon, sin permiso) o `ActivityManager.getProcessMemoryInfo`
    para per-proceso; carga instantánea vía delta de tiempos.
- **Permiso:**
  - Básico (`MemoryInfo`, `StatFs`, `/proc/stat` propio): ninguno → **P0**.
  - Desglose por app (`StorageStatsManager.queryStatsForPackage`,
    `UsageStatsManager`): `PACKAGE_USAGE_STATS` (acceso especial) → **P1**.
  - Detalle per-proceso ajeno: imposible sin shell/Shizuku → **P2**
    (`dumpsys meminfo/cpuinfo` vía Shizuku).
- **Cómo se obtiene:** P0 nada; P1 `Settings.ACTION_USAGE_ACCESS_SETTINGS`
  (el usuario lo activa en Ajustes; la app lo guía, nunca lo fuerza).
- **Scope MCP:** `read` (P0 y P1). El sub-modo `dumpsys` (P2) = `shell`
  con grant.
- **Riesgos + compuerta:** bajo. El desglose por app revela hábitos →
  minimización (solo la columna pedida), auditado, sin `confirm` para
  lectura; `confirm` no aplica (no hay escritura).
- **Fase: P0** (básico) **> P1** (desglose) **> P2** (`dumpsys` fino).
- **Medir:** latencia P0 < 30 ms; P1 < 200 ms; tamaño de respuesta < 4 KiB
  (agregar, nunca volcar tablas crudas).

## 3. Hardware — `get_device_info`

- **Fuente API exacta:** `android.os.Build` (`MANUFACTURER`, `MODEL`,
  `DEVICE`, `SDK_INT`, `SUPPORTED_ABIS`), `DisplayMetrics`
  (`widthPixels`, `heightPixels`, `densityDpi`), `BatteryManager`,
  `ActivityManager` (RAM total). Opcional: `PackageManager.hasSystemFeature`
  (`FEATURE_CAMERA`, `FEATURE_TELEPHONY`, …), `Locale`/`TimeZone`.
- **Permiso:** ninguno. `READ_PHONE_STATE` **no** necesario si no se
  pide IMEI/IMSI (y no se pide: ver riesgos). **P0.**
- **Scope MCP:** `read`.
- **Riesgos + compuerta:** fingerprinting. No exponer identificadores
  persistentes (`ANDROID_ID`, IMEI, MAC, serial) en este método; si algún
  día se necesitan → método separado `admin` + `confirm`. Este método:
  sin `confirm`.
- **Fase: P0.**
- **Medir:** respuesta < 2 KiB; útil como cabecera de forense
  (reproducibilidad banco KJ5/LG7n).

## 4. Settings — `settings_get`, `settings_put`

- **Fuente API exacta:** `Settings.System` / `Settings.Secure` /
  `Settings.Global` (`getString/putString`), `Settings.ACTION_*`
  para los accesos especiales; vía Shizuku: `settings get/put <ns> <k>`.
- **Permiso y obtención:**
  - `System` lectura: ninguno → P0 (get).
  - `System` escritura: `WRITE_SETTINGS` (acceso especial
    `ACTION_MANAGE_WRITE_SETTINGS`, el usuario lo concede en Ajustes) → **P1**.
  - `Secure` / `Global` escritura directa: `WRITE_SECURE_SETTINGS`
    (firma/privilegiada, **no concedible por runtime ni por `pm grant`**) →
    directo **IMPOSIBLE**; vía Shizuku-shell (`settings put`) → **P2**
    (régimen shell + grant Fase 6).
  - Lectura de claves sensibles (`Secure`: p. ej. localización,
    accesibilidad habilitada): legible según clave; las críticas solo
    vía shell → P2.
- **Scope MCP:** `settings_get` = `read`; `settings_put` = **`admin`**
  (AGENTS.md §3.4: settings es admin).
- **Riesgos + compuerta:** escritura en `Secure/Global` puede dejar el
  equipo sin accesibilidad/red/bloqueo (irreversible blando). **Denylist
  explícita** (claves críticas) → `admin` + `confirm: true`, mismo patrón
  que el shell-denylist; resto de `System` no crítico → `admin` +
  `confirm: true` igualmente (toda escritura de settings pide confirm;
  la lectura nunca).
- **Fase: P0** (get System) **> P1** (put System con `WRITE_SETTINGS`)
  **> P2** (Secure/Global vía Shizuku-shell, Fase 6+) **/ IMPOSIBLE**
  (directo sin Shizuku).
- **Medir:** % de claves objetivo legibles sin shell; tasa de denegación
  de `WRITE_SETTINGS`; cero escrituras sin `confirm` (grep forense).

## 5. Uso de apps — `get_app_usage`

- **Fuente API exacta:** `UsageStatsManager.queryUsageStats` /
  `queryEvents` (`PACKAGE_USAGE_STATS`).
- **Permiso:** `PACKAGE_USAGE_STATS` (acceso especial, no runtime).
- **Cómo se obtiene:** `Settings.ACTION_USAGE_ACCESS_SETTINGS`; el
  usuario lo activa por paquete; la app detecta y guía
  (`hasUsageAccess()`), nunca lo auto-concede. **P1.**
- **Scope MCP:** `read` (sensible, ver riesgos).
- **Riesgos + compuerta:** revela hábitos de uso (PII conductual).
  Minimización: ventana temporal acotada (param `hours`, máx. 24),
  agregación por paquete, sin eventos crudos por defecto; auditado.
  Sin `confirm` para lectura agregada; volcado de eventos crudos →
  `confirm: true`.
- **Fase: P1.**
- **Medir:** precisión de "app en foreground últimos N min" vs
  `get_foreground` muestreado; latencia < 300 ms.

## 6. Notificaciones + respuesta rápida — `list_notifications`, `reply_notification`

- **Fuente API exacta:** `NotificationListenerService`
  (`getActiveNotifications()`, `RemoteInput` para quick-reply;
  `cancelNotification()` para descartar).
- **Permiso:** `BIND_NOTIFICATION_LISTENER_SERVICE` + habilitación
  del usuario en `Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS`.
  **P1** (el grant más sensible de este catálogo).
- **Cómo se obtiene:** onboarding explícito; la app expone el estado
  (`notification_listening: bool`) en `hello.caps`; sin él →
  `NOTIFICATION_LISTENER_DISABLED` honesto.
- **Scope MCP:** `list_notifications` = `read` (sensible);
  `reply_notification` = **`ui`** (mutación visible) con régimen crítico.
- **Riesgos + compuerta:** lee contenido de terceros (OTP, mensajes,
  banca). Minimización obligatoria: proyección
  (`package`, `title`, `text_truncado`, `has_remote_input`,
  `posted_at`; **sin** `extras` crudos salvo pedido con `confirm`);
  en forense solo hash/longitud. `reply_notification` (enviar texto a
  un tercero) = acción crítica → `confirm: true` + preview
  (destino, texto-hash), igual que `generic-dual-tier §8.2`.
  `cancelNotification` → `confirm: true` (borrado).
- **Fase: P1** (con grant usuario). Sin grant no hay fallback honesto
  (el `dump_ui` no sustituye notificaciones; no inventar).
- **Medir:** cobertura (nº activas vs sombra del sistema), latencia
  < 200 ms, % de replies con `RemoteInput` disponible, cero lecturas
  de `extras` sin `confirm` en forense.

## 7. Contactos — `list_contacts`, `add_contact` (diferida)

- **Fuente API exacta:** `ContactsContract` (`ContactsContract.Contacts`,
  `CommonDataKinds.Phone/Email`, `ContentProviderOperation` para escritura).
- **Permiso:** `READ_CONTACTS` (runtime) para lectura; `WRITE_CONTACTS`
  (runtime) para escritura. **P1** ambas.
- **Cómo se obtiene:** `requestPermissions` en onboarding; degradado
  honesto (`CONTACTS_PERMISSION_DENIED`) si se niega.
- **Scope MCP:** `list_contacts` = `read` (sensible);
  `add_contact`/`update`/`delete` = `ui` + régimen crítico.
- **Riesgos + compuerta:** PII de terceros. Lectura: proyección mínima
  (`display_name`, `phone` solo si se pide, paginación `limit/offset`,
  filtro `query`), auditada. Escritura/borrado: `confirm: true` +
  preview; borrado → denylist blanda (igual que shell: `admin` +
  `confirm` si es masivo).
- **Fase: P1** (lectura primero; escritura después, con confirm).
- **Medir:** latencia < 300 ms en agenda de ~1k; paginación efectiva
  (respuesta < 100 KiB, nunca volcado completo).

## 8. Calendario — `list_events`, `create_event` (diferida)

- **Fuente API exacta:** `CalendarContract` (`Instances`/`Events`/
  `Calendars`; `ContentResolver.query/insert`).
- **Permiso:** `READ_CALENDAR` / `WRITE_CALENDAR` (runtime). **P1.**
- **Cómo se obtiene:** runtime en onboarding; degradado honesto.
- **Scope MCP:** `list_events` = `read` (sensible); `create_event` /
  `delete_event` = `ui` + régimen crítico.
- **Riesgos + compuerta:** PII temporal (dónde/cuándo está el usuario).
  Lectura acotada (`time_min/time_max`, máx. 7 días por defecto,
  `calendar_id` explícito). Creación: `confirm: true` + preview
  (título, inicio/fin, calendario destino); borrado: `confirm: true`.
- **Fase: P1** (lectura primero).
- **Medir:** exactitud de ventana (eventos devueltos ⊂ rango pedido);
  latencia < 300 ms.

## 9. Ubicación — `get_location`

- **Fuente API exacta:** `LocationManager` (`GPS_PROVIDER`,
  `NETWORK_PROVIDER`, `getLastKnownLocation`) o `FusedLocationProvider`
  (GMS; **evitar**: dependencia prohibida sin enmienda — usar
  `LocationManager` puro). `Geocoder` solo local si se necesita.
- **Permiso:** `ACCESS_COARSE_LOCATION` / `ACCESS_FINE_LOCATION`
  (runtime); `ACCESS_BACKGROUND_LOCATION` (API 29+, runtime separado +
  pantalla dedicada en Ajustes) solo si se justifica.
- **Cómo se obtiene:** runtime en contexto (nunca al arrancar); el modo
  preciso (`FINE`) se pide solo cuando el goal lo exige.
- **Scope MCP:** `read` (sensible, máxima).
- **Riesgos + compuerta:** PII de localización. `getLastKnownLocation`
  primero (sin activar GPS); fix fresco con `timeout_ms` acotado
  (máx. 30 s) y `max_age_s`. En forense: precisión redondeada + hash,
  nunca lat/lon cruda salvo `confirm: true` del operador. Background:
  **honesto** — posible non-root con el permiso, pero con fricción de
  plataforma (indicador persistente, throttling en segundo plano,
  política Play); Jam lo expone solo en foreground/FGS y documenta la
  degradación.
- **Fase: P1** (foreground). **Background: P1-restringido** (mismo
  permiso + justificación + FGS; medir throttling, no prometer fixes
  continuos).
- **Medir:** TTFF, precisión mediana (m), tasa de `TIMEOUT` honesto vs
  fix inventado (cero tolerancia a inventar).

## 10. Sesiones multimedia — `media_state`, `media_control`

- **Fuente API exacta:** `MediaSessionManager.getActiveSessions()`
  (requiere `NotificationListenerService` **o** `MEDIA_CONTENT_CONTROL`
  de firma) + `MediaController` (`getMetadata`, `getPlaybackState`,
  `getTransportControls().play/pause/skipToNext/...`).
- **Permiso:** vía NL (P1, §6) → **posible**; `MEDIA_CONTENT_CONTROL`
  directo → **IMPOSIBLE** non-root (firma). Control de volumen global:
  `AudioManager` (sin permiso para el propio stream).
- **Cómo se obtiene:** el mismo grant que §6; sin NL →
  `MEDIA_SESSIONS_UNAVAILABLE` honesto (no hay fallback por
  accesibilidad que sea fiable).
- **Scope MCP:** `media_state` = `read`; `media_control` = `ui`
  (play/pause/next/prev; el seek lleva `confirm` si altera contenido
  ajeno — por defecto sin confirm para transporte básico, con
  confirm para `stop`/colas destructivas).
- **Riesgos + compuerta:** metadatos revelan hábitos; transporte básico
  es reversible (sin confirm), mutación de cola/biblioteca → `confirm`.
- **Fase: P1** (montado sobre el grant NL). Sin NL: imposible honesto.
- **Medir:** % de sesiones visibles vs reproducción real; latencia
  comando→estado < 500 ms.

## 11. Cámara headless — `take_photo` (restringida)

- **Fuente API exacta:** `Camera2` (`CameraManager.openCamera`,
  `ImageReader JPEG`) o `camera2` + `MediaRecorder` para clip corto;
  obligatoriamente bajo **foreground service** con
  `foregroundServiceType="camera"` (API 29+; en 34 + permiso
  `FOREGROUND_SERVICE_CAMERA`).
- **Permiso:** `CAMERA` (runtime) + FGS visible con notificación
  persistente. **P1.**
- **Cómo se obtiene:** runtime + FGS activo; sin FGS en segundo plano
  la plataforma lo deniega (ver honestidad abajo).
- **Scope MCP:** `ui` (captura) con régimen crítico.
- **Riesgos + compuerta (honestidad):** Android 9+ restringe cámara en
  segundo plano; en API 29+ la cámara background silenciosa es
  **no-go por diseño de plataforma** (privacidad: indicador verde,
  FGS obligatorio). `take_photo` **solo** con: FGS + notificación +
  `confirm: true` del operador + auditado; **nunca silenciosa**,
  nunca sin indicador. Foto con pantalla apagada / device locked →
  degradado honesto según OEM (probar en banco, no prometer).
- **Fase: P1-restringida** (última de las P1; requiere validación en
  banco + revisión de amenaza). Alternativa P0: delegar a la app de
  cámara por intent (ver §12) en vez de captura propia.
- **Medir:** tasa de apertura con FGS, latencia captura < 2 s,
  tamaño < 4 MiB (WebP q80 si hace falta, mismo techo que screenshot),
  cero capturas sin `confirm` en audit.

## 12. Intents profundos — `send_intent`, `open_url` (+ direct-send)

- **Fuente API exacta:** `Context.startActivity(Intent)` /
  `am start` vía Shizuku (mismo camino que `open_app`, AGENTS.md §5.5:
  background-start restringido desde Android 10 → Shizuku `am start`,
  fallback `monkey`), `ACTION_VIEW`/`ACTION_SEND`/`ACTION_DIAL`/
  `ACTION_INSERT` (calendario/contactos), URIs `https`/`tel`/`mailto`/
  `geo`/`sms`.
- **Permiso:** ninguno nuevo para intents explícitos/view (P0); el
  contenido sensible lo pone el permiso de la app destino, no Jam.
  Ejemplo no-normativo: un deep-link con esquema de mensajería que
  pre-rellena texto — el **envío** sigue ocurriendo en la UI destino
  (carril Jev), no en Jam.
- **Cómo se obtiene:** validación estructural del intent
  (`action`, `uri` con forma, `package` con forma `a.b.c`) en código.
- **Scope MCP:** `open_url` / `send_intent` de solo-apertura = `ui`
  sin grant (misma clase que `open_app`); cualquier intent que
  **envíe/comunique/pague/borre** = régimen crítico (`confirm: true`
  + preview), igual que `generic-dual-tier §8.2`.
- **Riesgos + compuerta (honestidad direct-send):** el "envío directo
  sin UI" (mensaje que sale sin pasar por pantalla) es **IMPOSIBLE por
  API pública** para apps de terceros: no hay API de envío headless;
  el deep-link como máximo abre el editor pre-rellenado y el envío lo
  hace el usuario (o el carril Jev con compuertas + `confirm`). Jam
  **no** finge un `send_message` nativo; expone `send_intent`
  (abre+pre-rellena, verificado con `get_foreground`) y el envío, si
  el goal lo pide, va por UI automation con `confirm`.
- **Fase: P0** (apertura/pre-relleno) — el envío sigue en carril Jev.
- **Medir:** % de intents que dejan el foreground esperado en < 1 s;
  cero envíos atribuidos a `send_intent` en forense (el envío se
  audita en el paso Jev que lo hizo).

## 13. Portapapeles — `set_clipboard` (existe) + `get_clipboard` (restringido)

- **Fuente API exacta:** `ClipboardManager.setPrimaryClip` (ya existe,
  P0, `ui` sin grant) / `getPrimaryClip`; en host: `dumpsys clipboard`
  (adb, fuera del dispositivo).
- **Permiso:** escribir: ninguno → P0 (hecho). Leer en Android 10+:
  **solo foreground/IME por defecto** → lectura desde Jam en segundo
  plano = **IMPOSIBLE honesto** sin ser app en foco; vías reales:
  (a) host `dumpsys` (harness adb, no Shizuku-`shell`; ya previsto en
  `generic-dual-tier §12.4`), (b) pegado-en-campo-efímero + read-back
  del `text` del nodo (carril Jev), (c) Jam en foreground con foco
  (caso narrow, no general).
- **Scope MCP:** `set_clipboard` = `ui` (existe); `get_clipboard`
  (si se expone en foreground) = `read` sensible.
- **Riesgos + compuerta:** el clipboard contiene OTP/enlaces/secretos.
  En forense: solo `len` + `sha256` + vía de lectura, nunca crudo si
  el goal es sensible (§12.4). Lectura masiva/sondeo → prohibido.
- **Fase: P0** (set, hecho) **> host-only** (get vía `dumpsys`,
  harness, sin `shell` en dispositivo antes de Fase 6) **> P1-narrow**
  (get en foreground con foco).
- **Medir:** tasa `CLIPBOARD_EMPTY` honesto vs inventado (cero inventos);
  forma `https?://` validada por forma, sin literales de dominio.

---

## 14. Roadmap por fases y qué mide cada fase

### Fase N0 — P0, sin permisos nuevos (primera)

`get_battery`, `get_memory`, `get_storage` (básico), `get_device_info`,
`settings_get` (System), `open_url`/`send_intent` (apertura),
`set_clipboard` (ya existe).

- **Puerta:** sin onboarding nuevo; solo `read`/`ui` existentes.
- **Mide:** latencia p50/p95 por método (< 50 ms salvo storage),
  tamaño de respuesta (p95 < 4 KiB), cero crashes sin accesibilidad
  (UI degradada pero N0 viva, AGENTS.md §2.5), `pytest` + dispatcher
  verdes, `docs/PROTOCOL.md` actualizado por método.

### Fase N1 — P1, con grant del usuario (segunda, en orden)

1. `get_app_usage` (un permiso especial, bajo riesgo relativo).
2. `list_contacts` + `list_events` (PII, con proyección mínima).
3. `list_notifications` (+ `media_state` montado en el mismo grant).
4. `get_location` (foreground; background documentado-restringido).
5. `media_control` (transporte básico) → `reply_notification`
   (crítico, con `confirm`) → `create_event`/`add_contact` (críticos).
6. `take_photo` (última; revisión de amenaza + banco real).

- **Puerta por método:** onboarding que guía al Ajuste exacto, estado
  en `hello.caps`, error honesto sin grant (`*_DISABLED`/`*_DENIED`).
- **Mide por método:** tasa de grant otorgado, cobertura vs verdad del
  sistema (notificaciones activas, fix de ubicación), TTFF/mediana de
  precisión (ubicación), % de acciones críticas con `confirm` presente
  en forense (objetivo 100 %), cero PII cruda en forense (solo
  hash/longitud), latencia p95 < 500 ms (foto < 2 s).

### Fase N2 — P2, Shizuku-only (diseño ahora, código en Fase 6+)

`settings_put` (Secure/Global), `grant_permission` (ya en protocolo),
`shell`-backed (`dumpsys meminfo`, `settings`, `appops`), `get_cpu`
fino. Todo bajo régimen shell: scope `shell`/`admin` + grant activo +
audit + denylist. **El dispatcher sigue devolviendo
`METHOD_NOT_ALLOWED` hasta Fase 6** (AGENTS.md §2.8); N2 no adelanta
código, solo deja el contrato listo.

- **Mide (cuando Fase 6 abra la puerta):** tiempo de grant (s hasta
  aprobación/denegación/timeout 60 s), % de denylist interceptada,
  tasa `SHELL_DENIED` honesto, latencia shell p95, integridad del ring
  500 (sin pérdida bajo 5 req/s shell).

### Imposible non-root (no prometer, no implementar)

- Escritura `Secure`/`Global` directa sin Shizuku (`WRITE_SECURE_SETTINGS`).
- `MEDIA_CONTENT_CONTROL` directo sin NL.
- Lectura de clipboard en segundo plano en Android 10+ (vías honestas:
  host `dumpsys` o foreground/IME).
- Cámara background silenciosa (API 29+: FGS + indicador obligatorios).
- "Envío directo" headless a apps de terceros (sin API pública; va por
  intent pre-rellenado + carril Jev con `confirm`).
- Identificadores persistentes (IMEI/serial) sin privilegios de operador;
  lecturas globales de `Secure` críticas sin shell.

Cada imposible lleva su error honesto en el contrato (`*_UNAVAILABLE` /
`METHOD_NOT_ALLOWED` + hint accionable), nunca un stub silencioso ni
coordenadas inventadas.

## 15. Matriz resumen

| Tool | API | Permiso / obtención | Scope | Confirm | Fase |
|---|---|---|---|---|---|
| `get_battery` | `BatteryManager` | ninguno | `read` | no | **P0** |
| `get_memory` / `get_storage` básico | `ActivityManager` / `StatFs` | ninguno | `read` | no | **P0** |
| `get_device_info` | `Build`, `DisplayMetrics` | ninguno (sin IDs persistentes) | `read` | no | **P0** |
| `settings_get` (System) | `Settings.System` | ninguno | `read` | no | **P0** |
| `send_intent` / `open_url` (apertura) | `startActivity` / `am start` Shizuku | ninguno nuevo | `ui` sin grant | solo si envía/borra/paga | **P0** |
| `set_clipboard` | `ClipboardManager.set` | ninguno | `ui` sin grant | no (existe) | **P0 hecho** |
| `get_app_usage` | `UsageStatsManager` | `PACKAGE_USAGE_STATS`, Ajustes usuario | `read` | solo eventos crudos | **P1** |
| `list_contacts` | `ContactsContract` | `READ_CONTACTS` runtime | `read` | no (proyección mínima) | **P1** |
| `list_events` | `CalendarContract` | `READ_CALENDAR` runtime | `read` | no (ventana acotada) | **P1** |
| `list_notifications` / `media_state` | `NotificationListenerService` | habilitación usuario en Ajustes | `read` | solo `extras` crudos | **P1** |
| `get_location` (fg) | `LocationManager` | `COARSE`/`FINE` runtime | `read` | cruda en forense | **P1** |
| `media_control` / `reply` / `create_event` / `add_contact` | `MediaController` / `RemoteInput` / providers | grants anteriores | `ui` | **sí** | **P1 tardía** |
| `take_photo` | `Camera2` + FGS `camera` | `CAMERA` + FGS + notificación | `ui` | **sí, siempre** | **P1-restringida** |
| `settings_put` Secure/Global, `dumpsys` fino | `settings` / `dumpsys` vía Shizuku | Shizuku + grant Fase 6 | `shell`/`admin` | **sí** | **P2 (Fase 6+)** |
| Secure directo, `MEDIA_CONTENT_CONTROL`, clipboard-bg, cámara silenciosa, direct-send headless | — | firma/sistema o bloqueado por privacidad | — | — | **IMPOSIBLE** |
