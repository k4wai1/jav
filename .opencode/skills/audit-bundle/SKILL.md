---
name: audit-bundle
description: Regenera el paquete de auditoría externa del repo Jav en la raíz: jav-audit.zip sin compresión (código + docs + configs; sin binarios ni secretos), jav-audit.txt con el mismo contenido en texto plano concatenado y jav-tree.txt con el árbol completo. Úsala cuando el usuario diga "actualiza el zip", "regenera el paquete de auditoría", "actualiza el tree", pida el bundle para una auditoría externa o necesite el código en un bloque de texto legible.
---

# audit-bundle

Genera los dos artefactos de auditoría en la raíz del repo:

| Artefacto | Contenido |
| --- | --- |
| `jav-audit.zip` | ZIP **sin compresión** (`zip -0 -X`) con el código, docs y configs relevantes. Incluye `AUDIT-MANIFEST.txt` (versión, commit, fecha, nº de archivos, sha256 por archivo y exclusiones justificadas). |
| `jav-audit.txt` | **Volcado en texto plano concatenado** del mismo conjunto de archivos, para auditores que no abren ZIP. Cada archivo va precedido por `===== <ruta> =====`; contenido literal, sin numeración de línea. |
| `jav-tree.txt` | Árbol completo del proyecto (`tree -a -h`) con cabecera de versión/commit/fecha. |

Los tres están en `.gitignore`: **nunca se commitean**.

## Cuándo usarla

- "actualiza el zip"
- "regenera el paquete de auditoría"
- "actualiza el tree" / "tree del proyecto"
- Cualquier petición de empaquetar el repo para revisión externa.
- "Pásame el código en un txt" / auditor que no abre ZIP → `jav-audit.txt`.

## Cómo ejecutarla

Desde la raíz del repo (el script resuelve la raíz con `git rev-parse --show-toplevel`):

```bash
bash .opencode/skills/audit-bundle/audit-bundle.sh
```

El script es idempotente: sobrescribe los dos artefactos. Tarda ~1 s.

## Reglas duras

1. **No añadir binarios ni artefactos**: `dist/`, `build/`, `.gradle/`, `node_modules/`, `*.png|svg|jar|apk|pdf`… quedan fuera por diseño.
2. **No añadir secretos**: `.env`, `local.properties`, `google-services.json`, `*.keystore|jks|p12`. El script tiene una compuerta que **aborta sin generar nada** si detecta alguno en la lista final. Si aborta, no lo rodees: reporta el archivo y corrige la exclusión.
3. **No commitear** `jav-audit.zip`, `jav-audit.txt` ni `jav-tree.txt`.
4. Si cambian las reglas de qué entra en la auditoría, se edita el script (listas `EXCLUDE_RE`, `EXCLUDE_EXT_RE`, `SECRET_RE`) y se actualiza este documento; no se hace a mano cada vez.

## Verificación y reporte

El script ya verifica: nº de entradas del ZIP = nº de archivos + manifiesto, nº de secciones del dump = mismo total, y ausencia de patrones de secreto dentro del ZIP. Al terminar imprime ruta, tamaño, nº de archivos/líneas y `sha256` de los tres artefactos.

Reporta al usuario exactamente eso, en este formato:

```
jav-audit.zip  <tamaño>  <N> archivos  sha256:<hash>
jav-audit.txt  <tamaño>  <L> líneas    sha256:<hash>
jav-tree.txt   <tamaño>  <M> líneas    sha256:<hash>
```
