"""Jam MCP server (stdio). Tools → Jam por WS. Agente genérico run_goal en `loop.py` (contrato docs/specs/generic-dual-tier.md).

Docstrings de 5 secciones (Descripcion / Parametros / Retorno /
Permisos-Grants / Errores-gotchas). Se inyectan como descripcion de la
tool en el LLM: precisos y en espanol, como el resto del repo.
"""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from .tools import app as app_tools
from .tools import device as device_tools
from .tools import native as native_tools
from .tools import ui as ui_tools

mcp = FastMCP("jam")


@mcp.tool()
async def device_status() -> dict:
    """Estado de la conexion con Jam.

    Descripcion: Scopes del token, version de la app y app/activity en
      foreground.
    Parametros: Ninguno.
    Retorno: {ok, verified, evidence, hint}; evidence =
      {scopes[], app_version, foreground{package, activity}}.
    Permisos/Grants: conexion Jam + accesibilidad para foreground;
      scope read.
    Errores/gotchas: ACCESSIBILITY_DISABLED si la accesibilidad no esta
      conectada (el foreground puede venir vacio); conexion caida ->
      ok:false.
    """
    return await device_tools.device_status()


@mcp.tool()
async def list_packages(filter: str = "") -> dict:
    """Lista paquetes instalados (host `adb shell pm list packages`).

    Descripcion: Enumera paquetes visibles en el host adb; no pasa por
      el WS de Jam.
    Parametros: filter (str): subcadena case-insensitive; "" = todos.
    Retorno: {ok, verified, evidence, hint}; evidence =
      {count, packages[]}.
    Permisos/Grants: adb del host; sin scope Jam.
    Errores/gotchas: host sin adb o dispositivo desconectado -> fallo;
      por la visibilidad de paquetes (`<queries>`) la lista puede ser
      parcial.
    """
    return await device_tools.list_packages(filter)


@mcp.tool()
async def get_foreground() -> dict:
    """Paquete + activity en foreground.

    Descripcion: Lee la ventana activa por accesibilidad.
    Parametros: Ninguno.
    Retorno: {ok, verified, evidence, hint}; evidence =
      {package, activity}.
    Permisos/Grants: accesibilidad (scope read).
    Errores/gotchas: ACCESSIBILITY_DISABLED; sin ventana activa
      `package` puede ser "" (transitorio).
    """
    return await device_tools.get_foreground()


@mcp.tool()
async def open_app(package: str) -> dict:
    """Abre una app (Shizuku) y verifica que quedo en foreground.

    Descripcion: Lanza el LAUNCHER de `package` via Shizuku (`am start`)
      y confirma el foreground.
    Parametros: package (str): paquete `a.b.c` (obligatorio).
    Retorno: {ok, verified, evidence, hint}; evidence =
      {package, activity, foreground}.
    Permisos/Grants: scope ui; Shizuku disponible (sin grant de shell);
      nunca `su`.
    Errores/gotchas: SHIZUKU_UNAVAILABLE sin Shizuku; VALIDATION_ERROR
      con forma invalida; VERIFY_FAILED si no llego a foreground;
      fallback `monkey` cuando no hay activity LAUNCHER.
    """
    return await app_tools.open_app(package)


@mcp.tool()
async def close_app(package: str) -> dict:
    """Cierra una app (force-stop) y verifica la salida.

    Descripcion: Fuerza el cierre con Shizuku y confirma que ya no esta
      en foreground.
    Parametros: package (str): paquete `a.b.c` (obligatorio).
    Retorno: {ok, verified, evidence, hint}; evidence =
      {package, foreground}.
    Permisos/Grants: scope shell sin grant (bajo riesgo, PROTOCOL §8) +
      Shizuku.
    Errores/gotchas: SHIZUKU_UNAVAILABLE; VERIFY_FAILED si sigue en
      foreground.
    """
    return await app_tools.close_app(package)


