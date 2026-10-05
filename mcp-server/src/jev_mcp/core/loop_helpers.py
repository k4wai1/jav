"""Ayudas puras del loop generico (contrato generic-dual-tier §4 y §7).

Sin I/O y sin literales de dominio: poda determinista a tabla 0..253
(+NONE = 255 Choice), validaciones estructurales siempre aplicadas y
heuristica generica de acciones criticas/irreversibles.
"""
from __future__ import annotations

import hashlib

from ..ui_normalizer import PASSWORD_MARKERS

# 254 interactivos (indices 0..253) + 1 NONE = 255 Choice. Nunca se supera.
# plan-ahead v4 §4 + §9.5 (EXPERIMENT-TABLE-20 rechazado): el tope sigue en
# 254; cualquier poda agresiva exige protocolo A/B antes de tocarlo.
MAX_TABLE = 254

# Ancla espacial 3x3 (plan-ahead v4 §4, calculado en host desde bounds +
# resolución). Vocabulario normativo en inglés; `unknown` es fallback fuera
# de los 9 (sin resolución o bounds degenerados). Hint de desambiguación,
# nunca señal de seguridad.
ZONE_UNKNOWN = "unknown"
ZONE_VALUES = (
    "top-left", "top-center", "top-right",
    "mid-left", "mid-center", "mid-right",
    "bottom-left", "bottom-center", "bottom-right",
)

# Acciones elegibles para fast-path S1 (plan-ahead v4 §3.1). DONE y ESCALATE
# nunca son fast-path (gate S2 / vía S2 siempre).
FAST_ACTIONS = ("TAP", "TYPE", "SCROLL_DOWN", "SCROLL_UP", "BACK")


def zone_of(bounds: list | tuple | None,
            screen_w: int = 0, screen_h: int = 0) -> str:
    """Celda 3x3 en inglés desde centroide + resolución (puro, v4 §4).

    Corte por tercios en cada eje. Sin resolución (w/h <= 0) o bounds
    degenerados/ausentes → `unknown`. Nunca lanza.
    """
    try:
        w, h = int(screen_w or 0), int(screen_h or 0)
        if w <= 0 or h <= 0 or bounds is None or len(bounds) != 4:
            return ZONE_UNKNOWN
        left, top, right, bottom = (int(v) for v in bounds)
        if not (right > left and bottom > top and left >= 0 and top >= 0):
            return ZONE_UNKNOWN
        cx, cy = (left + right) / 2.0, (top + bottom) / 2.0
        col = "left" if cx < w / 3.0 else ("center" if cx < 2 * w / 3.0
                                          else "right")
        row = "top" if cy < h / 3.0 else ("mid" if cy < 2 * h / 3.0
                                         else "bottom")
        return f"{row}-{col}"
    except (TypeError, ValueError):
        return ZONE_UNKNOWN

# Read-back tras TYPE (patrón M2, P0-2): poll con timeout. Constantes
# nombradas e inyectables (confirm_input acepta override) para tests.
INPUT_TIMEOUT_MS = 2500
POLL_MS = 60

# Tope de `holds` en la vista del campo enfocado (igual que normalizer).
HOLDS_MAX = 140

# Valor enmascarado para secretos (nunca viaja ni se loguea el valor).
PASS_MASK = "a password, not read"

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


def _row_zone(c, bounds: list, screen_w: int = 0,
              screen_h: int = 0) -> str:
    """Zona precomputada si viaja en el candidato; si no, derivada pura."""
    if isinstance(c, dict) and c.get("zone") in ZONE_VALUES:
        return str(c["zone"])
    return zone_of(bounds, screen_w, screen_h)


