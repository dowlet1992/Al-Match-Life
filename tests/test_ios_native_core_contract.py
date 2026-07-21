from pathlib import Path


ROOT = Path(__file__).resolve().parents[1] / "mobile" / "ios" / "AlMatchLifeCore"


def test_ios_core_has_real_swift_package_and_no_embedded_credentials():
    files = list(ROOT.rglob("*.swift"))
    combined = "\n".join(path.read_text(encoding="utf-8") for path in files)
    assert (ROOT / "Package.swift").exists()
    assert "OPENAI_API_KEY" not in combined
    assert "clientSecret" in combined
    assert "KeychainTokenStore" in combined
    assert "kSecAttrAccessibleWhenUnlockedThisDeviceOnly" in combined


def test_ios_state_machine_matches_server_native_contract():
    source = (ROOT / "Sources/AlMatchLifeCore/SpeechEngineState.swift").read_text(encoding="utf-8")
    for state in ("idle", "connecting", "streaming", "fallback", "stopping", "stopped", "failed"):
        assert state in source
    assert ".streaming: [.fallback, .stopping, .failed]" in source
    assert "await realtime.stop()" in source
    assert "await fallback.stop()" in source


def test_ios_contract_decoding_is_typed_and_versioned():
    source = (ROOT / "Sources/AlMatchLifeCore/MobileContracts.swift").read_text(encoding="utf-8")
    assert "struct MobileBootstrap: Decodable, Sendable" in source
    assert "speechTranslationContract" in source
    assert "struct RealtimeSession: Decodable, Sendable" in source
    assert "callsEndpoint: URL" in source


def test_ios_api_client_rotates_tokens_single_flight_and_validates_speech():
    source = (ROOT / "Sources/AlMatchLifeCore/AuthenticatedAPIClient.swift").read_text(encoding="utf-8")
    assert "private var refreshTask: Task<SessionTokens, Error>?" in source
    assert "if let refreshTask { return try await refreshTask.value }" in source
    assert '"/api/auth/refresh"' in source
    assert "try install(tokens: tokens)" in source
    assert 'value(forHTTPHeaderField: "X-AI-Generated-Voice") == "true"' in source
    assert "responseCaptionID == captionID" in source
    assert "responseVoice == voice" in source
    assert "case insecureBaseURL" in source


def test_keychain_updates_existing_bundle_without_delete_first_gap():
    source = (ROOT / "Sources/AlMatchLifeCore/SecureTokenStore.swift").read_text(encoding="utf-8")
    save_body = source.split("public func save", 1)[1].split("public func read", 1)[0]
    assert "SecItemUpdate" in save_body
    assert "try delete" not in save_body


def test_ios_realtime_transport_isolated_track_sdp_and_cleanup_contract():
    source = (ROOT / "Sources/AlMatchLifeCore/RealtimeWebRTCTransport.swift").read_text(encoding="utf-8")
    assert "addClonedMicrophoneTrack" in source
    assert 'host?.lowercased() == "api.openai.com"' in source
    assert 'path == "/v1/realtime/calls"' in source
    assert "maximumSDPBytes = 64 * 1024" in source
    assert 'name=\\"sdp\\"; filename=\\"offer.sdp\\"' in source
    assert "session.expiresAt > now() + 5" in source
    assert "await candidate.close()" in source
    assert "partials.removeAll" in source


def test_ios_realtime_transport_consumes_only_expected_provider_events():
    source = (ROOT / "Sources/AlMatchLifeCore/RealtimeWebRTCTransport.swift").read_text(encoding="utf-8")
    assert "conversation.item.input_audio_transcription.delta" in source
    assert "conversation.item.input_audio_transcription.completed" in source
    assert 'case "error"' in source
    assert "transcriptHandler" in source


def test_ios_audio_session_uses_voice_chat_bluetooth_and_restores_other_audio():
    source = (ROOT / "Sources/AlMatchLifeCore/CallAudioSessionController.swift").read_text(encoding="utf-8")
    assert "callType == .video ? .videoChat : .voiceChat" in source
    assert "setCategory(.playAndRecord, mode: mode" in source
    assert ".allowBluetoothHFP" in source
    assert "setPreferredSampleRate(48_000)" in source
    assert "setPreferredIOBufferDuration(0.01)" in source
    assert "overrideOutputAudioPort(enabled ? .speaker : .none)" in source
    assert ".notifyOthersOnDeactivation" in source
    assert "guard isActive else { return }" in source


