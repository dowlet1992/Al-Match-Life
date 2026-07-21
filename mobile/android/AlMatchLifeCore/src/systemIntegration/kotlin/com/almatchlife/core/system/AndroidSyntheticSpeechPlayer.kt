package com.almatchlife.core.system

import android.content.Context
import android.media.AudioAttributes
import android.media.MediaPlayer
import com.almatchlife.core.SyntheticSpeech
import com.almatchlife.core.SyntheticSpeechPlayer
import java.io.File
import java.io.FileOutputStream
import java.util.concurrent.CompletableFuture
import java.util.concurrent.CompletionException
import java.util.concurrent.atomic.AtomicBoolean
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException
import kotlin.coroutines.suspendCoroutine

class SyntheticPlaybackException(message: String, cause: Throwable? = null) : RuntimeException(message, cause)

/**
 * MediaPlayer bridge for already metadata-validated server speech. Bytes are staged only in
 * the app-private cache, unlinked immediately after MediaPlayer receives its descriptor, and
 * never named with a user, call, caption, or language identifier.
 */
class AndroidSyntheticSpeechPlayer(context: Context) : SyntheticSpeechPlayer {
    private val cacheDirectory = context.applicationContext.cacheDir
    private val lock = Any()
    private var active: ActivePlayback? = null

    override suspend fun play(speech: SyntheticSpeech) {
        validateMp3(speech.bytes)
        val completion = CompletableFuture<Unit>()
        val player = MediaPlayer()
        val candidate = ActivePlayback(player, completion)
        synchronized(lock) {
            if (active != null) {
                player.release()
                throw SyntheticPlaybackException("synthetic speech playback is already active")
            }
            active = candidate
        }

        var staged: File? = null
        try {
            player.setAudioAttributes(AudioAttributes.Builder()
                .setUsage(AudioAttributes.USAGE_ASSISTANCE_ACCESSIBILITY)
                .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                .build())
            staged = File.createTempFile(TEMP_PREFIX, TEMP_SUFFIX, cacheDirectory)
            FileOutputStream(staged).use { output ->
                output.write(speech.bytes)
                output.fd.sync()
            }
            staged.inputStream().use { input -> player.setDataSource(input.fd) }
            if (!staged.delete()) throw SyntheticPlaybackException("could not unlink staged speech")
            staged = null

            player.setOnPreparedListener { prepared ->
                if (!candidate.finished.get()) runCatching { prepared.start() }
                    .onFailure { finish(candidate, SyntheticPlaybackException("speech start failed", it)) }
            }
            player.setOnCompletionListener { finish(candidate, null) }
            player.setOnErrorListener { _, _, _ ->
                finish(candidate, SyntheticPlaybackException("synthetic speech decoder rejected audio"))
                true
            }
            player.prepareAsync()
            completion.awaitPlayback()
        } catch (failure: Exception) {
            finish(candidate, failure)
            throw unwrap(failure)
        } finally {
            staged?.delete()
            finish(candidate, null)
        }
    }

    override suspend fun stop() {
        val current = synchronized(lock) { active }
        current?.let { finish(it, null) }
    }

    private fun finish(candidate: ActivePlayback, failure: Throwable?) {
        if (!candidate.finished.compareAndSet(false, true)) return
        synchronized(lock) { if (active === candidate) active = null }
        candidate.player.setOnPreparedListener(null)
        candidate.player.setOnCompletionListener(null)
        candidate.player.setOnErrorListener(null)
        runCatching { if (candidate.player.isPlaying) candidate.player.stop() }
        candidate.player.release()
        if (failure == null) candidate.completion.complete(Unit)
        else candidate.completion.completeExceptionally(failure)
    }

    private fun validateMp3(bytes: ByteArray) {
        if (bytes.size !in MIN_MP3_BYTES..MAX_MP3_BYTES) {
            throw SyntheticPlaybackException("invalid synthetic speech size")
        }
        val id3 = bytes.size >= 3 && bytes[0] == 'I'.code.toByte() &&
            bytes[1] == 'D'.code.toByte() && bytes[2] == '3'.code.toByte()
        val frameSync = bytes.size >= 2 && bytes[0].toInt() and 0xff == 0xff &&
            bytes[1].toInt() and 0xe0 == 0xe0
        if (!id3 && !frameSync) throw SyntheticPlaybackException("invalid MP3 signature")
    }

    private suspend fun CompletableFuture<Unit>.awaitPlayback(): Unit = suspendCoroutine { continuation ->
        whenComplete { _, failure ->
            if (failure == null) continuation.resume(Unit)
            else continuation.resumeWithException(unwrap(failure))
        }
    }

    private fun unwrap(failure: Throwable): Exception {
        val value = if (failure is CompletionException && failure.cause != null) failure.cause!! else failure
        return value as? Exception ?: SyntheticPlaybackException("synthetic playback failed", value)
    }

    private data class ActivePlayback(
        val player: MediaPlayer,
        val completion: CompletableFuture<Unit>,
        val finished: AtomicBoolean = AtomicBoolean(false),
    )

    private companion object {
        const val TEMP_PREFIX = "aml-synthetic-speech-"
        const val TEMP_SUFFIX = ".mp3"
        const val MIN_MP3_BYTES = 4
        const val MAX_MP3_BYTES = 2 * 1024 * 1024
    }
}
