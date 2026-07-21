from backend.services import mobile_speech_contract_service as service


def test_mobile_speech_contract_has_valid_declared_transitions():
    contract = service.build_contract()
    states = set(contract["states"])
    assert set(contract["transitions"]) == states
    assert all(set(targets) <= states for targets in contract["transitions"].values())
    assert contract["realtime_events"]["final"].endswith(".completed")


def test_mobile_speech_contract_is_privacy_safe_and_bounded():
    contract = service.build_contract()
    assert contract["audio_policy"]["raw_audio_persisted"] is False
    assert contract["audio_policy"]["speech_queue_max_items"] == 2
    assert contract["fallback_policy"]["max_consecutive_failures"] == 3
    assert "api_key" not in str(contract).lower().replace("provider_api_key_exposed", "")
