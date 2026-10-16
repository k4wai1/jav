package dev.jev.jam.service

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.GestureDescription
import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Path
import android.graphics.Point
import android.os.Build
import android.os.SystemClock
import android.util.Base64
import android.view.Display
import android.view.WindowManager
import android.view.accessibility.AccessibilityEvent
import dev.jev.jam.shell.ShizukuBridge
import dev.jev.jam.socket.JamError
import dev.jev.jam.ui.A11yNode
import dev.jev.jam.ui.ClickAncestor
import dev.jev.jam.ui.DisplayScale
import dev.jev.jam.ui.LiveNodeReanchor
import dev.jev.jam.ui.ReanchorStatus
import dev.jev.jam.ui.RealA11yNode
import dev.jev.jam.ui.Selector
import dev.jev.jam.ui.SelectorResolver
import dev.jev.jam.ui.UiNode
import dev.jev.jam.ui.UiSnapshot
import dev.jev.jam.ui.UiTreeExtractor
import dev.jev.jam.util.JevLog
import java.io.ByteArrayOutputStream
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicLong
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeoutOrNull

data class TapResult(val nodeId: String, val via: String)

data class ScreenshotData(val img: String, val w: Int, val h: Int, val via: String)

// Anti-ticker (spec tactical-robustness-p1p2 §1): los
// TYPE_WINDOW_CONTENT_CHANGED son ruido cosmético del sistema Y de la
// propia app (relojes, animaciones, cursores). No invalidan el snapshot
// por sí solos: la identidad real del nodo se valida en reanchorOrThrow
// al actuar (STALE_SNAPSHOT si de verdad cambió).
internal fun isVolatileEvent(eventType: Int?): Boolean =
    eventType == AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED

