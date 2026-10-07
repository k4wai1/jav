"""Tools device/: estado y paquetes.

Docstrings de 5 secciones (Descripcion / Parametros / Retorno /
Permisos-Grants / Errores-gotchas).
"""
from __future__ import annotations

import subprocess

from . import _base as B


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
      conectada; conexion caida -> ok:false.
    """
    jam = await B.jam_client()
    try:
        fg = await jam.get_foreground()
    finally:
        await jam.__aexit__()
    return B.ok(True, {
        "scopes": jam.scopes,
        "app_version": jam.app_version,
        "foreground": fg,
    })


async def list_packages(filter: str = "") -> dict:
    """Lista paquetes instalados (host `adb shell pm list packages`).

    Descripcion: Enumera paquetes visibles en el host adb; no pasa por
      el WS de Jam.
    Parametros: filter (str): subcadena case-insensitive; "" = todos.
    Retorno: {ok, verified, evidence, hint}; evidence =
      {count, packages[]}.
    Permisos/Grants: adb del host; sin scope Jam.
    Errores/gotchas: host sin adb o dispositivo desconectado -> fallo;
      por visibilidad de paquetes (`<queries>`) la lista puede ser
      parcial.
    """
    out = subprocess.run(["adb", "shell", "pm", "list", "packages"],
                         capture_output=True, text=True).stdout
    pkgs = [l.split(":", 1)[1] for l in out.splitlines() if l.startswith("package:")]
    if filter:
        fl = filter.lower()
        pkgs = [p for p in pkgs if fl in p.lower()]
    return B.ok(True, {"count": len(pkgs), "packages": pkgs})


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
    jam = await B.jam_client()
    try:
        fg = await jam.get_foreground()
    finally:
        await jam.__aexit__()
    return B.ok(True, fg)
