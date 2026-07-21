package com.almatchlife.core.system

import android.Manifest
import android.app.Activity
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.view.WindowManager
import com.almatchlife.core.NativeCallType

class IncomingCallActivity : Activity() {
    private var callId: String = ""
    private var eventId: String = ""
    private var callType: NativeCallType? = null

    override fun onCreate(state: Bundle?) {
        super.onCreate(state)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O_MR1) {
            setShowWhenLocked(true)
            setTurnScreenOn(true)
        } else {
            @Suppress("DEPRECATION")
            window.addFlags(
                WindowManager.LayoutParams.FLAG_SHOW_WHEN_LOCKED or
                    WindowManager.LayoutParams.FLAG_TURN_SCREEN_ON,
            )
        }
        readAndContinue(intent)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        readAndContinue(intent)
    }

    private fun readAndContinue(intent: Intent) {
        callId = intent.getStringExtra(AndroidCallRuntimeRegistry.EXTRA_CALL_ID).orEmpty()
        eventId = intent.getStringExtra(AndroidCallRuntimeRegistry.EXTRA_CALL_EVENT_ID).orEmpty()
        callType = NativeCallType.entries.firstOrNull {
            it.wireValue == intent.getStringExtra(AndroidCallRuntimeRegistry.EXTRA_CALL_TYPE)
        }
        if (!VALID_ID.matches(callId) || !VALID_EVENT_ID.matches(eventId) || callType == null) {
            finishAndRemoveTask()
            return
        }
        val permissions = buildList {
            if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
                add(Manifest.permission.RECORD_AUDIO)
            }
            if (callType == NativeCallType.VIDEO &&
                checkSelfPermission(Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) {
                add(Manifest.permission.CAMERA)
            }
        }
        if (permissions.isEmpty()) startCall() else requestPermissions(permissions.toTypedArray(), REQUEST_MEDIA)
    }

    override fun onRequestPermissionsResult(code: Int, permissions: Array<out String>, results: IntArray) {
        super.onRequestPermissionsResult(code, permissions, results)
        if (code != REQUEST_MEDIA) return
        if (results.isNotEmpty() && results.all { it == PackageManager.PERMISSION_GRANTED }) startCall()
        else {
            callType?.let { type ->
                runCatching { AndroidCallRuntimeRegistry.require().decline(callId, type, eventId) }
            }
            finishAndRemoveTask()
        }
    }

    private fun startCall() {
        val type = callType ?: return
        val service = Intent(this, OngoingCallService::class.java)
            .putExtra(AndroidCallRuntimeRegistry.EXTRA_CALL_ID, callId)
            .putExtra(AndroidCallRuntimeRegistry.EXTRA_CALL_TYPE, type.wireValue)
            .putExtra(AndroidCallRuntimeRegistry.EXTRA_CALL_EVENT_ID, eventId)
        try {
            startForegroundService(service)
        } catch (_: RuntimeException) {
            runCatching { AndroidCallRuntimeRegistry.require().decline(callId, type, eventId) }
        }
        finish()
    }

    private companion object {
        const val REQUEST_MEDIA = 4102
        val VALID_ID = Regex("^[A-Za-z0-9_-]{8,128}$")
        val VALID_EVENT_ID = Regex("^[A-Za-z0-9_-]{8,80}$")
    }
}
