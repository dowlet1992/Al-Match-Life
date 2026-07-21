package com.almatchlife.core.system

import android.Manifest
import android.annotation.SuppressLint
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Intent
import android.content.pm.PackageManager
import android.content.pm.ServiceInfo
import android.os.IBinder
import androidx.core.app.ServiceCompat
import com.almatchlife.core.NativeCallType

class OngoingCallService : Service() {
    private var activeCallId: String? = null

    override fun onCreate() {
        super.onCreate()
        getSystemService(NotificationManager::class.java).createNotificationChannel(
            NotificationChannel(CHANNEL_ID, "Ongoing calls", NotificationManager.IMPORTANCE_LOW),
        )
    }

    @SuppressLint("InlinedApi") // ServiceCompat handles these bit values on pre-30 devices.
    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val callId = intent?.getStringExtra(AndroidCallRuntimeRegistry.EXTRA_CALL_ID).orEmpty()
        val eventId = intent?.getStringExtra(AndroidCallRuntimeRegistry.EXTRA_CALL_EVENT_ID).orEmpty()
        val callType = NativeCallType.entries.firstOrNull {
            it.wireValue == intent?.getStringExtra(AndroidCallRuntimeRegistry.EXTRA_CALL_TYPE)
        }
        if (!VALID_ID.matches(callId) || !VALID_EVENT_ID.matches(eventId) ||
            callType == null || !hasRuntimePermissions(callType)
        ) {
            stopSelf(startId)
            return START_NOT_STICKY
        }
        if (activeCallId == callId) return START_NOT_STICKY
        if (activeCallId != null) { stopSelf(startId); return START_NOT_STICKY }
        val serviceTypes = ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE or
            if (callType == NativeCallType.VIDEO) ServiceInfo.FOREGROUND_SERVICE_TYPE_CAMERA else 0
        ServiceCompat.startForeground(this, NOTIFICATION_ID, notification(), serviceTypes)
        activeCallId = callId
        val runtime = runCatching { AndroidCallRuntimeRegistry.require() }.getOrElse {
            stopSelf(startId)
            return START_NOT_STICKY
        }
        runtime.startAcceptedCall(callId, callType, eventId).whenComplete { _, failure ->
            if (failure != null) stopSelf()
        }
        return START_NOT_STICKY
    }

    override fun onDestroy() {
        val callId = activeCallId
        activeCallId = null
        if (callId != null) runCatching { AndroidCallRuntimeRegistry.require().stopCall(callId) }
        ServiceCompat.stopForeground(this, ServiceCompat.STOP_FOREGROUND_REMOVE)
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun hasRuntimePermissions(callType: NativeCallType): Boolean =
        checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED &&
            (callType != NativeCallType.VIDEO ||
                checkSelfPermission(Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED)

    private fun notification(): Notification = Notification.Builder(this, CHANNEL_ID)
        .setSmallIcon(applicationInfo.icon)
        .setCategory(Notification.CATEGORY_CALL)
        .setOngoing(true)
        .setContentTitle("Al Match Life call")
        .setContentText("Call in progress")
        .build()

    private companion object {
        const val CHANNEL_ID = "ongoing_calls_v1"
        const val NOTIFICATION_ID = 41020
        val VALID_ID = Regex("^[A-Za-z0-9_-]{8,128}$")
        val VALID_EVENT_ID = Regex("^[A-Za-z0-9_-]{8,80}$")
    }
}
