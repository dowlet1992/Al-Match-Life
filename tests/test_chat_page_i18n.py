import app
from backend.models import User
from io import BytesIO
from werkzeug.datastructures import FileStorage


def login(client, email):
    with client.session_transaction() as session:
        session["user_email"] = email
        session["csrf_token"] = "token-1"


def make_user(email, name, language=""):
    user = User(name, 28, email, "hashed", "Germany", "", "Founder", "", [], [], [], [])
    user.language = language
    return user


def test_chat_page_uses_saved_german_for_primary_interface(monkeypatch):
    alice = make_user("alice@example.com", "Alice", language="de")
    bob = make_user("bob@example.com", "Bob")
    messages = [{
        "id": 1,
        "from": "alice@example.com",
        "to": "bob@example.com",
        "message": "Hello",
        "time": "10:00",
        "status": "sent",
    }]

    monkeypatch.setattr(app, "users", [alice, bob])
    monkeypatch.setattr(app, "load_messages", lambda: messages)
    monkeypatch.setattr(app, "save_messages", lambda messages: None)
    monkeypatch.setattr(app, "load_typing_status", lambda: {})
    monkeypatch.setattr(app, "load_presence_status", lambda: {})
    monkeypatch.setattr(app, "save_presence_status", lambda data: None)
    monkeypatch.setattr(app, "get_avatar_url", lambda email: f"/avatar/{email}.png")
    monkeypatch.setattr(app, "get_message_permission_status", lambda sender, receiver: (True, "", ""))
    monkeypatch.setattr(app, "format_visible_last_seen", lambda viewer_email, owner_email, timestamp: "online")

    client = app.app.test_client()
    login(client, "alice@example.com")

    response = client.get("/chat/alice@example.com/bob@example.com", headers={"Accept-Language": "ru-RU"})

    assert response.status_code == 200
    assert b'<html lang="de" dir="ltr">' in response.data
    assert app.translation_bundle("de")["messages"].encode() in response.data
    assert app.translation_bundle("de")["settings"].encode() in response.data
    assert "Назад".encode("utf-8") not in response.data
    assert "Поиск сообщений".encode("utf-8") not in response.data
    assert "Написать сообщение".encode("utf-8") not in response.data
    assert "Голосовое сообщение".encode("utf-8") not in response.data
    assert "Ответить".encode("utf-8") not in response.data
    assert "Удалить у меня".encode("utf-8") not in response.data
    assert "Ничего не найдено".encode("utf-8") not in response.data
    assert b"/static/chat.css" in response.data
    assert b"/static/chat.js" in response.data
    assert b"<script>" not in response.data
    assert b'id="chatConfig"' in response.data
    assert b'data-csrf-token="token-1"' in response.data


def test_chat_page_renders_typing_status_in_english(monkeypatch):
    alice = make_user("alice@example.com", "Alice", language="en")
    bob = make_user("bob@example.com", "Bob")

    monkeypatch.setattr(app, "users", [alice, bob])
    monkeypatch.setattr(app, "load_messages", lambda: [])
    monkeypatch.setattr(app, "save_messages", lambda messages: None)
    monkeypatch.setattr(app, "load_typing_status", lambda: {"bob@example.com->alice@example.com": 999999999999})
    monkeypatch.setattr(app, "load_presence_status", lambda: {})
    monkeypatch.setattr(app, "save_presence_status", lambda data: None)
    monkeypatch.setattr(app, "get_avatar_url", lambda email: f"/avatar/{email}.png")
    monkeypatch.setattr(app, "get_message_permission_status", lambda sender, receiver: (True, "", ""))

    client = app.app.test_client()
    login(client, "alice@example.com")

    response = client.get("/chat/alice@example.com/bob@example.com")

    assert response.status_code == 200
    assert b'<html lang="en" dir="ltr">' in response.data
    assert b"typing a message..." in response.data


