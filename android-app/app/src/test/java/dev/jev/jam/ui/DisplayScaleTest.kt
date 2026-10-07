package dev.jev.jam.ui

import org.junit.Assert.assertEquals
import org.junit.Test

/**
 * Proyección lógico→físico para `dispatchGesture` (bug 5002E:
 * override 360x720 vs panel 720x1440). JVM puro, sin Robolectric.
 */
class DisplayScaleTest {

    private val a10 = DisplayScale.Viewport(360, 720, 720, 1440)

    @Test
    fun `factor 2 en A10`() {
        val (sx, sy) = DisplayScale.scaleFactors(a10)
        assertEquals(2f, sx, 0.001f)
        assertEquals(2f, sy, 0.001f)
    }

    @Test
    fun `centroide y2mate se duplica`() {
        // Fallo medido: centroide lógico iba directo al gesto (mitad de pantalla).
        assertEquals(360 to 1200, DisplayScale.project(180, 600, a10))
        assertEquals(0 to 0, DisplayScale.project(0, 0, a10))
        assertEquals(719 to 1439, DisplayScale.project(360, 720, a10)) // clamp a físico-1
    }

    @Test
    fun `identidad sin override`() {
        val vp = DisplayScale.Viewport(720, 1440, 720, 1440)
        assertEquals(100 to 200, DisplayScale.project(100, 200, vp))
    }

    @Test
    fun `ejes independientes`() {
        val vp = DisplayScale.Viewport(360, 720, 720, 1440)
        assertEquals(2, DisplayScale.projectX(1, vp.logicalW, vp.physicalW))
        assertEquals(2, DisplayScale.projectX(1, 360, 720))
        assertEquals(2, DisplayScale.projectY(1, 720, 1440))
    }

    @Test
    fun `viewport invalido no escala`() {
        val vp = DisplayScale.Viewport(0, 0, 720, 1440)
        assertEquals(50 to 60, DisplayScale.project(50, 60, vp))
    }
}
