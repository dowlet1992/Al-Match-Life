package com.almatchlife.core.system

import com.almatchlife.core.ApiClientException
import com.almatchlife.core.CallSignal
import com.almatchlife.core.CaptionPoll
import com.almatchlife.core.CaptionSegment
import com.almatchlife.core.CaptionTranslation
import com.almatchlife.core.IceCandidate
import com.almatchlife.core.IceConfiguration
import com.almatchlife.core.IceServer
import com.almatchlife.core.MobileWireCodec
import com.almatchlife.core.NativeCallType
import com.almatchlife.core.RealtimeSession
import com.almatchlife.core.SessionTokens
import com.almatchlife.core.SignalAcknowledgement
import com.almatchlife.core.SignalPayload
import com.almatchlife.core.SignalPoll
import com.almatchlife.core.VoipCallPayload
import org.json.JSONArray
import org.json.JSONObject
import java.net.URI

/** Android platform JSON implementation with explicit bounds and no reflective DTO mapping. */
class AndroidMobileWireJsonCodec : MobileWireCodec {
    override fun encodeRefreshRequest(refreshToken: String): ByteArray = objectBytes {
        put("refresh_token", refreshToken)
    }

    override fun decodeSessionTokens(body: ByteArray): SessionTokens = parse(body).let {
        SessionTokens(it.requiredString("access_token", MAX_TOKEN), it.requiredString("refresh_token", MAX_TOKEN))
    }

    override fun encodeCallSignal(
        callId: String,
        otherEmail: String,
        callType: NativeCallType,
        type: String,
        eventId: String,
        reason: String?,
    ): ByteArray = objectBytes {
        putContext(otherEmail, callType)
        put("type", type)
        put("event_id", eventId)
        put("payload", JSONObject().apply {
            put("call_type", callType.wireValue)
            reason?.let { put("reason", it) }
        })
    }

    override fun decodeSignalAcknowledgement(body: ByteArray): SignalAcknowledgement = parse(body).let {
        SignalAcknowledgement(it.optBoolean("ok", false), it.requiredIdentifier("event_id", 16, 80))
    }

    override fun decodeIceConfiguration(body: ByteArray): IceConfiguration {
        val root = parse(body)
        val values = root.requiredArray("ice_servers", MAX_ICE_SERVERS)
        val servers = buildList {
            for (index in 0 until values.length()) {
                val item = values.optJSONObject(index) ?: invalid("invalid ICE server")
                val urlsValue = item.opt("urls")
                val urls = when (urlsValue) {
                    null -> invalid("missing ICE URLs")
                    is String -> listOf(urlsValue.bounded(MAX_URL, "ICE URL"))
                    is JSONArray -> urlsValue.strings(MAX_ICE_URLS, MAX_URL, "ICE URL")
                    else -> invalid("invalid ICE URLs")
                }
                add(IceServer(
                    urls,
                    item.optionalString("username", MAX_CREDENTIAL),
                    item.optionalString("credential", MAX_CREDENTIAL),
                ))
            }
        }
        return IceConfiguration(
            servers,
            root.requiredString("provider", 64),
            root.requiredFiniteDouble("expires_at"),
        )
    }

    override fun decodeSignalPoll(body: ByteArray): SignalPoll {
        val root = parse(body)
        val values = root.requiredArray("messages", MAX_SIGNAL_MESSAGES)
        val messages = buildList {
            for (index in 0 until values.length()) {
                val item = values.optJSONObject(index) ?: invalid("invalid signal")
                val payload = item.optJSONObject("payload") ?: JSONObject()
                add(CallSignal(
                    item.requiredIdentifier("id", 16, 80),
                    item.requiredString("type", 16),
                    SignalPayload(
                        sdp = payload.optionalString("sdp", MAX_SDP),
                        candidate = payload.optionalString("candidate", MAX_CANDIDATE),
                        sdpMid = payload.optionalString("sdpMid", 128),
                        sdpMLineIndex = payload.optionalInt("sdpMLineIndex"),
                        usernameFragment = payload.optionalString("usernameFragment", 256),
                    ),
                ))
            }
        }
        return SignalPoll(
            root.requiredString("status", 32), messages, root.requiredFiniteDouble("server_time"),
        )
    }

