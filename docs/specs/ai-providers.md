# ai-providers — S1 fijo Jev vs S2 agnóstico OpenAI-compatible

> Estado: **spec normativo 2026-10-08**. Redacta `@architect`,
> implementa `@coder`, certifica `@judge`. En conflicto, **AGENTS.md manda**.
>
> Fuentes leídas: `pkg/jev/jev.go` (S1 decisions + `JEV_MODEL` +
> `IsMock`), `pkg/director/director.go` (S2 `s2Endpoint` + `S2ModelID` +
> `IsMockS2`), `pkg/cost/cost.go` (tasas Jev + placeholder S2),
> `.env.example`, `docs/specs/go-migration-plan.md` §§6.4–6.6/8,
> `docs/specs/generic-dual-tier.md` §6, `docs/specs/director-client.md` §3.
>
> 100% genérico: cero paquetes concretos, cero literales de dominio,
> cero keys en este documento.

## 0. Verdad arquitectónica innegociable

**Jev NO es intercambiable con GPT.** S1 es un clasificador
discriminativo: expone una API de decisiones (`Choice`/`Noul`, con
distribución `probabilities` + `confidence` validada de forma estricta)
y no genera texto libre. Ningún `gpt-4o-mini`, `qwen` ni ningún otro
LLM autoregresivo puede ocupar su lugar, porque **no exponen esa API**:
no devuelven `choice ∈ criteria` con `probabilities` completa, suma
±0.025 y argmax, y por tanto jamás pasan `ValidateChoice`
(`pkg/jev/jev.go:111`). Intentar "enchufar" un chat-model como S1 no
degrada la calidad: **rompe el contrato** (`JevHallucination` honesto).

El proveedor agnóstico OpenAI-compatible (`chat/completions`) aplica
**SOLO a S2 / director + texto**: el que redacta `text_payload`,
comandos ejecutables y veredictos `verify_done`. S2 sí es
intercambiable; S1 nunca.

## 1. S1 fijo — resolver Jev (no agnóstico, no opcional)

| Aspecto | Valor normativo |
|---|---|
| Qué es | Clasificador discriminativo Choice/Noul, API de decisiones |
| Endpoint v1 | `POST https://openrouter.ai/api/alpha/decisions` (const `Endpoint`, `pkg/jev/jev.go:19`) |
| Swap futuro | API oficial TypeSafe (`TYPESAFE_BASE_URL`, modelo `jev-latest`); solo cuando `@coder` lo cablee. Hoy **no** está en el Go (solo en `.env.example` como reserva) |
| Modelo | Env `JEV_MODEL`, default **`typesafe/jev-1.13`** (`pkg/jev/jev.go:38`) |
| Key | **`OPENROUTER_API_KEY`** (requerida). Es la ÚNICA key que S1 acepta |
| `JAV_AI_*` | **No aplican a S1. Nunca.** `JAV_AI_BASE_URL` / `JAV_AI_API_KEY` / `JAV_AI_MODEL` solo alimentan S2; `pkg/jev` no los lee |
| Timeout | ~3 s + 1 retry (`Timeout`, `pkg/jev/jev.go:20`) |
| Validación | `ValidateChoice` estricta: `choice ∈ criteria`, `probabilities` dict completa, conf/probs finitas `[0,1]`, suma ±0.025, `choice` = argmax. Fallo → `JevHallucination`, nunca actuar |
| Tarifas | Normativas `0.042 in / 0.0 out` USD por MTok, overrides en vivo `JEV_RATE_IN` / `JEV_RATE_OUT` (`pkg/cost/cost.go:14`) |

### 1.1 Sin key → resolver desactivado, error honesto

Sin `OPENROUTER_API_KEY`, el path director **`resolve_element` queda
desactivado**: devuelve error honesto (código `S1_UNAVAILABLE` /
`JEV_UNAVAILABLE` con hint "rellena `OPENROUTER_API_KEY`"), **nunca un
`idx` inventado**. El stub `{mock:true}` heredado de `IsMock`
(`pkg/jev/jev.go:46`) existe solo como plomería offline/tests del
decisor legacy congelado; **no es una resolución válida** y ningún
tap/type puede ejecutarse sobre él.

