"""Tipos del estado semántico (lo que ve Jev / el agente)."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Candidate:
    id: str
    cls: str          # clase corta: "EditText", "Button", ...
    text: str = ""
    desc: str = ""
    resource_id: str = ""
    clickable: bool = False
    editable: bool = False
    focused: bool = False  # Fase 5: type exige foco explícito
    scrollable: bool = False  # generic-dual-tier §4: flag `scroll`
    visible: bool = True  # validación estructural del loop
    bounds: tuple[int, int, int, int] = (0, 0, 0, 0)  # l,t,r,b (Fase 5: título)

    @property
    def class_short(self) -> str:
        """La clase ya se guarda corta; fallback `View`."""
        return self.cls or "View"

    @property
    def flags(self) -> str:
        """Subset ordenado `click|edit|foc|scroll`; vacío = `—`."""
        parts = []
        if self.clickable:
            parts.append("click")
        if self.editable:
            parts.append("edit")
        if self.focused:
            parts.append("foc")
        if self.scrollable:
            parts.append("scroll")
        return "|".join(parts) if parts else "—"

    def compact(self) -> str:
        focus = " (focused)" if (self.editable and self.focused) else ""
        quoted = self.text or ""
        if quoted:
            return f'[{self.id}] {self.cls} "{quoted}"{focus}'
        if self.desc:
            return f'[{self.id}] {self.cls} desc="{self.desc}"'
        rid = self.resource_id.split("/")[-1] if self.resource_id else ""
        return f"[{self.id}] {self.cls} id={rid}" if rid else f"[{self.id}] {self.cls}"


@dataclass
class NormalizedState:
    package: str
    activity: str
    snapshot_id: int
    candidates: list[Candidate] = field(default_factory=list)
    raw_count: int = 0
    screen_height: int = 0  # Fase 5: fallback posicional del título

    def compact_lines(self) -> list[str]:
        return [c.compact() for c in self.candidates]
