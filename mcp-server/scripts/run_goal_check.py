"""Demo genérica: run_goal(goal) end-to-end (contrato generic-dual-tier).

    cd mcp-server && uv run python scripts/run_goal_check.py \
        --goal "activa el modo avión"

Sin OPENROUTER_API_KEY corre con stubs honestos (plomería + forense +
[COST]); con key, S1 Jev real y S2 GLM-5.3 ante escalado. Sin paquetes
ni contactos: un goal en lenguaje natural y compuertas genéricas.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from jev_mcp import jev_client, loop, s2_client  # noqa: E402


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--goal", required=True,
                    help='objetivo en lenguaje natural, p.ej. "activa el modo avión"')
    ap.add_argument("--confirm", action="store_true",
                    help="habilita acciones críticas/irreversibles (con preview auditada)")
    ap.add_argument("--forbidden", default=None,
                    help="pattern regex opt-in (sin él no hay filtro)")
    ap.add_argument("--max-steps", type=int, default=20)
    ap.add_argument("--timeout", type=float, default=60.0)
    ap.add_argument("--log-dir", default="logs")
    a = ap.parse_args()
    os.makedirs(a.log_dir, exist_ok=True)
    log_path = os.path.join(a.log_dir, f"run-{int(time.time())}.jsonl")
    from jev_mcp.tools import _base as _b
    _b.ensure_forward()
    print(f"goal={a.goal!r} "
          f"s1={'stub' if jev_client.is_mock() else 'real'} "
          f"s2={'stub' if s2_client.is_mock() else 'real'} "
          f"confirm={a.confirm} log={log_path}", flush=True)
    t0 = time.time()
    r = await loop.run_goal(a.goal, max_steps=a.max_steps,
                            timeout_s=a.timeout, log_path=log_path,
                            confirm=a.confirm, forbidden=a.forbidden)
    dt = time.time() - t0
    print(f"ok={r.get('ok')} verified={r.get('verified')} "
          f"steps={r.get('steps')} duration={dt:.1f}s "
          f"jev_calls={r.get('jev_calls')} s2_calls={r.get('s2_calls')} "
          f"jev_cost={r.get('jev_cost', 0.0):.6f} "
          f"s2_cost={r.get('s2_cost', 0.0):.6f} "
          f"total={r.get('total_cost', 0.0):.6f}", flush=True)
    print(f"evidence={r.get('evidence')}", flush=True)
    if r.get("needs_confirm"):
        print(f"hint={r.get('hint')}", flush=True)
    if not r.get("ok"):
        for h in r.get("history", [])[-4:]:
            print(f"  step {h['step']}: {h['action']} -> {h['result']}",
                  flush=True)
    return 0 if (r.get("ok") and r.get("verified")) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
