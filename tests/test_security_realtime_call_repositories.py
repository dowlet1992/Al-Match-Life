from backend.database import DatabaseSettings
from backend.repositories.call_signal_repository import JsonCallSignalRepository, PostgresCallSignalRepository, get_call_signal_repository
from backend.repositories.realtime_repository import JsonRealtimeRepository, PostgresRealtimeRepository, get_realtime_repository
from backend.repositories.security_repository import JsonSecurityRepository, PostgresSecurityRepository, get_security_repository, split_attempt_key


class FakeCursor:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, query, params=None):
        self.calls.append((query, params))

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0] if self.rows else None


class FakeConnection:
    def __init__(self, cursor):
        self.cursor_instance = cursor
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def cursor(self):
        return self.cursor_instance

    def commit(self):
        self.committed = True


class FakeClient:
    def __init__(self, rows=None):
        self.cursor = FakeCursor(rows)
        self.connection = FakeConnection(self.cursor)

    def connect(self):
        return self.connection


def test_split_attempt_key():
    assert split_attempt_key("user@example.com::127.0.0.1") == ("user@example.com", "127.0.0.1")
    assert split_attempt_key("bad") == ("bad", "")


def test_json_security_repository_round_trip(tmp_path):
    repository = JsonSecurityRepository(tmp_path / "attempts.json", tmp_path / "events.json")
    repository.save_login_attempts({"key": {"attempts": []}})
    repository.save_security_events([{"event": "login"}])

    assert repository.load_login_attempts() == {"key": {"attempts": []}}
    assert repository.load_security_events() == [{"event": "login"}]


def test_postgres_security_repository_saves_events():
    client = FakeClient()
    repository = PostgresSecurityRepository(client=client)

    repository.save_security_events([{"event": "login", "email": "a@test.com"}])

    assert client.connection.committed is True
    assert client.cursor.calls[0][0] == "DELETE FROM security_events"
    assert "INSERT INTO security_events" in client.cursor.calls[1][0]


def test_postgres_realtime_repository_saves_presence_and_typing():
    client = FakeClient()
    repository = PostgresRealtimeRepository(client=client)

    repository.save_typing_status({"alice@example.com::bob@example.com": {"is_typing": True}})
    repository.save_presence_status({"alice@example.com": {"online": True}})

    assert client.connection.committed is True
    assert any("INSERT INTO realtime_typing" in query for query, _ in client.cursor.calls)
    assert any("INSERT INTO realtime_presence" in query for query, _ in client.cursor.calls)


def test_json_realtime_repository_round_trip(tmp_path):
    repository = JsonRealtimeRepository(tmp_path / "typing.json", tmp_path / "presence.json")
    repository.save_typing_status({"a::b": True})
    repository.save_presence_status({"a": {"online": True}})

    assert repository.load_typing_status() == {"a::b": True}
    assert repository.load_presence_status() == {"a": {"online": True}}


def test_postgres_call_signal_repository_saves_calls():
    client = FakeClient()
    repository = PostgresCallSignalRepository(client=client)

    repository.save_all({"room": {"type": "offer"}})

    assert client.connection.committed is True
    assert client.cursor.calls[0][0] == "DELETE FROM call_signals"
    assert "INSERT INTO call_signals" in client.cursor.calls[1][0]


def test_json_call_signal_repository_round_trip(tmp_path):
    repository = JsonCallSignalRepository(tmp_path / "calls.json")
    repository.save_all({"room": {"type": "offer"}})

    assert repository.load_all() == {"room": {"type": "offer"}}


def test_json_call_maintenance_expires_only_due_unanswered_rooms(tmp_path):
    repository = JsonCallSignalRepository(tmp_path / "calls.json")
    repository.save_all({
        "connected": {"status": "active", "messages": [
            {"type": "ringing", "created_at": 1}, {"type": "answer", "created_at": 2},
        ]},
        "due": {"status": "ringing", "messages": [
            {"type": "ringing", "from": "a@test.com", "to": "b@test.com", "created_at": 1,
             "payload": {"call_type": "video"}},
        ]},
    })

    results = repository.expire_due_rooms(100, batch_size=1)

    assert len(results) == 1
    assert results[0]["transition"]["type"] == "missed"
    assert repository.get_room("connected")["status"] == "active"
    assert repository.expire_due_rooms(100, batch_size=1) == []


