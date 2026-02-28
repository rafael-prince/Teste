package com.example.jstoggle

import android.content.Context
import android.content.SharedPreferences

object PrefsManager {

    private const val PREF_NAME = "js_toggle_prefs"
    private const val KEY_JS_ENABLED = "js_enabled"
    private const val KEY_PENDING_TOGGLE = "pending_toggle"

    private fun prefs(context: Context): SharedPreferences =
        context.getSharedPreferences(PREF_NAME, Context.MODE_PRIVATE)

    /** Current assumed JS state. Defaults to true (JS enabled) on first use. */
    fun isJsEnabled(context: Context): Boolean =
        prefs(context).getBoolean(KEY_JS_ENABLED, true)

    fun setJsEnabled(context: Context, enabled: Boolean) {
        prefs(context).edit().putBoolean(KEY_JS_ENABLED, enabled).apply()
    }

    /** Flag checked by the AccessibilityService to know a toggle was requested. */
    fun isPendingToggle(context: Context): Boolean =
        prefs(context).getBoolean(KEY_PENDING_TOGGLE, false)

    fun setPendingToggle(context: Context, pending: Boolean) {
        prefs(context).edit().putBoolean(KEY_PENDING_TOGGLE, pending).apply()
    }
}
