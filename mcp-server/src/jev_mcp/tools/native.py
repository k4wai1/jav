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
    """Bateria: nivel %, cargando, enchufe, temperatura, ahorro. Tecnico, sin PII."""
    return await _jam_call("get_battery", {}, _call)


async def get_memory(_call=None) -> dict:
    """RAM: disponible/total/umbral/baja. Tecnico, sin PII."""
    return await _jam_call("get_memory", {}, _call)


async def get_storage(detail: str = "basic", _call=None) -> dict:
    """Almacenamiento interno: total/libre/disponible. `fine` = N2 (METHOD_NOT_ALLOWED)."""
    return await _jam_call("get_storage", {"detail": detail}, _call)


async def get_cpu(detail: str = "basic", _call=None) -> dict:
    """CPU: nº procesadores + uso % instantaneo. `fine` = N2 (METHOD_NOT_ALLOWED)."""
    return await _jam_call("get_cpu", {"detail": detail}, _call)


async def get_device_info(_call=None) -> dict:
    """Hardware: fabricante/modelo/ABI/pantalla/features/locale/zona. Sin IDs persistentes."""
    return await _jam_call("get_device_info", {}, _call)


async def settings_get(namespace: str = "system", key: str = "", _call=None) -> dict:
    """Lee un ajuste System/Secure/Global por clave. Lectura, sin confirm."""
    return await _jam_call("settings_get", {"namespace": namespace, "key": key}, _call)


async def settings_put(namespace: str = "system", key: str = "",
                        value: str = "", confirm: bool = False, _call=None) -> dict:
    """Escribe ajuste System (P1, WRITE_SETTINGS). Sin confirm -> planned+preview.
    Secure/Global = N2: METHOD_NOT_ALLOWED honesto hasta Fase 6."""
    return await _jam_call("settings_put", {"namespace": namespace, "key": key,
                                            "value": value, "confirm": confirm}, _call)


async def open_url(url: str, _call=None) -> dict:
    """Abre una URL (https/tel/mailto/sms/geo) en su app. Solo apertura; el envio va por Jev."""
    return await _jam_call("open_url", {"url": url}, _call)


async def send_intent(action: str, uri: str = "", package: str = "", mime: str = "",
                      confirm: bool = False, extras: dict | None = None, _call=None) -> dict:
    """Lanza un intent (apertura/pre-relleno). Si envia/comunica/borra y no hay
    confirm -> planned+preview sin ejecutar."""
    return await _jam_call("send_intent", {"action": action, "uri": uri,
                                          "package": package, "mime": mime,
                                          "confirm": confirm,
                                          "extras": extras or {}}, _call)


async def get_clipboard_device(_call=None) -> dict:
    """Lee el clipboard via Jam en foreground (caso narrow). En bg Android 10+
    lo bloquea -> CLIPBOARD_EMPTY honesto. Huesped: usa get_clipboard (dumpsys)."""
    d = await _jam_call("get_clipboard", {}, _call)
    if d.get("ok"):
        ev = d["evidence"]
        ev["forense"] = {"via": "jam-foreground", "len": ev.get("len", 0),
                         "sha256": ev.get("sha256", "")}
    return d


# --- N1: con grant del usuario -----------------------------------------------

async def get_app_usage(hours: int = 24, window: str | None = None, _call=None) -> dict:
    """Aggregate foreground time per package, ranked by `foreground_ms` (top 50).

    Without `window` returns the last `hours` (clamped 1..24), the legacy
    behavior. With `window`, `hours` is reinterpreted or ignored:
      - "today": since local midnight of the current day.
      - "week": the last 7 days.
      - "raw": the last `hours` (clamped 1..168).
    Evidence carries `window`, `begin`, `now`, `window_h` and
    `apps[{package, foreground_ms, last_used}]`. Without the special usage
    access grant Jam returns USAGE_ACCESS_DISABLED (honest, no guessing).
    """
    return await _jam_call("get_app_usage", {"hours": hours, "window": window}, _call)


async def list_contacts(query: str = "", limit: int = 50, offset: int = 0,
                        with_phone: bool = False, _call=None) -> dict:
    """Contactos paginados (nombre; telefono solo si se pide). Sin grant -> DENIED."""
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
    """Alta de contacto (critica). Sin confirm -> planned+preview."""
    return await _jam_call("add_contact", {"display_name": display_name, "phone": phone,
                                          "email": email, "confirm": confirm}, _call)


async def list_events(time_min: int = 0, time_max: int = 0, calendar_id: int = 0,
                      include_location: bool = False, _call=None) -> dict:
    """Eventos de calendario en ventana (max 7 dias). Sin grant -> DENIED."""
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
    """Crea evento (critico). Sin confirm -> planned+preview."""
    return await _jam_call("create_event", {"calendar_id": calendar_id, "title": title,
                                           "start_ms": start_ms, "end_ms": end_ms,
                                           "description": description,
                                           "confirm": confirm}, _call)


async def list_notifications(_call=None) -> dict:
    """Notificaciones activas (paquete/titulo/texto<=200/has_remote_input/hora).
    Sin grant -> NOTIFICATION_LISTENER_DISABLED."""
    d = await _jam_call("list_notifications", {}, _call)
    if d.get("ok"):
        ev = d["evidence"]
        ns = ev.get("notifications", []) or []
        canon = "|".join(f"{n.get('key')}" for n in ns)
        ev["forense"] = _forense_summary(canon, len(ns))
    return d


async def reply_notification(key: str, text: str, confirm: bool = False, _call=None) -> dict:
    """Responde una notificacion via RemoteInput (critica). Sin confirm -> planned+preview."""
    return await _jam_call("reply_notification", {"key": key, "text": text,
                                                 "confirm": confirm}, _call)


async def media_state(_call=None) -> dict:
    """Sesiones multimedia activas (paquete/titulo/artista/estado). Monta el grant NL."""
    return await _jam_call("media_state", {}, _call)


async def media_control(action: str, package: str = "",
                        confirm: bool = False, _call=None) -> dict:
    """Transporte play/pause/next/prev (reversible). stop = destructivo -> confirm."""
    return await _jam_call("media_control", {"action": action, "package": package,
                                            "confirm": confirm}, _call)


async def get_location(timeout_ms: int = 8000, max_age_s: int = 300, _call=None) -> dict:
    """Ubicacion foreground (caché fresca primero; fix con timeout<=30s). Sin fix -> TIMEOUT honesto."""
    d = await _jam_call("get_location", {"timeout_ms": timeout_ms,
                                        "max_age_s": max_age_s}, _call)
    if d.get("ok"):
        ev = d["evidence"]
        canon = f"{ev.get('lat')},{ev.get('lon')},{ev.get('accuracy_m')}"
        ev["forense"] = {"via": ev.get("via", ""),
                         "sha256": hashlib.sha256(canon.encode()).hexdigest()}
    return d


async def take_photo(confirm: bool = False, camera: str = "back", _call=None) -> dict:
    """Foto headless restringida (CAMERA+FGS+confirm siempre). Sin confirm -> planned."""
    return await _jam_call("take_photo", {"confirm": confirm, "camera": camera}, _call)


__all__ = [
    "get_battery", "get_memory", "get_storage", "get_cpu", "get_device_info",
    "settings_get", "settings_put", "open_url", "send_intent", "get_clipboard_device",
    "get_app_usage", "list_contacts", "add_contact", "list_events", "create_event",
    "list_notifications", "reply_notification", "media_state", "media_control",
    "get_location", "take_photo",
]