def test_chat_page_exposes_reviewed_turkish_message_errors(monkeypatch):
    alice = make_user("alice@example.com", "Alice", language="tr")
    bob = make_user("bob@example.com", "Bob")

    monkeypatch.setattr(app, "users", [alice, bob])
    monkeypatch.setattr(app, "load_messages", lambda: [])
    monkeypatch.setattr(app, "save_messages", lambda messages: None)
    monkeypatch.setattr(app, "load_typing_status", lambda: {})
    monkeypatch.setattr(app, "load_presence_status", lambda: {})
    monkeypatch.setattr(app, "save_presence_status", lambda data: None)
    monkeypatch.setattr(app, "get_avatar_url", lambda email: f"/avatar/{email}.png")
    monkeypatch.setattr(app, "get_message_permission_status", lambda sender, receiver: (True, "", ""))
    monkeypatch.setattr(app, "format_visible_last_seen", lambda *args: "çevrimiçi")

    client = app.app.test_client()
    login(client, alice.email)
    response = client.get(f"/chat/{alice.email}/{bob.email}")

    assert response.status_code == 200
    assert b'<html lang="tr" dir="ltr">' in response.data
    assert "Mesaj gönderilemedi. Lütfen bağlantınızı kontrol edip tekrar deneyin.".encode() in response.data
    assert "Taslak kaydedildi".encode() in response.data
    assert "Bağlantı yeniden kuruldu".encode() in response.data


def test_chat_message_actions_do_not_embed_message_text_in_javascript(monkeypatch):
    alice = make_user("alice@example.com", "Alice", language="en")
    bob = make_user("bob@example.com", "Bob")
    dangerous_text = '`); alert(1); // " onmouseover="alert(2)'
    messages = [{
        "id": 1,
        "from": "alice@example.com",
        "to": "bob@example.com",
        "message": dangerous_text,
        "time": '10:00" onclick="alert(3)',
        "status": "sent",
    }]
    monkeypatch.setattr(app, "users", [alice, bob])
    monkeypatch.setattr(app, "load_messages", lambda: messages)
    monkeypatch.setattr(app, "save_messages", lambda value: None)
    monkeypatch.setattr(app, "load_typing_status", lambda: {})
    monkeypatch.setattr(app, "load_presence_status", lambda: {})
    monkeypatch.setattr(app, "save_presence_status", lambda data: None)
    monkeypatch.setattr(app, "get_avatar_url", lambda email: "/avatar.png")
    monkeypatch.setattr(app, "get_message_permission_status", lambda sender, receiver: (True, "", ""))
    monkeypatch.setattr(app, "format_visible_last_seen", lambda *args: "online")

    client = app.app.test_client()
    login(client, alice.email)
    response = client.get(f"/chat/{alice.email}/{bob.email}")

    assert response.status_code == 200
    assert b"replyToMessage('1'," not in response.data
    assert b'data-message-action="reply"' in response.data
    assert b'data-message-text="`); alert(1); // &#34; onmouseover=&#34;alert(2)"' in response.data
    assert b'data-message-time="10:00&#34; onclick=&#34;alert(3)"' in response.data


def test_chat_renderer_has_no_inline_styles_or_event_handlers():
    source = open("backend/chat_call_routes.py", encoding="utf-8").read()
    chat_source = source[source.index("def chat_page"):source.index('@chat_call_routes.route("/react_message')]
    template_source = open("frontend/chat.html", encoding="utf-8").read()

    assert "<style>" not in chat_source
    assert 'render_template(' in chat_source
    assert '"chat.html"' in chat_source
    assert "<html" not in chat_source
    assert "chat_html" not in chat_source
    assert "media_html" not in chat_source
    assert "restriction_notice_html" not in chat_source
    assert "/static/chat.css" in template_source
    assert "/static/chat.js" in template_source
    assert "<script>" not in chat_source
    for event_name in (
        "onclick=",
        "ondblclick=",
        "oncontextmenu=",
        "onmousedown=",
        "ontouchstart=",
        "oninput=",
    ):
        assert event_name not in chat_source


