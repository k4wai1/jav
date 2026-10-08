# INSTALL — servidor `jav` (MCP stdio → Jam en Android)

> Binario **`jav`**, módulo **`github.com/k4wai1/jav`**.
> Un solo entrypoint stdio (`cmd/jav`), sin daemon, sin flags mutantes.
> Contrato: `docs/specs/go-migration-plan.md`. Proveedores IA:
> `docs/specs/ai-providers.md` (S1 Jev fijo vs S2 agnóstico).
> 100% genérico. Los valores aquí son **ejemplos no-secretos**;
> los secretos reales viven solo en tu `.env` local (`chmod 600`,
> nunca commiteado).

## 0. Requisitos

- Toolchain Go según `go.mod` + `go.sum` commiteado.
- `adb` en el `PATH` (para `list_packages`, clipboard-host, `wm size`,
  auto-`adb forward tcp:38472`).
- App Jam instalada en el dispositivo + servidor Jam corriendo
  (ella muestra el token y el QR de onboarding).
- Sin Jam alcanzable, `initialize` + `tools/list` funcionan igual
  (listan, no conectan); las tools que exigen Jam fallan honesto,
  nunca cuelgan.

## 1. One-liner (release)

```sh
curl -fsSL https://raw.githubusercontent.com/k4wai1/jav/master/install.sh | sh
```

Env del instalador: `VERSION=v0.1.0` (default `latest`),
`REPO=k4wai1/jav`, `PREFIX=/custom` (default: `/usr/local/bin` si
escribible, si no `~/.local/bin`), `BIN=jav`. Detecta
linux/darwin/windows × amd64/arm64 y deja el binario en el destino.

## 2. Desde fuente

```sh
git clone https://github.com/k4wai1/jav.git ~/jev-android-mcp
make build        # host → dist/jav-linux-amd64
make build-all    # linux/amd64 + linux/arm64 + darwin/arm64 + windows/amd64 → dist/
go run ./cmd/jav  # sin instalar: arranca el servidor MCP por stdio
```

`make test` (`go test ./...`), `make vet`, `make tools-list-diff`
(compara `tools/list` Go vs Python; diff vacío = OK). Cada build real
se documenta en `docs/BUILD.md` (comando, tiempo, RAM).

## 3. `.env` (forma, sin secretos)

```sh
cp .env.example .env
chmod 600 .env
```

```text
# Transporte MCP → Jam (JAV_* manda; JEV_WS_URL/JEV_TOKEN valen como fallback):
JAV_WS_URL=ws://127.0.0.1:38472/
# Remoto opt-in (WSS obligatorio fuera de loopback):
# JAV_WS_URL=wss://100.64.x.x:38472/
JAV_TOKEN=
# S1 Jev fijo (endpoint decisiones OpenRouter/TypeSafe, ver ai-providers.md §1):
OPENROUTER_API_KEY=
JEV_MODEL=typesafe/jev-1.13
# S2 agnóstico OpenAI-compatible (ver ai-providers.md §2; sin JAV_AI_*
# opera como v1: OpenRouter con la misma OPENROUTER_API_KEY):
# JAV_AI_BASE_URL=https://openrouter.ai/api/v1
# JAV_AI_API_KEY=
# JAV_AI_MODEL=
S2_MODEL=z-ai/glm-5.3-flash
# Tasas S2 (placeholder ajustable contra factura, nunca oficial):
# GLM_RATE_IN=0.15
# GLM_RATE_OUT=0.50
# Overrides S1 (defaults 0.042 / 0.0):
# JEV_RATE_IN=0.042
# JEV_RATE_OUT=0.0
# Forense del director (lo escribe el cliente, no el servidor):
JAV_LOG_DIR=logs/
```

Notas:

- `JAV_TOKEN` sale del QR/onboarding de Jam. Sin él, las tools Jam
  fallan `UNAUTHORIZED`-honesto.
- Sin `OPENROUTER_API_KEY`, S1 queda desactivado (error honesto, nunca
  resolución inventada) y S2 responde stub `{mock:true}`.
- `JAV_AI_API_KEY` es opcional si la base S2 es local sin auth
  (p.ej. `http://127.0.0.1:11434/v1`); contra base remota sin key →
  error honesto.
- Heredados que `jav` **no** lee: `OPENROUTER_MODEL`, `TYPESAFE_*`
  (swap futuro), `JEV_CERT_FINGERPRINT` (TLS tailnet = fase posterior).

## 4. Registro en clientes MCP

### 4.1 opencode.json (host Linux, stdio)

