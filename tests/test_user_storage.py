from backend.models import User
from backend.storage import load_users_from_json, save_users_to_json
from backend.repositories import JsonStore


def test_user_storage_saves_and_loads_users(tmp_path):
    path = tmp_path / "users.json"
    user = User(
        "Alice",
        30,
        "alice@example.com",
        "hashed-password",
        "Germany",
        "Builder",
        "Engineer",
        "partners",
        ["English"],
        ["Build"],
        ["AI"],
        ["Python"],
        80,
        True,
        True,
        "2026-01-01",
        True,
        False,
        True,
        "2026-01-02",
        "email",
    )

    save_users_to_json([user], filename=path)
    loaded_users = load_users_from_json(filename=path)

    assert len(loaded_users) == 1
    assert loaded_users[0].email == "alice@example.com"
    assert loaded_users[0].onboarding_completed is True
    assert loaded_users[0].account_verified_via == "email"


def test_user_storage_returns_none_for_invalid_shape(tmp_path):
    path = tmp_path / "users.json"
    JsonStore(path, []).save({"users": []})

    assert load_users_from_json(filename=path) is None
