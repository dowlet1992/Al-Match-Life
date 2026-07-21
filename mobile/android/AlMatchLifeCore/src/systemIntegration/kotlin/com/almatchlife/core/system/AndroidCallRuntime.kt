package com.almatchlife.core.system

import android.content.Context
import android.content.Intent
import com.almatchlife.core.NativeCallType
import com.almatchlife.core.VoipCallPayload
import java.util.concurrent.CompletableFuture
import java.util.concurrent.atomic.AtomicReference

interface AndroidCallRuntime {
    fun currentEmail(): String?
    fun receivePush(payload: VoipCallPayload)
    fun registerFcmToken(token: String)
    fun decline(callId: String, callType: NativeCallType, eventId: String): CompletableFuture<Void>
    fun startAcceptedCall(callId: String, callType: NativeCallType, eventId: String): CompletableFuture<Void>
    fun stopCall(callId: String): CompletableFuture<Void>
}

object AndroidCallRuntimeRegistry {
    private val installed = AtomicReference<AndroidCallRuntime?>()

    fun install(runtime: AndroidCallRuntime) {
        check(installed.compareAndSet(null, runtime)) { "Android call runtime already installed" }
    }

    fun require(): AndroidCallRuntime = installed.get()
        ?: throw IllegalStateException("Android call runtime must be installed by Application")

    fun openAnswerActivity(context: Context, callId: String, callType: NativeCallType, eventId: String) {
        context.startActivity(
            Intent(context, IncomingCallActivity::class.java)
                .putExtra(EXTRA_CALL_ID, callId)
                .putExtra(EXTRA_CALL_TYPE, callType.wireValue)
                .putExtra(EXTRA_CALL_EVENT_ID, eventId)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP),
        )
    }

    const val EXTRA_CALL_ID = "call_id"
    const val EXTRA_CALL_TYPE = "call_type"
    const val EXTRA_CALL_EVENT_ID = "call_event_id"
}

object FcmTokenSinkRegistry {
    private val installed = AtomicReference<((String) -> Unit)?>(null)

    fun install(sink: (String) -> Unit) {
        check(installed.compareAndSet(null, sink)) { "FCM token sink already installed" }
    }

    fun deliver(token: String) {
        installed.get()?.invoke(token)
    }
}