def test_postgres_call_maintenance_locks_candidate_batch_without_answered_rooms():
    room = {"status": "ringing", "messages": [
        {"type": "ringing", "from": "a@test.com", "to": "b@test.com", "created_at": 1,
         "payload": {"call_type": "audio"}},
    ]}
    client = FakeClient(rows=[("room-1", room)])

    results = PostgresCallSignalRepository(client=client).expire_due_rooms(100, batch_size=25)

    select_query, select_params = client.cursor.calls[0]
    assert "FOR UPDATE SKIP LOCKED" in select_query
    assert "message->>'type' = 'answer'" in select_query
    assert select_params == {"batch_size": 25}
    assert results[0]["transition"]["type"] == "missed"
    assert "UPDATE call_signals" in client.cursor.calls[1][0]
    assert client.connection.committed is True


def test_json_call_signal_repository_appends_caption_without_lost_update(tmp_path):
    repository = JsonCallSignalRepository(tmp_path / "calls.json")
    repository.save_all({"room": {"status": "active", "captions": []}})

    assert repository.append_caption("room", {"id": "one", "created_at": 100}, minimum_created_at=0) == "appended"
    assert repository.append_caption("room", {"id": "two", "created_at": 101}, minimum_created_at=0) == "appended"

    assert [item["id"] for item in repository.get_room("room")["captions"]] == ["one", "two"]
    assert repository.set_caption_translation("room", "one", "de", "Hallo") == "updated"
    assert repository.get_room("room")["captions"][0]["translations"] == {"de": "Hallo"}


def test_json_call_signal_repository_appends_only_selected_room(tmp_path):
    repository = JsonCallSignalRepository(tmp_path / "calls.json")
    repository.save_all({
        "room": {"status": "active", "messages": [], "captions": [{"id": "one"}]},
        "other": {"status": "ringing", "messages": [{"id": "untouched"}]},
    })

    updated = repository.append_signal(
        "room", {"id": "ended", "type": "ended"}, status="ended", close=True,
    )

    assert updated == {"status": "ended", "messages": [{"id": "ended", "type": "ended"}], "updated_at": ""}
    assert repository.get_room("other") == {"status": "ringing", "messages": [{"id": "untouched"}]}


def test_json_call_signal_repository_rate_limits_signal_atomically(tmp_path):
    repository = JsonCallSignalRepository(tmp_path / "calls.json")
    repository.save_all({"room": {"status": "active", "messages": []}})
    base = {"type": "ice", "from": "alice@example.com"}

    assert isinstance(repository.append_signal("room", {**base, "created_at": 100}, rate_limit=2), dict)
    assert isinstance(repository.append_signal("room", {**base, "created_at": 101}, rate_limit=2), dict)
    assert repository.append_signal("room", {**base, "created_at": 102}, rate_limit=2) == "rate_limited"
    assert len(repository.get_room("room")["messages"]) == 2


def test_json_call_signal_repository_enforces_protocol_state_machine(tmp_path):
    repository = JsonCallSignalRepository(tmp_path / "calls.json")
    alice = "alice@example.com"
    bob = "bob@example.com"

    assert repository.append_signal(
        "room", {"type": "answer", "from": bob, "to": alice, "created_at": 99},
        enforce_transition=True,
    ) == "invalid_transition"
    assert isinstance(repository.append_signal(
        "room", {"type": "ringing", "from": alice, "to": bob, "created_at": 100},
        enforce_transition=True,
    ), dict)
    assert repository.append_signal(
        "room", {"type": "accepted", "from": alice, "to": bob, "created_at": 101},
        enforce_transition=True,
    ) == "invalid_transition"
    assert isinstance(repository.append_signal(
        "room", {"type": "offer", "from": alice, "to": bob, "created_at": 102},
        enforce_transition=True,
    ), dict)
    assert isinstance(repository.append_signal(
        "room", {"type": "accepted", "from": bob, "to": alice, "created_at": 103},
        enforce_transition=True,
    ), dict)
    assert isinstance(repository.append_signal(
        "room", {"type": "answer", "from": bob, "to": alice, "created_at": 104},
        enforce_transition=True,
    ), dict)
    assert repository.append_signal(
        "room", {"type": "accepted", "from": bob, "to": alice, "created_at": 105},
        enforce_transition=True,
    ) == "invalid_transition"