def test_ios_voip_payload_is_expiring_receiver_bound_and_deterministic():
    source = (ROOT / "Sources/AlMatchLifeCore/VoIPCallCoordinator.swift").read_text(encoding="utf-8")
    assert "receiverEmail == currentEmail" in source
    assert "expiresAt >= now, expiresAt <= now + 180" in source
    assert "SHA256.hash" in source
    assert "maximumSeenEvents = 256" in source
    assert "seenEventIDs.contains(payload.eventID)" in source
    assert "active.removeValue(forKey: payload.uuid)" in source
    assert "await lifecycle.stop" in source


def test_ios_callkit_pushkit_bridge_reports_actions_and_avoids_lock_screen_pii():
    source = (ROOT / "Sources/AlMatchLifeCore/IOSCallKitPushKitBridge.swift").read_text(encoding="utf-8")
    assert 'CXHandle(type: .generic, value: "Al Match Life")' in source
    assert "reportNewIncomingCall" in source
    assert "CXAnswerCallAction" in source
    assert "CXEndCallAction" in source
    assert "coordinator.resetAll()" in source
    assert "desiredPushTypes = [.voIP]" in source
    assert "didInvalidatePushTokenFor" in source
    assert "defer { completion() }" in source
    assert "payload.dictionaryPayload" in source


def test_ios_native_lifecycle_orders_critical_layers_and_keeps_ai_optional():
    source = (ROOT / "Sources/AlMatchLifeCore/ProductionNativeCallLifecycle.swift").read_text(encoding="utf-8")
    accepted = source.index("type: .accepted")
    audio = source.index("audio.activate", accepted)
    media = source.index("media.start", audio)
    captions = source.index("captions.start", media)
    assert accepted < audio < media < captions
    assert "await optionalFeatureError(error)" in source
    assert "rollbackAfterAccept" in source
    assert source.index("captions.stop", source.index("rollbackAfterAccept")) < source.index("media.stop", source.index("rollbackAfterAccept"))
    assert '"ios_" + UUID().uuidString.lowercased()' in source


def test_ios_signaling_acknowledgement_must_match_original_event():
    source = (ROOT / "Sources/AlMatchLifeCore/AuthenticatedAPIClient.swift").read_text(encoding="utf-8")
    assert "acknowledgement.eventID == eventID" in source
    assert '"event_id": eventID' in source
    assert '"type": type' in source


def test_ios_primary_webrtc_loads_turn_before_peer_and_acks_after_processing():
    source = (ROOT / "Sources/AlMatchLifeCore/IncomingPersonWebRTCTransport.swift").read_text(encoding="utf-8")
    ice = source.index("signaling.ice(for: payload)")
    peer = source.index("factory.make(configuration: configuration)")
    media = source.index("candidate.addLocalMedia", peer)
    assert ice < peer < media
    process = source.index("try await process(message)")
    remember = source.index("remember(message.id)", process)
    ack = source.index("signaling.acknowledge", remember)
    assert process < remember < ack
    assert "result.serverTime - 1" in source
    assert "processedIDs.count > 600" in source
    assert "pendingACKIDs" in source


def test_ios_primary_webrtc_queues_ice_and_has_bounded_retry_backoff():
    source = (ROOT / "Sources/AlMatchLifeCore/IncomingPersonWebRTCTransport.swift").read_text(encoding="utf-8")
    assert "pendingLocalCandidates.count > 128" in source
    assert "guard localDescriptionPublished" in source
    assert "flushLocalCandidates" in source
    assert "pendingLocalCandidates.append(contentsOf: queued[index...])" in source
    assert "min(800 * (1 << min(consecutiveFailures, 3)), 6_400)" in source
    assert "await current?.close()" in source


def test_ios_signaling_contracts_are_typed_and_ack_batch_is_bounded():
    contracts = (ROOT / "Sources/AlMatchLifeCore/CallSignalingContracts.swift").read_text(encoding="utf-8")
    client = (ROOT / "Sources/AlMatchLifeCore/AuthenticatedAPIClient.swift").read_text(encoding="utf-8")
    assert "struct NativeICEConfiguration: Decodable, Sendable" in contracts
    assert "struct NativeCallSignal: Decodable, Sendable" in contracts
    assert "Array(eventIDs.prefix(50))" in client
    assert "URLQueryItem(name: \"other_email\"" in client