    override fun encodeSessionDescription(
        payload: VoipCallPayload,
        type: String,
        sdp: String,
        eventId: String,
    ): ByteArray = objectBytes {
        putContext(payload.callerEmail, payload.callType)
        put("type", type); put("event_id", eventId)
        put("payload", JSONObject().apply {
            put("type", type); put("sdp", sdp); put("call_type", payload.callType.wireValue)
        })
    }

    override fun encodeIceCandidate(
        payload: VoipCallPayload,
        candidate: IceCandidate,
        eventId: String,
    ): ByteArray = objectBytes {
        putContext(payload.callerEmail, payload.callType)
        put("type", "ice"); put("event_id", eventId)
        put("payload", JSONObject().apply {
            put("candidate", candidate.candidate); put("call_type", payload.callType.wireValue)
            candidate.sdpMid?.let { put("sdpMid", it) }
            candidate.sdpMLineIndex?.let { put("sdpMLineIndex", it) }
            candidate.usernameFragment?.let { put("usernameFragment", it) }
        })
    }

    override fun encodeSignalAcknowledgement(payload: VoipCallPayload, eventIds: List<String>): ByteArray =
        objectBytes {
            putContext(payload.callerEmail, payload.callType)
            put("event_ids", JSONArray(eventIds))
        }

    override fun decodeAcknowledgedEventIds(body: ByteArray): List<String> =
        parse(body).requiredArray("acknowledged_event_ids", 50).identifiers(16, 80)

    override fun encodeCallContext(otherEmail: String, callType: NativeCallType, voice: String?): ByteArray =
        objectBytes { putContext(otherEmail, callType); voice?.let { put("voice", it) } }

    override fun encodeCaptionTranslationRequest(
        otherEmail: String,
        callType: NativeCallType,
        targetLanguage: String,
    ): ByteArray = objectBytes {
        putContext(otherEmail, callType); put("target_language", targetLanguage)
    }

    override fun encodeCaption(
        segment: CaptionSegment,
        otherEmail: String,
        callType: NativeCallType,
    ): ByteArray = objectBytes {
        putContext(otherEmail, callType)
        put("text", segment.text); put("source_language", segment.sourceLanguage)
        put("is_final", true); put("sequence", segment.sequence)
    }

    override fun decodePublishedCaption(body: ByteArray): CaptionSegment =
        decodeCaption(parse(body).requiredObject("caption"))

    override fun decodeCaptionPoll(body: ByteArray): CaptionPoll {
        val root = parse(body)
        val values = root.requiredArray("captions", MAX_CAPTIONS)
        return CaptionPoll(
            buildList { for (index in 0 until values.length()) add(decodeCaption(values.requiredObject(index))) },
            root.requiredFiniteDouble("server_time"),
        )
    }

    override fun decodeCaptionTranslation(body: ByteArray): CaptionTranslation {
        val value = parse(body).requiredObject("translation")
        return CaptionTranslation(
            captionId = "pending",
            translatedText = value.requiredString("translated_text", MAX_CAPTION_TEXT),
            targetLanguage = value.requiredString("target_language", 32),
        )
    }

    override fun decodeRealtimeSession(body: ByteArray): RealtimeSession {
        val value = parse(body).requiredObject("session")
        val endpoint = runCatching { URI(value.requiredString("calls_endpoint", MAX_URL)) }
            .getOrElse { invalid("invalid Realtime endpoint") }
        return RealtimeSession(
            clientSecret = value.requiredString("client_secret", MAX_TOKEN),
            expiresAt = value.requiredLong("expires_at"),
            model = value.requiredString("model", 128),
            transcriptionModel = value.requiredString("transcription_model", 128),
            transport = value.requiredString("transport", 32),
            callsEndpoint = endpoint,
            sourceLanguage = value.requiredString("source_language", 32),
        )
    }

