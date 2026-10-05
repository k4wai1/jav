"""CostTracker: tarifas normativas, env overrides, acumulados, log [COST]."""
import os

import pytest

from jev_mcp import cost_tracker as CT
from jev_mcp.core import cost as core_cost


def test_jev_rates_normativos(monkeypatch):
    monkeypatch.delenv("JEV_RATE_IN", raising=False)
    monkeypatch.delenv("JEV_RATE_OUT", raising=False)
    assert CT.jev_rates() == (0.042, 0.0)


def test_env_overrides(monkeypatch):
    monkeypatch.setenv("JEV_RATE_IN", "0.10")
    monkeypatch.setenv("JEV_RATE_OUT", "0.20")
    monkeypatch.setenv("GLM_RATE_IN", "2.0")
    monkeypatch.setenv("GLM_RATE_OUT", "3.0")
    assert CT.jev_rates() == (0.10, 0.20)
    assert CT.glm_rates() == (2.0, 3.0)
    assert CT.rates_for(CT.jev_model_id()) == (0.10, 0.20)
    assert CT.rates_for("otro-modelo") == (2.0, 3.0)


def test_glm_default_es_placeholder_ajustable(monkeypatch):
    monkeypatch.delenv("GLM_RATE_IN", raising=False)
    monkeypatch.delenv("GLM_RATE_OUT", raising=False)
    assert CT.glm_rates() == (CT.GLM_PLACEHOLDER_IN, CT.GLM_PLACEHOLDER_OUT)
    # El default documentado como placeholder vive en el código marcado.
    import inspect
    src = inspect.getsource(CT)
    assert "PLACEHOLDER" in src


def test_track_acumula_e_imprime(capsys, monkeypatch):
    monkeypatch.delenv("JEV_RATE_IN", raising=False)
    monkeypatch.delenv("JEV_RATE_OUT", raising=False)
    t = CT.CostTracker(run_id="t1")
    usd = t.track(CT.jev_model_id(), 1_000_000, 500_000, step=1, tier="s1")
    assert usd == pytest.approx(0.042)  # out a 0.0
    t.track("s2-model", 0, 0, step=1, tier="s2", provider_cost=0.5)
    assert t.jev_cost == pytest.approx(0.042)
    assert t.s2_cost == pytest.approx(0.5)
    assert t.total_cost_usd == pytest.approx(0.542)
    out = capsys.readouterr().out
    assert out.count("[COST]") == 2
    assert "run=t1" in out


def test_stub_cero(capsys):
    t = CT.CostTracker(run_id="stub")
    assert t.track("m", 0, 0, step=1) == 0.0
    assert t.total_cost_usd == 0.0


def test_core_cost_reexporta():
    assert core_cost.CostTracker is CT.CostTracker
    assert core_cost.ModelRate is CT.ModelRate
    assert core_cost.RATES is CT.RATES
    r = core_cost.ModelRate(model="m", in_per_mtok=0.042, out_per_mtok=0.0)
    assert r.cost_usd(1_000_000, 10) == pytest.approx(0.042)


def test_sin_keys_en_fichero():
    import inspect
    src = inspect.getsource(CT)
    assert "OPENROUTER_API_KEY" not in src
    assert "sk-" not in src