def test_google_webrtc_adapter_is_conditional_unified_plan_and_turn_configured():
    source = (ROOT / "Sources/AlMatchLifeCore/GoogleWebRTCPersonPeerAdapter.swift").read_text(encoding="utf-8")
    assert "#if canImport(WebRTC) && os(iOS)" in source
    assert "RTCDefaultVideoEncoderFactory" in source
    assert "RTCDefaultVideoDecoderFactory" in source
    assert "rtcConfiguration.sdpSemantics = .unifiedPlan" in source
    assert "rtcConfiguration.iceServers = configuration.iceServers.map" in source
    assert "continualGatheringPolicy = .gatherContinually" in source
    assert "RTCCleanupSSL" not in source


def test_google_webrtc_adapter_media_is_bounded_and_cleans_capturer():
    source = (ROOT / "Sources/AlMatchLifeCore/GoogleWebRTCPersonPeerAdapter.swift").read_text(encoding="utf-8")
    assert '"googEchoCancellation": "true"' in source
    assert '"googNoiseSuppression": "true"' in source
    assert "size.width <= 1280 && size.height <= 720" in source
    assert "min(Int(maxFPS), 30)" in source
    assert "receiveLocalVideoTrack(videoTrack)" in source
    assert "didStartReceivingOn transceiver" in source
    assert "capturer.stopCapture" in source
    assert "values.0?.close()" in source


def test_ios_connection_recovery_is_offline_aware_bounded_and_injectable():
    source = (ROOT / "Sources/AlMatchLifeCore/IncomingPersonWebRTCTransport.swift").read_text(encoding="utf-8")
    network = (ROOT / "Sources/AlMatchLifeCore/NWPathNetworkStatus.swift").read_text(encoding="utf-8")
    assert "protocol RecoverySleeping" in source
    assert "sleeper.sleep(milliseconds: delayMilliseconds)" in source
    assert "guard await network.isOnline()" in source
    assert "recoveryAttempts >= 3" in source
    assert "delayMilliseconds = 1_000" in source
    assert "min(5_000 * (recoveryAttempts + 1), 10_000)" in source
    assert "failureHandler(PersonWebRTCTransportError.recoveryExhausted)" in source
    assert "NWPathMonitor" in network
    assert "path.status == .satisfied" in network
    assert "enum CallRecoveryStatus" in source
    assert "recoveryStatusHandler(.waitingForNetwork)" in source
    assert "recoveryStatusHandler(.failed)" in source


def test_ios_recovery_failure_has_one_connection_lost_terminal_path():
    coordinator = (ROOT / "Sources/AlMatchLifeCore/VoIPCallCoordinator.swift").read_text(encoding="utf-8")
    lifecycle = (ROOT / "Sources/AlMatchLifeCore/ProductionNativeCallLifecycle.swift").read_text(encoding="utf-8")
    assert "func connectionFailed(uuid: UUID)" in coordinator
    assert "await lifecycle.connectionLost(payload)" in coordinator
    assert "await system.reportEnded(uuid: uuid, reason: .failed)" in coordinator
    assert 'reason: "connection_lost"' in lifecycle
    assert 'if reason == "connection_lost"' in lifecycle


def test_ios_recovery_router_is_late_bound_thread_safe_and_once_only():
    source = (ROOT / "Sources/AlMatchLifeCore/CallRecoveryRouter.swift").read_text(encoding="utf-8")
    assert "private let lock = NSLock()" in source
    assert "func bind(coordinator: VoIPCallCoordinator)" in source
    assert "guard !self.failureDelivered, let coordinator = self.coordinator else { return nil }" in source
    assert "self.failureDelivered = true" in source
    assert "connectionFailed(uuid: self.callUUID)" in source
    assert "present(status, callUUID: self.callUUID)" in source


def test_google_webrtc_maps_native_ice_connection_states():
    source = (ROOT / "Sources/AlMatchLifeCore/GoogleWebRTCPersonPeerAdapter.swift").read_text(encoding="utf-8")
    assert "case .checking: .connecting" in source
    assert "case .connected, .completed: .connected" in source
    assert "case .disconnected: .disconnected" in source
    assert "case .failed: .failed" in source
