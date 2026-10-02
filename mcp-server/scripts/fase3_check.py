"""Check Fase 3a: open_app + force_stop + screenshot + shell gateado.

Pre-requisito: Shizuku arrancado por el usuario (con hint si no).
No usa shell arbitrario: solo 3a.

    cd mcp-server && uv run python scripts/fase3_check.py
"""
from __future__ import annotations

import asyncio
import base64
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from jev_mcp.socket_client import JamClient, JamError

WA = "com.whatsapp"


def adb(*args: str) -> str:
    return subprocess.run(["adb", *args], capture_output=True, text=True).stdout.strip()


def shizuku_running() -> bool:
    # El servidor se llama `shizuku_server` (root); el manager
    # `moe.shizuku.privileged.api` aparece y desaparece. Mirar el server.
    out = adb("shell", "ps -A")
    return "shizuku_server" in out


def token_from_logcat() -> str:
    out = subprocess.run(["adb", "logcat", "-d"], capture_output=True, text=True).stdout
    m = re.findall(r"JamWs token=([A-Za-z0-9_\-]+)", out)
    if not m:
        raise SystemExit("token no encontrado en logcat (¿servidor arrancado? abre Jam)")
    return m[-1]


async def main() -> int:
    if not shizuku_running():
        print("FAIL: Shizuku no corre. Ábrelo (app Shizuku), arráncalo y reintenta.",
              flush=True)
        return 1
    print("shizuku_server corriendo", flush=True)
    subprocess.run(["adb", "forward", "tcp:38472", "tcp:38472"],
                   capture_output=True, check=False)
    url = os.environ.get("JEV_WS_URL", "ws://127.0.0.1:38472/")
    token = os.environ.get("JEV_TOKEN") or token_from_logcat()
    fails = 0

    def check(name: str, cond: bool, detail: str = "") -> None:
        nonlocal fails
        print(f"[{'OK' if cond else 'FAIL'}] {name} {detail}", flush=True)
        if not cond:
            fails += 1

    try:
        async with JamClient(url, token) as jam:
            # 1-2. force_stop + verificación de salida.
            await jam.call("open_app", {"package": WA})
            fg = await jam.get_foreground()
            check("open_app lleva a WhatsApp", fg.get("package") == WA, str(fg))
            await jam.call("force_stop", {"package": WA})
            await asyncio.sleep(1)
            fg = await jam.get_foreground()
            check("force_stop saca de WhatsApp", fg.get("package") != WA, str(fg))

            # 2b. open_app de nuevo (deja WA abierto para lo siguiente).
            r = await jam.call("open_app", {"package": WA})
            check("open_app devuelve package/activity",
                  r.get("package") == WA and r.get("activity"), str(r))

            # 3. screenshot PNG.
            s = await jam.screenshot("png")
            raw = base64.b64decode(s["img_base64"])
            check("screenshot png válido",
                  len(s["img_base64"]) > 1000 and s["w"] > 0 and s["h"] > 0,
                  f"{s['w']}x{s['h']} via={s.get('via')} bytes={len(raw)}")
            with open("/tmp/jam_shot.png", "wb") as f:
                f.write(raw)
            print("  guardado en /tmp/jam_shot.png (comparar con screencap)", flush=True)

            # 5. shell gateado explícito.
            try:
                await jam.call("shell", {"command": "id"})
                check("shell rechazado", False, "fue aceptado")
            except JamError as e:
                check("shell rechazado", e.code == "METHOD_NOT_ALLOWED", e.code)

            # 6. método desconocido sigue siendo METHOD_NOT_ALLOWED.
            try:
                await jam.call("no_existe", {})
                check("método desconocido rechazado", False, "fue aceptado")
            except JamError as e:
                check("método desconocido rechazado",
                      e.code == "METHOD_NOT_ALLOWED", e.code)
    except JamError as e:
        print(f"FAIL JamError {e.code}: {e.error}", flush=True)
        return 1

    # 7-8 son manuales (denegar permiso / parar binder) — recordatorio.
    print("MANUAL: denegar permiso Shizuku → open_app debe dar SHIZUKU_DENIED;",
          "parar binder → SHIZUKU_UNAVAILABLE.", flush=True)
    print("OK fase3a" if fails == 0 else f"FAIL fase3a ({fails})", flush=True)
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
