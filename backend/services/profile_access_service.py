def normalize_email(value):
    return str(value or "").strip().lower()


def clean_text(value):
    return str(value or "").strip()


def message_permission_status(
    sender_email,
    receiver_email,
    sender_verified,
    receiver_settings,
    is_blocked,
    is_restricted,
    are_friends,
):
    sender_email = normalize_email(sender_email)
    receiver_email = normalize_email(receiver_email)

    if not sender_email or not receiver_email:
        return False, "Сообщения недоступны", "Невозможно проверить настройки сообщений."

    if is_blocked(receiver_email, sender_email):
        return False, "🚫 Сообщение недоступно", "Этот пользователь заблокировал вас. Вы не можете отправить ему сообщение."

    if is_blocked(sender_email, receiver_email):
        return False, "🚫 Пользователь заблокирован", "Вы заблокировали этого пользователя. Разблокируйте его в настройках, если хотите написать сообщение."

    if is_restricted(receiver_email, sender_email):
        return False, "Сообщения недоступны", "Этот пользователь ограничил возможность связи с вами."

    receiver_settings = receiver_settings if isinstance(receiver_settings, dict) else {}
    permission = receiver_settings.get("message_permission", "everyone")

    if permission == "none":
        return False, "💬 Сообщения закрыты", "Этот пользователь сейчас не принимает личные сообщения."

    if permission == "friends" and not are_friends(sender_email, receiver_email):
        return False, "👥 Только друзья", "Этот пользователь принимает сообщения только от друзей. Добавьте друг друга в друзья, чтобы начать переписку."

    if permission == "verified" and sender_verified is False:
        return False, "🛡 Только verified", "Этот пользователь принимает сообщения только от проверенных аккаунтов."

    return True, "", ""


def profile_view_status(viewer_email, owner_email, owner_settings, is_blocked, are_friends):
    viewer_email = normalize_email(viewer_email)
    owner_email = normalize_email(owner_email)
    owner_settings = owner_settings if isinstance(owner_settings, dict) else {}

    if not viewer_email or not owner_email:
        return {
            "status": "not_found",
            "is_own_profile": False,
            "profile_visibility": "public",
        }

    is_own_profile = viewer_email == owner_email
    profile_visibility = clean_text(owner_settings.get("profile_visibility", "public")) or "public"
    viewer_blocked_owner = is_blocked(viewer_email, owner_email)
    owner_blocked_viewer = is_blocked(owner_email, viewer_email)

    if viewer_blocked_owner and not is_own_profile:
        return {
            "status": "viewer_blocked_owner",
            "is_own_profile": is_own_profile,
            "profile_visibility": profile_visibility,
        }

    if owner_blocked_viewer and not is_own_profile:
        return {
            "status": "owner_blocked_viewer",
            "is_own_profile": is_own_profile,
            "profile_visibility": profile_visibility,
        }

    if not is_own_profile and owner_settings.get("account_deactivated") is True:
        return {
            "status": "deactivated",
            "is_own_profile": is_own_profile,
            "profile_visibility": profile_visibility,
        }

    if not is_own_profile and profile_visibility == "private":
        return {
            "status": "private",
            "is_own_profile": is_own_profile,
            "profile_visibility": profile_visibility,
        }

    if not is_own_profile and profile_visibility == "friends" and not are_friends(viewer_email, owner_email):
        return {
            "status": "friends_only",
            "is_own_profile": is_own_profile,
            "profile_visibility": profile_visibility,
        }

    return {
        "status": "allowed",
        "is_own_profile": is_own_profile,
        "profile_visibility": profile_visibility,
    }


def visible_last_seen_text(viewer_email, owner_email, owner_settings, timestamp_value, format_last_seen):
    viewer_email = normalize_email(viewer_email)
    owner_email = normalize_email(owner_email)

    if viewer_email == owner_email:
        return format_last_seen(timestamp_value)

    owner_settings = owner_settings if isinstance(owner_settings, dict) else {}
    if owner_settings.get("show_online_status") is False:
        return "статус скрыт"

    return format_last_seen(timestamp_value)


def can_show_in_ai_recommendations(viewer_email, candidate_email, candidate_settings, is_blocked, is_restricted):
    viewer_email = normalize_email(viewer_email)
    candidate_email = normalize_email(candidate_email)

    if not viewer_email or not candidate_email:
        return False

    if candidate_email == viewer_email:
        return False

    if is_blocked(viewer_email, candidate_email) or is_blocked(candidate_email, viewer_email):
        return False

    if is_restricted(viewer_email, candidate_email) or is_restricted(candidate_email, viewer_email):
        return False

    candidate_settings = candidate_settings if isinstance(candidate_settings, dict) else {}

    if candidate_settings.get("account_deactivated") is True:
        return False

    if candidate_settings.get("show_in_search") is False:
        return False

    if candidate_settings.get("recommend_my_profile") is False:
        return False

    if candidate_settings.get("vip_mode") is True:
        return False

    return True
