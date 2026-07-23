package com.almatchlife.core

import java.util.UUID

data class IceServer(val urls: List<String>, val username: String?, val credential: String?)
data class IceConfiguration(val servers: List<IceServer>, val provider: String, val expiresAt: Double)
data class IceCandidate(
    val candidate: String,
    val sdpMid: String?,
    val sdpMLineIndex: Int?,
    val usernameFragment: String?,
)
data class SignalPayload(
    val sdp: String? = null,
    val candidate: String? = null,
    val sdpMid: String? = null,
    val sdpMLineIndex: Int? = null,
    val usernameFragment: String? = null,
)
data class CallSignal(val id: String, val type: String, val payload: SignalPayload)
data class SignalPoll(val status: String, val messages: List<CallSignal>, val serverTime: Double)

enum class PeerConnectionState { NEW, CONNECTING, CONNECTED, DISCONNECTED, FAILED, CLOSED }
sealed interface RecoveryStatus {
    object Connected : RecoveryStatus
    object WaitingForNetwork : RecoveryStatus
    object Failed : RecoveryStatus
    data class Reconnecting(val attempt: Int, val maximum: Int) : RecoveryStatus
}

class PersonTransportException(message: String) : RuntimeException(message)

interface PersonPeer {
    suspend fun setLocalCandidateHandler(handler: suspend (IceCandidate) -> Unit)
    suspend fun setConnectionStateHandler(handler: suspend (PeerConnectionState) -> Unit)
    suspend fun addLocalMedia(callType: NativeCallType)
    suspend fun setRemoteDescription(type: String, sdp: String)
    suspend fun createAnswer(): String
    suspend fun addRemoteCandidate(candidate: IceCandidate)
    suspend fun close()
}

interface PersonPeerFactory { suspend fun make(configuration: IceConfiguration): PersonPeer }

interface PersonCallSignaling {
    suspend fun ice(payload: VoipCallPayload): IceConfiguration
    suspend fun poll(payload: VoipCallPayload, after: Double): SignalPoll
    suspend fun sendDescription(payload: VoipCallPayload, type: String, sdp: String, eventId: String)
    suspend fun sendCandidate(payload: VoipCallPayload, candidate: IceCandidate, eventId: String)
    suspend fun acknowledge(payload: VoipCallPayload, eventIds: List<String>)
}

interface NetworkStatus { suspend fun isOnline(): Boolean }
interface TaskSleeper { suspend fun sleep(milliseconds: Long) }
interface CancellationProbe { val isCancelled: Boolean }
interface BackgroundTask { fun cancel() }
interface BackgroundTaskLauncher {
    fun launch(block: suspend (CancellationProbe) -> Unit): BackgroundTask
}

