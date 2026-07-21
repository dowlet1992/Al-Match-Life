import CryptoKit
import Foundation

public enum VoIPPayloadError: Error, Sendable, Equatable {
    case invalidEventType, invalidEventID, invalidCallID, invalidCallType
    case invalidParticipant, wrongReceiver, invalidExpiry
}

public struct VoIPCallPayload: Sendable, Equatable {
    public enum EventType: String, Sendable { case incomingCall = "incoming_call", cancelled = "call_cancelled" }

    public let eventID: String
    public let eventType: EventType
    public let callID: String
    public let callType: NativeCallType
    public let callerEmail: String
    public let receiverEmail: String
    public let expiresAt: Int
    public let uuid: UUID

    public init(dictionary: [AnyHashable: Any], currentEmail: String, now: Int) throws {
        guard let eventType = EventType(rawValue: Self.text(dictionary["event_type"])) else {
            throw VoIPPayloadError.invalidEventType
        }
        let eventID = Self.text(dictionary["event_id"])
        guard Self.isIdentifier(eventID, minimum: 8, maximum: 80) else { throw VoIPPayloadError.invalidEventID }
        let callID = Self.text(dictionary["call_id"])
        guard Self.isIdentifier(callID, minimum: 8, maximum: 128) else { throw VoIPPayloadError.invalidCallID }
        guard let callType = NativeCallType(rawValue: Self.text(dictionary["call_type"])) else {
            throw VoIPPayloadError.invalidCallType
        }
        let callerEmail = Self.text(dictionary["caller_email"]).lowercased()
        let receiverEmail = Self.text(dictionary["receiver_email"]).lowercased()
        guard Self.isEmail(callerEmail), Self.isEmail(receiverEmail), callerEmail != receiverEmail else {
            throw VoIPPayloadError.invalidParticipant
        }
        guard receiverEmail == currentEmail.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() else {
            throw VoIPPayloadError.wrongReceiver
        }
        guard let expiresAt = Int(Self.text(dictionary["expires_at"])),
              expiresAt >= now, expiresAt <= now + 180 else { throw VoIPPayloadError.invalidExpiry }
        self.eventID = eventID
        self.eventType = eventType
        self.callID = callID
        self.callType = callType
        self.callerEmail = callerEmail
        self.receiverEmail = receiverEmail
        self.expiresAt = expiresAt
        self.uuid = Self.stableUUID(callID: callID, callType: callType)
    }

    private static func text(_ value: Any?) -> String { String(describing: value ?? "").trimmingCharacters(in: .whitespacesAndNewlines) }

    private static func isIdentifier(_ value: String, minimum: Int, maximum: Int) -> Bool {
        guard (minimum...maximum).contains(value.count) else { return false }
        return value.unicodeScalars.allSatisfy { CharacterSet.alphanumerics.contains($0) || $0 == "_" || $0 == "-" }
    }

    private static func isEmail(_ value: String) -> Bool {
        value.count <= 254 && !value.contains("\r") && !value.contains("\n") &&
        value.split(separator: "@", omittingEmptySubsequences: false).count == 2
    }

    private static func stableUUID(callID: String, callType: NativeCallType) -> UUID {
        var bytes = Array(SHA256.hash(data: Data("al-match-life:\(callType.rawValue):\(callID)".utf8)).prefix(16))
        bytes[6] = (bytes[6] & 0x0F) | 0x50
        bytes[8] = (bytes[8] & 0x3F) | 0x80
        return UUID(uuid: (
            bytes[0], bytes[1], bytes[2], bytes[3], bytes[4], bytes[5], bytes[6], bytes[7],
            bytes[8], bytes[9], bytes[10], bytes[11], bytes[12], bytes[13], bytes[14], bytes[15]
        ))
    }
}

public enum SystemCallEndReason: Sendable, Equatable { case remoteEnded, declined, failed, unanswered }

public protocol SystemCallReporting: Sendable {
    func reportIncoming(_ payload: VoIPCallPayload) async throws
    func reportEnded(uuid: UUID, reason: SystemCallEndReason) async
}