## 2. S2 agnóstico — director + texto (OpenAI-compatible)

S2 habla `POST {base}/chat/completions` con `{model, messages, temperature,
max_tokens}` y parsea `choices[0].message.content` como objeto JSON.
Cualquier servidor que cumpla ese shape sirve, local o remoto.

| Variable | Default / resolución | Notas |
|---|---|---|
| `JAV_AI_BASE_URL` | Default **`https://openrouter.ai/api/v1`** (el path de llamada es `{base}/chat/completions`) | Apunta a OpenRouter, Ollama, vLLM, DeepSeek-direct, OpenAI-direct o Termux-local según el operador |
| `JAV_AI_API_KEY` | **Opcional.** Orden: `JAV_AI_API_KEY` → fallback `OPENROUTER_API_KEY` → ninguna | Sin ninguna key contra base **local** (loopback/`localhost`) → permitido sin auth. Sin ninguna key contra base **remota** → error honesto, nunca reintento mudo ni stub silencioso |
| `JAV_AI_MODEL` | Default = **el S2 vigente por env** (cadena §2.1, nunca hardcodeado a un vendor) | Retrocompat: la cadena histórica sigue mandando si `JAV_AI_MODEL` está vacío |
| `S2_MODEL` / `GLM_MODEL` | Retrocompat (hoy la única vía cableada en Go) | `S2_MODEL` manda sobre `GLM_MODEL`; ambas valen como alias mientras `@coder` cablea `JAV_AI_*` |
| Timeout | 15 s + 1 retry (const `s2Timeout`, `pkg/director/director.go:349`) | Sin cambio |
| Tarifas | `GLM_RATE_IN` / `GLM_RATE_OUT` en vivo (defaults = placeholder ajustable contra factura, nunca verdad oficial) | `pkg/cost/cost.go:18`; el nombre histórico se conserva aunque el modelo ya no sea GLM |

### 2.1 Cadena de resolución del modelo S2 (orden)

```
JAV_AI_MODEL → S2_MODEL → GLM_MODEL → z-ai/glm-5.3-flash
```

Vacío en los cuatro → default final `z-ai/glm-5.3-flash`
(`s2DefaultModel`, `pkg/director/director.go:350`). `RATES` y
`rates_for` resuelven en vivo; el default en código es foto, no verdad.

### 2.2 Estado de implementación honesto (Go v1)

`go-migration-plan.md` §6.5 fija **solo OpenRouter en v1**: el Go hoy
cablea `s2Endpoint = https://openrouter.ai/api/v1/chat/completions`
con la misma `OPENROUTER_API_KEY` que S1 y modelo `S2_MODEL`/`GLM_MODEL`.
**`JAV_AI_*` es contrato normativo a cablear por `@coder`, no código
existente** (grep `JAV_AI_` en `cmd/`+`pkg/` → vacío a 2026-10-08).
Hasta que esté cableado, la vía operativa S2 es
`OPENROUTER_API_KEY` + `S2_MODEL`; este spec fija hacia dónde se
converge sin romperla.

## 3. Tabla qué-puede-ser-qué (ejemplos REALES)

