from backend import ai_memory_store
from backend.repositories.ai_memory_repository import JsonAiMemoryRepository


def test_ai_core_memory_store_accepts_only_dict(monkeypatch, tmp_path):
    repository = JsonAiMemoryRepository(tmp_path / "ai_core_memory.json", tmp_path / "ai_feed_learning.json")
    repository.core_store.save([])
    monkeypatch.setattr(ai_memory_store, "get_ai_memory_repository", lambda: repository)

    assert ai_memory_store.load_ai_core_memory() == {}


def test_ai_core_memory_store_saves_memory(monkeypatch, tmp_path):
    repository = JsonAiMemoryRepository(tmp_path / "ai_core_memory.json", tmp_path / "ai_feed_learning.json")
    monkeypatch.setattr(ai_memory_store, "get_ai_memory_repository", lambda: repository)

    ai_memory_store.save_ai_core_memory({"user@example.com": [{"answer": "Hello"}]})

    assert ai_memory_store.load_ai_core_memory() == {
        "user@example.com": [{"answer": "Hello"}]
    }


def test_ai_feed_learning_store_accepts_only_dict(monkeypatch, tmp_path):
    repository = JsonAiMemoryRepository(tmp_path / "ai_core_memory.json", tmp_path / "ai_feed_learning.json")
    repository.feed_store.save([])
    monkeypatch.setattr(ai_memory_store, "get_ai_memory_repository", lambda: repository)

    assert ai_memory_store.load_ai_feed_learning() == {}


def test_ai_feed_learning_store_saves_learning(monkeypatch, tmp_path):
    repository = JsonAiMemoryRepository(tmp_path / "ai_core_memory.json", tmp_path / "ai_feed_learning.json")
    monkeypatch.setattr(ai_memory_store, "get_ai_memory_repository", lambda: repository)

    ai_memory_store.save_ai_feed_learning({"user@example.com": {"actions": []}})

    assert ai_memory_store.load_ai_feed_learning() == {
        "user@example.com": {"actions": []}
    }
