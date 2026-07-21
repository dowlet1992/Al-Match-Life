import Testing
@testable import AlMatchLifeCore

actor MockRealtimeTransport: RealtimeSpeechTransport {
    private let shouldFail: Bool
    private(set) var starts = 0
    private(set) var stops = 0

    init(shouldFail: Bool = false) { self.shouldFail = shouldFail }

    func start() async throws {
        starts += 1
        if shouldFail { throw TestFailure.expected }
    }

    func stop() async { stops += 1 }
}

actor MockFallbackTransport: CaptionFallbackTransport {
    private let shouldFail: Bool
    private(set) var starts = 0
    private(set) var stops = 0

    init(shouldFail: Bool = false) { self.shouldFail = shouldFail }

    func start() async throws {
        starts += 1
        if shouldFail { throw TestFailure.expected }
    }

    func stop() async { stops += 1 }
}

enum TestFailure: Error { case expected }

@Test func realtimeSuccessStreamsAndStopsBothTransports() async throws {
    let realtime = MockRealtimeTransport()
    let fallback = MockFallbackTransport()
    let engine = SpeechEngineCoordinator(realtime: realtime, fallback: fallback)

    try await engine.start()
    #expect(await engine.state == .streaming)
    #expect(await realtime.starts == 1)
    #expect(await fallback.starts == 0)

    try await engine.stop()
    #expect(await engine.state == .stopped)
    #expect(await realtime.stops == 1)
    #expect(await fallback.stops == 1)
}

@Test func realtimeFailureUsesFallbackWithoutFailingCall() async throws {
    let realtime = MockRealtimeTransport(shouldFail: true)
    let fallback = MockFallbackTransport()
    let engine = SpeechEngineCoordinator(realtime: realtime, fallback: fallback)

    try await engine.start()

    #expect(await engine.state == .fallback)
    #expect(await fallback.starts == 1)
}

@Test func bothTransportsFailClosed() async {
    let engine = SpeechEngineCoordinator(
        realtime: MockRealtimeTransport(shouldFail: true),
        fallback: MockFallbackTransport(shouldFail: true)
    )

    await #expect(throws: SpeechEngineError.realtimeAndFallbackUnavailable) {
        try await engine.start()
    }
    #expect(await engine.state == .failed)
}

@Test func transitionTableMatchesServerContract() {
    #expect(SpeechEngineState.idle.canTransition(to: .connecting))
    #expect(SpeechEngineState.streaming.canTransition(to: .fallback))
    #expect(!SpeechEngineState.streaming.canTransition(to: .idle))
    #expect(SpeechEngineState.stopping.canTransition(to: .stopped))
}
