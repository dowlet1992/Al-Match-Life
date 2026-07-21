package com.almatchlife.core.system

import com.almatchlife.core.ApiClientException
import com.almatchlife.core.ApiRequest
import com.almatchlife.core.ApiResponse
import com.almatchlife.core.ApiTransport
import java.io.ByteArrayOutputStream
import java.net.HttpURLConnection
import java.util.concurrent.CompletableFuture
import java.util.concurrent.Executor
import java.util.concurrent.atomic.AtomicReference

/**
 * Dependency-free Android transport. Authentication, origin locking, and refresh remain owned
 * by AuthenticatedApiClient; this class performs exactly one bounded, non-redirecting exchange.
 */
class AndroidUrlConnectionApiTransport(
    private val executor: Executor,
    private val connectTimeoutMillis: Int = 10_000,
    private val readTimeoutMillis: Int = 20_000,
    private val maximumResponseBytes: Int = 2 * 1024 * 1024,
) : ApiTransport {
    init {
        require(connectTimeoutMillis in 1_000..60_000)
        require(readTimeoutMillis in 1_000..120_000)
        require(maximumResponseBytes in 64 * 1024..4 * 1024 * 1024)
    }

    override fun execute(request: ApiRequest): CompletableFuture<ApiResponse> {
        validateRequest(request)
        val connection = AtomicReference<HttpURLConnection?>()
        val future = DisconnectingFuture(connection)
        executor.execute {
            if (future.isCancelled) return@execute
            try {
                val current = request.uri.toURL().openConnection() as? HttpURLConnection
                    ?: throw ApiClientException("unsupported HTTP connection")
                connection.set(current)
                if (future.isCancelled) { current.disconnect(); return@execute }
                configure(current, request)
                val status = current.responseCode
                val headers = readHeaders(current)
                val declaredLength = current.contentLengthLong
                if (declaredLength > maximumResponseBytes) throw ApiClientException("HTTP response too large")
                val stream = if (status >= 400) current.errorStream else current.inputStream
                val body = stream?.use { input ->
                    val output = ByteArrayOutputStream(minOf(
                        if (declaredLength in 0..maximumResponseBytes.toLong()) declaredLength.toInt() else 8192,
                        maximumResponseBytes,
                    ))
                    val buffer = ByteArray(8192)
                    var total = 0
                    while (true) {
                        if (future.isCancelled) throw ApiClientException("HTTP request cancelled")
                        val count = input.read(buffer)
                        if (count < 0) break
                        total += count
                        if (total > maximumResponseBytes) throw ApiClientException("HTTP response too large")
                        output.write(buffer, 0, count)
                    }
                    output.toByteArray()
                } ?: ByteArray(0)
                future.complete(ApiResponse(status, headers, body))
            } catch (failure: Exception) {
                if (!future.isCancelled) future.completeExceptionally(failure)
            } finally {
                connection.getAndSet(null)?.disconnect()
            }
        }
        return future
    }

    private fun configure(connection: HttpURLConnection, request: ApiRequest) {
        connection.instanceFollowRedirects = false
        connection.connectTimeout = connectTimeoutMillis
        connection.readTimeout = readTimeoutMillis
        connection.requestMethod = request.method
        connection.useCaches = false
        request.headers.forEach { (name, value) -> connection.setRequestProperty(name, value) }
        connection.setRequestProperty("Accept-Encoding", "identity")
        request.body?.let { body ->
            connection.doOutput = true
            connection.setFixedLengthStreamingMode(body.size)
            connection.outputStream.use { it.write(body) }
        }
    }

    private fun validateRequest(request: ApiRequest) {
        if (request.uri.scheme !in setOf("https", "http") || request.uri.host.isNullOrBlank() ||
            request.uri.userInfo != null || request.uri.fragment != null
        ) throw ApiClientException("invalid transport URI")
        if (request.method !in ALLOWED_METHODS) throw ApiClientException("invalid transport method")
        if ((request.body?.size ?: 0) > MAXIMUM_REQUEST_BYTES) throw ApiClientException("HTTP request too large")
        if (request.headers.size > MAXIMUM_HEADERS) throw ApiClientException("too many HTTP headers")
        request.headers.forEach { (name, value) ->
            if (!HEADER_NAME.matches(name) || value.length > MAXIMUM_HEADER_VALUE || '\r' in value || '\n' in value) {
                throw ApiClientException("invalid HTTP header")
            }
        }
    }

    private fun readHeaders(connection: HttpURLConnection): Map<String, String> {
        val result = linkedMapOf<String, String>()
        connection.headerFields.entries.forEach { (name, values) ->
            if (name == null || values == null || result.size >= MAXIMUM_HEADERS) return@forEach
            val value = values.joinToString(",").take(MAXIMUM_HEADER_VALUE)
            if (HEADER_NAME.matches(name) && '\r' !in value && '\n' !in value) result[name] = value
        }
        return result
    }

    private class DisconnectingFuture(
        private val connection: AtomicReference<HttpURLConnection?>,
    ) : CompletableFuture<ApiResponse>() {
        override fun cancel(mayInterruptIfRunning: Boolean): Boolean {
            val cancelled = super.cancel(mayInterruptIfRunning)
            if (cancelled) connection.get()?.disconnect()
            return cancelled
        }
    }

    private companion object {
        val ALLOWED_METHODS = setOf("GET", "POST", "PUT", "PATCH", "DELETE")
        val HEADER_NAME = Regex("^[A-Za-z0-9!#$%&'*+.^_`|~-]{1,64}$")
        const val MAXIMUM_REQUEST_BYTES = 256 * 1024
        const val MAXIMUM_HEADERS = 64
        const val MAXIMUM_HEADER_VALUE = 8192
    }
}
