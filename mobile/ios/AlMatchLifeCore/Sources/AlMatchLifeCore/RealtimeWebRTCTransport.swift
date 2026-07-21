import Foundation

public enum RealtimeTransportError: Error, Sendable, Equatable {
    case alreadyRunning
    case expiredCredential
    case invalidProviderEndpoint
    case invalidCredential
    case invalidOffer
    case invalidAnswer
    case providerStatus(Int)
}

public protocol RealtimePeerConnection: AnyObject, Sendable {
    func setEventHandler(_ handler: @escaping @Sendable (Data) -> Void) async
    func addClonedMicrophoneTrack() async throws
    func createOffer() async throws -> String
    func setRemoteAnswer(_ sdp: String) async throws
    func close() async
}

public protocol RealtimePeerConnectionFactory: Sendable {
    func makePeerConnection() async throws -> any RealtimePeerConnection
}

public protocol RealtimeSDPExchanging: Sendable {
    func exchange(offer: String, session: RealtimeSession) async throws -> String
}

public struct URLSessionRealtimeSDPExchanger: RealtimeSDPExchanging, Sendable {
    public static let maximumSDPBytes = 64 * 1024
    private let transport: any HTTPTransport

    public init(transport: any HTTPTransport = URLSessionHTTPTransport()) {
        self.transport = transport
    }

    public func exchange(offer: String, session: RealtimeSession) async throws -> String {
        guard session.callsEndpoint.scheme == "https",
              session.callsEndpoint.host?.lowercased() == "api.openai.com",
              session.callsEndpoint.path == "/v1/realtime/calls" else {
            throw RealtimeTransportError.invalidProviderEndpoint
        }
        guard !session.clientSecret.isEmpty,
              !session.clientSecret.contains("\r"), !session.clientSecret.contains("\n") else {
            throw RealtimeTransportError.invalidCredential
        }
        guard offer.hasPrefix("v=0"),
              let offerData = offer.data(using: .utf8),
              offerData.count <= Self.maximumSDPBytes else {
            throw RealtimeTransportError.invalidOffer
        }

        let boundary = "AlMatchLife-\(UUID().uuidString)"
        var body = Data()
        body.append("--\(boundary)\r\n".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"sdp\"; filename=\"offer.sdp\"\r\n".data(using: .utf8)!)
        body.append("Content-Type: application/sdp\r\n\r\n".data(using: .utf8)!)
        body.append(offerData)
        body.append("\r\n--\(boundary)--\r\n".data(using: .utf8)!)

        var request = URLRequest(url: session.callsEndpoint)
        request.httpMethod = "POST"
        request.setValue("Bearer \(session.clientSecret)", forHTTPHeaderField: "Authorization")
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        request.setValue("application/sdp", forHTTPHeaderField: "Accept")
        request.setValue("no-store", forHTTPHeaderField: "Cache-Control")
        request.httpBody = body
        let (data, response) = try await transport.data(for: request)
        guard (200..<300).contains(response.statusCode) else {
            throw RealtimeTransportError.providerStatus(response.statusCode)
        }
        guard data.count <= Self.maximumSDPBytes,
              let answer = String(data: data, encoding: .utf8),
              answer.hasPrefix("v=0") else {
            throw RealtimeTransportError.invalidAnswer
        }
        return answer
    }
}

public struct RealtimeTranscript: Sendable, Equatable {
    public let itemID: String
    public let text: String
    public let isFinal: Bool
}

public actor OpenAIRealtimeSpeechTransport: RealtimeSpeechTransport {
    public typealias SessionProvider = @Sendable () async throws -> RealtimeSession
    public typealias TranscriptHandler = @Sendable (RealtimeTranscript) async -> Void
    public typealias ErrorHandler = @Sendable (String) async -> Void

    private let factory: any RealtimePeerConnectionFactory
    private let exchanger: any RealtimeSDPExchanging
    private let sessionProvider: SessionProvider
    private let transcriptHandler: TranscriptHandler
    private let errorHandler: ErrorHandler
    private let now: @Sendable () -> Int
    private var peer: (any RealtimePeerConnection)?
    private var partials: [String: String] = [:]

    public init(
        factory: any RealtimePeerConnectionFactory,
        exchanger: any RealtimeSDPExchanging = URLSessionRealtimeSDPExchanger(),
        sessionProvider: @escaping SessionProvider,
        transcriptHandler: @escaping TranscriptHandler,
        errorHandler: @escaping ErrorHandler,
        now: @escaping @Sendable () -> Int = { Int(Date().timeIntervalSince1970) }
    ) {
        self.factory = factory
        self.exchanger = exchanger
        self.sessionProvider = sessionProvider
        self.transcriptHandler = transcriptHandler
        self.errorHandler = errorHandler
        self.now = now
    }

    public func start() async throws {
        guard peer == nil else { throw RealtimeTransportError.alreadyRunning }
        let session = try await sessionProvider()
        guard session.expiresAt > now() + 5 else { throw RealtimeTransportError.expiredCredential }
        let candidate = try await factory.makePeerConnection()
        do {
            await candidate.setEventHandler { [weak self] data in
                Task { await self?.consumeEvent(data) }
            }
            try await candidate.addClonedMicrophoneTrack()
            let offer = try await candidate.createOffer()
            let answer = try await exchanger.exchange(offer: offer, session: session)
            try await candidate.setRemoteAnswer(answer)
            peer = candidate
        } catch {
            await candidate.close()
            throw error
        }
    }

    public func stop() async {
        let current = peer
        peer = nil
        partials.removeAll(keepingCapacity: false)
        await current?.setEventHandler { _ in }
        await current?.close()
    }

    private func consumeEvent(_ data: Data) async {
        guard let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let type = object["type"] as? String else { return }
        let itemID = (object["item_id"] as? String) ?? "current"
        switch type {
        case "conversation.item.input_audio_transcription.delta":
            let text = partials[itemID, default: ""] + ((object["delta"] as? String) ?? "")
            partials[itemID] = text
            if !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                await transcriptHandler(.init(itemID: itemID, text: text, isFinal: false))
            }
        case "conversation.item.input_audio_transcription.completed":
            let text = ((object["transcript"] as? String) ?? partials[itemID] ?? "")
                .trimmingCharacters(in: .whitespacesAndNewlines)
            partials.removeValue(forKey: itemID)
            if !text.isEmpty {
                await transcriptHandler(.init(itemID: itemID, text: text, isFinal: true))
            }
        case "error":
            let error = object["error"] as? [String: Any]
            await errorHandler((error?["code"] as? String) ?? "realtime_provider_error")
        default:
            break
        }
    }
}
