from backend.models import User
from backend.services.message_service import append_message, chat_summaries, create_text_message, next_message_id, visible_chat_messages


def test_next_message_id_and_append_message():
    messages = [{"id": 2}, {"id": "bad"}]
    message = create_text_message("alice@example.com", "bob@example.com", "Hello", time_text="now")

    assert next_message_id(messages) == 3
    appended = append_message(messages, message)

    assert appended["id"] == 3
    assert appended["from"] == "alice@example.com"
    assert appended["to"] == "bob@example.com"
    assert appended["message"] == "Hello"


def test_visible_chat_messages_filters_deleted_and_other_chats():
    messages = [
        {"id": 1, "from": "alice@example.com", "to": "bob@example.com", "message": "A"},
        {"id": 2, "from": "bob@example.com", "to": "alice@example.com", "message": "B"},
        {"id": 3, "from": "alice@example.com", "to": "tim@example.com", "message": "C"},
        {"id": 4, "from": "bob@example.com", "to": "alice@example.com", "deleted_for_everyone": True},
        {"id": 5, "from": "bob@example.com", "to": "alice@example.com", "deleted_for": ["alice@example.com"]},
    ]

    visible = visible_chat_messages(messages, "alice@example.com", "bob@example.com")

    assert [message["id"] for message in visible] == [1, 2]


def test_chat_summaries_returns_last_visible_conversation_per_user():
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    bob = User("Bob", 30, "bob@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    users = {alice.email: alice, bob.email: bob}
    messages = [
        {"id": 1, "from": "alice@example.com", "to": "bob@example.com", "message": "First"},
        {"id": 2, "from": "bob@example.com", "to": "alice@example.com", "message": "Last"},
    ]

    summaries = chat_summaries(
        messages,
        "alice@example.com",
        lambda email: users.get(email),
        lambda one, two: False,
    )

    assert len(summaries) == 1
    assert summaries[0]["user"].email == "bob@example.com"
    assert summaries[0]["last_message"]["message"] == "Last"
