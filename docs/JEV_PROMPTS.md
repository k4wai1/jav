# JEV_PROMPTS.md — preguntas tipadas del bucle WhatsApp

> Regla madre: Jev elige claves de `criteria`, nunca genera texto ni
> coordenadas. Sin `OPENROUTER_API_KEY` el stub devuelve happy-path
> (primer criterio / `true` / nivel máximo). Todo ejemplo de abajo es
> de corridas reales contra WhatsApp (LG7n).

## Gotcha: `clickable` NO es señal de elección

Medido en Fase 4: el campo "Buscar…" de WhatsApp **no es `clickable`**
y se toca por fallback a gesto (`via=gesture`). Las preguntas a Jev
**nunca** deben ponderar `clickable=true` como requisito; se elige por
`text`/`content_desc`, y el ejecutor resuelve el `via`. El prefilter del
bucle tampoco exige clickable (ver `is_search_trigger`).

## Formato común (batch: 3 preguntas por llamada)

```json
{
  "model": "typesafe/jev-1.13",
  "state": {"app": "com.whatsapp", "phase": "PICK", "step": 4,
            "history": ["tap n_84 ok", "type n_46 ok"],
            "candidates": ["[n_96] TextView \"Félex\"", "..."]},
  "questions": {
    "next_action": {"type": "choice", "instructions": "...",
                    "criteria": {"tap:n_96": "[n_96] ...", "abort": "..."}},
    "last_ok": {"type": "noul", "instructions": "¿...?",
                "criteria": {"true": "...", "false": "..."}},
    "progress": {"type": "score", "instructions": "...",
                 "criteria": ["0%", "25%", "50%", "75%", "100%"]}
  }
}
```

## Las 6 preguntas (una por fase)

| Fase | `next_action` (choice) | `criteria` |
| :--- | :--- | :--- |
| SEARCH | ¿Qué candidato abre la búsqueda? | `tap:<id>` por trigger + `abort` |
| TYPE_CONTACT | Campo enfocado → escribir; si no, tocar primero | `type:<id>` o `tap:<id>` + `abort` |
| PICK | ¿Qué candidato es el chat de `{contact}`? Si varios, el primero (más reciente); evita `(trabajo)` | `tap:<id>` por match (máx 5) + `abort` |
| VERIFY_CHAT | ¿El título es el chat correcto? | `proceed` / `tap:<otro>` (reintento ≤2, solo fuera de chats) / `abort` |
| FOCUS_MSG / TYPE_MSG | Tocar o escribir en el campo del mensaje | `tap:<id>` / `type:<id>` + `abort` |
| SEND | ¿Qué candidato envía? (send/Enviar; ignora mic/adjuntar/reenviar) | `tap:<id>` (máx 3) + `abort` |
| VERIFY | ¿Muestra el chat el mensaje? | `done` / `abort` (más check determinista) |

`last_ok` (noul) y `progress` (score) acompañan siempre en el mismo batch.

## Ejemplo real (dry-run stub, 2026-10-02)

```
step 1 SEARCH opts=['tap:n_84', 'tap:n_108', 'abort'] -> tap:n_84 (action_click)
step 2 TYPE_CONTACT opts=['tap:n_46', 'abort'] -> tap:n_46 (focus)
step 3 PICK opts=['type:n_46', 'abort'] -> type "Felix" (chars=5)
step 4 VERIFY_CHAT opts=['tap:n_96', ..., 'abort'] -> tap:n_96
step 5 VERIFY_CHAT opts=['abort'] -> abort WRONG_CHAT (sin título)
```

El stub elige siempre la primera opción y aun así el invariante
`WRONG_CHAT` paró antes de escribir en el chat. Con Jev real, el paso 4
elige entre candidatos reales y el 5 confirma por título.

## Variantes de nombre (caso Felix)

El contacto aparece como **"Félex"** (tilde) y el usuario escribe
"felix" o "felex". El prefilter normaliza (NFKD, sin tildes, minúsculas)
+ esqueleto consonántico (`flx` casa con ambas). Ante múltiples, manda
el último hablado (orden de resultados); la compuerta estricta del
título (`title_matches_strict`) decide el chat final, no el match previo.
