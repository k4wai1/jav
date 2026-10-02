package dev.jev.jam.socket

import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** Tests JVM del framing JSON (sin sockets). */
class WsProtocolTest {

    @Test
    fun `request roundtrip con params`() {
        val params = buildJsonObject { put("direction", "down") }
        val req = WsRequest("u1", "scroll", params)
        val back = JamJson.decodeFromString(WsRequest.serializer(), JamJson.encodeToString(WsRequest.serializer(), req))
        assertEquals("u1", back.id)
        assertEquals("scroll", back.method)
        assertEquals("down", back.params["direction"].toString().trim('"'))
    }

    @Test
    fun `error lleva id code y mensaje`() {
        val frame = errResponse("u2", "sin foco", "NOT_FOCUSED")
        val back = JamJson.decodeFromString(WsResponse.serializer(), frame)
        assertEquals("u2", back.id)
        assertEquals(false, back.ok)
        assertEquals("NOT_FOCUSED", back.code)
        assertEquals("sin foco", back.error)
        assertNull(back.result)
    }

    @Test
    fun `ok omite nulos`() {
        val frame = okResponse("u3", buildJsonObject { put("via", "gesture") })
        assertTrue(!frame.contains("error"))
        assertTrue(frame.contains("gesture"))
    }
}
