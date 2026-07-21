import Foundation
import Testing
@testable import AlMatchLifeCore

actor MockRealtimePeer: RealtimePeerConnection {
    private var handler: (@Sendable (Data) -> Void)?
    private(set) var clonedTrackAdded = false
    private(set) var remoteAnswer = ""
    private(set) var closed = false

    func setEventHandler(_ handler: @escaping @Sendable (Data) -> Void) async { self.handler = handler }
    func addClonedMicrophoneTrack() async throws { clonedTrackAdded = true }
    func createOffer() async throws -> String { "v=0\r\no=offer" }
    func setRemoteAnswer(_ sdp: String) async throws { remoteAnswer = sdp }
    func close() async { closed = true; handler = nil }
    func emit(_ json: String) { handler?(Data(json.utf8)) }
}

struct MockRealtimeFactory: RealtimePeerConnectionFactory {
    let peer: MockRealtimePeer
    func makePeerConnection() async throws -> any RealtimePeerConnection { peer }
}

struct MockSDPExchanger: RealtimeSDPExchanging {
    func exchange(offer: String, session: RealtimeSession) async throws -> String {
        #expect(offer.hasPrefix("v=0"))
        #expect(session.clientSecret == "ek_short")
        return "v=0\r\no=answer"
    }
}

actor TranscriptRecorder {
    private(set) var values: [RealtimeTranscript] = []
    func append(_ value: RealtimeTranscript) { values.append(value) }
}

@Test func realtimeTransportConnectsConsumesTranscriptAndCloses() async throws {
    let peer = MockRealtimePeer()
    let recorder = TranscriptRecorder()
    let session = RealtimeSession(
        clientSecret: "ek_short", expiresAt: 2_000, model: "gpt-realtime",
        transcriptionModel: "gpt-4o-mini-transcribe", transport: "webrtc",
        callsEndpoint: URL(string: "https://api.openai.com/v1/realtime/calls")!, sourceLanguage: "de"
    )
    let transport = OpenAIRealtimeSpeechTransport(
        factory: MockRealtimeFactory(peer: peer), exchanger: MockSDPExchanger(),
        sessionProvider: { session },
        transcriptHandler: { await recorder.append($0) }, errorHandler: { _ in }, now: { 1_000 }
    )

    try await transport.start()
    #expect(await peer.clonedTrackAdded)
    #expect(await peer.remoteAnswer.hasPrefix("v=0"))
    await peer.emit(#"{"type":"conversation.item.input_audio_transcription.delta","item_id":"one","delta":"Hal"}"#)
    await peer.emit(#"{"type":"conversation.item.input_audio_transcription.completed","item_id":"one","transcript":"Hallo"}"#)
    try await Task.sleep(for: .milliseconds(20))
    #expect(await recorder.values.last == RealtimeTranscript(itemID: "one", text: "Hallo", isFinal: true))

    await transport.stop()
    #expect(await peer.closed)
}

@Test func realtimeTransportRejectsExpiredCredentialBeforePeerCreation() async {
    let peer = MockRealtimePeer()
    let session = RealtimeSession(
        clientSecret: "ek_old", expiresAt: 1_004, model: "gpt-realtime",
        transcriptionModel: "gpt-4o-mini-transcribe", transport: "webrtc",
        callsEndpoint: URL(string: "https://api.openai.com/v1/realtime/calls")!, sourceLanguage: "auto"
    )
    let transport = OpenAIRealtimeSpeechTransport(
        factory: MockRealtimeFactory(peer: peer), exchanger: MockSDPExchanger(),
        sessionProvider: { session }, transcriptHandler: { _ in }, errorHandler: { _ in }, now: { 1_000 }
    )
    await #expect(throws: RealtimeTransportError.expiredCredential) { try await transport.start() }
    #expect(await peer.clonedTrackAdded == false)
}
