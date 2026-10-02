package dev.jev.jam.socket

import android.content.Context
import dev.jev.jam.BuildConfig
import dev.jev.jam.service.JevAccessibilityService
import dev.jev.jam.shell.ShellActions
import dev.jev.jam.ui.UiSnapshot
import dev.jev.jam.util.JevLog
import kotlinx.serialization.builtins.ListSerializer
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.decodeFromJsonElement
import kotlinx.serialization.json.put
import rikka.shizuku.Shizuku

/** Error tipado del protocolo: mensaje para el cliente + código. */
class JamError(message: String, val code: String) : Exception(message)

/**
 * Enruta métodos WS a ejecutores. Grupo UI + 3a (open_app/force_stop/
 * screenshot). `shell` se rechaza explícito hasta Fase 6 (no es
 * "desconocido": está gateado). Sin `su` en ningún camino (AGENTS.md §2).
 */
class CommandDispatcher(private val appContext: Context) {

    private val token: String by lazy {
        AuthStore.getOrCreateToken(appContext).also {
            JevLog.i(TAG, "token WS activo (${it.length} chars)")
        }
    }

    fun hello(req: WsRequest): Pair<Set<String>?, String> {
        val p = try {
            JamJson.decodeFromJsonElement(HelloParams.serializer(), req.params)
        } catch (t: Throwable) {
            return null to errResponse(req.id, "hello inválido", "VALIDATION_ERROR")
        }
        if (p.protocol_version != PROTOCOL_VERSION) {
            return null to errResponse(
                req.id, "protocol_version debe ser $PROTOCOL_VERSION", "PROTOCOL_MISMATCH"
            )
        }
        if (!AuthStore.verify(p.token, token)) {
            return null to errResponse(req.id, "token inválido", "UNAUTHORIZED")
        }
        val scopes = setOf("read", "ui")
        val acc = JevAccessibilityService.instance != null
        val shizuku = try {
            Shizuku.pingBinder()
        } catch (t: Throwable) {
            false
        }
        // Respuesta plana según PROTOCOL §2 (sin envoltura id/result).
        val frame = JamJson.encodeToString(
            HelloResult.serializer(),
            HelloResult(
                protocol_version = PROTOCOL_VERSION,
                app_version = BuildConfig.VERSION_NAME,
                scopes = scopes.toList(),
                caps = mapOf(
                    "accessibility" to acc,
                    "shizuku" to shizuku,
                    "shell_grant" to false
                )
            )
        )
        return scopes to frame
    }

    fun dispatch(req: WsRequest, scopes: Set<String>): String {
        return try {
            when (req.method) {
                "dump_ui" -> dumpUi(req)
                "tap" -> tap(req)
                "tap_node" -> tapNode(req)
                "type" -> type(req)
                "scroll" -> scroll(req)
                "press_back" -> globalBack(req)
                "press_home" -> globalHome(req)
                "wait_for_node" -> waitFor(req)
                "get_foreground" -> foreground(req)
                "open_app" -> openApp(req)
                "force_stop" -> forceStop(req)
                "screenshot" -> screenshot(req)
                "shell" -> throw JamError(
                    "shell se habilita en Fase 6 (seguridad cerrada)", "METHOD_NOT_ALLOWED"
                )
                else -> throw JamError("método desconocido: ${req.method}", "METHOD_NOT_ALLOWED")
            }
        } catch (e: JamError) {
            errResponse(req.id, e.message ?: "error", e.code)
        }
    }

    private fun svc(): JevAccessibilityService =
        JevAccessibilityService.instance
            ?: throw JamError("accesibilidad no conectada", "ACCESSIBILITY_DISABLED")

    private fun snapshotJson(s: UiSnapshot) = buildJsonObject {
        put("snapshot_id", s.snapshotId)
        put("package", s.packageName)
        put("activity", s.activity)
        put("timestamp", s.timestamp)
        put("nodes", JamJson.encodeToJsonElement(ListSerializer(dev.jev.jam.ui.UiNode.serializer()), s.nodes))
    }

    private fun dumpUi(req: WsRequest): String =
        okResponse(req.id, snapshotJson(svc().dumpUiTree()))

    private fun tap(req: WsRequest): String {
        val p = decodeParams<TapParams>(req)
        val sel = p.selector ?: throw JamError("tap requiere selector", "VALIDATION_ERROR")
        val r = svc().tapBySelector(sel)
        return okResponse(req.id, buildJsonObject {
            put("node_id", r.nodeId)
            put("via", r.via)
        })
    }

    private fun tapNode(req: WsRequest): String {
        val p = decodeParams<TapNodeParams>(req)
        if (p.node_id.isEmpty()) throw JamError("node_id vacío", "VALIDATION_ERROR")
        val r = svc().tapNode(p.node_id, p.snapshot_id)
        return okResponse(req.id, buildJsonObject {
            put("node_id", r.nodeId)
            put("via", r.via)
        })
    }

    private fun type(req: WsRequest): String {
        val p = decodeParams<TypeParams>(req)
        if (p.node_id.isEmpty()) throw JamError("node_id vacío", "VALIDATION_ERROR")
        val chars = svc().typeNode(p.node_id, p.snapshot_id, p.text)
        return okResponse(req.id, buildJsonObject {
            put("chars", chars)
        })
    }

    private fun scroll(req: WsRequest): String {
        val p = decodeParams<ScrollParams>(req)
        svc().scrollBy(p.direction, p.node_id)
        return okResponse(req.id)
    }

    private fun globalBack(req: WsRequest): String {
        svc().pressBack()
        return okResponse(req.id)
    }

    private fun globalHome(req: WsRequest): String {
        svc().pressHome()
        return okResponse(req.id)
    }

    private fun waitFor(req: WsRequest): String {
        val p = decodeParams<WaitParams>(req)
        val sel = p.selector ?: throw JamError("wait_for_node requiere selector", "VALIDATION_ERROR")
        val (nodeId, snapshotId) = svc().waitForNode(sel, p.timeout_ms)
        return okResponse(req.id, buildJsonObject {
            put("node_id", nodeId)
            put("snapshot_id", snapshotId)
        })
    }

    private fun foreground(req: WsRequest): String {
        val (pkg, act) = svc().getForeground()
        return okResponse(req.id, buildJsonObject {
            put("package", pkg)
            put("activity", act)
        })
    }

    private fun openApp(req: WsRequest): String {
        val p = decodeParams<OpenAppParams>(req)
        val (pkg, act) = svc().openApp(p.pkg)
        return okResponse(req.id, buildJsonObject {
            put("package", pkg)
            put("activity", act)
        })
    }

    private fun forceStop(req: WsRequest): String {
        val p = decodeParams<ForceStopParams>(req)
        // Sin svc(): force_stop no necesita accesibilidad (sigue vivo degradado).
        ShellActions.forceStop(p.pkg)
        return okResponse(req.id)
    }

    private fun screenshot(req: WsRequest): String {
        val p = decodeParams<ScreenshotParams>(req)
        val s = svc().screenshotPng(p.format, p.quality)
        return okResponse(req.id, buildJsonObject {
            put("img_base64", s.img)
            put("w", s.w)
            put("h", s.h)
            put("via", s.via)
        })
    }

    companion object {
        private const val TAG = "JamWs"
        const val PROTOCOL_VERSION = 1
    }
}
