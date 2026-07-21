package com.almatchlife.app

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.util.LruCache
import java.net.HttpURLConnection
import java.net.URI
import java.util.concurrent.CompletableFuture
import java.util.concurrent.Executor
import java.util.concurrent.atomic.AtomicReference

internal class SafeRemoteImageLoader(private val origin: URI, private val executor: Executor) {
    private val byteCache = object : LruCache<String, ByteArray>(CACHE_BYTES) {
        override fun sizeOf(key: String, value: ByteArray): Int = value.size
    }

    fun load(value: String): CompletableFuture<Bitmap> {
        val future = DisconnectingImageFuture()
        runCatching {
            executor.execute {
                if (future.isCancelled) return@execute
                runCatching {
                    val uri = validatedUri(value)
                    val key = uri.normalize().toASCIIString()
                    val cached = synchronized(byteCache) { byteCache.get(key) }
                    if (cached != null) {
                        runCatching { decodeBounded(cached) }.getOrElse {
                            synchronized(byteCache) { byteCache.remove(key) }
                            val downloaded = download(uri, future)
                            decodeBounded(downloaded).also {
                                synchronized(byteCache) { byteCache.put(key, downloaded) }
                            }
                        }
                    } else {
                        val downloaded = download(uri, future)
                        decodeBounded(downloaded).also {
                            synchronized(byteCache) { byteCache.put(key, downloaded) }
                        }
                    }
                }
                    .onSuccess { bitmap -> if (!future.complete(bitmap)) bitmap.recycle() }
                    .onFailure { failure -> if (!future.isCancelled) future.completeExceptionally(failure) }
            }
        }.onFailure { failure -> future.completeExceptionally(failure) }
        return future
    }

    fun trimMemory(aggressive: Boolean) {
        synchronized(byteCache) {
            if (aggressive) byteCache.evictAll() else byteCache.trimToSize(CACHE_BYTES / 2)
        }
    }

    private fun validatedUri(value: String): URI {
        val uri = origin.resolve(value)
        require(uri.scheme == origin.scheme && uri.host == origin.host && uri.port == origin.port &&
            uri.userInfo == null && uri.fragment == null) { "media origin rejected" }
        return uri
    }

    private fun download(uri: URI, future: DisconnectingImageFuture): ByteArray {
        val connection = uri.toURL().openConnection() as HttpURLConnection
        future.attach(connection)
        return try {
            connection.instanceFollowRedirects = false
            connection.useCaches = false
            connection.connectTimeout = 8_000
            connection.readTimeout = 12_000
            connection.setRequestProperty("Accept", "image/jpeg,image/png,image/webp")
            connection.setRequestProperty("Accept-Encoding", "identity")
            val status = connection.responseCode
            require(status == 200) { "media response rejected" }
            val contentType = connection.contentType?.substringBefore(';')?.trim()?.lowercase()
            require(contentType in ALLOWED_CONTENT_TYPES) { "media type rejected" }
            val declared = connection.contentLengthLong
            require(declared == -1L || declared in 1..MAX_BYTES.toLong()) { "media size rejected" }
            val bytes = connection.inputStream.use { input ->
                val output = java.io.ByteArrayOutputStream()
                val buffer = ByteArray(16 * 1024)
                var total = 0
                while (true) {
                    val count = input.read(buffer)
                    if (count < 0) break
                    total += count
                    require(total <= MAX_BYTES) { "media exceeds size cap" }
                    output.write(buffer, 0, count)
                }
                output.toByteArray()
            }
            require(signatureMatches(contentType, bytes)) { "media signature rejected" }
            validateDimensions(bytes)
            bytes
        } finally {
            future.detach(connection)
            connection.disconnect()
        }
    }

    private fun decodeBounded(bytes: ByteArray): Bitmap {
        val bounds = validateDimensions(bytes)
        var sample = 1
        while (bounds.outWidth / sample > PREVIEW_DIMENSION || bounds.outHeight / sample > PREVIEW_DIMENSION) sample *= 2
        return requireNotNull(BitmapFactory.decodeByteArray(
            bytes, 0, bytes.size, BitmapFactory.Options().apply { inSampleSize = sample },
        )) { "media decode failed" }
    }

    private fun validateDimensions(bytes: ByteArray): BitmapFactory.Options {
        val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeByteArray(bytes, 0, bytes.size, bounds)
        require(bounds.outWidth in 1..MAX_DIMENSION && bounds.outHeight in 1..MAX_DIMENSION &&
            bounds.outWidth.toLong() * bounds.outHeight <= MAX_PIXELS) { "media dimensions rejected" }
        return bounds
    }

    private fun signatureMatches(contentType: String?, bytes: ByteArray): Boolean = when (contentType) {
        "image/jpeg" -> bytes.size >= 3 && bytes[0] == 0xff.toByte() && bytes[1] == 0xd8.toByte() && bytes[2] == 0xff.toByte()
        "image/png" -> bytes.size >= 8 && bytes.copyOfRange(0, 8).contentEquals(PNG_SIGNATURE)
        "image/webp" -> bytes.size >= 12 && bytes.copyOfRange(0, 4).contentEquals("RIFF".toByteArray()) &&
            bytes.copyOfRange(8, 12).contentEquals("WEBP".toByteArray())
        else -> false
    }

    private companion object {
        const val MAX_BYTES = 3 * 1024 * 1024
        const val CACHE_BYTES = 12 * 1024 * 1024
        const val MAX_DIMENSION = 4096
        const val PREVIEW_DIMENSION = 1600
        const val MAX_PIXELS = 12_000_000L
        val ALLOWED_CONTENT_TYPES = setOf("image/jpeg", "image/png", "image/webp")
        val PNG_SIGNATURE = byteArrayOf(0x89.toByte(), 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a)
    }

    private class DisconnectingImageFuture : CompletableFuture<Bitmap>() {
        private val connection = AtomicReference<HttpURLConnection?>()

        fun attach(value: HttpURLConnection) {
            if (!connection.compareAndSet(null, value) || isCancelled) {
                value.disconnect()
                if (!isCancelled) throw IllegalStateException("image connection already attached")
            }
        }

        fun detach(value: HttpURLConnection) { connection.compareAndSet(value, null) }

        override fun cancel(mayInterruptIfRunning: Boolean): Boolean {
            val cancelled = super.cancel(mayInterruptIfRunning)
            if (cancelled) connection.getAndSet(null)?.disconnect()
            return cancelled
        }
    }
}
