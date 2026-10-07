package dev.jev.jam.socket

import dev.jev.jam.ui.Selector
import kotlinx.serialization.Serializable
import kotlinx.serialization.SerialName
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.decodeFromJsonElement
import kotlinx.serialization.json.put

/** JSON del protocolo: tolerante en entrada, sin nulos en salida. */
val JamJson = Json {
    ignoreUnknownKeys = true
    explicitNulls = false
    encodeDefaults = true
}

@Serializable
data class WsRequest(
    val id: String,
    val method: String,
    val params: JsonObject = JsonObject(emptyMap())
)

@Serializable
data class WsResponse(
    val id: String? = null,
    val ok: Boolean,
    val result: JsonObject? = null,
    val error: String? = null,
    val code: String? = null
)

fun okResponse(id: String, result: JsonObject = JsonObject(emptyMap())): String =
    JamJson.encodeToString(WsResponse.serializer(), WsResponse(id, true, result))

fun errResponse(id: String?, error: String, code: String): String =
    JamJson.encodeToString(WsResponse.serializer(), WsResponse(id, false, null, error, code))

fun eventFrame(event: String, fields: Map<String, String> = emptyMap()): String {
    val obj = buildJsonObject {
        put("event", event)
        for ((k, v) in fields) put(k, v)
    }
    return JamJson.encodeToString(JsonObject.serializer(), obj)
}

/** Params por método (PROTOCOL.md §4). */

@Serializable
data class HelloParams(
    val protocol_version: Int = 0,
    val client_version: String = "",
    val token: String = "",
    val client: String = ""
)

/** Respuesta plana del handshake (PROTOCOL.md §2). */
@Serializable
data class HelloResult(
    val ok: Boolean = true,
    val protocol_version: Int = 1,
    val app_version: String = "",
    val scopes: List<String> = emptyList(),
    val caps: Map<String, Boolean> = emptyMap()
)

@Serializable
data class TapParams(val selector: Selector? = null)

@Serializable
data class TapNodeParams(val node_id: String = "", val snapshot_id: Long = -1)

@Serializable
data class TypeParams(val node_id: String = "", val snapshot_id: Long = -1, val text: String = "")

@Serializable
data class ScrollParams(val direction: String = "down", val node_id: String? = null)

@Serializable
data class WaitParams(val selector: Selector? = null, val timeout_ms: Long = 5000)

@Serializable
data class OpenAppParams(@SerialName("package") val pkg: String = "")

@Serializable
data class ForceStopParams(@SerialName("package") val pkg: String = "")

@Serializable
data class ScreenshotParams(val format: String = "png", val quality: Int = 80)

@Serializable
data class SetClipboardParams(val text: String = "")

/**
 * Params del catálogo native-apis (docs/specs/native-apis.md §§1–13).
 * N0 sin params nuevos salvo filtros; N1 con grants de usuario;
 * N2 (`detail=fine`, `settings_put` secure/global) lo rechaza el
 * dispatcher con `METHOD_NOT_ALLOWED` hasta Fase 6.
 */
@Serializable
data class DetailParams(val detail: String = "basic")

@Serializable
data class SettingsGetParams(val namespace: String = "system", val key: String = "")

@Serializable
data class SettingsPutParams(
    val namespace: String = "system",
    val key: String = "",
    val value: String = "",
    val confirm: Boolean = false
)

@Serializable
data class AppUsageParams(val hours: Int = 24, val window: String? = null)

@Serializable
data class ContactsParams(
    val query: String = "",
    val limit: Int = 50,
    val offset: Int = 0,
    val with_phone: Boolean = false
)

@Serializable
data class EventsParams(
    val time_min: Long = 0,
    val time_max: Long = 0,
    val calendar_id: Long = 0,
    val include_location: Boolean = false
)

@Serializable
data class NotifReplyParams(val key: String = "", val text: String = "", val confirm: Boolean = false)

@Serializable
data class MediaControlParams(
    val action: String = "",
    @SerialName("package") val pkg: String = "",
    val confirm: Boolean = false
)

@Serializable
data class LocationParams(val timeout_ms: Long = 8000, val max_age_s: Long = 300)

@Serializable
data class OpenUrlParams(val url: String = "")

@Serializable
data class SendIntentParams(
    val action: String = "",
    val uri: String = "",
    @SerialName("package") val pkg: String = "",
    val mime: String = "",
    val confirm: Boolean = false,
    val extras: Map<String, String> = emptyMap()
)

@Serializable
data class CreateEventParams(
    val calendar_id: Long = 0,
    val title: String = "",
    val start_ms: Long = 0,
    val end_ms: Long = 0,
    val description: String = "",
    val confirm: Boolean = false
)

@Serializable
data class AddContactParams(
    val display_name: String = "",
    val phone: String = "",
    val email: String = "",
    val confirm: Boolean = false
)

@Serializable
data class TakePhotoParams(val confirm: Boolean = false, val camera: String = "back")

/** Decodifica params o lanza JamError de validación. */
inline fun <reified T> decodeParams(req: WsRequest): T {
    try {
        return JamJson.decodeFromJsonElement(req.params)
    } catch (t: Throwable) {
        throw JamError("params inválidos para ${req.method}", "VALIDATION_ERROR")
    }
}
