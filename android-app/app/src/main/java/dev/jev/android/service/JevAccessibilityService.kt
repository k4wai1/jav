package dev.jev.android.service

import android.accessibilityservice.AccessibilityService
import android.content.Intent
import android.view.accessibility.AccessibilityEvent

/**
 * Fase 0: stub. El `dumpUiTree()` real, el recorrido iterativo y
 * `ACTION_CLICK`-primero llegan en la Fase 1 (ver AGENTS.md §5-§6).
 */
class JevAccessibilityService : AccessibilityService() {

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        // Fase 1: marcar ui_dirty y notificar al socket. Nunca bloquear aquí.
    }

    override fun onInterrupt() {
        // No-op.
    }

    override fun onServiceConnected() {
        instance = this
    }

    override fun onUnbind(intent: Intent?): Boolean {
        if (instance === this) {
            instance = null
        }
        return super.onUnbind(intent)
    }

    companion object {
        @Volatile
        var instance: JevAccessibilityService? = null
            private set
    }
}
