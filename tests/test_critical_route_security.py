import app
import pytest
from backend.models import User
from backend.repositories.call_signal_repository import JsonCallSignalRepository


def _login(client, email, csrf_token="csrf-test-token"):
    with client.session_transaction() as session_data:
        session_data["user_email"] = email
        session_data["session_version"] = 1
        session_data["csrf_token"] = csrf_token


def test_privacy_page_requires_authentication():
    response = app.app.test_client().get("/privacy/alice@example.com")
    assert response.status_code == 302


def test_privacy_toggle_rejects_get_and_missing_csrf(monkeypatch):
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "Founder", "", [], [], [], [])
    monkeypatch.setattr(app, "users", [alice])
    client = app.app.test_client()
    _login(client, alice.email)

    assert client.get("/toggle_privacy/alice@example.com/show_in_search").status_code == 405
    assert client.post("/toggle_privacy/alice@example.com/show_in_search").status_code == 403


def test_privacy_toggle_accepts_owned_csrf_protected_post(monkeypatch):
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "Founder", "", [], [], [], [])
    monkeypatch.setattr(app, "users", [alice])
    monkeypatch.setattr(app, "get_user_privacy", lambda email: {"show_in_search": True})
    updates = []
    monkeypatch.setattr(app, "update_user_privacy", lambda email, setting, value: updates.append((email, setting, value)))
    client = app.app.test_client()
    _login(client, alice.email)

    response = client.post(
        "/toggle_privacy/alice@example.com/show_in_search",
        data={"csrf_token": "csrf-test-token"},
    )

    assert response.status_code == 302
    assert updates == [("alice@example.com", "show_in_search", False)]


def test_call_signal_rejects_sender_impersonation(monkeypatch):
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "Founder", "", [], [], [], [])
    bob = User("Bob", 30, "bob@example.com", "hashed", "Germany", "", "Engineer", "", [], [], [], [])
    mallory = User("Mallory", 31, "mallory@example.com", "hashed", "Germany", "", "Analyst", "", [], [], [], [])
    monkeypatch.setattr(app, "users", [alice, bob, mallory])
    monkeypatch.setattr(app, "load_call_signals", lambda: {})
    monkeypatch.setattr(app, "save_call_signals", lambda data: None)
    client = app.app.test_client()
    _login(client, mallory.email)
    room = app.get_call_room_id(alice.email, bob.email, "audio")

    response = client.post(
        f"/call_signal/{room}",
        json={"type": "ringing", "from": alice.email, "to": bob.email, "payload": {"call_type": "audio"}},
        headers={"X-CSRF-Token": "csrf-test-token"},
    )

    assert response.status_code == 403
    assert response.get_json()["error"] == "forbidden_participant"


def test_call_signal_rejects_room_outside_authenticated_pair(monkeypatch):
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "Founder", "", [], [], [], [])
    bob = User("Bob", 30, "bob@example.com", "hashed", "Germany", "", "Engineer", "", [], [], [], [])
    monkeypatch.setattr(app, "users", [alice, bob])
    client = app.app.test_client()
    _login(client, alice.email)

    response = client.get("/call_signal/not-the-room?other=bob@example.com&call_type=audio")

    assert response.status_code == 403
    assert response.get_json()["error"] == "forbidden_room"


def test_call_signal_rejects_malformed_sdp_before_storage(monkeypatch):
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "Founder", "", [], [], [], [])
    bob = User("Bob", 30, "bob@example.com", "hashed", "Germany", "", "Engineer", "", [], [], [], [])
    monkeypatch.setattr(app, "users", [alice, bob])
    monkeypatch.setattr(app, "get_call_signal_room", lambda room: None)
    monkeypatch.setattr(app, "is_blocked", lambda *args: False)
    monkeypatch.setattr(app, "is_restricted", lambda *args: False)
    stored = []
    monkeypatch.setattr(app, "append_call_signal", lambda *args, **kwargs: stored.append(args) or {})
    client = app.app.test_client()
    _login(client, alice.email)
    room = app.get_call_room_id(alice.email, bob.email, "audio")

    response = client.post(
        f"/call_signal/{room}",
        json={"event_id": "event_malformed_0001", "type": "offer", "from": alice.email, "to": bob.email,
              "payload": {"call_type": "audio", "type": "offer", "sdp": "invalid"}},
        headers={"X-CSRF-Token": "csrf-test-token"},
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "invalid_session_description"
    assert stored == []


def test_call_signal_rejects_oversized_request_before_json_parse(monkeypatch):
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "Founder", "", [], [], [], [])
    monkeypatch.setattr(app, "users", [alice])
    client = app.app.test_client()
    _login(client, alice.email)

    response = client.post(
        "/call_signal/room",
        data=b"x" * (app.call_signal_security_service.MAX_SIGNAL_REQUEST_BYTES + 1),
        content_type="application/json",
        headers={"X-CSRF-Token": "csrf-test-token"},
    )

    assert response.status_code == 413
    assert response.get_json()["error"] == "signal_request_too_large"


