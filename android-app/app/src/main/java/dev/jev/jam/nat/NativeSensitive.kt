package dev.jev.jam.nat

import android.Manifest
import android.app.AppOpsManager
import android.app.Notification
import android.app.PendingIntent
import android.app.RemoteInput
import android.app.usage.UsageStatsManager
import android.content.ComponentName
import android.content.ContentProviderOperation
import android.content.ContentUris
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.location.Location
import android.location.LocationListener
import android.location.LocationManager
import android.media.session.MediaSessionManager
import android.net.Uri
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.provider.CalendarContract
import android.provider.ContactsContract
import android.provider.Settings
import androidx.core.content.ContextCompat
import dev.jev.jam.service.JamNotificationListener
import dev.jev.jam.shell.ShizukuBridge
import dev.jev.jam.socket.JamError
import java.security.MessageDigest
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

/**
 * Lecturas/acciones N1 (con grant del usuario) + intents P0.
 * Sin `su` en ningún camino; Shizuku solo para `am start` (misma clase
 * que `open_app`). Escrituras y acciones críticas: `confirm: true`;
 * sin él → `{planned: true, preview}` sin ejecutar.
 * PII (contactos, ubicación, calendario, notificaciones): proyección
 * mínima; el hash/longitud para forense lo pone el lado MCP.
 */
object NativeSensitive {

    fun sha256(s: String): String {
        val d = MessageDigest.getInstance("SHA-256").digest(s.toByteArray(Charsets.UTF_8))
        return d.joinToString("") { "%02x".format(it) }
    }

    private fun granted(ctx: Context, perm: String): Boolean =
        ContextCompat.checkSelfPermission(ctx, perm) == PackageManager.PERMISSION_GRANTED

    // ---- uso de apps (P1, PACKAGE_USAGE_STATS, acceso especial) ----

    fun hasUsageAccess(ctx: Context): Boolean {
        return try {
            val ops = ctx.getSystemService(Context.APP_OPS_SERVICE) as AppOpsManager
            @Suppress("DEPRECATION")
            ops.checkOpNoThrow(
                AppOpsManager.OPSTR_GET_USAGE_STATS,
                android.os.Process.myUid(), ctx.packageName
            ) == AppOpsManager.MODE_ALLOWED
        } catch (t: Throwable) {
            false
        }
    }

    /**
     * Uso agregado por paquete. `window` opcional:
     *  - null/"": últimas `hours` (1..24, compat previa)
     *  - "today": desde medianoche local de hoy
     *  - "week": últimos 7 días
     *  - "raw": últimas `hours` (1..168)
     * Suma `totalTimeInForeground` por paquete en el rango (top 50).
     * `INTERVAL_DAILY` sirve para rangos multi-día: se suman los buckets.
     */
    fun getAppUsage(ctx: Context, hours: Int, window: String? = null): JsonObject {
        if (!hasUsageAccess(ctx)) {
            throw JamError(
                "acceso a uso no concedido; Ajustes → Acceso a datos de uso → Jam",
                "USAGE_ACCESS_DISABLED"
            )
        }
        val win = window?.trim()?.lowercase()?.takeIf { it.isNotEmpty() }
        if (!NatPolicies.validUsageWindow(win)) {
            throw JamError(
                "window debe ser today|week|raw (o vacío)",
                "VALIDATION_ERROR"
            )
        }
        val now = System.currentTimeMillis()
        val begin = NatPolicies.usageBegin(now, win, hours)
        val usm = ctx.getSystemService(Context.USAGE_STATS_SERVICE) as UsageStatsManager
        val stats = try {
            usm.queryUsageStats(UsageStatsManager.INTERVAL_DAILY, begin, now).orEmpty()
        } catch (t: SecurityException) {
            throw JamError("UsageStats denegado por el sistema", "USAGE_ACCESS_DISABLED")
        }
        val agg = stats.groupBy { it.packageName }.map { (pkg, list) ->
            pkg to (list.sumOf { it.totalTimeInForeground } to
                (list.maxOfOrNull { it.lastTimeUsed } ?: 0L))
        }.sortedByDescending { it.second.first }.take(50)
        return buildJsonObject {
            put("window", win ?: "hours")
            put("begin", begin)
            put("now", now)
            put("window_h", ((now - begin) / NatPolicies.HOUR_MS).toInt())
            put("count", agg.size)
            put("apps", buildJsonArray {
                for ((pkg, tt) in agg) {
                    add(buildJsonObject {
                        put("package", pkg)
                        put("foreground_ms", tt.first)
                        put("last_used", tt.second)
                    })
                }
            })
        }
    }

