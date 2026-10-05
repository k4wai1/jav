"""Tools ui/: lectura normalizada + acciones."""
from __future__ import annotations

from ..socket_client import JamError
from ..state import NormalizedState
from ..ui_normalizer import format_state, normalize
from . import _base as B


_SCREEN_H = 0


def screen_height() -> int:
    """Altura en px (cacheada; `adb shell wm size`). 0 si no se puede."""
    global _SCREEN_H
    if _SCREEN_H:
        return _SCREEN_H
    import re
    import subprocess
    try:
        out = subprocess.run(["adb", "shell", "wm", "size"],
                             capture_output=True, text=True,
                             timeout=10).stdout
        m = re.search(r"(\d+)x(\d+)", out)
        if m:
            _SCREEN_H = int(m.group(2))
    except Exception:
        pass
    return _SCREEN_H


async def _dump() -> tuple[dict, NormalizedState]:
    jam = await B.jam_client()
    try:
        return jam, normalize(await jam.dump_ui(), screen_h=screen_height())
    except Exception:
        await jam.__aexit__()
        raise


async def read_screen() -> dict:
    try:
        jam, st = await _dump()
        await jam.__aexit__()
    except JamError as e:
        return B.jam_fail(e)
    return B.ok(True, {
        "package": st.package,
        "activity": st.activity,
        "snapshot_id": st.snapshot_id,
        "raw_count": st.raw_count,
        "screen_height": screen_height(),
        "candidates": [
            {"id": c.id, "label": c.compact(), "cls": c.cls,
             "class_short": c.class_short, "flags": c.flags,
             "clickable": c.clickable, "editable": c.editable,
             "focused": c.focused, "scrollable": c.scrollable,
             "visible": c.visible,
             "text": c.text, "desc": c.desc,
             "resource_id": c.resource_id, "bounds": list(c.bounds)}
            for c in st.candidates
        ],
        "render": format_state(st),
    })


async def tap_text(text: str) -> dict:
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
    return B.ok(True, {"chars": r.get("result", {}).get("chars", 0)},
                hint="verifica el efecto con read_screen")


async def scroll(direction: str = "down", node_id: str | None = None) -> dict:
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
    return await _simple("press_back")


async def press_home() -> dict:
    return await _simple("press_home")


async def _simple(method: str) -> dict:
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