def test_json_call_signal_repository_acknowledges_duplicate_without_rewrite(tmp_path):
    repository = JsonCallSignalRepository(tmp_path / "calls.json")
    signal = {
        "id": "event_1234567890", "type": "ringing", "from": "alice@example.com",
        "to": "bob@example.com", "created_at": 100,
    }
    first = repository.append_signal("room", signal, enforce_transition=True, rate_limit=1)
    duplicate = repository.append_signal("room", signal, enforce_transition=True, rate_limit=1)

    assert first.get("_signal_duplicate") is None
    assert duplicate["_signal_duplicate"] is True
    assert len(repository.get_room("room")["messages"]) == 1
    conflict = repository.append_signal(
        "room", {**signal, "type": "ended"}, enforce_transition=True, rate_limit=1,
    )
    assert conflict == "idempotency_conflict"
    assert len(repository.get_room("room")["messages"]) == 1


def test_json_ringing_signal_enqueues_one_token_free_push_event_atomically(tmp_path):
    repository = JsonCallSignalRepository(tmp_path / "calls.json")
    signal = {"id": "ring_1234567890abcd", "type": "ringing", "from": "a@test.com", "to": "b@test.com", "created_at": 100}
    push_event = {
        "event_id": signal["id"], "target_email": "b@test.com", "event_type": "incoming_call",
        "payload": {"call_id": "room", "call_type": "video"}, "expires_at": 145,
    }
    repository.append_signal("room", signal, enforce_transition=True, push_event=push_event)
    repository.append_signal("room", signal, enforce_transition=True, push_event=push_event)
    room = repository.get_room("room")
    assert room["push_outbox"] == [push_event]
    assert "token" not in str(room["push_outbox"]).lower()


def test_json_call_signal_ack_is_idempotent_and_recipient_owned(tmp_path):
    repository = JsonCallSignalRepository(tmp_path / "calls.json")
    repository.save_all({"room": {"status": "active", "messages": [{
        "id": "event_1234567890", "type": "offer",
        "from": "alice@example.com", "to": "bob@example.com",
    }]}})

    assert repository.acknowledge_signals(
        "room", "alice@example.com", ["event_1234567890"], 100,
    ) == ("acknowledged", 0)
    assert repository.acknowledge_signals(
        "room", "bob@example.com", ["event_1234567890"], 101,
    ) == ("acknowledged", 1)
    assert repository.acknowledge_signals(
        "room", "bob@example.com", ["event_1234567890"], 200,
    ) == ("acknowledged", 1)
    message = repository.get_room("room")["messages"][0]
    assert message["acknowledged_by"] == "bob@example.com"
    assert message["acknowledged_at"] == 101


def test_json_call_signal_room_timeout_is_atomic_and_idempotent(tmp_path):
    repository = JsonCallSignalRepository(tmp_path / "calls.json")
    repository.save_all({"ringing": {
        "status": "active", "captions": [{"text": "temporary"}],
        "messages": [{"id": "ring", "type": "ringing", "from": "alice@example.com",
                      "to": "bob@example.com", "payload": {"call_type": "video"}, "created_at": 100}],
    }, "negotiating": {
        "status": "active", "messages": [
            {"type": "ringing", "from": "alice@example.com", "to": "bob@example.com",
             "payload": {"call_type": "audio"}, "created_at": 100},
            {"type": "accepted", "from": "bob@example.com", "to": "alice@example.com", "created_at": 110},
        ],
    }, "answered": {
        "status": "active", "messages": [
            {"type": "ringing", "created_at": 100}, {"type": "answer", "created_at": 120},
        ],
    }})

    missed = repository.expire_room("ringing", now=146)
    negotiation = repository.expire_room("negotiating", now=141)

    assert missed["transition"]["type"] == "missed"
    assert missed["transition"]["payload"] == {"call_type": "video", "reason": "ringing_timeout"}
    assert "captions" not in missed["room"]
    assert negotiation["transition"]["type"] == "ended"
    assert negotiation["transition"]["payload"]["reason"] == "negotiation_timeout"
    assert missed["room"]["push_outbox"][0]["event_type"] == "call_cancelled"
    assert missed["room"]["push_outbox"][0]["payload"]["call_id"] == "ringing"
    assert repository.expire_room("ringing", now=200)["transition"] is None
    assert repository.expire_room("answered", now=1000)["transition"] is None


