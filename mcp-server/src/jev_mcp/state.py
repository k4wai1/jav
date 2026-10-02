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

    def compact(self) -> str:
        quoted = self.text or ""
        if quoted:
            return f'[{self.id}] {self.cls} "{quoted}"'
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

    def compact_lines(self) -> list[str]:
        return [c.compact() for c in self.candidates]