def test_chat_upload_uses_private_uuid_filename(monkeypatch, tmp_path):
    alice = make_user("alice@example.com", "Alice", language="en")
    bob = make_user("bob@example.com", "Bob")
    messages = []
    monkeypatch.setattr(app, "users", [alice, bob])
    monkeypatch.setattr(app, "UPLOAD_FOLDER", str(tmp_path))
    monkeypatch.setattr(app, "load_messages", lambda: messages)
    monkeypatch.setattr(app, "save_messages", lambda value: None)
    monkeypatch.setattr(app, "load_typing_status", lambda: {})
    monkeypatch.setattr(app, "load_presence_status", lambda: {})
    monkeypatch.setattr(app, "save_presence_status", lambda data: None)
    monkeypatch.setattr(app, "get_avatar_url", lambda email: "/avatar.png")
    monkeypatch.setattr(app, "get_message_permission_status", lambda sender, receiver: (True, "", ""))
    monkeypatch.setattr(app, "format_visible_last_seen", lambda *args: "online")

    client = app.app.test_client()
    login(client, alice.email)
    response = client.post(
        f"/chat/{alice.email}/{bob.email}",
        data={
            "csrf_token": "token-1",
            "media": (BytesIO(b"\x89PNG\r\n\x1a\nprivate-image"), "Personal Name.png"),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 302
    media_url = messages[0]["media_url"]
    assert f"/media-files/chat_{alice.id}_" in media_url
    assert alice.email not in media_url
    assert "Personal_Name" not in media_url
    assert messages[0]["media_name"] == "Personal_Name.png"
    assert (tmp_path / media_url.rsplit("/", 1)[-1]).exists()


def test_chat_accepts_uuid_and_rejects_spoofed_sender(monkeypatch):
    alice = make_user("alice@example.com", "Alice", language="en")
    bob = make_user("bob@example.com", "Bob")
    monkeypatch.setattr(app, "users", [alice, bob])
    monkeypatch.setattr(app, "load_messages", lambda: [])
    monkeypatch.setattr(app, "load_typing_status", lambda: {})
    monkeypatch.setattr(app, "load_presence_status", lambda: {})
    monkeypatch.setattr(app, "save_presence_status", lambda data: None)
    monkeypatch.setattr(app, "get_avatar_url", lambda email: "/avatar.png")
    monkeypatch.setattr(app, "get_message_permission_status", lambda sender, receiver: (True, "", ""))
    monkeypatch.setattr(app, "format_visible_last_seen", lambda *args: "online")
    monkeypatch.setattr(app, "log_security_event", lambda *args: None)
    client = app.app.test_client()
    login(client, alice.email)

    own_response = client.get(f"/chat/{alice.id}/{bob.id}")
    spoofed_response = client.get(f"/chat/{bob.id}/{alice.id}")

    assert own_response.status_code == 200
    assert f'/messages/{alice.id}'.encode() in own_response.data
    assert spoofed_response.status_code == 403


def test_chat_voice_webm_is_saved_and_rendered_as_audio(monkeypatch, tmp_path):
    alice = make_user("alice@example.com", "Alice", language="en")
    bob = make_user("bob@example.com", "Bob")
    messages = []
    monkeypatch.setattr(app, "users", [alice, bob])
    monkeypatch.setattr(app, "UPLOAD_FOLDER", str(tmp_path))
    monkeypatch.setattr(app, "load_messages", lambda: messages)
    monkeypatch.setattr(app, "save_messages", lambda value: None)
    monkeypatch.setattr(app, "load_typing_status", lambda: {})
    monkeypatch.setattr(app, "load_presence_status", lambda: {})
    monkeypatch.setattr(app, "save_presence_status", lambda data: None)
    monkeypatch.setattr(app, "get_avatar_url", lambda email: "/avatar.png")
    monkeypatch.setattr(app, "get_message_permission_status", lambda sender, receiver: (True, "", ""))
    monkeypatch.setattr(app, "format_visible_last_seen", lambda *args: "online")

    client = app.app.test_client()
    login(client, alice.email)
    response = client.post(
        f"/chat/{alice.email}/{bob.email}",
        data={
            "csrf_token": "token-1",
            "media": (BytesIO(b"\x1a\x45\xdf\xa3opus-voice"), "voice-message.webm", "audio/webm"),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 302
    assert messages[0]["media_type"] == "audio"
    assert messages[0]["media_url"].endswith(".webm")


def test_chat_voice_recorder_negotiates_format_and_uploads_blob_directly():
    script = open("static/chat.js", encoding="utf-8").read()

    assert "MediaRecorder.isTypeSupported" in script
    assert "audio/webm;codecs=opus" in script
    assert "audio/ogg;codecs=opus" in script
    assert "audio/mp4" in script
    assert "formData.append('media', audioBlob" in script
    assert "new DataTransfer()" not in script
    assert script.startswith("(() => {")
    assert "window.__chatPageCleanup" in script
    assert "app:navigation-before" in script


def test_chat_composer_preserves_drafts_and_reports_connectivity():
    template = open("frontend/chat.html", encoding="utf-8").read()
    script = open("static/chat.js", encoding="utf-8").read()

    assert 'maxlength="2000"' in template
    assert 'id="composerStatus"' in template
    assert 'role="status"' in template
    assert 'id="composerCounter"' in template
    assert "novix-chat-draft:" in script
    assert "window.localStorage.setItem(messageDraftKey, value)" in script
    assert "window.localStorage.getItem(messageDraftKey)" in script
    assert "window.localStorage.removeItem(messageDraftKey)" in script
    assert "window.addEventListener('offline'" in script
    assert "window.addEventListener('online'" in script
    assert "saveMessageDraft(false);updateComposerCounter()" in script


def test_chat_send_failure_uses_localized_safe_copy():
    script = open("static/chat.js", encoding="utf-8").read()

    assert "CHAT_I18N.messageSendError" in script
    assert "alert(error.message" not in script
    assert "throw new Error('send_failed')" in script


def test_document_allowlist_accepts_real_pdf_and_utf8_text_only():
    pdf = FileStorage(stream=BytesIO(b"%PDF-1.7\nsafe"), filename="document.pdf")
    fake_pdf = FileStorage(stream=BytesIO(b"<script>alert(1)</script>"), filename="document.pdf")
    text = FileStorage(stream=BytesIO("Безопасный текст".encode()), filename="notes.txt")
    binary_text = FileStorage(stream=BytesIO(b"text\x00binary"), filename="notes.txt")

    assert app.allowed_mime_type(pdf) is True
    assert app.allowed_mime_type(fake_pdf) is False
    assert app.allowed_mime_type(text) is True
    assert app.allowed_mime_type(binary_text) is False


def test_chat_ui_and_server_do_not_advertise_unscanned_archive_documents():
    template = open("frontend/chat.html", encoding="utf-8").read()
    source = open("backend/chat_call_routes.py", encoding="utf-8").read()

    for extension in (".doc", ".docx", ".xls", ".xlsx", ".zip"):
        assert extension not in template
    assert 'document_ext = ["pdf", "txt"]' in source


def test_upload_validator_enforces_per_category_size_limits(monkeypatch):
    monkeypatch.setitem(app.UPLOAD_SIZE_LIMITS, "image", 12)
    allowed_image = FileStorage(
        stream=BytesIO(b"\x89PNG\r\n\x1a\n1234"),
        filename="small.png",
    )
    oversized_image = FileStorage(
        stream=BytesIO(b"\x89PNG\r\n\x1a\n12345"),
        filename="large.png",
    )

    assert app.allowed_mime_type(allowed_image) is True
    assert app.allowed_mime_type(oversized_image) is False
