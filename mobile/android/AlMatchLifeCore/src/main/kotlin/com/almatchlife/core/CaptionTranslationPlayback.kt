package com.almatchlife.core

import java.util.ArrayDeque

interface RemoteAudioDucker { suspend fun setDucked(ducked: Boolean) }
interface SyntheticSpeechPlayer {
    /** Returns only after playback finishes. */
    suspend fun play(speech: SyntheticSpeech)
    suspend fun stop()
}

interface CaptionPresenter {
    suspend fun showOriginal(caption: CaptionSegment)
    suspend fun showTranslation(caption: CaptionSegment, translation: CaptionTranslation)
}

class RemoteCaptionPolling(
    private val api: AuthenticatedApiClient,
    private val payload: VoipCallPayload,
    private val translation: LatestCaptionTranslation,
    private val launcher: BackgroundTaskLauncher,
    private val sleeper: TaskSleeper,
    private val onError: suspend (Exception) -> Unit,
) : SpeechTransport {
    private val lock = Any()
    private var task: BackgroundTask? = null
    private var generation = 0L
    private var watermark = 0.0
    private val processedIds = ArrayDeque<String>()

    override suspend fun start() {
        val runGeneration = synchronized(lock) {
            check(task == null) { "remote caption polling is already running" }
            generation += 1
            generation
        }
        val candidate = launcher.launch { cancellation -> pollLoop(runGeneration, cancellation) }
        synchronized(lock) {
            if (generation == runGeneration && task == null) task = candidate else candidate.cancel()
        }
    }

    override suspend fun stop() {
        val current = synchronized(lock) {
            generation += 1
            task.also {
                task = null
                watermark = 0.0
                processedIds.clear()
            }
        }
        current?.cancel()
    }

    private suspend fun pollLoop(runGeneration: Long, cancellation: CancellationProbe) {
        var failures = 0
        while (!cancellation.isCancelled && synchronized(lock) { generation == runGeneration }) {
            try {
                val after = synchronized(lock) { watermark }
                val result = api.pollCaptions(payload, after)
                for (caption in result.captions) {
                    if (synchronized(lock) { caption.id in processedIds }) continue
                    translation.receive(caption) // Original is presented before async translation starts.
                    synchronized(lock) { remember(caption.id) }
                }
                synchronized(lock) { watermark = maxOf(watermark, result.serverTime - CURSOR_OVERLAP_SECONDS) }
                failures = 0
            } catch (failure: Exception) {
                failures += 1
                onError(failure)
            }
            val delay = if (failures == 0) NORMAL_POLL_MILLIS
                else minOf(RETRY_BASE_MILLIS * (1L shl minOf(failures - 1, 3)), MAX_RETRY_MILLIS)
            sleeper.sleep(delay)
        }
    }

    private fun remember(captionId: String) {
        if (captionId in processedIds) return
        processedIds.addLast(captionId)
        while (processedIds.size > MAX_PROCESSED_IDS) processedIds.removeFirst()
    }

    private companion object {
        const val CURSOR_OVERLAP_SECONDS = 1.0
        const val NORMAL_POLL_MILLIS = 1_000L
        const val RETRY_BASE_MILLIS = 800L
        const val MAX_RETRY_MILLIS = 6_400L
        const val MAX_PROCESSED_IDS = 300
    }
}

/** Keeps the original immediately visible and discards a late translation after a newer caption arrives. */
class LatestCaptionTranslation(
    private val api: AuthenticatedApiClient,
    private val payload: VoipCallPayload,
    private val targetLanguage: String,
    private val presenter: CaptionPresenter,
    private val launch: (suspend () -> Unit) -> Unit,
    private val onError: suspend (Exception) -> Unit,
    private val onTranslated: (CaptionSegment) -> Unit = {},
) {
    private val lock = Any()
    private var latestCaptionId: String? = null
    private var stopped = false

    suspend fun receive(caption: CaptionSegment) {
        synchronized(lock) { if (stopped) return; latestCaptionId = caption.id }
        presenter.showOriginal(caption)
        launch {
            try {
                val translation = api.translateCaption(payload, caption.id, targetLanguage)
                if (synchronized(lock) { !stopped && latestCaptionId == caption.id }) {
                    presenter.showTranslation(caption, translation)
                    onTranslated(caption)
                }
            } catch (failure: Exception) { onError(failure) }
        }
    }

    fun stop() = synchronized(lock) { stopped = true; latestCaptionId = null }
    fun resume() = synchronized(lock) { stopped = false; latestCaptionId = null }
}

/**
 * Plays only validated server speech, serially. The queue deliberately keeps at most two
 * captions: conversational audio must never build an unbounded delayed narration backlog.
 */
class SafeTranslatedSpeechPlayback(
    private val api: AuthenticatedApiClient,
    private val payload: VoipCallPayload,
    private val player: SyntheticSpeechPlayer,
    private val ducker: RemoteAudioDucker,
    private val voice: String = "coral",
    private val launch: (suspend () -> Unit) -> Unit,
    private val onError: suspend (Exception) -> Unit,
) {
    private val lock = Any()
    private val queue = ArrayDeque<String>()
    private var running = false
    private var stopped = false
    private var generation = 0L

    fun enqueue(captionId: String) {
        if (captionId.length !in 8..80 || !captionId.all { it.isLetterOrDigit() || it == '_' || it == '-' }) return
        val shouldLaunch = synchronized(lock) {
            if (stopped || queue.contains(captionId)) return
            while (queue.size >= 2) queue.removeFirst()
            queue.addLast(captionId)
            if (running) false else { running = true; true }
        }
        if (shouldLaunch) launch { drain() }
    }

    suspend fun cancel() {
        synchronized(lock) { stopped = true; generation += 1; queue.clear(); running = false }
        try { player.stop() } finally { ducker.setDucked(false) }
    }

    fun resume() = synchronized(lock) { stopped = false }

    private suspend fun drain() {
        val myGeneration = synchronized(lock) { generation }
        while (true) {
            val captionId = synchronized(lock) {
                if (stopped || generation != myGeneration || queue.isEmpty()) {
                    running = false
                    null
                } else queue.removeFirst()
            } ?: return
            try {
                val speech = api.translatedSpeech(payload, captionId, voice)
                if (synchronized(lock) { stopped || generation != myGeneration }) continue
                ducker.setDucked(true)
                try { player.play(speech) } finally { ducker.setDucked(false) }
            } catch (failure: Exception) {
                runCatching { ducker.setDucked(false) }
                onError(failure)
            }
        }
    }
}

/** Lifecycle bridge installed as NativeCallLifecycle's optional captions feature. */
class AndroidSpeechCaptions(
    private val engine: SpeechEngineCoordinator,
    private val remote: RemoteCaptionPolling,
    private val translation: LatestCaptionTranslation,
    private val playback: SafeTranslatedSpeechPlayback,
    private val localSpeechError: suspend (Exception) -> Unit = {},
) : OptionalCaptions {
    override suspend fun start() {
        playback.resume()
        translation.resume()
        remote.start()
        try { engine.start() } catch (failure: Exception) {
            // Receiving remote captions remains useful when both local speech providers fail.
            localSpeechError(failure)
        }
    }

    override suspend fun stop() {
        remote.stop()
        translation.stop()
        try { playback.cancel() } finally { engine.stop() }
    }
}
