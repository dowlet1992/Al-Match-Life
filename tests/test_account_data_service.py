from backend.services import account_data_service


class FakeUser:
    def info(self):
        return {
            "email": "alice@example.com",
            "name": "Alice",
            "password": "secret",
        }


def test_safe_account_payload_removes_password():
    payload = account_data_service.safe_account_payload(FakeUser())

    assert payload == {
        "email": "alice@example.com",
        "name": "Alice",
    }


def test_social_snapshot_for_email_keeps_only_related_edges():
    social_data = {
        "friends": [
            {"user": "alice@example.com", "friend": "bob@example.com"},
            {"user": "bob@example.com", "friend": "carol@example.com"},
        ],
        "follows": [
            {"follower": "bob@example.com", "following": "alice@example.com"},
            {"follower": "bob@example.com", "following": "carol@example.com"},
        ],
        "friend_requests": [
            {"from": "alice@example.com", "to": "dana@example.com"},
            {"from": "bob@example.com", "to": "carol@example.com"},
        ],
    }

    assert account_data_service.social_snapshot_for_email(social_data, "ALICE@example.com") == {
        "friends": [{"user": "alice@example.com", "friend": "bob@example.com"}],
        "follows": [{"follower": "bob@example.com", "following": "alice@example.com"}],
        "friend_requests": [{"from": "alice@example.com", "to": "dana@example.com"}],
    }


def test_relationship_snapshot_and_cleanup_for_email():
    data = {
        "blocks": {
            "alice@example.com": ["bob@example.com"],
            "bob@example.com": ["alice@example.com", "carol@example.com"],
            "carol@example.com": ["dana@example.com"],
        }
    }

    assert account_data_service.relationship_snapshot_for_email(data, "blocks", "alice@example.com") == {
        "blocks": {
            "alice@example.com": ["bob@example.com"],
            "bob@example.com": ["alice@example.com"],
        }
    }
    assert account_data_service.clean_relationship_map(data, "blocks", "alice@example.com") == {
        "blocks": {
            "bob@example.com": ["carol@example.com"],
            "carol@example.com": ["dana@example.com"],
        }
    }


def test_record_involves_email_checks_multiple_fields():
    assert account_data_service.record_involves_email(
        {"from": "alice@example.com", "to": "bob@example.com"},
        "ALICE@example.com",
        ["from", "to"],
    ) is True
    assert account_data_service.record_involves_email(
        {"from": "carol@example.com", "to": "bob@example.com"},
        "alice@example.com",
        ["from", "to"],
    ) is False
