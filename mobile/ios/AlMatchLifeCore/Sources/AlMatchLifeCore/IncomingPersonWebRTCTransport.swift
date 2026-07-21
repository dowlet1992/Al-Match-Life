import Foundation

public enum PersonWebRTCTransportError: Error, Sendable, Equatable {
    case alreadyRunning, missingDescription, invalidAcknowledgement, terminalCall(String), recoveryExhausted
}

public enum PersonPeerConnectionState: Sendable { case new, connecting, connected, disconnected, failed, closed }
public enum CallRecoveryStatus: Sendable, Equatable {
    case connected, reconnecting(attempt: Int, maximum: Int), waitingForNetwork, failed
}

public protocol PersonPeerConnection: AnyObject, Sendable {
    func setLocalCandidateHandler(_ handler: @escaping @Sendable (NativeICECandidate) -> Void) async
    func setConnectionStateHandler(_ handler: @escaping @Sendable (PersonPeerConnectionState) -> Void) async
    func addLocalMedia(callType: NativeCallType) async throws
    func setRemoteDescription(type: String, sdp: String) async throws
    func createAnswer() async throws -> String
    func addRemoteCandidate(_ candidate: NativeICECandidate) async throws
    func close() async
}

public protocol NetworkStatusProviding: Sendable { func isOnline() async -> Bool }
public struct AlwaysOnlineNetworkStatus: NetworkStatusProviding, Sendable {
    public init() {}
    public func isOnline() async -> Bool { true }
}
public protocol RecoverySleeping: Sendable { func sleep(milliseconds: Int) async }
public struct TaskRecoverySleeper: RecoverySleeping, Sendable {
    public init() {}
    public func sleep(milliseconds: Int) async { try? await Task.sleep(for: .milliseconds(milliseconds)) }
}

public protocol RemoteMediaTrackReceiving: Sendable {
    func receiveLocalVideoTrack(_ track: AnyObject) async
    func receiveRemoteVideoTrack(_ track: AnyObject) async
    func remoteAudioAvailable() async
}

public protocol PersonPeerConnectionFactory: Sendable {
    func make(configuration: NativeICEConfiguration) async throws -> any PersonPeerConnection
}

public protocol PersonCallSignaling: Sendable {
    func ice(for payload: VoIPCallPayload) async throws -> NativeICEConfiguration
    func poll(for payload: VoIPCallPayload, after: Double) async throws -> NativeSignalPoll
    func sendDescription(for payload: VoIPCallPayload, type: String, sdp: String, eventID: String) async throws
    func sendCandidate(for payload: VoIPCallPayload, candidate: NativeICECandidate, eventID: String) async throws
    func acknowledge(for payload: VoIPCallPayload, eventIDs: [String]) async throws
}

extension AuthenticatedAPIClient: PersonCallSignaling {
    public func ice(for payload: VoIPCallPayload) async throws -> NativeICEConfiguration {
        try await iceConfiguration(callID: payload.callID, otherEmail: payload.callerEmail, callType: payload.callType)
    }
    public func poll(for payload: VoIPCallPayload, after: Double) async throws -> NativeSignalPoll {
        try await pollCallSignals(callID: payload.callID, otherEmail: payload.callerEmail, callType: payload.callType, after: after)
    }
    public func sendDescription(for payload: VoIPCallPayload, type: String, sdp: String, eventID: String) async throws {
        let result = try await sendSessionDescription(
            callID: payload.callID, otherEmail: payload.callerEmail, callType: payload.callType,
            type: type, sdp: sdp, eventID: eventID
        )
        guard result.ok, result.eventID == eventID else { throw PersonWebRTCTransportError.invalidAcknowledgement }
    }
    public func sendCandidate(
        for payload: VoIPCallPayload, candidate: NativeICECandidate, eventID: String
    ) async throws {
        let result = try await sendICECandidate(
            callID: payload.callID, otherEmail: payload.callerEmail, callType: payload.callType,
            candidate: candidate, eventID: eventID
        )
        guard result.ok, result.eventID == eventID else { throw PersonWebRTCTransportError.invalidAcknowledgement }
    }
    public func acknowledge(for payload: VoIPCallPayload, eventIDs: [String]) async throws {
        guard !eventIDs.isEmpty else { return }
        let result = try await acknowledgeCallSignals(
            callID: payload.callID, otherEmail: payload.callerEmail, callType: payload.callType, eventIDs: eventIDs
        )
        guard result.ok, Set(result.acknowledgedEventIDs) == Set(eventIDs) else {
            throw PersonWebRTCTransportError.invalidAcknowledgement
        }
    }
}

