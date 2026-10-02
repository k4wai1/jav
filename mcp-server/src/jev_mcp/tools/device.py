"""Tools device/: estado y paquetes."""
from __future__ import annotations

import subprocess

from . import _base as B


async def device_status() -> dict:
    jam = await B.jam_client()
    try:
        fg = await jam.get_foreground()
    finally:
        await jam.__aexit__()
    return B.ok(True, {
        "scopes": jam.scopes,
        "app_version": jam.app_version,
        "foreground": fg,
    })


async def list_packages(filter: str = "") -> dict:
    out = subprocess.run(["adb", "shell", "pm", "list", "packages"],
                         capture_output=True, text=True).stdout
    pkgs = [l.split(":", 1)[1] for l in out.splitlines() if l.startswith("package:")]
    if filter:
        fl = filter.lower()
        pkgs = [p for p in pkgs if fl in p.lower()]
    return B.ok(True, {"count": len(pkgs), "packages": pkgs})


async def get_foreground() -> dict:
    jam = await B.jam_client()
    try:
        fg = await jam.get_foreground()
    finally:
        await jam.__aexit__()
    return B.ok(True, fg)
