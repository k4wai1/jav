package dev.jev.jam.ui

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * Nodo normalizado de UI. Schema exacto: PROTOCOL.md §5.
 * `nodes` es array plano; el parentesco va por `children` (ids).
 */
@Serializable
data class UiNode(
    val id: String,
    val text: String?,
    @SerialName("content_desc") val contentDesc: String?,
    @SerialName("class") val className: String?,
    @SerialName("resource_id") val resourceId: String?,
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

@Serializable
data class UiSnapshot(
    @SerialName("snapshot_id") val snapshotId: Long,
    @SerialName("package") val packageName: String,
    val activity: String = "",
    val timestamp: Long = 0L,
    val nodes: List<UiNode> = emptyList()
)
