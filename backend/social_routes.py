from flask import Blueprint, abort, jsonify, redirect, render_template, request

from backend.services.social_notification_service import social_notification_text


def create_social_routes(deps):
    social_routes = Blueprint("social_routes", __name__)

    def localized_copy(user):
        ui = deps["translation_bundle"](deps["get_current_language"](user))
        language = ui.get("language_code", "en")
        copies = {
            "ru": {
                "friends": "Друзья", "followers": "Подписчики", "following": "Подписки",
                "requests": "Заявки в друзья", "open": "Открыть профиль", "empty": "Пока список пуст.",
                "request_empty": "Заявок пока нет.", "request_text": "хочет добавить вас в друзья",
                "accept": "Принять", "decline": "Отклонить", "accepted": "Принято", "declined": "Отклонено", "trust": "Уровень доверия",
                "unavailable": "Действие недоступно", "follow_blocked": "Подписка невозможна, потому что один из пользователей заблокировал другого.",
                "request_blocked": "Заявку в друзья нельзя отправить, потому что один из пользователей заблокировал другого.",
                "accept_blocked": "Подтверждение дружбы невозможно, потому что один из пользователей заблокировал другого.",
                "decline_blocked": "Отклонение заявки недоступно, потому что один из пользователей заблокировал другого.",
            },
            "de": {
                "friends": "Freunde", "followers": "Follower", "following": "Abonniert",
                "requests": "Freundschaftsanfragen", "open": "Profil öffnen", "empty": "Die Liste ist leer.",
                "request_empty": "Keine Freundschaftsanfragen.", "request_text": "möchte Sie als Freund hinzufügen",
                "accept": "Annehmen", "decline": "Ablehnen", "accepted": "Angenommen", "declined": "Abgelehnt", "trust": "Vertrauenswert",
                "unavailable": "Aktion nicht verfügbar", "follow_blocked": "Das Folgen ist nicht möglich, weil eine Person die andere blockiert hat.",
                "request_blocked": "Die Freundschaftsanfrage kann nicht gesendet werden, weil eine Person die andere blockiert hat.",
                "accept_blocked": "Die Freundschaft kann nicht bestätigt werden, weil eine Person die andere blockiert hat.",
                "decline_blocked": "Die Anfrage kann nicht abgelehnt werden, weil eine Person die andere blockiert hat.",
            },
            "en": {
                "friends": "Friends", "followers": "Followers", "following": "Following",
                "requests": "Friend requests", "open": "Open profile", "empty": "The list is empty.",
                "request_empty": "No friend requests yet.", "request_text": "wants to add you as a friend",
                "accept": "Accept", "decline": "Decline", "accepted": "Accepted", "declined": "Declined", "trust": "Trust score",
                "unavailable": "Action unavailable", "follow_blocked": "Following is unavailable because one person has blocked the other.",
                "request_blocked": "The friend request cannot be sent because one person has blocked the other.",
                "accept_blocked": "The friendship cannot be confirmed because one person has blocked the other.",
                "decline_blocked": "The request cannot be declined because one person has blocked the other.",
            },
            "tr": {
                "friends": "Arkadaşlar", "followers": "Takipçiler", "following": "Takip edilenler",
                "requests": "Arkadaşlık istekleri", "open": "Profili aç", "empty": "Liste henüz boş.",
                "request_empty": "Henüz arkadaşlık isteği yok.", "request_text": "sizi arkadaş olarak eklemek istiyor",
                "accept": "Kabul et", "decline": "Reddet", "accepted": "Kabul edildi", "declined": "Reddedildi", "trust": "Güven puanı",
                "unavailable": "İşlem kullanılamıyor", "follow_blocked": "Kullanıcılardan biri diğerini engellediği için takip edilemiyor.",
                "request_blocked": "Kullanıcılardan biri diğerini engellediği için arkadaşlık isteği gönderilemiyor.",
                "accept_blocked": "Kullanıcılardan biri diğerini engellediği için arkadaşlık onaylanamıyor.",
                "decline_blocked": "Kullanıcılardan biri diğerini engellediği için istek reddedilemiyor.",
            },
        }
        return ui, copies.get(language, copies["en"])

    def session_user():
        return deps["find_user_by_email"](deps["current_session_email"]())

    def require_route_owner(route_identifier):
        route_user = deps["find_user_by_identifier"](route_identifier)
        current_email = deps["normalize_email"](deps["current_session_email"]())
        if route_user is None or not current_email or current_email != deps["normalize_email"](route_user.email):
            abort(403)
        return route_user

    def people_page(kind, owner_identifier, value_loader):
        owner = deps["find_user_by_identifier"](owner_identifier)
        if owner is None:
            return "User not found", 404
        viewer = session_user()
        if viewer is None:
            abort(401)
        ui, copy = localized_copy(viewer)
        people = []
        seen = set()
        values = value_loader(owner.email)
        for value in values if isinstance(values, list) else []:
            normalized = deps["normalize_email"](value)
            if not normalized or normalized in seen:
                continue
            person = deps["find_user_by_email"](normalized)
            if person is None:
                continue
            seen.add(normalized)
            people.append({
                "id": person.id,
                "email": person.email,
                "name": person.name,
                "profession": person.profession,
                "trust_score": getattr(person, "trust_score", 0),
                "avatar_url": deps["get_avatar_url"](person.email),
            })
        return render_template(
            "social_list.html", ui=ui, copy=copy, email=viewer.email,
            owner=owner, title=copy[kind], people=people, requests=None,
        )

    def find_pair(viewer_identifier, profile_identifier):
        return (
            deps["find_user_by_identifier"](viewer_identifier),
            deps["find_user_by_identifier"](profile_identifier),
        )

    def blocked(viewer_email, profile_email):
        return deps["is_blocked"](viewer_email, profile_email) or deps["is_blocked"](profile_email, viewer_email)

    def blocked_action_page(viewer, message_key):
        _, copy = localized_copy(viewer)
        return deps["simple_page"](
            f"🚫 {copy['unavailable']}", copy[message_key], viewer.email
        )

    def notify(target, actor, event_type):
        language = deps["get_current_language"](target)
        deps["create_social_notification"](
            target.email,
            social_notification_text(event_type, actor.name, language),
            event_type,
            actor.email,
        )

    def follow_response(viewer, profile, is_following):
        if request.headers.get("X-Requested-With") != "fetch":
            return redirect(f"/profile/{profile.id}?viewer={viewer.id}")
        ui = deps["translation_bundle"](deps["get_current_language"](viewer))
        return jsonify({
            "ok": True,
            "is_following": is_following,
            "followers_count": deps["count_followers"](profile.email),
            "next_action": (
                f"/unfollow/{viewer.id}/{profile.id}"
                if is_following else f"/follow/{viewer.id}/{profile.id}"
            ),
            "label": ui.get("following" if is_following else "follow", "Following" if is_following else "Follow"),
        })

    def friend_request_response(viewer, profile, status, fallback_url):
        if request.headers.get("X-Requested-With") != "fetch":
            return redirect(fallback_url)
        _, copy = localized_copy(viewer)
        return jsonify({
            "ok": True,
            "status": status,
            "label": copy[status],
            "profile_id": profile.id,
        })

    def missing_friend_request_response(fallback_url):
        if request.headers.get("X-Requested-With") != "fetch":
            return redirect(fallback_url)
        return jsonify({"ok": False, "error": "friend_request_not_found"}), 409

    @social_routes.route("/follow/<viewer_identifier>/<profile_identifier>", methods=["POST"])
    @deps["login_required"]
    def follow_route(viewer_identifier, profile_identifier):
        deps["validate_csrf_token"]()
        viewer = require_route_owner(viewer_identifier)
        profile = deps["find_user_by_identifier"](profile_identifier)
        if viewer is None or profile is None:
            return "User not found", 404
        viewer_email, profile_email = viewer.email, profile.email
        if viewer_email == profile_email:
            return redirect(f"/profile/{profile.id}?viewer={viewer.id}")
        if blocked(viewer_email, profile_email):
            deps["log_security_event"]("follow_blocked", viewer_email, f"Blocked follow attempt to {profile_email}")
            return blocked_action_page(viewer, "follow_blocked")
        if deps["follow_user"](viewer_email, profile_email):
            notify(profile, viewer, "follow")
        return follow_response(viewer, profile, True)

    @social_routes.route("/unfollow/<viewer_identifier>/<profile_identifier>", methods=["POST"])
    @deps["login_required"]
    def unfollow_route(viewer_identifier, profile_identifier):
        deps["validate_csrf_token"]()
        viewer = require_route_owner(viewer_identifier)
        profile = deps["find_user_by_identifier"](profile_identifier)
        if viewer is None or profile is None:
            return "User not found", 404
        viewer_email, profile_email = viewer.email, profile.email
        deps["unfollow_user"](viewer_email, profile_email)
        return follow_response(viewer, profile, False)

    @social_routes.route("/send_friend_request/<viewer_identifier>/<profile_identifier>", methods=["POST"])
    @deps["login_required"]
    def send_friend_request_route(viewer_identifier, profile_identifier):
        deps["validate_csrf_token"]()
        viewer = require_route_owner(viewer_identifier)
        profile = deps["find_user_by_identifier"](profile_identifier)
        if viewer is None or profile is None:
            return "User not found", 404
        viewer_email, profile_email = viewer.email, profile.email
        if viewer_email == profile_email:
            return redirect(f"/profile/{profile.id}?viewer={viewer.id}")
        if blocked(viewer_email, profile_email):
            deps["log_security_event"]("friend_request_blocked", viewer_email, f"Blocked friend request attempt to {profile_email}")
            return blocked_action_page(viewer, "request_blocked")
        if deps["send_friend_request"](viewer_email, profile_email):
            notify(profile, viewer, "friend_request")
        return redirect(f"/profile/{profile.id}?viewer={viewer.id}")

    @social_routes.route("/accept_friend_request/<viewer_identifier>/<profile_identifier>", methods=["POST"])
    @deps["login_required"]
    def accept_friend_request_route(viewer_identifier, profile_identifier):
        deps["validate_csrf_token"]()
        viewer = require_route_owner(viewer_identifier)
        profile = deps["find_user_by_identifier"](profile_identifier)
        if viewer is None or profile is None:
            return "User not found", 404
        viewer_email, profile_email = viewer.email, profile.email
        if blocked(viewer_email, profile_email):
            deps["log_security_event"]("friend_accept_blocked", viewer_email, f"Blocked friend accept with {profile_email}")
            return blocked_action_page(viewer, "accept_blocked")
        accepted = deps["accept_friend_request"](viewer_email, profile_email)
        if accepted:
            deps["update_friend_request_notification_status"](viewer_email, profile_email, "accepted")
            notify(profile, viewer, "friend_request_accepted")
        else:
            return missing_friend_request_response(f"/friend_requests/{viewer.id}")
        return friend_request_response(
            viewer, profile, "accepted", f"/profile/{profile.id}?viewer={viewer.id}"
        )

    @social_routes.route("/decline_friend_request/<viewer_identifier>/<profile_identifier>", methods=["POST"])
    @deps["login_required"]
    def decline_friend_request_route(viewer_identifier, profile_identifier):
        deps["validate_csrf_token"]()
        viewer = require_route_owner(viewer_identifier)
        profile = deps["find_user_by_identifier"](profile_identifier)
        if viewer is None or profile is None:
            return "User not found", 404
        viewer_email, profile_email = viewer.email, profile.email
        if blocked(viewer_email, profile_email):
            deps["log_security_event"]("friend_decline_blocked", viewer_email, f"Blocked friend decline with {profile_email}")
            return blocked_action_page(viewer, "decline_blocked")
        declined = deps["decline_friend_request"](viewer_email, profile_email)
        if not declined:
            return missing_friend_request_response(f"/friend_requests/{viewer.id}")
        deps["update_friend_request_notification_status"](viewer_email, profile_email, "declined")
        notify(profile, viewer, "friend_request_declined")
        return friend_request_response(
            viewer, profile, "declined", f"/friend_requests/{viewer.id}"
        )

    @social_routes.route("/friends/<owner_identifier>")
    @deps["login_required"]
    def friends_page(owner_identifier):
        return people_page("friends", owner_identifier, deps["get_friends"])

    @social_routes.route("/followers/<owner_identifier>")
    @deps["login_required"]
    def followers_page(owner_identifier):
        return people_page("followers", owner_identifier, deps["get_followers"])

    @social_routes.route("/following/<owner_identifier>")
    @deps["login_required"]
    def following_page(owner_identifier):
        return people_page("following", owner_identifier, deps["get_following"])

    @social_routes.route("/friend_requests/<owner_identifier>")
    @deps["login_required"]
    def friend_requests_page(owner_identifier):
        user = require_route_owner(owner_identifier)
        if user is None:
            return "User not found", 404
        email = user.email
        ui, copy = localized_copy(user)
        requests = []
        seen = set()
        raw_requests = deps["get_friend_requests"](email)
        for item in raw_requests if isinstance(raw_requests, list) else []:
            if not isinstance(item, dict):
                continue
            sender_email = deps["normalize_email"](item.get("from"))
            if not sender_email or sender_email in seen:
                continue
            sender = deps["find_user_by_email"](sender_email)
            if sender is None:
                continue
            seen.add(sender_email)
            requests.append({"id": sender.id, "email": sender.email, "name": sender.name, "avatar_url": deps["get_avatar_url"](sender.email)})
        return render_template(
            "social_list.html", ui=ui, copy=copy, email=user.email,
            owner=user, title=copy["requests"], people=None, requests=requests,
            csrf_token_input=deps["csrf_input"](),
        )

    return social_routes