@mcp.tool()
async def read_screen() -> dict:
    """Pantalla normalizada: candidatos compactos + snapshot_id.

    Descripcion: Dumpea el arbol de accesibilidad y lo normaliza a
      candidatos accionables con ids; es la base del bucle de decision.
    Parametros: Ninguno.
    Retorno: {ok, verified, evidence, hint}; evidence =
      {package, activity, snapshot_id, raw_count, screen_height,
       screen_width, focused_field, first_result, candidates[], render}.
      `snapshot_id` monotono; dimensiones en PX logicos.
    Permisos/Grants: accesibilidad (scope read).
    Errores/gotchas: ACCESSIBILITY_DISABLED; el `snapshot_id` es
      obligatorio para tap_node/type_text y falla con STALE_SNAPSHOT si
      la UI cambio. Filtra nodos de decoracion del sistema.
    """
    return await ui_tools.read_screen()


@mcp.tool()
async def tap_text(text: str) -> dict:
    """Atajo del Director: toca el primer nodo que contiene el texto.

    Descripcion: Conveniencia para el Director (hace un dump interno).
      NO es una accion del enum de Jev; el enum usa TAP sobre node_id
      via tap_node con snapshot fresco.
    Parametros: text (str): subcadena a matchear.
    Retorno: {ok, verified, evidence, hint}; evidence =
      {node_id, via}.
    Permisos/Grants: accesibilidad (scope ui).
    Errores/gotchas: SELECTOR_NOT_FOUND si no matchea; preferir
      tap_node(node_id, snapshot_id) si ya hay snapshot fresco (evita el
      dump interno).
    """
    return await ui_tools.tap_text(text)


@mcp.tool()
async def tap_node(node_id: str, snapshot_id: int) -> dict:
    """Toca por id + snapshot (rapido, sin dump interno).

    Descripcion: Accion TAP del enum Jev: toca un nodo concreto del
      snapshot. Si el nodo es clickable usa ACTION_CLICK; si no,
      dispatchGesture al centro de bounds.
    Parametros: node_id (str): id del candidato; snapshot_id (int): el
      devuelto por read_screen/wait_for_text.
    Retorno: {ok, verified, evidence, hint}; evidence =
      {node_id, via}.
    Permisos/Grants: accesibilidad (scope ui).
    Errores/gotchas: STALE_SNAPSHOT si la UI cambio (re-lee y usa el
      nuevo id); SELECTOR_NOT_FOUND si el id no existe. La accion no
      devuelve snapshot: verificar el efecto con read_screen.
    """
    return await ui_tools.tap_node(node_id, snapshot_id)


@mcp.tool()
async def type_text(node_id: str, snapshot_id: int, text: str) -> dict:
    """Escribe en un campo ya enfocado (semantica REPLACE).

    Descripcion: Accion TYPE del enum Jev: escribe con ACTION_SET_TEXT
      (reemplaza el contenido, sin teclado simulado ni append).
    Parametros: node_id (str); snapshot_id (int); text (str): contenido
      final del campo.
    Retorno: {ok, verified, evidence, hint}; evidence =
      {chars, snapshot_id}.
    Permisos/Grants: accesibilidad (scope ui).
    Errores/gotchas: NOT_FOCUSED si el nodo no esta enfocado (haz tap
      antes; no hay taps implicitos); STALE_SNAPSHOT. No devuelve
      snapshot: verifica con read_screen.
    """
    return await ui_tools.type_text(node_id, snapshot_id, text)


@mcp.tool()
async def scroll(direction: str = "down", node_id: str | None = None) -> dict:
    """Scroll en una direccion, opcionalmente sobre un nodo.

    Descripcion: Accion SCROLL_UP/DOWN del enum Jev; opcionalmente
      limitada a un nodo scrollable.
    Parametros: direction (str): "up"|"down"|"left"|"right" (default
      "down"); node_id (str|null): nodo scrollable opcional.
    Retorno: {ok, verified, evidence, hint}; evidence =
      {direction}.
    Permisos/Grants: accesibilidad (scope ui).
    Errores/gotchas: VALIDATION_ERROR con direccion invalida; no
      devuelve snapshot: verifica con read_screen.
    """
    return await ui_tools.scroll(direction, node_id)


