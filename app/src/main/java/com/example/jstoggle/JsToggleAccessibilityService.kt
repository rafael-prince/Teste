package com.example.jstoggle

import android.accessibilityservice.AccessibilityService
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.net.Uri
import android.os.Handler
import android.os.Looper
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import android.widget.Toast

/**
 * Accessibility service that navigates Chrome's settings UI to toggle JavaScript.
 *
 * Flow:
 * 1. TileService sets PENDING_TOGGLE flag and sends ACTION_TRIGGER_TOGGLE broadcast
 * 2. This service receives the broadcast and launches Chrome's JS settings page
 * 3. onAccessibilityEvent detects Chrome's settings UI appearing
 * 4. Service finds the toggle switch and clicks it
 * 5. Service presses Back to return the user and updates state
 */
class JsToggleAccessibilityService : AccessibilityService() {

    companion object {
        const val ACTION_TRIGGER_TOGGLE = "com.example.jstoggle.ACTION_TRIGGER_TOGGLE"
        private const val TOGGLE_TIMEOUT_MS = 6000L

        /** Known Chrome package names. */
        val CHROME_PACKAGES = listOf(
            "com.android.chrome",
            "com.chrome.beta",
            "com.chrome.dev",
            "com.chrome.canary"
        )

        private var instance: JsToggleAccessibilityService? = null

        fun isRunning(): Boolean = instance != null
    }

    private val handler = Handler(Looper.getMainLooper())
    private var waitingForToggle = false
    private var toggleTimeoutRunnable: Runnable? = null
    private var activePackage: String? = null

