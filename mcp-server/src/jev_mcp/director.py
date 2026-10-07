"""Fachada director-cliente v5 (director-client.md §5).

El director (OpenCode/operador, unico planificador) invoca paso a paso,
un paso = una herramienta atomica. Cada una devuelve
{ok, verified, evidence, hint}; verified=true solo con verificacion real.

Nombres exactos para invocacion estilo curl desde el host::

    uv run python -c "from jev_mcp.tools import open_app, ..."
    uv run python -c "from jev_mcp.director import resolve_element, ..."

Este modulo NO importa ``loop.run_goal`` ni el decisor single-pass con
goal global (congelados §6): el path director usa el resolver ciego
``core.director_resolve`` (sobre ``jev_client.ask``, una Choice, sin
goal global).

Herramientas §5:
1 open_app(package) — existe (app.py, Shizuku am start + verify foreground)
2 resolve_element(description) — nueva §3 (este modulo re-exporta la pura)
3 tap_idx(idx, snapshot_id) — sobre ui.tap_node (by_idx vigente, sin snapshot)
4 type_text(node_id, snapshot_id, text) — existe (ACTION_SET_TEXT + foco)
5 read_screen_state() — existe como ui.read_screen (dump + normalizer + tabla)
6 get_clipboard() — existe como clipboard.read_clipboard (dumpsys + forma)
7 set_clipboard(text) — nueva §4.1 (Jam ClipboardManager + read-back)
+ scroll/back/wait/screenshot sin cambio.
"""
from __future__ import annotations

from .core import loop_helpers as _h
from .core.director_resolve import build_resolve_state as _build_state
from .core.director_resolve import resolve_element as _resolve
from .tools import app as _app
from .tools import clipboard as _clip
from .tools import ui as _ui

# --- §5.2 resolver (ciego al goal) ----------------------------------------


async def resolve_element(
    description_en: str,
    table: list,
    snapshot_id: int,
    *,
    current_app: str = "",
    first_result: int | None = None,
    _ask=None,
    _tracker=None,
    _run_id: str = "",
) -> dict:
    """Jev-resolver UMA Choice: micro-intencion EN + tabla -> {idx|NONE, conf}.

    ``description_en`` describe SOLO lo visible-ahora en ingles, una frase
    (p.ej. "Tap the Copy link row"). NUNCA el goal global: el state enviado
    a Jev solo contiene screen_goal + current_app + snapshot_id + table +
    first_result (anti-poisoning §3.1, verificado en test capturando state).
    """
    return await _resolve(
        description_en,
        table,
        snapshot_id,
        current_app=current_app,
        first_result=first_result,
        _ask=_ask,
        _tracker=_tracker,
        _run_id=_run_id,
    )


# --- §5.1 open_app ----------------------------------------------------------


async def open_app(package: str) -> dict:
    """Abre una app (Shizuku am start, fallback monkey) + verify foreground."""
    return await _app.open_app(package)


async def close_app(package: str) -> dict:
    """Cierra una app (force-stop) + verifica salida."""
    return await _app.close_app(package)


# --- §5.5 lectura -----------------------------------------------------------


async def read_screen_state() -> dict:
    """Pantalla vigente: dump_ui + normalizer + tabla + snapshot monotónico."""
    return await _ui.read_screen()


# Alias: el director puede pedir read_screen indistintamente.
read_screen = read_screen_state


# --- §5.3 tap_idx ------------------------------------------------------------


async def tap_idx(
    idx: int,
    snapshot_id: int,
    candidates: list | None = None,
    *,
    screen_height: int = 0,
    _tap=None,
) -> dict:
    """Tapea por indice de tabla vigente (resuelve by_idx[idx] -> node_id).

    ``candidates``: lista ``candidates`` de la evidencia de
    ``read_screen_state`` vigente (mismo snapshot). Sin ella se re-observa
    UNA vez (el director prefiere pasarla para no pagar un dump extra;
    el tap por selector interno de Jam sí dumpea, el tap_node no).

    Garantías §7.1: idx en tabla, nodo visible, bounds en pantalla,
    snapshot fresco (mismatch -> STALE_SNAPSHOT, re-observar + re-resolver
    una vez en el director, no en la app). Reporta `via`, sin snapshot.
    """
    cands = candidates
    snap = snapshot_id
    if cands is None:
        st = await read_screen_state()
        if not st.get("ok"):
            return st
        ev = st.get("evidence", {}) or {}
        cands = ev.get("candidates", [])
        snap = ev.get("snapshot_id", snapshot_id)
        if snap != snapshot_id:
            return {
                "ok": False,
                "verified": False,
                "evidence": {
                    "code": "STALE_SNAPSHOT",
                    "error": (f"snapshot {snapshot_id} != vigente {snap}; "
                              "re-resuelve contra la tabla nueva"),
                },
                "hint": "re-haz read_screen_state y resolve_element",
            }
        screen_height = ev.get("screen_height", 0) or screen_height
    rows, by_idx = _h.build_table(
        list(cands or []),
        0,
        int(screen_height or 0),
    )
    row = by_idx.get(idx) if isinstance(idx, int) else None
    bad = _h.validate_target(row, int(screen_height or 0))
    if bad:
        hint = "re-haz read_screen_state; el indice no matchea"
        if bad.get("code") == "STALE_SNAPSHOT":
            hint = "re-haz read_screen_state y re-resuelve (1 reintento)"
        return {"ok": False, "verified": False,
                "evidence": bad, "hint": hint}
    tap_fn = _tap or _ui.tap_node
    return await tap_fn(row["id"], snapshot_id)


# --- §5.4 type_text ----------------------------------------------------------


async def type_text(node_id: str, snapshot_id: int, text: str) -> dict:
    """REPLACE via ACTION_SET_TEXT; exige foco (sin focused -> NOT_FOCUSED)."""
    return await _ui.type_text(node_id, snapshot_id, text)


# --- §5.6/7 clipboard --------------------------------------------------------


async def get_clipboard(_run=None, _fallback_text: str | None = None) -> dict:
    """Lee el clipboard host (dumpsys) + verifica forma https?://."""
    return _clip.read_clipboard(_run=_run, _fallback_text=_fallback_text)


async def set_clipboard(text: str, _jam=None, _run=None) -> dict:
    """Escribe via Jam ClipboardManager + read-back de forma (§4.1)."""
    return await _clip.set_clipboard(text, _jam=_jam, _run=_run)


__all__ = [
    "resolve_element",
    "open_app",
    "close_app",
    "read_screen_state",
    "read_screen",
    "tap_idx",
    "type_text",
    "get_clipboard",
    "set_clipboard",
]
