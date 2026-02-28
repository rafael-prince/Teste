package com.example.jstoggle

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.graphics.drawable.Icon
import android.os.Build
import android.service.quicksettings.Tile
import android.service.quicksettings.TileService
import android.widget.Toast

/**
 * Quick Settings tile that triggers the JavaScript toggle in Chrome.
 *
 * When the user taps this tile:
 * 1. If the accessibility service is not running, open the setup activity
 * 2. Otherwise, set a pending-toggle flag and send a broadcast to the
 *    accessibility service, which handles the actual Chrome UI navigation
 */
class JsToggleTileService : TileService() {

    companion object {
        const val ACTION_STATE_CHANGED = "com.example.jstoggle.ACTION_STATE_CHANGED"
    }

    private val stateReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            if (intent.action == ACTION_STATE_CHANGED) {
                updateTileState()
            }
        }
    }

    override fun onStartListening() {
        super.onStartListening()
        updateTileState()
        registerReceiver(
            stateReceiver,
            IntentFilter(ACTION_STATE_CHANGED),
            RECEIVER_NOT_EXPORTED
        )
    }

    override fun onStopListening() {
        try {
            unregisterReceiver(stateReceiver)
        } catch (_: Exception) {
            // Already unregistered
        }
        super.onStopListening()
    }

    override fun onClick() {
        super.onClick()

        if (!JsToggleAccessibilityService.isRunning()) {
            // Accessibility service not enabled — open setup screen
            Toast.makeText(this, "Enable the accessibility service first", Toast.LENGTH_SHORT).show()
            val intent = Intent(this, MainActivity::class.java).apply {
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            }
            startActivityAndCollapse(intent)
            return
        }

        // Set pending flag and trigger the accessibility service
        PrefsManager.setPendingToggle(this, true)

        val triggerIntent = Intent(JsToggleAccessibilityService.ACTION_TRIGGER_TOGGLE).apply {
            setPackage(packageName)
        }
        sendBroadcast(triggerIntent)

        // Collapse the Quick Settings panel
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            // On Android 12+, the panel collapses automatically after startActivity
        }
    }

    private fun updateTileState() {
        val tile = qsTile ?: return
        val jsEnabled = PrefsManager.isJsEnabled(this)

        tile.state = if (jsEnabled) Tile.STATE_ACTIVE else Tile.STATE_INACTIVE
        tile.label = if (jsEnabled) "JS: ON" else "JS: OFF"
        tile.icon = Icon.createWithResource(this, R.drawable.ic_js)

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            tile.subtitle = if (jsEnabled) "JavaScript enabled" else "JavaScript disabled"
        }

        tile.updateTile()
    }
}
