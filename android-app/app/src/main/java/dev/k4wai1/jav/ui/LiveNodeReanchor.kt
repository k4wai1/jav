package dev.k4wai1.jav.ui

/**
 * Resultado de [LiveNodeReanchor.reanchor]. Invariante: `node != null`
 * <=> `status.found`. Cuando `node != null` es propiedad del helper y
 * **el llamador debe reciclarlo** (`node.recycle()`).
 */
enum class ReanchorStatus(val errorCode: String?) {
    EXACT(null),
    REANCHORED(null),
    NOT_FOUND("STALE_SNAPSHOT"),
    AMBIGUOUS("STALE_SNAPSHOT"),
    NO_WINDOW("SELECTOR_NOT_FOUND");

    val found: Boolean get() = errorCode == null
}

data class ReanchorResult(
    val node: A11yNode?,
    val status: ReanchorStatus
) {
    /** true solo si se recuperó por proximidad (paso 2), no por posición. */
    val reanchored: Boolean get() = status == ReanchorStatus.REANCHORED
}

object LiveNodeReanchor {
    /** Tope de nodos visitados: el mismo del extractor. */
    const val MAX_NODES: Int = UiTreeExtractor.MAX_NODES

    /** Deriva máxima tolerada del centroide, en px lógicos de a11y. */
    const val MAX_DRIFT_PX: Int = 24

    fun reanchor(
        root: A11yNode?,
        expected: UiNode,
        expectedIdx: Int,
        maxDriftPx: Int = MAX_DRIFT_PX,
        maxNodes: Int = MAX_NODES
    ): ReanchorResult {
        if (root == null || !root.isVisibleToUser || maxNodes < 1) {
            return ReanchorResult(null, ReanchorStatus.NO_WINDOW)
        }
        if (expectedIdx < 0) {
            return ReanchorResult(null, ReanchorStatus.NOT_FOUND)
        }

        val queue = ArrayDeque<A11yNode>()
        val owned = ArrayList<A11yNode>()
        val candidates = ArrayList<A11yNode>()
        val want = centroid(expected.bounds)
        queue.add(root)
        var visited = 0
        var winner: A11yNode? = null
        var status = ReanchorStatus.NOT_FOUND

        while (queue.isNotEmpty() && visited < maxNodes) {
            val n = queue.removeFirst()
            if (visited == expectedIdx && matchesIdentity(n, expected)) {
                winner = n
                status = ReanchorStatus.EXACT
                break
            }
            if (matchesIdentity(n, expected)) {
                val c = centroid(n.boundsInScreen)
                if (c != null && want != null && chebyshev(c, want) <= maxDriftPx) {
                    candidates.add(n)
                }
            }
            visited++
            for (i in 0 until n.childCount) {
                val ch = n.getChild(i) ?: continue
                if (!ch.isVisibleToUser) {
                    ch.recycle()
                    continue
                }
                owned.add(ch)
                queue.add(ch)
            }
        }

        if (winner == null) {
            when (candidates.size) {
                1 -> {
                    winner = candidates[0]
                    status = ReanchorStatus.REANCHORED
                }
                0 -> status = ReanchorStatus.NOT_FOUND
                else -> status = ReanchorStatus.AMBIGUOUS
            }
        }
        for (n in owned) if (n !== winner) n.recycle()
        return ReanchorResult(winner, status)
    }

    fun matchesIdentity(live: A11yNode, expected: UiNode): Boolean =
        live.text?.toString() == expected.text &&
            live.viewIdResourceName == expected.resourceId &&
            live.className?.toString() == expected.className &&
            live.contentDescription?.toString() == expected.contentDesc
}

private fun centroid(b: List<Int>): Pair<Int, Int>? =
    if (b.size == 4) (b[0] + b[2]) / 2 to (b[1] + b[3]) / 2 else null

private fun chebyshev(a: Pair<Int, Int>, b: Pair<Int, Int>): Int =
    maxOf(kotlin.math.abs(a.first - b.first), kotlin.math.abs(a.second - b.second))