    // ---- contactos (P1, READ_CONTACTS runtime) ----

    fun listContacts(
        ctx: Context, query: String, limit: Int, offset: Int, withPhone: Boolean
    ): JsonObject {
        if (!granted(ctx, Manifest.permission.READ_CONTACTS)) {
            throw JamError(
                "READ_CONTACTS no concedido; pide el permiso en la app Jam",
                "CONTACTS_PERMISSION_DENIED"
            )
        }
        val lim = limit.coerceIn(1, 100)
        val off = offset.coerceAtLeast(0)
        val sel = if (query.isBlank()) null else "${ContactsContract.Contacts.DISPLAY_NAME} LIKE ?"
        val args = if (query.isBlank()) null else arrayOf("%$query%")
        val out = ArrayList<JsonObject>()
        var skipped = 0
        ctx.contentResolver.query(
            ContactsContract.Contacts.CONTENT_URI,
            arrayOf(ContactsContract.Contacts._ID, ContactsContract.Contacts.DISPLAY_NAME),
            sel, args,
            "${ContactsContract.Contacts.DISPLAY_NAME} ASC"
        )?.use { c ->
            val idCol = c.getColumnIndexOrThrow(ContactsContract.Contacts._ID)
            val nameCol = c.getColumnIndexOrThrow(ContactsContract.Contacts.DISPLAY_NAME)
            while (c.moveToNext()) {
                if (skipped < off) {
                    skipped++
                    continue
                }
                if (out.size >= lim) break
                val id = c.getLong(idCol)
                val name = c.getString(nameCol).orEmpty()
                var phone: String? = null
                if (withPhone) {
                    ctx.contentResolver.query(
                        ContactsContract.CommonDataKinds.Phone.CONTENT_URI,
                        arrayOf(ContactsContract.CommonDataKinds.Phone.NUMBER),
                        "${ContactsContract.CommonDataKinds.Phone.CONTACT_ID} = ?",
                        arrayOf(id.toString()), null
                    )?.use { p ->
                        if (p.moveToFirst()) phone = p.getString(0)
                    }
                }
                out.add(buildJsonObject {
                    put("id", id)
                    put("display_name", name)
                    if (phone != null) put("phone", phone!!)
                })
            }
        }
        return buildJsonObject {
            put("returned", out.size)
            put("offset", off)
            put("contacts", buildJsonArray { out.forEach { add(it) } })
        }
    }

