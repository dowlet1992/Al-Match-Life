from backend import realtime_status
from backend.repositories.realtime_repository import JsonRealtimeRepository


def test_typing_status_store_accepts_only_dict(monkeypatch, tmp_path):
    repository = JsonRealtimeRepository(tmp_path / "typing.json", tmp_path / "presence.json")
    repository.typing_store.save([])
    monkeypatch.setattr(realtime_status, "get_realtime_repository", lambda: repository)

    assert realtime_status.load_typing_status() == {}


def test_typing_status_store_saves_data(monkeypatch, tmp_path):
    repository = JsonRealtimeRepository(tmp_path / "typing.json", tmp_path / "presence.json")
    monkeypatch.setattr(realtime_status, "get_realtime_repository", lambda: repository)

    realtime_status.save_typing_status({"alice::bob": True})

    assert realtime_status.load_typing_status() == {"alice::bob": True}


def test_presence_status_store_accepts_only_dict(monkeypatch, tmp_path):
    repository = JsonRealtimeRepository(tmp_path / "typing.json", tmp_path / "presence.json")
    repository.presence_store.save([])
    monkeypatch.setattr(realtime_status, "get_realtime_repository", lambda: repository)

    assert realtime_status.load_presence_status() == {}


def test_presence_status_store_saves_data(monkeypatch, tmp_path):
    repository = JsonRealtimeRepository(tmp_path / "typing.json", tmp_path / "presence.json")
    monkeypatch.setattr(realtime_status, "get_realtime_repository", lambda: repository)

    realtime_status.save_presence_status({"alice@example.com": {"online": True}})

    assert realtime_status.load_presence_status() == {
        "alice@example.com": {"online": True}
    }