@pytest.mark.parametrize("signal_type", ["ended", "declined"])
def test_call_signal_closure_purges_temporary_caption_data(monkeypatch, signal_type):
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "Founder", "", [], [], [], [])
    bob = User("Bob", 30, "bob@example.com", "hashed", "Germany", "", "Engineer", "", [], [], [], [])
    monkeypatch.setattr(app, "users", [alice, bob])
    room_id = app.get_call_room_id(alice.email, bob.email, "audio")
    call_rooms = {room_id: {
        "status": "active",
        "messages": [
            {"type": "ringing", "from": bob.email, "to": alice.email, "created_at": 98},
            {"type": "offer", "from": bob.email, "to": alice.email, "created_at": 99},
            {"type": "accepted", "from": alice.email, "to": bob.email, "created_at": 100},
        ],
        "captions": [{"id": "caption", "text": "temporary"}],
        "transcription_reservations": [{"sequence": 1}],
    }}
    saved = []
    push_events = []
    monkeypatch.setattr(app, "get_call_signal_room", lambda selected_room: call_rooms.get(selected_room))

    def append_signal(selected_room, signal, status="active", close=False, **options):
        push_events.append(options.get("push_event"))
        room = dict(call_rooms.get(selected_room, {}))
        room["messages"] = [*room.get("messages", []), signal]
        room["status"] = status
        if close:
            room.pop("captions", None)
            room.pop("transcription_reservations", None)
        call_rooms[selected_room] = room
        saved.append(room)
        return room

    monkeypatch.setattr(app, "append_call_signal", append_signal)
    monkeypatch.setattr(app, "record_call_chat_event", lambda *args, **kwargs: True)
    monkeypatch.setattr(app, "is_blocked", lambda *args: False)
    monkeypatch.setattr(app, "is_restricted", lambda *args: False)
    client = app.app.test_client()
    _login(client, alice.email)

    response = client.post(
        f"/call_signal/{room_id}",
        json={
            "event_id": f"event_{signal_type}_0001",
            "type": signal_type,
            "from": alice.email,
            "to": bob.email,
            "payload": {"call_type": "audio"},
        },
        headers={"X-CSRF-Token": "csrf-test-token"},
    )

    assert response.status_code == 200
    closed_room = saved[-1]
    assert closed_room["status"] == signal_type
    assert "captions" not in closed_room
    assert "transcription_reservations" not in closed_room
    assert push_events[-1]["event_type"] == "call_cancelled"
    assert push_events[-1]["target_email"] == alice.email


def test_call_signal_rejects_client_generated_missed_event(monkeypatch):
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "Founder", "", [], [], [], [])
    bob = User("Bob", 30, "bob@example.com", "hashed", "Germany", "", "Engineer", "", [], [], [], [])
    monkeypatch.setattr(app, "users", [alice, bob])
    client = app.app.test_client()
    _login(client, alice.email)
    room = app.get_call_room_id(alice.email, bob.email, "audio")

    response = client.post(
        f"/call_signal/{room}",
        json={"type": "missed", "from": alice.email, "to": bob.email, "payload": {"call_type": "audio"}},
        headers={"X-CSRF-Token": "csrf-test-token"},
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "invalid_signal_type"


def test_call_signal_retry_returns_duplicate_ack_without_second_write(monkeypatch, tmp_path):
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "Founder", "", [], [], [], [])
    bob = User("Bob", 30, "bob@example.com", "hashed", "Germany", "", "Engineer", "", [], [], [], [])
    repository = JsonCallSignalRepository(tmp_path / "calls.json")
    monkeypatch.setattr(app, "users", [alice, bob])
    monkeypatch.setattr(app, "get_call_signal_room", repository.get_room)
    monkeypatch.setattr(app, "append_call_signal", repository.append_signal)
    monkeypatch.setattr(app, "acknowledge_call_signals", repository.acknowledge_signals)
    monkeypatch.setattr(app, "is_blocked", lambda *args: False)
    monkeypatch.setattr(app, "is_restricted", lambda *args: False)
    client = app.app.test_client()
    _login(client, alice.email)
    room = app.get_call_room_id(alice.email, bob.email, "audio")
    payload = {
        "event_id": "event_retry_12345678", "type": "ringing", "from": alice.email,
        "to": bob.email, "payload": {"call_type": "audio"},
    }

    first = client.post(f"/call_signal/{room}", json=payload, headers={"X-CSRF-Token": "csrf-test-token"})
    retry = client.post(f"/call_signal/{room}", json=payload, headers={"X-CSRF-Token": "csrf-test-token"})
    conflicting_payload = {**payload, "type": "ended"}
    conflict = client.post(
        f"/call_signal/{room}", json=conflicting_payload,
        headers={"X-CSRF-Token": "csrf-test-token"},
    )

    assert first.status_code == 200
    assert first.get_json() == {"ok": True, "event_id": payload["event_id"], "duplicate": False}
    assert retry.status_code == 200
    assert retry.get_json() == {"ok": True, "event_id": payload["event_id"], "duplicate": True}
    assert conflict.status_code == 409
    assert conflict.get_json()["error"] == "signal_idempotency_conflict"
    assert len(repository.get_room(room)["messages"]) == 1

    bob_client = app.app.test_client()
    _login(bob_client, bob.email)
    ack = bob_client.post(
        f"/call_signal/{room}/ack",
        json={"other_email": alice.email, "call_type": "audio", "event_ids": [payload["event_id"]]},
        headers={"X-CSRF-Token": "csrf-test-token"},
    )
    delivery = client.get(f"/call_signal/{room}?other={bob.email}&call_type=audio&after=0")

    assert ack.status_code == 200
    assert ack.get_json()["acknowledged_count"] == 1
    assert delivery.status_code == 200
    assert delivery.get_json()["acknowledged_event_ids"] == [payload["event_id"]]


