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

    // Monotónico incluso si Android recrea el servicio (nuevo proceso =
    // nuevo AtomicLong): se persiste en cada incremento. Sin esto, un
    // snapshot_id reutilizado rompería la protección STALE_SNAPSHOT.
    // lazy: getSharedPreferences antes de attachBaseContext daría NPE
    // (crash visto en LG7n al instanciar el servicio).
    private val snapshotCounter: AtomicLong by lazy {
        AtomicLong(getSharedPreferences(PREFS, MODE_PRIVATE).getLong(KEY_SNAPSHOT, 0L))
    }

    private fun nextSnapshotId(): Long {
        val id = snapshotCounter.incrementAndGet()
        getSharedPreferences(PREFS, MODE_PRIVATE).edit().putLong(KEY_SNAPSHOT, id).apply()
        return id
    }

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
                snapshotId = nextSnapshotId(),
                packageName = "",
                secure = true,
                nodes = emptyList()
            )
        try {
            val start = System.nanoTime()
            val snap = UiTreeExtractor.extract(
                RealA11yNode(root),
                root.packageName?.toString().orEmpty(),
                nextSnapshotId()
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
        private const val PREFS = "jam"
        private const val KEY_SNAPSHOT = "snapshot_id"

        @Volatile
        var instance: JevAccessibilityService? = null
            private set
    }
}
