package com.almatchlife.core.system

import android.Manifest
import android.annotation.SuppressLint
import android.app.Activity
import android.app.NotificationManager
import android.content.Context
import android.content.Intent
import android.content.SharedPreferences
import android.content.pm.PackageManager
import android.os.Build
import android.provider.Settings
import androidx.core.net.toUri

enum class NotificationPermissionState { GRANTED, EXPLANATION_REQUIRED, REQUESTABLE, SETTINGS_REQUIRED }

class NotificationPermissionController(
    context: Context,
    private val preferences: SharedPreferences,
) {
    private val applicationContext = context.applicationContext
    private val notificationManager = applicationContext.getSystemService(NotificationManager::class.java)

    fun state(activity: Activity): NotificationPermissionState {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) {
            return if (notificationManager.areNotificationsEnabled()) NotificationPermissionState.GRANTED
            else NotificationPermissionState.SETTINGS_REQUIRED
        }
        if (activity.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED) {
            return if (notificationManager.areNotificationsEnabled()) NotificationPermissionState.GRANTED
            else NotificationPermissionState.SETTINGS_REQUIRED
        }
        if (activity.shouldShowRequestPermissionRationale(Manifest.permission.POST_NOTIFICATIONS)) {
            return NotificationPermissionState.EXPLANATION_REQUIRED
        }
        return if (preferences.getBoolean(REQUESTED_KEY, false)) {
            NotificationPermissionState.SETTINGS_REQUIRED
        } else NotificationPermissionState.REQUESTABLE
    }

    @SuppressLint("UseKtx") // The synchronous result is required before requesting permission.
    fun markRequestStarted() {
        check(preferences.edit().putBoolean(REQUESTED_KEY, true).commit()) {
            "could not persist notification permission state"
        }
    }

    fun notificationSettingsIntent(): Intent = Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS)
        .putExtra(Settings.EXTRA_APP_PACKAGE, applicationContext.packageName)

    fun canUseFullScreenIntent(): Boolean =
        Build.VERSION.SDK_INT < Build.VERSION_CODES.UPSIDE_DOWN_CAKE || notificationManager.canUseFullScreenIntent()

    @SuppressLint("InlinedApi") // Guarded by the explicit Android 14 runtime check below.
    fun fullScreenSettingsIntent(): Intent {
        check(Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            "full-screen intent settings require Android 14"
        }
        return Intent(Settings.ACTION_MANAGE_APP_USE_FULL_SCREEN_INTENT)
            .setData("package:${applicationContext.packageName}".toUri())
    }

    private companion object { const val REQUESTED_KEY = "post_notifications_requested_v1" }
}