/**
 * Fase 2: percepción + acciones UI. Fase 3a: `open_app`/`force_stop`
 * (Shizuku) + `screenshot` (`takeScreenshot`, API 30+).
 * `snapshot_id` persistido anti-staleness; toda mutación marca `uiDirty`.
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
        if (event == null) {
            uiDirty = true
            return
        }
        if (!isVolatileEvent(event.eventType)) {
            uiDirty = true
        }
        if (event.eventType == AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED) {
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

    // ---- acciones UI (Fase 2) ----

    private fun requireFreshNode(nodeId: String, snapshotId: Long): UiNode {
        if (snapshotId != lastSnapshotId || uiDirty) {
            throw JamError("snapshot obsoleto; re-haz dump_ui", "STALE_SNAPSHOT")
        }
        return lastNodes.find { it.id == nodeId }
            ?: throw JamError("nodo fuera del snapshot", "STALE_SNAPSHOT")
    }

    private fun reanchorOrThrow(expected: UiNode): A11yNode {
        val idx = expected.id.removePrefix("n_").toIntOrNull()
            ?: throw JamError("node_id inválido", "VALIDATION_ERROR")
        val root = rootInActiveWindow
            ?: throw JamError("el nodo ya no existe", "SELECTOR_NOT_FOUND")
        val res = try {
            LiveNodeReanchor.reanchor(RealA11yNode(root), expected, idx)
        } finally {
            root.recycle()
        }
        val live = res.node
        if (res.status.found && live != null) return live
        when (res.status) {
            ReanchorStatus.NOT_FOUND -> throw JamError("la UI cambió entre dump y acción; re-haz dump_ui", "STALE_SNAPSHOT")
            ReanchorStatus.AMBIGUOUS -> throw JamError("el nodo se duplicó en pantalla; re-haz dump_ui", "STALE_SNAPSHOT")
            ReanchorStatus.NO_WINDOW -> throw JamError("el nodo ya no existe", "SELECTOR_NOT_FOUND")
            else -> throw IllegalStateException("reanchor inconsistente: ${res.status}")
        }
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
        val live = reanchorOrThrow(node)
        try {
            val via: String
            if (live.isClickable && live.performClick()) {
                via = "action_click"
            } else {
                val ancestor = ClickAncestor.find(live)
                if (ancestor != null) {
                    ancestor.recycle()
                    via = "click_ancestor"
                } else {
                    val bs = live.boundsInScreen
                    if (bs.size != 4) throw JamError("nodo sin bounds", "INTERNAL_ERROR")
                    val cx = (bs[0] + bs[2]) / 2
                    val cy = (bs[1] + bs[3]) / 2
                    val (px, py) = toPhysical(cx, cy)
                    JevLog.d(TAG, "tap gesto log=$cx,$cy phys=$px,$py")
                    if (!dispatchTap(px, py)) {
                        throw JamError("gesto rechazado por el sistema", "INTERNAL_ERROR")
                    }
                    via = "gesture"
                }
            }
            if (node.editable || live.isEditable) {
                try {
                    if (!live.performFocus()) {
                        JevLog.d(TAG, "performFocus rechazado tras $via")
                    }
                } catch (t: Throwable) {
                    JevLog.d(TAG, "performFocus lanzó: ${t.message}")
                }
            }
            return TapResult(node.id, via)
        } finally {
            live.recycle()
            uiDirty = true
        }
    }

    fun typeNode(nodeId: String, snapshotId: Long, text: String): Int {
        val expected = requireFreshNode(nodeId, snapshotId)
        val live = reanchorOrThrow(expected)
        try {
            if (!live.isFocused) {
                throw JamError("el nodo no tiene foco; haz tap antes", "NOT_FOCUSED")
            }
            if (!live.setText(text)) {
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
        val vp = currentViewport()
        val (apx, apy) = DisplayScale.project(x1, y1, vp)
        val (bpx, bpy) = DisplayScale.project(x2, y2, vp)
        JevLog.d(TAG, "scroll $direction log=($x1,$y1)->($x2,$y2) phys=($apx,$apy)->($bpx,$bpy)")
        if (!dispatchSwipe(apx, apy, bpx, bpy)) {
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

    // ---- Fase 3a: Shizuku + screenshot ----

    /**
     * Abre la app por su launcher (`monkey`; no requiere conocer la
     * activity). Verifica con foreground (exit 0 de monkey no basta).
     */
    fun openApp(pkg: String): Pair<String, String> {
        if (pkg.isBlank()) throw JamError("package vacío", "VALIDATION_ERROR")
        val r = ShizukuBridge.exec(
            listOf("monkey", "-p", pkg, "-c", "android.intent.category.LAUNCHER", "1")
        )
        if (r.exitCode != 0) {
            throw JamError("monkey falló (exit ${r.exitCode}): ${r.stderr.take(200)}", "INTERNAL_ERROR")
        }
        if ((r.stdout + r.stderr).contains("No activities found")) {
            throw JamError("el paquete no tiene activity lanzable", "VALIDATION_ERROR")
        }
        val deadline = SystemClock.uptimeMillis() + OPEN_APP_WAIT_MS
        var last = "" to ""
        do {
            val snap = dumpUiTree()
            last = snap.packageName to snap.activity
            if (last.first == pkg) break
            SystemClock.sleep(500)
        } while (SystemClock.uptimeMillis() < deadline)
        if (last.first != pkg) throw JamError("la app no llegó a foreground", "TIMEOUT")
        return last
    }

    fun screenshotPng(format: String, quality: Int): ScreenshotData {
        if (format != "png" && format != "webp") {
            throw JamError("format debe ser png|webp", "VALIDATION_ERROR")
        }
        val bmp = takeScreenshotBlocking()
        try {
            val fmt = webpOrPng(format)
            val out = ByteArrayOutputStream()
            bmp.compress(fmt, quality.coerceIn(1, 100), out)
            val b64 = Base64.encodeToString(out.toByteArray(), Base64.NO_WRAP)
            if (b64.length > MAX_SCREENSHOT_B64) {
                throw JamError(
                    "imagen excede 4 MiB; usa format=webp, quality=80", "PAYLOAD_TOO_LARGE"
                )
            }
            val via = if (Build.VERSION.SDK_INT < Build.VERSION_CODES.R) "screencap" else "takeScreenshot"
            return ScreenshotData(b64, bmp.width, bmp.height, via)
        } finally {
            if (!bmp.isRecycled) bmp.recycle()
        }
    }

    /**
     * WEBP_LOSSY es API 30+; en API 29 se usa WEBP (deprecado). Referenciar
     * WEBP_LOSSY en API 29 lanza NoSuchFieldError (Error, no JamError), así
     * que la referencia vive aislada y solo se ejecuta en API 30+.
     */
    private fun webpOrPng(format: String): Bitmap.CompressFormat = when {
        format != "webp" -> Bitmap.CompressFormat.PNG
        Build.VERSION.SDK_INT >= Build.VERSION_CODES.R -> webpLossy()
        else -> webpLegacy()
    }

    @Suppress("DEPRECATION")
    private fun webpLegacy(): Bitmap.CompressFormat = Bitmap.CompressFormat.WEBP

    private fun webpLossy(): Bitmap.CompressFormat = Bitmap.CompressFormat.WEBP_LOSSY

    private fun takeScreenshotBlocking(): Bitmap {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.R) {
            return screencapBlocking()
        }
        val latch = CountDownLatch(1)
        var bitmap: Bitmap? = null
        var error: JamError? = null
        takeScreenshot(
            Display.DEFAULT_DISPLAY,
            mainExecutor,
            object : AccessibilityService.TakeScreenshotCallback {
                override fun onSuccess(result: AccessibilityService.ScreenshotResult) {
                    try {
                        val hb = result.hardwareBuffer
                        try {
                            // Copiar ANTES de close(): sin copy el bitmap sale corrupto.
                            bitmap = Bitmap.wrapHardwareBuffer(hb, result.colorSpace)
                                ?.copy(Bitmap.Config.ARGB_8888, false)
                                ?: throw IllegalStateException("wrapHardwareBuffer nulo")
                        } finally {
                            hb.close()
                        }
                    } catch (t: Throwable) {
                        error = JamError("captura corrupta: ${t.message}", "INTERNAL_ERROR")
                    } finally {
                        latch.countDown()
                    }
                }

                override fun onFailure(errorCode: Int) {
                    error = if (errorCode == AccessibilityService.ERROR_TAKE_SCREENSHOT_SECURE_WINDOW) {
                        JamError("superficie protegida", "SECURE_SURFACE")
                    } else {
                        JamError("takeScreenshot falló: $errorCode", "INTERNAL_ERROR")
                    }
                    latch.countDown()
                }
            }
        )
        if (!latch.await(SCREENSHOT_TIMEOUT_MS, TimeUnit.MILLISECONDS)) {
            throw JamError("timeout screenshot", "TIMEOUT")
        }
        error?.let { throw it }
        return bitmap ?: throw JamError("bitmap nulo", "INTERNAL_ERROR")
    }

    private fun screencapBlocking(): Bitmap {
        val r = ShizukuBridge.exec(
            listOf("sh", "-c", "screencap -p | base64"), timeoutMs = SCREENSHOT_TIMEOUT_MS
        )
        if (r.exitCode != 0) {
            throw JamError("screencap falló (exit ${r.exitCode}): ${r.stderr.take(200)}", "INTERNAL_ERROR")
        }
        val b64 = r.stdout.filter { !it.isWhitespace() }
        if (b64.isEmpty()) {
            throw JamError("captura vacía o superficie protegida (screencap)", "SECURE_SURFACE")
        }
        val raw = try {
            Base64.decode(b64, Base64.DEFAULT)
        } catch (t: IllegalArgumentException) {
            throw JamError("captura vacía o superficie protegida (screencap)", "SECURE_SURFACE")
        }
        return BitmapFactory.decodeByteArray(raw, 0, raw.size)
            ?: throw JamError("captura vacía o superficie protegida (screencap)", "SECURE_SURFACE")
    }

    // ---- gestos ----

    /**
     * Viewport actual: lógico = `Display.getRealSize` (espacio de a11y,
     * respeta `wm size override`); físico = `Display.Mode` (panel real,
     * inmune al override), rotado a la orientación actual.
     * Si `getRealSize` ignorase el override (devuelve físico), el viewport
     * sale identidad y el gesto no escala (se loguea para diagnóstico).
     */
    @Suppress("DEPRECATION")
    private fun currentViewport(): DisplayScale.Viewport {
        try {
            val wm = getSystemService(Context.WINDOW_SERVICE) as WindowManager
            val d = wm.defaultDisplay
            val real = Point()
            d.getRealSize(real)
            val mode = d.mode
            var pw = mode.physicalWidth
            var ph = mode.physicalHeight
            if ((real.x > real.y) != (pw > ph)) {
                val t = pw; pw = ph; ph = t
            }
            val dm = resources.displayMetrics
            JevLog.d(
                TAG,
                "viewport real=${real.x}x${real.y} mode=${pw}x${ph} " +
                    "dm=${dm.widthPixels}x${dm.heightPixels} rot=${d.rotation}"
            )
            return DisplayScale.Viewport(real.x, real.y, pw, ph)
        } catch (t: Throwable) {
            val dm = resources.displayMetrics
            return DisplayScale.Viewport(dm.widthPixels, dm.heightPixels, dm.widthPixels, dm.heightPixels)
        }
    }

    private fun toPhysical(x: Int, y: Int): Pair<Int, Int> =
        DisplayScale.project(x, y, currentViewport())

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
        private const val OPEN_APP_WAIT_MS = 5000L
        private const val SCREENSHOT_TIMEOUT_MS = 5000L
        private const val MAX_SCREENSHOT_B64 = 3_500_000

        @Volatile
        var instance: JevAccessibilityService? = null
            private set
    }

    private data class Quad(val x1: Int, val y1: Int, val x2: Int, val y2: Int)
}
