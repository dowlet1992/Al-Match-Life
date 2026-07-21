from types import SimpleNamespace

from backend.services.turn_credential_service import FALLBACK_ICE_SERVERS, TurnCredentialService


class FakeTokens:
    def __init__(self, ice_servers):
        self.ice_servers = ice_servers
        self.calls = []

    def create(self, **options):
        self.calls.append(options)
        return SimpleNamespace(ice_servers=self.ice_servers)


def test_turn_service_returns_and_caches_ephemeral_credentials():
    tokens = FakeTokens([
        {"urls": "stun:global.stun.twilio.com:3478"},
        {"urls": "turn:global.turn.twilio.com:443?transport=tcp", "username": "temporary", "credential": "secret"},
    ])
    service = TurnCredentialService(SimpleNamespace(tokens=tokens))

    first = service.get_ice_configuration("alice::room", now=100)
    second = service.get_ice_configuration("alice::room", now=200)

    assert first["provider"] == "twilio"
    assert first["ttl"] == 3600
    assert first["expires_at"] == 3700
    assert first["cached"] is False
    assert second["cached"] is True
    assert len(tokens.calls) == 1
    assert tokens.calls[0] == {"ttl": 3600}
    assert "account_sid" not in first
    assert "auth_token" not in first


def test_turn_service_rejects_incomplete_or_unsafe_provider_entries():
    tokens = FakeTokens([
        {"urls": "https://not-an-ice-server.example.com"},
        {"urls": "turn:relay.example.com", "username": "", "credential": ""},
    ])
    service = TurnCredentialService(SimpleNamespace(tokens=tokens))

    result = service.get_ice_configuration("alice::room", now=100)

    assert result["provider"] == "stun_fallback"
    assert result["ice_servers"] == FALLBACK_ICE_SERVERS


def test_turn_service_falls_back_without_provider():
    result = TurnCredentialService().get_ice_configuration("alice::room", now=100)

    assert result["provider"] == "stun_fallback"
    assert result["ttl"] == 0
    assert result["ice_servers"] == FALLBACK_ICE_SERVERS
