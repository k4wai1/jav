package dev.k4wai1.jav.socket

import java.lang.reflect.InvocationHandler
import java.lang.reflect.Method
import java.lang.reflect.Proxy
import org.java_websocket.WebSocket
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * v2.3.0: `ClientRegistry` es el único punto de verdad entre loopback y
 * WSS (LAN/tailnet). Aquí se prueba con un proxy dinámico sobre
 * `WebSocket` (sin dependencias nuevas).
 */
class ClientRegistryTest {

    private class FakeWs {
        val sent = mutableListOf<String>()
        val closes = mutableListOf<Int>()

        @Volatile
        var open = true
    }

    private fun fake(w: FakeWs): WebSocket {
        val handler = InvocationHandler { _, m: Method, args: Array<Any?>? ->
            when (m.name) {
                "send" -> {
                    (args?.firstOrNull() as? String)?.let { w.sent.add(it) }
                    null
                }
                "close" -> {
                    w.closes.add((args?.firstOrNull() as? Int) ?: -1)
                    w.open = false
                    null
                }
                "isOpen" -> w.open
                "isClosing" -> !w.open
                "isFlushAndClose" -> !w.open
                "toString" -> "FakeWs"
                "hashCode" -> System.identityHashCode(w)
                "equals" -> false
                else -> defaultValue(m.returnType)
            }
        }
        return Proxy.newProxyInstance(
            WebSocket::class.java.classLoader,
            arrayOf<Class<*>>(WebSocket::class.java),
            handler
        ) as WebSocket
    }

    private fun defaultValue(type: Class<*>): Any? = when (type) {
        java.lang.Boolean.TYPE -> false
        java.lang.Integer.TYPE -> 0
        java.lang.Long.TYPE -> 0L
        java.lang.Short.TYPE -> 0.toShort()
        java.lang.Byte.TYPE -> 0.toByte()
        java.lang.Character.TYPE -> '\u0000'
        java.lang.Float.TYPE -> 0f
        java.lang.Double.TYPE -> 0.0
        else -> null
    }

    @Test
    fun sinClienteNoHayConteoNiBroadcast() {
        val r = ClientRegistry()
        assertEquals(0, r.clientCount())
        assertNull(r.clientAuthed())
        r.broadcastEvent("x") // no-op, no debe lanzar
        assertNull(r.active)
    }

    @Test
    fun activoSinHelloCuentaPeroNoEstaAutenticado() {
        val r = ClientRegistry()
        val w = FakeWs()
        val ws = fake(w)
        r.active = ws

        assertEquals(1, r.clientCount())
        assertEquals(false, r.clientAuthed())
        r.broadcastEvent("frame")
        assertTrue("sin hello no debe recibir broadcasts", w.sent.isEmpty())
    }

    @Test
    fun activoAutenticadoRecibeBroadcast() {
        val r = ClientRegistry()
        val w = FakeWs()
        val ws = fake(w)
        r.active = ws
        r.authedScopes[ws] = setOf("read", "ui")

        assertEquals(1, r.clientCount())
        assertEquals(true, r.clientAuthed())
        r.broadcastEvent("shell_grant")
        assertEquals(listOf("shell_grant"), w.sent)
    }

    @Test
    fun conexionCerradaNoCuentaNiEsAutenticada() {
        val r = ClientRegistry()
        val w = FakeWs()
        val ws = fake(w)
        w.open = false
        r.active = ws
        r.authedScopes[ws] = setOf("admin")

        assertEquals(0, r.clientCount())
        assertNull(r.clientAuthed())
        r.broadcastEvent("x")
        assertTrue(w.sent.isEmpty())
    }

    @Test
    fun revokeAllCierraActiveCandidateYAutenticados() {
        val r = ClientRegistry()
        val aw = FakeWs()
        val active = fake(aw)
        val cw = FakeWs()
        val candidate = fake(cw)
        val ow = FakeWs()
        val other = fake(ow)

        r.active = active
        r.candidate = candidate
        r.authedScopes[active] = setOf("admin")
        r.authedScopes[other] = setOf("read")

        r.revokeAll()

        assertTrue(r.authedScopes.isEmpty())
        assertNull(r.active)
        assertNull(r.candidate)
        for ((w, name) in listOf(
            aw to "active", cw to "candidate", ow to "authed-extra"
        )) {
            assertEquals("$name: un único close", 1, w.closes.size)
            assertEquals("$name: código 4401", 4401, w.closes.first())
            assertTrue(
                "$name: frame UNAUTHORIZED",
                w.sent.lastOrNull()?.contains("UNAUTHORIZED") == true
            )
            assertFalse("$name: cerrado", w.open)
        }
    }
}
