package dev.k4wai1.jav.net

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Rango CGNAT Tailscale `100.64.0.0/10` (Fase 2b) y alias histórico;
 * v2.1.0 lo expone [NetworkDetector] (tailnet + LAN RFC 1918).
 */
class TailnetDetectorTest {

    @Test
    fun aceptaLosLimitesDelRango() {
        assertTrue(NetworkDetector.isTailnetIpv4("100.64.0.0"))
        assertTrue(NetworkDetector.isTailnetIpv4("100.64.0.1"))
        assertTrue(NetworkDetector.isTailnetIpv4("100.100.50.7"))
        assertTrue(NetworkDetector.isTailnetIpv4("100.127.255.255"))
    }

    @Test
    fun rechazaFueraDelRango() {
        assertFalse(NetworkDetector.isTailnetIpv4("100.63.255.255"))
        assertFalse(NetworkDetector.isTailnetIpv4("100.128.0.0"))
        assertFalse(NetworkDetector.isTailnetIpv4("10.0.0.1"))
        assertFalse(NetworkDetector.isTailnetIpv4("192.168.1.1"))
        assertFalse(NetworkDetector.isTailnetIpv4("127.0.0.1"))
        assertFalse(NetworkDetector.isTailnetIpv4("0.0.0.0"))
    }

    @Test
    fun rechazaEntradasInvalidas() {
        assertFalse(NetworkDetector.isTailnetIpv4(""))
        assertFalse(NetworkDetector.isTailnetIpv4("100.64"))
        assertFalse(NetworkDetector.isTailnetIpv4("100.64.0"))
        assertFalse(NetworkDetector.isTailnetIpv4("100.64.0.256"))
        assertFalse(NetworkDetector.isTailnetIpv4("100.a.0.1"))
        assertFalse(NetworkDetector.isTailnetIpv4("::1"))
        assertFalse(NetworkDetector.isTailnetIpv4("100.64.0.1.5"))
    }
}
