import json

from backend.services.knowledge_retrieval_service import LocalKnowledgeBase


def test_retrieval_returns_grounded_country_facts_and_source():
    context, sources = LocalKnowledgeBase().context("главные отличия Германии от Франции и членство в ЕС")
    assert "both members of the European Union" in context
    assert "unitary semi-presidential republic" in context
    assert "Metropolitan France is larger" in context
    assert sources == ["European Union country profiles and national constitutional summaries"]


def test_retrieval_fails_closed_for_unrelated_question(tmp_path):
    corpus = tmp_path / "knowledge.json"
    corpus.write_text(json.dumps([{"title": "Alpha", "content": "Beta gamma", "source": "Test"}]), encoding="utf-8")
    assert LocalKnowledgeBase([corpus]).context("unrelated quantum question") == ("", [])


def test_invalid_knowledge_file_is_ignored(tmp_path):
    corpus = tmp_path / "broken.json"
    corpus.write_text("not-json", encoding="utf-8")
    assert LocalKnowledgeBase([corpus]).search("anything") == []


def test_retrieval_does_not_claim_grounding_from_one_generic_entity():
    context, sources = LocalKnowledgeBase().context("кто сейчас президент Франции")

    assert context == ""
    assert sources == []


def test_retrieval_normalizes_common_russian_word_endings():
    context, sources = LocalKnowledgeBase().context("Германия и Франция являются членами Евросоюза?")

    assert "both members of the European Union" in context
    assert sources
