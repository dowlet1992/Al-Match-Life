import base64
import re

from flask import Blueprint, jsonify, request

from backend.services import profile_access_service


def create_social_api(deps):
    social_api = Blueprint("social_api", __name__)

    def api_error(message, status_code=400):
        response = jsonify({
            "ok": False,
            "error": deps["clean_text"](message),
        })
        response.status_code = status_code
        return response

    def private_json(payload):
        response = jsonify(payload)
        response.headers["Cache-Control"] = "private, no-store"
        return response

    def current_user_or_error():
        user = deps["get_api_current_user"]()
        if user is None:
            return None, api_error("Authentication required", 401)
        return user, None

    def target_user_or_error(target_email):
        target_user = deps["find_user_by_email"](target_email)
        if target_user is None:
            return None, api_error("User not found", 404)
        return target_user, None

    def decode_cursor(value):
        value = deps["clean_text"](value)
        if not value:
            return "", None
        if len(value) > 512 or re.fullmatch(r"[A-Za-z0-9_-]+", value) is None:
            return None, api_error("Invalid cursor", 400)
        try:
            padding = "=" * (-len(value) % 4)
            decoded = base64.urlsafe_b64decode((value + padding).encode("ascii")).decode("utf-8")
        except (UnicodeError, ValueError):
            return None, api_error("Invalid cursor", 400)
        normalized = deps["normalize_email"](decoded)
        if not normalized or decoded != normalized:
            return None, api_error("Invalid cursor", 400)
        return normalized, None

    def encode_cursor(email):
        return base64.urlsafe_b64encode(email.encode("utf-8")).decode("ascii").rstrip("=")

    def requested_limit():
        raw_limit = request.args.get("limit", "20")
        try:
            limit = int(raw_limit)
        except (TypeError, ValueError):
            return None, api_error("Invalid limit", 400)
        if limit < 1 or limit > 50:
            return None, api_error("Limit must be between 1 and 50", 400)
        return limit, None

    def social_list_response(target_email, kind):
        current_user, error = current_user_or_error()
        if error:
            return error
        target_user, error = target_user_or_error(target_email)
        if error:
            return error

        access = profile_access_service.profile_view_status(
            current_user.email,
            target_user.email,
            deps["normalize_user_ai_settings"](target_user.email),
            deps["is_blocked"],
            deps["are_friends"],
        )
        if access["status"] == "deactivated":
            return api_error("User not found", 404)
        if access["status"] != "allowed":
            return api_error("Social list is not available for this profile", 403)

        limit, error = requested_limit()
        if error:
            return error
        after, error = decode_cursor(request.args.get("cursor", ""))
        if error:
            return error

        social_data = deps["load_social"]()
        source = deps["get_followers"](target_user.email) if kind == "followers" else deps["get_following"](target_user.email)
        visible = []
        for email in sorted(set(deps["normalize_email"](item) for item in source)):
            if not email or (after and email <= after):
                continue
            item_user = deps["find_user_by_email"](email)
            if item_user is None or deps["social_service"].blocked_between(current_user.email, email, deps["is_blocked"]):
                continue
            item_settings = deps["normalize_user_ai_settings"](email)
            if item_settings.get("account_deactivated") is True:
                continue
            visible.append(item_user)
            if len(visible) > limit:
                break

        has_more = len(visible) > limit
        page_users = visible[:limit]
        items = [{
            "user": deps["api_user_payload"](item_user),
            "relationship": deps["social_service"].relationship_snapshot(current_user, item_user, social_data),
        } for item_user in page_users]
        next_cursor = encode_cursor(page_users[-1].email) if has_more and page_users else None
        return private_json({
            "ok": True,
            "kind": kind,
            "profile": deps["api_user_payload"](target_user),
            "items": items,
            "next_cursor": next_cursor,
        })

    @social_api.route("/api/users/<path:target_email>/followers")
    def api_followers(target_email):
        return social_list_response(target_email, "followers")

    @social_api.route("/api/users/<path:target_email>/following")
    def api_following(target_email):
        return social_list_response(target_email, "following")

    @social_api.route("/api/users/<path:target_email>/relationship")
    def api_relationship(target_email):
        current_user, error = current_user_or_error()
        if error:
            return error

        target_user, error = target_user_or_error(target_email)
        if error:
            return error

        if deps["social_service"].blocked_between(current_user.email, target_user.email, deps["is_blocked"]):
            return api_error("Social relationship is not available for these users", 403)

        return private_json({
            "ok": True,
            "relationship": deps["social_service"].relationship_snapshot(current_user, target_user),
        })

    @social_api.route("/api/users/<path:target_email>/follow", methods=["POST"])
    def api_follow_user(target_email):
        current_user, error = current_user_or_error()
        if error:
            return error

        target_user, error = target_user_or_error(target_email)
        if error:
            return error

        result = deps["social_service"].follow(current_user, target_user, deps["is_blocked"])
        if not result.get("ok"):
            return api_error(result.get("error", "Social action failed"), result.get("status", 400))

        if result.get("changed"):
            deps["create_social_notification"](
                target_user.email,
                f"{current_user.name} подписался на вас.",
                "follow",
                current_user.email,
            )

        return jsonify(result)

    @social_api.route("/api/users/<path:target_email>/follow", methods=["DELETE"])
    def api_unfollow_user(target_email):
        current_user, error = current_user_or_error()
        if error:
            return error

        target_user, error = target_user_or_error(target_email)
        if error:
            return error

        return jsonify(deps["social_service"].unfollow(current_user, target_user))

    @social_api.route("/api/users/<path:target_email>/friend-request", methods=["POST"])
    def api_send_friend_request(target_email):
        current_user, error = current_user_or_error()
        if error:
            return error

        target_user, error = target_user_or_error(target_email)
        if error:
            return error

        result = deps["social_service"].request_friend(current_user, target_user, deps["is_blocked"])
        if not result.get("ok"):
            return api_error(result.get("error", "Social action failed"), result.get("status", 400))

        if result.get("changed"):
            deps["create_social_notification"](
                target_user.email,
                f"{current_user.name} отправил вам заявку в друзья.",
                "friend_request",
                current_user.email,
            )

        return jsonify(result)

    @social_api.route("/api/users/<path:target_email>/friend-request/accept", methods=["POST"])
    def api_accept_friend_request(target_email):
        current_user, error = current_user_or_error()
        if error:
            return error

        target_user, error = target_user_or_error(target_email)
        if error:
            return error

        result = deps["social_service"].accept_request(current_user, target_user, deps["is_blocked"])
        if not result.get("ok"):
            return api_error(result.get("error", "Social action failed"), result.get("status", 400))

        if result.get("changed"):
            deps["update_friend_request_notification_status"](current_user.email, target_user.email, "accepted")
            deps["create_social_notification"](
                target_user.email,
                f"{current_user.name} принял вашу заявку в друзья.",
                "friend_request_accepted",
                current_user.email,
            )

        return jsonify(result)

    @social_api.route("/api/users/<path:target_email>/friend-request/decline", methods=["POST"])
    def api_decline_friend_request(target_email):
        current_user, error = current_user_or_error()
        if error:
            return error

        target_user, error = target_user_or_error(target_email)
        if error:
            return error

        result = deps["social_service"].decline_request(current_user, target_user)
        if result.get("changed"):
            deps["update_friend_request_notification_status"](current_user.email, target_user.email, "declined")
            deps["create_social_notification"](
                target_user.email,
                f"{current_user.name} отклонил вашу заявку в друзья.",
                "friend_request_declined",
                current_user.email,
            )

        return jsonify(result)

    return social_api