    private val triggerReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            if (intent.action == ACTION_TRIGGER_TOGGLE) {
                startToggleFlow()
            }
        }
    }

    override fun onCreate() {
        super.onCreate()
        instance = this
        registerReceiver(
            triggerReceiver,
            IntentFilter(ACTION_TRIGGER_TOGGLE),
            RECEIVER_NOT_EXPORTED
        )
    }

    override fun onDestroy() {
        instance = null
        unregisterReceiver(triggerReceiver)
        cancelTimeout()
        super.onDestroy()
    }

    override fun onServiceConnected() {
        super.onServiceConnected()
        instance = this
    }

    override fun onInterrupt() {
        cancelTimeout()
        waitingForToggle = false
    }

    /**
     * Start the toggle flow: launch Chrome to its JavaScript settings page.
     */
    private fun startToggleFlow() {
        val pkg = findInstalledChrome()
        if (pkg == null) {
            Toast.makeText(this, "Chrome is not installed", Toast.LENGTH_SHORT).show()
            PrefsManager.setPendingToggle(this, false)
            return
        }
        activePackage = pkg
        waitingForToggle = true

        // Launch Chrome directly to the JavaScript settings page
        try {
            val intent = Intent(Intent.ACTION_VIEW).apply {
                setPackage(pkg)
                data = Uri.parse("chrome://settings/content/javascript")
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
            }
            startActivity(intent)
        } catch (e: Exception) {
            // Fallback: open Chrome's settings activity directly
            try {
                val intent = Intent().apply {
                    setClassName(pkg, "org.chromium.chrome.browser.settings.SettingsActivity")
                    addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                }
                startActivity(intent)
            } catch (e2: Exception) {
                Toast.makeText(this, "Cannot open Chrome settings", Toast.LENGTH_SHORT).show()
                waitingForToggle = false
                PrefsManager.setPendingToggle(this, false)
                return
            }
        }

        // Set a timeout so we don't stay in the waiting state forever
        toggleTimeoutRunnable = Runnable {
            if (waitingForToggle) {
                waitingForToggle = false
                PrefsManager.setPendingToggle(this, false)
                Toast.makeText(this, "JS toggle timed out — try again", Toast.LENGTH_SHORT).show()
            }
        }
        handler.postDelayed(toggleTimeoutRunnable!!, TOGGLE_TIMEOUT_MS)
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        if (!waitingForToggle || event == null) return

        val eventPkg = event.packageName?.toString() ?: return
        if (eventPkg !in CHROME_PACKAGES) return

        when (event.eventType) {
            AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED,
            AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED -> {
                tryToggleJavaScript()
            }
        }
    }

    /**
     * Search the current window's node tree for the JavaScript toggle and click it.
     */
    private fun tryToggleJavaScript() {
        val root = rootInActiveWindow ?: return

        // Strategy 1: We're on the JavaScript settings page.
        // Look for a Switch/Toggle widget that's a sibling or near "JavaScript" text.
        if (findAndClickJsToggle(root)) {
            onToggleSuccess()
            root.recycle()
            return
        }

        // Strategy 2: We might be on the Site Settings page — look for "JavaScript" list item
        val jsNode = findNodeByText(root, "JavaScript")
        if (jsNode != null) {
            // Check if this node is clickable (it's a list item we need to tap into)
            val clickable = findClickableParent(jsNode)
            if (clickable != null) {
                // Check if there's a switch right here (we might already be on the JS page)
                val switchNearby = findSwitchInSameParent(jsNode)
                if (switchNearby != null) {
                    switchNearby.performAction(AccessibilityNodeInfo.ACTION_CLICK)
                    onToggleSuccess()
                    root.recycle()
                    return
                }
                // Otherwise click to navigate into JavaScript settings
                clickable.performAction(AccessibilityNodeInfo.ACTION_CLICK)
            }
            jsNode.recycle()
        }

        // Strategy 3: We might be on the main Settings page — look for "Site settings"
        val siteSettingsNode = findNodeByText(root, "Site settings")
        if (siteSettingsNode != null) {
            val clickable = findClickableParent(siteSettingsNode)
            clickable?.performAction(AccessibilityNodeInfo.ACTION_CLICK)
            siteSettingsNode.recycle()
        }

        root.recycle()
    }

    /**
     * Find a Switch/Toggle widget associated with JavaScript and click it.
     * Returns true if a toggle was found and clicked.
     */
    private fun findAndClickJsToggle(root: AccessibilityNodeInfo): Boolean {
        // Look for switch-like widgets
        val switches = mutableListOf<AccessibilityNodeInfo>()
        findNodesByClassName(root, switches, setOf(
            "android.widget.Switch",
            "android.widget.ToggleButton",
            "androidx.appcompat.widget.SwitchCompat",
            "com.google.android.material.switchmaterial.SwitchMaterial",
            "com.google.android.material.materialswitch.MaterialSwitch"
        ))

        for (switchNode in switches) {
            // Check if this switch is on a page related to JavaScript
            // by looking at the page title or nearby text nodes
            val parent = switchNode.parent
            if (parent != null) {
                if (containsText(root, "JavaScript") || containsText(root, "javascript")) {
                    switchNode.performAction(AccessibilityNodeInfo.ACTION_CLICK)
                    return true
                }
            }
        }

        // Also try: find any node with text "JavaScript" that has a checkable/clickable widget
        val allNodes = mutableListOf<AccessibilityNodeInfo>()
        collectAllNodes(root, allNodes)
        for (node in allNodes) {
            if (node.isCheckable) {
                // Is there "JavaScript" text visible on the same screen?
                if (containsText(root, "JavaScript")) {
                    node.performAction(AccessibilityNodeInfo.ACTION_CLICK)
                    return true
                }
            }
        }

        return false
    }

    private fun onToggleSuccess() {
        waitingForToggle = false
        cancelTimeout()

        // Flip the stored state
        val wasEnabled = PrefsManager.isJsEnabled(this)
        PrefsManager.setJsEnabled(this, !wasEnabled)
        PrefsManager.setPendingToggle(this, false)

        // Notify tile to refresh
        sendBroadcast(Intent(JsToggleTileService.ACTION_STATE_CHANGED).apply {
            setPackage(packageName)
        })

        val newState = if (!wasEnabled) "enabled" else "disabled"
        handler.post {
            Toast.makeText(this, "JavaScript $newState", Toast.LENGTH_SHORT).show()
        }

        // Go back to the previous app after a short delay
        handler.postDelayed({
            performGlobalAction(GLOBAL_ACTION_BACK)
            handler.postDelayed({
                performGlobalAction(GLOBAL_ACTION_BACK)
            }, 300)
        }, 500)
    }

    // --- Node tree traversal helpers ---

    private fun findNodeByText(root: AccessibilityNodeInfo, text: String): AccessibilityNodeInfo? {
        val nodes = root.findAccessibilityNodeInfosByText(text)
        return nodes?.firstOrNull()
    }

    private fun containsText(root: AccessibilityNodeInfo, text: String): Boolean {
        val nodes = root.findAccessibilityNodeInfosByText(text)
        val found = nodes != null && nodes.isNotEmpty()
        nodes?.forEach { it.recycle() }
        return found
    }

    private fun findClickableParent(node: AccessibilityNodeInfo): AccessibilityNodeInfo? {
        var current: AccessibilityNodeInfo? = node
        while (current != null) {
            if (current.isClickable) return current
            current = current.parent
        }
        return null
    }

    private fun findSwitchInSameParent(node: AccessibilityNodeInfo): AccessibilityNodeInfo? {
        val parent = node.parent ?: return null
        for (i in 0 until parent.childCount) {
            val child = parent.getChild(i) ?: continue
            val className = child.className?.toString() ?: ""
            if ("Switch" in className || "Toggle" in className || child.isCheckable) {
                return child
            }
        }
        return null
    }

    private fun findNodesByClassName(
        node: AccessibilityNodeInfo,
        result: MutableList<AccessibilityNodeInfo>,
        classNames: Set<String>
    ) {
        val className = node.className?.toString() ?: ""
        if (className in classNames) {
            result.add(node)
        }
        for (i in 0 until node.childCount) {
            val child = node.getChild(i) ?: continue
            findNodesByClassName(child, result, classNames)
        }
    }

    private fun collectAllNodes(
        node: AccessibilityNodeInfo,
        result: MutableList<AccessibilityNodeInfo>
    ) {
        result.add(node)
        for (i in 0 until node.childCount) {
            val child = node.getChild(i) ?: continue
            collectAllNodes(child, result)
        }
    }

    private fun findInstalledChrome(): String? {
        val pm = packageManager
        for (pkg in CHROME_PACKAGES) {
            try {
                pm.getPackageInfo(pkg, 0)
                return pkg
            } catch (_: Exception) {
                // Not installed, try next
            }
        }
        return null
    }

    private fun cancelTimeout() {
        toggleTimeoutRunnable?.let { handler.removeCallbacks(it) }
        toggleTimeoutRunnable = null
    }
}
