import Foundation

public struct SessionTokens: Codable, Sendable, Equatable {
    public let accessToken: String
    public let refreshToken: String

    public init(accessToken: String, refreshToken: String) {
        self.accessToken = accessToken
        self.refreshToken = refreshToken
    }

    enum CodingKeys: String, CodingKey {
        case accessToken = "access_token"
        case refreshToken = "refresh_token"
    }
}

public enum APIClientError: Error, Sendable, Equatable {
    case insecureBaseURL
    case unauthenticated
    case invalidResponse
    case httpStatus(Int)
    case invalidSyntheticSpeech
}

public protocol HTTPTransport: Sendable {
    func data(for request: URLRequest) async throws -> (Data, HTTPURLResponse)
}

public struct URLSessionHTTPTransport: HTTPTransport, Sendable {
    private let session: URLSession

    public init(session: URLSession = .shared) { self.session = session }

    public func data(for request: URLRequest) async throws -> (Data, HTTPURLResponse) {
        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse else { throw APIClientError.invalidResponse }
        return (data, http)
    }
}

public struct SyntheticSpeech: Sendable {
    public let data: Data
    public let captionID: String
    public let language: String
    public let voice: String
}

public struct CallSignalAcknowledgement: Decodable, Sendable {
    public let ok: Bool
    public let eventID: String
    public let duplicate: Bool
    enum CodingKeys: String, CodingKey { case ok, duplicate; case eventID = "event_id" }
}

