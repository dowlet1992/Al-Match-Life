package com.almatchlife.core

import java.util.UUID

interface CallSignaling {
    suspend fun send(type: String, eventId: String, payload: VoipCallPayload, reason: String? = null)
}
interface CallAudio { suspend fun activate(callType: NativeCallType); suspend fun deactivate() }
interface PersonMedia { suspend fun start(payload: VoipCallPayload); suspend fun stop() }
interface OptionalCaptions { suspend fun start(); suspend fun stop() }

class NativeCallLifecycle(
    private val signaling: CallSignaling,
    private val audio: CallAudio,
    private val media: PersonMedia,
    private val captions: OptionalCaptions,
    private val optionalFeatureError: suspend (Exception) -> Unit,
) {
    private var mediaActive = false

    suspend fun accept(payload: VoipCallPayload) {
        if (mediaActive) return
        signaling.send("accepted", eventId(), payload)
        try {
            audio.activate(payload.callType)
            media.start(payload)
            mediaActive = true
        } catch (failure: Exception) {
            rollbackAfterAccept(payload)
            throw failure
        }
        try { captions.start() } catch (failure: Exception) { optionalFeatureError(failure) }
    }

    suspend fun decline(payload: VoipCallPayload) = signaling.send("declined", eventId(), payload)
    suspend fun end(payload: VoipCallPayload) = signaling.send("ended", eventId(), payload)
    suspend fun connectionLost(payload: VoipCallPayload) =
        signaling.send("ended", eventId(), payload, reason = "connection_lost")

    suspend fun stop() {
        try { captions.stop() } finally {
            try { media.stop() } finally { audio.deactivate(); mediaActive = false }
        }
    }

    private suspend fun rollbackAfterAccept(payload: VoipCallPayload) {
        try { stop() } finally { runCatching { signaling.send("ended", eventId(), payload) } }
    }

    private fun eventId() = "android_${UUID.randomUUID().toString().lowercase()}"
}
