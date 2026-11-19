package dev.k4wai1.jav.service

import android.view.accessibility.AccessibilityEvent
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/** v2.3.1: solo eventos con efecto prueban que un tap surtió efecto. */
class EffectEventTest {

    @Test
    fun hoverAndTouchAreNotEffects() {
        assertFalse(isEffectEvent(AccessibilityEvent.TYPE_VIEW_HOVER_ENTER))
        assertFalse(isEffectEvent(AccessibilityEvent.TYPE_VIEW_HOVER_EXIT))
        assertFalse(isEffectEvent(AccessibilityEvent.TYPE_TOUCH_INTERACTION_START))
        assertFalse(isEffectEvent(AccessibilityEvent.TYPE_TOUCH_INTERACTION_END))
        assertFalse(isEffectEvent(AccessibilityEvent.TYPE_GESTURE_DETECTION_START))
    }

    @Test
    fun clickAndWindowChangesAreEffects() {
        assertTrue(isEffectEvent(AccessibilityEvent.TYPE_VIEW_CLICKED))
        assertTrue(isEffectEvent(AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED))
        assertTrue(isEffectEvent(AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED))
        assertTrue(isEffectEvent(AccessibilityEvent.TYPE_VIEW_SCROLLED))
        assertTrue(isEffectEvent(AccessibilityEvent.TYPE_VIEW_FOCUSED))
    }
}