def test_json_call_signal_repository_ignores_stale_signals_after_closure(tmp_path):
    repository = JsonCallSignalRepository(tmp_path / "calls.json")
    repository.save_all({"room": {
        "status": "ended",
        "accepted_at": 100,
        "messages": [{"type": "accepted"}, {"type": "ended"}],
    }})

    assert repository.append_signal("room", {"type": "ice"}) is None
    assert repository.append_signal("room", {"type": "missed"}, status="missed", close=True) is None
    assert repository.get_room("room")["messages"] == [{"type": "accepted"}, {"type": "ended"}]

    reopened = repository.append_signal("room", {"type": "ringing"}, status="active")
    assert reopened["status"] == "active"
    assert reopened["messages"] == [{"type": "ringing"}]
    assert "accepted_at" not in reopened


def test_json_call_signal_repository_deletes_only_participant_rooms(tmp_path):
    repository = JsonCallSignalRepository(tmp_path / "calls.json")
    repository.save_all({
        "new": {"participants": ["alice@example.com", "bob@example.com"], "messages": []},
        "legacy": {"messages": [{"from": "carol@example.com", "to": "alice@example.com"}]},
        "other": {"participants": ["bob@example.com", "carol@example.com"], "messages": []},
    })

    assert repository.delete_for_participant("ALICE@example.com") == 2
    assert repository.load_all() == {
        "other": {"participants": ["bob@example.com", "carol@example.com"], "messages": []},
    }


def test_json_call_signal_repository_prunes_expired_rooms_and_old_signals(tmp_path):
    repository = JsonCallSignalRepository(tmp_path / "calls.json")
    now = 1_000_000
    repository.save_all({
        "closed-old": {"status": "ended", "messages": [{"created_at": now - 90_000}]},
        "closed-fresh": {"status": "ended", "messages": [{"created_at": now - 100}]},
        "open-stale": {"status": "active", "messages": [{"created_at": now - 700_000}]},
        "open-fresh": {"status": "active", "messages": [{"created_at": now - 100}]},
    })

    assert repository.prune_expired(now=now) == 2
    assert set(repository.load_all()) == {"closed-fresh", "open-fresh"}

    updated = repository.append_signal(
        "open-fresh",
        {"type": "ice", "created_at": now},
        status="active",
    )
    assert [message["created_at"] for message in updated["messages"]] == [now - 100, now]


def test_json_call_signal_repository_keeps_accepted_time_outside_signal_window(tmp_path):
    repository = JsonCallSignalRepository(tmp_path / "calls.json")
    accepted = repository.append_signal(
        "room",
        {"type": "accepted", "created_at": 100, "from": "a@test.com", "to": "b@test.com"},
    )
    assert accepted["accepted_at"] == 100

    updated = repository.append_signal(
        "room",
        {"type": "ice", "created_at": 100 + 90_000, "from": "a@test.com", "to": "b@test.com"},
    )
    assert updated["accepted_at"] == 100
    assert [message["type"] for message in updated["messages"]] == ["ice"]


def test_json_call_signal_repository_reserves_transcription_atomically(tmp_path):
    repository = JsonCallSignalRepository(tmp_path / "calls.json")
    repository.save_all({"room": {"status": "active"}})

    assert repository.reserve_transcription("room", "alice@example.com", 1, 100, limit=2) == "reserved"
    assert repository.reserve_transcription("room", "alice@example.com", 1, 101, limit=2) == "duplicate"
    assert repository.reserve_transcription("room", "alice@example.com", 2, 102, limit=2) == "reserved"
    assert repository.reserve_transcription("room", "alice@example.com", 3, 103, limit=2) == "rate_limited"


def test_json_call_signal_repository_bounds_and_rate_limits_quality_samples(tmp_path):
    repository = JsonCallSignalRepository(tmp_path / "calls.json")
    repository.save_all({"room": {"status": "active"}})

    first = {"participant_email": "alice@example.com", "created_at": 100, "rtt_ms": 20}
    assert repository.append_quality_sample("room", first, max_items=2) == "appended"
    assert repository.append_quality_sample("room", {**first, "created_at": 102}, max_items=2) == "rate_limited"
    assert repository.append_quality_sample("room", {**first, "created_at": 105}, max_items=2) == "appended"
    assert repository.append_quality_sample("room", {**first, "created_at": 110}, max_items=2) == "appended"
    assert [item["created_at"] for item in repository.get_room("room")["quality_samples"]] == [105, 110]

    closed = repository.append_signal(
        "room", {"type": "ended", "created_at": 120}, status="ended", close=True,
    )
    assert "quality_samples" not in closed
    assert closed["quality_summary"]["sample_count"] == 2
    assert "participant_email" not in str(closed["quality_summary"])


