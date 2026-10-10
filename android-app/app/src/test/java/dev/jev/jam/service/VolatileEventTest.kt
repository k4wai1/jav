package dev.jev.jam.service

import android.view.accessibility.AccessibilityEvent
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class VolatileEventTest {

    @Test
    fun `content changed es volatil`() {
        assertTrue(isVolatileEvent(AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED))
    }

    @Test
    fun `window state changed no es volatil`() {
        assertFalse(isVolatileEvent(AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED))
    }

    @Test
    fun `view clicked no es volatil`() {
        assertFalse(isVolatileEvent(AccessibilityEvent.TYPE_VIEW_CLICKED))
    }

    @Test
    fun `evento nulo no es volatil`() {
        assertFalse(isVolatileEvent(null))
    }
}
