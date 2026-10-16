package dev.jev.jam.socket

import kotlinx.serialization.json.decodeFromJsonElement
import kotlinx.serialization.json.encodeToJsonElement
import kotlinx.serialization.builtins.ListSerializer
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/** Tests JVM del audit ring (Fase 6a, sin Android). */
class AuditLogTest {

    private fun reset() = AuditLog.clear()

    @Test
    fun `registra y lista en orden con seq monotonic`() {
        reset()
        val a = AuditLog.record("get_battery", "n0", "{}", "OK", "loopback", ts = 1000)
        val b = AuditLog.record("dump_ui", "read", "{}", "OK", "loopback", ts = 1001)
        assertEquals(1L, a.seq)
        assertEquals(2L, b.seq)
        assertEquals(2, AuditLog.size())
        val all = AuditLog.list()
        assertEquals(listOf(1L, 2L), all.map { it.seq })
        assertEquals("get_battery", all[0].method)
        assertEquals(1001L, all[1].ts)
    }

    @Test
    fun `args_sha256 nunca expone texto en claro ni el token`() {
        reset()
        val secreto = "Bearer token-super-secreto-123"
        val e = AuditLog.record("hello", "auth", "{\"token\":\"$secreto\"}", "OK", "loopback")
        assertEquals(16, e.args_sha256.length)
        assertFalse(e.args_sha256.contains("token"))
        assertFalse(e.args_sha256.contains("secreto"))
        assertFalse(e.args_sha256.contains(secreto))
        assertTrue(e.args_sha256.all { it in "0123456789abcdef" })
    }

    @Test
    fun `eviccion exacta a 500 conserva las ultimas`() {
        reset()
        repeat(510) { i ->
            AuditLog.record("m$i", "n0", "{}", "OK", "loopback", ts = i.toLong())
        }
        assertEquals(500, AuditLog.size())
        val all = AuditLog.list(limit = 500)
        assertEquals(500, all.size)
        assertEquals(11L, all.first().seq)
        assertEquals(510L, all.last().seq)
    }

    @Test
    fun `filtro since_seq y limit recortan por la cola`() {
        reset()
        repeat(10) { AuditLog.record("m$it", "n0", "{}", "OK", "loopback") }
        val since = AuditLog.list(limit = 100, sinceSeq = 7)
        assertEquals(listOf(8L, 9L, 10L), since.map { it.seq })
        val tail = AuditLog.list(limit = 3, sinceSeq = 0)
        assertEquals(listOf(8L, 9L, 10L), tail.map { it.seq })
        val clamped = AuditLog.list(limit = 0, sinceSeq = 0)
        assertEquals(1, clamped.size)
        assertEquals(10L, clamped.first().seq)
    }

    @Test
    fun `lista vacia y roundtrip serializable`() {
        reset()
        assertTrue(AuditLog.list().isEmpty())
        assertEquals(0, AuditLog.size())
        val e = AuditLog.record("get_cpu", "n0", "{\"detail\":\"basic\"}", "OK", "127.0.0.1:5555")
        val json = JamJson.encodeToJsonElement(AuditEntry.serializer(), e)
        val back = JamJson.decodeFromJsonElement(AuditEntry.serializer(), json)
        assertEquals(e, back)
        assertEquals("127.0.0.1:5555", back.origin)
        val arr = JamJson.encodeToJsonElement(
            ListSerializer(AuditEntry.serializer()), listOf(e)
        )
        assertTrue(arr.toString().contains("args_sha256"))
    }
}
