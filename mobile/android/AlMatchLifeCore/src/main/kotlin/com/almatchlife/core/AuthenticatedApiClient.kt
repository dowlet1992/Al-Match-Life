package com.almatchlife.core

import java.net.URI
import java.util.concurrent.CompletableFuture
import java.util.concurrent.CompletionException
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException
import kotlin.coroutines.suspendCoroutine

internal fun <T> failedFutureCompat(failure: Throwable): CompletableFuture<T> =
    CompletableFuture<T>().also { it.completeExceptionally(failure) }

data class SessionTokens(val accessToken: String, val refreshToken: String)

interface SessionTokenStore {
    fun save(tokens: SessionTokens)
    fun read(): SessionTokens?
    fun clear()
}

data class ApiRequest(
    val method: String,
    val uri: URI,
    val headers: Map<String, String>,
    val body: ByteArray? = null,
)

data class ApiResponse(
    val statusCode: Int,
    val headers: Map<String, String>,
    val body: ByteArray,
)

interface ApiTransport {
    fun execute(request: ApiRequest): CompletableFuture<ApiResponse>
}

data class SignalAcknowledgement(val ok: Boolean, val eventId: String)

data class RealtimeSession(
    val clientSecret: String,
    val expiresAt: Long,
    val model: String,
    val transcriptionModel: String,
    val transport: String,
    val callsEndpoint: URI,
    val sourceLanguage: String,
)

data class CaptionSegment(
    val id: String,
    val text: String,
    val speakerEmail: String,
    val sourceLanguage: String,
    val createdAt: Double,
    val sequence: Long = 0,
)

data class CaptionPoll(val captions: List<CaptionSegment>, val serverTime: Double)
data class CaptionTranslation(val captionId: String, val translatedText: String, val targetLanguage: String)
data class SyntheticSpeech(
    val bytes: ByteArray,
    val captionId: String,
    val language: String,
    val voice: String,
)

interface MobileWireCodec {
    fun encodeRefreshRequest(refreshToken: String): ByteArray
    fun decodeSessionTokens(body: ByteArray): SessionTokens
    fun encodeCallSignal(
        callId: String,
        otherEmail: String,
        callType: NativeCallType,
        type: String,
        eventId: String,
        reason: String?,
    ): ByteArray
    fun decodeSignalAcknowledgement(body: ByteArray): SignalAcknowledgement
    fun decodeIceConfiguration(body: ByteArray): IceConfiguration
    fun decodeSignalPoll(body: ByteArray): SignalPoll
    fun encodeSessionDescription(payload: VoipCallPayload, type: String, sdp: String, eventId: String): ByteArray
    fun encodeIceCandidate(payload: VoipCallPayload, candidate: IceCandidate, eventId: String): ByteArray
    fun encodeSignalAcknowledgement(payload: VoipCallPayload, eventIds: List<String>): ByteArray
    fun decodeAcknowledgedEventIds(body: ByteArray): List<String>
    fun encodeCallContext(otherEmail: String, callType: NativeCallType, voice: String? = null): ByteArray
    fun encodeCaptionTranslationRequest(otherEmail: String, callType: NativeCallType, targetLanguage: String): ByteArray
    fun encodeCaption(segment: CaptionSegment, otherEmail: String, callType: NativeCallType): ByteArray
    fun decodePublishedCaption(body: ByteArray): CaptionSegment
    fun decodeCaptionPoll(body: ByteArray): CaptionPoll
    fun decodeCaptionTranslation(body: ByteArray): CaptionTranslation
    fun decodeRealtimeSession(body: ByteArray): RealtimeSession
}

class ApiClientException(message: String, cause: Throwable? = null) : RuntimeException(message, cause)

