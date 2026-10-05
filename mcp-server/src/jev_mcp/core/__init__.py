"""Core genérico del MCP (determinista): mecanismos, cero datos de dominio.

Puro y sin I/O: compuertas (guards), ayudas del loop (loop_helpers),
costes (cost), coincidencia de texto (text_match) y títulos (titles).
Ningún paquete concreto, regex de UI de una app o literal de dominio
vive aquí. El agente general `run_goal` (loop.py) consume este core.
"""
