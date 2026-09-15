import json
from unittest.mock import patch

from backend.repositories.json_store import JsonStore


def test_json_store_reuses_cached_decode_and_returns_isolated_values(tmp_path):
    path = tmp_path / "data.json"
    path.write_text('{"items":[1]}', encoding="utf-8")
    store = JsonStore(path, {"items": []})
    JsonStore.clear_cache()

    with patch("builtins.open", wraps=open) as tracked_open:
        first = store.load()
        first["items"].append(2)
        second = store.load()

    assert tracked_open.call_count == 1
    assert second == {"items": [1]}


def test_json_store_invalidates_cache_when_file_changes(tmp_path):
    path = tmp_path / "data.json"
    path.write_text('{"value":"one"}', encoding="utf-8")
    store = JsonStore(path, {})
    JsonStore.clear_cache()

    assert store.load() == {"value": "one"}
    path.write_text('{"value":"updated"}', encoding="utf-8")

    assert store.load() == {"value": "updated"}


def test_json_store_save_is_compact_atomic_and_updates_cache(tmp_path):
    path = tmp_path / "nested" / "data.json"
    store = JsonStore(path, {})
    JsonStore.clear_cache()
    value = {"message": "Привет", "items": [1, 2, 3]}

    store.save(value)
    value["items"].append(4)

    raw = path.read_text(encoding="utf-8")
    assert raw == '{"message":"Привет","items":[1,2,3]}\n'
    assert json.loads(raw) == store.load()
    assert store.load()["items"] == [1, 2, 3]


def test_json_store_cache_is_bounded(tmp_path, monkeypatch):
    JsonStore.clear_cache()
    monkeypatch.setattr(JsonStore, "_max_cache_entries", 2)

    for index in range(3):
        path = tmp_path / f"{index}.json"
        path.write_text(str(index), encoding="utf-8")
        JsonStore(path, None).load()

    assert len(JsonStore._cache) == 2
