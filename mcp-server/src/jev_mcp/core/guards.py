"""Compuertas deterministas (AGENTS.md §5.14-16). Puras, parametrizadas.

Mecanismo en core, datos en el plugin: el plugin pasa su `pattern` /
`verified` / `key`/`cands`/`snap`; core no conoce ninguna app.
"""
from __future__ import annotations

import re

FORBIDDEN_DEFAULT: str = r"reenviar|forward|compartir|share|eliminar|delete|borrar"


class InvalidAction(ValueError):
    """Clave Jev fuera de criteria o nodo desconocido.

    El plugin la traduce a `jev_client.JevHallucination` para preservar
    el contrato externo del loop.
    """


def is_forbidden(cand: dict, pattern: str = FORBIDDEN_DEFAULT) -> bool:
    t = f"{cand.get('desc') or ''} {cand.get('text') or ''}"
    return bool(re.search(pattern, t, re.I))


def check_stuck_same(action: dict, history: list, n: int = 2) -> dict | None:
    """Si (kind,node_id) == últimas n → abort STUCK_SAME. Puro."""
    if action.get("kind") not in ("tap_node", "type_text") or not action.get("node_id"):
        return None
    sig = (action["kind"], action["node_id"])
    prev = [(h.get("action", {}).get("kind"), h.get("action", {}).get("node_id"))
            for h in history[-n:]]
    if len(prev) == n and all(s == sig for s in prev):
        return {"kind": "abort", "key": action.get("key", ""),
                "code": "STUCK_SAME",
                "reason": f"misma acción {n + 1}× seguidas: {sig}"}
    return None


def require_verified(verified: bool, key: str, code: str) -> dict | None:
    """Si no verificado → abort {code} (NO_VERIFY/SEND_UNSAFE/...). Puro."""
    if verified:
        return None
    return {"kind": "abort", "key": key, "code": code,
            "reason": f"sin verificación previa ({code}); no se actúa"}


def guarded_action(key: str, cands: dict, snap: int, *,
                   forbidden: bool) -> dict | None:
    """Valida clave tap:/type:/done/abort contra cands+snapshot.

    None = pasa (el plugin construye la acción con sus datos);
    dict = abort FORBIDDEN_TARGET. Clave o nodo inválido →
    `InvalidAction` (el plugin la traduce a JevHallucination).
    Puro.
    """
    if key in ("abort", "done") or ":" not in key:
        if key not in ("abort", "done"):
            raise InvalidAction(f"clave fuera de criteria: {key}")
        if key == "done":
            return None
        return {"kind": "abort", "key": key, "code": "JEV_ABORT",
                "reason": "Jev eligió abort"}
    kind, nid = key.split(":", 1)
    if nid not in cands:
        raise InvalidAction(f"nodo {nid} no está en el estado")
    if kind not in ("tap", "type"):
        raise InvalidAction(f"acción desconocida: {kind}")
    if forbidden:
        label = (cands[nid] or {}).get("label", nid)
        return {"kind": "abort", "key": key, "code": "FORBIDDEN_TARGET",
                "reason": f"target prohibido: {label}"}
    _ = snap  # el snapshot lo estampa el plugin en la acción construida
    return None
