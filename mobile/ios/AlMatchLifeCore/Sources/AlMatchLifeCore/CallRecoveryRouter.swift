import Foundation

public protocol CallRecoveryStatusPresenting: Sendable {
    func present(_ status: CallRecoveryStatus, callUUID: UUID) async
}

public final class CallRecoveryRouter: @unchecked Sendable {
    private let lock = NSLock()
    private let callUUID: UUID
    private let presenter: any CallRecoveryStatusPresenting
    private var coordinator: VoIPCallCoordinator?
    private var failureDelivered = false

    public init(callUUID: UUID, presenter: any CallRecoveryStatusPresenting) {
        self.callUUID = callUUID
        self.presenter = presenter
    }

    public func bind(coordinator: VoIPCallCoordinator) {
        lock.withLock { self.coordinator = coordinator }
    }

    public func statusHandler() -> @Sendable (CallRecoveryStatus) async -> Void {
        { [weak self] status in
            guard let self else { return }
            await self.presenter.present(status, callUUID: self.callUUID)
        }
    }

    public func failureHandler() -> @Sendable (Error) async -> Void {
        { [weak self] _ in
            guard let self else { return }
            let target = self.lock.withLock { () -> VoIPCallCoordinator? in
                guard !self.failureDelivered, let coordinator = self.coordinator else { return nil }
                self.failureDelivered = true
                return coordinator
            }
            await target?.connectionFailed(uuid: self.callUUID)
        }
    }
}
