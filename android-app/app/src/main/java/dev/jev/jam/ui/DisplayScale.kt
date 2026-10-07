package dev.jev.jam.ui

/**
 * Proyección de coordenadas de accesibilidad (espacio lógico) a píxeles
 * físicos del panel para `dispatchGesture`.
 *
 * Contexto: `AccessibilityNodeInfo.getBoundsInScreen` devuelve bounds en el
 * espacio lógico del WindowManager (afectado por `wm size override`), mientras
 * que `dispatchGesture` consume píxeles físicos del panel. En el 5002E:
 * lógico 360x720 (override) vs físico 720x1440 → factor 2.0 por eje.
 *
 * Fórmula (por eje, con redondeo al entero más próximo y clamp fuera):
 *   x_phys = round(x_log * physW / logW)
 *   y_phys = round(y_log * physH / logH)
 * con enteros exactos: `(x * phys + log/2) / log` (long intermedio).
 * Si logW/logH <= 0 o phys==log (sin override) → identidad.
 *
 * `bounds` de `dump_ui` se queda en espacio lógico (verdad de a11y);
 * solo el gesto se proyecta. Densidad no interviene: ambos espacios ya
 * están en píxeles, no en dp.
 */
object DisplayScale {

    data class Viewport(val logicalW: Int, val logicalH: Int, val physicalW: Int, val physicalH: Int)

    fun scaleFactors(vp: Viewport): Pair<Float, Float> {
        if (vp.logicalW <= 0 || vp.logicalH <= 0) return 1f to 1f
        return (vp.physicalW.toFloat() / vp.logicalW.toFloat()) to
            (vp.physicalH.toFloat() / vp.logicalH.toFloat())
    }

    fun projectX(x: Int, logicalW: Int, physicalW: Int): Int {
        if (logicalW <= 0 || physicalW == logicalW) return x
        return ((x.toLong() * physicalW + logicalW / 2) / logicalW).toInt()
    }

    fun projectY(y: Int, logicalH: Int, physicalH: Int): Int {
        if (logicalH <= 0 || physicalH == logicalH) return y
        return ((y.toLong() * physicalH + logicalH / 2) / logicalH).toInt()
    }

    fun project(x: Int, y: Int, vp: Viewport): Pair<Int, Int> {
        val px = projectX(x, vp.logicalW, vp.physicalW).coerceIn(0, (vp.physicalW - 1).coerceAtLeast(0))
        val py = projectY(y, vp.logicalH, vp.physicalH).coerceIn(0, (vp.physicalH - 1).coerceAtLeast(0))
        return px to py
    }
}
