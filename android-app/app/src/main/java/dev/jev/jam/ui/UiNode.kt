package dev.jev.jam.ui

/**
 * Nodo normalizado de UI. Schema exacto: PROTOCOL.md §5.
 * `nodes` es array plano; el parentesco va por `children` (ids).
 * La anotación @Serializable llega en la Fase 2 con el socket.
 */
data class UiNode(
    val id: String,
    val text: String?,
    val contentDesc: String?,
    val className: String?,
    val resourceId: String?,
    /** [left, top, right, bottom] en píxeles de pantalla. */
    val bounds: List<Int>,
    val clickable: Boolean,
    val editable: Boolean,
    val scrollable: Boolean,
    val enabled: Boolean,
    val checked: Boolean,
    val focused: Boolean,
    val visible: Boolean,
    val children: List<String>
)

data class UiSnapshot(
    val snapshotId: Long,
    val packageName: String,
    /** true si no hay ventana activa (p.ej. FLAG_SECURE): nodes == []. */
    val secure: Boolean,
    val nodes: List<UiNode>
)
