"""Tools ui/: lectura normalizada + acciones.

Docstrings de 5 secciones (Descripcion / Parametros / Retorno /
Permisos-Grants / Errores-gotchas). Varios son atajos del Director, no
acciones del enum de Jev (el enum decide TAP/TYPE/SCROLL/BACK/DONE).
"""
from __future__ import annotations

from ..core import loop_helpers as _h
from ..socket_client import JamError
from ..state import NormalizedState
from ..ui_normalizer import format_state, normalize
from . import _base as B


_SCREEN_H = 0
_SCREEN_W = 0


def _refresh_screen_size() -> None:
    """Lee `adb shell wm size` una vez (ancho + alto, cacheados)."""
    global _SCREEN_H, _SCREEN_W
    import re
    import subprocess
    try:
        out = subprocess.run(["adb", "shell", "wm", "size"],
                             capture_output=True, text=True,
                             timeout=10).stdout
        m = re.search(r"(\d+)x(\d+)", out)
        if m:
            _SCREEN_W = int(m.group(1))
            _SCREEN_H = int(m.group(2))
    except Exception:
        pass


def screen_height() -> int:
    """Altura en px (cacheada; `adb shell wm size`). 0 si no se puede."""
    if not _SCREEN_H:
        _refresh_screen_size()
    return _SCREEN_H


def screen_width() -> int:
    """Ancho en px (cacheado; `adb shell wm size`). 0 si no se puede."""
    if not _SCREEN_W:
        _refresh_screen_size()
    return _SCREEN_W


async def _dump() -> tuple[dict, NormalizedState]:
    jam = await B.jam_client()
    try:
        return jam, normalize(await jam.dump_ui(), screen_h=screen_height(),
                              screen_w=screen_width())
    except Exception:
        await jam.__aexit__()
        raise


async def read_screen() -> dict:
    """Pantalla normalizada: candidatos compactos + snapshot_id.

    Descripcion: Dumpea el arbol de accesibilidad y lo normaliza a
      candidatos accionables con ids; base del bucle de decision.
    Parametros: Ninguno.
    Retorno: {ok, verified, evidence, hint}; evidence =
      {package, activity, snapshot_id, raw_count, screen_height,
       screen_width, focused_field, first_result, candidates[], render}.
      `snapshot_id` monotono; dimensiones en PX logicos.
    Permisos/Grants: accesibilidad (scope read).
    Errores/gotchas: ACCESSIBILITY_DISABLED; `snapshot_id` obligatorio
      para tap_node/type_text (STALE_SNAPSHOT si la UI cambio); filtra
      nodos de decoracion del sistema.
    """
    try:
        jam, st = await _dump()
        await jam.__aexit__()
    except JamError as e:
        return B.jam_fail(e)
    ff = st.focused_field.as_view() if st.focused_field is not None else {
        "label": "none", "kind": "none", "holds": "empty"}
    cands = [
        {"id": c.id, "label": c.compact(), "cls": c.cls,
         "class_short": c.class_short, "flags": c.flags,
         "clickable": c.clickable, "editable": c.editable,
         "focused": c.focused, "scrollable": c.scrollable,
         "visible": c.visible,
         "text": c.text, "desc": c.desc,
         "resource_id": c.resource_id, "bounds": list(c.bounds)}
        for c in st.candidates
    ]
    # Hint §12.2: primer interactivo del contenedor principal mid-list
    # (prior, nunca poda: la tabla viaja completa).
    first = _h.first_result(
        [{**c, "idx": i} for i, c in enumerate(cands[:_h.MAX_TABLE])])
    return B.ok(True, {
        "package": st.package,
        "activity": st.activity,
        "snapshot_id": st.snapshot_id,
        "raw_count": st.raw_count,
        "screen_height": screen_height(),
        "screen_width": screen_width(),
        "focused_field": ff,  # P0-1: campo enfocado + contenido (EN, sin secreto)
        "first_result": first,  # §12.2: idx o None, nunca inventado
        "candidates": cands,
        "render": format_state(st),
    })


