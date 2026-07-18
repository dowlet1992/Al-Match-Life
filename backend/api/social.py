from flask import Blueprint, jsonify


def create_social_api(deps):
    social_api = Blueprint("social_api", __name__)

    def api_error(message, status_code=400):
        response = jsonify({
            "ok": False,
            "error": deps["clean_text"](message),
        })
        response.status_code = status_code
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
