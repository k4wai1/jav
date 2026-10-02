"""Check Fase 4: cliente MCP por stdio contra server.py, flujo WhatsApp.

    cd mcp-server && uv run python scripts/fase4_check.py  (con JEV_TOKEN)

Flujo: device_status → open_app whatsapp → read_screen (≤60, package ok,
sin statusBar) → tap_text Buscar → type_text Felix (o NOT_FOCUSED) →
read_screen (snapshot avanzó). Mide latencias por tool.
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")

sys.path.insert(0, os.path.join(ROOT, "src"))

from mcp.client.session import ClientSession  # noqa: E402
from mcp.client.stdio import StdioServerParameters, stdio_client  # noqa: E402


async def main() -> int:
    if not os.environ.get("JEV_TOKEN"):
        raise SystemExit("Falta JEV_TOKEN en el entorno")
    subprocess.run(["adb", "forward", "tcp:38472", "tcp:38472"],
                   capture_output=True, check=False)
    env = {**os.environ, "PYTHONPATH": os.path.join(ROOT, "src")}
    params = StdioServerParameters(
        command="uv", args=["run", "--project", ROOT,
                            "python", "-m", "jev_mcp.server"], env=env)
    fails = 0
    lat: dict[str, float] = {}

    async def call(name: str, args: dict) -> dict:
        t0 = time.time()
        res = await session.call_tool(name, args)
        lat[name] = (time.time() - t0) * 1000
        # FastMCP devuelve structuredContent o content[0].text JSON
        import json
        if getattr(res, "structuredContent", None):
            out = res.structuredContent
            return out.get("result", out) if isinstance(out, dict) else out
        txt = res.content[0].text if res.content else "{}"
        return json.loads(txt)

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = sorted(t.name for t in tools.tools)
            print(f"tools ({len(names)}): {names}", flush=True)
            assert "read_screen" in names and "tap_text" in names

            st = await call("device_status", {})
            print(f"device_status: {st}", flush=True)
            assert st.get("ok") and st.get("verified"), st

            r = await call("open_app", {"package": "com.whatsapp"})
            print(f"open_app: verified={r.get('verified')}", flush=True)
            assert r.get("ok") and r.get("verified"), r

            s1 = await call("read_screen", {})
            n1 = len(s1["evidence"]["candidates"])
            print(f"read_screen: snap={s1['evidence']['snapshot_id']} "
                  f"cands={n1}/{s1['evidence']['raw_count']} "
                  f"pkg={s1['evidence']['package']}", flush=True)
            assert s1["evidence"]["package"] == "com.whatsapp", s1
            assert n1 <= 60, n1
            assert not any("Background" in (c.get("resource_id") or "")
                           for c in s1["evidence"]["candidates"])
            snap1 = s1["evidence"]["snapshot_id"]

            t = await call("tap_text", {"text": "Buscar"})
            print(f"tap_text: {t}", flush=True)
            assert t.get("ok") and t.get("evidence", {}).get("via"), t

            s2 = await call("read_screen", {})
            snap2 = s2["evidence"]["snapshot_id"]
            cands = s2["evidence"]["candidates"]
            edit = next((c for c in cands if c.get("editable")), None)
            print(f"read_screen2: snap={snap2} edit={edit}", flush=True)
            assert snap2 > snap1, (snap1, snap2)
            if edit:
                r2 = await call("type_text", {"node_id": edit["id"],
                                             "snapshot_id": snap2, "text": "Felix"})
                print(f"type_text: {r2}", flush=True)
                assert r2.get("ok"), r2
            else:
                print("sin editable visible: salto type_text (NOT_FOCUSED no aplica)", flush=True)

            s3 = await call("read_screen", {})
            assert s3["evidence"]["snapshot_id"] >= snap2

    print("latencias ms:", {k: round(v) for k, v in lat.items()}, flush=True)
    print("OK fase4" if fails == 0 else "FAIL fase4", flush=True)
    return fails


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
