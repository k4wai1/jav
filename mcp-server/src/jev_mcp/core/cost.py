"""Tarifas y CostTracker del agente generico (re-export de ..cost_tracker).

Contrato: docs/specs/generic-dual-tier.md §5. La implementacion canonica
vive en `jev_mcp.cost_tracker`; este modulo la expone como `core.cost`.
"""
from ..cost_tracker import (  # noqa: F401
    GLM_PLACEHOLDER_IN,
    GLM_PLACEHOLDER_OUT,
    JEV_DEFAULT_IN,
    JEV_DEFAULT_OUT,
    RATES,
    CostTracker,
    ModelRate,
    glm_model_id,
    glm_rates,
    jev_model_id,
    jev_rates,
    rates_for,
)
