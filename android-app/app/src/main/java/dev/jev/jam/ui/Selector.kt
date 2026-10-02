package dev.jev.jam.ui

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * Selector semántico (PROTOCOL.md §4.0). Semántica AND, primer match BFS,
 * determinista. `resource_id` admite sufijo, `index` elige el n-ésimo.
 */
@Serializable
data class Selector(
    val text: String? = null,
    @SerialName("text_contains") val textContains: String? = null,
    @SerialName("resource_id") val resourceId: String? = null,
    @SerialName("content_desc") val contentDesc: String? = null,
    @SerialName("class") val className: String? = null,
    val clickable: Boolean? = null,
    val index: Int = 0
)

object SelectorResolver {

    fun resolve(nodes: List<UiNode>, sel: Selector): UiNode? {
        var skipped = 0
        val want = sel.index.coerceAtLeast(0)
        for (n in nodes) {
            if (!matches(n, sel)) continue
            if (skipped < want) {
                skipped++
                continue
            }
            return n
        }
        return null
    }

    fun matches(n: UiNode, sel: Selector): Boolean {
        if (sel.text != null && n.text != sel.text) return false
        if (sel.textContains != null && (n.text == null || !n.text.contains(sel.textContains))) return false
        if (sel.resourceId != null) {
            val r = n.resourceId ?: return false
            if (r != sel.resourceId && !r.endsWith(sel.resourceId)) return false
        }
        if (sel.contentDesc != null && n.contentDesc != sel.contentDesc) return false
        if (sel.className != null && n.className != sel.className) return false
        if (sel.clickable != null && n.clickable != sel.clickable) return false
        return true
    }
}
