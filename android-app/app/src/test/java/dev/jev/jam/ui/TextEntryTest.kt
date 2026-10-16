package dev.jev.jam.ui

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class TextEntryTest {

    @Test
    fun setTextPathWhenAccepted() {
        val node = FakeA11yNode(setTextResult = true, pasteResult = true)
        var prepared = false
        val via = TextEntry.write(node, "hola", preparePaste = { prepared = true })
        assertEquals(TextEntry.VIA_SET_TEXT, via)
        assertEquals(1, node.setTextAttempts)
        assertEquals(0, node.pasteAttempts)
        assertTrue(!prepared)
    }

    @Test
    fun pasteFallbackWhenSetTextFails() {
        val node = FakeA11yNode(setTextResult = false, pasteResult = true)
        var prepared = false
        val via = TextEntry.write(node, "hola", preparePaste = { prepared = true })
        assertEquals(TextEntry.VIA_PASTE, via)
        assertEquals(1, node.setTextAttempts)
        assertEquals(1, node.pasteAttempts)
        assertTrue(prepared)
        assertEquals("hola", node.lastSetText.toString())
    }

    @Test
    fun nullWhenBothFail() {
        val node = FakeA11yNode(setTextResult = false, pasteResult = false)
        var prepared = false
        val via = TextEntry.write(node, "hola", preparePaste = { prepared = true })
        assertNull(via)
        assertEquals(1, node.setTextAttempts)
        assertEquals(1, node.pasteAttempts)
        assertTrue(prepared)
    }
}
