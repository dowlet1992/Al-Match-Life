from backend import social_safety_store, stories_store
from backend.repositories.social_safety_repository import (
    JsonRelationshipMapRepository,
    JsonReportsRepository,
)
from backend.repositories.stories_repository import JsonStoriesRepository


def test_stories_store_requires_stories_list(monkeypatch, tmp_path):
    repository = JsonStoriesRepository(tmp_path / "stories.json")
    repository.store.save({"stories": {}})
    monkeypatch.setattr(stories_store, "get_stories_repository", lambda: repository)

    assert stories_store.load_stories() == {"stories": []}


def test_stories_store_saves_stories(monkeypatch, tmp_path):
    repository = JsonStoriesRepository(tmp_path / "stories.json")
    monkeypatch.setattr(stories_store, "get_stories_repository", lambda: repository)

    stories_store.save_stories({"stories": [{"id": "story-1"}]})

    assert stories_store.load_stories() == {"stories": [{"id": "story-1"}]}


def test_blocks_store_supports_legacy_plain_dict(monkeypatch, tmp_path):
    repository = JsonRelationshipMapRepository(tmp_path / "blocks.json", "blocks")
    repository.store.save({"alice@example.com": ["bob@example.com"]})
    monkeypatch.setattr(social_safety_store, "get_blocks_repository", lambda: repository)

    assert social_safety_store.load_blocks() == {
        "blocks": {"alice@example.com": ["bob@example.com"]}
    }


def test_reports_store_requires_reports_list(monkeypatch, tmp_path):
    repository = JsonReportsRepository(tmp_path / "reports.json")
    repository.store.save({"reports": {}})
    monkeypatch.setattr(social_safety_store, "get_reports_repository", lambda: repository)

    assert social_safety_store.load_reports() == {"reports": []}


def test_restrictions_store_saves_restrictions(monkeypatch, tmp_path):
    repository = JsonRelationshipMapRepository(tmp_path / "restrictions.json", "restrictions")
    monkeypatch.setattr(social_safety_store, "get_restrictions_repository", lambda: repository)

    social_safety_store.save_restrictions({
        "restrictions": {"alice@example.com": ["bob@example.com"]}
    })

    assert social_safety_store.load_restrictions() == {
        "restrictions": {"alice@example.com": ["bob@example.com"]}
    }


def test_hidden_stories_store_saves_hidden_stories(monkeypatch, tmp_path):
    repository = JsonRelationshipMapRepository(tmp_path / "hidden_stories.json", "hidden_stories")
    monkeypatch.setattr(social_safety_store, "get_hidden_stories_repository", lambda: repository)

    social_safety_store.save_hidden_stories({
        "hidden_stories": {"alice@example.com": ["bob@example.com"]}
    })

    assert social_safety_store.load_hidden_stories() == {
        "hidden_stories": {"alice@example.com": ["bob@example.com"]}
    }