```json
{
  "mcp": {
    "jav": {
      "type": "local",
      "command": ["$HOME/jev-android-mcp/dist/jav-linux-amd64"],
      "enabled": true,
      "environment": {
        "JAV_WS_URL": "ws://127.0.0.1:38472/",
        "JAV_TOKEN": "",
        "OPENROUTER_API_KEY": "",
        "JEV_MODEL": "typesafe/jev-1.13",
        "JAV_AI_BASE_URL": "https://openrouter.ai/api/v1",
        "JAV_AI_MODEL": "z-ai/glm-5.3-flash",
        "S2_MODEL": "z-ai/glm-5.3-flash",
        "JAV_LOG_DIR": "logs/"
      }
    }
  }
}
```

Variante local-S2 (misma key ausente = sin auth en loopback):

```json
{
  "mcp": {
    "jav": {
      "type": "local",
      "command": ["$HOME/jev-android-mcp/dist/jav-linux-amd64"],
      "enabled": true,
      "environment": {
        "JAV_WS_URL": "ws://127.0.0.1:38472/",
        "JAV_TOKEN": "",
        "OPENROUTER_API_KEY": "",
        "JEV_MODEL": "typesafe/jev-1.13",
        "JAV_AI_BASE_URL": "http://127.0.0.1:11434/v1",
        "JAV_AI_MODEL": "modelo-local",
        "JAV_LOG_DIR": "logs/"
      }
    }
  }
}
```

### 4.2 Claude Desktop (`claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "jav": {
      "command": "/home/user/jev-android-mcp/dist/jav-linux-amd64",
      "env": {
        "JAV_WS_URL": "ws://127.0.0.1:38472/",
        "JAV_TOKEN": "",
        "OPENROUTER_API_KEY": "",
        "JEV_MODEL": "typesafe/jev-1.13",
        "JAV_AI_BASE_URL": "https://openrouter.ai/api/v1",
        "JAV_AI_MODEL": "z-ai/glm-5.3-flash",
        "S2_MODEL": "z-ai/glm-5.3-flash"
      }
    }
  }
}
```

### 4.3 Cursor (`~/.cursor/mcp.json` o `.cursor/mcp.json`)

```json
{
  "mcpServers": {
    "jav": {
      "command": "/home/user/jev-android-mcp/dist/jav-linux-amd64",
      "env": {
        "JAV_WS_URL": "ws://127.0.0.1:38472/",
        "JAV_TOKEN": "",
        "OPENROUTER_API_KEY": "",
        "JEV_MODEL": "typesafe/jev-1.13",
        "JAV_AI_BASE_URL": "https://openrouter.ai/api/v1",
        "JAV_AI_MODEL": "z-ai/glm-5.3-flash",
        "S2_MODEL": "z-ai/glm-5.3-flash",
        "JAV_LOG_DIR": "logs/"
      }
    }
  }
}
```

### 4.4 Termux (teléfono como host)

```sh
# Binario arm64; misma ruta o ~/.local/bin/jav
curl -fsSL https://raw.githubusercontent.com/k4wai1/jav/master/install.sh | sh
# o copia dist/jav-linux-arm64 al teléfono y renómbralo a jav.

export JAV_WS_URL="ws://127.0.0.1:38472/"
export JAV_TOKEN=""            # del QR de Jam
export OPENROUTER_API_KEY=""   # S1 (requerida para resolver)
export JEV_MODEL="typesafe/jev-1.13"
export JAV_AI_BASE_URL="http://127.0.0.1:11434/v1"  # S2 local sin auth…
export JAV_AI_MODEL="modelo-local"                  # …o https://openrouter.ai/api/v1
export JAV_LOG_DIR="logs/"
jav  # stdio: conéctalo como servidor local desde tu cliente MCP
```

En Termux el cliente MCP (opencode) usa el bloque §4.1 con la ruta del
binario arm64 y las mismas variables. S2 Termux-local = `JAV_AI_BASE_URL`
en loopback sin key (ver `ai-providers.md` §3).

## 5. Verificación

```sh
go build ./... && go vet ./...   # limpio, sin warnings
go test ./...                     # verde
```

Smoke sin Jam: `device_status` → `{ok:false,…}` honesto con hint
(no cuelgue, no pánico). Con Jam: `adb forward tcp:38472 tcp:38472`
(es automático ante `connection refused` en loopback) + `device_status`
→ scopes + `app_version` + foreground.

## 6. Seguridad (resumen operativo)

- Token bearer obligatorio en todos los binds, loopback incluido.
- `ws` solo en loopback; fuera de loopback, WSS obligatorio + nunca `0.0.0.0` por defecto.
- Logs/`[COST]`/`[S2]` solo a stderr; stdout es JSON-RPC puro.
- `.env` y configs con secretos: `chmod 600`, nunca commitear.
- `shell` on-device: `METHOD_NOT_ALLOWED` hasta Fase 6 (el `dumpsys`/`wm size`/`forward` corren en el host adb, no en el teléfono).