public protocol NativeCallLifecycle: Sendable {
    func accept(_ payload: VoIPCallPayload) async throws
    func decline(_ payload: VoIPCallPayload) async
    func end(_ payload: VoIPCallPayload) async
    func connectionLost(_ payload: VoIPCallPayload) async
    func stop(_ payload: VoIPCallPayload) async
}

public enum VoIPPushDisposition: Sendable, Equatable { case reported, cancelled, duplicate, ignored }

public actor VoIPCallCoordinator {
    private let system: any SystemCallReporting
    private let lifecycle: any NativeCallLifecycle
    private var seenEventIDs: [String] = []
    private var active: [UUID: VoIPCallPayload] = [:]
    private var accepted: Set<UUID> = []
    private let maximumSeenEvents = 256

    public init(system: any SystemCallReporting, lifecycle: any NativeCallLifecycle) {
        self.system = system
        self.lifecycle = lifecycle
    }

    public func receive(_ payload: VoIPCallPayload) async throws -> VoIPPushDisposition {
        guard !seenEventIDs.contains(payload.eventID) else { return .duplicate }
        remember(payload.eventID)
        if payload.eventType == .cancelled {
            guard let current = active.removeValue(forKey: payload.uuid), current.callID == payload.callID else {
                return .ignored
            }
            accepted.remove(payload.uuid)
            await lifecycle.stop(current)
            await system.reportEnded(uuid: current.uuid, reason: .remoteEnded)
            return .cancelled
        }
        guard active[payload.uuid] == nil else { return .duplicate }
        do {
            try await system.reportIncoming(payload)
            active[payload.uuid] = payload
            return .reported
        } catch {
            await lifecycle.stop(payload)
            throw error
        }
    }

    public func accept(uuid: UUID) async throws {
        guard let payload = active[uuid] else { return }
        do {
            try await lifecycle.accept(payload)
            accepted.insert(uuid)
        } catch {
            active.removeValue(forKey: uuid)
            accepted.remove(uuid)
            await lifecycle.stop(payload)
            await system.reportEnded(uuid: uuid, reason: .failed)
            throw error
        }
    }

    public func decline(uuid: UUID) async {
        guard let payload = active.removeValue(forKey: uuid) else { return }
        accepted.remove(uuid)
        await lifecycle.decline(payload)
        await lifecycle.stop(payload)
        await system.reportEnded(uuid: uuid, reason: .declined)
    }

    public func endFromSystem(uuid: UUID) async {
        guard let payload = active.removeValue(forKey: uuid) else { return }
        let wasAccepted = accepted.remove(uuid) != nil
        if wasAccepted { await lifecycle.end(payload) }
        else { await lifecycle.decline(payload) }
        await lifecycle.stop(payload)
    }

    public func resetAll() async {
        let calls = Array(active.values)
        active.removeAll(keepingCapacity: false)
        accepted.removeAll(keepingCapacity: false)
        for payload in calls { await lifecycle.stop(payload) }
    }

    public func timedOut(uuid: UUID) async {
        guard let payload = active.removeValue(forKey: uuid) else { return }
        accepted.remove(uuid)
        await lifecycle.stop(payload)
        await system.reportEnded(uuid: uuid, reason: .unanswered)
    }

    public func ended(uuid: UUID) async {
        guard let payload = active.removeValue(forKey: uuid) else { return }
        accepted.remove(uuid)
        await lifecycle.stop(payload)
        await system.reportEnded(uuid: uuid, reason: .remoteEnded)
    }

    public func connectionFailed(uuid: UUID) async {
        guard let payload = active.removeValue(forKey: uuid) else { return }
        accepted.remove(uuid)
        await lifecycle.connectionLost(payload)
        await lifecycle.stop(payload)
        await system.reportEnded(uuid: uuid, reason: .failed)
    }

    private func remember(_ eventID: String) {
        seenEventIDs.append(eventID)
        if seenEventIDs.count > maximumSeenEvents {
            seenEventIDs.removeFirst(seenEventIDs.count - maximumSeenEvents)
        }
    }
}