@mcp.tool()
async def press_back() -> dict:
    """Boton atras global.

    Descripcion: Accion BACK del enum Jev.
    Parametros: Ninguno.
    Retorno: {ok, verified, evidence, hint}; evidence = {action}.
    Permisos/Grants: accesibilidad (scope ui).
    Errores/gotchas: ACCESSIBILITY_DISABLED; verifica con read_screen.
    """
    return await ui_tools.press_back()


@mcp.tool()
async def press_home() -> dict:
    """Atajo del Director: boton home global.

    Descripcion: Conveniencia para el Director. NO es una accion del
      enum de Jev.
    Parametros: Ninguno.
    Retorno: {ok, verified, evidence, hint}; evidence = {action}.
    Permisos/Grants: accesibilidad (scope ui).
    Errores/gotchas: ACCESSIBILITY_DISABLED.
    """
    return await ui_tools.press_home()


@mcp.tool()
async def wait_for_text(text: str, timeout_ms: int = 5000) -> dict:
    """Atajo del Director: espera a que aparezca un texto.

    Descripcion: Conveniencia para el Director (no es accion del enum
      de Jev). Devuelve node_id + snapshot usable.
    Parametros: text (str): subcadena a esperar; timeout_ms (int):
      MILISEGUNDOS de espera (default 5000).
    Retorno: {ok, verified, evidence, hint}; evidence =
      {node_id, snapshot_id}.
    Permisos/Grants: accesibilidad (scope read).
    Errores/gotchas: TIMEOUT si no aparece; el snapshot_id sirve directo
      en tap_node si no hubo mas cambios.
    """
    return await ui_tools.wait_for_text(text, timeout_ms)


@mcp.tool()
async def screenshot(fmt: str = "png", quality: int = 80) -> dict:
    """Atajo del Director: captura la pantalla.

    Descripcion: Conveniencia para el Director via takeScreenshot (API
      30+) o fallback `screencap` con Shizuku (API 29). NO es una accion
      del enum de Jev.
    Parametros: fmt (str): "png"|"webp" (default "png"); quality (int):
      calidad 0..100, solo aplica a webp (default 80).
    Retorno: {ok, verified, evidence, hint}; evidence =
      {w, h, via, img_base64}; `w`/`h` en PX.
    Permisos/Grants: accesibilidad/Shizuku segun la via (scope read).
    Errores/gotchas: SECURE_SURFACE si la ventana tiene FLAG_SECURE;
      PAYLOAD_TOO_LARGE si excede 4 MiB (hint: WebP q80).
    """
    return await ui_tools.screenshot(fmt, quality)


# --- Carril APIs directas (native-apis): sin Jev, sin UI --------------------

@mcp.tool()
async def get_battery() -> dict:
    """Estado de la bateria.

    Descripcion: Nivel, carga, enchufe, temperatura y ahorro. Sin PII.
    Parametros: Ninguno.
    Retorno: {ok, verified, evidence, hint}; evidence =
      {level_pct, capacity_pct, charging, plugged, temp_c?, saver,
       latency_ms}. `level_pct`/`capacity_pct` en %, `temp_c` en grados C.
    Permisos/Grants: scope read; sin permisos nuevos.
    Errores/gotchas: -1 si el sistema no reporta; `temp_c` opcional.
    """
    return await native_tools.get_battery()


