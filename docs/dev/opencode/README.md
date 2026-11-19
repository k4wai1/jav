# OpenCode (flujo interno de desarrollo)

> **No forma parte del runtime de Jav.** Son archivos de trabajo del
> mantenedor con OpenCode. Se movieron aquí en `v2.6.0` para que la raíz del
> repo no dependa de un cliente MCP concreto (Claude Desktop, Cursor,
> Windsurf, Cline y OpenCode consumen el mismo servidor `jav` por stdio).

## Contenido

| Ruta | Qué es |
|---|---|
| `AGENTS-MULTIAGENT.md` | Reparto de roles entre agentes (subordinado a `AGENTS.md`). |
| `opencode.json` | Config de OpenCode (modelo y agente por defecto). |
| `agents/` | Definiciones de agentes (`architect`, `coder`, `explorer`, `judge`, `orchestrator`). |

## Cómo usarlo

OpenCode descubre `opencode.json` y `.opencode/agents/` en la **raíz** del
proyecto. Como aquí viven fuera de la raíz, enlaza o copia lo que necesites
antes de abrir una sesión:

```bash
# Opción A — enlaces simbólicos (recomendado; no duplica contenido)
ln -sf docs/dev/opencode/opencode.json opencode.json
ln -sfn docs/dev/opencode/agents .opencode/agents

# Opción B — copia temporal
cp docs/dev/opencode/opencode.json opencode.json
cp -r docs/dev/opencode/agents .opencode/agents
```

Los enlaces quedan ignorados por git (ver `.gitignore`), así que no
reintroducen acoplamiento en el repo.

## Skill de auditoría

`.opencode/skills/audit-bundle/` se conserva **en su sitio** porque OpenCode
la carga desde `.opencode/skills/` y es parte del flujo local de auditoría
(no afecta al runtime de Jav).

## Cliente MCP

Para registrar el servidor `jav` en cualquier cliente, usa el bloque estándar
`mcpServers` del `README.md`. La config de vinculación
(`~/.config/jav/config.json`) no depende del cliente.
