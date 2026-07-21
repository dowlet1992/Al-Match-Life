import Foundation

public struct MobileBootstrap: Decodable, Sendable {
    public let ok: Bool
    public let apiVersion: Int
    public let features: Features
    public let languages: Languages
    public let callContract: CallContract
    public let speechTranslationContract: SpeechTranslationContract

    enum CodingKeys: String, CodingKey {
        case ok, features, languages
        case apiVersion = "api_version"
        case callContract = "call_contract"
        case speechTranslationContract = "speech_translation_contract"
    }
}

public struct Features: Decodable, Sendable {
    public let liveCallCaptions: Bool
    public let serverTranscriptionConsent: Bool
    public let aiVoiceTranslationConsent: Bool
    public let realtimeSpeechProviderAvailable: Bool

    enum CodingKeys: String, CodingKey {
        case liveCallCaptions = "live_call_captions"
        case serverTranscriptionConsent = "server_transcription_consent"
        case aiVoiceTranslationConsent = "ai_voice_translation_consent"
        case realtimeSpeechProviderAvailable = "realtime_speech_provider_available"
    }
}

public struct Languages: Decodable, Sendable {
    public let ui: String
    public let callSpoken: String
    public let callCaptionTarget: String

    enum CodingKeys: String, CodingKey {
        case ui
        case callSpoken = "call_spoken"
        case callCaptionTarget = "call_caption_target"
    }
}

public struct CallContract: Decodable, Sendable {
    public let realtimeSessionEndpointTemplate: String
    public let translatedSpeechEndpointTemplate: String

    enum CodingKeys: String, CodingKey {
        case realtimeSessionEndpointTemplate = "realtime_session_endpoint_template"
        case translatedSpeechEndpointTemplate = "translated_speech_endpoint_template"
    }
}

public struct SpeechTranslationContract: Decodable, Sendable {
    public let version: Int
    public let states: [SpeechEngineState]
    public let transitions: [String: [SpeechEngineState]]
    public let realtimeEvents: [String: String]

    enum CodingKeys: String, CodingKey {
        case version, states, transitions
        case realtimeEvents = "realtime_events"
    }
}

public struct RealtimeSessionEnvelope: Decodable, Sendable {
    public let ok: Bool
    public let session: RealtimeSession
}

public struct RealtimeSession: Decodable, Sendable {
    public let clientSecret: String
    public let expiresAt: Int
    public let model: String
    public let transcriptionModel: String
    public let transport: String
    public let callsEndpoint: URL
    public let sourceLanguage: String

    enum CodingKeys: String, CodingKey {
        case model, transport
        case clientSecret = "client_secret"
        case expiresAt = "expires_at"
        case transcriptionModel = "transcription_model"
        case callsEndpoint = "calls_endpoint"
        case sourceLanguage = "source_language"
    }
}
