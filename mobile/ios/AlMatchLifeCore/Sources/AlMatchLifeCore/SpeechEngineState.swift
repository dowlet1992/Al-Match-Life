import Foundation

public enum SpeechEngineState: String, Codable, Sendable, CaseIterable {
    case idle, connecting, streaming, fallback, stopping, stopped, failed

    private static let transitions: [SpeechEngineState: Set<SpeechEngineState>] = [
        .idle: [.connecting, .stopped],
        .connecting: [.streaming, .fallback, .stopping, .failed],
        .streaming: [.fallback, .stopping, .failed],
        .fallback: [.connecting, .stopping, .failed],
        .stopping: [.stopped],
        .stopped: [.connecting],
        .failed: [.connecting, .stopping],
    ]

    public func canTransition(to next: SpeechEngineState) -> Bool {
        Self.transitions[self, default: []].contains(next)
    }
}

public enum SpeechEngineError: Error, Equatable, Sendable {
    case invalidTransition(from: SpeechEngineState, to: SpeechEngineState)
    case realtimeAndFallbackUnavailable
}

public protocol RealtimeSpeechTransport: Sendable {
    func start() async throws
    func stop() async
}

public protocol CaptionFallbackTransport: Sendable {
    func start() async throws
    func stop() async
}

public actor SpeechEngineCoordinator {
    public private(set) var state: SpeechEngineState = .idle
    private let realtime: any RealtimeSpeechTransport
    private let fallback: any CaptionFallbackTransport

    public init(realtime: any RealtimeSpeechTransport, fallback: any CaptionFallbackTransport) {
        self.realtime = realtime
        self.fallback = fallback
    }

    public func start() async throws {
        try transition(to: .connecting)
        do {
            try await realtime.start()
            try transition(to: .streaming)
        } catch {
            try transition(to: .fallback)
            do {
                try await fallback.start()
            } catch {
                try transition(to: .failed)
                throw SpeechEngineError.realtimeAndFallbackUnavailable
            }
        }
    }

    public func useFallback() async throws {
        guard state == .streaming else {
            throw SpeechEngineError.invalidTransition(from: state, to: .fallback)
        }
        await realtime.stop()
        try transition(to: .fallback)
        do {
            try await fallback.start()
        } catch {
            try transition(to: .failed)
            throw SpeechEngineError.realtimeAndFallbackUnavailable
        }
    }

    public func stop() async throws {
        if state == .stopped { return }
        if state == .idle {
            try transition(to: .stopped)
            return
        }
        try transition(to: .stopping)
        await realtime.stop()
        await fallback.stop()
        try transition(to: .stopped)
    }

    private func transition(to next: SpeechEngineState) throws {
        guard state.canTransition(to: next) else {
            throw SpeechEngineError.invalidTransition(from: state, to: next)
        }
        state = next
    }
}
