import Foundation

public enum NativeCallType: String, Codable, Sendable {
    case audio, video
}

public protocol CallAudioSessionControlling: AnyObject, Sendable {
    func activate(for callType: NativeCallType, speakerEnabled: Bool) async throws
    func setSpeakerEnabled(_ enabled: Bool) async throws
    func deactivate() async throws
}

#if os(iOS)
import AVFAudio

@MainActor
public final class IOSCallAudioSessionController: CallAudioSessionControlling {
    private let session: AVAudioSession
    public private(set) var isActive = false
    public private(set) var speakerEnabled = false

    public init(session: AVAudioSession = .sharedInstance()) {
        self.session = session
    }

    public func activate(for callType: NativeCallType, speakerEnabled: Bool) async throws {
        let options: AVAudioSession.CategoryOptions = [.allowBluetoothHFP]
        let mode: AVAudioSession.Mode = callType == .video ? .videoChat : .voiceChat
        try session.setCategory(.playAndRecord, mode: mode, options: options)
        try session.setPreferredSampleRate(48_000)
        try session.setPreferredIOBufferDuration(0.01)
        try session.setActive(true)
        isActive = true
        try await setSpeakerEnabled(speakerEnabled)
    }

    public func setSpeakerEnabled(_ enabled: Bool) async throws {
        guard isActive else { return }
        try session.overrideOutputAudioPort(enabled ? .speaker : .none)
        speakerEnabled = enabled
    }

    public func deactivate() async throws {
        guard isActive else { return }
        try session.overrideOutputAudioPort(.none)
        try session.setActive(false, options: [.notifyOthersOnDeactivation])
        speakerEnabled = false
        isActive = false
    }
}
#endif
