package com.almatchlife.core.webrtc

import com.almatchlife.core.RealtimePeer
import com.almatchlife.core.RealtimePeerFactory
import com.almatchlife.core.RealtimeSpeechException
import org.webrtc.AudioTrack
import org.webrtc.DataChannel
import org.webrtc.IceCandidate
import org.webrtc.MediaConstraints
import org.webrtc.MediaStream
import org.webrtc.PeerConnection
import org.webrtc.PeerConnectionFactory
import org.webrtc.RtpReceiver
import org.webrtc.SdpObserver
import org.webrtc.SessionDescription
import java.nio.ByteBuffer
import java.util.concurrent.atomic.AtomicBoolean
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException
import kotlin.coroutines.suspendCoroutine

/**
 * A call-media owner supplies a distinct track handle so this adapter never captures the
 * microphone itself or mutates the person-to-person peer's sender.
 */
interface ClonedMicrophoneTrack {
    val track: AudioTrack
    fun release()
}

interface ClonedMicrophoneTrackProvider {
    fun acquire(): ClonedMicrophoneTrack
}

/** Compiled only after the application pins and audits a Google WebRTC AAR. */
class GoogleRealtimeSpeechPeerFactory(
    private val factory: PeerConnectionFactory,
    private val microphone: ClonedMicrophoneTrackProvider,
    private val launchCallback: (suspend () -> Unit) -> Unit,
) : RealtimePeerFactory {
    override suspend fun create(): RealtimePeer {
        val adapter = GoogleRealtimeSpeechPeer(microphone, launchCallback)
        val configuration = PeerConnection.RTCConfiguration(emptyList()).apply {
            sdpSemantics = PeerConnection.SdpSemantics.UNIFIED_PLAN
            bundlePolicy = PeerConnection.BundlePolicy.MAXBUNDLE
            rtcpMuxPolicy = PeerConnection.RtcpMuxPolicy.REQUIRE
            continualGatheringPolicy = PeerConnection.ContinualGatheringPolicy.GATHER_CONTINUALLY
            keyType = PeerConnection.KeyType.ECDSA
        }
        val peer = factory.createPeerConnection(configuration, adapter)
            ?: throw RealtimeSpeechException.InvalidSdp()
        adapter.attach(peer)
        return adapter
    }
}

