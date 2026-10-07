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
    fun `open_url package forzado exige forma valida`() {
        // Forma a.b.c (>= 2 etiquetas): forzar handler sin chooser.
        assertTrue(NatPolicies.validPackage("com.google.android.youtube"))
        assertTrue(NatPolicies.validPackage("org.mozilla.firefox"))
        // `pkg=""` = resolver por el sistema: no se valida, no matchea.
        assertFalse(NatPolicies.validPackage(""))
        assertFalse(NatPolicies.validPackage("com.1bad"))
        assertFalse(NatPolicies.validPackage("com..app"))
        assertFalse(NatPolicies.validPackage("/system/bin/sh"))
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
    fun `clamp raw acota 1 a 168 h`() {
        assertEquals(1, NatPolicies.clampRawHours(0))
        assertEquals(1, NatPolicies.clampRawHours(-9))
        assertEquals(168, NatPolicies.clampRawHours(999))
        assertEquals(72, NatPolicies.clampRawHours(72))
    }

    @Test
    fun `ventanas de uso validas`() {
        assertTrue(NatPolicies.validUsageWindow(null))
        assertTrue(NatPolicies.validUsageWindow("today"))
        assertTrue(NatPolicies.validUsageWindow("week"))
        assertTrue(NatPolicies.validUsageWindow("raw"))
        assertFalse(NatPolicies.validUsageWindow("month"))
        assertFalse(NatPolicies.validUsageWindow("hours"))
    }

    @Test
    fun `usage begin por ventana`() {
        val now = 1_700_000_000_000L
        val h = NatPolicies.HOUR_MS
        // sin window: horas 1..24 (compat)
        assertEquals(now - 24 * h, NatPolicies.usageBegin(now, null, 24))
        assertEquals(now - 24 * h, NatPolicies.usageBegin(now, null, 99))
        // raw: hasta 168 h
        assertEquals(now - 48 * h, NatPolicies.usageBegin(now, "raw", 48))
        assertEquals(now - 168 * h, NatPolicies.usageBegin(now, "raw", 999))
        // week: exactamente 7 días
        assertEquals(now - NatPolicies.MAX_WINDOW_MS, NatPolicies.usageBegin(now, "week", 1))
        // today: medianoche local, <= now y múltiplo de día local
        val midnight = NatPolicies.usageBegin(now, "today", 1)
        assertTrue(midnight <= now)
        assertTrue(now - midnight < 24 * h)
        val c = java.util.Calendar.getInstance()
        c.timeInMillis = midnight
        assertEquals(0, c.get(java.util.Calendar.HOUR_OF_DAY))
        assertEquals(0, c.get(java.util.Calendar.MINUTE))
        assertEquals(0, c.get(java.util.Calendar.SECOND))
        assertEquals(0, c.get(java.util.Calendar.MILLISECOND))
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
