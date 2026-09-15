import app


def test_grounding_revision_is_not_needed_for_supported_numbers(monkeypatch):
    monkeypatch.setattr(app, "call_ai_chat", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("unexpected revision")))

    answer = app._grounded_revision("Germany has 16 states.", "Germany has 16 states.")

    assert answer == "Germany has 16 states."


def test_grounding_revision_removes_unsupported_precision(monkeypatch):
    calls = []

    def revise(messages, **kwargs):
        calls.append((messages, kwargs))
        return "France has a larger metropolitan area than Germany."

    monkeypatch.setattr(app, "call_ai_chat", revise)
    answer = app._grounded_revision(
        "France covers 643,801 km2 and is larger than Germany.",
        "Metropolitan France is larger in area than Germany.",
    )

    assert answer == "France has a larger metropolitan area than Germany."
    assert calls[0][1]["strict"] is True
    assert calls[0][1]["temperature"] == 0.0
