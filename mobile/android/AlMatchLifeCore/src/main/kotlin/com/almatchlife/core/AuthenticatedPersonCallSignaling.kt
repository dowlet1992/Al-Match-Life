package com.almatchlife.core

import java.util.concurrent.CompletableFuture
import java.util.concurrent.CompletionException
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException
import kotlin.coroutines.suspendCoroutine

class AuthenticatedPersonCallSignaling(
    private val client: AuthenticatedApiClient,
    private val codec: MobileWireCodec,
    private val nowEpochSeconds: () -> Double,
) : PersonCallSignaling {
    override suspend fun ice(payload: VoipCallPayload): IceConfiguration {
        val response = get(payload, "ice-servers")
        val configuration = codec.decodeIceConfiguration(response.body)
        if (configuration.servers.isEmpty() || configuration.expiresAt <= nowEpochSeconds() + 5.0) {
            throw PersonTransportException("invalid or expiring ICE configuration")
        }
        configuration.servers.forEach { server ->
            if (server.urls.isEmpty() || server.urls.any { !validIceUrl(it) }) {
                throw PersonTransportException("invalid ICE server")
            }
        }
        return configuration
    }

    override suspend fun poll(payload: VoipCallPayload, after: Double): SignalPoll {
        if (!after.isFinite() || after < 0.0) throw PersonTransportException("invalid signaling watermark")
        val result = codec.decodeSignalPoll(get(payload, "signals", mapOf("after" to after.toString())).body)
        if (!result.serverTime.isFinite() || result.serverTime < 0.0) {
            throw PersonTransportException("invalid server time")
        }
        if (result.status !in setOf("active", "ringing", "accepted", "declined", "ended", "missed")) {
            throw PersonTransportException("invalid call status")
        }
        return result
    }

    override suspend fun sendDescription(
        payload: VoipCallPayload,
        type: String,
        sdp: String,
        eventId: String,
    ) {
        if (type !in setOf("offer", "answer") || sdp.isBlank() || sdp.length > 64 * 1024) {
            throw PersonTransportException("invalid session description")
        }
        postSignal(payload, eventId, codec.encodeSessionDescription(payload, type, sdp, eventId))
    }

    override suspend fun sendCandidate(payload: VoipCallPayload, candidate: IceCandidate, eventId: String) {
        if (candidate.candidate.isBlank() || candidate.candidate.length > 4096) {
            throw PersonTransportException("invalid ICE candidate")
        }
        postSignal(payload, eventId, codec.encodeIceCandidate(payload, candidate, eventId))
    }

    override suspend fun acknowledge(payload: VoipCallPayload, eventIds: List<String>) {
        val unique = eventIds.distinct()
        if (unique.isEmpty() || unique.size > 50 || unique.size != eventIds.size) {
            throw PersonTransportException("invalid acknowledgement batch")
        }
        val response = client.request(
            path = callPath(payload, "signals/ack"),
            method = "POST",
            body = codec.encodeSignalAcknowledgement(payload, unique),
            headers = JSON_HEADERS,
        ).awaitSuccess()
        if (codec.decodeAcknowledgedEventIds(response.body).toSet() != unique.toSet()) {
            throw PersonTransportException("acknowledgement mismatch")
        }
    }

    private suspend fun get(
        payload: VoipCallPayload,
        suffix: String,
        extraQuery: Map<String, String> = emptyMap(),
    ): ApiResponse = client.request(
        path = callPath(payload, suffix),
        query = extraQuery + mapOf(
            "other_email" to payload.callerEmail,
            "call_type" to payload.callType.wireValue,
        ),
    ).awaitSuccess()

    private suspend fun postSignal(payload: VoipCallPayload, eventId: String, body: ByteArray) {
        requireEventId(eventId)
        val response = client.request(
            path = callPath(payload, "signals"), method = "POST", body = body, headers = JSON_HEADERS,
        ).awaitSuccess()
        val acknowledgement = codec.decodeSignalAcknowledgement(response.body)
        if (!acknowledgement.ok || acknowledgement.eventId != eventId) {
            throw PersonTransportException("signal acknowledgement mismatch")
        }
    }

    private fun callPath(payload: VoipCallPayload, suffix: String): String =
        "/api/calls/${payload.callId}/$suffix"

    private fun requireEventId(value: String) {
        if (value.length !in 16..80 || !value.all { it.isLetterOrDigit() || it == '_' || it == '-' }) {
            throw PersonTransportException("invalid event ID")
        }
    }

    private fun validIceUrl(value: String): Boolean {
        val normalized = value.lowercase()
        return normalized.startsWith("stun:") || normalized.startsWith("turn:") || normalized.startsWith("turns:")
    }

    private suspend fun CompletableFuture<ApiResponse>.awaitSuccess(): ApiResponse = suspendCoroutine { continuation ->
        whenComplete { response, failure ->
            when {
                failure != null -> continuation.resumeWithException(unwrap(failure))
                response.statusCode !in 200..299 -> continuation.resumeWithException(
                    PersonTransportException("HTTP ${response.statusCode}"),
                )
                else -> continuation.resume(response)
            }
        }
    }

    private fun unwrap(failure: Throwable): Throwable =
        if (failure is CompletionException && failure.cause != null) failure.cause!! else failure

    private companion object {
        val JSON_HEADERS = mapOf("Content-Type" to "application/json", "Cache-Control" to "no-store")
    }
}