    fun addContact(
        ctx: Context, name: String, phone: String, email: String, confirm: Boolean
    ): JsonObject {
        if (name.isBlank()) throw JamError("display_name vacío", "VALIDATION_ERROR")
        if (!confirm) {
            return planned(
                mapOf("display_name" to name, "phone_len" to phone.length.toString(),
                    "email_len" to email.length.toString())
            )
        }
        if (!granted(ctx, Manifest.permission.WRITE_CONTACTS)) {
            throw JamError("WRITE_CONTACTS no concedido", "CONTACTS_PERMISSION_DENIED")
        }
        val ops = ArrayList<ContentProviderOperation>()
        ops.add(
            ContentProviderOperation.newInsert(ContactsContract.RawContacts.CONTENT_URI)
                .withValue(ContactsContract.RawContacts.ACCOUNT_TYPE, null as String?)
                .withValue(ContactsContract.RawContacts.ACCOUNT_NAME, null as String?)
                .build()
        )
        ops.add(
            ContentProviderOperation.newInsert(ContactsContract.Data.CONTENT_URI)
                .withValueBackReference(ContactsContract.Data.RAW_CONTACT_ID, 0)
                .withValue(
                    ContactsContract.Data.MIMETYPE,
                    ContactsContract.CommonDataKinds.StructuredName.CONTENT_ITEM_TYPE
                )
                .withValue(ContactsContract.CommonDataKinds.StructuredName.DISPLAY_NAME, name)
                .build()
        )
        if (phone.isNotBlank()) {
            ops.add(
                ContentProviderOperation.newInsert(ContactsContract.Data.CONTENT_URI)
                    .withValueBackReference(ContactsContract.Data.RAW_CONTACT_ID, 0)
                    .withValue(
                        ContactsContract.Data.MIMETYPE,
                        ContactsContract.CommonDataKinds.Phone.CONTENT_ITEM_TYPE
                    )
                    .withValue(ContactsContract.CommonDataKinds.Phone.NUMBER, phone)
                    .withValue(
                        ContactsContract.CommonDataKinds.Phone.TYPE,
                        ContactsContract.CommonDataKinds.Phone.TYPE_MOBILE
                    )
                    .build()
            )
        }
        if (email.isNotBlank()) {
            ops.add(
                ContentProviderOperation.newInsert(ContactsContract.Data.CONTENT_URI)
                    .withValueBackReference(ContactsContract.Data.RAW_CONTACT_ID, 0)
                    .withValue(
                        ContactsContract.Data.MIMETYPE,
                        ContactsContract.CommonDataKinds.Email.CONTENT_ITEM_TYPE
                    )
                    .withValue(ContactsContract.CommonDataKinds.Email.ADDRESS, email)
                    .build()
            )
        }
        return try {
            val res = ctx.contentResolver.applyBatch(ContactsContract.AUTHORITY, ops)
            buildJsonObject {
                put("added", true)
                put("ops", ops.size)
                put("uri", res.firstOrNull()?.uri?.toString().orEmpty())
            }
        } catch (t: Exception) {
            throw JamError("alta falló: ${t.message?.take(150)}", "INTERNAL_ERROR")
        }
    }

    // ---- calendario (P1, READ_CALENDAR / WRITE_CALENDAR runtime) ----

    fun listEvents(
        ctx: Context, timeMin: Long, timeMax: Long, calendarId: Long, includeLocation: Boolean
    ): JsonObject {
        if (!granted(ctx, Manifest.permission.READ_CALENDAR)) {
            throw JamError(
                "READ_CALENDAR no concedido; pide el permiso en la app Jam",
                "CALENDAR_PERMISSION_DENIED"
            )
        }
        val now = System.currentTimeMillis()
        val tMin = if (timeMin <= 0) now else timeMin
        val tMax = if (timeMax <= 0) tMin + NatPolicies.MAX_WINDOW_MS else timeMax
        if (!NatPolicies.windowOk(tMax - tMin)) {
            throw JamError("ventana > 7 días; acota time_min/time_max", "VALIDATION_ERROR")
        }
        val uri = CalendarContract.Instances.CONTENT_URI.buildUpon()
            .let { ContentUris.appendId(it, tMin); ContentUris.appendId(it, tMax); it.build() }
        val proj = mutableListOf(
            CalendarContract.Instances.EVENT_ID,
            CalendarContract.Instances.TITLE,
            CalendarContract.Instances.BEGIN,
            CalendarContract.Instances.END,
            CalendarContract.Instances.CALENDAR_ID
        )
        if (includeLocation) proj.add(CalendarContract.Instances.EVENT_LOCATION)
        val sel = if (calendarId > 0) "${CalendarContract.Instances.CALENDAR_ID} = ?" else null
        val args = if (calendarId > 0) arrayOf(calendarId.toString()) else null
        val out = ArrayList<JsonObject>()
        ctx.contentResolver.query(
            uri, proj.toTypedArray(), sel, args,
            "${CalendarContract.Instances.BEGIN} ASC"
        )?.use { c ->
            val iId = c.getColumnIndexOrThrow(CalendarContract.Instances.EVENT_ID)
            val iTitle = c.getColumnIndexOrThrow(CalendarContract.Instances.TITLE)
            val iBegin = c.getColumnIndexOrThrow(CalendarContract.Instances.BEGIN)
            val iEnd = c.getColumnIndexOrThrow(CalendarContract.Instances.END)
            val iCal = c.getColumnIndexOrThrow(CalendarContract.Instances.CALENDAR_ID)
            val iLoc = if (includeLocation) {
                c.getColumnIndex(CalendarContract.Instances.EVENT_LOCATION)
            } else -1
            while (c.moveToNext() && out.size < 100) {
                val loc = if (iLoc >= 0) c.getString(iLoc).orEmpty() else ""
                out.add(buildJsonObject {
                    put("event_id", c.getLong(iId))
                    put("title", c.getString(iTitle).orEmpty())
                    put("begin", c.getLong(iBegin))
                    put("end", c.getLong(iEnd))
                    put("calendar_id", c.getString(iCal).orEmpty())
                    if (includeLocation) put("location", loc)
                })
            }
        }
        return buildJsonObject {
            put("time_min", tMin)
            put("time_max", tMax)
            put("returned", out.size)
            put("events", buildJsonArray { out.forEach { add(it) } })
        }
    }