@mcp.tool()
async def get_memory() -> dict:
    """Memoria RAM.

    Descripcion: Disponible, total, umbral de baja memoria y flag.
    Parametros: Ninguno.
    Retorno: {ok, verified, evidence, hint}; evidence =
      {avail_bytes, total_bytes, threshold_bytes, low_memory,
       latency_ms}; BYTES.
    Permisos/Grants: scope read; sin permisos nuevos.
    Errores/gotchas: `low_memory` puede parpadear; no confundir bytes
      con MiB.
    """
    return await native_tools.get_memory()


@mcp.tool()
async def get_storage(detail: str = "basic") -> dict:
    """Almacenamiento interno del volumen de datos.

    Descripcion: Total/libre/disponible (`StatFs`). `fine` (desglose por
      app) es N2, no implementado aun.
    Parametros: detail (str): "basic" (default) o "fine".
    Retorno: {ok, verified, evidence, hint}; evidence =
      {path, total_bytes, free_bytes, avail_bytes, latency_ms}; BYTES.
    Permisos/Grants: scope read; `fine` requeriria shell/Shizuku (Fase 6+).
    Errores/gotchas: detail="fine" -> METHOD_NOT_ALLOWED (N2);
      `free_bytes` != `avail_bytes`.
    """
    return await native_tools.get_storage(detail)


@mcp.tool()
async def get_cpu(detail: str = "basic") -> dict:
    """Numero de procesadores y uso de CPU instantaneo.

    Descripcion: Cuenta nucleos y mide uso por delta de `/proc/stat`.
      `fine` (per-proceso) es N2.
    Parametros: detail (str): "basic" (default) o "fine".
    Retorno: {ok, verified, evidence, hint}; evidence =
      {processors, usage_pct, latency_ms}. `processors` = numero de
      nucleos; `usage_pct` en % 0..100.
    Permisos/Grants: scope read; sin permisos nuevos.
    Errores/gotchas: `usage_pct = -1` es deliberado si SELinux bloquea
      `/proc/stat` (no es error); `cores` (`processors`) siempre valido;
      detail="fine" -> METHOD_NOT_ALLOWED (N2).
    """
    return await native_tools.get_cpu(detail)


@mcp.tool()
async def get_device_info() -> dict:
    """Hardware y configuracion, sin identificadores persistentes.

    Descripcion: Modelo/ABI/pantalla/features/locale/zona. Nunca IMEI,
      MAC, serial ni ANDROID_ID.
    Parametros: Ninguno.
    Retorno: {ok, verified, evidence, hint}; evidence =
      {manufacturer, model, device, sdk_int, abis[], screen_w, screen_h,
       density_dpi, locale, timezone, features{}, latency_ms}; PX y dpi.
    Permisos/Grants: scope read; sin permisos nuevos.
    Errores/gotchas: no incluye IDs persistentes; `device` no es un id
      unico (es la placa).
    """
    return await native_tools.get_device_info()


@mcp.tool()
async def settings_get(namespace: str = "system", key: str = "") -> dict:
    """Lee un ajuste System/Secure/Global por clave.

    Descripcion: Lectura puntual de `Settings.<namespace>`. Sin confirm.
    Parametros: namespace (str): "system"|"secure"|"global" (default
      "system"); key (str): obligatoria.
    Retorno: {ok, verified, evidence, hint}; evidence =
      {namespace, key, found, value?, latency_ms}.
    Permisos/Grants: scope read; claves sensibles pueden estar denegadas.
    Errores/gotchas: FORBIDDEN si la clave esta restringida;
      VALIDATION_ERROR con namespace invalido o key vacia.
    """
    return await native_tools.settings_get(namespace, key)


