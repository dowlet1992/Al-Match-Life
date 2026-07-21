package com.almatchlife.core

import java.net.URI

sealed class RealtimeSpeechException(message: String) : RuntimeException(message) {
    class AlreadyRunning : RealtimeSpeechException("realtime speech is already running")
    class ExpiredCredential : RealtimeSpeechException("realtime credential is expired")
    class InvalidProviderEndpoint : RealtimeSpeechException("invalid realtime provider endpoint")
    class InvalidCredential : RealtimeSpeechException("invalid realtime credential")
    class InvalidSdp : RealtimeSpeechException("invalid realtime SDP")
    class ProviderStatus(val status: Int) : RealtimeSpeechException("realtime provider rejected SDP: $status")
}

data class RealtimeTranscript(val itemId: String, val text: String, val isFinal: Boolean)
data class RealtimeProviderEvent(
    val type: String,
    val itemId: String? = null,
    val delta: String? = null,
    val transcript: String? = null,
    val errorCode: String? = null,
)

interface RealtimeEventCodec { fun decode(bytes: ByteArray): RealtimeProviderEvent? }

interface RealtimePeer {
    suspend fun setEventHandler(handler: suspend (ByteArray) -> Unit)
    suspend fun addClonedMicrophoneTrack()
    suspend fun createOffer(): String
    suspend fun setRemoteAnswer(sdp: String)
    suspend fun close()
}

interface RealtimePeerFactory { suspend fun create(): RealtimePeer }
interface RealtimeSdpExchanger { suspend fun exchange(offer: String, session: RealtimeSession): String }

class ProviderRealtimeSdpExchanger(private val transport: ApiTransport) : RealtimeSdpExchanger {
    override suspend fun exchange(offer: String, session: RealtimeSession): String {
        validateSession(session)
        val offerBytes = offer.toByteArray(Charsets.UTF_8)
        if (!offer.startsWith("v=0") || offerBytes.size > MAX_SDP_BYTES) throw RealtimeSpeechException.InvalidSdp()
        val boundary = "AlMatchLife-${java.util.UUID.randomUUID()}"
        val prefix = "--$boundary\r\nContent-Disposition: form-data; name=\"sdp\"; filename=\"offer.sdp\"\r\n" +
            "Content-Type: application/sdp\r\n\r\n"
        val suffix = "\r\n--$boundary--\r\n"
        val body = prefix.toByteArray() + offerBytes + suffix.toByteArray()
        val response = transport.execute(ApiRequest(
            method = "POST",
            uri = session.callsEndpoint,
            headers = mapOf(
                "Authorization" to "Bearer ${session.clientSecret}",
                "Content-Type" to "multipart/form-data; boundary=$boundary",
                "Accept" to "application/sdp",
                "Cache-Control" to "no-store",
            ),
            body = body,
        )).awaitRealtime()
        if (response.statusCode !in 200..299) throw RealtimeSpeechException.ProviderStatus(response.statusCode)
        if (response.body.size > MAX_SDP_BYTES) throw RealtimeSpeechException.InvalidSdp()
        return response.body.toString(Charsets.UTF_8).also {
            if (!it.startsWith("v=0")) throw RealtimeSpeechException.InvalidSdp()
        }
    }

    private fun validateSession(session: RealtimeSession) {
        val uri: URI = session.callsEndpoint
        if (uri.scheme != "https" || uri.host?.lowercase() != "api.openai.com" || uri.path != "/v1/realtime/calls" ||
            uri.userInfo != null || uri.query != null || uri.fragment != null
        ) throw RealtimeSpeechException.InvalidProviderEndpoint()
        if (session.clientSecret.isBlank() || session.clientSecret.length > 8192 ||
            '\r' in session.clientSecret || '\n' in session.clientSecret
        ) throw RealtimeSpeechException.InvalidCredential()
    }

    private suspend fun <T> java.util.concurrent.CompletableFuture<T>.awaitRealtime(): T =
        kotlin.coroutines.suspendCoroutine { continuation ->
            whenComplete { value, failure ->
                if (failure == null) continuation.resumeWith(Result.success(value))
                else continuation.resumeWith(Result.failure(failure.cause ?: failure))
            }
        }

    companion object { const val MAX_SDP_BYTES = 64 * 1024 }
}

class OpenAiRealtimeSpeechTransport(
    private val factory: RealtimePeerFactory,
    private val exchanger: RealtimeSdpExchanger,
    private val eventCodec: RealtimeEventCodec,
    private val sessionProvider: suspend () -> RealtimeSession,
    private val transcriptHandler: suspend (RealtimeTranscript) -> Unit,
    private val errorHandler: suspend (String) -> Unit,
    private val nowEpochSeconds: () -> Long = { System.currentTimeMillis() / 1000 },
) : SpeechTransport {
    private val lock = Any()
    private var peer: RealtimePeer? = null
    private val partials = mutableMapOf<String, String>()

    override suspend fun start() {
        synchronized(lock) { if (peer != null) throw RealtimeSpeechException.AlreadyRunning() }
        val session = sessionProvider()
        if (session.expiresAt <= nowEpochSeconds() + 5) throw RealtimeSpeechException.ExpiredCredential()
        val candidate = factory.create()
        try {
            candidate.setEventHandler(::consumeEvent)
            candidate.addClonedMicrophoneTrack()
            val answer = exchanger.exchange(candidate.createOffer(), session)
            candidate.setRemoteAnswer(answer)
            synchronized(lock) {
                if (peer != null) throw RealtimeSpeechException.AlreadyRunning()
                peer = candidate
            }
        } catch (failure: Exception) {
            candidate.setEventHandler { }
            candidate.close()
            throw failure
        }
    }

    override suspend fun stop() {
        val current = synchronized(lock) { peer.also { peer = null; partials.clear() } }
        current?.setEventHandler { }
        current?.close()
    }

    private suspend fun consumeEvent(bytes: ByteArray) {
        val event = eventCodec.decode(bytes) ?: return
        val itemId = event.itemId ?: "current"
        when (event.type) {
            "conversation.item.input_audio_transcription.delta" -> {
                val text = synchronized(lock) {
                    (partials[itemId].orEmpty() + event.delta.orEmpty()).also { partials[itemId] = it }
                }
                if (text.isNotBlank()) transcriptHandler(RealtimeTranscript(itemId, text, false))
            }
            "conversation.item.input_audio_transcription.completed" -> {
                val text = synchronized(lock) { (event.transcript ?: partials.remove(itemId).orEmpty()).trim() }
                synchronized(lock) { partials.remove(itemId) }
                if (text.isNotEmpty()) transcriptHandler(RealtimeTranscript(itemId, text, true))
            }
            "error" -> errorHandler(event.errorCode ?: "realtime_provider_error")
        }
    }
}

/** Publishes final provider transcripts only; interim text remains device-local. */
class FinalCaptionPublisher(
    private val api: AuthenticatedApiClient,
    private val payload: VoipCallPayload,
    private val sourceLanguage: () -> String,
) {
    private val lock = Any()
    private var sequence = 0L

    suspend fun receive(transcript: RealtimeTranscript): CaptionSegment? {
        if (!transcript.isFinal || transcript.text.isBlank()) return null
        val next = synchronized(lock) { sequence += 1; sequence }
        return api.publishCaption(payload, CaptionSegment(
            id = "pending",
            text = transcript.text.trim().take(500),
            speakerEmail = payload.receiverEmail,
            sourceLanguage = sourceLanguage(),
            createdAt = 0.0,
            sequence = next,
        ))
    }
}