def test_signal_poll_atomically_expires_unanswered_call_without_chat_open(monkeypatch):
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "Founder", "", [], [], [], [])
    bob = User("Bob", 30, "bob@example.com", "hashed", "Germany", "", "Engineer", "", [], [], [], [])
    room = app.get_call_room_id(alice.email, bob.email, "audio")
    transition = {
        "id": "timeout_1234567890", "type": "missed", "from": alice.email, "to": bob.email,
        "payload": {"call_type": "audio", "reason": "ringing_timeout"}, "created_at": 146,
    }
    monkeypatch.setattr(app, "users", [alice, bob])
    monkeypatch.setattr(app, "is_blocked", lambda *args: False)
    monkeypatch.setattr(app, "is_restricted", lambda *args: False)
    monkeypatch.setattr(app, "expire_call_signal_room", lambda selected_room, now: {
        "transition": transition, "room": {"status": "missed", "messages": [transition]},
    })
    recorded = []
    monkeypatch.setattr(app, "record_call_chat_event", lambda *args: recorded.append(args) or True)
    client = app.app.test_client()
    _login(client, bob.email)

    response = client.get(f"/call_signal/{room}?other={alice.email}&call_type=audio&after=0")

    assert response.status_code == 200
    assert response.get_json()["status"] == "missed"
    assert response.get_json()["messages"][0]["payload"]["reason"] == "ringing_timeout"
    assert recorded[0][:4] == (alice.email, bob.email, "audio", "missed")


def test_feed_mutations_reject_get_and_missing_csrf(monkeypatch):
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "Founder", "", [], [], [], [])
    monkeypatch.setattr(app, "users", [alice])
    client = app.app.test_client()
    _login(client, alice.email)

    paths = [
        "/like_post/alice@example.com/1",
        "/save_post/alice@example.com/1",
        "/send_shared_post/alice@example.com/1/bob@example.com",
    ]
    for path in paths:
        assert client.get(path).status_code == 405
        assert client.post(path).status_code == 403


def test_message_mutations_reject_get_and_missing_csrf(monkeypatch):
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "Founder", "", [], [], [], [])
    monkeypatch.setattr(app, "users", [alice])
    client = app.app.test_client()
    _login(client, alice.email)

    paths = [
        "/react_message/alice@example.com/bob@example.com/1/%F0%9F%91%8D",
        "/delete_message/alice@example.com/bob@example.com/1/me",
        "/pin_message/alice@example.com/bob@example.com/1",
        "/unpin_message/alice@example.com/bob@example.com/1",
        "/forward_message/alice@example.com/1/bob@example.com",
    ]
    for path in paths:
        assert client.get(path).status_code == 405
        assert client.post(path).status_code == 403


def test_settings_and_logout_mutations_reject_get_and_missing_csrf(monkeypatch):
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "Founder", "", [], [], [], [])
    monkeypatch.setattr(app, "users", [alice])
    client = app.app.test_client()
    _login(client, alice.email)

    paths = [
        "/settings/alice@example.com/people_controls/unblock/bob@example.com",
        "/settings/alice@example.com/people_controls/unrestrict/bob@example.com",
        "/settings/alice@example.com/people_controls/show_stories/bob@example.com",
        "/set_language/alice@example.com/en",
        "/logout",
    ]
    for path in paths:
        assert client.get(path).status_code == 405
        assert client.post(path).status_code == 403
