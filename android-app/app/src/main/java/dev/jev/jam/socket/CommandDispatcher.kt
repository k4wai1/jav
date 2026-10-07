package dev.jev.jam.socket

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.pm.PackageManager
import androidx.core.content.ContextCompat
import dev.jev.jam.BuildConfig
import dev.jev.jam.nat.CameraCapture
import dev.jev.jam.nat.NatPolicies
import dev.jev.jam.nat.NativeDevice
import dev.jev.jam.nat.NativeSensitive
import dev.jev.jam.nat.photoResult
import dev.jev.jam.service.JamNotificationListener
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
        // Caps N1 del catálogo native-apis: grants de usuario por método.
        // (Líneas nuevas de protocolo propuestas → las anota @architect.)
        fun granted(perm: String) =
            ContextCompat.checkSelfPermission(appContext, perm) ==
                PackageManager.PERMISSION_GRANTED
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
                    "shell_grant" to false,
                    "usage_access" to NativeSensitive.hasUsageAccess(appContext),
                    "notification_listening" to JamNotificationListener.isConnected(),
                    "contacts" to granted(android.Manifest.permission.READ_CONTACTS),
                    "calendar" to granted(android.Manifest.permission.READ_CALENDAR),
                    "location" to (granted(
                        android.Manifest.permission.ACCESS_FINE_LOCATION
                    ) || granted(android.Manifest.permission.ACCESS_COARSE_LOCATION)),
                    "camera" to granted(android.Manifest.permission.CAMERA)
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
                "set_clipboard" -> setClipboard(req)
                // Catálogo native-apis N0 (sin permisos nuevos), scope read/ui.
                "get_battery" -> okResponse(req.id, NativeDevice.getBattery(appContext))
                "get_memory" -> okResponse(req.id, NativeDevice.getMemory(appContext))
                "get_storage" -> storage(req)
                "get_cpu" -> cpu(req)
                "get_device_info" -> okResponse(req.id, NativeDevice.getDeviceInfo(appContext))
                "settings_get" -> settingsGet(req)
                "open_url" -> openUrl(req)
                "send_intent" -> sendIntent(req)
                "get_clipboard" -> okResponse(req.id, NativeSensitive.getClipboardFg(appContext))
                // Catálogo N1 (grants de usuario), lectura sensible + críticas con confirm.
                "get_app_usage" -> appUsage(req)
                "list_contacts" -> listContacts(req)
                "add_contact" -> addContact(req)
                "list_events" -> listEvents(req)
                "create_event" -> createEvent(req)
                "list_notifications" -> okResponse(req.id, NativeSensitive.listNotifications())
                "reply_notification" -> replyNotif(req)
                "media_state" -> okResponse(req.id, NativeSensitive.mediaState(appContext))
                "media_control" -> mediaControl(req)
                "get_location" -> location(req)
                "take_photo" -> takePhoto(req)
                "settings_put" -> settingsPut(req)
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

    /**
     * v5 director-client §4.1: escribe el clipboard del SO sin shell.
     * La propia app Jam ejecuta `ClipboardManager.setPrimaryClip`
     * (foreground service, sin Shizuku, sin grant de shell; misma clase
     * de API que `takeScreenshot`/`ACTION_SET_TEXT`, no un exec).
     * Scope `ui`, sin grant. La lectura sigue por host `dumpsys`
     * (Android 10+ restringe leer al foreground/IME).
     */
    private fun setClipboard(req: WsRequest): String {
        val p = decodeParams<SetClipboardParams>(req)
        if (p.text.isEmpty()) throw JamError("text vacío", "VALIDATION_ERROR")
        val cm = appContext.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        cm.setPrimaryClip(ClipData.newPlainText("jev", p.text))
        return okResponse(req.id, buildJsonObject {
            put("chars", p.text.length)
        })
    }

    // ---- catálogo native-apis (N0 + N1; N2 = METHOD_NOT_ALLOWED) ----

    private fun storage(req: WsRequest): String {
        val p = decodeParams<DetailParams>(req)
        // detail=fine → N2 (dumpsys vía Shizuku, Fase 6+): stub honesto.
        return okResponse(req.id, NativeDevice.getStorage(p.detail))
    }

    private fun cpu(req: WsRequest): String {
        val p = decodeParams<DetailParams>(req)
        // detail=fine → N2 (per-proceso vía Shizuku, Fase 6+): stub honesto.
        return okResponse(req.id, NativeDevice.getCpu(p.detail))
    }

    private fun settingsGet(req: WsRequest): String {
        val p = decodeParams<SettingsGetParams>(req)
        return okResponse(req.id, NativeDevice.settingsGet(appContext, p.namespace, p.key))
    }

    /**
     * N2 salvo namespace `system` (P1 con WRITE_SETTINGS): Secure/Global
     * directo es IMPOSIBLE non-root; vía Shizuku-shell llega en Fase 6+.
     */
    private fun settingsPut(req: WsRequest): String {
        val p = decodeParams<SettingsPutParams>(req)
        if (!NatPolicies.putAllowed(p.namespace)) {
            throw JamError(
                "settings_put ${p.namespace} requiere Shizuku/shell (Fase 6+)",
                "METHOD_NOT_ALLOWED"
            )
        }
        if (!p.confirm) return okResponse(req.id, NativeSensitive.planned(
            mapOf("namespace" to p.namespace, "key" to p.key,
                "value_sha256" to NativeSensitive.sha256(p.value))
        ))
        return okResponse(req.id, NativeSensitive.settingsPut(appContext, p.namespace, p.key, p.value))
    }

    private fun openUrl(req: WsRequest): String {
        val p = decodeParams<OpenUrlParams>(req)
        return okResponse(req.id, NativeSensitive.openUrl(appContext, p.url))
    }

    private fun sendIntent(req: WsRequest): String {
        val p = decodeParams<SendIntentParams>(req)
        return okResponse(
            req.id,
            NativeSensitive.sendIntent(
                appContext, p.action, p.uri, p.pkg, p.mime, p.confirm, p.extras
            )
        )
    }

    private fun appUsage(req: WsRequest): String {
        val p = decodeParams<AppUsageParams>(req)
        return okResponse(req.id, NativeSensitive.getAppUsage(appContext, p.hours, p.window))
    }

    private fun listContacts(req: WsRequest): String {
        val p = decodeParams<ContactsParams>(req)
        return okResponse(
            req.id,
            NativeSensitive.listContacts(appContext, p.query, p.limit, p.offset, p.with_phone)
        )
    }

    private fun addContact(req: WsRequest): String {
        val p = decodeParams<AddContactParams>(req)
        return okResponse(
            req.id,
            NativeSensitive.addContact(appContext, p.display_name, p.phone, p.email, p.confirm)
        )
    }

    private fun listEvents(req: WsRequest): String {
        val p = decodeParams<EventsParams>(req)
        return okResponse(
            req.id,
            NativeSensitive.listEvents(
                appContext, p.time_min, p.time_max, p.calendar_id, p.include_location
            )
        )
    }

    private fun createEvent(req: WsRequest): String {
        val p = decodeParams<CreateEventParams>(req)
        return okResponse(
            req.id,
            NativeSensitive.createEvent(
                appContext, p.calendar_id, p.title, p.start_ms, p.end_ms,
                p.description, p.confirm
            )
        )
    }

    private fun replyNotif(req: WsRequest): String {
        val p = decodeParams<NotifReplyParams>(req)
        return okResponse(
            req.id, NativeSensitive.replyNotification(appContext, p.key, p.text, p.confirm)
        )
    }

    private fun mediaControl(req: WsRequest): String {
        val p = decodeParams<MediaControlParams>(req)
        return okResponse(
            req.id, NativeSensitive.mediaControl(appContext, p.action, p.pkg, p.confirm)
        )
    }

    private fun location(req: WsRequest): String {
        val p = decodeParams<LocationParams>(req)
        return okResponse(
            req.id, NativeSensitive.getLocation(appContext, p.timeout_ms, p.max_age_s)
        )
    }

    /** P1-restringida: FGS + notificación + `confirm` siempre; nunca silenciosa. */
    private fun takePhoto(req: WsRequest): String {
        val p = decodeParams<TakePhotoParams>(req)
        NativeSensitive.takePhotoGate(p.confirm)?.let { return okResponse(req.id, it) }
        val b64 = CameraCapture.capture(appContext, p.camera)
        return okResponse(req.id, photoResult(b64))
    }

    companion object {
        private const val TAG = "JamWs"
        const val PROTOCOL_VERSION = 1
    }
}
