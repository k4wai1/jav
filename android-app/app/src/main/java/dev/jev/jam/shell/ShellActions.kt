package dev.jev.jam.shell

import dev.jev.jam.socket.JamError

/**
 * Operaciones Shizuku que NO requieren AccessibilityService.
 * (Las que sí la requieren —verificación por dump— viven en el servicio.)
 * Sin accesibilidad estas siguen funcionando (degradación honesta).
 */
object ShellActions {

    const val SELF_PACKAGE = "dev.jev.jam"

    fun forceStop(pkg: String) {
        if (pkg.isBlank()) throw JamError("package vacío", "VALIDATION_ERROR")
        if (pkg == SELF_PACKAGE) {
            throw JamError("no me puedo cerrar a mí mismo", "VALIDATION_ERROR")
        }
        val r = ShizukuBridge.exec(listOf("am", "force-stop", pkg))
        if (r.exitCode != 0) {
            throw JamError("force-stop falló: ${r.stderr.take(200)}", "INTERNAL_ERROR")
        }
    }
}