@mcp.tool()
async def settings_put(namespace: str = "system", key: str = "",
                        value: str = "", confirm: bool = False) -> dict:
    """Escribe un ajuste (System) con confirmacion.

    Descripcion: Escritura de `Settings.System` (P1, WRITE_SETTINGS).
      Secure/Global requieren shell/Shizuku (N2, Fase 6+).
    Parametros: namespace (str): "system"|"secure"|"global" (default
      "system"); key (str); value (str): valor crudo; confirm (bool).
    Retorno: sin `confirm` -> {ok:true, verified:false, evidence=
      {planned:true, preview{value_sha256}, hint}}; con `confirm` ->
      {ok:true, verified:true, evidence={namespace, key, written}}.
    Permisos/Grants: System: WRITE_SETTINGS (ajuste especial) + scope
      admin + confirm. Secure/Global: N2.
    Errores/gotchas: Secure/Global -> METHOD_NOT_ALLOWED (N2);
      WRITE_SETTINGS_DISABLED sin permiso; SETTINGS_PUT_FAILED si el
      sistema rechaza. Revertir = put con el valor previo (leer antes
      con settings_get).
    """
    return await native_tools.settings_put(namespace, key, value, confirm)


@mcp.tool()
async def open_url(url: str, package: str = "") -> dict:
    """Abre una URL en su app; solo apertura, el envio va por el carril Jev.

    Descripcion: Lanza ACTION_VIEW sobre `url`. Sin `package`, el sistema
      resuelve y con >1 handler muestra chooser (ResolverActivity); con
      `package` se fija el componente del handler (1 salto, sin chooser).
    Parametros: url (str): esquema `://…` valido (obligatoria;
      https/tel/mailto/sms/geo); package (str): paquete `a.b.c` del
      handler a forzar; "" (default) = resolver del sistema.
    Retorno: {ok, verified, evidence, hint}; evidence =
      {url, via, package?, latency_ms}; `via` =
      "startActivity"|"startActivity-package"|"shizuku-am".
    Permisos/Grants: scope ui, sin grant.
    Errores/gotchas: con package="" y >1 handler -> chooser; con
      `package` no hay chooser. Paquete no instalado -> PACKAGE_NOT_FOUND;
      instalado sin handler -> INTENT_UNRESOLVED; esquema invalido ->
      VALIDATION_ERROR. No envia (eso es send_intent + Jev).
    """
    return await native_tools.open_url(url, package)


@mcp.tool()
async def send_intent(action: str, uri: str = "", package: str = "", mime: str = "",
                      confirm: bool = False, extras: dict | None = None) -> dict:
    """Lanza un intent (apertura/pre-relleno); el envio ocurre en la UI destino.

    Descripcion: Construye y lanza un Intent. No hay envio headless real:
      como maximo abre el editor pre-rellenado; el envio lo hace la app
      destino (o el carril Jev con compuertas).
    Parametros: action (str): VIEW|SEND|CALL|DIAL|...; uri (str):
      esquema://…; package (str): paquete `a.b.c` a forzar; mime (str);
      confirm (bool); extras (dict[str,str]) -> --es.
    Retorno: accion critica sin confirm -> {ok:true, verified:false,
      evidence={planned:true, preview, hint}}; con exito ->
      {ok:true, verified:true, evidence={action, via}}.
    Permisos/Grants: scope ui sin grant; acciones criticas (SEND/SENDTO/
      SEND_MULTIPLE/CALL o VIEW con sms/tel/mailto) exigen confirm=true.
    Errores/gotchas: SEND/CALL sin confirm -> planned (nunca envia solo);
      no finge envio nativo; package invalido -> VALIDATION_ERROR;
      fallback Shizuku `am start` -> via "shizuku-am".
    """
    return await native_tools.send_intent(action, uri, package, mime, confirm, extras)


@mcp.tool()
async def get_clipboard_device() -> dict:
    """Lee el clipboard del dispositivo en foreground (nunca crudo).

    Descripcion: Caso narrow en primer plano; en background Android 10+
      se reporta honesto. Para el host usa el atajo get_clipboard.
    Parametros: Ninguno.
    Retorno: {ok, verified, evidence, hint}; evidence =
      {len, sha256, via, forense{via, len, sha256}, latency_ms}; el
      texto NUNCA viaja.
    Permisos/Grants: scope read sensible.
    Errores/gotchas: background Android 10+ o vacio -> CLIPBOARD_EMPTY
      honesto; no sondea ni inventa.
    """
    return await native_tools.get_clipboard_device()


