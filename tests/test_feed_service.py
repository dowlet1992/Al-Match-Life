from backend.models import User
from backend.services.feed_service import add_comment, append_post, create_text_post, find_post, toggle_list_value


def test_feed_service_create_and_append_post():
    user = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    feed_data = {"posts": [{"id": 2, "text": "old"}]}

    post = create_text_post(
        user,
        "New idea",
        post_type="Идея",
        location="Berlin",
        hashtags=["ai"],
        language="en",
    )
    appended = append_post(feed_data, post)

    assert appended["id"] == 3
    assert appended["email"] == "alice@example.com"
    assert appended["text"] == "New idea"
    assert feed_data["posts"][-1]["hashtags"] == ["ai"]


def test_feed_service_find_post_toggle_and_comment():
    feed_data = {"posts": [{"id": 1, "likes": [], "saves": [], "comments": []}]}
    posts, post = find_post(feed_data, 1)

    assert posts == feed_data["posts"]
    assert post["id"] == 1

    assert toggle_list_value(post, "likes", "alice@example.com") is True
    assert post["likes"] == ["alice@example.com"]
    assert toggle_list_value(post, "likes", "alice@example.com") is False
    assert post["likes"] == []

    assert toggle_list_value(post, "saves", "alice@example.com") is True
    comment = add_comment(post, "alice@example.com", "Alice", "Great")

    assert post["saves"] == ["alice@example.com"]
    assert comment["text"] == "Great"
    assert post["comments"][0]["author"] == "alice@example.com"
