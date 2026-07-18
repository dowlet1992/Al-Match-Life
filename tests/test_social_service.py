from backend.models import User
from backend.services import social_service


def test_social_service_blocks_self_follow(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])

    result = social_service.follow(alice, alice, lambda one, two: False)

    assert result["ok"] is False
    assert result["status"] == 400


def test_social_service_respects_block_check(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    bob = User("Bob", 30, "bob@example.com", "hashed", "Germany", "", "", "", [], [], [], [])

    result = social_service.request_friend(alice, bob, lambda one, two: True)

    assert result["ok"] is False
    assert result["status"] == 403


def test_social_service_follow_request_accept_and_decline(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    bob = User("Bob", 30, "bob@example.com", "hashed", "Germany", "", "", "", [], [], [], [])

    follow_result = social_service.follow(alice, bob, lambda one, two: False)
    assert follow_result["ok"] is True
    assert follow_result["changed"] is True
    assert follow_result["is_following"] is True

    request_result = social_service.request_friend(alice, bob, lambda one, two: False)
    assert request_result["ok"] is True
    assert request_result["changed"] is True
    assert request_result["friend_request_sent"] is True

    accept_result = social_service.accept_request(bob, alice, lambda one, two: False)
    assert accept_result["ok"] is True
    assert accept_result["changed"] is True
    assert accept_result["are_friends"] is True

    decline_result = social_service.decline_request(bob, alice)
    assert decline_result["ok"] is True
    assert decline_result["changed"] is False
