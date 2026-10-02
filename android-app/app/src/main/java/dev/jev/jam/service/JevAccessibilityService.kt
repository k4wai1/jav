package dev.jev.jam.service

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.GestureDescription
import android.content.Intent
import android.graphics.Path
import android.graphics.Rect
import android.os.Bundle
import android.os.SystemClock
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import dev.jev.jam.socket.JamError
import dev.jev.jam.ui.RealA11yNode
import dev.jev.jam.ui.Selector
import dev.jev.jam.ui.SelectorResolver
import dev.jev.jam.ui.UiNode
import dev.jev.jam.ui.UiSnapshot
import dev.jev.jam.ui.UiTreeExtractor
import dev.jev.jam.util.JevLog
import java.util.concurrent.atomic.AtomicLong
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeoutOrNull

data class TapResult(val nodeId: String, val via: String)

/**
 * Fase 2: percepción + acciones. `dumpUiTree()` sirve snapshots con
 * `snapshot_id` persistido; las acciones por id lo exigen (`STALE_SNAPSHOT`
 * si la UI cambió). Taps: `ACTION_CLICK` primero si `clickable`,
 * `dispatchGesture` como fallback; siempre se reporta `via`.
 * `type` exige foco explícito (`NOT_FOCUSED` si no).
 * Toda mutación marca `uiDirty` (el cliente re-dumpea para verificar).
 */
class JevAccessibilityService : AccessibilityService() {

    // Monotónico incluso si Android recrea el servicio: se persiste en
    // cada incremento. lazy: getSharedPreferences antes de attachBaseContext
    // daría NPE (crash visto en LG7n al instanciar el servicio).
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

    @Volatile
    private var lastActivity: String = ""

    @Volatile
    private var lastSnapshotId: Long = -1L

    @Volatile
    private var lastNodes: List<UiNode> = emptyList()

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        uiDirty = true
        if (event?.eventType == AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED) {
            event.className?.toString()?.let { lastActivity = it }
        }
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

    /** Snapshot normalizado de la ventana activa. Sin raíz: lista vacía. */
    fun dumpUiTree(): UiSnapshot {
        val id = nextSnapshotId()
        val root = rootInActiveWindow
        if (root == null) {
            lastSnapshotId = id
            lastNodes = emptyList()
            return UiSnapshot(id, "", lastActivity, System.currentTimeMillis(), emptyList())
        }
        try {
            val start = System.nanoTime()
            val snap = UiTreeExtractor.extract(
                RealA11yNode(root),
                root.packageName?.toString().orEmpty(),
                id,
                activity = lastActivity
            )
            lastSnapshotId = id
            lastNodes = snap.nodes
            uiDirty = false
            JevLog.d(TAG, "dump_ui: ${snap.nodes.size} nodos en ${(System.nanoTime() - start) / 1_000_000}ms")
            return snap
        } finally {
            root.recycle()
        }
    }

    fun getForeground(): Pair<String, String> {
        val snap = dumpUiTree()
        return snap.packageName to snap.activity
    }

    // ---- acciones ----

    private fun requireFreshNode(nodeId: String, snapshotId: Long): UiNode {
        if (snapshotId != lastSnapshotId || uiDirty) {
            throw JamError("snapshot obsoleto; re-haz dump_ui", "STALE_SNAPSHOT")
        }
        return lastNodes.find { it.id == nodeId }
            ?: throw JamError("nodo fuera del snapshot", "STALE_SNAPSHOT")
    }

    /**
     * Re-recorre el árbol actual y devuelve el nodo vivo en la posición
     * BFS `index` (mismo orden que el extractor). El llamador lo recicla.
     */
    private fun findLiveNodeByIndex(index: Int): AccessibilityNodeInfo? {
        val root = rootInActiveWindow ?: return null
        if (!root.isVisibleToUser) {
            root.recycle()
            return null
        }
        val queue = ArrayDeque<AccessibilityNodeInfo>()
        val owned = ArrayList<AccessibilityNodeInfo>()
        queue.add(root)
        var count = 0
        var result: AccessibilityNodeInfo? = null
        while (queue.isNotEmpty() && result == null) {
            val node = queue.removeFirst()
            if (count == index) {
                result = node
                break
            }
            count++
            for (i in 0 until node.childCount) {
                val c = node.getChild(i) ?: continue
                if (!c.isVisibleToUser) {
                    c.recycle()
                    continue
                }
                owned.add(c)
                queue.add(c)
            }
        }
        for (n in owned) if (n !== result) n.recycle()
        if (result !== root) root.recycle()
        return result
    }

    private fun verifySame(live: AccessibilityNodeInfo, expected: UiNode) {
        val same = live.text?.toString() == expected.text &&
            live.viewIdResourceName == expected.resourceId &&
            live.className?.toString() == expected.className
        if (!same) throw JamError("la UI cambió entre dump y acción; re-haz dump_ui", "STALE_SNAPSHOT")
    }

    fun tapBySelector(sel: Selector): TapResult {
        val snap = dumpUiTree()
        val node = SelectorResolver.resolve(snap.nodes, sel)
            ?: throw JamError("selector sin match", "SELECTOR_NOT_FOUND")
        return tapLiveNode(node)
    }

    fun tapNode(nodeId: String, snapshotId: Long): TapResult =
        tapLiveNode(requireFreshNode(nodeId, snapshotId))

