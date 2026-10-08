#!/usr/bin/env python3
"""tools-list-diff: compara tools/list Go vs Python.

Referencia: jev_mcp.server en vivo (mcp-server/src en sys.path o
PYTHONPATH). Candidato: binario Go por stdio (initialize + tools/list).
Compara por tool: existencia, required y tipos de propiedades.
Diff vacío (exit 0) = igualdad de name + schema.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys


def py_reference() -> dict:
    # Raíz del repo = padre del dir que contiene este script
    # (scripts/tools-list-diff.py tras la reubicación de go-mcp/ → raíz).
    from pathlib import Path
    repo_root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(repo_root / "mcp-server" / "src"))
    import jev_mcp.server as s

    tools = asyncio.run(s.mcp.list_tools())
    ref = {}
    for t in tools:
        ref[t.name] = {"inputSchema": t.inputSchema}
    return ref


def go_candidate(binpath: str) -> dict:
    init = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2024-11-05",
                       "capabilities": {}, "clientInfo": {"name": "diff", "version": "0"}}}
    listed = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
    payload = json.dumps(init) + "\n" + json.dumps(listed) + "\n"
    p = subprocess.run([binpath], input=payload, capture_output=True, text=True, timeout=30)
    if p.returncode not in (0, None) and not p.stdout:
        raise SystemExit(f"binario sin stdout: rc={p.returncode} stderr={p.stderr[:500]}")
    tools = {}
    for line in p.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError as e:
            raise SystemExit(f"stdout corrupto (no JSON-RPC): {line[:200]} ({e})")
        res = (msg.get("result") or {})
        for t in res.get("tools", []):
            tools[t["name"]] = {"inputSchema": t.get("inputSchema", {})}
    if not tools:
        raise SystemExit("tools/list vacío en el candidato Go")
    return tools


def prop_type(prop: dict) -> str:
    if "anyOf" in prop:
        kinds = sorted(x.get("type", "?") for x in prop["anyOf"])
        return "anyOf:" + ",".join(kinds)
    return str(prop.get("type", "?"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", required=True)
    args = ap.parse_args()
    ref = py_reference()
    got = go_candidate(args.bin)
    diffs = []
    if set(ref) != set(got):
        diffs.append(f"nombres: solo-python={sorted(set(ref) - set(got))} solo-go={sorted(set(got) - set(ref))}")
    for name in sorted(set(ref) & set(got)):
        r, g = ref[name]["inputSchema"], got[name]["inputSchema"]
        if (r.get("required") or []) != (g.get("required") or []):
            diffs.append(f"{name}: required py={r.get('required')} go={g.get('required')}")
        rp, gp = r.get("properties", {}), g.get("properties", {})
        if set(rp) != set(gp):
            diffs.append(f"{name}: props py={sorted(rp)} go={sorted(gp)}")
            continue
        for prop in sorted(rp):
            if prop_type(rp[prop]) != prop_type(gp[prop]):
                diffs.append(f"{name}.{prop}: tipo py={prop_type(rp[prop])} go={prop_type(gp[prop])}")
    if diffs:
        print("DIFF tools/list (Go vs Python):")
        for d in diffs:
            print("  -", d)
        return 1
    print(f"OK tools/list: 35/35 iguales (name + required + tipos) [{len(ref)} tools]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