    fun createEvent(
        ctx: Context, calendarId: Long, title: String,
        startMs: Long, endMs: Long, description: String, confirm: Boolean
    ): JsonObject {
        if (title.isBlank() || startMs <= 0 || endMs <= startMs) {
            throw JamError("title/start_ms/end_ms inválidos", "VALIDATION_ERROR")
        }
        if (!confirm) {
            return planned(
                mapOf("title_sha256" to sha256(title), "title_len" to title.length.toString(),
                    "start" to startMs.toString(), "end" to endMs.toString())
            )
        }
        if (!granted(ctx, Manifest.permission.WRITE_CALENDAR)) {
            throw JamError("WRITE_CALENDAR no concedido", "CALENDAR_PERMISSION_DENIED")
        }
        val calId = if (calendarId > 0) calendarId else defaultCalendarId(ctx)
            ?: throw JamError("sin calendarios visibles", "CALENDAR_UNAVAILABLE")
        val values = android.content.ContentValues().apply {
            put(CalendarContract.Events.CALENDAR_ID, calId)
            put(CalendarContract.Events.TITLE, title)
            put(CalendarContract.Events.DTSTART, startMs)
            put(CalendarContract.Events.DTEND, endMs)
            if (description.isNotBlank()) put(CalendarContract.Events.DESCRIPTION, description)
            put(CalendarContract.Events.EVENT_TIMEZONE, java.util.TimeZone.getDefault().id)
        }
        return try {
            val uri = ctx.contentResolver.insert(CalendarContract.Events.CONTENT_URI, values)
                ?: throw JamError("insert nulo", "INTERNAL_ERROR")
            buildJsonObject {
                put("created", true)
                put("event_id", uri.lastPathSegment.orEmpty())
            }
        } catch (t: Exception) {
            if (t is JamError) throw t
            throw JamError("alta falló: ${t.message?.take(150)}", "INTERNAL_ERROR")
        }
    }

    private fun defaultCalendarId(ctx: Context): Long? {
        ctx.contentResolver.query(
            CalendarContract.Calendars.CONTENT_URI,
            arrayOf(CalendarContract.Calendars._ID),
            "${CalendarContract.Calendars.VISIBLE} = 1", null,
            "${CalendarContract.Calendars._ID} ASC"
        )?.use { c ->
            if (c.moveToFirst()) return c.getLong(0)
        }
        return null
    }

    // ---- notificaciones + media (P1, NotificationListener) ----

