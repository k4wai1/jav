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
    # Núcleo canónico (no tocar: compatibilidad forense) + extensión
    # guía §3.2 (v1). Todo fallo sale con hint imperativo (nunca vacío).
    hints = {
        "STALE_SNAPSHOT": "re-haz read_screen y usa el snapshot nuevo",
        "NOT_FOCUSED": "haz tap sobre el campo antes de type_text",
        "SELECTOR_NOT_FOUND": "re-haz read_screen; el selector no matchea",
        "ACCESSIBILITY_DISABLED": "habilita Jam en Ajustes → Accesibilidad",
        "SHIZUKU_UNAVAILABLE": "arranca Shizuku y reintenta",
        "TIMEOUT": "reintenta o sube el timeout",
        "SECURE_SURFACE": "la ventana tiene FLAG_SECURE; usa dump_ui, no screenshot",
        "PAYLOAD_TOO_LARGE": "reintenta con fmt webp y quality 80",
        "METHOD_NOT_ALLOWED": "metodo no disponible en esta fase; no reintentes igual",
        "UNAUTHORIZED": "revisa JAV_TOKEN en el entorno del servidor",
        "SHIZUKU_DENIED": "concede el permiso runtime de Shizuku a Jam y reintenta",
        "FORBIDDEN": "pide scope/permiso correspondiente; no reintentes el mismo payload",
        "VALIDATION_ERROR": "revisa los parametros de la tool (forma, enum, rangos, unidades)",
        "INTENT_UNRESOLVED": "elige otra app destino o abre sin package (chooser) y verifica",
        "PACKAGE_NOT_FOUND": ("verifica el paquete con list_packages; "
                              "el paquete lo aporta el operador, no lo adivines"),
        "CLIPBOARD_EMPTY": ("copia primero en la app-origen y re-lee "
                            "(host dumpsys o pegado-readback); no inventes contenido"),
        "UI_UNSTABLE": ("para: dif de forenses + informe "
                        "(firma igual en 2 corridas = no relanzar)"),
        "VERIFY_FAILED": ("confirma con get_foreground/read_screen; "
                          "si no llegó, un reintento y luego informe"),
        "CONNECTION_FAILED": ("revisa adb forward + dispositivo conectado; "
                              "reintenta una vez tras forward"),
        "RATE_LIMITED": "espera y reintenta con backoff; segundo cliente recibe BUSY",
        "BUSY": "espera y reintenta con backoff; segundo cliente recibe BUSY",
        "SHELL_DENIED": ("pide grant en el dispositivo (1 comando/5 min/30 min); "
                         "denylist exige admin + confirm:true"),
        "SHELL_DENYLIST": ("pide grant en el dispositivo (1 comando/5 min/30 min); "
                           "denylist exige admin + confirm:true"),
    }
    _grant = ("concede el acceso en el dispositivo (estado visible en hello.caps) "
              "y reintenta; sin grant, error honesto")
    for _c in ("USAGE_ACCESS_DISABLED", "CONTACTS_PERMISSION_DENIED",
               "CALENDAR_PERMISSION_DENIED", "NOTIFICATION_LISTENER_DISABLED",
               "MEDIA_SESSIONS_UNAVAILABLE", "LOCATION_PERMISSION_DENIED",
               "CAMERA_DENIED", "WRITE_SETTINGS_DISABLED"):
        hints[_c] = _grant
    _dst = ("re-observe el destino (lista/sesiones/permiso) y decide de nuevo; "
            "nunca inventes el efecto")
    for _c in ("NOTIFICATION_GONE", "NO_REMOTE_INPUT", "REPLY_FAILED",
               "MEDIA_SESSION_GONE", "MEDIA_CONTROL_FAILED",
               "LOCATION_UNAVAILABLE", "LOCATION_TIMEOUT",
               "CAMERA_UNAVAILABLE", "CAMERA_FAILED",
               "SETTINGS_PUT_FAILED", "CALENDAR_UNAVAILABLE", "INTENT_FAILED"):
        hints[_c] = _dst
    return fail(e.code, e.error, hints.get(
        e.code,
        "revisa evidence.code/error y re-observe el estado antes de "
        "reintentar (nunca reintentes el mismo payload a ciegas)"))
