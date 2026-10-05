"""CostTracker dual-tier S1 Jev + S2 GLM-5.3 (docs/specs/generic-dual-tier.md §5).

Tarifas:
- Jev: $0.042 in / $0.00 out por MTok (normativo del contrato).
- GLM-5.3: SOLO via env GLM_RATE_IN / GLM_RATE_OUT; los defaults en
  codigo son PLACEHOLDER ajustable contra factura OpenRouter, nunca
  verdad oficial.
- Overrides JEV_RATE_IN / JEV_RATE_OUT (defaults 0.042 / 0.0) para no
  recompilar ante un cambio de precio.

Sin API keys en este fichero: la key vive solo en el entorno y la leen
los clientes (jev_client / s2_client).
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

log = logging.getLogger("cost")

# --- defaults normativos / placeholder -------------------------------------
JEV_DEFAULT_IN = 0.042
JEV_DEFAULT_OUT = 0.0
# PLACEHOLDER — ajustar contra factura OpenRouter (GLM-5.3 sin tasa oficial
# fijada en contrato; configurable via GLM_RATE_IN / GLM_RATE_OUT).
GLM_PLACEHOLDER_IN = 1.0  # PLACEHOLDER — ajustar contra factura OpenRouter
GLM_PLACEHOLDER_OUT = 1.0  # PLACEHOLDER — ajustar contra factura OpenRouter


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def jev_model_id() -> str:
    return os.environ.get("JEV_MODEL", "typesafe/jev-1.13")


def glm_model_id() -> str:
    return os.environ.get("GLM_MODEL", "z-ai/glm-5.3")


def jev_rates() -> tuple[float, float]:
    """(in, out) USD por MTok, con overrides JEV_RATE_IN/OUT en vivo."""
    return (_env_float("JEV_RATE_IN", JEV_DEFAULT_IN),
            _env_float("JEV_RATE_OUT", JEV_DEFAULT_OUT))


def glm_rates() -> tuple[float, float]:
    """(in, out) USD por MTok, SOLO via env GLM_RATE_IN/OUT en vivo."""
    return (_env_float("GLM_RATE_IN", GLM_PLACEHOLDER_IN),
            _env_float("GLM_RATE_OUT", GLM_PLACEHOLDER_OUT))


@dataclass(frozen=True)
class ModelRate:
    """Tarifa de un modelo en USD por millon de tokens."""

    model: str
    in_per_mtok: float
    out_per_mtok: float

    def cost_usd(self, in_tok: int, out_tok: int) -> float:
        return in_tok / 1e6 * self.in_per_mtok + out_tok / 1e6 * self.out_per_mtok


# Foto a import-time (los overrides se resuelven en vivo en rates_for/track).
RATES: dict[str, tuple[float, float]] = {
    os.environ.get("JEV_MODEL", "typesafe/jev-1.13"): (
        float(os.environ.get("JEV_RATE_IN", JEV_DEFAULT_IN)),
        float(os.environ.get("JEV_RATE_OUT", JEV_DEFAULT_OUT)),
    ),
    os.environ.get("GLM_MODEL", "z-ai/glm-5.3"): (
        float(os.environ.get("GLM_RATE_IN", GLM_PLACEHOLDER_IN)),
        float(os.environ.get("GLM_RATE_OUT", GLM_PLACEHOLDER_OUT)),
    ),
}


def rates_for(model: str) -> tuple[float, float]:
    """Tarifa vigente para `model`, resolviendo env en vivo.

    El modelo Jev usa JEV_RATE_IN/OUT; cualquier otro (S2 GLM-5.3 y
    futuros) usa GLM_RATE_IN/OUT.
    """
    if model == jev_model_id():
        return jev_rates()
    return glm_rates()


@dataclass
class CostTracker:
    """Acumula coste USD por corrida; cada llamada LLM pasa por track()."""

    run_id: str = ""
    jev_cost: float = 0.0
    s2_cost: float = 0.0
    steps: int = 0
    lines: list[str] = field(default_factory=list)

    def track(self, model: str, in_tok: int, out_tok: int, *,
              step: int | None = None, tier: str = "s1",
              provider_cost: float | None = None) -> float:
        """Registra una llamada y devuelve su coste USD del paso.

        `tier="s1"` acumula en jev_cost; cualquier otro en s2_cost.
        Si el proveedor devolvio coste directo (sin tokens), se registra
        tal cual via provider_cost (source=provider).
        Sin key (stub, 0 tokens y sin provider_cost) -> usd=0.0.
        """
        in_tok = int(in_tok or 0)
        out_tok = int(out_tok or 0)
        if provider_cost is not None and in_tok == 0 and out_tok == 0:
            usd = float(provider_cost)
            source = "provider"
        else:
            rate_in, rate_out = rates_for(model)
            usd = in_tok / 1e6 * rate_in + out_tok / 1e6 * rate_out
            source = "computed"
        if tier == "s1":
            self.jev_cost += usd
        else:
            self.s2_cost += usd
        if step is not None:
            self.steps = max(self.steps, int(step))
        line = (f"[COST] model={model} in={in_tok} out={out_tok} "
                f"usd={usd:.6f} step={step} run={self.run_id} src={source}")
        self.lines.append(line)
        print(line, flush=True)
        log.info(line)
        return usd

    @property
    def total_cost_usd(self) -> float:
        return self.jev_cost + self.s2_cost

    def summary(self) -> dict:
        return {"jev_cost": self.jev_cost, "s2_cost": self.s2_cost,
                "total_cost": self.total_cost_usd, "steps": self.steps}
