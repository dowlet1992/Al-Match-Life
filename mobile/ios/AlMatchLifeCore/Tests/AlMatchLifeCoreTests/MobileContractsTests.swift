import Foundation
import Testing
@testable import AlMatchLifeCore

@Test func decodesProductionSpeechContractAndEphemeralSession() throws {
    let bootstrapJSON = #"""
    {
      "ok": true,
      "api_version": 1,
      "features": {
        "live_call_captions": true,
        "server_transcription_consent": true,
        "ai_voice_translation_consent": true,
        "realtime_speech_provider_available": true
      },
      "languages": {"ui":"en","call_spoken":"de","call_caption_target":"en"},
      "call_contract": {
        "realtime_session_endpoint_template":"/api/calls/{call_id}/translation/realtime-session",
        "translated_speech_endpoint_template":"/api/calls/{call_id}/captions/{caption_id}/speech"
      },
      "speech_translation_contract": {
        "version":1,
        "states":["idle","connecting","streaming","fallback","stopping","stopped","failed"],
        "transitions":{"streaming":["fallback","stopping","failed"]},
        "realtime_events":{"partial":"delta","final":"completed","error":"error"}
      }
    }
    """#
    let bootstrap = try JSONDecoder().decode(MobileBootstrap.self, from: Data(bootstrapJSON.utf8))
    #expect(bootstrap.speechTranslationContract.version == 1)
    #expect(bootstrap.speechTranslationContract.transitions["streaming"] == [.fallback, .stopping, .failed])

    let sessionJSON = #"""
    {"ok":true,"session":{"client_secret":"ek_short","expires_at":1900000000,
    "model":"gpt-realtime","transcription_model":"gpt-4o-mini-transcribe",
    "transport":"webrtc","calls_endpoint":"https://api.openai.com/v1/realtime/calls",
    "source_language":"de"}}
    """#
    let envelope = try JSONDecoder().decode(RealtimeSessionEnvelope.self, from: Data(sessionJSON.utf8))
    #expect(envelope.session.clientSecret == "ek_short")
    #expect(envelope.session.callsEndpoint.host == "api.openai.com")
}