public actor IncomingPersonWebRTCTransport: PersonCallMediaTransport {
    private let factory: any PersonPeerConnectionFactory
    private let signaling: any PersonCallSignaling
    private let network: any NetworkStatusProviding
    private let failureHandler: @Sendable (Error) async -> Void
    private let recoveryStatusHandler: @Sendable (CallRecoveryStatus) async -> Void
    private let sleeper: any RecoverySleeping
    private var peer: (any PersonPeerConnection)?
    private var payload: VoIPCallPayload?
    private var pollTask: Task<Void, Never>?
    private var recoveryTask: Task<Void, Never>?
    private var connectionState: PersonPeerConnectionState = .new
    private var recoveryAttempts = 0
    private var watermark: Double = 0
    private var processedIDs: [String] = []
    private var pendingACKIDs: [String] = []
    private var localDescriptionPublished = false
    private var pendingLocalCandidates: [NativeICECandidate] = []

    public init(
        factory: any PersonPeerConnectionFactory, signaling: any PersonCallSignaling,
        network: any NetworkStatusProviding = AlwaysOnlineNetworkStatus(),
        sleeper: any RecoverySleeping = TaskRecoverySleeper(),
        recoveryStatusHandler: @escaping @Sendable (CallRecoveryStatus) async -> Void = { _ in },
        failureHandler: @escaping @Sendable (Error) async -> Void = { _ in }
    ) {
        self.factory = factory
        self.signaling = signaling
        self.network = network
        self.sleeper = sleeper
        self.recoveryStatusHandler = recoveryStatusHandler
        self.failureHandler = failureHandler
    }

    public func start(_ payload: VoIPCallPayload) async throws {
        guard peer == nil else { throw PersonWebRTCTransportError.alreadyRunning }
        let configuration = try await signaling.ice(for: payload)
        let candidate = try await factory.make(configuration: configuration)
        do {
            await candidate.setLocalCandidateHandler { [weak self] value in
                Task { await self?.publishLocalCandidate(value) }
            }
            await candidate.setConnectionStateHandler { [weak self] state in
                Task { await self?.connectionChanged(state) }
            }
            try await candidate.addLocalMedia(callType: payload.callType)
            self.peer = candidate
            self.payload = payload
            self.pollTask = Task { [weak self] in await self?.pollLoop() }
        } catch {
            await candidate.close()
            throw error
        }
    }

    public func stop() async {
        pollTask?.cancel()
        recoveryTask?.cancel()
        pollTask = nil
        recoveryTask = nil
        let current = peer
        peer = nil
        payload = nil
        watermark = 0
        processedIDs.removeAll(keepingCapacity: false)
        pendingACKIDs.removeAll(keepingCapacity: false)
        pendingLocalCandidates.removeAll(keepingCapacity: false)
        localDescriptionPublished = false
        connectionState = .closed
        recoveryAttempts = 0
        await current?.setLocalCandidateHandler { _ in }
        await current?.setConnectionStateHandler { _ in }
        await current?.close()
    }

    private func connectionChanged(_ state: PersonPeerConnectionState) async {
        connectionState = state
        switch state {
        case .connected:
            recoveryAttempts = 0
            recoveryTask?.cancel()
            recoveryTask = nil
            await recoveryStatusHandler(.connected)
        case .disconnected, .failed:
            await recoveryStatusHandler(.reconnecting(attempt: recoveryAttempts, maximum: 3))
            startRecoveryWatchIfNeeded()
        case .closed:
            if peer != nil { await failureHandler(PersonWebRTCTransportError.recoveryExhausted); await stop() }
        default:
            break
        }
    }

    private func startRecoveryWatchIfNeeded() {
        guard recoveryTask == nil else { return }
        recoveryTask = Task { [weak self] in await self?.recoveryWatch() }
    }

    private func recoveryWatch() async {
        var delayMilliseconds = 5_000
        while !Task.isCancelled, peer != nil,
              connectionState == .disconnected || connectionState == .failed {
            await sleeper.sleep(milliseconds: delayMilliseconds)
            guard !Task.isCancelled else { return }
            guard await network.isOnline() else {
                await recoveryStatusHandler(.waitingForNetwork)
                delayMilliseconds = 1_000
                continue
            }
            guard connectionState != .connected else { return }
            recoveryAttempts += 1
            await recoveryStatusHandler(.reconnecting(attempt: recoveryAttempts, maximum: 3))
            if recoveryAttempts >= 3 {
                recoveryTask = nil
                await recoveryStatusHandler(.failed)
                await failureHandler(PersonWebRTCTransportError.recoveryExhausted)
                await stop()
                return
            }
            delayMilliseconds = min(5_000 * (recoveryAttempts + 1), 10_000)
        }
        recoveryTask = nil
    }

    private func pollLoop() async {
        var consecutiveFailures = 0
        while !Task.isCancelled, let payload {
            do {
                let result = try await signaling.poll(for: payload, after: watermark)
                if ["declined", "ended", "missed"].contains(result.status) {
                    await stop()
                    return
                }
                for message in result.messages where !processedIDs.contains(message.id) {
                    try await process(message)
                    remember(message.id)
                    if !pendingACKIDs.contains(message.id) { pendingACKIDs.append(message.id) }
                }
                if localDescriptionPublished { try? await flushLocalCandidates() }
                if !pendingACKIDs.isEmpty {
                    let batch = Array(pendingACKIDs.prefix(50))
                    try await signaling.acknowledge(for: payload, eventIDs: batch)
                    pendingACKIDs.removeFirst(batch.count)
                }
                watermark = max(watermark, result.serverTime - 1)
                consecutiveFailures = 0
            } catch let error as PersonWebRTCTransportError {
                if case .terminalCall = error { await stop(); return }
                consecutiveFailures += 1
            } catch {
                consecutiveFailures += 1
            }
            let delay = min(800 * (1 << min(consecutiveFailures, 3)), 6_400)
            try? await Task.sleep(for: .milliseconds(delay))
        }
    }

    private func process(_ message: NativeCallSignal) async throws {
        guard let peer else { return }
        switch message.type {
        case "offer":
            guard let sdp = message.payload.sdp else { throw PersonWebRTCTransportError.missingDescription }
            try await peer.setRemoteDescription(type: "offer", sdp: sdp)
            let answer = try await peer.createAnswer()
            guard let payload else { return }
            try await signaling.sendDescription(for: payload, type: "answer", sdp: answer, eventID: Self.eventID("answer"))
            localDescriptionPublished = true
            try await flushLocalCandidates()
        case "answer":
            guard let sdp = message.payload.sdp else { throw PersonWebRTCTransportError.missingDescription }
            try await peer.setRemoteDescription(type: "answer", sdp: sdp)
        case "ice":
            guard let value = message.payload.candidate else { return }
            try await peer.addRemoteCandidate(.init(
                candidate: value, sdpMid: message.payload.sdpMid,
                sdpMLineIndex: message.payload.sdpMLineIndex,
                usernameFragment: message.payload.usernameFragment
            ))
        case "declined", "ended", "missed":
            throw PersonWebRTCTransportError.terminalCall(message.type)
        default:
            break
        }
    }

    private func publishLocalCandidate(_ candidate: NativeICECandidate) async {
        guard localDescriptionPublished, let payload else {
            pendingLocalCandidates.append(candidate)
            if pendingLocalCandidates.count > 128 { pendingLocalCandidates.removeFirst() }
            return
        }
        do {
            try await signaling.sendCandidate(for: payload, candidate: candidate, eventID: Self.eventID("ice"))
        } catch {
            pendingLocalCandidates.append(candidate)
            if pendingLocalCandidates.count > 128 { pendingLocalCandidates.removeFirst() }
        }
    }

    private func flushLocalCandidates() async throws {
        guard let payload else { return }
        let queued = pendingLocalCandidates
        pendingLocalCandidates.removeAll(keepingCapacity: true)
        for (index, candidate) in queued.enumerated() {
            do {
                try await signaling.sendCandidate(for: payload, candidate: candidate, eventID: Self.eventID("ice"))
            } catch {
                pendingLocalCandidates.append(contentsOf: queued[index...])
                throw error
            }
        }
    }

    private func remember(_ eventID: String) {
        processedIDs.append(eventID)
        if processedIDs.count > 600 { processedIDs.removeFirst(processedIDs.count - 600) }
    }

    private static func eventID(_ type: String) -> String {
        "ios_\(type)_" + UUID().uuidString.lowercased()
    }
}