public actor AuthenticatedAPIClient {
    private static let tokenAccount = "mobile-session-v1"
    private let baseURL: URL
    private let transport: any HTTPTransport
    private let tokenStore: any SecureTokenStoring
    private let decoder = JSONDecoder()
    private let encoder = JSONEncoder()
    private var refreshTask: Task<SessionTokens, Error>?

    public init(
        baseURL: URL,
        transport: any HTTPTransport = URLSessionHTTPTransport(),
        tokenStore: any SecureTokenStoring = KeychainTokenStore()
    ) throws {
        let isLocalhost = ["localhost", "127.0.0.1", "::1"].contains(baseURL.host?.lowercased() ?? "")
        guard baseURL.scheme?.lowercased() == "https" || (isLocalhost && baseURL.scheme == "http") else {
            throw APIClientError.insecureBaseURL
        }
        self.baseURL = baseURL
        self.transport = transport
        self.tokenStore = tokenStore
    }

    public func install(tokens: SessionTokens) throws {
        let data = try encoder.encode(tokens)
        guard let encoded = String(data: data, encoding: .utf8) else { throw APIClientError.invalidResponse }
        try tokenStore.save(encoded, account: Self.tokenAccount)
    }

    public func clearSession() throws {
        try tokenStore.delete(account: Self.tokenAccount)
    }

    public func bootstrap() async throws -> MobileBootstrap {
        let (data, _) = try await authenticatedRequest(path: "/api/mobile/bootstrap", method: "GET")
        return try decoder.decode(MobileBootstrap.self, from: data)
    }

    public func createRealtimeSession(callID: String, otherEmail: String, callType: String) async throws -> RealtimeSession {
        let body = try JSONSerialization.data(withJSONObject: ["other_email": otherEmail, "call_type": callType])
        let path = "/api/calls/\(encodePath(callID))/translation/realtime-session"
        let (data, _) = try await authenticatedRequest(path: path, method: "POST", body: body)
        return try decoder.decode(RealtimeSessionEnvelope.self, from: data).session
    }

    public func translatedSpeech(
        callID: String, captionID: String, otherEmail: String, callType: String, voice: String = "coral"
    ) async throws -> SyntheticSpeech {
        let body = try JSONSerialization.data(withJSONObject: [
            "other_email": otherEmail, "call_type": callType, "voice": voice,
        ])
        let path = "/api/calls/\(encodePath(callID))/captions/\(encodePath(captionID))/speech"
        let (data, response) = try await authenticatedRequest(path: path, method: "POST", body: body)
        guard response.value(forHTTPHeaderField: "X-AI-Generated-Voice") == "true",
              response.mimeType == "audio/mpeg",
              let responseCaptionID = response.value(forHTTPHeaderField: "X-Caption-Id"),
              responseCaptionID == captionID,
              let language = response.value(forHTTPHeaderField: "Content-Language"),
              let responseVoice = response.value(forHTTPHeaderField: "X-AI-Voice"),
              responseVoice == voice,
              !language.isEmpty,
              !data.isEmpty else {
            throw APIClientError.invalidSyntheticSpeech
        }
        return SyntheticSpeech(data: data, captionID: responseCaptionID, language: language, voice: responseVoice)
    }

    public func sendCallSignal(
        callID: String, otherEmail: String, callType: NativeCallType,
        type: String, eventID: String, payload: [String: String]
    ) async throws -> CallSignalAcknowledgement {
        let body = try JSONSerialization.data(withJSONObject: [
            "other_email": otherEmail, "call_type": callType.rawValue,
            "type": type, "event_id": eventID, "payload": payload,
        ])
        let path = "/api/calls/\(encodePath(callID))/signals"
        let (data, _) = try await authenticatedRequest(path: path, method: "POST", body: body)
        let acknowledgement = try decoder.decode(CallSignalAcknowledgement.self, from: data)
        guard acknowledgement.ok, acknowledgement.eventID == eventID else { throw APIClientError.invalidResponse }
        return acknowledgement
    }

    public func iceConfiguration(callID: String, otherEmail: String, callType: NativeCallType) async throws -> NativeICEConfiguration {
        let path = callPath(callID, suffix: "ice-servers", otherEmail: otherEmail, callType: callType, after: nil)
        let (data, _) = try await authenticatedRequest(path: path, method: "GET")
        return try decoder.decode(NativeICEConfiguration.self, from: data)
    }

    public func pollCallSignals(
        callID: String, otherEmail: String, callType: NativeCallType, after: Double
    ) async throws -> NativeSignalPoll {
        let path = callPath(callID, suffix: "signals", otherEmail: otherEmail, callType: callType, after: after)
        let (data, _) = try await authenticatedRequest(path: path, method: "GET")
        return try decoder.decode(NativeSignalPoll.self, from: data)
    }

    public func acknowledgeCallSignals(
        callID: String, otherEmail: String, callType: NativeCallType, eventIDs: [String]
    ) async throws -> NativeSignalACK {
        let body = try JSONSerialization.data(withJSONObject: [
            "other_email": otherEmail, "call_type": callType.rawValue, "event_ids": Array(eventIDs.prefix(50)),
        ])
        let path = "/api/calls/\(encodePath(callID))/signals/ack"
        let (data, _) = try await authenticatedRequest(path: path, method: "POST", body: body)
        return try decoder.decode(NativeSignalACK.self, from: data)
    }

    public func sendSessionDescription(
        callID: String, otherEmail: String, callType: NativeCallType, type: String, sdp: String, eventID: String
    ) async throws -> CallSignalAcknowledgement {
        let body = try JSONSerialization.data(withJSONObject: [
            "other_email": otherEmail, "call_type": callType.rawValue, "type": type, "event_id": eventID,
            "payload": ["type": type, "sdp": sdp, "call_type": callType.rawValue],
        ])
        let (data, _) = try await authenticatedRequest(
            path: "/api/calls/\(encodePath(callID))/signals", method: "POST", body: body
        )
        return try decoder.decode(CallSignalAcknowledgement.self, from: data)
    }

    public func sendICECandidate(
        callID: String, otherEmail: String, callType: NativeCallType,
        candidate: NativeICECandidate, eventID: String
    ) async throws -> CallSignalAcknowledgement {
        var candidatePayload: [String: Any] = ["candidate": candidate.candidate, "call_type": callType.rawValue]
        if let value = candidate.sdpMid { candidatePayload["sdpMid"] = value }
        if let value = candidate.sdpMLineIndex { candidatePayload["sdpMLineIndex"] = value }
        if let value = candidate.usernameFragment { candidatePayload["usernameFragment"] = value }
        let body = try JSONSerialization.data(withJSONObject: [
            "other_email": otherEmail, "call_type": callType.rawValue, "type": "ice",
            "event_id": eventID, "payload": candidatePayload,
        ])
        let (data, _) = try await authenticatedRequest(
            path: "/api/calls/\(encodePath(callID))/signals", method: "POST", body: body
        )
        return try decoder.decode(CallSignalAcknowledgement.self, from: data)
    }

    private func authenticatedRequest(
        path: String, method: String, body: Data? = nil, mayRefresh: Bool = true
    ) async throws -> (Data, HTTPURLResponse) {
        let tokens = try loadTokens()
        var request = try makeRequest(path: path, method: method, body: body)
        request.setValue("Bearer \(tokens.accessToken)", forHTTPHeaderField: "Authorization")
        let result = try await transport.data(for: request)
        if result.1.statusCode == 401 && mayRefresh {
            let refreshed = try await refreshTokens(staleAccessToken: tokens.accessToken)
            var retry = try makeRequest(path: path, method: method, body: body)
            retry.setValue("Bearer \(refreshed.accessToken)", forHTTPHeaderField: "Authorization")
            let retryResult = try await transport.data(for: retry)
            guard (200..<300).contains(retryResult.1.statusCode) else {
                throw APIClientError.httpStatus(retryResult.1.statusCode)
            }
            return retryResult
        }
        guard (200..<300).contains(result.1.statusCode) else { throw APIClientError.httpStatus(result.1.statusCode) }
        return result
    }

    private func refreshTokens(staleAccessToken: String) async throws -> SessionTokens {
        let current = try loadTokens()
        if current.accessToken != staleAccessToken { return current }
        if let refreshTask { return try await refreshTask.value }
        let baseURL = self.baseURL
        let transport = self.transport
        let refreshToken = current.refreshToken
        let task = Task<SessionTokens, Error> {
            var request = URLRequest(url: baseURL.appending(path: "/api/auth/refresh"))
            request.httpMethod = "POST"
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.setValue("application/json", forHTTPHeaderField: "Accept")
            request.httpBody = try JSONSerialization.data(withJSONObject: ["refresh_token": refreshToken])
            let (data, response) = try await transport.data(for: request)
            guard (200..<300).contains(response.statusCode) else { throw APIClientError.unauthenticated }
            return try JSONDecoder().decode(SessionTokens.self, from: data)
        }
        refreshTask = task
        do {
            let tokens = try await task.value
            try install(tokens: tokens)
            refreshTask = nil
            return tokens
        } catch {
            refreshTask = nil
            try? clearSession()
            throw error
        }
    }

    private func loadTokens() throws -> SessionTokens {
        guard let encoded = try tokenStore.read(account: Self.tokenAccount),
              let data = encoded.data(using: .utf8) else { throw APIClientError.unauthenticated }
        return try decoder.decode(SessionTokens.self, from: data)
    }

    private func makeRequest(path: String, method: String, body: Data?) throws -> URLRequest {
        guard let url = URL(string: path, relativeTo: baseURL)?.absoluteURL,
              url.host == baseURL.host else { throw APIClientError.invalidResponse }
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue("no-store", forHTTPHeaderField: "Cache-Control")
        if let body {
            request.httpBody = body
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }
        return request
    }

    private func callPath(
        _ callID: String, suffix: String, otherEmail: String, callType: NativeCallType, after: Double?
    ) -> String {
        var components = URLComponents()
        components.path = "/api/calls/\(encodePath(callID))/\(suffix)"
        var items = [URLQueryItem(name: "other_email", value: otherEmail), URLQueryItem(name: "call_type", value: callType.rawValue)]
        if let after { items.append(URLQueryItem(name: "after", value: String(after))) }
        components.queryItems = items
        return components.string ?? ""
    }

    private func encodePath(_ value: String) -> String {
        value.addingPercentEncoding(withAllowedCharacters: .alphanumerics) ?? ""
    }
}
