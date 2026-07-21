from backend import call_signals_store, news_store
from backend.repositories.call_signal_repository import JsonCallSignalRepository
from backend.repositories.news_repository import JsonNewsRepository


def test_news_store_accepts_only_list(monkeypatch, tmp_path):
    repository = JsonNewsRepository(tmp_path / "news.json")
    repository.store.save({})
    monkeypatch.setattr(news_store, "get_news_repository", lambda: repository)

    assert news_store.load_news() == []


def test_news_store_limits_saved_items(monkeypatch, tmp_path):
    repository = JsonNewsRepository(tmp_path / "news.json")
    monkeypatch.setattr(news_store, "get_news_repository", lambda: repository)

    news_store.save_news([{"id": 1}, {"id": 2}, {"id": 3}], limit=2)

    assert news_store.load_news() == [{"id": 2}, {"id": 3}]


def test_call_signals_store_accepts_only_dict(monkeypatch, tmp_path):
    repository = JsonCallSignalRepository(tmp_path / "call_signals.json")
    repository.store.save([])
    monkeypatch.setattr(call_signals_store, "get_call_signal_repository", lambda: repository)

    assert call_signals_store.load_call_signals() == {}


def test_call_signals_store_saves_data(monkeypatch, tmp_path):
    repository = JsonCallSignalRepository(tmp_path / "call_signals.json")
    monkeypatch.setattr(call_signals_store, "get_call_signal_repository", lambda: repository)

    call_signals_store.save_call_signals({"room": {"type": "offer"}})

    assert call_signals_store.load_call_signals() == {"room": {"type": "offer"}}


def test_call_signals_store_appends_single_room_signal(monkeypatch, tmp_path):
    repository = JsonCallSignalRepository(tmp_path / "call_signals.json")
    monkeypatch.setattr(call_signals_store, "get_call_signal_repository", lambda: repository)

    room = call_signals_store.append_call_signal(
        "room", {"id": "offer", "type": "offer"}, status="active",
    )

    assert room["messages"] == [{"id": "offer", "type": "offer"}]
    assert call_signals_store.load_call_signals()["room"] == room


def test_call_signals_store_deletes_participant_rooms(monkeypatch, tmp_path):
    repository = JsonCallSignalRepository(tmp_path / "call_signals.json")
    repository.save_all({
        "mine": {"participants": ["alice@example.com", "bob@example.com"]},
        "other": {"participants": ["bob@example.com", "carol@example.com"]},
    })
    monkeypatch.setattr(call_signals_store, "get_call_signal_repository", lambda: repository)

    assert call_signals_store.delete_call_rooms_for_participant("alice@example.com") == 1
    assert list(call_signals_store.load_call_signals()) == ["other"]


def test_call_signals_store_prunes_expired_rooms(monkeypatch, tmp_path):
    repository = JsonCallSignalRepository(tmp_path / "call_signals.json")
    repository.save_all({"old": {"status": "ended", "messages": [{"created_at": 1}]}})
    monkeypatch.setattr(call_signals_store, "get_call_signal_repository", lambda: repository)

    assert call_signals_store.prune_expired_call_rooms(now=100_000) == 1
    assert call_signals_store.load_call_signals() == {}