@mcp.tool()
async def get_app_usage(hours: int = 24, window: str | None = None) -> dict:
    """Tiempo en foreground agregado por paquete (top 50).

    Descripcion: Suma `totalTimeInForeground` por paquete. Solo
      agregados, sin eventos crudos.
    Parametros: hours (int): 1..24 sin `window` (default 24), 1..168 con
      `window="raw"`; window (str|None): "today"|"week"|"raw"|None.
    Retorno: {ok, verified, evidence, hint}; evidence =
      {window, begin, now, window_h, count,
       apps[{package, foreground_ms, last_used}], latency_ms}.
      `foreground_ms` en MILISEGUNDOS; begin/now/last_used en ms Unix.
    Permisos/Grants: acceso especial "Acceso a datos de uso"
      (PACKAGE_USAGE_STATS).
    Errores/gotchas: sin grant -> USAGE_ACCESS_DISABLED; apps de fondo
      que acumulan tiempo (p.ej. Termux) inflan `foreground_ms`; solo
      agregados.
    """
    return await native_tools.get_app_usage(hours, window)


@mcp.tool()
async def list_contacts(query: str = "", limit: int = 50, offset: int = 0,
                        with_phone: bool = False) -> dict:
    """Lista contactos con proyeccion minima y paginacion.

    Descripcion: Pagina contactos (nombre; telefono solo si se pide).
      PII: forense solo conteos/hashes.
    Parametros: query (str): filtro de nombre; limit (int): 1..100
      (default 50); offset (int): >=0; with_phone (bool): incluye numero.
    Retorno: {ok, verified, evidence, hint}; evidence =
      {returned, offset, contacts[{id, display_name, phone?}],
       forense{count, sha256}, latency_ms}.
    Permisos/Grants: READ_CONTACTS (runtime).
    Errores/gotchas: sin permiso -> CONTACTS_PERMISSION_DENIED; sin
      `total`; el forense solo guarda count+sha256 (sin PII cruda).
    """
    return await native_tools.list_contacts(query, limit, offset, with_phone)


@mcp.tool()
async def add_contact(display_name: str, phone: str = "", email: str = "",
                      confirm: bool = False) -> dict:
    """Alta de contacto (accion critica).

    Descripcion: Inserta un contacto via ContactsContract; exige
      confirmacion explicita.
    Parametros: display_name (str); phone (str) opcional; email (str)
      opcional; confirm (bool).
    Retorno: sin confirm -> {ok:true, verified:false, evidence=
      {planned:true, preview, hint}}; con confirm -> {ok:true,
      verified:true, evidence={added, ops, uri}}.
    Permisos/Grants: WRITE_CONTACTS (runtime) + confirm=true.
    Errores/gotchas: sin confirm -> planned; sin permiso ->
      CONTACTS_PERMISSION_DENIED; VALIDATION_ERROR si display_name vacio;
      preview solo longitudes/hashes.
    """
    return await native_tools.add_contact(display_name, phone, email, confirm)


@mcp.tool()
async def list_events(time_min: int = 0, time_max: int = 0, calendar_id: int = 0,
                      include_location: bool = False) -> dict:
    """Eventos de calendario en una ventana (max 7 dias).

    Descripcion: Consulta instancias de calendario. PII: forense solo
      conteos/hashes.
    Parametros: time_min (int): inicio en MILISEGUNDOS Unix (0 = ahora);
      time_max (int): fin en MILISEGUNDOS Unix (0 = time_min + 7 dias);
      calendar_id (int): 0 = todos; include_location (bool).
    Retorno: {ok, verified, evidence, hint}; evidence =
      {time_min, time_max, returned,
       events[{event_id, title, begin, end, calendar_id, location?}],
       forense{count, sha256}, latency_ms}; begin/end en ms Unix.
    Permisos/Grants: READ_CALENDAR (runtime).
    Errores/gotchas: time_min/time_max/begin/end en MILISEGUNDOS Unix;
      ventana > 7 dias -> VALIDATION_ERROR; sin permiso ->
      CALENDAR_PERMISSION_DENIED; sin `total`; PII solo conteos/hash.
    """
    return await native_tools.list_events(time_min, time_max, calendar_id, include_location)