def test_json_call_signal_repository_purges_temporary_caption_data(tmp_path):
    repository = JsonCallSignalRepository(tmp_path / "calls.json")
    repository.save_all({"room": {
        "status": "ended",
        "captions": [{"id": "one"}],
        "transcription_reservations": [{"sequence": 1}],
        "messages": [{"type": "ended"}],
    }})

    assert repository.purge_caption_data("room") is True
    assert repository.get_room("room") == {"status": "ended", "messages": [{"type": "ended"}]}
    assert repository.purge_caption_data("room") is False


def test_postgres_call_signal_caption_append_locks_room_row():
    client = FakeClient(rows=[({"status": "active", "captions": []},)])
    repository = PostgresCallSignalRepository(client=client)

    status = repository.append_caption("room", {"id": "one", "created_at": 100})

    assert status == "appended"
    assert "FOR UPDATE" in client.cursor.calls[0][0]
    assert "UPDATE call_signals" in client.cursor.calls[1][0]
    assert client.connection.committed is True


def test_postgres_call_quality_append_locks_room_row():
    client = FakeClient(rows=[({"status": "active", "quality_samples": []},)])
    repository = PostgresCallSignalRepository(client=client)

    status = repository.append_quality_sample(
        "room", {"participant_email": "alice@example.com", "created_at": 100},
    )

    assert status == "appended"
    assert "FOR UPDATE" in client.cursor.calls[0][0]
    assert "UPDATE call_signals" in client.cursor.calls[1][0]
    assert client.connection.committed is True


def test_postgres_call_signal_append_upserts_and_locks_only_room():
    client = FakeClient(rows=[({"status": "active", "messages": [{"id": "offer"}]},)])
    repository = PostgresCallSignalRepository(client=client)

    updated = repository.append_signal("room", {"id": "answer"}, status="active")

    assert "ON CONFLICT (room_id) DO NOTHING" in client.cursor.calls[0][0]
    assert "FOR UPDATE" in client.cursor.calls[1][0]
    assert "UPDATE call_signals" in client.cursor.calls[2][0]
    assert all("DELETE FROM call_signals" not in query for query, _ in client.cursor.calls)
    assert updated["messages"] == [{"id": "offer"}, {"id": "answer"}]
    assert client.connection.committed is True


def test_postgres_ringing_and_push_outbox_share_one_transaction():
    client = FakeClient(rows=[({},)])
    repository = PostgresCallSignalRepository(client=client)
    push_event = {
        "event_id": "ring_1234567890abcd", "target_email": "b@test.com",
        "event_type": "incoming_call", "payload": {"call_id": "room"}, "expires_at": 145,
    }
    repository.append_signal(
        "room", {"id": push_event["event_id"], "type": "ringing", "from": "a@test.com", "to": "b@test.com", "created_at": 100},
        enforce_transition=True, push_event=push_event,
    )
    assert "UPDATE call_signals" in client.cursor.calls[2][0]
    assert "INSERT INTO call_push_outbox" in client.cursor.calls[3][0]
    assert "ON CONFLICT (event_id) DO NOTHING" in client.cursor.calls[3][0]
    assert client.connection.committed is True


def test_postgres_call_signal_rate_limit_is_checked_under_room_lock():
    client = FakeClient(rows=[({
        "status": "active",
        "messages": [
            {"type": "ice", "from": "alice@example.com", "created_at": 100},
            {"type": "ice", "from": "alice@example.com", "created_at": 101},
        ],
    },)])
    repository = PostgresCallSignalRepository(client=client)

    status = repository.append_signal(
        "room", {"type": "ice", "from": "alice@example.com", "created_at": 102},
        rate_limit=2, rate_window=60,
    )

    assert status == "rate_limited"
    assert "FOR UPDATE" in client.cursor.calls[1][0]
    assert len(client.cursor.calls) == 2
    assert client.connection.committed is False


def test_postgres_call_signal_transition_is_checked_under_room_lock():
    client = FakeClient(rows=[({"status": "active", "messages": []},)])
    repository = PostgresCallSignalRepository(client=client)

    status = repository.append_signal(
        "room", {"type": "ended", "from": "alice@example.com", "to": "bob@example.com", "created_at": 100},
        status="ended", close=True, enforce_transition=True,
    )

    assert status == "invalid_transition"
    assert "FOR UPDATE" in client.cursor.calls[0][0]
    assert len(client.cursor.calls) == 1
    assert client.connection.committed is False


