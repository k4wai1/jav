"""Ayudas puras del loop generico (contrato generic-dual-tier §4 y §7).

Sin I/O y sin literales de dominio: poda determinista a tabla 0..253
(+NONE = 255 Choice), validaciones estructurales siempre aplicadas y
heuristica generica de acciones criticas/irreversibles.
"""
from __future__ import annotations

# 254 interactivos (indices 0..253) + 1 NONE = 255 Choice. Nunca se supera.
MAX_TABLE = 254

DECISION_ACTIONS = ("TAP", "TYPE", "SCROLL_DOWN", "SCROLL_UP",
                    "BACK", "DONE", "ESCALATE")

# Flags compactos de la tabla enriquecida (§4): subset ordenado,
# `|`-separado; vacío = `—`. Derivación pura, sin literales de app.
EMPTY_FLAGS = "—"

# Verbos genericos de categorias criticas/irreversibles (§7.2):
# comunicar a terceros, comprar/pagar, borrar datos, cuenta/permisos.
# Genericos, no de ninguna app; el operador puede ampliar por goal.
SENSITIVE_VERBS = (
    "enviar", "send", "mandar",
    "comprar", "buy", "pagar", "pay", "pago",
    "borrar", "eliminar", "delete", "suprimir",
    "cuenta", "account", "permiso", "permission",
)


def short_class(cls: str) -> str:
    """Último segmento de la clase Android (`Button`, `EditText`, …).

    Desconocida o vacía → `View`. Derivación pura, sin literales de app.
    """
    short = (cls or "").rsplit(".", 1)[-1].strip()
    return short or "View"


def row_flags(*, clickable: bool = False, editable: bool = False,
              focused: bool = False, scrollable: bool = False) -> str:
    """Subset ordenado y compacto: `click|edit|foc|scroll`; vacío = `—`."""
    parts = []
    if clickable:
        parts.append("click")
    if editable:
        parts.append("edit")
    if focused:
        parts.append("foc")
    if scrollable:
        parts.append("scroll")
    return "|".join(parts) if parts else EMPTY_FLAGS


def _row_class_short(c) -> str:
    if isinstance(c, dict):
        for k in ("class_short", "cls", "class"):
            if c.get(k):
                return short_class(str(c[k]))
        return "View"
    return short_class(str(getattr(c, "cls", "") or ""))


def _row_flags(c) -> str:
    if isinstance(c, dict) and c.get("flags"):
        return str(c["flags"])
    if isinstance(c, dict):
        return row_flags(clickable=bool(c.get("clickable")),
                         editable=bool(c.get("editable")),
                         focused=bool(c.get("focused")),
                         scrollable=bool(c.get("scrollable")))
    return row_flags(clickable=bool(getattr(c, "clickable", False)),
                     editable=bool(getattr(c, "editable", False)),
                     focused=bool(getattr(c, "focused", False)),
                     scrollable=bool(getattr(c, "scrollable", False)))


def build_table(candidates: list) -> tuple[list[dict], dict[int, dict]]:
    """Poda a tabla numerada 0..253. Devuelve (rows, by_idx).

    Cada fila: {idx, id, label, bounds, clickable, editable, focused,
    scrollable, visible, class_short, flags}. Exceso >254: se conservan
    los primeros (el normalizer ya prioriza editables >
    clickables-con-texto > resto en orden BFS estable); el resto se
    alcanza por SCROLL + re-dump.
    """
    rows: list[dict] = []
    for i, c in enumerate(candidates[:MAX_TABLE]):
        if isinstance(c, dict):
            cid = c.get("id", f"n_{i}")
            label = c.get("label") or c.get("text") or c.get("desc") or cid
            bounds = c.get("bounds") or [0, 0, 0, 0]
            rows.append({
                "idx": i,
                "id": cid,
                "label": str(label),
                "bounds": list(bounds) if len(bounds) == 4 else [0, 0, 0, 0],
                "clickable": bool(c.get("clickable")),
                "editable": bool(c.get("editable")),
                "focused": bool(c.get("focused")),
                "scrollable": bool(c.get("scrollable")),
                "visible": bool(c.get("visible", True)),
                "class_short": _row_class_short(c),
                "flags": _row_flags(c),
            })
        else:  # Candidate dataclass
            rows.append({
                "idx": i,
                "id": getattr(c, "id", f"n_{i}"),
                "label": c.compact(),
                "bounds": list(getattr(c, "bounds", (0, 0, 0, 0))),
                "clickable": bool(getattr(c, "clickable", False)),
                "editable": bool(getattr(c, "editable", False)),
                "focused": bool(getattr(c, "focused", False)),
                "scrollable": bool(getattr(c, "scrollable", False)),
                "visible": bool(getattr(c, "visible", True)),
                "class_short": _row_class_short(c),
                "flags": _row_flags(c),
            })
    return rows, {r["idx"]: r for r in rows}


