"""Compuertas deterministas genericas (contrato generic-dual-tier §7).

Puras y sin I/O. Cero literales de dominio: el default global de
prohibidos esta eliminado; el filtrado es opt-in por goal via `pattern`
explicito del operador. Sin pattern declarado no hay filtro.
"""
from __future__ import annotations

import re


class InvalidAction(ValueError):
    """Clave de decision fuera del enum o nodo desconocido.

    El loop la traduce a fallo honesto (JEV_HALLUCINATION); nunca se actua.
    """


def is_forbidden(cand: dict, pattern: str | None = None) -> bool:
    """Opt-in por goal: sin `pattern` declarado -> False (sin filtro).

    Con pattern, matchea regex (case-insensitive) contra text+desc del
    candidato. El operador declara sus patrones si el goal lo exige.
    """
    if not pattern:
        return False
    t = f"{cand.get('desc') or ''} {cand.get('text') or ''}"
    try:
        return bool(re.search(pattern, t, re.I))
    except re.error:
        return False


def check_stuck_same(action: dict, history: list, n: int = 2) -> dict | None:
    """Si (kind,node_id) == ultimas n -> abort STUCK_SAME. Puro."""
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
    """Si no verificado -> abort {code}. Puro."""
    if verified:
        return None
    return {"kind": "abort", "key": key, "code": code,
            "reason": f"sin verificación previa ({code}); no se actúa"}


def guarded_action(key: str, cands: dict, snap: int, *,
                   forbidden: bool) -> dict | None:
    """Valida clave tap:/type:/done/abort/escalate contra cands+snapshot.

    None = pasa; dict = abort FORBIDDEN_TARGET / abort JEV_ABORT.
    `forbidden` es booleano explicito ya resuelto por el llamante
    (via is_forbidden con pattern opt-in). Clave o nodo invalido ->
    `InvalidAction`. Puro.
    """
    if key in ("abort", "done", "escalate") or ":" not in key:
        if key not in ("abort", "done", "escalate"):
            raise InvalidAction(f"clave fuera de criteria: {key}")
        if key in ("done", "escalate"):
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
    _ = snap  # el snapshot lo estampa el llamante en la acción construida
    return None


def gate_tau(conf: float, tau: float) -> dict | None:
    """Si conf < tau -> {kind: escalate, reason: LOW_CONF}. Puro.

    El valor de `tau` es constante del loop (TAU = 0.70 por contrato).
    Conf/tau no numéricos -> escalado conservador.
    """
    try:
        c = float(conf)
        t = float(tau)
    except (TypeError, ValueError):
        return {"kind": "escalate", "reason": "LOW_CONF",
                "conf": conf, "tau": tau}
    if c < t:
        return {"kind": "escalate", "reason": "LOW_CONF",
                "conf": c, "tau": t}
    return None
