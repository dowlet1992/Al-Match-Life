from backend.repositories import JsonStore


def test_json_store_returns_default_for_missing_file(tmp_path):
    store = JsonStore(tmp_path / "missing.json", {"items": []})

    data = store.load()
    data["items"].append("changed")

    assert store.load() == {"items": []}


def test_json_store_saves_and_loads_data(tmp_path):
    store = JsonStore(tmp_path / "nested" / "data.json", {"items": []})

    store.save({"items": ["one"]})

    assert store.load() == {"items": ["one"]}


def test_json_store_returns_default_for_invalid_json(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{", encoding="utf-8")
    store = JsonStore(path, [])

    assert store.load() == []
