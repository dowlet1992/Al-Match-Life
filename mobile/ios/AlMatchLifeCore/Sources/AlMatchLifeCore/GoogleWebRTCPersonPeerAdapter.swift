#if canImport(WebRTC) && os(iOS)
import AVFoundation
import Foundation
@preconcurrency import WebRTC

public enum GoogleWebRTCAdapterError: Error, Sendable {
    case peerCreationFailed, localMediaFailed, cameraUnavailable, cameraFormatUnavailable
    case invalidDescriptionType, operationFailed(String)
}

public final class GoogleWebRTCPersonPeerFactory: PersonPeerConnectionFactory, @unchecked Sendable {
    private let factory: RTCPeerConnectionFactory
    private let remoteMedia: any RemoteMediaTrackReceiving

    public init(remoteMedia: any RemoteMediaTrackReceiving) {
        RTCInitializeSSL()
        self.factory = RTCPeerConnectionFactory(
            encoderFactory: RTCDefaultVideoEncoderFactory(),
            decoderFactory: RTCDefaultVideoDecoderFactory()
        )
        self.remoteMedia = remoteMedia
    }

    public func make(configuration: NativeICEConfiguration) async throws -> any PersonPeerConnection {
        let rtcConfiguration = RTCConfiguration()
        rtcConfiguration.sdpSemantics = .unifiedPlan
        rtcConfiguration.continualGatheringPolicy = .gatherContinually
        rtcConfiguration.bundlePolicy = .maxBundle
        rtcConfiguration.rtcpMuxPolicy = .require
        rtcConfiguration.iceServers = configuration.iceServers.map {
            RTCIceServer(urlStrings: $0.urls, username: $0.username ?? "", credential: $0.credential ?? "")
        }
        let constraints = RTCMediaConstraints(
            mandatoryConstraints: nil,
            optionalConstraints: ["DtlsSrtpKeyAgreement": "true"]
        )
        let adapter = GoogleWebRTCPersonPeerAdapter(factory: factory, remoteMedia: remoteMedia)
        guard let peer = factory.peerConnection(with: rtcConfiguration, constraints: constraints, delegate: adapter) else {
            throw GoogleWebRTCAdapterError.peerCreationFailed
        }
        adapter.install(peer: peer)
        return adapter
    }
}

private final class GoogleWebRTCPersonPeerAdapter: NSObject, PersonPeerConnection, RTCPeerConnectionDelegate, @unchecked Sendable {
    private let lock = NSLock()
    private let factory: RTCPeerConnectionFactory
    private let remoteMedia: any RemoteMediaTrackReceiving
    private var peer: RTCPeerConnection?
    private var candidateHandler: (@Sendable (NativeICECandidate) -> Void)?
    private var connectionStateHandler: (@Sendable (PersonPeerConnectionState) -> Void)?
    private var cameraCapturer: RTCCameraVideoCapturer?
    private var localAudioTrack: RTCAudioTrack?
    private var localVideoTrack: RTCVideoTrack?

    init(factory: RTCPeerConnectionFactory, remoteMedia: any RemoteMediaTrackReceiving) {
        self.factory = factory
        self.remoteMedia = remoteMedia
    }

    func install(peer: RTCPeerConnection) { lock.withLock { self.peer = peer } }

    func setLocalCandidateHandler(_ handler: @escaping @Sendable (NativeICECandidate) -> Void) async {
        lock.withLock { candidateHandler = handler }
    }

    func setConnectionStateHandler(_ handler: @escaping @Sendable (PersonPeerConnectionState) -> Void) async {
        lock.withLock { connectionStateHandler = handler }
    }

    func addLocalMedia(callType: NativeCallType) async throws {
        guard let peer = lock.withLock({ self.peer }) else { throw GoogleWebRTCAdapterError.peerCreationFailed }
        let audioSource = factory.audioSource(with: RTCMediaConstraints(mandatoryConstraints: [
            "googEchoCancellation": "true", "googAutoGainControl": "true", "googNoiseSuppression": "true",
        ], optionalConstraints: nil))
        let audioTrack = factory.audioTrack(with: audioSource, trackId: "aml-audio")
        guard peer.add(audioTrack, streamIds: ["aml-stream"]) != nil else { throw GoogleWebRTCAdapterError.localMediaFailed }
        lock.withLock { localAudioTrack = audioTrack }
        guard callType == .video else { return }

        let videoSource = factory.videoSource()
        let capturer = RTCCameraVideoCapturer(delegate: videoSource)
        let videoTrack = factory.videoTrack(with: videoSource, trackId: "aml-video")
        guard peer.add(videoTrack, streamIds: ["aml-stream"]) != nil else { throw GoogleWebRTCAdapterError.localMediaFailed }
        try await startFrontCamera(capturer)
        lock.withLock { cameraCapturer = capturer; localVideoTrack = videoTrack }
        await remoteMedia.receiveLocalVideoTrack(videoTrack)
    }

