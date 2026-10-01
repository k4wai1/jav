package dev.jev.jam.ui

import android.graphics.Rect
import android.view.accessibility.AccessibilityNodeInfo

/**
 * Fuente abstracta de nodos. Desacopla el recorrido del framework Android
 * para que [UiTreeExtractor] sea testeable en JVM sin Robolectric.
 * Implementación real: [RealA11yNode]. Tests: `FakeA11yNode`.
 */
interface A11yNode {
    val text: CharSequence?
    val contentDescription: CharSequence?
    val className: CharSequence?
    val viewIdResourceName: String?
    val isClickable: Boolean
    val isEditable: Boolean
    val isScrollable: Boolean
    val isEnabled: Boolean
    val isChecked: Boolean
    val isFocused: Boolean
    val isVisibleToUser: Boolean
    /** [left, top, right, bottom] en píxeles de pantalla. */
    val boundsInScreen: List<Int>
    val childCount: Int
    fun getChild(index: Int): A11yNode?
    /** Libera el nodo nativo. El extractor recicla todo lo que obtiene
     * vía [getChild]; la raíz la recicla el llamador (el servicio). */
    fun recycle()
}

/**
 * Adaptador fino sobre AccessibilityNodeInfo: cero lógica, solo delegación.
 * Toda la decisión vive en [UiTreeExtractor] (testeable).
 */
class RealA11yNode(private val info: AccessibilityNodeInfo) : A11yNode {
    override val text: CharSequence? get() = info.text
    override val contentDescription: CharSequence? get() = info.contentDescription
    override val className: CharSequence? get() = info.className
    override val viewIdResourceName: String? get() = info.viewIdResourceName
    override val isClickable: Boolean get() = info.isClickable
    override val isEditable: Boolean get() = info.isEditable
    override val isScrollable: Boolean get() = info.isScrollable
    override val isEnabled: Boolean get() = info.isEnabled
    override val isChecked: Boolean get() = info.isChecked
    override val isFocused: Boolean get() = info.isFocused
    override val isVisibleToUser: Boolean get() = info.isVisibleToUser
    override val boundsInScreen: List<Int>
        get() {
            val r = Rect()
            info.getBoundsInScreen(r)
            return listOf(r.left, r.top, r.right, r.bottom)
        }
    override val childCount: Int get() = info.childCount
    override fun getChild(index: Int): A11yNode? =
        info.getChild(index)?.let(::RealA11yNode)
    override fun recycle() = info.recycle()
}

/**
 * Recorrido BFS iterativo (nunca recursión: los árboles pueden ser profundos).
 * Reglas: solo nodos visibles (subárboles invisibles se podan), ids `n_i`
 * contiguos en orden BFS, tope `maxNodes`, `children` ⊆ ids del snapshot.
 */
object UiTreeExtractor {

    const val MAX_NODES = 500

    fun extract(
        root: A11yNode?,
        packageName: String,
        snapshotId: Long,
        maxNodes: Int = MAX_NODES
    ): UiSnapshot {
        if (root == null || maxNodes < 1) {
            return UiSnapshot(snapshotId, packageName, secure = root == null, nodes = emptyList())
        }
        if (!root.isVisibleToUser) {
            return UiSnapshot(snapshotId, packageName, secure = false, nodes = emptyList())
        }
        val nodes = ArrayList<UiNode>(256)
        val queue = ArrayDeque<Pair<String, A11yNode>>()
        var assigned = 1 // raíz incluida: incluidos + encolados nunca supera maxNodes
        queue.add("n_0" to root)
        while (queue.isNotEmpty() && nodes.size < maxNodes) {
            val (id, node) = queue.removeFirst()
            try {
                val childIds = ArrayList<String>(node.childCount)
                for (i in 0 until node.childCount) {
                    val child = node.getChild(i) ?: continue
                    if (assigned >= maxNodes || !child.isVisibleToUser) {
                        child.recycle()
                        continue
                    }
                    val childId = "n_${assigned++}"
                    childIds.add(childId)
                    queue.add(childId to child)
                }
                nodes.add(
                    UiNode(
                        id = id,
                        text = node.text?.toString(),
                        contentDesc = node.contentDescription?.toString(),
                        className = node.className?.toString(),
                        resourceId = node.viewIdResourceName,
                        bounds = node.boundsInScreen,
                        clickable = node.isClickable,
                        editable = node.isEditable,
                        scrollable = node.isScrollable,
                        enabled = node.isEnabled,
                        checked = node.isChecked,
                        focused = node.isFocused,
                        visible = true,
                        children = childIds
                    )
                )
            } finally {
                if (node !== root) node.recycle()
            }
        }
        // Invariante: si la cola se vacía, todo lo asignado quedó incluido.
        // Si nodes.size == maxNodes con cola no vacía, sobran encolados sin
        // incluir: se reciclan aquí para no fugar nodos nativos.
        while (queue.isNotEmpty()) {
            val (_, leftover) = queue.removeFirst()
            if (leftover !== root) leftover.recycle()
        }
        return UiSnapshot(snapshotId, packageName, secure = false, nodes = nodes)
    }
}