    fun listNotifications(): JsonObject {
        val active = JamNotificationListener.active()
            ?: throw JamError(
                "listener de notificaciones no habilitado; Ajustes → Notificaciones → Jam",
                "NOTIFICATION_LISTENER_DISABLED"
            )
        return buildJsonObject {
            put("count", active.size)
            put("notifications", buildJsonArray {
                for (sbn in active.take(50)) {
                    val n = sbn.notification
                    val ex = n.extras
                    val title = ex.getCharSequence(Notification.EXTRA_TITLE)?.toString().orEmpty()
                    val text = (ex.getCharSequence(Notification.EXTRA_BIG_TEXT)
                        ?: ex.getCharSequence(Notification.EXTRA_TEXT))?.toString().orEmpty()
                    val hasRi = n.actions?.any { it.remoteInputs?.isNotEmpty() == true } == true
                    add(buildJsonObject {
                        put("key", sbn.key)
                        put("package", sbn.packageName)
                        put("title", NatPolicies.truncate(title, NatPolicies.NOTIF_TEXT_MAX))
                        put("text", NatPolicies.truncate(text, NatPolicies.NOTIF_TEXT_MAX))
                        put("has_remote_input", hasRi)
                        put("posted_at", sbn.postTime)
                    })
                }
            })
        }
    }

    fun replyNotification(ctx: Context, key: String, text: String, confirm: Boolean): JsonObject {
        if (key.isBlank() || text.isBlank()) throw JamError("key/text vacíos", "VALIDATION_ERROR")
        if (!confirm) {
            return planned(
                mapOf("key" to key, "text_len" to text.length.toString(),
                    "text_sha256" to sha256(text))
            )
        }
        val active = JamNotificationListener.active()
            ?: throw JamError("listener no habilitado", "NOTIFICATION_LISTENER_DISABLED")
        val sbn = active.find { it.key == key }
            ?: throw JamError("notificación ya no activa", "NOTIFICATION_GONE")
        val action = sbn.notification.actions?.firstOrNull {
            it.remoteInputs?.isNotEmpty() == true
        } ?: throw JamError("sin RemoteInput (no admite respuesta)", "NO_REMOTE_INPUT")
        return try {
            val ri = action.remoteInputs!!
            val results = Bundle()
            for (r in ri) results.putCharSequence(r.resultKey, text)
            val fill = Intent()
            RemoteInput.addResultsToIntent(ri, fill, results)
            action.actionIntent.send(ctx, 0, fill)
            buildJsonObject {
                put("replied", true)
                put("key", key)
                put("via", "remote_input")
            }
        } catch (t: PendingIntent.CanceledException) {
            throw JamError("respuesta cancelada por el sistema", "REPLY_FAILED")
        } catch (t: Exception) {
            throw JamError("respuesta falló: ${t.message?.take(150)}", "REPLY_FAILED")
        }
    }

    fun mediaState(ctx: Context): JsonObject {
        val sessions = activeSessions(ctx)
        return buildJsonObject {
            put("count", sessions.size)
            put("sessions", buildJsonArray {
                for (c in sessions.take(10)) {
                    val md = try {
                        c.metadata
                    } catch (t: Throwable) {
                        null
                    }
                    val st = try {
                        c.playbackState
                    } catch (t: Throwable) {
                        null
                    }
                    add(buildJsonObject {
                        put("package", c.packageName)
                        put("title", md?.getString(
                            android.media.MediaMetadata.METADATA_KEY_TITLE).orEmpty())
                        put("artist", md?.getString(
                            android.media.MediaMetadata.METADATA_KEY_ARTIST).orEmpty())
                        put("state", stateStr(st?.state ?: -1))
                    })
                }
            })
        }
    }

    private fun stateStr(s: Int): String = when (s) {
        android.media.session.PlaybackState.STATE_PLAYING -> "playing"
        android.media.session.PlaybackState.STATE_PAUSED -> "paused"
        android.media.session.PlaybackState.STATE_STOPPED -> "stopped"
        android.media.session.PlaybackState.STATE_BUFFERING -> "buffering"
        else -> "unknown"
    }

    private fun activeSessions(ctx: Context) =
        try {
            val msm = ctx.getSystemService(Context.MEDIA_SESSION_SERVICE) as MediaSessionManager
            msm.getActiveSessions(
                ComponentName(ctx, JamNotificationListener::class.java)
            ).orEmpty()
        } catch (t: SecurityException) {
            throw JamError(
                "sesiones no disponibles (habilita el listener)", "MEDIA_SESSIONS_UNAVAILABLE"
            )
        }