@mcp.tool()
async def create_event(title: str, start_ms: int, end_ms: int, calendar_id: int = 0,
                       description: str = "", confirm: bool = False) -> dict:
    """Crea un evento (accion critica).

    Descripcion: Inserta un evento via CalendarContract; exige
      confirmacion explicita.
    Parametros: title (str); start_ms (int): inicio en MILISEGUNDOS Unix;
      end_ms (int): fin en MILISEGUNDOS Unix (> start_ms); calendar_id
      (int): 0 = primer calendario visible; description (str) opcional;
      confirm (bool).
    Retorno: sin confirm -> {ok:true, verified:false, evidence=
      {planned:true, preview{title_sha256, title_len, start, end}, hint}};
      con confirm -> {ok:true, verified:true, evidence=
      {created, event_id}}.
    Permisos/Grants: WRITE_CALENDAR (runtime) + confirm=true.
    Errores/gotchas: start_ms/end_ms en MILISEGUNDOS Unix; sin confirm ->
      planned; sin permiso -> CALENDAR_PERMISSION_DENIED; sin calendario
      visible -> CALENDAR_UNAVAILABLE; title/vals invalidos ->
      VALIDATION_ERROR; preview hashea el titulo.
    """
    return await native_tools.create_event(title, start_ms, end_ms, calendar_id,
                                           description, confirm)


@mcp.tool()
async def list_notifications() -> dict:
    """Notificaciones activas con proyeccion minima.

    Descripcion: Hasta 50 notificaciones del NotificationListener,
      titulo/texto truncados a 200 chars. PII: forense solo
      conteos/hashes.
    Parametros: Ninguno.
    Retorno: {ok, verified, evidence, hint}; evidence =
      {count, notifications[{key, package, title<=200, text<=200,
       has_remote_input, posted_at}], forense{count, sha256},
       latency_ms}; `posted_at` en ms Unix.
    Permisos/Grants: servicio NotificationListener habilitado (Acceso a
      notificaciones).
    Errores/gotchas: sin listener -> NOTIFICATION_LISTENER_DISABLED; en
      algunas ROM el servicio no enlaza aunque se active (p.ej. 5002E:
      "no disponible en este dispositivo"): error honesto, no inventa.
    """
    return await native_tools.list_notifications()


@mcp.tool()
async def reply_notification(key: str, text: str, confirm: bool = False) -> dict:
    """Responde una notificacion via RemoteInput (accion critica).

    Descripcion: Envia una respuesta a la notificacion `key`; exige
      confirmacion explicita.
    Parametros: key (str): de list_notifications; text (str): cuerpo;
      confirm (bool).
    Retorno: sin confirm -> {ok:true, verified:false, evidence=
      {planned:true, preview{key, text_len, text_sha256}, hint}}; con
      confirm -> {ok:true, verified:true, evidence={replied, key, via}}.
    Permisos/Grants: listener habilitado + confirm=true.
    Errores/gotchas: sin confirm -> planned; listener ausente ->
      NOTIFICATION_LISTENER_DISABLED; notificacion inactiva ->
      NOTIFICATION_GONE; sin RemoteInput -> NO_REMOTE_INPUT; fallo ->
      REPLY_FAILED; NL puede no existir en algunas ROM.
    """
    return await native_tools.reply_notification(key, text, confirm)