    private fun tapLiveNode(node: UiNode): TapResult {
        val idx = node.id.removePrefix("n_").toIntOrNull()
            ?: throw JamError("node_id inválido", "VALIDATION_ERROR")
        val live = findLiveNodeByIndex(idx)
            ?: throw JamError("el nodo ya no existe", "SELECTOR_NOT_FOUND")
        try {
            verifySame(live, node)
            if (live.isClickable && live.performAction(AccessibilityNodeInfo.ACTION_CLICK)) {
                return TapResult(node.id, "action_click")
            }
            val b = Rect()
            live.getBoundsInScreen(b)
            if (!dispatchTap(b.centerX(), b.centerY())) {
                throw JamError("gesto rechazado por el sistema", "INTERNAL_ERROR")
            }
            return TapResult(node.id, "gesture")
        } finally {
            live.recycle()
            uiDirty = true
        }
    }

    fun typeNode(nodeId: String, snapshotId: Long, text: String): Int {
        val expected = requireFreshNode(nodeId, snapshotId)
        val idx = nodeId.removePrefix("n_").toIntOrNull()
            ?: throw JamError("node_id inválido", "VALIDATION_ERROR")
        val live = findLiveNodeByIndex(idx)
            ?: throw JamError("el nodo ya no existe", "SELECTOR_NOT_FOUND")
        try {
            verifySame(live, expected)
            if (!live.isFocused) {
                throw JamError("el nodo no tiene foco; haz tap antes", "NOT_FOCUSED")
            }
            val args = Bundle().apply {
                putCharSequence(
                    AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, text
                )
            }
            if (!live.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args)) {
                throw JamError("ACTION_SET_TEXT rechazado", "INTERNAL_ERROR")
            }
            return text.length
        } finally {
            live.recycle()
            uiDirty = true
        }
    }

    fun scrollBy(direction: String, nodeId: String?) {
        val dm = resources.displayMetrics
        val w = dm.widthPixels
        val h = dm.heightPixels
        var x = w / 2
        var y = h / 2
        if (nodeId != null) {
            val snap = dumpUiTree()
            val n = snap.nodes.find { it.id == nodeId }
                ?: throw JamError("nodo no encontrado", "SELECTOR_NOT_FOUND")
            if (n.bounds.size != 4) throw JamError("nodo sin bounds", "INTERNAL_ERROR")
            x = (n.bounds[0] + n.bounds[2]) / 2
            y = (n.bounds[1] + n.bounds[3]) / 2
        }
        val spanX = w / 3
        val spanY = h / 3
        // "down" = ver lo de abajo = dedo sube. Convención documentada.
        val (x1, y1, x2, y2) = when (direction) {
            "down" -> Quad(x, y + spanY / 2, x, y - spanY / 2)
            "up" -> Quad(x, y - spanY / 2, x, y + spanY / 2)
            "left" -> Quad(x - spanX / 2, y, x + spanX / 2, y)
            "right" -> Quad(x + spanX / 2, y, x - spanX / 2, y)
            else -> throw JamError("direction debe ser up|down|left|right", "VALIDATION_ERROR")
        }
        if (!dispatchSwipe(x1, y1, x2, y2)) {
            throw JamError("gesto rechazado por el sistema", "INTERNAL_ERROR")
        }
        uiDirty = true
    }

    fun pressBack() {
        if (!performGlobalAction(GLOBAL_ACTION_BACK)) {
            throw JamError("back rechazado", "INTERNAL_ERROR")
        }
        uiDirty = true
    }

    fun pressHome() {
        if (!performGlobalAction(GLOBAL_ACTION_HOME)) {
            throw JamError("home rechazado", "INTERNAL_ERROR")
        }
        uiDirty = true
    }

    fun waitForNode(sel: Selector, timeoutMs: Long): Pair<String, Long> {
        val deadline = SystemClock.uptimeMillis() + timeoutMs.coerceIn(0, MAX_WAIT_MS)
        do {
            val snap = dumpUiTree()
            SelectorResolver.resolve(snap.nodes, sel)?.let { return it.id to snap.snapshotId }
            SystemClock.sleep(POLL_MS)
        } while (SystemClock.uptimeMillis() < deadline)
        throw JamError("nodo no apareció en ${timeoutMs}ms", "TIMEOUT")
    }

    // ---- gestos ----

    private fun dispatchTap(x: Int, y: Int): Boolean =
        dispatchStroke(x, y, x, y, TAP_MS)

    private fun dispatchSwipe(x1: Int, y1: Int, x2: Int, y2: Int): Boolean =
        dispatchStroke(x1, y1, x2, y2, SWIPE_MS)

    private fun dispatchStroke(x1: Int, y1: Int, x2: Int, y2: Int, durationMs: Long): Boolean {
        val path = Path().apply {
            moveTo(x1.toFloat(), y1.toFloat())
            lineTo(x2.toFloat(), y2.toFloat())
        }
        val stroke = GestureDescription.StrokeDescription(path, 0, durationMs)
        val gesture = GestureDescription.Builder().addStroke(stroke).build()
        val done = CompletableDeferred<Boolean>()
        val accepted = dispatchGesture(gesture, object : AccessibilityService.GestureResultCallback() {
            override fun onCompleted(gestureDescription: GestureDescription?) {
                done.complete(true)
            }

            override fun onCancelled(gestureDescription: GestureDescription?) {
                done.complete(false)
            }
        }, null)
        if (!accepted) return false
        return runBlocking { withTimeoutOrNull(GESTURE_TIMEOUT_MS) { done.await() } ?: false }
    }

    companion object {
        private const val TAG = "JamUi"
        private const val PREFS = "jam"
        private const val KEY_SNAPSHOT = "snapshot_id"
        private const val TAP_MS = 100L
        private const val SWIPE_MS = 400L
        private const val GESTURE_TIMEOUT_MS = 3000L
        private const val POLL_MS = 250L
        private const val MAX_WAIT_MS = 30_000L

        @Volatile
        var instance: JevAccessibilityService? = null
            private set
    }

    private data class Quad(val x1: Int, val y1: Int, val x2: Int, val y2: Int)
}
