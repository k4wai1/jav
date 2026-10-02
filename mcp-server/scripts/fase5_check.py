"""Demo Fase 5: send_whatsapp(contact, text) end-to-end.

    cd mcp-server && uv run python scripts/fase5_check.py \
        --contact Felix --text "voy en media hora"

Sin OPENROUTER_API_KEY corre con stub (plomería); con key, Jev real.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from jev_mcp import jev_client  # noqa: E402
from jev_mcp.tasks.whatsapp import send_whatsapp  # noqa: E402


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--contact", default="Felix")
    ap.add_argument("--text", default="voy en media hora")
    ap.add_argument("--confirm-real-send", action="store_true",
                    help="desactiva dry-run: permite el tap de enviar")
    ap.add_argument("--log-dir", default="logs")
    a = ap.parse_args()
    dry = not a.confirm_real_send
    os.makedirs(a.log_dir, exist_ok=True)
    import time as _t
    log_path = os.path.join(a.log_dir, f"run-{int(_t.time())}.jsonl")
    subprocess.run(["adb", "forward", "tcp:38472", "tcp:38472"],
                   capture_output=True, check=False)
    print(f"contact={a.contact!r} text={a.text!r} "
          f"jev={'stub' if jev_client.is_mock() else 'real'} "
          f"dry_run={dry} log={log_path}", flush=True)
    t0 = time.time()
    from jev_mcp.tasks.whatsapp import send_whatsapp as _send
    import jev_mcp.tasks.whatsapp as _w
    _w.WA = "com.whatsapp"
    r = await _send(a.contact, a.text, dry_run=dry, log_path=log_path)
    dt = time.time() - t0
    steps = r.get("steps", 0)
    print(f"ok={r.get('ok')} verified={r.get('verified')} "
          f"steps={steps} duration={dt:.1f}s "
          f"avg={(dt / max(1, steps)) * 1000:.0f}ms/paso "
          f"jev_calls={r.get('jev_calls')} cost={r.get('jev_cost', 0.0):.6f}",
          flush=True)
    print(f"evidence={r.get('evidence')}", flush=True)
    if not r.get("ok"):
        for h in r.get("history", [])[-4:]:
            print(f"  step {h['step']}: {h['action']} -> {h['result']}", flush=True)
    return 0 if (r.get("ok") and r.get("verified")) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