def serialize_table(rows: list[dict]) -> list[list]:
    """Filas enriquecidas para Jev: [idx, class_short, flags, label].

    El `id` opaco y los `bounds` completos no viajan a Jev: quedan en
    `by_idx` del loop para validación estructural y ejecución.
    """
    return [[r["idx"], r.get("class_short", "View"),
             r.get("flags", EMPTY_FLAGS), r.get("label", "")]
            for r in rows]


def check_decision_json(dec: dict) -> dict | None:
    """JSON de decision valido contra el enum S1. None = valida.

    Esperado: {action, target (int|"NONE"), needs_system_2 (bool),
    conf (float 0..1), [type_text]}. Fallo -> JEV_HALLUCINATION.
    """
    if not isinstance(dec, dict):
        return {"code": "JEV_HALLUCINATION",
                "error": f"decisión no es objeto: {type(dec).__name__}"}
    action = dec.get("action")
    if action not in DECISION_ACTIONS:
        return {"code": "JEV_HALLUCINATION",
                "error": f"action fuera del enum: {action!r}"}
    target = dec.get("target")
    if not (target == "NONE" or isinstance(target, int)):
        return {"code": "JEV_HALLUCINATION",
                "error": f"target inválido (int|NONE): {target!r}"}
    if isinstance(target, int) and not (0 <= target <= MAX_TABLE - 1):
        return {"code": "JEV_HALLUCINATION",
                "error": f"target fuera de 0..{MAX_TABLE - 1}: {target}"}
    try:
        conf = float(dec.get("conf"))
    except (TypeError, ValueError):
        return {"code": "JEV_HALLUCINATION",
                "error": f"conf no numérico: {dec.get('conf')!r}"}
    if not 0.0 <= conf <= 1.0:
        return {"code": "JEV_HALLUCINATION",
                "error": f"conf fuera de [0,1]: {conf}"}
    if not isinstance(dec.get("needs_system_2", False), bool):
        return {"code": "JEV_HALLUCINATION",
                "error": "needs_system_2 no es bool"}
    return None


def validate_target(row: dict | None, screen_h: int = 0) -> dict | None:
    """Validacion estructural del target antes de mutar. None = pasa.

    Exige: fila presente en el snapshot vigente, visible y con
    coordenadas dentro de pantalla (no degeneradas). Fallo ->
    SELECTOR_NOT_FOUND honesto, sin tocar el dispositivo.
    """
    if row is None:
        return {"code": "SELECTOR_NOT_FOUND",
                "error": "target NONE o ausente en la tabla vigente"}
    if not row.get("visible", True):
        return {"code": "SELECTOR_NOT_FOUND",
                "error": f"nodo {row.get('id')} no visible en snapshot vigente"}
    b = row.get("bounds") or [0, 0, 0, 0]
    if len(b) != 4:
        return {"code": "SELECTOR_NOT_FOUND",
                "error": f"bounds inválidos en {row.get('id')}: {b}"}
    l, t, r, bb = (int(v) for v in b)
    if not (r > l and bb > t and l >= 0 and t >= 0):
        return {"code": "SELECTOR_NOT_FOUND",
                "error": f"coordenadas fuera de pantalla en {row.get('id')}: {b}"}
    if screen_h and not (t < screen_h and l < 4096):
        return {"code": "SELECTOR_NOT_FOUND",
                "error": f"nodo {row.get('id')} fuera de pantalla: {b}"}
    return None


def is_sensitive(goal: str, target_label: str = "") -> bool:
    """Heuristica generica de accion critica/irreversible (§7.2).

    Matchea verbos de categoria (comunicar/comprar/borrar/cuenta) en el
    goal o en la etiqueta del target. Sin confirm:true del operador, el
    loop planea sin ejecutar.
    """
    hay = f"{goal or ''} {target_label or ''}".lower()
    return any(v in hay for v in SENSITIVE_VERBS)


def centroid(bounds: list) -> tuple[int, int]:
    l, t, r, b = (int(v) for v in bounds)
    return ((l + r) // 2, (t + b) // 2)
