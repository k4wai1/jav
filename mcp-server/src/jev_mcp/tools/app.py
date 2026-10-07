"""Tools app/: abrir/cerrar (Shizuku vía Jam).

Docstrings de 5 secciones (Descripcion / Parametros / Retorno /
Permisos-Grants / Errores-gotchas).
"""
from __future__ import annotations

from ..socket_client import JamError
from . import _base as B


async def open_app(package: str) -> dict:
    """Abre una app (Shizuku) y verifica que quedo en foreground.

    Descripcion: Lanza el LAUNCHER de `package` via Shizuku (`am start`)
      y confirma el foreground con get_foreground.
    Parametros: package (str): paquete `a.b.c` (obligatorio).
    Retorno: {ok, verified, evidence, hint}; evidence =
      {package, activity, foreground}.
    Permisos/Grants: scope ui; Shizuku disponible (sin grant de shell);
      nunca `su`.
    Errores/gotchas: SHIZUKU_UNAVAILABLE sin Shizuku; VALIDATION_ERROR
      con forma invalida; VERIFY_FAILED si no llego a foreground;
      fallback `monkey` cuando no hay activity LAUNCHER.
    """
    jam = await B.jam_client()
    try:
        r = await jam.open_app(package)
        fg = await jam.get_foreground()
    except JamError as e:
        return B.jam_fail(e)
    finally:
        await jam.__aexit__()
    if fg.get("package") != package:
        return B.fail("VERIFY_FAILED", f"foreground={fg}",
                      hint="la app no llegó a foreground; reintenta open_app")
    return B.ok(True, {"package": package, "activity": r.get("activity"),
                       "foreground": fg})


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
    jam = await B.jam_client()
    try:
        await jam.force_stop(package)
        fg = await jam.get_foreground()
    except JamError as e:
        return B.jam_fail(e)
    finally:
        await jam.__aexit__()
    if fg.get("package") == package:
        return B.fail("VERIFY_FAILED", f"sigue en foreground: {fg}",
                      hint="reintenta close_app")
    return B.ok(True, {"package": package, "foreground": fg})