class AuthenticatedApiClient(
    baseUri: URI,
    private val transport: ApiTransport,
    private val tokenStore: SessionTokenStore,
    private val codec: MobileWireCodec,
    allowLoopbackHttp: Boolean = false,
) : CallSignaling {
    private val baseUri = validateBaseUri(baseUri, allowLoopbackHttp)
    private val refreshLock = Any()
    private var refreshInFlight: CompletableFuture<SessionTokens>? = null

    fun request(
        path: String,
        method: String = "GET",
        body: ByteArray? = null,
        headers: Map<String, String> = emptyMap(),
        query: Map<String, String> = emptyMap(),
    ): CompletableFuture<ApiResponse> {
        val tokens = tokenStore.read()
            ?: return failedFutureCompat(ApiClientException("authentication required"))
        return authorizedRequest(path, method, body, headers, query, tokens.accessToken).thenCompose { response ->
            if (response.statusCode != 401) CompletableFuture.completedFuture(response)
            else refreshSingleFlight(tokens.accessToken).thenCompose { refreshed ->
                authorizedRequest(path, method, body, headers, query, refreshed.accessToken)
            }
        }
    }

    override suspend fun send(
        type: String,
        eventId: String,
        payload: VoipCallPayload,
        reason: String?,
    ) {
        requireIdentifier(eventId, 16, 80, "event id")
        val body = codec.encodeCallSignal(
            payload.callId,
            payload.callerEmail,
            payload.callType,
            type,
            eventId,
            reason,
        )
        val response = request(
            path = "/api/calls/${payload.callId}/signals",
            method = "POST",
            body = body,
            headers = mapOf("Content-Type" to "application/json"),
        ).await()
        if (response.statusCode !in 200..299) throw ApiClientException("signal rejected: ${response.statusCode}")
        val acknowledgement = codec.decodeSignalAcknowledgement(response.body)
        if (!acknowledgement.ok || acknowledgement.eventId != eventId) {
            throw ApiClientException("signal acknowledgement mismatch")
        }
    }

    suspend fun createRealtimeSession(payload: VoipCallPayload): RealtimeSession {
        val response = checkedRequest(
            "/api/calls/${safePath(payload.callId)}/translation/realtime-session",
            codec.encodeCallContext(payload.callerEmail, payload.callType),
        )
        return codec.decodeRealtimeSession(response.body)
    }

    suspend fun publishCaption(payload: VoipCallPayload, segment: CaptionSegment): CaptionSegment {
        if (segment.text.isBlank() || segment.text.length > 500 || segment.sequence < 0) {
            throw ApiClientException("invalid caption segment")
        }
        val response = checkedRequest(
            "/api/calls/${safePath(payload.callId)}/captions",
            codec.encodeCaption(segment, payload.callerEmail, payload.callType),
        )
        return codec.decodePublishedCaption(response.body)
    }

    suspend fun pollCaptions(payload: VoipCallPayload, after: Double): CaptionPoll {
        val response = request(
            path = "/api/calls/${safePath(payload.callId)}/captions",
            query = mapOf(
                "other_email" to payload.callerEmail,
                "call_type" to payload.callType.wireValue,
                "after" to after.coerceAtLeast(0.0).toString(),
            ),
        ).await()
        requireSuccess(response, "caption poll")
        return codec.decodeCaptionPoll(response.body)
    }

    suspend fun translateCaption(
        payload: VoipCallPayload,
        captionId: String,
        targetLanguage: String,
    ): CaptionTranslation {
        requireIdentifier(captionId, 8, 80, "caption id")
        val body = codec.encodeCaptionTranslationRequest(payload.callerEmail, payload.callType, targetLanguage)
        val response = checkedRequest(
            "/api/calls/${safePath(payload.callId)}/captions/${safePath(captionId)}/translation",
            body,
        )
        return codec.decodeCaptionTranslation(response.body).copy(captionId = captionId)
    }

    suspend fun translatedSpeech(
        payload: VoipCallPayload,
        captionId: String,
        voice: String = "coral",
    ): SyntheticSpeech {
        requireIdentifier(captionId, 8, 80, "caption id")
        if (voice !in ALLOWED_SYNTHETIC_VOICES) throw ApiClientException("unsupported synthetic voice")
        val response = checkedRequest(
            "/api/calls/${safePath(payload.callId)}/captions/${safePath(captionId)}/speech",
            codec.encodeCallContext(payload.callerEmail, payload.callType, voice),
            accept = "audio/mpeg",
        )
        val contentType = response.header("Content-Type")?.substringBefore(';')?.trim()?.lowercase()
        val generated = response.header("X-AI-Generated-Voice")
        val responseCaptionId = response.header("X-Caption-Id")
        val language = response.header("Content-Language")?.trim().orEmpty()
        val responseVoice = response.header("X-AI-Voice")
        if (contentType != "audio/mpeg" || generated != "true" || responseCaptionId != captionId ||
            responseVoice != voice || language.isBlank() || response.body.isEmpty() ||
            response.body.size > MAX_SYNTHETIC_SPEECH_BYTES
        ) throw ApiClientException("invalid synthetic speech response")
        return SyntheticSpeech(response.body, captionId, language, voice)
    }

    private suspend fun checkedRequest(path: String, body: ByteArray, accept: String = "application/json"): ApiResponse {
        val response = request(
            path = path,
            method = "POST",
            body = body,
            headers = mapOf("Content-Type" to "application/json", "Accept" to accept),
        ).await()
        requireSuccess(response, "request")
        return response
    }

    private fun requireSuccess(response: ApiResponse, operation: String) {
        if (response.statusCode !in 200..299) throw ApiClientException("$operation rejected: ${response.statusCode}")
    }

    private fun ApiResponse.header(name: String): String? =
        headers.entries.firstOrNull { it.key.equals(name, ignoreCase = true) }?.value

    private fun safePath(value: String): String {
        requireIdentifier(value, 8, 128, "path identifier")
        return value
    }

    private fun authorizedRequest(
        path: String,
        method: String,
        body: ByteArray?,
        headers: Map<String, String>,
        query: Map<String, String>,
        accessToken: String,
    ): CompletableFuture<ApiResponse> {
        requireSafeToken(accessToken)
        val normalizedMethod = method.uppercase()
        if (normalizedMethod !in setOf("GET", "POST", "PUT", "PATCH", "DELETE")) {
            return failedFutureCompat(ApiClientException("unsupported HTTP method"))
        }
        val uri = endpoint(path, query)
        val safeHeaders = headers.toMutableMap()
        if (safeHeaders.keys.any { it.equals("Authorization", ignoreCase = true) }) {
            return failedFutureCompat(ApiClientException("authorization header is managed internally"))
        }
        safeHeaders["Authorization"] = "Bearer $accessToken"
        if (safeHeaders.keys.none { it.equals("Accept", ignoreCase = true) }) {
            safeHeaders["Accept"] = "application/json"
        }
        return transport.execute(ApiRequest(normalizedMethod, uri, safeHeaders, body))
    }

    private fun refreshSingleFlight(staleAccessToken: String): CompletableFuture<SessionTokens> = synchronized(refreshLock) {
        refreshInFlight?.let { return@synchronized it }
        val current = tokenStore.read()
            ?: return@synchronized failedFutureCompat(ApiClientException("authentication required"))
        if (current.accessToken != staleAccessToken) return@synchronized CompletableFuture.completedFuture(current)
        requireSafeToken(current.refreshToken)
        val request = ApiRequest(
            method = "POST",
            uri = endpoint("/api/auth/refresh"),
            headers = mapOf("Accept" to "application/json", "Content-Type" to "application/json"),
            body = codec.encodeRefreshRequest(current.refreshToken),
        )
        val candidate = transport.execute(request).thenApply { response ->
            if (response.statusCode !in 200..299) throw ApiClientException("refresh rejected")
            codec.decodeSessionTokens(response.body).also {
                requireSafeToken(it.accessToken)
                requireSafeToken(it.refreshToken)
                tokenStore.save(it)
            }
        }
        refreshInFlight = candidate
        candidate.whenComplete { _, failure ->
            synchronized(refreshLock) {
                if (refreshInFlight === candidate) {
                    refreshInFlight = null
                    if (failure != null) tokenStore.clear()
                }
            }
        }
        candidate
    }

    private fun endpoint(path: String, query: Map<String, String> = emptyMap()): URI {
        if (!path.startsWith('/') || path.startsWith("//") || '?' in path || '#' in path) {
            throw ApiClientException("invalid API path")
        }
        if (query.size > 16 || query.any { (key, value) -> key.isBlank() || key.length > 64 || value.length > 2048 }) {
            throw ApiClientException("invalid API query")
        }
        val queryText = query.entries.joinToString("&") { (key, value) ->
            "${encodeQueryValue(key)}=${encodeQueryValue(value)}"
        }.ifEmpty { null }
        val originPath = URI(baseUri.scheme, null, baseUri.host, baseUri.port, path, null, null).toASCIIString()
        val resolved = URI.create(if (queryText == null) originPath else "$originPath?$queryText")
        if (resolved.scheme != baseUri.scheme || resolved.host != baseUri.host || resolved.port != baseUri.port) {
            throw ApiClientException("API endpoint escaped origin")
        }
        return resolved
    }

    private fun encodeQueryValue(value: String): String = java.net.URLEncoder
        .encode(value, Charsets.UTF_8.name())
        .replace("+", "%20")

    private fun requireSafeToken(token: String) {
        if (token.isBlank() || token.length > 8192 || '\r' in token || '\n' in token) {
            throw ApiClientException("invalid bearer token")
        }
    }

    private fun requireIdentifier(value: String, minimum: Int, maximum: Int, label: String) {
        if (value.length !in minimum..maximum || !value.all { it.isLetterOrDigit() || it == '_' || it == '-' }) {
            throw ApiClientException("invalid $label")
        }
    }

    private suspend fun <T> CompletableFuture<T>.await(): T = suspendCoroutine { continuation ->
        whenComplete { value, failure ->
            if (failure == null) continuation.resume(value)
            else continuation.resumeWithException(
                if (failure is CompletionException && failure.cause != null) failure.cause!! else failure,
            )
        }
    }

    private companion object {
        const val MAX_SYNTHETIC_SPEECH_BYTES = 2 * 1024 * 1024
        val ALLOWED_SYNTHETIC_VOICES = setOf("alloy", "ash", "ballad", "coral", "echo", "sage", "shimmer", "verse")
        fun validateBaseUri(uri: URI, allowLoopbackHttp: Boolean): URI {
            // 10.0.2.2 is the Android Emulator's reserved alias for the host loopback.
            // It is accepted only when the caller explicitly enables debug loopback HTTP.
            val loopback = uri.host?.lowercase() in setOf("localhost", "127.0.0.1", "::1", "10.0.2.2")
            if (uri.scheme != "https" && !(allowLoopbackHttp && uri.scheme == "http" && loopback)) {
                throw ApiClientException("HTTPS is required")
            }
            if (uri.host.isNullOrBlank() || uri.userInfo != null || uri.query != null || uri.fragment != null) {
                throw ApiClientException("invalid base URI")
            }
            return URI(uri.scheme, null, uri.host, uri.port, "/", null, null)
        }
    }
}
