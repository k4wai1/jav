"""Tools native/: carril APIs directas (docs/specs/native-apis.md).

Cada funcion = una primitiva del catalogo viable N0+N1. Sin Jev, sin UI,
sin `su`: Jam responde por llamada al framework Android. N2 (Shizuku/
shell on-device: Secure/Global-write, dumpsys fino) NO se implementa:
el dispatcher responde METHOD_NOT_ALLOWED honesto hasta Fase 6 y aqui
se propaga tal cual.

Envolvente {ok, verified, evidence, hint} en todas. `evidence` siempre
lleva `latency_ms` (medida local, costo 0: sin LLM). PII (contactos,
ubicacion, calendario, notificaciones): `evidence` porta lo minimo para
el director y `evidence["forense"]` solo conteos/hashes, nunca crudo.

Docstrings de 5 secciones (Descripcion / Parametros / Retorno /
Permisos-Grants / Errores-gotchas), en espanol como el resto del repo.
"""
from __future__ import annotations

import hashlib
import time

from ..socket_client import JamError
from . import _base as B


def _forense_summary(canonical: str, count: int) -> dict:
    return {"count": count,
            "sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest()}


async def _jam_call(method: str, params: dict | None = None, _call=None) -> dict:
    """Llama a Jam y envuelve. `_call`: hook tests `async (m, p) -> result`."""
    t0 = time.perf_counter()
    try:
        if _call is not None:
            result = await _call(method, params or {})
        else:
            jam = await B.jam_client()
            try:
                result = await jam.call(method, params or {})
            finally:
                await jam.__aexit__()
        ms = round((time.perf_counter() - t0) * 1000, 1)
        ev = dict(result or {})
        ev["latency_ms"] = ms
        verified = True if ev.get("planned") is not True else False
        return B.ok(verified, ev)
    except JamError as e:
        ms = round((time.perf_counter() - t0) * 1000, 1)
        d = B.jam_fail(e)
        d["evidence"]["latency_ms"] = ms
        return d


# --- N0: sin permisos nuevos -------------------------------------------------

async def get_battery(_call=None) -> dict:
    """Estado de la bateria.

    Descripcion: Nivel, carga, enchufe, temperatura y ahorro de energia.
    Sin PII; no pide permiso nuevo.
    Parametros: Ninguno.
    Retorno: {ok, verified, evidence, hint}; evidence =
      {level_pct, capacity_pct, charging, plugged, temp_c?, saver,
       latency_ms}. `level_pct`/`capacity_pct` en %, `temp_c` en grados C.
    Permisos/Grants: scope read; sin permisos nuevos.
    Errores/gotchas: valores enteros -1 si el sistema no reporta; `temp_c`
      es opcional (ausente si no hay termometro). `ok:false` = conexion
      con Jam caida.
    """
    return await _jam_call("get_battery", {}, _call)


async def get_memory(_call=None) -> dict:
    """Memoria RAM del equipo.

    Descripcion: RAM disponible, total, umbral de baja memoria y flag.
    Sin PII.
    Parametros: Ninguno.
    Retorno: {ok, verified, evidence, hint}; evidence =
      {avail_bytes, total_bytes, threshold_bytes, low_memory, latency_ms}.
      Todos los tamanos en BYTES.
    Permisos/Grants: scope read; sin permisos nuevos.
    Errores/gotchas: `low_memory` puede parpadear; no confundir bytes con
      MiB (dividir entre 1048576).
    """
    return await _jam_call("get_memory", {}, _call)


async def get_storage(detail: str = "basic", _call=None) -> dict:
    """Almacenamiento interno del volumen de datos.

    Descripcion: Total/libre/disponible del volumen interno (`StatFs`).
    `fine` (desglose por app) es N2 y no se implementa aun.
    Parametros: detail (str): "basic" (default) o "fine". `fine` = N2.
    Retorno: {ok, verified, evidence, hint}; evidence =
      {path, total_bytes, free_bytes, avail_bytes, latency_ms}. BYTES.
    Permisos/Grants: scope read; `fine` requeriria shell/Shizuku (Fase 6+).
    Errores/gotchas: detail="fine" -> METHOD_NOT_ALLOWED honesto (N2).
      `free_bytes` != `avail_bytes` (reservado al sistema).
    """
    return await _jam_call("get_storage", {"detail": detail}, _call)


async def get_cpu(detail: str = "basic", _call=None) -> dict:
    """Numero de procesadores y uso de CPU instantaneo.

    Descripcion: Cuenta nucleos y mide uso por delta de `/proc/stat`
      (ventana ~120 ms). `fine` (per-proceso) es N2.
    Parametros: detail (str): "basic" (default) o "fine". `fine` = N2.
    Retorno: {ok, verified, evidence, hint}; evidence =
      {processors, usage_pct, latency_ms}. `processors` = numero de
      nucleos (siempre valido); `usage_pct` en % 0..100.
    Permisos/Grants: scope read; sin permisos nuevos.
    Errores/gotchas: `usage_pct = -1` es DELIBERADO cuando SELinux
      bloquea `/proc/stat` (no es error, no inventar); `cores`
      (`processors`) siempre es valido. detail="fine" ->
      METHOD_NOT_ALLOWED (N2).
    """
    return await _jam_call("get_cpu", {"detail": detail}, _call)


async def get_device_info(_call=None) -> dict:
    """Hardware y configuracion del equipo, sin identificadores persistentes.

    Descripcion: Fabricante/modelo/device/ABI/pantalla/features/locale/
      zona horaria. Nunca IMEI, MAC, serial ni ANDROID_ID.
    Parametros: Ninguno.
    Retorno: {ok, verified, evidence, hint}; evidence =
      {manufacturer, model, device, sdk_int, abis[], screen_w, screen_h,
       density_dpi, locale, timezone, features{}, latency_ms}.
      Dimensiones en PXLOGICOS y `density_dpi` en dpi.
    Permisos/Grants: scope read; sin permisos nuevos.
    Errores/gotchas: por privacidad no incluye IDs persistentes; no usar
      `device` como identificador unico (es el nombre de placa).
    """
    return await _jam_call("get_device_info", {}, _call)


async def settings_get(namespace: str = "system", key: str = "", _call=None) -> dict:
    """Lee un ajuste System/Secure/Global por clave.

    Descripcion: Lectura puntual de `Settings.<namespace>.getString`.
    Parametros: namespace (str): "system"|"secure"|"global" (default
      "system"); key (str): clave a leer (obligatoria).
    Retorno: {ok, verified, evidence, hint}; evidence =
      {namespace, key, found, value?, latency_ms}. `value` solo si
      `found` es true.
    Permisos/Grants: scope read; sin confirm. Claves sensibles pueden
      estar denegadas por el sistema.
    Errores/gotchas: FORBIDDEN si la clave esta restringida;
      VALIDATION_ERROR con namespace invalido o key vacia. No expone
      valores de Secure criticos.
    """
    return await _jam_call("settings_get", {"namespace": namespace, "key": key}, _call)


async def settings_put(namespace: str = "system", key: str = "",
                        value: str = "", confirm: bool = False, _call=None) -> dict:
    """Escribe un ajuste (System) con confirmacion explicita.

    Descripcion: Escritura de `Settings.System` (P1, permiso especial
      WRITE_SETTINGS). Secure/Global requieren shell/Shizuku y no se
      implementan aun (N2).
    Parametros: namespace (str): "system"|"secure"|"global" (default
      "system"); key (str); value (str): valor crudo a escribir;
      confirm (bool): obligatorio para ejecutar.
    Retorno: sin `confirm` -> {ok:true, verified:false, evidence=
      {planned:true, preview{value_sha256}, hint}}; con `confirm` ->
      {ok:true, verified:true, evidence={namespace, key, written}}.
    Permisos/Grants: System: WRITE_SETTINGS (ajuste especial, no runtime)
      + scope admin + `confirm:true`. Secure/Global: N2 (Fase 6+).
    Errores/gotchas: Secure/Global -> METHOD_NOT_ALLOWED (N2);
      WRITE_SETTINGS_DISABLED sin permiso; SETTINGS_PUT_FAILED si el
      sistema rechaza. Revertir = segundo put con el valor previo (leer
      antes con settings_get). Sin confirm -> planned+preview.
    """
    return await _jam_call("settings_put", {"namespace": namespace, "key": key,
                                            "value": value, "confirm": confirm}, _call)


async def open_url(url: str, package: str = "", _call=None) -> dict:
    """Abre una URL en su app; solo apertura, el envio va por el carril Jev.

    Descripcion: Lanza ACTION_VIEW sobre `url`. Sin `package`, el sistema
      resuelve y con >1 handler muestra chooser (ResolverActivity); con
      `package` se fija el componente del handler (1 salto, sin chooser).
    Parametros: url (str): esquema `://…` valido (obligatoria;
      https/tel/mailto/sms/geo); package (str): paquete `a.b.c` del
      handler a forzar; "" (default) = resolver del sistema.
    Retorno: {ok, verified, evidence, hint}; evidence =
      {url, via, package?, latency_ms}. `via` =
      "startActivity" | "startActivity-package" | "shizuku-am".
    Permisos/Grants: scope ui, sin grant; ninguno nuevo.
    Errores/gotchas: con package="" y >1 handler -> chooser (el
      ResolverActivity pide elegir); con `package` no hay chooser.
      Paquete no instalado -> PACKAGE_NOT_FOUND; instalado pero sin
      handler para el URI -> INTENT_UNRESOLVED; esquema invalido ->
      VALIDATION_ERROR. No envia/comunica (eso es send_intent + Jev).
    """
    return await _jam_call("open_url", {"url": url, "package": package}, _call)


async def send_intent(action: str, uri: str = "", package: str = "", mime: str = "",
                      confirm: bool = False, extras: dict | None = None, _call=None) -> dict:
    """Lanza un intent (apertura/pre-relleno); el envio real ocurre en la UI destino.

    Descripcion: Construye y lanza un Intent. No hay envio headless real
      en API publica: como maximo abre el editor pre-rellenado; el envio
      lo hace la app destino (o el carril Jev con compuertas).
    Parametros: action (str): p.ej. "android.intent.action.VIEW"|SEND|
      CALL|DIAL; uri (str): forma esquema://…; package (str): paquete
      `a.b.c` a forzar; mime (str): tipo MIME; confirm (bool);
      extras (dict[str,str]): extras --es.
    Retorno: accion critica sin `confirm` -> {ok:true, verified:false,
      evidence={planned:true, preview, hint}}; con exito ->
      {ok:true, verified:true, evidence={action, via}}.
    Permisos/Grants: scope ui sin grant; acciones criticas
      (SEND/SENDTO/SEND_MULTIPLE/CALL, o VIEW con sms/tel/mailto) exigen
      `confirm:true`.
    Errores/gotchas: SEND/CALL sin confirm -> planned sin ejecutar (nunca
      se envia solo); no finge un envio nativo; package invalido ->
      VALIDATION_ERROR; fallback Shizuku `am start` -> via "shizuku-am".
    """
    return await _jam_call("send_intent", {"action": action, "uri": uri,
                                          "package": package, "mime": mime,
                                          "confirm": confirm,
                                          "extras": extras or {}}, _call)


async def get_clipboard_device(_call=None) -> dict:
    """Lee el clipboard del dispositivo via Jam en foreground (nunca crudo).

    Descripcion: Caso narrow de lectura en primer plano. En segundo plano
      Android 10+ la bloquea y se reporta honesto. Para el host usar el
      atajo `get_clipboard` (dumpsys).
    Parametros: Ninguno.
    Retorno: {ok, verified, evidence, hint}; evidence =
      {len, sha256, via, forense{via, len, sha256}, latency_ms}.
      El texto NUNCA viaja: solo longitud y hash.
    Permisos/Grants: scope read sensible; sin permiso nuevo.
    Errores/gotchas: background Android 10+ o vacio -> CLIPBOARD_EMPTY
      honesto; no sondea ni inventa contenido.
    """
    d = await _jam_call("get_clipboard", {}, _call)
    if d.get("ok"):
        ev = d["evidence"]
        ev["forense"] = {"via": "jam-foreground", "len": ev.get("len", 0),
                         "sha256": ev.get("sha256", "")}
    return d


# --- N1: con grant del usuario -----------------------------------------------

async def get_app_usage(hours: int = 24, window: str | None = None, _call=None) -> dict:
    """Tiempo en foreground agregado por paquete (top 50).

    Descripcion: Suma `totalTimeInForeground` por paquete en la ventana
      elegida. Solo agregados, sin eventos crudos.
    Parametros: hours (int): 1..24 sin `window` (default 24), 1..168 con
      `window="raw"`; window (str|None): "today" (medianoche local),
      "week" (7 dias), "raw" (hours 1..168) o None (comportamiento previo).
    Retorno: {ok, verified, evidence, hint}; evidence =
      {window, begin, now, window_h, count,
       apps[{package, foreground_ms, last_used}], latency_ms}.
      `foreground_ms` en MILISEGUNDOS (dividir entre 60000 para minutos);
      `begin`/`now`/`last_used` en ms Unix.
    Permisos/Grants: acceso especial "Acceso a datos de uso"
      (PACKAGE_USAGE_STATS) habilitado por el usuario.
    Errores/gotchas: sin grant -> USAGE_ACCESS_DISABLED; apps de fondo
      que acumulan tiempo aunque no se usen en primer plano (p.ej. Termux
      en segundo plano) inflan `foreground_ms`; `window_h` es la ventana
      efectiva en horas.
    """
    return await _jam_call("get_app_usage", {"hours": hours, "window": window}, _call)


async def list_contacts(query: str = "", limit: int = 50, offset: int = 0,
                        with_phone: bool = False, _call=None) -> dict:
    """Lista contactos con proyeccion minima y paginacion.

    Descripcion: Pagina contactos (nombre; telefono solo si se pide).
      PII sensible: en forense solo conteos/hashes.
    Parametros: query (str): filtro por subcadena de nombre; limit (int):
      1..100 (default 50); offset (int): >=0; with_phone (bool): incluye
      numero telefonico.
    Retorno: {ok, verified, evidence, hint}; evidence =
      {returned, offset, contacts[{id, display_name, phone?}],
       forense{count, sha256}, latency_ms}.
    Permisos/Grants: READ_CONTACTS (runtime).
    Errores/gotchas: sin permiso -> CONTACTS_PERMISSION_DENIED; respuesta
      paginada sin `total`; el forense MCP solo guarda count+sha256,
      nunca el nombre/telefono crudo.
    """
    d = await _jam_call("list_contacts", {"query": query, "limit": limit,
                                         "offset": offset, "with_phone": with_phone}, _call)
    if d.get("ok"):
        ev = d["evidence"]
        cs = ev.get("contacts", []) or []
        canon = "|".join(f"{c.get('id')}" for c in cs)
        ev["forense"] = _forense_summary(canon, len(cs))
    return d


async def add_contact(display_name: str, phone: str = "", email: str = "",
                      confirm: bool = False, _call=None) -> dict:
    """Alta de contacto (accion critica).

    Descripcion: Inserta un contacto via ContactsContract. Requiere
      confirmacion explicita.
    Parametros: display_name (str): nombre (obligatorio); phone (str):
      telefono opcional; email (str): email opcional; confirm (bool).
    Retorno: sin `confirm` -> {ok:true, verified:false, evidence=
      {planned:true, preview, hint}}; con `confirm` ->
      {ok:true, verified:true, evidence={added, ops, uri}}.
    Permisos/Grants: WRITE_CONTACTS (runtime) + `confirm:true`.
    Errores/gotchas: sin confirm -> planned; sin permiso ->
      CONTACTS_PERMISSION_DENIED; VALIDATION_ERROR si display_name vacio.
      El preview solo lleva longitudes/hashes (sin PII cruda).
    """
    return await _jam_call("add_contact", {"display_name": display_name, "phone": phone,
                                          "email": email, "confirm": confirm}, _call)


async def list_events(time_min: int = 0, time_max: int = 0, calendar_id: int = 0,
                      include_location: bool = False, _call=None) -> dict:
    """Eventos de calendario en una ventana (max 7 dias).

    Descripcion: Consulta instancias de calendario. PII sensible: en
      forense solo conteos/hashes.
    Parametros: time_min (int): inicio en MILISEGUNDOS Unix (0 = ahora);
      time_max (int): fin en MILISEGUNDOS Unix (0 = time_min + 7 dias);
      calendar_id (int): 0 = todos; include_location (bool).
    Retorno: {ok, verified, evidence, hint}; evidence =
      {time_min, time_max, returned,
       events[{event_id, title, begin, end, calendar_id, location?}],
       forense{count, sha256}, latency_ms}. `begin`/`end` en MILISEGUNDOS
      Unix.
    Permisos/Grants: READ_CALENDAR (runtime).
    Errores/gotchas: `time_min`/`time_max`/`begin`/`end` en MILISEGUNDOS
      Unix (no segundos); ventana mayor a 7 dias -> VALIDATION_ERROR;
      sin permiso -> CALENDAR_PERMISSION_DENIED; sin `total`; PII solo
      conteos/hash en forense. `end` puede pasar de `time_max` (evento
      que continua).
    """
    d = await _jam_call("list_events", {"time_min": time_min, "time_max": time_max,
                                        "calendar_id": calendar_id,
                                        "include_location": include_location}, _call)
    if d.get("ok"):
        ev = d["evidence"]
        es = ev.get("events", []) or []
        canon = "|".join(f"{e.get('event_id')}:{e.get('begin')}" for e in es)
        ev["forense"] = _forense_summary(canon, len(es))
    return d


async def create_event(title: str, start_ms: int, end_ms: int, calendar_id: int = 0,
                      description: str = "", confirm: bool = False, _call=None) -> dict:
    """Crea un evento de calendario (accion critica).

    Descripcion: Inserta un evento via CalendarContract. Requiere
      confirmacion explicita.
    Parametros: title (str); start_ms (int): inicio en MILISEGUNDOS Unix;
      end_ms (int): fin en MILISEGUNDOS Unix (> start_ms); calendar_id
      (int): 0 = primer calendario visible; description (str) opcional;
      confirm (bool).
    Retorno: sin `confirm` -> {ok:true, verified:false, evidence=
      {planned:true, preview{title_sha256, title_len, start, end}, hint}};
      con `confirm` -> {ok:true, verified:true, evidence=
      {created, event_id}}.
    Permisos/Grants: WRITE_CALENDAR (runtime) + `confirm:true`.
    Errores/gotchas: `start_ms`/`end_ms` en MILISEGUNDOS Unix; sin
      confirm -> planned; sin permiso -> CALENDAR_PERMISSION_DENIED; sin
      calendario visible -> CALENDAR_UNAVAILABLE; title/vals invalidos ->
      VALIDATION_ERROR. El preview hashea el titulo (sin texto crudo).
    """
    return await _jam_call("create_event", {"calendar_id": calendar_id, "title": title,
                                           "start_ms": start_ms, "end_ms": end_ms,
                                           "description": description,
                                           "confirm": confirm}, _call)


async def list_notifications(_call=None) -> dict:
    """Notificaciones activas con proyeccion minima.

    Descripcion: Lista hasta 50 notificaciones del NotificationListener,
      con titulo/texto truncados a 200 chars. PII: forense solo
      conteos/hashes.
    Parametros: Ninguno.
    Retorno: {ok, verified, evidence, hint}; evidence =
      {count, notifications[{key, package, title<=200, text<=200,
       has_remote_input, posted_at}], forense{count, sha256}, latency_ms}.
      `posted_at` en MILISEGUNDOS Unix.
    Permisos/Grants: servicio NotificationListener habilitado (Acceso a
      notificaciones).
    Errores/gotchas: sin listener -> NOTIFICATION_LISTENER_DISABLED; en
      algunas ROM/Ajustes el servicio no enlaza aunque se active (p.ej.
      el 5002E dice "no disponible en este dispositivo"): error honesto,
      no se inventan notificaciones; sin `extras` crudos.
    """
    d = await _jam_call("list_notifications", {}, _call)
    if d.get("ok"):
        ev = d["evidence"]
        ns = ev.get("notifications", []) or []
        canon = "|".join(f"{n.get('key')}" for n in ns)
        ev["forense"] = _forense_summary(canon, len(ns))
    return d


async def reply_notification(key: str, text: str, confirm: bool = False, _call=None) -> dict:
    """Responde una notificacion via RemoteInput (accion critica).

    Descripcion: Envia una respuesta a la notificacion identificada por
      `key`. Requiere confirmacion explicita.
    Parametros: key (str): clave de la notificacion (de
      list_notifications); text (str): cuerpo de la respuesta;
      confirm (bool).
    Retorno: sin `confirm` -> {ok:true, verified:false, evidence=
      {planned:true, preview{key, text_len, text_sha256}, hint}}; con
      `confirm` -> {ok:true, verified:true, evidence=
      {replied, key, via}}.
    Permisos/Grants: listener habilitado + `confirm:true`.
    Errores/gotchas: sin confirm -> planned; listener ausente ->
      NOTIFICATION_LISTENER_DISABLED; notificacion ya no activa ->
      NOTIFICATION_GONE; sin RemoteInput -> NO_REMOTE_INPUT; cancelado o
      fallo -> REPLY_FAILED. NL puede no existir en algunas ROM.
    """
    return await _jam_call("reply_notification", {"key": key, "text": text,
                                                 "confirm": confirm}, _call)


async def media_state(_call=None) -> dict:
    """Sesiones multimedia activas.

    Descripcion: Lista hasta 10 sesiones con paquete/titulo/artista/
      estado. Monta (depende de) el grant del NotificationListener.
    Parametros: Ninguno.
    Retorno: {ok, verified, evidence, hint}; evidence =
      {count, sessions[{package, title, artist, state}], latency_ms}.
      `state` = playing|paused|stopped|buffering|unknown.
    Permisos/Grants: NotificationListener habilitado.
    Errores/gotchas: sin listener/permiso -> MEDIA_SESSIONS_UNAVAILABLE;
      algunas ROM no exponen el listener; sin PII de mas (solo metadata).
    """
    return await _jam_call("media_state", {}, _call)


async def media_control(action: str, package: str = "",
                        confirm: bool = False, _call=None) -> dict:
    """Controla el transporte multimedia de una sesion.

    Descripcion: play/pause/next/prev son reversibles; `stop` es
      destructivo y exige confirmacion.
    Parametros: action (str): "play"|"pause"|"next"|"prev"|"stop";
      package (str): "" = primera sesion; confirm (bool).
    Retorno: `stop` sin confirm -> {ok:true, verified:false, evidence=
      {planned:true, preview}}; con exito -> {ok:true, verified:true,
      evidence={action, package, via}}.
    Permisos/Grants: listener habilitado; `stop` exige `confirm:true`.
    Errores/gotchas: sin sesiones -> MEDIA_SESSIONS_UNAVAILABLE; paquete
      sin sesion -> MEDIA_SESSION_GONE; fallo -> MEDIA_CONTROL_FAILED;
      action invalida -> VALIDATION_ERROR. play/pause/next/prev no
      requieren confirm (reversibles).
    """
    return await _jam_call("media_control", {"action": action, "package": package,
                                            "confirm": confirm}, _call)


async def get_location(timeout_ms: int = 8000, max_age_s: int = 300, _call=None) -> dict:
    """Ubicacion en foreground (cache fresca primero; si no, fix).

    Descripcion: Devuelve la ultima ubicacion conocida si es suficientemente
      fresca; si no, espera un fix hasta el timeout. Nunca inventa. PII:
      forense solo hash.
    Parametros: timeout_ms (int): espera maxima del fix en MILISEGUNDOS,
      <=30000 (default 8000); max_age_s (int): antiguedad maxima aceptada
      de cache en SEGUNDOS, <=3600 (default 300).
    Retorno: {ok, verified, evidence, hint}; evidence =
      {lat, lon, accuracy_m, provider, age_s,
       via: "last_known"|"fresh", forense{via, sha256}, latency_ms}.
      `accuracy_m` en metros, `age_s` en segundos.
    Permisos/Grants: ACCESS_FINE_LOCATION o ACCESS_COARSE_LOCATION
      (runtime).
    Errores/gotchas: `timeout_ms` en MILISEGUNDOS y `max_age_s` en
      SEGUNDOS (no mezclar); sin permiso -> LOCATION_PERMISSION_DENIED;
      proveedores GPS/red apagados -> LOCATION_UNAVAILABLE; sin fix en el
      timeout -> LOCATION_TIMEOUT (jamas coordenadas inventadas).
    """
    d = await _jam_call("get_location", {"timeout_ms": timeout_ms,
                                        "max_age_s": max_age_s}, _call)
    if d.get("ok"):
        ev = d["evidence"]
        canon = f"{ev.get('lat')},{ev.get('lon')},{ev.get('accuracy_m')}"
        ev["forense"] = {"via": ev.get("via", ""),
                         "sha256": hashlib.sha256(canon.encode()).hexdigest()}
    return d


async def take_photo(confirm: bool = False, camera: str = "back", _call=None) -> dict:
    """Foto headless restringida (nunca silenciosa).

    Descripcion: Captura via Camera2 bajo foreground service visible con
      indicador. Exige confirmacion SIEMPRE; jamas es silenciosa.
    Parametros: confirm (bool): obligatorio; camera (str): "back"|"front".
    Retorno: sin `confirm` -> {ok:true, verified:false, evidence=
      {planned:true, preview, hint}}; con `confirm` -> {ok:true,
      verified:true, evidence={img_base64, w, h, via}} (<4 MiB; `w`/`h`
      en PX).
    Permisos/Grants: CAMERA (runtime) + FGS `camera` + `confirm:true`
      siempre.
    Errores/gotchas: sin confirm -> planned (siempre); sin permiso ->
      CAMERA_DENIED; sin camara -> CAMERA_UNAVAILABLE; fallo ->
      CAMERA_FAILED; con pantalla bloqueada o en algunas ROM puede
      degradar; alternativa: delegar a la app de camara por send_intent.
    """
    return await _jam_call("take_photo", {"confirm": confirm, "camera": camera}, _call)


__all__ = [
    "get_battery", "get_memory", "get_storage", "get_cpu", "get_device_info",
    "settings_get", "settings_put", "open_url", "send_intent", "get_clipboard_device",
    "get_app_usage", "list_contacts", "add_contact", "list_events", "create_event",
    "list_notifications", "reply_notification", "media_state", "media_control",
    "get_location", "take_photo",
]
