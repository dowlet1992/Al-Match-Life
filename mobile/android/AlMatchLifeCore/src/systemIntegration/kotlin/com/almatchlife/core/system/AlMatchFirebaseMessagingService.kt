package com.almatchlife.core.system

import com.almatchlife.core.VoipPayloadValidator
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage

class AlMatchFirebaseMessagingService : FirebaseMessagingService() {
    override fun onMessageReceived(message: RemoteMessage) {
        val runtime = runCatching { AndroidCallRuntimeRegistry.require() }.getOrNull() ?: return
        val currentEmail = runtime.currentEmail()?.trim()?.lowercase()?.takeIf { it.isNotEmpty() } ?: return
        val payload = runCatching {
            VoipPayloadValidator.validate(message.data, currentEmail, System.currentTimeMillis() / 1000)
        }.getOrNull() ?: return
        runtime.receivePush(payload)
    }

    @Suppress("OVERRIDE_DEPRECATION")
    override fun onNewToken(token: String) {
        if (token.isBlank() || token.length > 4096 || '\r' in token || '\n' in token) return
        FcmTokenSinkRegistry.deliver(token)
        runCatching { AndroidCallRuntimeRegistry.require() }.getOrNull()?.registerFcmToken(token)
    }
}
