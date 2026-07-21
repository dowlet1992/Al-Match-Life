package com.almatchlife.core

import java.nio.ByteBuffer
import java.security.MessageDigest
import java.util.UUID

enum class NativeCallType(val wireValue: String) { AUDIO("audio"), VIDEO("video") }
enum class PushEventType(val wireValue: String) { INCOMING_CALL("incoming_call"), CALL_CANCELLED("call_cancelled") }

data class VoipCallPayload(
    val eventId: String,
    val eventType: PushEventType,
    val callId: String,
    val callType: NativeCallType,
    val callerEmail: String,
    val receiverEmail: String,
    val expiresAtEpochSeconds: Long,
    val stableUuid: UUID,
)

class InvalidVoipPayload(message: String) : IllegalArgumentException(message)

object VoipPayloadValidator {
    private val identifier = Regex("^[A-Za-z0-9_-]+$")

    fun validate(data: Map<String, String>, currentEmail: String, nowEpochSeconds: Long): VoipCallPayload {
        val eventType = PushEventType.entries.firstOrNull { it.wireValue == data["event_type"] }
            ?: throw InvalidVoipPayload("invalid event type")
        val eventId = boundedIdentifier(data["event_id"], 8, 80, "event id")
        val callId = boundedIdentifier(data["call_id"], 8, 128, "call id")
        val callType = NativeCallType.entries.firstOrNull { it.wireValue == data["call_type"] }
            ?: throw InvalidVoipPayload("invalid call type")
        val caller = validEmail(data["caller_email"])
        val receiver = validEmail(data["receiver_email"])
        if (caller == receiver) throw InvalidVoipPayload("participants must be distinct")
        if (receiver != currentEmail.trim().lowercase()) throw InvalidVoipPayload("wrong receiver")
        val expiresAt = data["expires_at"]?.toLongOrNull() ?: throw InvalidVoipPayload("invalid expiry")
        if (expiresAt < nowEpochSeconds || expiresAt > nowEpochSeconds + 180) {
            throw InvalidVoipPayload("expiry outside trusted window")
        }
        return VoipCallPayload(
            eventId, eventType, callId, callType, caller, receiver, expiresAt,
            stableUuid(callId, callType),
        )
    }

    private fun boundedIdentifier(value: String?, minimum: Int, maximum: Int, label: String): String {
        val normalized = value?.trim().orEmpty()
        if (normalized.length !in minimum..maximum || !identifier.matches(normalized)) {
            throw InvalidVoipPayload("invalid $label")
        }
        return normalized
    }

    private fun validEmail(value: String?): String {
        val normalized = value?.trim()?.lowercase().orEmpty()
        if (normalized.length > 254 || '\r' in normalized || '\n' in normalized ||
            normalized.count { it == '@' } != 1 || normalized.startsWith('@') || normalized.endsWith('@')) {
            throw InvalidVoipPayload("invalid participant")
        }
        return normalized
    }

    private fun stableUuid(callId: String, callType: NativeCallType): UUID {
        val digest = MessageDigest.getInstance("SHA-256")
            .digest("al-match-life:${callType.wireValue}:$callId".toByteArray(Charsets.UTF_8))
            .copyOf(16)
        digest[6] = ((digest[6].toInt() and 0x0f) or 0x50).toByte()
        digest[8] = ((digest[8].toInt() and 0x3f) or 0x80).toByte()
        val buffer = ByteBuffer.wrap(digest)
        return UUID(buffer.long, buffer.long)
    }
}