    fun mediaControl(ctx: Context, action: String, pkg: String, confirm: Boolean): JsonObject {
        val destructive = action == "stop"
        if (destructive && !confirm) {
            return planned(mapOf("action" to action, "package" to pkg))
        }
        val sessions = activeSessions(ctx)
        if (sessions.isEmpty()) {
            throw JamError("sin sesiones activas", "MEDIA_SESSIONS_UNAVAILABLE")
        }
        val c = if (pkg.isBlank()) sessions.first()
        else sessions.find { it.packageName == pkg }
            ?: throw JamError("sesión no encontrada para $pkg", "MEDIA_SESSION_GONE")
        return try {
            val t = c.transportControls
            when (action) {
                "play" -> t.play()
                "pause" -> t.pause()
                "next" -> t.skipToNext()
                "prev" -> t.skipToPrevious()
                "stop" -> t.stop()
                else -> throw JamError("action debe ser play|pause|next|prev|stop",
                    "VALIDATION_ERROR")
            }
            buildJsonObject {
                put("action", action)
                put("package", c.packageName)
                put("via", "transport_controls")
            }
        } catch (t: JamError) {
            throw t
        } catch (t: Exception) {
            throw JamError("control falló: ${t.message?.take(150)}", "MEDIA_CONTROL_FAILED")
        }
    }

    // ---- ubicación (P1 foreground, LocationManager puro; sin GMS) ----

    fun getLocation(ctx: Context, timeoutMs: Long, maxAgeS: Long): JsonObject {
        val fine = granted(ctx, Manifest.permission.ACCESS_FINE_LOCATION)
        val coarse = granted(ctx, Manifest.permission.ACCESS_COARSE_LOCATION)
        if (!fine && !coarse) {
            throw JamError(
                "sin permiso de ubicación; pide COARSE/FINE en la app Jam",
                "LOCATION_PERMISSION_DENIED"
            )
        }
        val lm = ctx.getSystemService(Context.LOCATION_SERVICE) as LocationManager
        val maxAge = maxAgeS.coerceIn(0, 3600)
        val now = System.currentTimeMillis()
        val last = listOf(LocationManager.GPS_PROVIDER, LocationManager.NETWORK_PROVIDER)
            .filter { lm.isProviderEnabled(it) }
            .mapNotNull {
                try {
                    lm.getLastKnownLocation(it)
                } catch (t: SecurityException) {
                    null
                }
            }.maxByOrNull { it.time }
        if (last != null && (now - last.time) / 1000 <= maxAge) {
            return locJson(last, (now - last.time) / 1000, "last_known")
        }
        val timeout = timeoutMs.coerceIn(0, 30_000)
        if (timeout <= 0) {
            throw JamError("sin fix fresco en caché; sube timeout_ms", "LOCATION_TIMEOUT")
        }
        val providers = mutableListOf<String>()
        if (fine && lm.isProviderEnabled(LocationManager.GPS_PROVIDER)) {
            providers.add(LocationManager.GPS_PROVIDER)
        }
        if (lm.isProviderEnabled(LocationManager.NETWORK_PROVIDER)) {
            providers.add(LocationManager.NETWORK_PROVIDER)
        }
        if (providers.isEmpty()) {
            throw JamError("proveedores apagados (GPS/red)", "LOCATION_UNAVAILABLE")
        }
        val latch = CountDownLatch(1)
        var fix: Location? = null
        val listener = LocationListener { loc ->
            if (fix == null) {
                fix = loc
                latch.countDown()
            }
        }
        return try {
            for (p in providers) {
                try {
                    lm.requestLocationUpdates(p, 0, 0f, listener, Looper.getMainLooper())
                } catch (t: SecurityException) {
                    // Sigue con el siguiente proveedor.
                }
            }
            latch.await(timeout, TimeUnit.MILLISECONDS)
            val f = fix ?: throw JamError(
                "sin fix en ${timeout}ms; no se inventa ubicación", "LOCATION_TIMEOUT"
            )
            locJson(f, 0, "fresh")
        } finally {
            try {
                lm.removeUpdates(listener)
            } catch (t: Throwable) {
                // Limpieza best-effort.
            }
        }
    }

