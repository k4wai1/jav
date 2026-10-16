package dev.k4wai1.jav.net

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/** Fase 2b: rango CGNAT Tailscale `100.64.0.0/10`. */
class TailnetDetectorTest {

    @Test
    fun aceptaLosLimitesDelRango() {
        assertTrue(TailnetDetector.isTailnetIpv4("100.64.0.0"))
        assertTrue(TailnetDetector.isTailnetIpv4("100.64.0.1"))
        assertTrue(TailnetDetector.isTailnetIpv4("100.100.50.7"))
        assertTrue(TailnetDetector.isTailnetIpv4("100.127.255.255"))
    }

    @Test
    fun rechazaFueraDelRango() {
        assertFalse(TailnetDetector.isTailnetIpv4("100.63.255.255"))
        assertFalse(TailnetDetector.isTailnetIpv4("100.128.0.0"))
        assertFalse(TailnetDetector.isTailnetIpv4("10.0.0.1"))
        assertFalse(TailnetDetector.isTailnetIpv4("192.168.1.1"))
        assertFalse(TailnetDetector.isTailnetIpv4("127.0.0.1"))
        assertFalse(TailnetDetector.isTailnetIpv4("0.0.0.0"))
    }

    @Test
    fun rechazaEntradasInvalidas() {
        assertFalse(TailnetDetector.isTailnetIpv4(""))
        assertFalse(TailnetDetector.isTailnetIpv4("100.64"))
        assertFalse(TailnetDetector.isTailnetIpv4("100.64.0"))
        assertFalse(TailnetDetector.isTailnetIpv4("100.64.0.256"))
        assertFalse(TailnetDetector.isTailnetIpv4("100.a.0.1"))
        assertFalse(TailnetDetector.isTailnetIpv4("::1"))
        assertFalse(TailnetDetector.isTailnetIpv4("100.64.0.1.5"))
    }
}
