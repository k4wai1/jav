"""Check end-to-end Fase 2 contra WhatsApp real (sin Jev).

Flujo: adb forward + token desde logcat + abrir WhatsApp + hello +
get_foreground + dump_ui + tap(selector descubierto) + tap_node +
STALE_SNAPSHOT + dump_ui de verificación.

    cd mcp-server && uv run python scripts/fase2_check.py

Criterio: tap ok con via explícito y snapshot_id avanzando; el snapshot
viejo debe fallar con STALE_SNAPSHOT.
"""
from __future__ import annotations

import asyncio
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from jev_mcp.socket_client import JamClient, JamError


def adb(*args: str) -> str:
    return subprocess.run(["adb", *args], capture_output=True, text=True).stdout.strip()


def token_from_logcat() -> str:
    out = subprocess.run(["adb", "logcat", "-d"], capture_output=True, text=True).stdout
    m = re.findall(r"JamWs token=([A-Za-z0-9_\-]+)", out)
    if not m:
        raise SystemExit("token no encontrado en logcat (¿servidor arrancado? abre Jam)")
    return m[-1]


def candidates(nodes: list) -> list:
    """Nodos clicables con texto o content-desc, priorizando navegación atrás."""
    scored = []
    for n in nodes:
        if not n.get("clickable"):
            continue
        t = (n.get("text") or "") + " " + (n.get("content_desc") or "")
        if not t.strip():
            continue
        prio = 0
        if re.search(r"atrás|navegar|back|up\b", t, re.I):
            prio = 2
        elif n.get("editable"):
            prio = 1
        scored.append((prio, t.strip()[:60], n["id"]))
    scored.sort(reverse=True)
    return scored


async def main() -> int:
    subprocess.run(["adb", "forward", "tcp:38472", "tcp:38472"],
                   capture_output=True, check=False)
    url = os.environ.get("JEV_WS_URL", "ws://127.0.0.1:38472/")
    token = os.environ.get("JEV_TOKEN") or token_from_logcat()

    adb("shell", "monkey", "-p", "com.whatsapp", "-c",
        "android.intent.category.LAUNCHER", "1")
    await asyncio.sleep(3)

    try:
        async with JamClient(url, token) as jam:
            print(f"hello ok scopes={jam.scopes} app={jam.app_version}", flush=True)
            assert set(jam.scopes) >= {"read", "ui"}, f"scopes raros: {jam.scopes}"
            fg = await jam.get_foreground()
            print(f"foreground={fg}", flush=True)
            assert fg.get("package") == "com.whatsapp", f"no está WhatsApp: {fg}"

            d1 = await jam.dump_ui()
            s1, n1 = d1["snapshot_id"], d1["nodes"]
            print(f"dump1: snapshot={s1} nodes={len(n1)}", flush=True)

            cands = candidates(n1)
            print(f"candidatos clicables: {len(cands)}", flush=True)
            for prio, t, i in cands[:5]:
                print(f"  [{i}] {t}", flush=True)
            if not cands:
                print("FAIL: sin nodos clicables", flush=True)
                return 1
            _, shown, target = cands[0]
            sel = selector_for(target, n1)
            print(f"tap -> {target} ({shown}) sel={sel}", flush=True)
            r = await jam.tap(sel)
            print(f"tap ok via={r.get('via')} node={r.get('node_id')}", flush=True)
            assert r.get("via") in ("action_click", "gesture"), r

            # tap_node con snapshot fresco del MISMO dump debe funcionar
            # si la UI no cambió; si cambió, STALE es respuesta válida.
            try:
                r2 = await jam.call("tap_node", {"node_id": target, "snapshot_id": s1})
                print(f"tap_node fresco -> {r2}", flush=True)
            except JamError as e:
                print(f"tap_node fresco -> {e.code} (aceptable si la UI cambió)", flush=True)
                assert e.code in ("STALE_SNAPSHOT", "SELECTOR_NOT_FOUND"), e

            d2 = await jam.dump_ui()
            s2 = d2["snapshot_id"]
            print(f"dump2: snapshot={s2} nodes={len(d2['nodes'])}", flush=True)
            assert s2 > s1, "snapshot no avanzó"

            # tap_node con snapshot viejo DEBE fallar con STALE_SNAPSHOT.
            try:
                await jam.call("tap_node", {"node_id": target, "snapshot_id": s1})
                print("FAIL: snapshot viejo aceptado (debió ser STALE)", flush=True)
                return 1
            except JamError as e:
                assert e.code == "STALE_SNAPSHOT", f"código inesperado: {e}"
                print(f"stale check ok ({e.code})", flush=True)

            print("OK fase2", flush=True)
            return 0
    except JamError as e:
        print(f"FAIL JamError {e.code}: {e.error}", flush=True)
        return 1
    except AssertionError as e:
        print(f"FAIL assert: {e}", flush=True)
        return 1


def selector_for(node_id: str, nodes: list) -> dict:
    for n in nodes:
        if n["id"] == node_id:
            if n.get("resource_id"):
                return {"resource_id": n["resource_id"].split("/")[-1]}
            if n.get("text"):
                return {"text": n["text"]}
            if n.get("content_desc"):
                return {"content_desc": n["content_desc"]}
    return {"text_contains": node_id}


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
