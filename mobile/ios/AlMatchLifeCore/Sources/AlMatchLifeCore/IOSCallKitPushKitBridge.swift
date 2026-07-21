#if os(iOS)
@preconcurrency import CallKit
import Foundation
@preconcurrency import PushKit

public actor IOSCallKitReporter: SystemCallReporting {
    private let provider: CXProvider
    private let delegate: CallKitActionDelegate

    public init(localizedName: String = "Al Match Life") {
        let configuration = CXProviderConfiguration(localizedName: localizedName)
        configuration.supportsVideo = true
        configuration.maximumCallGroups = 1
        configuration.maximumCallsPerCallGroup = 1
        configuration.supportedHandleTypes = [.generic]
        self.provider = CXProvider(configuration: configuration)
        self.delegate = CallKitActionDelegate()
        provider.setDelegate(delegate, queue: nil)
    }

    public func bind(coordinator: VoIPCallCoordinator) {
        delegate.reference.set(coordinator)
    }

    public func reportIncoming(_ payload: VoIPCallPayload) async throws {
        let update = CXCallUpdate()
        update.remoteHandle = CXHandle(type: .generic, value: "Al Match Life")
        update.localizedCallerName = "Al Match Life call"
        update.hasVideo = payload.callType == .video
        update.supportsHolding = false
        update.supportsGrouping = false
        update.supportsUngrouping = false
        try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
            provider.reportNewIncomingCall(with: payload.uuid, update: update) { error in
                if let error { continuation.resume(throwing: error) }
                else { continuation.resume() }
            }
        }
    }

    public func reportEnded(uuid: UUID, reason: SystemCallEndReason) async {
        let mapped: CXCallEndedReason = switch reason {
        case .remoteEnded: .remoteEnded
        case .declined: .declinedElsewhere
        case .failed: .failed
        case .unanswered: .unanswered
        }
        provider.reportCall(with: uuid, endedAt: Date(), reason: mapped)
    }
}

private final class CallKitActionDelegate: NSObject, CXProviderDelegate, @unchecked Sendable {
    let reference = LockedCoordinatorReference()

    func providerDidReset(_ provider: CXProvider) {
        guard let coordinator = reference.get() else { return }
        Task { await coordinator.resetAll() }
    }

    func provider(_ provider: CXProvider, perform action: CXAnswerCallAction) {
        guard let coordinator = reference.get() else { action.fail(); return }
        Task {
            do { try await coordinator.accept(uuid: action.callUUID); action.fulfill() }
            catch { action.fail() }
        }
    }

    func provider(_ provider: CXProvider, perform action: CXEndCallAction) {
        guard let coordinator = reference.get() else { action.fail(); return }
        Task { await coordinator.endFromSystem(uuid: action.callUUID); action.fulfill() }
    }
}

private final class LockedCoordinatorReference: @unchecked Sendable {
    private let lock = NSLock()
    private var coordinator: VoIPCallCoordinator?
    func set(_ value: VoIPCallCoordinator) { lock.withLock { coordinator = value } }
    func get() -> VoIPCallCoordinator? { lock.withLock { coordinator } }
}

@MainActor
public final class IOSPushKitBridge: NSObject, PKPushRegistryDelegate {
    public typealias CurrentEmail = @Sendable () -> String
    public typealias TokenHandler = @Sendable (Data?) async -> Void
    public typealias ErrorHandler = @Sendable (Error) async -> Void

    private let registry: PKPushRegistry
    private let coordinator: VoIPCallCoordinator
    private let currentEmail: CurrentEmail
    private let tokenHandler: TokenHandler
    private let errorHandler: ErrorHandler

    public init(
        coordinator: VoIPCallCoordinator,
        currentEmail: @escaping CurrentEmail,
        tokenHandler: @escaping TokenHandler,
        errorHandler: @escaping ErrorHandler
    ) {
        self.registry = PKPushRegistry(queue: .main)
        self.coordinator = coordinator
        self.currentEmail = currentEmail
        self.tokenHandler = tokenHandler
        self.errorHandler = errorHandler
        super.init()
        registry.delegate = self
        registry.desiredPushTypes = [.voIP]
    }

    public func pushRegistry(_ registry: PKPushRegistry, didUpdate pushCredentials: PKPushCredentials, for type: PKPushType) {
        guard type == .voIP else { return }
        Task { await tokenHandler(pushCredentials.token) }
    }

    public func pushRegistry(_ registry: PKPushRegistry, didInvalidatePushTokenFor type: PKPushType) {
        guard type == .voIP else { return }
        Task { await tokenHandler(nil) }
    }

    public func pushRegistry(
        _ registry: PKPushRegistry, didReceiveIncomingPushWith payload: PKPushPayload,
        for type: PKPushType, completion: @escaping () -> Void
    ) {
        guard type == .voIP else { completion(); return }
        do {
            let parsed = try VoIPCallPayload(
                dictionary: payload.dictionaryPayload, currentEmail: currentEmail(),
                now: Int(Date().timeIntervalSince1970)
            )
            Task {
                defer { completion() }
                do { _ = try await coordinator.receive(parsed) }
                catch { await errorHandler(error) }
            }
        } catch {
            Task { await errorHandler(error); completion() }
        }
    }
}
#endif
