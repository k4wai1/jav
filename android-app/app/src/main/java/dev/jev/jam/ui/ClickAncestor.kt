package dev.jev.jam.ui

/**
 * Walk-up al contenedor interactivo (spec tactical-robustness-p1p2 §3).
 * Muchos nodos accionables exponen el clickable en un ancestro (el hijo es
 * un TextView/ViewGroup decorativo). El helper no muta el árbol: solo
 * asciende, ejecuta ACTION_CLICK y libera lo que obtuvo.
 */
object ClickAncestor {
    const val MAX_HOPS = 3

    /**
     * Primer ancestro clickable y visible (<= [maxHops]) cuyo
     * [A11yNode.performClick] tenga éxito. Devuelve `null` si no hay
     * ninguno. El nodo raíz [node] es prestado (no se recicla aquí); el
     * resto de nodos obtenidos por `parent()` se reciclan salvo el
     * devuelto, que el llamador debe reciclar.
     */
    fun find(node: A11yNode?, maxHops: Int = MAX_HOPS): A11yNode? {
        if (node == null || maxHops <= 0) return null
        val obtained = ArrayList<A11yNode>(maxHops)
        var cursor: A11yNode? = node
        var winner: A11yNode? = null
        var hops = 0
        while (hops < maxHops) {
            val parent = cursor?.parent() ?: break
            obtained.add(parent)
            cursor = parent
            hops++
            if (parent.isClickable && parent.isVisibleToUser && parent.performClick()) {
                winner = parent
                break
            }
        }
        for (n in obtained) {
            if (n !== winner) n.recycle()
        }
        return winner
    }
}