    private fun locJson(l: Location, ageS: Long, via: String): JsonObject = buildJsonObject {
        put("lat", l.latitude)
        put("lon", l.longitude)
        put("accuracy_m", if (l.hasAccuracy()) l.accuracy else -1f)
        put("provider", l.provider.orEmpty())
        put("age_s", ageS)
        put("via", via)
    }

    // ---- portapapeles en foreground (P1-narrow; bg en Android 10+ = honesto) ----

    fun getClipboardFg(ctx: Context): JsonObject {
        val cm = ctx.getSystemService(Context.CLIPBOARD_SERVICE) as android.content.ClipboardManager
        val text = try {
            cm.primaryClip?.getItemAt(0)?.coerceToText(ctx)?.toString().orEmpty()
        } catch (t: SecurityException) {
            ""
        }
        if (text.isEmpty()) {
            throw JamError(
                "clipboard vacío o ilegible en segundo plano (Android 10+)",
                "CLIPBOARD_EMPTY"
            )
        }
        return buildJsonObject {
            put("len", text.length)
            put("sha256", sha256(text))
            put("via", "jam-foreground")
        }
    }

    // ---- intents P0 (apertura/pre-relleno; el envío va por carril Jev) ----

    /**
     * Abre `url` con `ACTION_VIEW`. Con `pkg` no vacío se fuerza el handler
     * de ese paquete (componente explícito) para evitar el ResolverActivity
     * cuando >1 app maneja el URI (medido: `youtu.be` con 2 clientes).
     * Paquete con forma inválida → `VALIDATION_ERROR`; no instalado →
     * `PACKAGE_NOT_FOUND`; instalado pero sin handler para el URI →
     * `INTENT_UNRESOLVED`. `pkg=""` = resolver por el sistema (comportamiento
     * previo, puede mostrar chooser). Fallback Shizuku `am start` si el
     * background-start está restringido (mismo camino que `open_app`).
     */
    fun openUrl(ctx: Context, url: String, pkg: String = ""): JsonObject {
        if (!NatPolicies.validUrl(url)) {
            throw JamError("url con forma inválida (esquema://…)", "VALIDATION_ERROR")
        }
        if (pkg.isNotBlank() && !NatPolicies.validPackage(pkg)) {
            throw JamError("package con forma inválida (a.b.c)", "VALIDATION_ERROR")
        }
        val force = pkg.isNotBlank()
        val intent = Intent(Intent.ACTION_VIEW, Uri.parse(url))
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        var comp: ComponentName? = null
        if (force) {
            intent.setPackage(pkg)
            try {
                @Suppress("DEPRECATION")
                ctx.packageManager.getPackageInfo(pkg, 0)
            } catch (t: PackageManager.NameNotFoundException) {
                throw JamError("paquete no instalado: $pkg", "PACKAGE_NOT_FOUND")
            }
            val resolved = ctx.packageManager.resolveActivity(
                intent, PackageManager.MATCH_DEFAULT_ONLY
            ) ?: throw JamError("el paquete $pkg no maneja $url", "INTENT_UNRESOLVED")
            comp = resolved.activityInfo?.let { ComponentName(it.packageName, it.name) }
            if (comp != null) intent.component = comp
        }
        return try {
            ctx.startActivity(intent)
            buildJsonObject {
                put("url", url)
                put("via", if (force) "startActivity-package" else "startActivity")
                if (force) put("package", pkg)
            }
        } catch (t: android.content.ActivityNotFoundException) {
            throw JamError("ninguna app resuelve $url", "INTENT_UNRESOLVED")
        } catch (t: Exception) {
            val args = mutableListOf("am", "start", "-a", Intent.ACTION_VIEW, "-d", url)
            if (comp != null) {
                args.add("-n")
                args.add("${comp.packageName}/${comp.className}")
            }
            shizukuAm(args)
            buildJsonObject {
                put("url", url)
                put("via", "shizuku-am")
                if (force) put("package", pkg)
            }
        }
    }

