import Foundation
import Testing
@testable import AlMatchLifeCore

actor MockSystemCalls: SystemCallReporting {
    private(set) var incoming: [VoIPCallPayload] = []
    private(set) var ended: [(UUID, SystemCallEndReason)] = []
    func reportIncoming(_ payload: VoIPCallPayload) async throws { incoming.append(payload) }
    func reportEnded(uuid: UUID, reason: SystemCallEndReason) async { ended.append((uuid, reason)) }
}

actor MockCallLifecycle: NativeCallLifecycle {
    private(set) var accepted = 0
    private(set) var declined = 0
    private(set) var ended = 0
    private(set) var connectionLost = 0
    private(set) var stopped = 0
    func accept(_ payload: VoIPCallPayload) async throws { accepted += 1 }
    func decline(_ payload: VoIPCallPayload) async { declined += 1 }
    func end(_ payload: VoIPCallPayload) async { ended += 1 }
    func connectionLost(_ payload: VoIPCallPayload) async { connectionLost += 1 }
    func stop(_ payload: VoIPCallPayload) async { stopped += 1 }
}

private func push(eventID: String, type: String = "incoming_call", expires: Int = 1_040) -> [AnyHashable: Any] {
    ["event_id": eventID, "event_type": type, "call_id": "stable_call_1234", "call_type": "audio",
     "caller_email": "alice@example.com", "receiver_email": "bob@example.com", "expires_at": String(expires)]
}

@Test func validatesReportsDeduplicatesAndCancelsSameCall() async throws {
    let system = MockSystemCalls()
    let lifecycle = MockCallLifecycle()
    let coordinator = VoIPCallCoordinator(system: system, lifecycle: lifecycle)

    let firstPayload = try VoIPCallPayload(dictionary: push(eventID: "ring_event_1234"), currentEmail: "bob@example.com", now: 1_000)
    let first = try await coordinator.receive(firstPayload)
    let duplicate = try await coordinator.receive(firstPayload)
    let cancelPayload = try VoIPCallPayload(
        dictionary: push(eventID: "cancel_event_12", type: "call_cancelled", expires: 1_100),
        currentEmail: "bob@example.com", now: 1_000
    )
    let cancelled = try await coordinator.receive(cancelPayload)

    #expect(first == .reported)
    #expect(duplicate == .duplicate)
    #expect(cancelled == .cancelled)
    #expect(await system.incoming.count == 1)
    #expect(await lifecycle.stopped == 1)
    #expect(await system.ended.count == 1)
}

@Test func rejectsExpiredAndWrongReceiverBeforeCallKit() async {
    let coordinator = VoIPCallCoordinator(system: MockSystemCalls(), lifecycle: MockCallLifecycle())
    await #expect(throws: VoIPPayloadError.invalidExpiry) {
        _ = try VoIPCallPayload(dictionary: push(eventID: "expired_event_1", expires: 999), currentEmail: "bob@example.com", now: 1_000)
    }
    await #expect(throws: VoIPPayloadError.wrongReceiver) {
        _ = try VoIPCallPayload(dictionary: push(eventID: "wrong_user_1234"), currentEmail: "mallory@example.com", now: 1_000)
    }
}

@Test func stableCallUUIDDoesNotDependOnPushEventID() throws {
    let one = try VoIPCallPayload(dictionary: push(eventID: "event_number_one"), currentEmail: "bob@example.com", now: 1_000)
    let two = try VoIPCallPayload(dictionary: push(eventID: "event_number_two"), currentEmail: "bob@example.com", now: 1_000)
    #expect(one.uuid == two.uuid)
}

@Test func systemEndDeclinesOnlyBeforeAcceptance() async throws {
    let lifecycle = MockCallLifecycle()
    let coordinator = VoIPCallCoordinator(system: MockSystemCalls(), lifecycle: lifecycle)
    let first = try VoIPCallPayload(dictionary: push(eventID: "preaccept_end_1"), currentEmail: "bob@example.com", now: 1_000)
    _ = try await coordinator.receive(first)
    await coordinator.endFromSystem(uuid: first.uuid)
    #expect(await lifecycle.declined == 1)
    #expect(await lifecycle.ended == 0)

    let second = try VoIPCallPayload(dictionary: push(eventID: "accepted_end_12"), currentEmail: "bob@example.com", now: 1_000)
    _ = try await coordinator.receive(second)
    try await coordinator.accept(uuid: second.uuid)
    await coordinator.endFromSystem(uuid: second.uuid)
    #expect(await lifecycle.declined == 1)
    #expect(await lifecycle.ended == 1)
    #expect(await lifecycle.stopped == 2)
}

@Test func recoveryFailureSignalsConnectionLostStopsAndFailsSystemCall() async throws {
    let system = MockSystemCalls()
    let lifecycle = MockCallLifecycle()
    let coordinator = VoIPCallCoordinator(system: system, lifecycle: lifecycle)
    let payload = try VoIPCallPayload(dictionary: push(eventID: "recovery_failed_1"), currentEmail: "bob@example.com", now: 1_000)
    _ = try await coordinator.receive(payload)
    try await coordinator.accept(uuid: payload.uuid)

    await coordinator.connectionFailed(uuid: payload.uuid)

    #expect(await lifecycle.connectionLost == 1)
    #expect(await lifecycle.stopped == 1)
    #expect(await system.ended.last?.1 == .failed)
}