    private fun decodeCaption(value: JSONObject): CaptionSegment = CaptionSegment(
        id = value.requiredIdentifier("id", 8, 80),
        text = value.requiredString("text", MAX_CAPTION_TEXT),
        speakerEmail = value.requiredString("speaker_email", 254),
        sourceLanguage = value.requiredString("source_language", 32),
        createdAt = value.requiredFiniteDouble("created_at"),
        sequence = value.optLong("sequence", 0).also { if (it < 0) invalid("invalid caption sequence") },
    )

    private fun parse(bytes: ByteArray): JSONObject {
        if (bytes.isEmpty() || bytes.size > MAX_JSON_BYTES) invalid("invalid JSON response size")
        return runCatching { JSONObject(bytes.toString(Charsets.UTF_8)) }
            .getOrElse { invalid("invalid JSON response") }
    }

    private fun objectBytes(block: JSONObject.() -> Unit): ByteArray =
        JSONObject().apply(block).toString().toByteArray(Charsets.UTF_8).also {
            if (it.size > MAX_JSON_BYTES) invalid("JSON request too large")
        }

    private fun JSONObject.putContext(otherEmail: String, callType: NativeCallType) {
        put("other_email", otherEmail); put("call_type", callType.wireValue)
    }

    private fun JSONObject.requiredString(name: String, maximum: Int): String =
        optString(name, "").bounded(maximum, name)

    private fun JSONObject.optionalString(name: String, maximum: Int): String? =
        if (!has(name) || isNull(name)) null else optString(name, "").bounded(maximum, name)

    private fun String.bounded(maximum: Int, label: String): String =
        takeIf { it.isNotEmpty() && it.length <= maximum && '\u0000' !in it }
            ?: invalid("invalid $label")

    private fun JSONObject.requiredIdentifier(name: String, minimum: Int, maximum: Int): String =
        requiredString(name, maximum).takeIf {
            it.length >= minimum && it.all { character -> character.isLetterOrDigit() || character == '_' || character == '-' }
        } ?: invalid("invalid $name")

    private fun JSONObject.requiredArray(name: String, maximum: Int): JSONArray =
        optJSONArray(name)?.also { if (it.length() > maximum) invalid("too many $name") }
            ?: invalid("invalid $name")

    private fun JSONObject.requiredObject(name: String): JSONObject = optJSONObject(name) ?: invalid("invalid $name")
    private fun JSONArray.requiredObject(index: Int): JSONObject = optJSONObject(index) ?: invalid("invalid array item")
    private fun JSONObject.requiredFiniteDouble(name: String): Double = optDouble(name, Double.NaN).also {
        if (!it.isFinite() || it < 0) invalid("invalid $name")
    }
    private fun JSONObject.requiredLong(name: String): Long =
        if (!has(name) || isNull(name)) invalid("invalid $name") else optLong(name, Long.MIN_VALUE).also {
            if (it == Long.MIN_VALUE) invalid("invalid $name")
        }
    private fun JSONObject.optionalInt(name: String): Int? =
        if (!has(name) || isNull(name)) null else optInt(name)

    private fun JSONArray.strings(maximumItems: Int, maximumLength: Int, label: String): List<String> {
        if (length() !in 1..maximumItems) invalid("invalid $label list")
        return buildList { for (index in 0 until length()) add(optString(index, "").bounded(maximumLength, label)) }
    }

    private fun JSONArray.identifiers(minimum: Int, maximum: Int): List<String> = buildList {
        for (index in 0 until length()) {
            val value = optString(index, "")
            if (value.length !in minimum..maximum || !value.all { it.isLetterOrDigit() || it == '_' || it == '-' }) {
                invalid("invalid event ID")
            }
            add(value)
        }
    }

    private fun invalid(message: String): Nothing = throw ApiClientException(message)

    private companion object {
        const val MAX_JSON_BYTES = 256 * 1024
        const val MAX_TOKEN = 8192
        const val MAX_URL = 2048
        const val MAX_CREDENTIAL = 2048
        const val MAX_SDP = 64 * 1024
        const val MAX_CANDIDATE = 4096
        const val MAX_CAPTION_TEXT = 500
        const val MAX_ICE_SERVERS = 16
        const val MAX_ICE_URLS = 8
        const val MAX_SIGNAL_MESSAGES = 300
        const val MAX_CAPTIONS = 100
    }
}