def build_table(candidates: list, screen_w: int = 0,
                screen_h: int = 0) -> tuple[list[dict], dict[int, dict]]:
    """Poda a tabla numerada 0..253. Devuelve (rows, by_idx).

    Cada fila: {idx, id, label, text, resource_id, bounds, clickable,
    editable, focused, scrollable, visible, class_short, zone, flags}.
    Exceso >254: se conservan los primeros (el normalizer ya prioriza
    editables > clickables-con-texto > resto en orden BFS estable); el
    resto se alcanza por SCROLL + re-dump. `text`/`resource_id` viajan en
    la fila (no en la tabla serializada a S1) para verificación read-back.
    `zone` (v4 §4) se deriva de bounds + resolución; sin resolución →
    `unknown` (el loop la tolera; `validate_target` sigue mandando).
    """
    rows: list[dict] = []
    for i, c in enumerate(candidates[:MAX_TABLE]):
        if isinstance(c, dict):
            cid = c.get("id", f"n_{i}")
            label = c.get("label") or c.get("text") or c.get("desc") or cid
            bounds = c.get("bounds") or [0, 0, 0, 0]
            bounds = list(bounds) if len(bounds) == 4 else [0, 0, 0, 0]
            rows.append({
                "idx": i,
                "id": cid,
                "label": str(label),
                "text": str(c.get("text") or ""),
                "resource_id": str(c.get("resource_id") or ""),
                "bounds": bounds,
                "clickable": bool(c.get("clickable")),
                "editable": bool(c.get("editable")),
                "focused": bool(c.get("focused")),
                "scrollable": bool(c.get("scrollable")),
                "visible": bool(c.get("visible", True)),
                "class_short": _row_class_short(c),
                "zone": _row_zone(c, bounds, screen_w, screen_h),
                "flags": _row_flags(c),
            })
        else:  # Candidate dataclass
            bounds = list(getattr(c, "bounds", (0, 0, 0, 0)))
            rows.append({
                "idx": i,
                "id": getattr(c, "id", f"n_{i}"),
                "label": c.compact(),
                "text": str(getattr(c, "text", "") or ""),
                "resource_id": str(getattr(c, "resource_id", "") or ""),
                "bounds": bounds,
                "clickable": bool(getattr(c, "clickable", False)),
                "editable": bool(getattr(c, "editable", False)),
                "focused": bool(getattr(c, "focused", False)),
                "scrollable": bool(getattr(c, "scrollable", False)),
                "visible": bool(getattr(c, "visible", True)),
                "class_short": _row_class_short(c),
                "zone": _row_zone(c, bounds, screen_w, screen_h),
                "flags": _row_flags(c),
            })
    return rows, {r["idx"]: r for r in rows}


def serialize_table(rows: list[dict]) -> list[list]:
    """Filas enriquecidas para Jev: [idx, class_short, zone, flags, label].

    El `id` opaco y los `bounds` completos no viajan a Jev: quedan en
    `by_idx` del loop para validación estructural y ejecución.
    """
    return [[r["idx"], r.get("class_short", "View"),
             r.get("zone", ZONE_UNKNOWN),
             r.get("flags", EMPTY_FLAGS), r.get("label", "")]
            for r in rows]


def _row_secret(row: dict) -> bool:
    hay = (f"{row.get('class_short') or ''} {row.get('resource_id') or ''} "
           f"{row.get('label') or ''}").lower()
    return any(m in hay for m in PASSWORD_MARKERS)


def focused_field_view(rows_or_cands: list) -> dict:
    """Vista EN {label, holds} del campo enfocado (P0-1, puro).

    Acepta filas de build_table o candidatos crudos (dicts o Candidate).
    El loop la pasa a ask_decision; si read_screen ya trae
    `focused_field`, esa vale (viene del normalizer). Password → máscara,
    vacío/ausente → holds "empty". Sin mutación, sin literales de app.
    """
    first = rows_or_cands[0] if rows_or_cands else None
    if isinstance(first, dict) and "idx" in first:
        rows = rows_or_cands  # ya son filas de build_table
    else:
        rows, _ = build_table(list(rows_or_cands or []))
    editables = [r for r in (rows or []) if r.get("editable")]
    if not editables:
        return {"label": "none", "holds": "empty"}
    chosen = next((r for r in editables if r.get("focused")), editables[0])
    if _row_secret(chosen):
        return {"label": chosen.get("label") or chosen.get("id") or "none",
                "holds": PASS_MASK}
    text = (chosen.get("text") or "")[:HOLDS_MAX]
    if not text and chosen.get("label"):
        text = str(chosen["label"])[:HOLDS_MAX]
    return {"label": chosen.get("label") or chosen.get("id") or "none",
            "holds": text if text else "empty"}


