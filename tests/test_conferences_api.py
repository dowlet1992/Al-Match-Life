import app
from backend.models import User


def session_headers(client, email):
    with client.session_transaction() as session:
        session["user_email"] = email
        session["csrf_token"] = "conference-csrf"
    return {"X-CSRF-Token": "conference-csrf"}


def test_create_conference_persists_private_room(monkeypatch):
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    bob = User("Bob", 29, "bob@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    carol = User("Carol", 30, "carol@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    monkeypatch.setattr(app, "users", [alice, bob, carol])
    stored = []
    monkeypatch.setattr(app, "append_call_signal", lambda room, signal, **options: stored.append((room, signal, options)) or {"participants": [alice.email, signal["to"]]})
    client = app.app.test_client()
    response = client.post("/api/conferences", headers=session_headers(client, alice.email), json={
        "call_type": "video", "participants": [bob.email, carol.email],
    })
    assert response.status_code == 201
    assert response.get_json()["room_id"].startswith("novix_")
    assert len(stored) == 2
    assert all(item[2]["enforce_transition"] is False for item in stored)


def test_conference_token_does_not_expose_email_identity(monkeypatch):
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    monkeypatch.setattr(app, "users", [alice])
    monkeypatch.setattr(app, "get_call_signal_room", lambda room: {"participants": [alice.email]})
    monkeypatch.setenv("LIVEKIT_API_KEY", "novix-key")
    monkeypatch.setenv("LIVEKIT_API_SECRET", "a-secure-secret-at-least-32-characters")
    client = app.app.test_client()
    response = client.post("/api/conferences/novix_room/token", headers=session_headers(client, alice.email))
    assert response.status_code == 200
    assert alice.email not in response.get_json()["token"]
    assert response.headers["Cache-Control"] == "private, no-store"


def test_eligible_conference_contacts_exclude_current_peer_and_blocked_users(monkeypatch):
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    bob = User("Bob", 29, "bob@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    carol = User("Carol", 30, "carol@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    blocked = User("Blocked", 31, "blocked@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    monkeypatch.setattr(app, "users", [alice, bob, carol, blocked])
    monkeypatch.setattr(app, "is_blocked", lambda one, two: blocked.email in {one, two})
    monkeypatch.setattr(app, "is_restricted", lambda one, two: False)
    client = app.app.test_client()
    session_headers(client, alice.email)

    response = client.get("/api/conferences/eligible", query_string={"exclude": bob.email})

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "private, no-store"
    assert [person["email"] for person in response.get_json()["people"]] == [carol.email]


def test_conference_page_renders_local_sdk_and_invite_controls(monkeypatch):
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    bob = User("Bob", 29, "bob@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    room = {"participants": [alice.email, bob.email], "messages": [{
        "type": "conference_invite", "from": alice.email, "to": bob.email,
        "payload": {"owner": alice.email, "call_type": "video"},
    }]}
    monkeypatch.setattr(app, "users", [alice, bob])
    monkeypatch.setattr(app, "get_call_signal_room", lambda selected: room)
    client = app.app.test_client()
    session_headers(client, alice.email)
    response = client.get("/conference/novix_secure_room")
    assert response.status_code == 200
    assert b'/static/vendor/livekit-client.umd.min.js' in response.data
    assert b'id="participantGrid"' in response.data
    assert b'id="conferenceInvite"' in response.data
    assert b'data-max-participants="4"' in response.data


def test_only_conference_owner_can_invite(monkeypatch):
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    bob = User("Bob", 29, "bob@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    carol = User("Carol", 30, "carol@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    room = {"participants": [alice.email, bob.email], "messages": [{
        "type": "conference_invite", "from": alice.email, "to": bob.email,
        "payload": {"owner": alice.email, "call_type": "video"},
    }]}
    monkeypatch.setattr(app, "users", [alice, bob, carol])
    monkeypatch.setattr(app, "get_call_signal_room", lambda selected: room)
    client = app.app.test_client()
    response = client.post(
        "/api/conferences/novix_secure_room/participants",
        headers=session_headers(client, bob.email), json={"email": carol.email},
    )
    assert response.status_code == 403
    assert response.get_json()["error"] == "conference_invite_forbidden"


def test_recent_conference_invitation_is_private_and_discoverable(monkeypatch):
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    bob = User("Bob", 29, "bob@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    monkeypatch.setattr(app, "users", [alice, bob])
    monkeypatch.setattr(app, "load_call_signals", lambda: {"novix_secure_room": {
        "status": "ringing", "participants": [alice.email, bob.email], "messages": [{
            "type": "conference_invite", "from": alice.email, "to": bob.email,
            "created_at": __import__("time").time(), "payload": {"owner": alice.email, "call_type": "audio"},
        }],
    }})
    client = app.app.test_client()
    session_headers(client, bob.email)
    response = client.get("/api/conferences/invitations")
    assert response.status_code == 200
    assert response.get_json()["invitations"][0]["join_url"] == "/conference/novix_secure_room"
    assert response.get_json()["invitations"][0]["call_type"] == "audio"
    assert response.headers["Cache-Control"] == "private, no-store"
