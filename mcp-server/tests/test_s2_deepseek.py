"""S2 provider conmutable openrouter|deepseek (genérico, sin app).

Cubre: default openrouter (sin romper), dispatch deepseek por env,
endpoint/modelo/headers DeepSeek, mismo esquema de comandos +
verify_done, mismo retry S2EmptyResponse, PII enmascarada, S2 sin
tocar dispositivo (solo comandos), CostTracker con DEEPSEEK_RATE_*.
HTTP mockeado; sin red real; sin literales de dominio.
"""
import pytest

from jev_mcp import cost_tracker as CT
from jev_mcp import s2_client


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class _CaptureClient:
    seq = []
    calls = 0
    last_url = None
    last_headers = None
    last_json = None

    def __init__(self, *a, **kw):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, headers=None, json=None):
        type(self).calls += 1
        type(self).last_url = url
        type(self).last_headers = dict(headers or {})
        type(self).last_json = dict(json or {})
        idx = min(type(self).calls - 1, len(type(self).seq) - 1)
        return _Resp(type(self).seq[idx])


def _patch(monkeypatch, seq, env):
    _CaptureClient.seq = seq
    _CaptureClient.calls = 0
    _CaptureClient.last_url = None
    _CaptureClient.last_headers = None
    _CaptureClient.last_json = None
    for k in ("S2_PROVIDER", "DEEPSEEK_API_KEY", "OPENROUTER_API_KEY",
              "S2_DEEPSEEK_MODEL", "GLM_MODEL",
              "DEEPSEEK_RATE_IN", "DEEPSEEK_RATE_OUT"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(s2_client.httpx, "AsyncClient", _CaptureClient)


def _ok_hint():
    return {"choices": [{"message": {"content":
             '{"command": "HINT", "guidance_for_s1": "re-observe the screen",'
             ' "stop": false}'}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5}}


def test_default_es_openrouter_sin_romper(monkeypatch):
    monkeypatch.delenv("S2_PROVIDER", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    assert s2_client.s2_provider() == "openrouter"
    assert s2_client.s2_model_id() == s2_client.glm_model_id()
    assert s2_client._endpoint() == s2_client.OPENROUTER_ENDPOINT
    assert not s2_client.is_mock()


def test_deepseek_dispatch_modelo_y_mock(monkeypatch):
    _patch(monkeypatch, [], {"S2_PROVIDER": "deepseek"})
    assert s2_client.s2_provider() == "deepseek"
    assert s2_client.deepseek_model_id() == "deepseek-chat"
    assert s2_client.s2_model_id() == "deepseek-chat"
    assert s2_client._endpoint() == s2_client.DEEPSEEK_ENDPOINT
    assert s2_client.is_mock()  # sin DEEPSEEK_API_KEY -> stub
    monkeypatch.setenv("S2_DEEPSEEK_MODEL", "deepseek-reasoner")
    assert s2_client.s2_model_id() == "deepseek-reasoner"
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    assert not s2_client.is_mock()


def test_openrouter_sigue_usando_su_key(monkeypatch):
    _patch(monkeypatch, [], {"S2_PROVIDER": "openrouter",
                             "DEEPSEEK_API_KEY": "ds-key"})
    assert s2_client.is_mock()  # openrouter sin su key -> stub
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    assert not s2_client.is_mock()


@pytest.mark.asyncio
async def test_advise_deepseek_endpoint_model_headers(capsys, monkeypatch):
    _patch(monkeypatch, [_ok_hint()],
           {"S2_PROVIDER": "deepseek", "DEEPSEEK_API_KEY": "ds-key"})
    out, usage = await s2_client.advise("generic goal", reason="bootstrap",
                                        table_lines=["0 Button click Ok"])
    assert out["command"] == "HINT"
    assert usage == {"in_tokens": 10, "out_tokens": 5}
    assert _CaptureClient.calls == 1
    assert _CaptureClient.last_url == "https://api.deepseek.com/chat/completions"
    assert _CaptureClient.last_json["model"] == "deepseek-chat"
    auth = _CaptureClient.last_headers.get("Authorization", "")
    assert auth == "Bearer ds-key"
    assert "HTTP-Referer" not in _CaptureClient.last_headers
    assert "X-Title" not in _CaptureClient.last_headers
    logged = capsys.readouterr().out
    assert "provider=deepseek" in logged
    assert "model=deepseek-chat" in logged


@pytest.mark.asyncio
async def test_advise_openrouter_endpoint_por_defecto(monkeypatch):
    _patch(monkeypatch, [_ok_hint()],
           {"OPENROUTER_API_KEY": "or-key"})
    await s2_client.advise("generic goal", reason="bootstrap",
                           table_lines=[])
    assert _CaptureClient.last_url == (
        "https://openrouter.ai/api/v1/chat/completions")
    assert _CaptureClient.last_headers.get("X-Title") == "jam-loop-s2"


@pytest.mark.asyncio
async def test_advise_deepseek_null_retry_luego_ok(monkeypatch):
    null = {"choices": [{"message": {"content": None}}], "usage": {}}
    _patch(monkeypatch, [null, _ok_hint()],
           {"S2_PROVIDER": "deepseek", "DEEPSEEK_API_KEY": "ds-key"})
    out, _ = await s2_client.advise("generic goal", reason="LOW_CONF",
                                    table_lines=[])
    assert out["command"] == "HINT"
    assert _CaptureClient.calls == 2


@pytest.mark.asyncio
async def test_advise_deepseek_vacio_persistente(monkeypatch):
    bad = {"choices": [{"message": {"content": "sin json"}}], "usage": {}}
    _patch(monkeypatch, [bad, bad],
           {"S2_PROVIDER": "deepseek", "DEEPSEEK_API_KEY": "ds-key"})
    with pytest.raises(s2_client.S2EmptyResponse) as ei:
        await s2_client.advise("generic goal", reason="x", table_lines=[])
    assert ei.value.code == "S2_EMPTY_RESPONSE"
    assert _CaptureClient.calls == 2


@pytest.mark.asyncio
async def test_verify_done_deepseek_ok(monkeypatch):
    payload = {"choices": [{"message": {"content":
                '{"achieved": true, "evidence": "effect visible"}'}}],
               "usage": {"prompt_tokens": 7, "completion_tokens": 3}}
    _patch(monkeypatch, [payload],
           {"S2_PROVIDER": "deepseek", "DEEPSEEK_API_KEY": "ds-key"})
    out, usage = await s2_client.verify_done("generic goal",
                                             table_lines=["0 View — Item"],
                                             n_actions=1, final_snapshot=9)
    assert out["achieved"] is True
    assert usage == {"in_tokens": 7, "out_tokens": 3}
    assert _CaptureClient.last_url == (
        "https://api.deepseek.com/chat/completions")


@pytest.mark.asyncio
async def test_stub_deepseek_sin_key_es_mock(monkeypatch):
    _patch(monkeypatch, [], {"S2_PROVIDER": "deepseek"})
    out, usage = await s2_client.advise("generic goal", reason="bootstrap",
                                        table_lines=[])
    assert out.get("mock") is True
    assert _CaptureClient.calls == 0
    v, _ = await s2_client.verify_done("generic goal", table_lines=[])
    assert v.get("mock") is True


def test_mask_pii_igual_en_deepseek():
    assert s2_client.mask_pii("call 123456789 now") == "call <digits:9> now"
    assert s2_client.mask_pii("ok 1234") == "ok 1234"


def test_cost_deepseek_placeholder_y_override(monkeypatch):
    for k in ("DEEPSEEK_RATE_IN", "DEEPSEEK_RATE_OUT"):
        monkeypatch.delenv(k, raising=False)
    assert CT.deepseek_rates() == (CT.DEEPSEEK_PLACEHOLDER_IN,
                                   CT.DEEPSEEK_PLACEHOLDER_OUT)
    import inspect
    assert "PLACEHOLDER" in inspect.getsource(CT)
    monkeypatch.setenv("DEEPSEEK_RATE_IN", "1.0")
    monkeypatch.setenv("DEEPSEEK_RATE_OUT", "2.0")
    assert CT.deepseek_rates() == (1.0, 2.0)
    monkeypatch.setenv("S2_DEEPSEEK_MODEL", "deepseek-chat")
    assert CT.rates_for("deepseek-chat") == (1.0, 2.0)


def test_cost_track_provider_deepseek_en_linea(capsys, monkeypatch):
    monkeypatch.setenv("S2_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_RATE_IN", "1.0")
    monkeypatch.setenv("DEEPSEEK_RATE_OUT", "2.0")
    t = CT.CostTracker(run_id="ds")
    usd = t.track("deepseek-chat", 1_000_000, 1_000_000,
                  step=0, tier="s2")
    assert usd == pytest.approx(3.0)
    out = capsys.readouterr().out
    assert "provider=deepseek" in out
    assert "[COST]" in out
