"""Tools app/: abrir/cerrar (Shizuku vía Jam)."""
from __future__ import annotations

from ..socket_client import JamError
from . import _base as B


async def open_app(package: str) -> dict:
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
