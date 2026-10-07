"""Re-export director-cliente v5 para invocación estilo curl.

El director invoca paso a paso::

    uv run python -c "from jev_mcp.tools import open_app, read_screen_state"

Este paquete NO toca ``loop.run_goal`` ni el decisor con goal global
(congelados §6): el resolver es ciego al goal (``core.director_resolve``
sobre ``ask``).
"""
from ..director import (  # noqa: F401
    close_app,
    get_clipboard,
    open_app,
    read_screen,
    read_screen_state,
    resolve_element,
    set_clipboard,
    tap_idx,
    type_text,
)
from . import app, clipboard, device, ui  # noqa: F401
