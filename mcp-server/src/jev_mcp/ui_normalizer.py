"""Normalizer: árbol crudo de Jam (≤500 nodos) → ≤254 candidatos.

Cadena real: 500 raw (extractor: invisibles fuera + tope 500)
→ 254 (aquí: decoración/contenedores fuera + tope MAX_CANDIDATES=254)
⊂ 255 Choice (capacidad Jev: 254 + 1 NONE). Tope vigente = capacidad
(contrato generic-dual-tier §4: 0..253 + NONE = 255 Choice).

Reglas (AGENTS.md §5.10+):
1. Fuera decoración del sistema (statusBar/navBarBackground).
2. Los nodos ya vienen de la ventana activa (sin filtro por paquete:
   el extractor solo sirve la ventana en foco).
3. Fuera contenedores sin interacción propia.
4. Dentro: clickable, editable, scrollable o con texto/desc.
5. Tope 254, prioridad editable > clickable-con-texto > resto (estable).
6. Formato compacto `[n_42] EditText "Buscar"`.
"""
from __future__ import annotations

from .state import Candidate, FocusedField, NormalizedState

DECOR_SUBSTR = ("statusBarBackground", "navigationBarBackground")

CONTAINERS = {
    "android.widget.LinearLayout",
    "android.widget.FrameLayout",
    "android.widget.RelativeLayout",
    "android.view.ViewGroup",
    "android.widget.ListView",
    "android.widget.GridView",
    "android.widget.ScrollView",
    "androidx.recyclerview.widget.RecyclerView",
    "androidx.viewpager.widget.ViewPager",
}

MAX_CANDIDATES = 254

# Marcadores genéricos de secreto (clase/rid/hint/desc, case-insensitive).
# Sin literales de app: categorías de campo, no pantallas.
PASSWORD_MARKERS = ("password", "passwd", "passcode", "pin", "credential")

# Tope de `holds`: suficiente para desambiguar escrito-vs-enviado sin
# llevar PII larga al prompt.
HOLDS_MAX = 140


def short_class(cls: str) -> str:
    return cls.rsplit(".", 1)[-1] if cls else "View"


def _is_password(n: dict) -> bool:
    hay = (f"{n.get('class') or ''} {n.get('resource_id') or ''} "
           f"{n.get('hint') or ''} {n.get('content_desc') or ''}").lower()
    return any(m in hay for m in PASSWORD_MARKERS)


def _field_label(n: dict) -> str:
    text = (n.get("text") or "").strip()
    if text:
        return text
    desc = (n.get("content_desc") or "").strip()
    if desc:
        return desc
    rid = n.get("resource_id") or ""
    if "/" in rid:
        return rid.rsplit("/", 1)[-1]
    return n.get("id", "")


def the_focused_field(nodes: list[dict]) -> FocusedField | None:
    """Campo que recibiría typing + contenido actual (patrón A2, P0-1).

    Fuente: foco real de Accessibility vía `dump_ui`. Elegido = editable
    focuseado si hay; si no, primer editable (ruido menor, no mutación).
    Sin editables → None. Nunca inventa foco desde layout: solo lee flags
    reales. Password → marcada (el valor nunca sale: ver as_view).
    """
    editables = [n for n in nodes if n.get("editable")]
    if not editables:
        return None
    chosen = next((n for n in editables if n.get("focused")), editables[0])
    secret = _is_password(chosen)
    return FocusedField(
        label=_field_label(chosen),
        kind="password" if secret else "text",
        holds=(chosen.get("text") or "").strip()[:HOLDS_MAX],
        is_password=secret,
    )


def _keep(n: dict) -> bool:
    rid = n.get("resource_id") or ""
    if any(d in rid for d in DECOR_SUBSTR):
        return False
    text = (n.get("text") or "").strip()
    desc = (n.get("content_desc") or "").strip()
    cls = n.get("class") or ""
    interactive = bool(n.get("clickable") or n.get("editable") or n.get("scrollable"))
    if not interactive and not text and not desc:
        return False  # contenedor mudo (regla 3+4 en una)
    return True


def _rank(c: Candidate) -> int:
    if c.editable:
        return 0
    if c.clickable and (c.text or c.desc):
        return 1
    return 2


def normalize(dump: dict, limit: int = MAX_CANDIDATES,
              screen_h: int = 0, screen_w: int = 0) -> NormalizedState:
    nodes = dump.get("nodes", [])
    kept: list[Candidate] = []
    for n in nodes:
        if not _keep(n):
            continue
        b = n.get("bounds") or [0, 0, 0, 0]
        kept.append(Candidate(
            id=n.get("id", ""),
            cls=short_class(n.get("class") or ""),
            text=(n.get("text") or "").strip(),
            desc=(n.get("content_desc") or "").strip(),
            resource_id=n.get("resource_id") or "",
            clickable=bool(n.get("clickable")),
            editable=bool(n.get("editable")),
            focused=bool(n.get("focused")),
            scrollable=bool(n.get("scrollable")),
            visible=bool(n.get("visible", True)),
            bounds=(b[0], b[1], b[2], b[3]) if len(b) == 4 else (0, 0, 0, 0),
        ))
    kept.sort(key=_rank)  # estable: conserva orden BFS dentro de cada tier
    return NormalizedState(
        package=dump.get("package", ""),
        activity=dump.get("activity", ""),
        snapshot_id=dump.get("snapshot_id", -1),
        candidates=kept[:limit],
        raw_count=len(nodes),
        screen_height=screen_h,
        screen_width=screen_w,
        focused_field=the_focused_field(nodes),
    )


def format_state(st: NormalizedState) -> str:
    head = f"{st.package} snap={st.snapshot_id} ({len(st.candidates)}/{st.raw_count})"
    return "\n".join([head, *st.compact_lines()])