class IncomingPersonWebRtcTransport(
    private val factory: PersonPeerFactory,
    private val signaling: PersonCallSignaling,
    private val network: NetworkStatus,
    private val sleeper: TaskSleeper,
    private val launcher: BackgroundTaskLauncher,
    private val recoveryStatus: suspend (RecoveryStatus) -> Unit = {},
    private val failureHandler: suspend (VoipCallPayload, Exception) -> Unit = { _, _ -> },
) : PersonMedia {
    private val lock = Any()
    private var peer: PersonPeer? = null
    private var payload: VoipCallPayload? = null
    private var pollTask: BackgroundTask? = null
    private var recoveryTask: BackgroundTask? = null
    private var generation = 0L
    private var connectionState = PeerConnectionState.NEW
    private var recoveryAttempts = 0
    private var watermark = 0.0
    private val processedIds = ArrayDeque<String>()
    private val pendingAckIds = ArrayDeque<String>()
    private val pendingLocalCandidates = ArrayDeque<IceCandidate>()
    private var localDescriptionPublished = false

    override suspend fun start(payload: VoipCallPayload) {
        synchronized(lock) { if (peer != null) throw PersonTransportException("already running") }
        val configuration = signaling.ice(payload) // TURN must exist before peer construction.
        val candidate = factory.make(configuration)
        try {
            candidate.setLocalCandidateHandler { publishLocalCandidate(it) }
            candidate.setConnectionStateHandler { connectionChanged(it) }
            candidate.addLocalMedia(payload.callType)
            val currentGeneration = synchronized(lock) {
                if (peer != null) throw PersonTransportException("already running")
                generation += 1
                peer = candidate
                this.payload = payload
                generation
            }
            val task = launcher.launch { cancellation -> pollLoop(currentGeneration, cancellation) }
            synchronized(lock) {
                if (generation == currentGeneration && peer === candidate) pollTask = task else task.cancel()
            }
        } catch (failure: Exception) {
            candidate.close()
            throw failure
        }
    }

    override suspend fun stop() {
        val snapshot = synchronized(lock) {
            generation += 1
            val value = Triple(peer, pollTask, recoveryTask)
            peer = null
            payload = null
            pollTask = null
            recoveryTask = null
            connectionState = PeerConnectionState.CLOSED
            recoveryAttempts = 0
            watermark = 0.0
            localDescriptionPublished = false
            processedIds.clear()
            pendingAckIds.clear()
            pendingLocalCandidates.clear()
            value
        }
        snapshot.second?.cancel()
        snapshot.third?.cancel()
        snapshot.first?.setLocalCandidateHandler {}
        snapshot.first?.setConnectionStateHandler {}
        snapshot.first?.close()
    }

    private suspend fun pollLoop(runGeneration: Long, cancellation: CancellationProbe) {
        var consecutiveFailures = 0
        while (!cancellation.isCancelled && isCurrent(runGeneration)) {
            val currentPayload = synchronized(lock) { payload } ?: return
            try {
                val after = synchronized(lock) { watermark }
                val result = signaling.poll(currentPayload, after)
                if (result.status in setOf("declined", "ended", "missed")) { stop(); return }
                for (message in result.messages) {
                    if (synchronized(lock) { message.id in processedIds }) continue
                    process(message)
                    synchronized(lock) {
                        rememberProcessed(message.id)
                        if (message.id !in pendingAckIds) pendingAckIds.addLast(message.id)
                    }
                }
                flushLocalCandidatesIfReady()
                val ackBatch = synchronized(lock) { pendingAckIds.take(50) }
                if (ackBatch.isNotEmpty()) {
                    signaling.acknowledge(currentPayload, ackBatch)
                    synchronized(lock) {
                        ackBatch.forEach { acknowledged ->
                            if (pendingAckIds.firstOrNull() == acknowledged) pendingAckIds.removeFirst()
                            else pendingAckIds.remove(acknowledged)
                        }
                    }
                }
                synchronized(lock) { watermark = maxOf(watermark, result.serverTime - 1.0) }
                consecutiveFailures = 0
            } catch (terminal: PersonTransportException) {
                if (terminal.message?.startsWith("terminal:") == true) { stop(); return }
                consecutiveFailures += 1
            } catch (_: Exception) {
                consecutiveFailures += 1
            }
            val delay = minOf(800L * (1L shl minOf(consecutiveFailures, 3)), 6_400L)
            sleeper.sleep(delay)
        }
    }

    private suspend fun process(message: CallSignal) {
        val currentPeer = synchronized(lock) { peer } ?: return
        when (message.type) {
            "offer" -> {
                val sdp = message.payload.sdp ?: throw PersonTransportException("missing offer SDP")
                currentPeer.setRemoteDescription("offer", sdp)
                val answer = currentPeer.createAnswer()
                val currentPayload = synchronized(lock) { payload } ?: return
                signaling.sendDescription(currentPayload, "answer", answer, eventId("answer"))
                synchronized(lock) { localDescriptionPublished = true }
                flushLocalCandidatesIfReady()
            }
            "answer" -> currentPeer.setRemoteDescription(
                "answer", message.payload.sdp ?: throw PersonTransportException("missing answer SDP"),
            )
            "ice" -> message.payload.candidate?.let {
                currentPeer.addRemoteCandidate(
                    IceCandidate(it, message.payload.sdpMid, message.payload.sdpMLineIndex, message.payload.usernameFragment),
                )
            }
            "declined", "ended", "missed" -> throw PersonTransportException("terminal:${message.type}")
        }
    }

    private suspend fun publishLocalCandidate(candidate: IceCandidate) {
        val current = synchronized(lock) {
            val currentPayload = payload
            if (!localDescriptionPublished || currentPayload == null) {
                enqueueCandidate(candidate)
                null
            } else currentPayload
        } ?: return
        try {
            signaling.sendCandidate(current, candidate, eventId("ice"))
        } catch (_: Exception) {
            synchronized(lock) { enqueueCandidate(candidate) }
        }
    }

    private suspend fun flushLocalCandidatesIfReady() {
        val snapshot = synchronized(lock) {
            if (!localDescriptionPublished || payload == null || pendingLocalCandidates.isEmpty()) null
            else payload!! to pendingLocalCandidates.toList().also { pendingLocalCandidates.clear() }
        } ?: return
        snapshot.second.forEachIndexed { index, candidate ->
            try {
                signaling.sendCandidate(snapshot.first, candidate, eventId("ice"))
            } catch (failure: Exception) {
                synchronized(lock) {
                    snapshot.second.drop(index).asReversed().forEach { pendingLocalCandidates.addFirst(it) }
                    while (pendingLocalCandidates.size > 128) pendingLocalCandidates.removeFirst()
                }
                throw failure
            }
        }
    }

    private suspend fun connectionChanged(state: PeerConnectionState) {
        synchronized(lock) { connectionState = state }
        when (state) {
            PeerConnectionState.CONNECTED -> {
                val task = synchronized(lock) {
                    recoveryAttempts = 0
                    recoveryTask.also { recoveryTask = null }
                }
                task?.cancel()
                recoveryStatus(RecoveryStatus.Connected)
            }
            PeerConnectionState.DISCONNECTED, PeerConnectionState.FAILED -> startRecoveryWatch()
            PeerConnectionState.CLOSED -> if (synchronized(lock) { peer != null }) recoveryExhausted()
            else -> Unit
        }
    }

    private suspend fun startRecoveryWatch() {
        recoveryStatus(RecoveryStatus.Reconnecting(synchronized(lock) { recoveryAttempts }, 3))
        val currentGeneration = synchronized(lock) {
            if (recoveryTask != null || peer == null) return
            generation
        }
        val task = launcher.launch { cancellation -> recoveryLoop(currentGeneration, cancellation) }
        synchronized(lock) {
            if (generation == currentGeneration && recoveryTask == null) recoveryTask = task else task.cancel()
        }
    }

    private suspend fun recoveryLoop(runGeneration: Long, cancellation: CancellationProbe) {
        var delay = 5_000L
        while (!cancellation.isCancelled && isCurrent(runGeneration)) {
            sleeper.sleep(delay)
            if (cancellation.isCancelled || !isCurrent(runGeneration)) return
            if (!network.isOnline()) {
                recoveryStatus(RecoveryStatus.WaitingForNetwork)
                delay = 1_000L
                continue
            }
            if (synchronized(lock) { connectionState == PeerConnectionState.CONNECTED }) return
            val attempt = synchronized(lock) { ++recoveryAttempts }
            recoveryStatus(RecoveryStatus.Reconnecting(attempt, 3))
            if (attempt >= 3) { recoveryExhausted(); return }
            delay = minOf(5_000L * (attempt + 1), 10_000L)
        }
    }

    private suspend fun recoveryExhausted() {
        synchronized(lock) { recoveryTask = null }
        recoveryStatus(RecoveryStatus.Failed)
        val failedPayload = synchronized(lock) { payload }
        if (failedPayload != null) {
            failureHandler(failedPayload, PersonTransportException("recovery exhausted"))
        }
        stop()
    }

    private fun isCurrent(value: Long): Boolean = synchronized(lock) { generation == value && peer != null }
    private fun enqueueCandidate(value: IceCandidate) {
        pendingLocalCandidates.addLast(value)
        while (pendingLocalCandidates.size > 128) pendingLocalCandidates.removeFirst()
    }
    private fun rememberProcessed(value: String) {
        processedIds.addLast(value)
        while (processedIds.size > 600) processedIds.removeFirst()
    }
    private fun eventId(type: String) = "android_${type}_${UUID.randomUUID().toString().lowercase()}"
}
