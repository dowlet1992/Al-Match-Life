#if canImport(Network)
import Foundation
import Network

public final class NWPathNetworkStatus: NetworkStatusProviding, @unchecked Sendable {
    private let monitor: NWPathMonitor
    private let queue = DispatchQueue(label: "com.aimatchlife.network-status")
    private let lock = NSLock()
    private var online = true

    public init() {
        monitor = NWPathMonitor()
        monitor.pathUpdateHandler = { [weak self] path in
            guard let self else { return }
            self.lock.withLock { self.online = path.status == .satisfied }
        }
        monitor.start(queue: queue)
    }

    deinit { monitor.cancel() }
    public func isOnline() async -> Bool { lock.withLock { online } }
}
#endif
