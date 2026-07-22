package com.almatchlife.core.webrtc

import android.content.Context
import org.webrtc.AudioSource
import org.webrtc.AudioTrack
import org.webrtc.Camera2Enumerator
import org.webrtc.CameraVideoCapturer
import org.webrtc.DataChannel
import org.webrtc.EglBase
import org.webrtc.IceCandidate as RtcIceCandidate
import org.webrtc.MediaConstraints
import org.webrtc.MediaStream
import org.webrtc.PeerConnection
import org.webrtc.PeerConnectionFactory
import org.webrtc.RtpReceiver
import org.webrtc.SessionDescription
import org.webrtc.SdpObserver
import org.webrtc.SurfaceTextureHelper
import org.webrtc.VideoSource
import org.webrtc.VideoTrack
import com.almatchlife.core.IceCandidate
import com.almatchlife.core.IceConfiguration
import com.almatchlife.core.NativeCallType
import com.almatchlife.core.PeerConnectionState
import com.almatchlife.core.PersonPeer
import com.almatchlife.core.PersonPeerFactory
import com.almatchlife.core.PersonTransportException
import java.util.concurrent.atomic.AtomicBoolean
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException
import kotlin.coroutines.suspendCoroutine

/** Compiled only by the Android app module after a reviewed Google WebRTC AAR is pinned. */
class GoogleWebRtcPeerFactory(
    context: Context,
    private val factory: PeerConnectionFactory,
    private val eglContext: EglBase.Context,
    private val launchCallback: (suspend () -> Unit) -> Unit,
    private val localVideo: (VideoTrack) -> Unit = {},
    private val remoteVideo: (VideoTrack) -> Unit = {},
    private val remoteAudio: (AudioTrack) -> Unit = {},
) : PersonPeerFactory {
    private val applicationContext = context.applicationContext

    override suspend fun make(configuration: IceConfiguration): PersonPeer {
        val rtcServers = configuration.servers.map { server ->
            val builder = PeerConnection.IceServer.builder(server.urls)
            server.username?.let(builder::setUsername)
            server.credential?.let(builder::setPassword)
            builder.createIceServer()
        }
        val rtcConfiguration = PeerConnection.RTCConfiguration(rtcServers).apply {
            sdpSemantics = PeerConnection.SdpSemantics.UNIFIED_PLAN
            bundlePolicy = PeerConnection.BundlePolicy.MAXBUNDLE
            rtcpMuxPolicy = PeerConnection.RtcpMuxPolicy.REQUIRE
            continualGatheringPolicy = PeerConnection.ContinualGatheringPolicy.GATHER_CONTINUALLY
            keyType = PeerConnection.KeyType.ECDSA
        }
        val adapter = GoogleWebRtcPeer(
            applicationContext, factory, eglContext, launchCallback, localVideo, remoteVideo, remoteAudio,
        )
        val peer = factory.createPeerConnection(rtcConfiguration, adapter)
            ?: throw PersonTransportException("could not create Google WebRTC peer")
        adapter.attach(peer)
        return adapter
    }
}

