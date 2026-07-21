import Foundation
import Testing
@testable import AlMatchLifeCore

final class MemoryTokenStore: SecureTokenStoring, @unchecked Sendable {
    private let lock = NSLock()
    private var values: [String: String] = [:]

    func save(_ token: String, account: String) throws {
        lock.withLock { values[account] = token }
    }

    func read(account: String) throws -> String? {
        lock.withLock { values[account] }
    }

    func delete(account: String) throws {
        lock.withLock { values.removeValue(forKey: account) }
    }
}

actor ScriptedTransport: HTTPTransport {
    struct Reply: Sendable { let status: Int; let data: Data; let headers: [String: String] }
    private var replies: [Reply]
    private(set) var requests: [URLRequest] = []

    init(_ replies: [Reply]) { self.replies = replies }

    func data(for request: URLRequest) async throws -> (Data, HTTPURLResponse) {
        requests.append(request)
        let reply = replies.removeFirst()
        let response = HTTPURLResponse(
            url: request.url!, statusCode: reply.status, httpVersion: "HTTP/1.1", headerFields: reply.headers
        )!
        return (reply.data, response)
    }
}

@Test func rejectsNonTLSProductionBaseURL() {
    #expect(throws: APIClientError.insecureBaseURL) {
        _ = try AuthenticatedAPIClient(baseURL: URL(string: "http://api.example.com")!)
    }
}

@Test func refreshesOnceAndRetriesWithRotatedAccessToken() async throws {
    let bootstrap = Data(#"{"ok":true,"api_version":1,"features":{"live_call_captions":true,"server_transcription_consent":true,"ai_voice_translation_consent":false,"realtime_speech_provider_available":true},"languages":{"ui":"en","call_spoken":"auto","call_caption_target":"en"},"call_contract":{"realtime_session_endpoint_template":"/r","translated_speech_endpoint_template":"/s"},"speech_translation_contract":{"version":1,"states":["idle"],"transitions":{"idle":[]},"realtime_events":{}}}"#.utf8)
    let transport = ScriptedTransport([
        .init(status: 401, data: Data(), headers: [:]),
        .init(status: 200, data: Data(#"{"access_token":"new-access","refresh_token":"new-refresh"}"#.utf8), headers: ["Content-Type": "application/json"]),
        .init(status: 200, data: bootstrap, headers: ["Content-Type": "application/json"]),
    ])
    let client = try AuthenticatedAPIClient(
        baseURL: URL(string: "https://api.example.com")!, transport: transport, tokenStore: MemoryTokenStore()
    )
    try await client.install(tokens: SessionTokens(accessToken: "old-access", refreshToken: "old-refresh"))

    _ = try await client.bootstrap()

    let requests = await transport.requests
    #expect(requests.count == 3)
    #expect(requests[0].value(forHTTPHeaderField: "Authorization") == "Bearer old-access")
    #expect(requests[1].url?.path == "/api/auth/refresh")
    #expect(requests[2].value(forHTTPHeaderField: "Authorization") == "Bearer new-access")
}

@Test func validatesSyntheticSpeechIdentityHeaders() async throws {
    let store = MemoryTokenStore()
    let transport = ScriptedTransport([.init(
        status: 200,
        data: Data("ID3audio".utf8),
        headers: [
            "Content-Type": "audio/mpeg", "X-AI-Generated-Voice": "true",
            "X-AI-Voice": "coral", "X-Caption-Id": "caption-1", "Content-Language": "en",
        ]
    )])
    let client = try AuthenticatedAPIClient(
        baseURL: URL(string: "https://api.example.com")!, transport: transport, tokenStore: store
    )
    try await client.install(tokens: SessionTokens(accessToken: "access", refreshToken: "refresh"))

    let speech = try await client.translatedSpeech(
        callID: "room-1", captionID: "caption-1", otherEmail: "other@example.com", callType: "audio"
    )
    #expect(speech.voice == "coral")
    #expect(speech.language == "en")
}