| Slot | Válido | PROHIBIDO (falla honesto, nunca fallback silencioso) |
|---|---|---|
| **S1 modelo** (`JEV_MODEL`) | `typesafe/jev-1.13` (vía OpenRouter decisions); `jev-latest` (vía API oficial TypeSafe, swap futuro) | `gpt-4o-mini`, `qwen-*`, `deepseek-*`, `glm-*`, cualquier chat-model OpenAI-compatible: **no exponen la API de decisiones** → `JevHallucination` |
| **S1 endpoint** | `https://openrouter.ai/api/alpha/decisions`; `TYPESAFE_BASE_URL` oficial (futuro) | `…/chat/completions` de Ollama/vLLM/OpenAI/DeepSeek: shape equivocado, nunca S1 |
| **S1 key** | `OPENROUTER_API_KEY` (hoy); `TYPESAFE_API_KEY` (con el swap futuro) | `JAV_AI_API_KEY`: S1 no la lee |
| **S2 vía OpenRouter** | `JAV_AI_BASE_URL=https://openrouter.ai/api/v1` + `JAV_AI_MODEL=z-ai/glm-5.3-flash`; o `JAV_AI_MODEL=deepseek/deepseek-chat` (slug OpenRouter, misma key) | — |
| **S2 vía OpenAI-direct** | `JAV_AI_BASE_URL=https://api.openai.com/v1` + `JAV_AI_MODEL=gpt-4o-mini` + `JAV_AI_API_KEY=<key>` | `gpt-4o-mini` **como S1**: prohibido (§0) |
| **S2 vía DeepSeek-direct** | `JAV_AI_BASE_URL=https://api.deepseek.com` + `JAV_AI_MODEL=deepseek-chat` + `JAV_AI_API_KEY=<key>` | Histórica: el provider DeepSeek-direct se eliminó del Python; en Go vuelve SOLO como instancia S2 agnóstica, jamás como S1 |
| **S2 local Ollama** | `JAV_AI_BASE_URL=http://127.0.0.1:11434/v1` + `JAV_AI_MODEL=<modelo-local>` sin `JAV_AI_API_KEY` (sin auth en loopback) | Exponer el Ollama fuera de loopback sin auth: prohibido (misma regla que binds §3) |
| **S2 local vLLM** | `JAV_AI_BASE_URL=http://127.0.0.1:8000/v1` + `JAV_AI_MODEL=<modelo-servido>` sin key si el servidor no exige auth | — |
| **S2 Termux-local** | `JAV_AI_BASE_URL=http://127.0.0.1:<puerto>/v1` + modelo servido en el propio teléfono, sin key | El teléfono como servidor S2 no cambia el threat model del `shell` on-device (sigue `METHOD_NOT_ALLOWED` hasta Fase 6) |

Lectura de la tabla: **todo lo que es un chat-model OpenAI-compatible
puede ser S2; nada de eso puede ser S1.** La columna S1 tiene
exactamente dos valores (uno vigente, uno futuro); la columna S2 está
abierta por diseño.

## 4. Errores honestos (contrato)

- S1 sin key en path director → `S1_UNAVAILABLE`/`JEV_UNAVAILABLE` + hint de key. Nunca `idx`, nunca tap.
- S1 con chat-model como `JEV_MODEL` → `JevHallucination` (distribución inválida), nunca actuar.
- S2 sin key contra base remota → error honesto de auth/config, nunca stub silencioso.
- S2 `content` vacío / sin objeto `{…}` tras reintento → `S2EmptyResponse`; comando fuera de esquema → `S2BadCommand`. Ambos ya existen en `pkg/director` y valen para cualquier base.
- S2 nunca toca el dispositivo, sea cual sea el proveedor.

## 5. Aceptación (`@judge`, sin editar)

1. `grep -rn 'JAV_AI_' cmd/ pkg/ --include='*.go'` → S1 (`pkg/jev`) **vacío**: S1 no lee `JAV_AI_*`.
2. `JEV_MODEL` solo acepta slugs Jev documentados en §3; test con `JEV_MODEL=gpt-4o-mini` (u otro chat-model) → `JevHallucination`, cero mutaciones.
3. `resolve_element` sin `OPENROUTER_API_KEY` → error honesto, nunca `{idx}` utilizable.
4. S2 contra base local sin key (stub de `chat/completions` en loopback) → comando válido parseado; contra base remota sin key → error honesto.
5. Cadena §2.1: cada nivel de la cadena gana al siguiente (test por env).
6. `uv`-equivalente Go: `go test ./...` verde antes y después.