async def tap_text(text: str) -> dict:
    """Atajo del Director: toca el primer nodo que contiene el texto.

    Descripcion: Conveniencia para el Director (hace un dump interno).
      NO es una accion del enum de Jev; el enum usa TAP sobre node_id
      via tap_node con snapshot fresco.
    Parametros: text (str): subcadena a matchear.
    Retorno: {ok, verified, evidence, hint}; evidence = {node_id, via}.
    Permisos/Grants: accesibilidad (scope ui).
    Errores/gotchas: SELECTOR_NOT_FOUND si no matchea; preferir
      tap_node(node_id, snapshot_id) si ya hay snapshot fresco.
    """
    try:
        jam = await B.jam_client()
        try:
            r = await jam.tap({"text_contains": text})
        finally:
            await jam.__aexit__()
    except JamError as e:
        return B.jam_fail(e)
    return B.ok(True, {"node_id": r.get("node_id"), "via": r.get("via")},
                hint="verifica el efecto con read_screen")


async def tap_node(node_id: str, snapshot_id: int) -> dict:
    """Toca por id + snapshot (rapido, sin dump interno).

    Descripcion: Accion TAP del enum Jev: toca un nodo concreto del
      snapshot. Clickable -> ACTION_CLICK; si no, dispatchGesture al
      centro de bounds.
    Parametros: node_id (str); snapshot_id (int): de read_screen/
      wait_for_text.
    Retorno: {ok, verified, evidence, hint}; evidence = {node_id, via}.
    Permisos/Grants: accesibilidad (scope ui).
    Errores/gotchas: STALE_SNAPSHOT si la UI cambio; SELECTOR_NOT_FOUND
      si el id no existe. No devuelve snapshot: verificar con
      read_screen.
    """
    try:
        jam = await B.jam_client()
        try:
            r = await jam._send("tap_node", {"node_id": node_id, "snapshot_id": snapshot_id})
            if not r.get("ok"):
                raise JamError(r.get("code", "?"), r.get("error", "?"))
        finally:
            await jam.__aexit__()
    except JamError as e:
        return B.jam_fail(e)
    res = r.get("result", {})
    return B.ok(True, {"node_id": res.get("node_id"), "via": res.get("via")},
                hint="verifica el efecto con read_screen")


async def type_text(node_id: str, snapshot_id: int, text: str) -> dict:
    """Escribe en un campo ya enfocado (semantica REPLACE).

    Descripcion: Accion TYPE del enum Jev: escribe con ACTION_SET_TEXT
      (reemplaza el contenido; sin teclado simulado ni append). El
      snapshot_id es eco del request; el fresco lo aporta el bucle.
    Parametros: node_id (str); snapshot_id (int); text (str): contenido
      final del campo.
    Retorno: {ok, verified, evidence, hint}; evidence =
      {chars, snapshot_id}.
    Permisos/Grants: accesibilidad (scope ui).
    Errores/gotchas: NOT_FOCUSED si el nodo no esta enfocado (haz tap
      antes; no hay taps implicitos); STALE_SNAPSHOT. No devuelve
      snapshot: verifica con read_screen.
    """
    try:
        jam = await B.jam_client()
        try:
            r = await jam._send("type", {"node_id": node_id,
                                         "snapshot_id": snapshot_id, "text": text})
            if not r.get("ok"):
                raise JamError(r.get("code", "?"), r.get("error", "?"))
        finally:
            await jam.__aexit__()
    except JamError as e:
        return B.jam_fail(e)
    return B.ok(True, {"chars": r.get("result", {}).get("chars", 0),
                       "snapshot_id": snapshot_id},
                hint="verifica el efecto con read_screen")


async def scroll(direction: str = "down", node_id: str | None = None) -> dict:
    """Scroll en una direccion, opcionalmente sobre un nodo.

    Descripcion: Accion SCROLL_UP/DOWN del enum Jev; opcionalmente
      limitada a un nodo scrollable.
    Parametros: direction (str): "up"|"down"|"left"|"right" (default
      "down"); node_id (str|null): nodo scrollable opcional.
    Retorno: {ok, verified, evidence, hint}; evidence = {direction}.
    Permisos/Grants: accesibilidad (scope ui).
    Errores/gotchas: VALIDATION_ERROR con direccion invalida; no
      devuelve snapshot: verifica con read_screen.
    """
    try:
        jam = await B.jam_client()
        try:
            params: dict = {"direction": direction}
            if node_id:
                params["node_id"] = node_id
            await jam._send("scroll", params)
        finally:
            await jam.__aexit__()
    except JamError as e:
        return B.jam_fail(e)
    return B.ok(True, {"direction": direction},
                hint="verifica el efecto con read_screen")


