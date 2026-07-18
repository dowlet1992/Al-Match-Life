from backend import messages as messages_repository
from backend.repositories.message_repository import JsonMessageRepository


def test_messages_repository_loads_only_lists(monkeypatch, tmp_path):
    repository = JsonMessageRepository(tmp_path / "messages.json")
    repository.store.save({"messages": []})
    monkeypatch.setattr(messages_repository, "get_message_repository", lambda: repository)

    assert messages_repository.load_messages() == []


def test_messages_repository_saves_messages(monkeypatch, tmp_path):
    repository = JsonMessageRepository(tmp_path / "messages.json")
    monkeypatch.setattr(messages_repository, "get_message_repository", lambda: repository)

    messages_repository.save_messages([{"id": 1, "message": "Hello"}])

    assert messages_repository.load_messages() == [{"id": 1, "message": "Hello"}]
