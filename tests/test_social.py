from backend.social import (
    accept_friend_request,
    are_friends,
    decline_friend_request,
    follow_user,
    get_followers,
    get_following,
    has_friend_request,
    is_following,
    send_friend_request,
    unfollow_user,
)


def test_follow_and_unfollow_user(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    assert follow_user("alice@example.com", "bob@example.com") is True
    assert follow_user("ALICE@example.com", "BOB@example.com") is False
    assert is_following("alice@example.com", "bob@example.com") is True
    assert get_followers("bob@example.com") == ["alice@example.com"]
    assert get_following("alice@example.com") == ["bob@example.com"]

    assert unfollow_user("alice@example.com", "bob@example.com") is True
    assert is_following("alice@example.com", "bob@example.com") is False


def test_friend_request_accept_and_decline(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    assert send_friend_request("alice@example.com", "bob@example.com") is True
    assert has_friend_request("alice@example.com", "bob@example.com") is True

    assert accept_friend_request("bob@example.com", "alice@example.com") is True
    assert are_friends("alice@example.com", "bob@example.com") is True
    assert has_friend_request("alice@example.com", "bob@example.com") is False

    assert send_friend_request("carol@example.com", "bob@example.com") is True
    assert decline_friend_request("bob@example.com", "carol@example.com") is True
    assert has_friend_request("carol@example.com", "bob@example.com") is False
    assert are_friends("carol@example.com", "bob@example.com") is False


def test_friend_request_guards_against_self_duplicates_and_existing_friends(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    assert send_friend_request("alice@example.com", "alice@example.com") is False
    assert send_friend_request("alice@example.com", "bob@example.com") is True
    assert send_friend_request("alice@example.com", "bob@example.com") is False

    assert accept_friend_request("bob@example.com", "alice@example.com") is True
    assert accept_friend_request("bob@example.com", "alice@example.com") is False
    assert send_friend_request("alice@example.com", "bob@example.com") is False
    assert send_friend_request("bob@example.com", "alice@example.com") is False
