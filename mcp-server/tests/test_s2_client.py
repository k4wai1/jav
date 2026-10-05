"""S2 null-content: retry + S2_EMPTY_RESPONSE tipado (genérico, sin app)."""
import pytest

from jev_mcp import s2_client


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class _Client:
    """Fake httpx.AsyncClient con secuencia de payloads; cuenta POSTs."""
    seq = []
    calls = 0

    def __init__(self, *a, **kw):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, *a, **kw):
        type(self).calls += 1
        idx = min(type(self).calls - 1, len(type(self).seq) - 1)
        return _Resp(type(self).seq[idx])


def _patch(monkeypatch, seq):
    _Client.seq = seq
    _Client.calls = 0
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(s2_client.httpx, "AsyncClient", _Client)


def _null_payload():
    return {"choices": [{"message": {"content": None}}], "usage": {}}


def _ok_payload():
    return {"choices": [{"message": {"content": '{"command": "HINT", "guidance_for_s1": "re-observe the screen", "stop": false}'}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5}}


@pytest.mark.asyncio
async def test_null_content_retries_then_s2_empty_response(monkeypatch):
    """content null persistente → 1 reintento (2 POSTs) → S2EmptyResponse."""
    _patch(monkeypatch, [_null_payload(), _null_payload()])
    with pytest.raises(s2_client.S2EmptyResponse) as ei:
        await s2_client.advise("goal", reason="LOW_CONF", table_lines=[])
    assert ei.value.code == "S2_EMPTY_RESPONSE"
    assert _Client.calls == 2


@pytest.mark.asyncio
async def test_null_then_ok_recovers_on_retry(monkeypatch):
    """null transitorio → reintento recupera comando (2 POSTs, sin excepción)."""
    _patch(monkeypatch, [_null_payload(), _ok_payload()])
    out, usage = await s2_client.advise("goal", reason="LOW_CONF",
                                        table_lines=[])
    assert out["command"] == "HINT"
    assert out["guidance_for_s1"] == "re-observe the screen"
    assert usage == {"in_tokens": 10, "out_tokens": 5}
    assert _Client.calls == 2


def test_parse_command_open_app_valida_forma():
    out = s2_client.parse_command({"command": "OPEN_APP",
                                   "package": "com.example.messenger",
                                   "guidance_for_s1": "App is open.",
                                   "stop": False})
    assert out["package"] == "com.example.messenger"
    assert out["target"] == "NONE"
    with pytest.raises(s2_client.S2BadCommand):
        s2_client.parse_command({"command": "OPEN_APP", "package": "sin-puntos"})
    with pytest.raises(s2_client.S2BadCommand):
        s2_client.parse_command({"command": "TYPE", "text": ""})
    with pytest.raises(s2_client.S2BadCommand):
        s2_client.parse_command({"command": "TAPEAR"})
    with pytest.raises(s2_client.S2BadCommand):
        s2_client.parse_command({"command": "TYPE", "text": "hi",
                                 "target": 999})


@pytest.mark.asyncio
async def test_garbage_without_braces_retries_then_empty(monkeypatch):
    """sin {...} parseable persistente → 2 POSTs → S2EmptyResponse."""
    bad = {"choices": [{"message": {"content": "sin json"}}], "usage": {}}
    _patch(monkeypatch, [bad, bad])
    with pytest.raises(s2_client.S2EmptyResponse):
        await s2_client.advise("goal", reason="x", table_lines=[])
    assert _Client.calls == 2


@pytest.mark.asyncio
async def test_loop_traduce_empty_a_s2_unavailable_con_hint():
    """El loop traduce S2EmptyResponse → S2_UNAVAILABLE + hint reintento."""
    from jev_mcp import loop as _loop

    async def _obs():
        return {"package": "p", "activity": "a", "snapshot_id": 1,
                "screen_height": 1600, "candidates": [], "raw_count": 0}

    async def _dec(goal, rows, snapshot, history_summary="",
                   s2_guidance="", current_app="", screen_goal=""):
        return ({"action": "ESCALATE", "target": "NONE",
                 "needs_system_2": False, "conf": 0.61, "type_text": ""},
                {"in_tokens": 10, "out_tokens": 1})

    async def _adv(goal, reason="", table_lines=None,
                   history_summary="", need_text=False,
                   current_app="", screen_goal=""):
        raise s2_client.S2EmptyResponse("content None o vacío")

    async def _exe(action):
        raise AssertionError("ESCALATE nunca ejecuta")

    r = await _loop.run_goal("goal genérico", _observe=_obs, _decide=_dec,
                             _advise=_adv, _execute_fn=_exe)
    assert not r["ok"] and r["evidence"]["code"] == "S2_UNAVAILABLE", r
    assert "S2_EMPTY_RESPONSE" in r["evidence"]["error"], r
    assert r["hint"] == "reintentar: null-content transitorio de S2", r
