package dev.jev.jam.service

import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification

/**
 * Puerta P1 para `list_notifications` / `reply_notification` / `media_*`.
 * El grant lo da el usuario en Ajustes (la app lo guía, nunca lo fuerza);
 * sin él el dispatcher responde `NOTIFICATION_LISTENER_DISABLED` honesto.
 */
class JamNotificationListener : NotificationListenerService() {

    override fun onListenerConnected() {
        instance = this
    }

    override fun onListenerDisconnected() {
        if (instance === this) instance = null
    }

    companion object {
        @Volatile
        private var instance: JamNotificationListener? = null

        fun isConnected(): Boolean = instance != null

        /** Activas o null si el listener no está habilitado. */
        fun active(): List<StatusBarNotification>? {
            val svc = instance ?: return null
            return try {
                svc.activeNotifications?.toList().orEmpty()
            } catch (t: SecurityException) {
                null
            }
        }
    }
}