    fun sendIntent(
        ctx: Context, action: String, uri: String, pkg: String,
        mime: String, confirm: Boolean, extras: Map<String, String>
    ): JsonObject {
        val canon = NatPolicies.canonicalizeAction(action)
        if (canon.isBlank()) throw JamError("action vacía", "VALIDATION_ERROR")
        if (pkg.isNotBlank() && !NatPolicies.validPackage(pkg)) {
            throw JamError("package con forma inválida", "VALIDATION_ERROR")
        }
        if (NatPolicies.isCritical(canon, uri) && !confirm) {
            return planned(
                mapOf("action" to canon, "uri_scheme" to uri.substringBefore(":"),
                    "package" to pkg, "extras_n" to extras.size.toString())
            )
        }
        // Vía directa primero (Jam en foreground la permite); si el
        // background-start la bloquea, Shizuku `am start` (camino open_app).
        val intent = Intent(canon).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        if (uri.isNotBlank()) intent.data = Uri.parse(uri)
        if (pkg.isNotBlank()) intent.setPackage(pkg)
        if (mime.isNotBlank()) intent.type = mime
        for ((k, v) in extras) intent.putExtra(k, v)
        return try {
            ctx.startActivity(intent)
            buildJsonObject {
                put("action", canon)
                put("via", "startActivity")
            }
        } catch (t: Exception) {
            val args = mutableListOf("am", "start", "-a", canon)
            if (uri.isNotBlank()) {
                args.add("-d")
                args.add(uri)
            }
            if (mime.isNotBlank()) {
                args.add("-t")
                args.add(mime)
            }
            for ((k, v) in extras) {
                args.add("--es")
                args.add(k)
                args.add(v)
            }
            shizukuAm(args)
            buildJsonObject {
                put("action", canon)
                put("via", "shizuku-am")
            }
        }
    }

    private fun shizukuAm(args: List<String>) {
        val r = try {
            ShizukuBridge.exec(args)
        } catch (t: JamError) {
            throw JamError("Shizuku no disponible; arráncalo y reintenta", "SHIZUKU_UNAVAILABLE")
        }
        if (r.exitCode != 0) {
            throw JamError("am falló (exit ${r.exitCode}): ${r.stderr.take(200)}",
                "INTENT_FAILED")
        }
    }

    // ---- settings_put System (P1, WRITE_SETTINGS especial) ----

    fun settingsPut(ctx: Context, namespace: String, key: String, value: String): JsonObject {
        if (key.isBlank()) throw JamError("key vacía", "VALIDATION_ERROR")
        val ok = try {
            Settings.System.putString(ctx.contentResolver, key, value)
        } catch (t: SecurityException) {
            throw JamError(
                "WRITE_SETTINGS no concedido; Ajustes → Jam → permitir modificar ajustes",
                "WRITE_SETTINGS_DISABLED"
            )
        }
        if (!ok) throw JamError("put rechazado por el sistema", "SETTINGS_PUT_FAILED")
        return buildJsonObject {
            put("namespace", namespace)
            put("key", key)
            put("written", true)
        }
    }

    // ---- cámara headless restringida (P1, CAMERA + FGS + confirm siempre) ----

    fun takePhotoGate(confirm: Boolean): JsonObject? {
        if (!confirm) {
            return planned(
                mapOf("needs" to "fgs+notificacion+indicador",
                    "note" to "nunca silenciosa; FGS obligatorio")
            )
        }
        return null
    }

    fun checkCamera(ctx: Context) {
        if (!granted(ctx, Manifest.permission.CAMERA)) {
            throw JamError("CAMERA no concedido; pide el permiso en la app Jam",
                "CAMERA_DENIED")
        }
        if (!ctx.packageManager.hasSystemFeature(PackageManager.FEATURE_CAMERA_ANY)) {
            throw JamError("sin cámara en este equipo", "CAMERA_UNAVAILABLE")
        }
    }

    /** `{planned: true, preview}`: sin `confirm` no se ejecuta nada. */
    fun planned(preview: Map<String, String>): JsonObject = buildJsonObject {
        put("planned", true)
        put("preview", buildJsonObject {
            for ((k, v) in preview) put(k, v)
        })
        put("hint", "repite con confirm:true para ejecutar")
    }
}
