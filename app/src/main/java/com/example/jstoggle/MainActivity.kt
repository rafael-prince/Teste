package com.example.jstoggle

import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.service.quicksettings.TileService
import android.view.View
import android.widget.Button
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import android.content.ComponentName
import android.app.StatusBarManager
import android.graphics.drawable.Icon

class MainActivity : AppCompatActivity() {

    private lateinit var statusText: TextView
    private lateinit var jsStateText: TextView
    private lateinit var enableServiceBtn: Button
    private lateinit var addTileBtn: Button

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        statusText = findViewById(R.id.status_text)
        jsStateText = findViewById(R.id.js_state_text)
        enableServiceBtn = findViewById(R.id.btn_enable_service)
        addTileBtn = findViewById(R.id.btn_add_tile)

        enableServiceBtn.setOnClickListener {
            openAccessibilitySettings()
        }

        addTileBtn.setOnClickListener {
            requestAddTile()
        }
    }

    override fun onResume() {
        super.onResume()
        updateUI()
    }

    private fun updateUI() {
        val serviceEnabled = JsToggleAccessibilityService.isRunning()
        val jsEnabled = PrefsManager.isJsEnabled(this)

        statusText.text = if (serviceEnabled)
            "Accessibility Service: ENABLED"
        else
            "Accessibility Service: DISABLED"

        statusText.setTextColor(
            if (serviceEnabled) getColor(android.R.color.holo_green_dark)
            else getColor(android.R.color.holo_red_dark)
        )

        enableServiceBtn.text = if (serviceEnabled)
            "Service Enabled — Open Settings"
        else
            "Enable Accessibility Service"

        jsStateText.text = if (jsEnabled)
            "JavaScript is assumed ON"
        else
            "JavaScript is assumed OFF"
    }

    private fun openAccessibilitySettings() {
        val intent = Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS).apply {
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        startActivity(intent)
    }

    private fun requestAddTile() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            val statusBarManager = getSystemService(StatusBarManager::class.java)
            statusBarManager.requestAddTileService(
                ComponentName(this, JsToggleTileService::class.java),
                getString(R.string.tile_label),
                Icon.createWithResource(this, R.drawable.ic_js),
                { it.run() }
            ) { resultCode ->
                // Result handling is optional; the system shows its own UI
            }
        } else {
            // On older Android, user must manually add the tile
            android.widget.Toast.makeText(
                this,
                "Swipe down the notification shade, tap Edit, and add the \"JS Toggle\" tile",
                android.widget.Toast.LENGTH_LONG
            ).show()
        }
    }
}
