import Foundation
import Testing
@testable import AlMatchLifeCore

actor LifecycleTrace {
    private(set) var events: [String] = []
    func add(_ event: String) { events.append(event) }
}

struct MockNativeSignaling: NativeCallSignaling {
    let trace: LifecycleTrace
    func send(type: NativeSignalType, eventID: String, payload: VoIPCallPayload, reason: String?) async throws {
        #expect(eventID.hasPrefix("ios_"))
        await trace.add("signal:\(type.rawValue)\(reason.map { ":\($0)" } ?? "")")
    }
}

final class MockCallAudio: CallAudioSessionControlling, @unchecked Sendable {
    let trace: LifecycleTrace
    init(trace: LifecycleTrace) { self.trace = trace }
    func activate(for callType: NativeCallType, speakerEnabled: Bool) async throws { await trace.add("audio:start") }
    func setSpeakerEnabled(_ enabled: Bool) async throws {}
    func deactivate() async throws { await trace.add("audio:stop") }
}

struct MockPersonMedia: PersonCallMediaTransport {
    let trace: LifecycleTrace
    let shouldFail: Bool
    func start(_ payload: VoIPCallPayload) async throws {
        await trace.add("media:start")
        if shouldFail { throw TestFailure.expected }
    }
    func stop() async { await trace.add("media:stop") }
}

struct MockCaptions: CallCaptionLifecycle {
    let trace: LifecycleTrace
    let shouldFail: Bool
    func start() async throws {
        await trace.add("captions:start")
        if shouldFail { throw TestFailure.expected }
    }
    func stop() async throws { await trace.add("captions:stop") }
}

private func lifecyclePayload() throws -> VoIPCallPayload {
    try VoIPCallPayload(dictionary: [
        "event_id": "incoming_event_1", "event_type": "incoming_call", "call_id": "stable_call_1234",
        "call_type": "video", "caller_email": "alice@example.com", "receiver_email": "bob@example.com",
        "expires_at": "1040",
    ], currentEmail: "bob@example.com", now: 1_000)
}

@Test func acceptsInOrderAndCaptionFailureDoesNotEndMainCall() async throws {
    let trace = LifecycleTrace()
    let lifecycle = ProductionNativeCallLifecycle(
        signaling: MockNativeSignaling(trace: trace), audio: MockCallAudio(trace: trace),
        media: MockPersonMedia(trace: trace, shouldFail: false), captions: MockCaptions(trace: trace, shouldFail: true),
        optionalFeatureError: { _ in await trace.add("captions:error") }
    )
    try await lifecycle.accept(try lifecyclePayload())
    #expect(await trace.events == ["signal:accepted", "audio:start", "media:start", "captions:start", "captions:error"])
}

@Test func mainMediaFailureRollsBackAndSignalsEnded() async {
    let trace = LifecycleTrace()
    let lifecycle = ProductionNativeCallLifecycle(
        signaling: MockNativeSignaling(trace: trace), audio: MockCallAudio(trace: trace),
        media: MockPersonMedia(trace: trace, shouldFail: true), captions: MockCaptions(trace: trace, shouldFail: false),
        optionalFeatureError: { _ in }
    )
    await #expect(throws: TestFailure.expected) { try await lifecycle.accept(try lifecyclePayload()) }
    #expect(await trace.events == [
        "signal:accepted", "audio:start", "media:start", "captions:stop", "media:stop", "audio:stop", "signal:ended",
    ])
}

@Test func declineSendsOnlySignal() async throws {
    let trace = LifecycleTrace()
    let lifecycle = ProductionNativeCallLifecycle(
        signaling: MockNativeSignaling(trace: trace), audio: MockCallAudio(trace: trace),
        media: MockPersonMedia(trace: trace, shouldFail: false), captions: MockCaptions(trace: trace, shouldFail: false),
        optionalFeatureError: { _ in }
    )
    await lifecycle.decline(try lifecyclePayload())
    #expect(await trace.events == ["signal:declined"])
}

@Test func connectionLossUsesAllowedHistoryReason() async throws {
    let trace = LifecycleTrace()
    let lifecycle = ProductionNativeCallLifecycle(
        signaling: MockNativeSignaling(trace: trace), audio: MockCallAudio(trace: trace),
        media: MockPersonMedia(trace: trace, shouldFail: false), captions: MockCaptions(trace: trace, shouldFail: false),
        optionalFeatureError: { _ in }
    )
    await lifecycle.connectionLost(try lifecyclePayload())
    #expect(await trace.events == ["signal:ended:connection_lost"])
}