private class GoogleRealtimeSpeechPeer(
    private val microphone: ClonedMicrophoneTrackProvider,
    private val launchCallback: (suspend () -> Unit) -> Unit,
) : RealtimePeer, PeerConnection.Observer {
    private val closed = AtomicBoolean(false)
    private var peer: PeerConnection? = null
    private var microphoneHandle: ClonedMicrophoneTrack? = null
    private var events: DataChannel? = null
    private var eventHandler: suspend (ByteArray) -> Unit = {}

    fun attach(value: PeerConnection) {
        check(peer == null)
        peer = value
        attachDataChannel(value.createDataChannel(EVENTS_CHANNEL, DataChannel.Init()))
    }

    override suspend fun setEventHandler(handler: suspend (ByteArray) -> Unit) {
        eventHandler = handler
    }

    override suspend fun addClonedMicrophoneTrack() {
        check(!closed.get()) { "realtime peer is closed" }
        check(microphoneHandle == null) { "microphone track already added" }
        val handle = microphone.acquire()
        try {
            handle.track.setEnabled(true)
            if (peerOrThrow().addTrack(handle.track, listOf(REALTIME_STREAM)) == null) {
                throw RealtimeSpeechException.InvalidSdp()
            }
            microphoneHandle = handle
        } catch (failure: Exception) {
            handle.release()
            throw failure
        }
    }

    override suspend fun createOffer(): String {
        check(microphoneHandle != null) { "microphone track must be added before offer" }
        val offer = awaitCreateOffer()
        awaitSetDescription { observer -> peerOrThrow().setLocalDescription(observer, offer) }
        return offer.description
    }

    override suspend fun setRemoteAnswer(sdp: String) {
        if (!sdp.startsWith("v=0") || sdp.toByteArray().size > MAX_SDP_BYTES) {
            throw RealtimeSpeechException.InvalidSdp()
        }
        awaitSetDescription { observer ->
            peerOrThrow().setRemoteDescription(observer, SessionDescription(SessionDescription.Type.ANSWER, sdp))
        }
    }

    override suspend fun close() {
        if (!closed.compareAndSet(false, true)) return
        eventHandler = {}
        events?.unregisterObserver()
        events?.close()
        events?.dispose()
        events = null
        microphoneHandle?.release()
        microphoneHandle = null
        peer?.close()
        peer?.dispose()
        peer = null
    }

    private fun attachDataChannel(channel: DataChannel?) {
        if (channel == null || closed.get()) {
            channel?.dispose()
            return
        }
        if (events != null && events !== channel) {
            channel.close()
            channel.dispose()
            return
        }
        events = channel
        channel.registerObserver(object : DataChannel.Observer {
            override fun onBufferedAmountChange(previousAmount: Long) = Unit
            override fun onStateChange() = Unit
            override fun onMessage(buffer: DataChannel.Buffer) {
                if (buffer.binary || closed.get()) return
                val view = buffer.data.slice()
                if (view.remaining() !in 1..MAX_EVENT_BYTES) return
                val bytes = ByteArray(view.remaining())
                view.get(bytes)
                launchCallback { eventHandler(bytes) }
            }
        })
    }

    private suspend fun awaitCreateOffer(): SessionDescription = suspendCoroutine { continuation ->
        val delivered = AtomicBoolean(false)
        peerOrThrow().createOffer(object : SdpObserver {
            override fun onCreateSuccess(value: SessionDescription) {
                if (delivered.compareAndSet(false, true)) continuation.resume(value)
            }
            override fun onCreateFailure(error: String) {
                if (delivered.compareAndSet(false, true)) {
                    continuation.resumeWithException(RealtimeSpeechException.InvalidSdp())
                }
            }
            override fun onSetSuccess() = Unit
            override fun onSetFailure(error: String) = Unit
        }, MediaConstraints())
    }

    private suspend fun awaitSetDescription(operation: (SdpObserver) -> Unit) =
        suspendCoroutine<Unit> { continuation ->
            val delivered = AtomicBoolean(false)
            operation(object : SdpObserver {
                override fun onSetSuccess() {
                    if (delivered.compareAndSet(false, true)) continuation.resume(Unit)
                }
                override fun onSetFailure(error: String) {
                    if (delivered.compareAndSet(false, true)) {
                        continuation.resumeWithException(RealtimeSpeechException.InvalidSdp())
                    }
                }
                override fun onCreateSuccess(value: SessionDescription) = Unit
                override fun onCreateFailure(error: String) = Unit
            })
        }

    private fun peerOrThrow(): PeerConnection = peer ?: throw IllegalStateException("realtime peer is closed")

    override fun onDataChannel(channel: DataChannel) = attachDataChannel(channel)
    override fun onSignalingChange(value: PeerConnection.SignalingState) = Unit
    override fun onIceConnectionChange(value: PeerConnection.IceConnectionState) = Unit
    override fun onIceConnectionReceivingChange(value: Boolean) = Unit
    override fun onIceGatheringChange(value: PeerConnection.IceGatheringState) = Unit
    override fun onIceCandidate(value: IceCandidate) = Unit
    override fun onIceCandidatesRemoved(values: Array<out IceCandidate>) = Unit
    override fun onAddStream(stream: MediaStream) = Unit
    override fun onRemoveStream(stream: MediaStream) = Unit
    override fun onRenegotiationNeeded() = Unit
    override fun onAddTrack(receiver: RtpReceiver, streams: Array<out MediaStream>) = Unit
    override fun onConnectionChange(value: PeerConnection.PeerConnectionState) = Unit

    private companion object {
        const val EVENTS_CHANNEL = "oai-events"
        const val REALTIME_STREAM = "aml_realtime_transcription"
        const val MAX_SDP_BYTES = 64 * 1024
        const val MAX_EVENT_BYTES = 64 * 1024
    }
}
