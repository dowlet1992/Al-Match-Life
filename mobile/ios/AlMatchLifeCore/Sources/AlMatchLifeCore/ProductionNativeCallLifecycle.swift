import Foundation

public enum NativeSignalType: String, Sendable { case accepted, declined, ended }

public protocol NativeCallSignaling: Sendable {
    func send(type: NativeSignalType, eventID: String, payload: VoIPCallPayload, reason: String?) async throws
}

public protocol PersonCallMediaTransport: Sendable {
    func start(_ payload: VoIPCallPayload) async throws
    func stop() async
}

public protocol CallCaptionLifecycle: Sendable {
    func start() async throws
    func stop() async throws
}

extension SpeechEngineCoordinator: CallCaptionLifecycle {}

public actor ProductionNativeCallLifecycle: NativeCallLifecycle {
    public typealias OptionalFeatureErrorHandler = @Sendable (Error) async -> Void
    private let signaling: any NativeCallSignaling
    private let audio: any CallAudioSessionControlling
    private let media: any PersonCallMediaTransport
    private let captions: any CallCaptionLifecycle
    private let optionalFeatureError: OptionalFeatureErrorHandler
    private var mediaActive = false

    public init(
        signaling: any NativeCallSignaling,
        audio: any CallAudioSessionControlling,
        media: any PersonCallMediaTransport,
        captions: any CallCaptionLifecycle,
        optionalFeatureError: @escaping OptionalFeatureErrorHandler
    ) {
        self.signaling = signaling
        self.audio = audio
        self.media = media
        self.captions = captions
        self.optionalFeatureError = optionalFeatureError
    }

    public func accept(_ payload: VoIPCallPayload) async throws {
        if mediaActive { return }
        try await signaling.send(type: .accepted, eventID: Self.eventID(), payload: payload, reason: nil)
        do {
            try await audio.activate(for: payload.callType, speakerEnabled: payload.callType == .video)
            try await media.start(payload)
            mediaActive = true
        } catch {
            await rollbackAfterAccept(payload)
            throw error
        }
        do {
            try await captions.start()
        } catch {
            await optionalFeatureError(error)
        }
    }

    public func decline(_ payload: VoIPCallPayload) async {
        try? await signaling.send(type: .declined, eventID: Self.eventID(), payload: payload, reason: nil)
    }

    public func end(_ payload: VoIPCallPayload) async {
        try? await signaling.send(type: .ended, eventID: Self.eventID(), payload: payload, reason: nil)
    }

    public func connectionLost(_ payload: VoIPCallPayload) async {
        try? await signaling.send(
            type: .ended, eventID: Self.eventID(), payload: payload, reason: "connection_lost"
        )
    }

    public func stop(_ payload: VoIPCallPayload) async {
        try? await captions.stop()
        await media.stop()
        try? await audio.deactivate()
        mediaActive = false
    }

    private func rollbackAfterAccept(_ payload: VoIPCallPayload) async {
        try? await captions.stop()
        await media.stop()
        try? await audio.deactivate()
        mediaActive = false
        try? await signaling.send(type: .ended, eventID: Self.eventID(), payload: payload, reason: nil)
    }

    private static func eventID() -> String {
        "ios_" + UUID().uuidString.lowercased()
    }
}

extension AuthenticatedAPIClient: NativeCallSignaling {
    public func send(
        type: NativeSignalType, eventID: String, payload: VoIPCallPayload, reason: String?
    ) async throws {
        var signalPayload = ["call_type": payload.callType.rawValue]
        if reason == "connection_lost" { signalPayload["reason"] = reason }
        _ = try await sendCallSignal(
            callID: payload.callID, otherEmail: payload.callerEmail, callType: payload.callType,
            type: type.rawValue, eventID: eventID, payload: signalPayload
        )
    }
}