private class GoogleWebRtcPeer(
    private val context: Context,
    private val factory: PeerConnectionFactory,
    private val eglContext: EglBase.Context,
    private val launchCallback: (suspend () -> Unit) -> Unit,
    private val localVideo: (VideoTrack) -> Unit,
    private val remoteVideo: (VideoTrack) -> Unit,
    private val remoteAudio: (AudioTrack) -> Unit,
) : PersonPeer, PeerConnection.Observer {
    private var peer: PeerConnection? = null
    private var candidateHandler: suspend (IceCandidate) -> Unit = {}
    private var stateHandler: suspend (PeerConnectionState) -> Unit = {}
    private var audioSource: AudioSource? = null
    private var audioTrack: AudioTrack? = null
    private var videoSource: VideoSource? = null
    private var videoTrack: VideoTrack? = null
    private var capturer: CameraVideoCapturer? = null
    private var surfaceHelper: SurfaceTextureHelper? = null
    private val closed = AtomicBoolean(false)

    fun attach(value: PeerConnection) { check(peer == null); peer = value }

    override suspend fun setLocalCandidateHandler(handler: suspend (IceCandidate) -> Unit) {
        candidateHandler = handler
    }

    override suspend fun setConnectionStateHandler(handler: suspend (PeerConnectionState) -> Unit) {
        stateHandler = handler
    }

    override suspend fun addLocalMedia(callType: NativeCallType) {
        val current = peer ?: throw PersonTransportException("peer not attached")
        val audioConstraints = MediaConstraints().apply {
            mandatory.add(MediaConstraints.KeyValuePair("googEchoCancellation", "true"))
            mandatory.add(MediaConstraints.KeyValuePair("googAutoGainControl", "true"))
            mandatory.add(MediaConstraints.KeyValuePair("googNoiseSuppression", "true"))
            mandatory.add(MediaConstraints.KeyValuePair("googHighpassFilter", "true"))
        }
        val createdAudioSource = factory.createAudioSource(audioConstraints)
        val createdAudioTrack = factory.createAudioTrack("aml_audio", createdAudioSource).apply { setEnabled(true) }
        if (current.addTrack(createdAudioTrack, listOf("aml_stream")) == null) {
            createdAudioTrack.dispose(); createdAudioSource.dispose()
            throw PersonTransportException("could not add local audio")
        }
        audioSource = createdAudioSource
        audioTrack = createdAudioTrack
        if (callType == NativeCallType.VIDEO) addVideo(current)
    }

    private fun addVideo(current: PeerConnection) {
        val enumerator = Camera2Enumerator(context)
        val cameraName = enumerator.deviceNames.firstOrNull(enumerator::isFrontFacing)
            ?: throw PersonTransportException("front camera unavailable")
        val selected = enumerator.getSupportedFormats(cameraName).orEmpty()
            .filter { it.width <= 1280 && it.height <= 720 }
            .maxWithOrNull(compareBy({ it.width * it.height }, { it.framerate.max }))
            ?: throw PersonTransportException("supported camera format unavailable")
        val createdCapturer = enumerator.createCapturer(cameraName, null)
            ?: throw PersonTransportException("could not create camera capturer")
        val helper = SurfaceTextureHelper.create("AML-Camera", eglContext)
        val source = factory.createVideoSource(false)
        val track = factory.createVideoTrack("aml_video", source).apply { setEnabled(true) }
        try {
            createdCapturer.initialize(helper, context, source.capturerObserver)
            createdCapturer.startCapture(selected.width, selected.height, minOf(selected.framerate.max / 1000, 30))
            if (current.addTrack(track, listOf("aml_stream")) == null) {
                throw PersonTransportException("could not add local video")
            }
            capturer = createdCapturer
            surfaceHelper = helper
            videoSource = source
            videoTrack = track
            localVideo(track)
        } catch (failure: Exception) {
            runCatching { createdCapturer.stopCapture() }
            createdCapturer.dispose(); helper.dispose(); track.dispose(); source.dispose()
            throw failure
        }
    }

    override suspend fun setRemoteDescription(type: String, sdp: String) {
        val descriptionType = when (type) {
            "offer" -> SessionDescription.Type.OFFER
            "answer" -> SessionDescription.Type.ANSWER
            else -> throw PersonTransportException("unsupported SDP type")
        }
        awaitSdp { observer -> peerOrThrow().setRemoteDescription(observer, SessionDescription(descriptionType, sdp)) }
    }

    override suspend fun createAnswer(): String {
        val answer = suspendCoroutine<SessionDescription> { continuation ->
            val delivered = AtomicBoolean(false)
            peerOrThrow().createAnswer(object : SdpObserver {
                override fun onCreateSuccess(value: SessionDescription) {
                    if (delivered.compareAndSet(false, true)) continuation.resume(value)
                }
                override fun onCreateFailure(error: String) {
                    if (delivered.compareAndSet(false, true)) continuation.resumeWithException(PersonTransportException(error))
                }
                override fun onSetSuccess() = Unit
                override fun onSetFailure(error: String) = Unit
            }, MediaConstraints())
        }
        awaitSdp { observer -> peerOrThrow().setLocalDescription(observer, answer) }
        return answer.description
    }

    override suspend fun addRemoteCandidate(candidate: IceCandidate) {
        val accepted = peerOrThrow().addIceCandidate(
            RtcIceCandidate(candidate.sdpMid, candidate.sdpMLineIndex ?: 0, candidate.candidate),
        )
        if (!accepted) throw PersonTransportException("remote ICE candidate rejected")
    }

    override suspend fun close() {
        if (!closed.compareAndSet(false, true)) return
        candidateHandler = {}
        stateHandler = {}
        runCatching { capturer?.stopCapture() }
        capturer?.dispose(); capturer = null
        surfaceHelper?.dispose(); surfaceHelper = null
        videoTrack?.dispose(); videoTrack = null
        videoSource?.dispose(); videoSource = null
        audioTrack?.dispose(); audioTrack = null
        audioSource?.dispose(); audioSource = null
        peer?.close(); peer?.dispose(); peer = null
    }

    private suspend fun awaitSdp(operation: (SdpObserver) -> Unit) = suspendCoroutine<Unit> { continuation ->
        val delivered = AtomicBoolean(false)
        operation(object : SdpObserver {
            override fun onSetSuccess() { if (delivered.compareAndSet(false, true)) continuation.resume(Unit) }
            override fun onSetFailure(error: String) {
                if (delivered.compareAndSet(false, true)) continuation.resumeWithException(PersonTransportException(error))
            }
            override fun onCreateSuccess(value: SessionDescription) = Unit
            override fun onCreateFailure(error: String) = Unit
        })
    }

    private fun peerOrThrow(): PeerConnection = peer ?: throw PersonTransportException("peer closed")
    override fun onIceCandidate(value: RtcIceCandidate) = launchCallback {
        candidateHandler(IceCandidate(value.sdp, value.sdpMid, value.sdpMLineIndex, null))
    }
    override fun onConnectionChange(value: PeerConnection.PeerConnectionState) = launchCallback {
        stateHandler(when (value) {
            PeerConnection.PeerConnectionState.NEW -> PeerConnectionState.NEW
            PeerConnection.PeerConnectionState.CONNECTING -> PeerConnectionState.CONNECTING
            PeerConnection.PeerConnectionState.CONNECTED -> PeerConnectionState.CONNECTED
            PeerConnection.PeerConnectionState.DISCONNECTED -> PeerConnectionState.DISCONNECTED
            PeerConnection.PeerConnectionState.FAILED -> PeerConnectionState.FAILED
            PeerConnection.PeerConnectionState.CLOSED -> PeerConnectionState.CLOSED
        })
    }
    override fun onAddTrack(receiver: RtpReceiver, streams: Array<out MediaStream>) {
        when (val track = receiver.track()) {
            is VideoTrack -> remoteVideo(track)
            is AudioTrack -> remoteAudio(track)
        }
    }
    override fun onSignalingChange(value: PeerConnection.SignalingState) = Unit
    override fun onIceConnectionChange(value: PeerConnection.IceConnectionState) = Unit
    override fun onIceConnectionReceivingChange(value: Boolean) = Unit
    override fun onIceGatheringChange(value: PeerConnection.IceGatheringState) = Unit
    override fun onIceCandidatesRemoved(values: Array<out RtcIceCandidate>) = Unit
    override fun onAddStream(stream: MediaStream) = Unit
    override fun onRemoveStream(stream: MediaStream) = Unit
    override fun onDataChannel(channel: DataChannel) = Unit
    override fun onRenegotiationNeeded() = Unit
}