def test_postgres_call_signal_duplicate_is_acknowledged_under_room_lock():
    signal = {
        "id": "event_1234567890", "type": "ended", "from": "alice@example.com",
        "to": "bob@example.com", "created_at": 100,
    }
    client = FakeClient(rows=[({"status": "ended", "messages": [signal]},)])
    repository = PostgresCallSignalRepository(client=client)

    result = repository.append_signal(
        "room", signal, status="ended", close=True, enforce_transition=True, rate_limit=1,
    )

    assert result["_signal_duplicate"] is True
    assert "FOR UPDATE" in client.cursor.calls[0][0]
    assert len(client.cursor.calls) == 1


def test_postgres_call_delivery_ack_locks_room_and_checks_recipient():
    client = FakeClient(rows=[({"status": "active", "messages": [{
        "id": "event_1234567890", "from": "alice@example.com", "to": "bob@example.com",
    }]},)])
    repository = PostgresCallSignalRepository(client=client)

    status, count = repository.acknowledge_signals(
        "room", "bob@example.com", ["event_1234567890"], 100,
    )

    assert (status, count) == ("acknowledged", 1)
    assert "FOR UPDATE" in client.cursor.calls[0][0]
    assert client.cursor.calls[1][1]["payload"]["messages"][0]["acknowledged_by"] == "bob@example.com"
    assert client.connection.committed is True


def test_postgres_call_room_timeout_locks_and_updates_one_room():
    client = FakeClient(rows=[({"status": "active", "messages": [{
        "type": "ringing", "from": "alice@example.com", "to": "bob@example.com",
        "payload": {"call_type": "audio"}, "created_at": 100,
    }]},)])
    repository = PostgresCallSignalRepository(client=client)

    result = repository.expire_room("room", now=146)

    assert result["transition"]["type"] == "missed"
    assert "FOR UPDATE" in client.cursor.calls[0][0]
    assert client.cursor.calls[1][1]["payload"]["status"] == "missed"
    assert "INSERT INTO call_push_outbox" in client.cursor.calls[2][0]
    assert client.cursor.calls[2][1]["event_type"] == "call_cancelled"
    assert client.connection.committed is True


def test_postgres_call_signal_ignores_stale_signal_after_closure():
    client = FakeClient(rows=[({"status": "ended", "messages": [{"type": "ended"}]},)])
    repository = PostgresCallSignalRepository(client=client)

    assert repository.append_signal("room", {"type": "ice"}) is None
    assert len(client.cursor.calls) == 2
    assert client.connection.committed is False


def test_postgres_call_signal_deletes_only_matching_participant_rooms():
    client = FakeClient()
    repository = PostgresCallSignalRepository(client=client)

    repository.delete_for_participant("ALICE@example.com")

    query, params = client.cursor.calls[0]
    assert query.lstrip().startswith("DELETE FROM call_signals")
    assert "payload->'participants'" in query
    assert "payload->'messages'" in query
    assert params == {"email": "alice@example.com"}
    assert client.connection.committed is True


def test_postgres_call_signal_prunes_closed_and_stale_rooms_by_database_timestamp():
    client = FakeClient()
    repository = PostgresCallSignalRepository(client=client)

    repository.prune_expired(now=1_000_000)

    query, params = client.cursor.calls[0]
    assert query.lstrip().startswith("DELETE FROM call_signals")
    assert "updated_at < %(closed_before)s" in query
    assert "updated_at < %(stale_before)s" in query
    assert params["closed_before"] > params["stale_before"]
    assert client.connection.committed is True


def test_postgres_call_signal_caption_purge_locks_room_row():
    client = FakeClient(rows=[({
        "status": "ended",
        "captions": [{"id": "one"}],
        "transcription_reservations": [{"sequence": 1}],
    },)])
    repository = PostgresCallSignalRepository(client=client)

    assert repository.purge_caption_data("room") is True
    assert "FOR UPDATE" in client.cursor.calls[0][0]
    assert client.cursor.calls[1][1]["payload"] == {"status": "ended"}
    assert client.connection.committed is True


def test_repository_factories_use_postgres():
    settings = DatabaseSettings(storage_backend="postgres", database_url="postgresql://example/db")

    assert isinstance(get_security_repository(settings=settings, client=FakeClient()), PostgresSecurityRepository)
    assert isinstance(get_realtime_repository(settings=settings, client=FakeClient()), PostgresRealtimeRepository)
    assert isinstance(get_call_signal_repository(settings=settings, client=FakeClient()), PostgresCallSignalRepository)
