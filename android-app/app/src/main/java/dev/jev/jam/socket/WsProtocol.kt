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

/** Decodifica params o lanza JamError de validación. */
inline fun <reified T> decodeParams(req: WsRequest): T {
    try {
        return JamJson.decodeFromJsonElement(req.params)
    } catch (t: Throwable) {
        throw JamError("params inválidos para ${req.method}", "VALIDATION_ERROR")
    }
}
