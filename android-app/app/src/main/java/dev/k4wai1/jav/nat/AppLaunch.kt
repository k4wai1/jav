package dev.k4wai1.jav.nat

/**
 * Parsers puros de `open_app` (v2.3.1), separados de Shizuku para poder
 * testearlos en JVM sin dispositivo.
 *
 * Antes `open_app` dependía solo de `monkey`, que aborta (exit 252) cuando
 * Shizuku corre como **root (uid 0)** o cuando la app está congelada. El
 * camino nuevo resuelve el componente launcher y lanza con
 * `am start --user 0 -n`.
 */
object AppLaunch {

    /**
     * Extrae `<pkg>/<activity>` de la salida de
     * `cmd package resolve-activity --brief --user 0 -a MAIN -c LAUNCHER <pkg>`.
     *
     * Salida típica:
     * ```
     * priority=0 preferredOrder=0 match=0x108000 specificIndex=-1 isDefault=false
     *   com.example/.MainActivity
     * ```
     */
    fun parseComponent(out: String): String? =
        out.lineSequence()
            .map { it.trim() }
            .lastOrNull { it.contains("/") && !it.startsWith("priority=") && it.isNotBlank() }

    /**
     * `pm list packages -d` lista paquetes deshabilitados; Hail/icebox usan
     * `pm disable-user`, así que aparecen aquí. Comparación exacta por
     * línea (`package:<pkg>`) para no confundir prefijos.
     */
    fun isDisabledIn(disabledListOutput: String, pkg: String): Boolean =
        disabledListOutput.lineSequence().any { it.trim() == "package:$pkg" }
}
