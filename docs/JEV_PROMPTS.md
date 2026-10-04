# JEV_PROMPTS.md — preguntas tipadas del bucle genérico (Dual-Tier v2)

> Regla madre: Jev elige claves de `criteria`, nunca genera texto ni
> coordenadas. Sin key el stub devuelve happy-path (primer criterio /
> `true` / nivel máximo). Los dominios concretos viven en plugins
> (`tasks/<dominio>.py`); aquí solo el formato genérico.
> Ejemplo no-normativo (único): un plugin de mensajería.

## Gotcha: `clickable` NO es señal de elección

Medido en Fase 4: campos de búsqueda reales pueden no ser `clickable`
y resolverse por fallback a gesto (`via=gesture`). Las preguntas a Jev
**nunca** deben ponderar `clickable=true` como requisito; se elige por
`text`/`content_desc`/`resource_id`, y el ejecutor resuelve el `via`.
El prefilter del bucle tampoco exige clickable.

## Formato común (batch single-pass: 3 preguntas por llamada)

```json
{
  "model": "typesafe/jev-1.13",
  "state": {"package": "<genérico>", "phase": "LOCATE", "step": 4,
            "history": ["tap n_84 ok", "type n_46 ok"],
            "candidates": ["[n_96] TextView \"…\"", "..."]},
  "questions": {
    "next_action": {"type": "choice", "instructions": "...",
                    "criteria": {"tap:n_96": "[n_96] ...",
                                 "type:n_46": "[n_46] ...",
                                 "done": "...", "escalate": "...",
                                 "abort": "..."}},
    "last_ok": {"type": "noul", "instructions": "¿...?",
                "criteria": {"true": "...", "false": "..."}},
    "progress": {"type": "score", "instructions": "...",
                 "criteria": ["0%", "25%", "50%", "75%", "100%"]}
  }
}
```

`next_action` (Choice, ≤255 con `NONE`) lleva `conf` calibrada;
`conf < TAU` (default ~0.70, parametrizado por plugin) → `escalate`.
`last_ok` (Noul) señala bloqueos semánticos → `escalate`.
`progress` (Score) detecta estancamiento → `escalate`.

## Las fases genéricas (el plugin define las suyas sobre este esqueleto)

| Fase genérica | `next_action` (choice) | `criteria` |
| :--- | :--- | :--- |
| LOCATE | ¿Qué candidato abre / localiza el contexto? | `tap:<id>` por trigger + `escalate` + `abort` |
| FOCUS / TYPE | Campo enfocado → escribir; si no, tocar primero | `type:<id>` o `tap:<id>` + `escalate` + `abort` |
| PICK | ¿Qué candidato es el objetivo (máx N)? | `tap:<id>` por match + `escalate` + `abort` |
| VERIFY_CONTEXT | ¿El título/contexto es el correcto (match estricto)? | `proceed` / `tap:<otro>` (reintento ≤2, solo fuera de contexto ajeno) / `escalate` / `abort` |
| ACT | ¿Qué candidato ejecuta la acción (ignora señuelos/forbidden)? | `tap:<id>` (máx N) + `escalate` + `abort` |
| VERIFY | ¿La pantalla muestra el efecto esperado? | `done` / `escalate` / `abort` (más check determinista) |

`last_ok` (noul) y `progress` (score) acompañan siempre en el mismo batch.
Toda acción sensible (`is_sensitive`) va en `dry_run` planeada sin ejecutar
hasta compuerta verde.

## Ejemplo real (forma, sin dominio)

```
step 1 LOCATE opts=['tap:n_84', 'tap:n_108', 'escalate', 'abort'] -> tap:n_84 (action_click)
step 2 FOCUS  opts=['tap:n_46', 'escalate', 'abort'] -> tap:n_46 (focus)
step 3 PICK   opts=['type:n_46', 'escalate', 'abort'] -> type "…" (chars=N)
step 4 VERIFY_CONTEXT opts=['tap:n_96', ..., 'escalate', 'abort'] -> escalate LOW_CONF
step 5 VERIFY_CONTEXT opts=['abort', 'escalate'] -> abort WRONG_CONTEXT (sin título, sin tapear)
```

El invariante `WRONG_CONTEXT` para antes de actuar en contexto ajeno.
Con Jev real, el paso 4 elige entre candidatas reales o escala por `tau`.

## Variantes de nombre (mecanismo genérico, sin literales)

El prefilter normaliza (NFKD, sin tildes, minúsculas) + esqueleto
consonántico (parametrizado en `core/text_match.py`). Ante múltiples,
el plugin define el desempate (p.ej. más reciente primero); la compuerta
estricta del título (`title_matches_strict`) decide el contexto final,
no el match previo.
