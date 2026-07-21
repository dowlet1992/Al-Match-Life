from flask import Blueprint, jsonify, request


def create_device_push_api(deps):
    api = Blueprint("device_push_api", __name__)

    def current_user():
        user = deps["get_api_current_user"]()
        if user is None:
            return None, (jsonify({"ok": False, "error": "Authentication required"}), 401)
        return user, None

    @api.route("/api/push/config", methods=["GET"])
    def push_config():
        user, auth_error = current_user()
        if auth_error:
            return auth_error
        public_key = deps["web_push_public_key"]()
        response = jsonify({"ok": True, "web_push": {"configured": bool(public_key), "public_key": public_key}})
        response.headers["Cache-Control"] = "private, no-store"
        return response

    @api.route("/api/push/devices", methods=["GET", "POST"])
    def devices():
        user, auth_error = current_user()
        if auth_error:
            return auth_error
        repository = deps["get_device_push_repository"]()
        if request.method == "GET":
            devices = [deps["device_push_service"].public_device(item) for item in repository.list_for_user(user.email)]
            return jsonify({"ok": True, "devices": devices})
        deps["validate_write_request"]()
        registration, error = deps["device_push_service"].normalize_registration(
            request.get_json(silent=True), deps["clean_text"],
        )
        if error:
            return jsonify({"ok": False, "error": error}), 400
        device = repository.upsert(user.email, registration)
        return jsonify({"ok": True, "device": deps["device_push_service"].public_device(device)}), 201

    @api.route("/api/push/devices/<device_id>", methods=["DELETE"])
    def revoke_device(device_id):
        user, auth_error = current_user()
        if auth_error:
            return auth_error
        deps["validate_write_request"]()
        if not deps["device_push_service"].DEVICE_ID_PATTERN.fullmatch(str(device_id)):
            return jsonify({"ok": False, "error": "Invalid device identifier"}), 400
        removed = deps["get_device_push_repository"]().revoke(user.email, device_id)
        return jsonify({"ok": True, "revoked": removed})

    return api
