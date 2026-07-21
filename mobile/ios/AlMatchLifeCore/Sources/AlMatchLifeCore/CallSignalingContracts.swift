import Foundation

public struct NativeICEServer: Decodable, Sendable, Equatable {
    public let urls: [String]
    public let username: String?
    public let credential: String?

    enum CodingKeys: String, CodingKey { case urls, username, credential }
    public init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        if let many = try? values.decode([String].self, forKey: .urls) { urls = many }
        else { urls = [try values.decode(String.self, forKey: .urls)] }
        username = try values.decodeIfPresent(String.self, forKey: .username)
        credential = try values.decodeIfPresent(String.self, forKey: .credential)
    }
}

public struct NativeICEConfiguration: Decodable, Sendable {
    public let ok: Bool
    public let iceServers: [NativeICEServer]
    public let provider: String
    public let expiresAt: Double
    enum CodingKeys: String, CodingKey {
        case ok, provider
        case iceServers = "ice_servers"
        case expiresAt = "expires_at"
    }
}

public struct NativeSignalPayload: Decodable, Sendable {
    public let type: String?
    public let sdp: String?
    public let candidate: String?
    public let sdpMid: String?
    public let sdpMLineIndex: Int?
    public let usernameFragment: String?
}

public struct NativeCallSignal: Decodable, Sendable {
    public let id: String
    public let type: String
    public let from: String
    public let to: String
    public let payload: NativeSignalPayload
    public let createdAt: Double
    enum CodingKeys: String, CodingKey { case id, type, from, to, payload; case createdAt = "created_at" }
}

public struct NativeSignalPoll: Decodable, Sendable {
    public let ok: Bool
    public let status: String
    public let messages: [NativeCallSignal]
    public let acknowledgedEventIDs: [String]
    public let serverTime: Double
    enum CodingKeys: String, CodingKey {
        case ok, status, messages
        case acknowledgedEventIDs = "acknowledged_event_ids"
        case serverTime = "server_time"
    }
}

public struct NativeSignalACK: Decodable, Sendable {
    public let ok: Bool
    public let acknowledgedEventIDs: [String]
    public let acknowledgedCount: Int
    enum CodingKeys: String, CodingKey {
        case ok
        case acknowledgedEventIDs = "acknowledged_event_ids"
        case acknowledgedCount = "acknowledged_count"
    }
}

public struct NativeICECandidate: Sendable, Equatable {
    public let candidate: String
    public let sdpMid: String?
    public let sdpMLineIndex: Int?
    public let usernameFragment: String?
    public init(candidate: String, sdpMid: String?, sdpMLineIndex: Int?, usernameFragment: String?) {
        self.candidate = candidate
        self.sdpMid = sdpMid
        self.sdpMLineIndex = sdpMLineIndex
        self.usernameFragment = usernameFragment
    }
}
