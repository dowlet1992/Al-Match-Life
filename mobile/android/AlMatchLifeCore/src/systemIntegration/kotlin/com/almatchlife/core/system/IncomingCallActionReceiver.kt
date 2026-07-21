package com.almatchlife.core.system

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import com.almatchlife.core.NativeCallType
import com.almatchlife.core.failedFutureCompat

class IncomingCallActionReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.component?.className != javaClass.name || intent.`package` != context.packageName) return
        val callId = intent.getStringExtra(AndroidCallRuntimeRegistry.EXTRA_CALL_ID).orEmpty()
        if (!VALID_ID.matches(callId)) return
        val eventId = intent.getStringExtra(AndroidCallRuntimeRegistry.EXTRA_CALL_EVENT_ID).orEmpty()
        if (!VALID_EVENT_ID.matches(eventId)) return
        val callType = NativeCallType.entries.firstOrNull {
            it.wireValue == intent.getStringExtra(AndroidCallRuntimeRegistry.EXTRA_CALL_TYPE)
        } ?: return
        when (intent.action) {
            ACTION_ANSWER -> AndroidCallRuntimeRegistry.openAnswerActivity(context, callId, callType, eventId)
            ACTION_DECLINE -> {
                val pending = goAsync()
                runCatching { AndroidCallRuntimeRegistry.require().decline(callId, callType, eventId) }
                    .getOrElse { failedFutureCompat(it) }
                    .whenComplete { _, _ -> pending.finish() }
            }
        }
    }

    companion object {
        const val ACTION_ANSWER = "com.almatchlife.call.ANSWER"
        const val ACTION_DECLINE = "com.almatchlife.call.DECLINE"
        private val VALID_ID = Regex("^[A-Za-z0-9_-]{8,128}$")
        private val VALID_EVENT_ID = Regex("^[A-Za-z0-9_-]{8,80}$")
    }
}
