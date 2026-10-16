package dev.jev.jam.service

import android.graphics.drawable.Icon
import android.service.quicksettings.Tile
import android.service.quicksettings.TileService
import dev.jev.jam.R
import dev.jev.jam.util.JevLog

/**
 * Fase 6a: Quick Settings Tile del Kill Switch (AGENTS.md §3.8).
 * Refleja `JevForegroundService.serverOn` y, al tocar, dispara la
 * revocación de token + parada del servidor. Sin UI propia.
 */
class JamKillSwitchTile : TileService() {

    override fun onStartListening() {
        super.onStartListening()
        refresh()
    }

    override fun onClick() {
        super.onClick()
        if (JevForegroundService.serverOn) {
            try {
                JevForegroundService.triggerKillSwitch(applicationContext)
            } catch (t: Throwable) {
                JevLog.e(TAG, "kill switch del tile falló", t)
            }
        }
        refresh()
    }

    private fun refresh() {
        val tile = qsTile ?: return
        val on = JevForegroundService.serverOn
        tile.state = if (on) Tile.STATE_ACTIVE else Tile.STATE_INACTIVE
        tile.label = if (on) "Jam ON" else "Jam OFF"
        tile.subtitle = if (on) "toca para apagar" else "servidor detenido"
        tile.icon = Icon.createWithResource(this, R.drawable.ic_jam_kill)
        tile.updateTile()
    }

    private companion object {
        const val TAG = "JamWs"
    }
}
