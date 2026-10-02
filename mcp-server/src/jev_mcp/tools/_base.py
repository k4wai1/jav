"""Base: conexión Jam con auto-forward + envolvente de respuesta."""
from __future__ import annotations

import os
import subprocess

from ..socket_client import JamClient, JamError

URL = os.environ.get("JEV_WS_URL", "ws://127.0.0.1:38472/")


def token() -> str:
    t = os.environ.get("JEV_TOKEN", "")
    if not t:
        raise SystemExit("Falta JEV_TOKEN en el entorno (ver ../.env.example)")
    return t


def ensure_forward() -> None:
    subprocess.run(["adb", "forward", "tcp:38472", "tcp:38472"],
                   capture_output=True, check=False)


async def jam_client() -> JamClient:
    """Conecta; si el forward falta, lo crea y reintenta una vez."""
    try:
        jam = JamClient(URL, token())
        await jam.__aenter__()
        return jam
    except (OSError, ConnectionRefusedError):
        ensure_forward()
        jam = JamClient(URL, token())
        await jam.__aenter__()
        return jam


def ok(verified: bool, evidence: dict, hint: str = "") -> dict:
    return {"ok": True, "verified": verified, "evidence": evidence, "hint": hint}


def fail(code: str, error: str, hint: str = "") -> dict:
    return {"ok": False, "verified": False,
            "evidence": {"code": code, "error": error}, "hint": hint}


def jam_fail(e: JamError) -> dict:
    hints = {
        "STALE_SNAPSHOT": "re-haz read_screen y usa el snapshot nuevo",
        "NOT_FOCUSED": "haz tap sobre el campo antes de type_text",
        "SELECTOR_NOT_FOUND": "re-haz read_screen; el selector no matchea",
        "ACCESSIBILITY_DISABLED": "habilita Jam en Ajustes → Accesibilidad",
        "SHIZUKU_UNAVAILABLE": "arranca Shizuku y reintenta",
        "TIMEOUT": "reintenta o sube el timeout",
    }
    return fail(e.code, e.error, hints.get(e.code, ""))
