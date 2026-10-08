"""Guía MCP_SPEC_GUIDELINES §2-§3: §6+§7 en las 35 descripciones y
recovery_instruction (hint imperativo, nunca vacío) en todo error."""
import asyncio

from jev_mcp.server import mcp
from jev_mcp.socket_client import JamError
from jev_mcp.tools import _base as B

TABLE_CODES = [
    "STALE_SNAPSHOT", "NOT_FOCUSED", "SELECTOR_NOT_FOUND", "TIMEOUT",
    "ACCESSIBILITY_DISABLED", "SHIZUKU_UNAVAILABLE", "SHIZUKU_DENIED",
    "UNAUTHORIZED", "FORBIDDEN", "METHOD_NOT_ALLOWED", "VALIDATION_ERROR",
    "SECURE_SURFACE", "PAYLOAD_TOO_LARGE", "INTENT_UNRESOLVED",
    "PACKAGE_NOT_FOUND", "CLIPBOARD_EMPTY", "UI_UNSTABLE", "VERIFY_FAILED",
    "CONNECTION_FAILED", "RATE_LIMITED", "BUSY", "SHELL_DENIED",
    "SHELL_DENYLIST", "USAGE_ACCESS_DISABLED", "CONTACTS_PERMISSION_DENIED",
    "CALENDAR_PERMISSION_DENIED", "NOTIFICATION_LISTENER_DISABLED",
    "MEDIA_SESSIONS_UNAVAILABLE", "LOCATION_PERMISSION_DENIED",
    "CAMERA_DENIED", "WRITE_SETTINGS_DISABLED", "NOTIFICATION_GONE",
    "NO_REMOTE_INPUT", "REPLY_FAILED", "MEDIA_SESSION_GONE",
    "MEDIA_CONTROL_FAILED", "LOCATION_UNAVAILABLE", "LOCATION_TIMEOUT",
    "CAMERA_UNAVAILABLE", "CAMERA_FAILED", "SETTINGS_PUT_FAILED",
    "CALENDAR_UNAVAILABLE", "INTENT_FAILED",
]


def _tools():
    return {t.name: t for t in asyncio.run(mcp.list_tools())}


def test_35_tools_con_secciones_6_y_7():
    tools = _tools()
    assert len(tools) == 35, sorted(tools)
    for name, t in sorted(tools.items()):
        d = t.description or ""
        assert "Cuándo NO usar" in d, name
        assert "Ejemplo" in d, name
        # §6 nombra alternativa exacta (forma NO … → usa …)
        assert "→ usa" in d or "→ " in d, name


def test_descripciones_sin_literales_de_dominio():
    tools = _tools()
    for name, t in sorted(tools.items()):
        d = (t.description or "").lower()
        for lit in ("whatsapp", "contact_name", "verify_chat", "wrong_chat",
                    "api_key", "sk-", "gmail", "telegram"):
            assert lit not in d, f"{name}: literal {lit}"


def test_jam_fail_toda_la_tabla_con_hint_imperativo():
    for code in TABLE_CODES:
        d = B.jam_fail(JamError(code, "detalle"))
        assert d["ok"] is False
        assert d["verified"] is False
        assert d["evidence"]["code"] == code
        hint = d["hint"]
        assert isinstance(hint, str) and hint.strip(), code


def test_jam_fail_codigo_desconocido_hint_generico_no_vacio():
    d = B.jam_fail(JamError("FUTURE_CODE_X", "detalle"))
    assert d["hint"].strip(), "prohibido hint vacío"