async def press_back() -> dict:
    """Boton atras global.

    Descripcion: Accion BACK del enum Jev.
    Parametros: Ninguno.
    Retorno: {ok, verified, evidence, hint}; evidence = {action}.
    Permisos/Grants: accesibilidad (scope ui).
    Errores/gotchas: ACCESSIBILITY_DISABLED; verifica con read_screen.
    """
    return await _simple("press_back")


async def press_home() -> dict:
    """Atajo del Director: boton home global.

    Descripcion: Conveniencia para el Director. NO es una accion del
      enum de Jev.
    Parametros: Ninguno.
    Retorno: {ok, verified, evidence, hint}; evidence = {action}.
    Permisos/Grants: accesibilidad (scope ui).
    Errores/gotchas: ACCESSIBILITY_DISABLED.
    """
    return await _simple("press_home")


async def _simple(method: str) -> dict:
    """Atajo simple: envia un metodo sin params y verifica con read_screen.

    Descripcion: Helper para press_back/press_home.
    Parametros: method (str): nombre del metodo WS.
    Retorno: {ok, verified, evidence={action}, hint}.
    Permisos/Grants: accesibilidad (scope ui).
    Errores/gotchas: ACCESSIBILITY_DISABLED; verifica con read_screen.
    """
    try:
        jam = await B.jam_client()
        try:
            await jam.call(method)
        finally:
            await jam.__aexit__()
    except JamError as e:
        return B.jam_fail(e)
    return B.ok(True, {"action": method},
                hint="verifica el efecto con read_screen")


async def wait_for_text(text: str, timeout_ms: int = 5000) -> dict:
    """Atajo del Director: espera a que aparezca un texto.

    Descripcion: Conveniencia para el Director (no es accion del enum de
      Jev). Devuelve node_id + snapshot usable.
    Parametros: text (str): subcadena a esperar; timeout_ms (int):
      MILISEGUNDOS (default 5000).
    Retorno: {ok, verified, evidence, hint}; evidence =
      {node_id, snapshot_id}.
    Permisos/Grants: accesibilidad (scope read).
    Errores/gotchas: TIMEOUT si no aparece; el snapshot_id sirve directo
      en tap_node si no hubo mas cambios.
    """
    try:
        jam = await B.jam_client()
        try:
            r = await jam.wait_for_node({"text_contains": text}, timeout_ms)
        finally:
            await jam.__aexit__()
    except JamError as e:
        return B.jam_fail(e)
    return B.ok(True, {"node_id": r.get("node_id"),
                       "snapshot_id": r.get("snapshot_id")},
                hint="usa snapshot_id directo en tap_node si no hubo cambios")


async def screenshot(fmt: str = "png", quality: int = 80) -> dict:
    """Atajo del Director: captura la pantalla.

    Descripcion: Conveniencia para el Director via takeScreenshot (API
      30+) o `screencap` con Shizuku (API 29). NO es accion del enum de
      Jev.
    Parametros: fmt (str): "png"|"webp" (default "png"); quality (int):
      0..100, solo webp (default 80).
    Retorno: {ok, verified, evidence, hint}; evidence =
      {w, h, via, img_base64}; `w`/`h` en PX.
    Permisos/Grants: accesibilidad/Shizuku segun via (scope read).
    Errores/gotchas: SECURE_SURFACE si la ventana tiene FLAG_SECURE;
      PAYLOAD_TOO_LARGE si excede 4 MiB (hint: WebP q80).
    """
    try:
        jam = await B.jam_client()
        try:
            r = await jam.screenshot(fmt, quality)
        finally:
            await jam.__aexit__()
    except JamError as e:
        return B.jam_fail(e)
    return B.ok(True, {"w": r.get("w"), "h": r.get("h"), "via": r.get("via"),
                       "img_base64": r.get("img_base64")})
