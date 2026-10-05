"""OBSOLETO (contrato generic-dual-tier 2026-10-05): tasks/ se eliminó.

Usa en su lugar:

    cd mcp-server && uv run python scripts/run_goal_check.py \
        --goal "activa el modo avión"

Este stub existe solo para redirigir comprobaciones antiguas; no
contiene lógica de dominio y falla con instrucciones.
"""
from __future__ import annotations

import sys

print("fase5_check está obsoleto: tasks/ se eliminó (generic-dual-tier). "
      "Usa scripts/run_goal_check.py --goal \"...\"",
      file=sys.stderr)
raise SystemExit(2)
