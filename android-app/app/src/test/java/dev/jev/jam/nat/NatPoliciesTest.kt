package dev.jev.jam.nat

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/** Reglas puras del catálogo native-apis (JVM, sin framework). */
class NatPoliciesTest {

    @Test
    fun `send y call son criticos, view https no`() {
        assertTrue(NatPolicies.isCritical("android.intent.action.SEND", ""))
        assertTrue(NatPolicies.isCritical("android.intent.action.CALL", "tel:123"))
        assertFalse(NatPolicies.isCritical("android.intent.action.VIEW", "https://x.test/a"))
    }

    @Test
    fun `view a sms es critico por esquema`() {
        assertTrue(NatPolicies.isCritical("android.intent.action.VIEW", "sms:123?body=hola"))
    }

    @Test
    fun `dial abre marcador, no es envio`() {
        assertFalse(NatPolicies.isCritical("android.intent.action.DIAL", "tel:123"))
    }

    @Test
    fun `paquetes con forma`() {
        assertTrue(NatPolicies.validPackage("dev.jev.jam"))
        assertTrue(NatPolicies.validPackage("com.ejemplo.app"))
        assertFalse(NatPolicies.validPackage(""))
        assertFalse(NatPolicies.validPackage("sinespacio"))
        assertFalse(NatPolicies.validPackage("rm -rf /"))
    }

    @Test
    fun `urls con esquema permitido`() {
        assertTrue(NatPolicies.validUrl("https://ejemplo.test/a"))
        assertTrue(NatPolicies.validUrl("geo:0,0?q=x"))
        assertFalse(NatPolicies.validUrl("file:///etc/passwd"))
        assertFalse(NatPolicies.validUrl("https:"))
    }

    @Test
    fun `horas y ventana acotadas`() {
        assertEquals(1, NatPolicies.clampHours(0))
        assertEquals(24, NatPolicies.clampHours(99))
        assertTrue(NatPolicies.windowOk(7L * 24 * 60 * 60 * 1000))
        assertFalse(NatPolicies.windowOk(8L * 24 * 60 * 60 * 1000))
        assertFalse(NatPolicies.windowOk(-5))
    }

    @Test
    fun `put solo system, get system-secure-global`() {
        assertTrue(NatPolicies.putAllowed("system"))
        assertFalse(NatPolicies.putAllowed("secure"))
        assertFalse(NatPolicies.putAllowed("global"))
        assertTrue(NatPolicies.getAllowed("secure"))
        assertFalse(NatPolicies.getAllowed("otro"))
    }

    @Test
    fun `truncado de PII`() {
        assertEquals("abc", NatPolicies.truncate("abc", 200))
        assertEquals(200, NatPolicies.truncate("x".repeat(500), 200).length)
    }
}
