import app


def set_csrf(client):
    with client.session_transaction() as session:
        session["csrf_token"] = "token-1"


def test_core_user_journey_from_registration_to_main_pages(monkeypatch):
    journey_users = []
    sent_codes = []

    monkeypatch.setattr(app, "users", journey_users)
    monkeypatch.setattr(app, "save_users_to_json", lambda users_value: None)
    monkeypatch.setattr(app, "create_verification_code", lambda purpose, contact_type, contact_value: "123456")
    monkeypatch.setattr(app, "send_verification_code", lambda contact_type, contact_value, code: sent_codes.append((contact_type, contact_value, code)))
    monkeypatch.setattr(app, "verify_contact_code", lambda purpose, contact_type, contact_value, code: code == "123456")
    monkeypatch.setattr(app, "bind_session_to_user", lambda user: None)
    monkeypatch.setattr(app, "log_security_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "get_notifications", lambda email: [])
    monkeypatch.setattr(app, "load_feed", lambda: {"posts": []})
    monkeypatch.setattr(app, "load_stories", lambda: {"stories": []})
    monkeypatch.setattr(app, "load_messages", lambda: [])
    monkeypatch.setattr(app, "generate_life_radar", lambda user: [])
    monkeypatch.setattr(app, "find_best_matches", lambda user, users: [])
    monkeypatch.setattr(app, "analyze_user_profile", lambda user: {"summary": "AI profile hint"})
    monkeypatch.setattr(app, "get_avatar_url", lambda email: "/static/default-avatar.png")

    client = app.app.test_client()

    home_response = client.get("/", headers={"Accept-Language": "en-US"})
    register_page_response = client.get("/register", headers={"Accept-Language": "en-US"})

    assert home_response.status_code == 200
    assert register_page_response.status_code == 200

    set_csrf(client)
    register_response = client.post(
        "/register",
        data={
            "csrf_token": "token-1",
            "contact_type": "email",
            "email": "journey@example.com",
            "phone": "",
            "password": "journey-password-123",
            "name": "Journey User",
            "age": "31",
            "country": "Germany",
            "bio": "Building a professional network",
            "profession": "Product Builder",
            "looking_for": "Partners",
            "languages": "English, German",
            "goals": "Build AI Match Life",
            "interests": "AI, startups",
            "skills": "Product, Python",
        },
    )

    assert register_response.status_code == 302
    assert register_response.headers["Location"].endswith(
        "/verify_account?contact_type=email&contact_value=journey%40example.com"
    )
    assert len(journey_users) == 1
    assert journey_users[0].account_verified is False
    assert sent_codes == [("email", "journey@example.com", "123456")]

    verify_response = client.post(
        "/verify_account?contact_type=email&contact_value=journey@example.com",
        data={
            "csrf_token": "token-1",
            "code": "123456",
        },
    )

    assert verify_response.status_code == 303
    assert verify_response.headers["Location"].endswith("/dashboard/journey@example.com")

    onboarding_response = client.get("/onboarding/journey@example.com", headers={"Accept-Language": "en-US"})
    assert onboarding_response.status_code == 200
    assert b"AI profile hint" in onboarding_response.data

    skip_onboarding_response = client.post(
        "/onboarding/journey@example.com",
        data={
            "csrf_token": "token-1",
            "action": "skip",
        },
    )

    assert skip_onboarding_response.status_code == 303
    assert skip_onboarding_response.headers["Location"].endswith("/dashboard/journey@example.com")

    main_pages = [
        "/dashboard/journey@example.com",
        "/feed/journey@example.com",
        "/profile/journey@example.com?viewer=journey@example.com",
        "/matches/journey@example.com",
        "/messages/journey@example.com",
        "/settings/journey@example.com",
    ]

    for page_url in main_pages:
        response = client.get(page_url, headers={"Accept-Language": "en-US"})
        assert response.status_code == 200, page_url
        assert b"User not found" not in response.data