    func setRemoteDescription(type: String, sdp: String) async throws {
        let descriptionType: RTCSdpType
        switch type { case "offer": descriptionType = .offer; case "answer": descriptionType = .answer
        default: throw GoogleWebRTCAdapterError.invalidDescriptionType }
        guard let peer = lock.withLock({ self.peer }) else { throw GoogleWebRTCAdapterError.peerCreationFailed }
        try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
            peer.setRemoteDescription(RTCSessionDescription(type: descriptionType, sdp: sdp)) { error in
                if let error { continuation.resume(throwing: error) } else { continuation.resume() }
            }
        }
    }

    func createAnswer() async throws -> String {
        guard let peer = lock.withLock({ self.peer }) else { throw GoogleWebRTCAdapterError.peerCreationFailed }
        let constraints = RTCMediaConstraints(mandatoryConstraints: nil, optionalConstraints: nil)
        let answer = try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<RTCSessionDescription, Error>) in
            peer.answer(for: constraints) { description, error in
                if let error { continuation.resume(throwing: error) }
                else if let description { continuation.resume(returning: description) }
                else { continuation.resume(throwing: GoogleWebRTCAdapterError.operationFailed("empty_answer")) }
            }
        }
        try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
            peer.setLocalDescription(answer) { error in
                if let error { continuation.resume(throwing: error) } else { continuation.resume() }
            }
        }
        return answer.sdp
    }

    func addRemoteCandidate(_ candidate: NativeICECandidate) async throws {
        guard let peer = lock.withLock({ self.peer }) else { throw GoogleWebRTCAdapterError.peerCreationFailed }
        let value = RTCIceCandidate(
            sdp: candidate.candidate, sdpMLineIndex: Int32(candidate.sdpMLineIndex ?? 0), sdpMid: candidate.sdpMid
        )
        try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
            peer.add(value) { error in
                if let error { continuation.resume(throwing: error) } else { continuation.resume() }
            }
        }
    }

    func close() async {
        let values = lock.withLock { () -> (RTCPeerConnection?, RTCCameraVideoCapturer?) in
            let values = (peer, cameraCapturer)
            peer = nil; cameraCapturer = nil; localAudioTrack = nil; localVideoTrack = nil
            candidateHandler = nil; connectionStateHandler = nil
            return values
        }
        if let capturer = values.1 {
            await withCheckedContinuation { continuation in capturer.stopCapture { continuation.resume() } }
        }
        values.0?.close()
    }

    private func startFrontCamera(_ capturer: RTCCameraVideoCapturer) async throws {
        let devices = RTCCameraVideoCapturer.captureDevices()
        guard let device = devices.first(where: { $0.position == .front }) ?? devices.first else {
            throw GoogleWebRTCAdapterError.cameraUnavailable
        }
        let formats = RTCCameraVideoCapturer.supportedFormats(for: device)
        let bounded = formats.filter {
            let size = CMVideoFormatDescriptionGetDimensions($0.formatDescription)
            return size.width <= 1280 && size.height <= 720
        }
        guard let format = (bounded.isEmpty ? formats : bounded).max(by: {
            let left = CMVideoFormatDescriptionGetDimensions($0.formatDescription)
            let right = CMVideoFormatDescriptionGetDimensions($1.formatDescription)
            return left.width * left.height < right.width * right.height
        }) else { throw GoogleWebRTCAdapterError.cameraFormatUnavailable }
        let maxFPS = format.videoSupportedFrameRateRanges.map(\.maxFrameRate).max() ?? 30
        let fps = min(Int(maxFPS), 30)
        try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
            capturer.startCapture(with: device, format: format, fps: fps) { error in
                if let error { continuation.resume(throwing: error) } else { continuation.resume() }
            }
        }
    }

    func peerConnection(_ peerConnection: RTCPeerConnection, didGenerate candidate: RTCIceCandidate) {
        let handler = lock.withLock { candidateHandler }
        handler?(.init(candidate: candidate.sdp, sdpMid: candidate.sdpMid,
                       sdpMLineIndex: Int(candidate.sdpMLineIndex), usernameFragment: nil))
    }

    func peerConnection(_ peerConnection: RTCPeerConnection, didAdd stream: RTCMediaStream) {
        if let video = stream.videoTracks.first { Task { await remoteMedia.receiveRemoteVideoTrack(video) } }
        if !stream.audioTracks.isEmpty { Task { await remoteMedia.remoteAudioAvailable() } }
    }


    func peerConnection(_ peerConnection: RTCPeerConnection, didStartReceivingOn transceiver: RTCRtpTransceiver) {
        if let video = transceiver.receiver.track as? RTCVideoTrack {
            Task { await remoteMedia.receiveRemoteVideoTrack(video) }
        } else if transceiver.receiver.track is RTCAudioTrack {
            Task { await remoteMedia.remoteAudioAvailable() }
        }
    }

    func peerConnection(_ peerConnection: RTCPeerConnection, didRemove stream: RTCMediaStream) {}
    func peerConnectionShouldNegotiate(_ peerConnection: RTCPeerConnection) {}
    func peerConnection(_ peerConnection: RTCPeerConnection, didChange stateChanged: RTCSignalingState) {}
    func peerConnection(_ peerConnection: RTCPeerConnection, didChange newState: RTCIceConnectionState) {
        let mapped: PersonPeerConnectionState = switch newState {
        case .new: .new
        case .checking: .connecting
        case .connected, .completed: .connected
        case .disconnected: .disconnected
        case .failed: .failed
        case .closed: .closed
        case .count: .failed
        @unknown default: .failed
        }
        lock.withLock { connectionStateHandler }?(mapped)
    }
    func peerConnection(_ peerConnection: RTCPeerConnection, didChange newState: RTCIceGatheringState) {}
    func peerConnection(_ peerConnection: RTCPeerConnection, didOpen dataChannel: RTCDataChannel) {}
}
#endif
