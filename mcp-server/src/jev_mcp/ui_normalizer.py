"""Normalizer: árbol crudo de Jam (≤500 nodos) → ≤60 candidatos.

Cadena real: 500 raw (extractor: invisibles fuera + tope 500)
→ 60 (aquí: decoración/contenedores fuera + tope MAX_CANDIDATES=60)
⊂ 255 Choice (capacidad Jev: 254 + 1 NONE). El 254+NONE es capacidad,
no tope vigente (subir 60→254 pendiente Fase 5).

Reglas (AGENTS.md §5.10+):
1. Fuera decoración del sistema (statusBar/navBarBackground).
2. Los nodos ya vienen de la ventana activa (sin filtro por paquete:
   el extractor solo sirve la ventana en foco).
3. Fuera contenedores sin interacción propia.
4. Dentro: clickable, editable, scrollable o con texto/desc.
5. Tope 60, prioridad editable > clickable-con-texto > resto (estable).
6. Formato compacto `[n_42] EditText "Buscar"`.
"""
from __future__ import annotations

from .state import Candidate, NormalizedState

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

MAX_CANDIDATES = 60


def short_class(cls: str) -> str:
    return cls.rsplit(".", 1)[-1] if cls else "View"


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
              screen_h: int = 0) -> NormalizedState:
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
    )


def format_state(st: NormalizedState) -> str:
    head = f"{st.package} snap={st.snapshot_id} ({len(st.candidates)}/{st.raw_count})"
    return "\n".join([head, *st.compact_lines()])
