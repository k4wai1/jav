package dev.jev.jam.service

import android.accessibilityservice.AccessibilityService
import android.content.Intent
import android.view.accessibility.AccessibilityEvent
import dev.jev.jam.ui.RealA11yNode
import dev.jev.jam.ui.UiSnapshot
import dev.jev.jam.ui.UiTreeExtractor
import dev.jev.jam.util.JevLog
import java.util.concurrent.atomic.AtomicLong

/**
 * Fase 1: `dumpUiTree()` real. Recorrido BFS iterativo, tope 500 nodos,
 * `snapshot_id` monotónico (PROTOCOL.md §5). Sin raíz activa → secure.
 * `onAccessibilityEvent` solo marca dirty; el snapshot se sirve bajo demanda.
 */
class JevAccessibilityService : AccessibilityService() {

    private val snapshotCounter = AtomicLong(0)

    @Volatile
    var uiDirty: Boolean = false
        private set

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        uiDirty = true
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

    /**
     * Snapshot normalizado de la ventana activa. La raíz nativa se recicla
     * aquí; el llamador no gestiona nodos. Nunca devuelve null.
     */
    fun dumpUiTree(): UiSnapshot {
        val root = rootInActiveWindow
            ?: return UiSnapshot(
                snapshotId = snapshotCounter.incrementAndGet(),
                packageName = "",
                secure = true,
                nodes = emptyList()
            )
        try {
            val start = System.nanoTime()
            val snap = UiTreeExtractor.extract(
                RealA11yNode(root),
                root.packageName?.toString().orEmpty(),
                snapshotCounter.incrementAndGet()
            )
            uiDirty = false
            JevLog.d(TAG, "dump_ui: ${snap.nodes.size} nodos en ${(System.nanoTime() - start) / 1_000_000}ms")
            return snap
        } finally {
            root.recycle()
        }
    }

    companion object {
        private const val TAG = "JamUi"

        @Volatile
        var instance: JevAccessibilityService? = null
            private set
    }
}
