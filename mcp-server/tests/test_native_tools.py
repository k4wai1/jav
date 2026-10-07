"""Tests native-apis (con stubs, sin Jam): envolvente, latencia, planned y N2."""
import pytest

from jev_mcp.socket_client import JamError
from jev_mcp.tools import native as N


def _ok(result):
    async def call(method, params):
        _ok.last = (method, params)
        return result
    return call


def _err(code, error="x"):
    async def call(method, params):
        raise JamError(code, error)
    return call


@pytest.mark.asyncio
async def test_n0_read_envelope_latency():
    d = await N.get_battery(_call=_ok({"level_pct": 77, "charging": False}))
    assert d["ok"] and d["verified"]
    assert d["evidence"]["level_pct"] == 77
    assert "latency_ms" in d["evidence"]
    assert _ok is not None
    assert N.__name__.endswith("native")


@pytest.mark.asyncio
async def test_n0_params_forwarded():
    seen = {}

    async def call(method, params):
        seen.update({"m": method, "p": params})
        return {"found": True}

    d = await N.settings_get("system", "screen_brightness", _call=call)
    assert d["ok"]
    assert (seen["m"], seen["p"]) == (
        "settings_get", {"namespace": "system", "key": "screen_brightness"})


@pytest.mark.asyncio
async def test_app_usage_window_forwarded():
    seen = {}

    async def call(method, params):
        seen.update({"m": method, "p": params})
        return {"window": "week", "count": 0, "apps": []}

    d = await N.get_app_usage(window="week", _call=call)
    assert d["ok"]
    assert seen == {"m": "get_app_usage", "p": {"hours": 24, "window": "week"}}
    # sin window, el contrato previo se mantiene (hours explícito)
    await N.get_app_usage(hours=12, _call=call)
    assert seen["p"] == {"hours": 12, "window": None}


@pytest.mark.asyncio
async def test_open_url_package_forwarded():
    seen = {}

    async def call(method, params):
        seen.update({"m": method, "p": params})
        return {"url": "https://youtu.be/x", "via": "startActivity-package",
                "package": "com.google.android.youtube"}

    d = await N.open_url("https://youtu.be/x",
                         package="com.google.android.youtube", _call=call)
    assert d["ok"] and d["verified"]
    assert seen == {"m": "open_url",
                    "p": {"url": "https://youtu.be/x",
                          "package": "com.google.android.youtube"}}
    assert d["evidence"]["package"] == "com.google.android.youtube"
    # sin package: comportamiento previo (resolver del sistema)
    await N.open_url("https://x.test/a", _call=call)
    assert seen["p"] == {"url": "https://x.test/a", "package": ""}


@pytest.mark.asyncio
async def test_planned_not_verified():
    d = await N.send_intent("android.intent.action.SEND", _call=_ok({"planned": True}))
    assert d["ok"] and not d["verified"]


@pytest.mark.asyncio
async def test_n2_stub_propagates():
    d = await N.settings_put("secure", "adb_enabled", "1",
                             confirm=True, _call=_err("METHOD_NOT_ALLOWED", "Fase 6"))
    assert not d["ok"]
    assert d["evidence"]["code"] == "METHOD_NOT_ALLOWED"
    assert "latency_ms" in d["evidence"]


@pytest.mark.asyncio
async def test_pii_forense_no_raw_leak_shape():
    contacts = {"returned": 2, "contacts": [
        {"id": 1, "display_name": "A"}, {"id": 2, "display_name": "B"}]}
    d = await N.list_contacts(_call=_ok(contacts))
    assert d["ok"]
    f = d["evidence"]["forense"]
    assert f["count"] == 2 and len(f["sha256"]) == 64
    assert "A" not in f.values() and "B" not in f.values()


@pytest.mark.asyncio
async def test_denied_honest():
    d = await N.list_notifications(_call=_err("NOTIFICATION_LISTENER_DISABLED", "habilita"))
    assert not d["ok"]
    assert d["evidence"]["code"] == "NOTIFICATION_LISTENER_DISABLED"


@pytest.mark.asyncio
async def test_take_photo_planned_shape():
    d = await N.take_photo(confirm=False, _call=_ok({"planned": True, "preview": {}}))
    assert d["ok"] and not d["verified"]
