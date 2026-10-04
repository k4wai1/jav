"""Core genérico del MCP (System1 determinista): mecanismos, cero datos de app.

Puro y sin I/O: todo lo específico de cada app (PACKAGE, resource_id,
regex de UI, contactos) vive en el plugin `tasks/<app>.py`, que importa
de aquí (dependencia plugin → core, nunca al revés).
"""