def prepare_input_verification(row: dict | None, text: str) -> dict | None:
    """Target exact-span para read-back tras TYPE (patrón M2, P0-2).

    None si no-editable / password / texto vacío (no verificable: el
    loop aborta input_unverified en vez de retypear a ciegas).
    Si no: {target: {id, resource_id, hint, bounds}, text}.
    """
    if not isinstance(row, dict) or not row.get("editable"):
        return None
    if not text or _row_secret(row):
        return None
    return {"target": {
                "id": row.get("id", ""),
                "resource_id": row.get("resource_id", "") or "",
                "hint": str(row.get("label", "") or ""),
                "bounds": list(row.get("bounds") or [0, 0, 0, 0]),
            },
            "text": text}


def input_matches(candidates: list, verification: dict) -> bool:
    """Exact-span: misma identidad Y text==esperado en exactamente 1 (M2).

    Identidad = mismo resource_id estable, o fallback id+hint+bounds si
    no hay rid. `candidates`: dicts crudos post-observe (con text,
    resource_id, id, label, bounds).
    """
    target = (verification or {}).get("target", {})
    want = (verification or {}).get("text", "")
    tid, trid = target.get("id", ""), target.get("resource_id", "")
    thint, tbounds = target.get("hint", ""), list(target.get("bounds") or [])
    hits = 0
    for c in candidates or []:
        if not isinstance(c, dict):
            continue
        rid = c.get("resource_id", "") or ""
        same = bool(trid and rid and rid == trid)
        if not same and not trid:
            same = (c.get("id") == tid
                    and str(c.get("label", "") or "") == thint
                    and list(c.get("bounds") or []) == tbounds)
        if same and (c.get("text", "") or "") == want:
            hits += 1
    return hits == 1


async def confirm_input(verification: dict, observe_fn,
                        timeout_ms: int = INPUT_TIMEOUT_MS,
                        poll_ms: int = POLL_MS) -> tuple[bool, dict]:
    """Poll read-back hasta inputMatches o timeout (M2, P0-2). Sin retype.

    observe_fn: async () -> state-dict con candidates. Devuelve
    (ok, {snapshot, attempts}). Fallo de lectura = no-match transitorio
    (sigue poll hasta timeout); timeout → (False, ...) y el loop cierra
    input_unverified SIN segundo type_text.
    """
    import asyncio
    import time

    t0 = time.monotonic()
    attempts = 0
    last_snap = -1
    while True:
        try:
            st = await observe_fn()
        except Exception:
            st = None
        if isinstance(st, dict):
            last_snap = st.get("snapshot_id", last_snap)
            if input_matches(st.get("candidates", []), verification):
                return True, {"snapshot": last_snap, "attempts": attempts}
        attempts += 1
        if (time.monotonic() - t0) * 1000 >= timeout_ms:
            return False, {"snapshot": last_snap, "attempts": attempts}
        await asyncio.sleep(max(poll_ms, 1) / 1000)


def screen_fingerprint(candidates: list) -> str:
    """Firma de pantalla por contenido (id+texto, ordenada, sha256).

    Puro y genérico. El loop la usa como before/after en forense P0-2
    (P1-5 la endurecerá ignorando tickers).
    """
    parts = []
    for c in candidates or []:
        if isinstance(c, dict):
            parts.append((str(c.get("id", "")),
                          str(c.get("text", "") or c.get("label", ""))))
        else:
            parts.append((str(getattr(c, "id", "")),
                          str(getattr(c, "text", "") or "")))
    raw = "|".join(f"{i}={t}" for i, t in sorted(parts))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


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