@mcp.tool()
async def media_state() -> dict:
    """Sesiones multimedia activas.

    Descripcion: Hasta 10 sesiones con paquete/titulo/artista/estado.
      Monta el grant del NotificationListener.
    Parametros: Ninguno.
    Retorno: {ok, verified, evidence, hint}; evidence =
      {count, sessions[{package, title, artist, state}], latency_ms};
      `state` = playing|paused|stopped|buffering|unknown.
    Permisos/Grants: NotificationListener habilitado.
    Errores/gotchas: sin listener/permiso -> MEDIA_SESSIONS_UNAVAILABLE;
      algunas ROM no exponen el listener.
    """
    return await native_tools.media_state()


@mcp.tool()
async def media_control(action: str, package: str = "",
                        confirm: bool = False) -> dict:
    """Controla el transporte multimedia.

    Descripcion: play/pause/next/prev (reversibles); `stop` es
      destructivo y exige confirmacion.
    Parametros: action (str): "play"|"pause"|"next"|"prev"|"stop";
      package (str): "" = primera sesion; confirm (bool).
    Retorno: `stop` sin confirm -> {ok:true, verified:false, evidence=
      {planned:true, preview}}; con exito -> {ok:true, verified:true,
      evidence={action, package, via}}.
    Permisos/Grants: listener habilitado; `stop` exige confirm=true.
    Errores/gotchas: sin sesiones -> MEDIA_SESSIONS_UNAVAILABLE; paquete
      sin sesion -> MEDIA_SESSION_GONE; fallo -> MEDIA_CONTROL_FAILED;
      action invalida -> VALIDATION_ERROR.
    """
    return await native_tools.media_control(action, package, confirm)


@mcp.tool()
async def get_location(timeout_ms: int = 8000, max_age_s: int = 300) -> dict:
    """Ubicacion en foreground (cache fresca primero; si no, fix).

    Descripcion: Devuelve la ultima ubicacion conocida si es fresca; si
      no, espera un fix hasta el timeout. Nunca inventa. PII: forense
      solo hash.
    Parametros: timeout_ms (int): espera en MILISEGUNDOS, <=30000
      (default 8000); max_age_s (int): antiguedad maxima de cache en
      SEGUNDOS, <=3600 (default 300).
    Retorno: {ok, verified, evidence, hint}; evidence =
      {lat, lon, accuracy_m, provider, age_s, via: last_known|fresh,
       forense{via, sha256}, latency_ms}; `accuracy_m` en metros,
      `age_s` en segundos.
    Permisos/Grants: ACCESS_FINE_LOCATION o ACCESS_COARSE_LOCATION
      (runtime).
    Errores/gotchas: timeout_ms en MILISEGUNDOS y max_age_s en SEGUNDOS;
      sin permiso -> LOCATION_PERMISSION_DENIED; proveedores apagados ->
      LOCATION_UNAVAILABLE; sin fix -> LOCATION_TIMEOUT (nunca inventa).
    """
    return await native_tools.get_location(timeout_ms, max_age_s)


@mcp.tool()
async def take_photo(confirm: bool = False, camera: str = "back") -> dict:
    """Foto headless restringida (nunca silenciosa).

    Descripcion: Captura via Camera2 bajo foreground service visible con
      indicador. Exige confirmacion SIEMPRE.
    Parametros: confirm (bool): obligatorio; camera (str):
      "back"|"front".
    Retorno: sin confirm -> {ok:true, verified:false, evidence=
      {planned:true, preview, hint}}; con confirm -> {ok:true,
      verified:true, evidence={img_base64, w, h, via}} (<4 MiB; PX).
    Permisos/Grants: CAMERA (runtime) + FGS `camera` + confirm=true
      siempre.
    Errores/gotchas: sin confirm -> planned; sin permiso -> CAMERA_DENIED;
      sin camara -> CAMERA_UNAVAILABLE; fallo -> CAMERA_FAILED; en
      pantalla bloqueada o algunas ROM puede degradar.
    """
    return await native_tools.take_photo(confirm, camera)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
