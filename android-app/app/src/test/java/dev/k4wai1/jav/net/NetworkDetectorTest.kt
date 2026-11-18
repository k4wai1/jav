package dev.k4wai1.jav.net

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/** v2.1.0: rangos bindeables (tailnet CGNAT + RFC 1918) sin `0.0.0.0`. */
class NetworkDetectorTest {

    @Test
    fun rfc1918Validas() {
        assertTrue(NetworkDetector.isRfc1918Ipv4("10.0.0.1"))
        assertTrue(NetworkDetector.isRfc1918Ipv4("10.255.255.255"))
        assertTrue(NetworkDetector.isRfc1918Ipv4("172.16.0.1"))
        assertTrue(NetworkDetector.isRfc1918Ipv4("172.31.255.254"))
        assertTrue(NetworkDetector.isRfc1918Ipv4("192.168.1.40"))
    }

    @Test
    fun rfc1918Invalidas() {
        assertFalse(NetworkDetector.isRfc1918Ipv4("172.15.0.1"))
        assertFalse(NetworkDetector.isRfc1918Ipv4("172.32.0.1"))
        assertFalse(NetworkDetector.isRfc1918Ipv4("192.169.0.1"))
        assertFalse(NetworkDetector.isRfc1918Ipv4("100.64.0.1"))
        assertFalse(NetworkDetector.isRfc1918Ipv4("8.8.8.8"))
        assertFalse(NetworkDetector.isRfc1918Ipv4("192.168.1"))
    }

    @Test
    fun bindableIncluyeTailnetYRechazaEspeciales() {
        assertTrue(NetworkDetector.isBindableIpv4("100.100.50.7")) // tailnet
        assertTrue(NetworkDetector.isBindableIpv4("192.168.1.40")) // LAN
        assertFalse(NetworkDetector.isBindableIpv4("0.0.0.0"))
        assertFalse(NetworkDetector.isBindableIpv4("127.0.0.1"))
        assertFalse(NetworkDetector.isBindableIpv4("169.254.1.1"))
        assertFalse(NetworkDetector.isBindableIpv4("8.8.8.8"))
    }

    @Test
    fun detectAllNuncaDevuelveLoopbackNiVacio0() {
        // En JVM de test no hay interfaces Android reales: la lista puede
        // ser vacía, pero jamás debe contener 0.0.0.0/127.x si aparece algo.
        for (ip in NetworkDetector.detectAll()) {
            assertFalse("loopback detectado: $ip", ip.startsWith("127."))
            assertTrue("no bindeable: $ip", NetworkDetector.isBindableIpv4(ip))
        }
    }
}
