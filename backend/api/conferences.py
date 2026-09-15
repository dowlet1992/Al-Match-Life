import os
import secrets
import time

from flask import Blueprint, jsonify, render_template, request

from backend.services import conference_service


def create_conferences_api(deps):
    api = Blueprint("conferences_api", __name__)

    def fail(code, status=400):
        response = jsonify({"ok": False, "error": code})
        response.status_code = status
        response.headers["Cache-Control"] = "private, no-store"
        return response

    def current_user():
        user = deps["get_api_current_user"]()
        return (user, None) if user is not None else (None, fail("authentication_required", 401))

    def conference_context(room_id, user):
        if not room_id.startswith("novix_") or len(room_id) > 80:
            return None, [], fail("conference_not_found", 404)
        room = deps["get_call_signal_room"](room_id)
        participants = conference_service.room_participants(room, deps["normalize_email"])
        if deps["normalize_email"](user.email) not in participants:
            return None, [], fail("conference_not_found", 404)
        return room, participants, None

    @api.route("/conference/<room_id>", methods=["GET"])
    def conference_page(room_id):
        user, error = current_user()
        if error:
            return error
        room, participants, error = conference_context(room_id, user)
        if error:
            return error
        participant_users = [deps["find_user_by_email"](email) for email in participants]
        participant_users = [item for item in participant_users if item is not None]
        eligible = []
        for candidate in deps["get_users"]():
            email = deps["normalize_email"](candidate.email)
            if email in participants:
                continue
            if (deps["is_blocked"](user.email, email) or deps["is_blocked"](email, user.email)
                    or deps["is_restricted"](user.email, email) or deps["is_restricted"](email, user.email)):
                continue
            eligible.append({"email": email, "name": candidate.name, "avatar": deps["get_avatar_url"](email)})
        ui = deps["translation_bundle"](deps["get_current_language"](user))
        return render_template(
            "conference.html", ui=ui, user=user, room_id=room_id,
            call_type=conference_service.room_call_type(room), csrf_token=deps["get_csrf_token"](),
            owner=conference_service.room_owner(room, deps["normalize_email"]),
            participants=[{"email": item.email, "name": item.name, "avatar": deps["get_avatar_url"](item.email)} for item in participant_users],
            eligible=eligible, max_participants=conference_service.MAX_PARTICIPANTS,
        )

    @api.route("/api/conferences", methods=["POST"])
    def create_conference():
        user, error = current_user()
        if error:
            return error
        deps["validate_write_request"]()
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return fail("invalid_conference_request")
        call_type = deps["clean_text"](data.get("call_type", "video"))
        requested = data.get("participants", [])
        if call_type not in {"audio", "video"} or not isinstance(requested, list):
            return fail("invalid_conference_request")
        if not 1 <= len(requested) <= conference_service.MAX_PARTICIPANTS - 1:
            return fail("conference_participant_limit")
        participants = conference_service.normalize_participants(user.email, requested, deps["normalize_email"])
        if len(participants) != len({deps["normalize_email"](item) for item in requested if deps["normalize_email"](item)}) + 1:
            return fail("invalid_conference_participants")
        participant_users = []
        for email in participants:
            participant = deps["find_user_by_email"](email)
            if participant is None:
                return fail("user_not_found", 404)
            if email != deps["normalize_email"](user.email) and (
                deps["is_blocked"](user.email, email) or deps["is_blocked"](email, user.email)
                or deps["is_restricted"](user.email, email) or deps["is_restricted"](email, user.email)
            ):
                return fail("conference_unavailable", 403)
            participant_users.append(participant)

        room_id = conference_service.new_room_id()
        now = time.time()
        for participant in participant_users:
            if deps["normalize_email"](participant.email) == deps["normalize_email"](user.email):
                continue
            signal = {
                "id": secrets.token_urlsafe(12), "type": "conference_invite",
                "from": deps["normalize_email"](user.email), "to": deps["normalize_email"](participant.email),
                "payload": {"call_type": call_type, "owner": deps["normalize_email"](user.email)},
                "created_at": now,
            }
            stored = deps["append_call_signal"](
                room_id, signal, status="ringing", updated_at=str(now), close=False, enforce_transition=False,
            )
            if not isinstance(stored, dict):
                return fail("conference_not_created", 409)
        deps["log_security_event"]("conference_created", user.email, f"room={room_id};participants={len(participants)};type={call_type}")
        return jsonify({
            "ok": True, "room_id": room_id, "call_type": call_type,
            "participants": [deps["public_user"](item) for item in participant_users],
            "join_url": f"/conference/{room_id}",
        }), 201

    @api.route("/api/conferences/eligible", methods=["GET"])
    def eligible_conference_participants():
        user, error = current_user()
        if error:
            return error
        excluded = {
            deps["normalize_email"](item)
            for item in request.args.getlist("exclude")
            if deps["normalize_email"](item)
        }
        excluded.add(deps["normalize_email"](user.email))
        people = []
        for candidate in deps["get_users"]():
            email = deps["normalize_email"](candidate.email)
            if email in excluded:
                continue
            if (deps["is_blocked"](user.email, email) or deps["is_blocked"](email, user.email)
                    or deps["is_restricted"](user.email, email) or deps["is_restricted"](email, user.email)):
                continue
            people.append({"email": email, "name": candidate.name, "avatar": deps["get_avatar_url"](email)})
        people.sort(key=lambda item: (str(item["name"]).casefold(), item["email"]))
        response = jsonify({"ok": True, "people": people[:100]})
        response.headers["Cache-Control"] = "private, no-store"
        return response

    @api.route("/api/conferences/invitations", methods=["GET"])
    def conference_invitations():
        user, error = current_user()
        if error:
            return error
        email = deps["normalize_email"](user.email)
        now = time.time()
        invitations = []
        for room_id, room in deps["load_call_signals"]().items():
            if not str(room_id).startswith("novix_") or not isinstance(room, dict):
                continue
            if room.get("status") in {"ended", "declined", "missed"}:
                continue
            for signal in reversed(room.get("messages", []) if isinstance(room.get("messages"), list) else []):
                if not isinstance(signal, dict) or signal.get("type") != "conference_invite":
                    continue
                if deps["normalize_email"](signal.get("to")) != email:
                    continue
                try:
                    created_at = float(signal.get("created_at", 0) or 0)
                except (TypeError, ValueError):
                    created_at = 0
                if created_at < now - 120:
                    break
                caller = deps["find_user_by_email"](signal.get("from"))
                if caller is not None:
                    invitations.append({
                        "room_id": room_id, "join_url": f"/conference/{room_id}",
                        "call_type": conference_service.room_call_type(room),
                        "caller_name": caller.name, "caller_avatar": deps["get_avatar_url"](caller.email),
                        "created_at": created_at,
                    })
                break
        response = jsonify({"ok": True, "invitations": sorted(invitations, key=lambda item: item["created_at"], reverse=True)[:3]})
        response.headers["Cache-Control"] = "private, no-store"
        return response

    @api.route("/api/conferences/<room_id>/token", methods=["POST"])
    def conference_token(room_id):
        user, error = current_user()
        if error:
            return error
        deps["validate_write_request"]()
        room, participants, error = conference_context(room_id, user)
        if error:
            return error
        api_key = os.environ.get("LIVEKIT_API_KEY", "")
        api_secret = os.environ.get("LIVEKIT_API_SECRET", "")
        token = conference_service.issue_access_token(
            api_key, api_secret, room_id, getattr(user, "uuid", "") or deps["stable_user_id"](user), user.name,
            {"avatar": deps["get_avatar_url"](user.email)},
        )
        if not token:
            return fail("conference_provider_unavailable", 503)
        response = jsonify({"ok": True, "url": os.environ.get("LIVEKIT_URL", "ws://127.0.0.1:7880"), "token": token})
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["Pragma"] = "no-cache"
        return response

    @api.route("/api/conferences/<room_id>/participants", methods=["POST"])
    def add_conference_participant(room_id):
        user, error = current_user()
        if error:
            return error
        deps["validate_write_request"]()
        room, participants, error = conference_context(room_id, user)
        if error:
            return error
        if conference_service.room_owner(room, deps["normalize_email"]) != deps["normalize_email"](user.email):
            return fail("conference_invite_forbidden", 403)
        if len(participants) >= conference_service.MAX_PARTICIPANTS:
            return fail("conference_participant_limit", 409)
        data = request.get_json(silent=True)
        email = deps["normalize_email"](data.get("email", "") if isinstance(data, dict) else "")
        participant = deps["find_user_by_email"](email)
        if participant is None or email in participants:
            return fail("invalid_conference_participant", 400)
        if (deps["is_blocked"](user.email, email) or deps["is_blocked"](email, user.email)
                or deps["is_restricted"](user.email, email) or deps["is_restricted"](email, user.email)):
            return fail("conference_unavailable", 403)
        signal = {
            "id": secrets.token_urlsafe(12), "type": "conference_invite",
            "from": deps["normalize_email"](user.email), "to": email,
            "payload": {"call_type": conference_service.room_call_type(room), "owner": deps["normalize_email"](user.email)},
            "created_at": time.time(),
        }
        stored = deps["append_call_signal"](room_id, signal, status="active", updated_at=str(time.time()), close=False, enforce_transition=False)
        if not isinstance(stored, dict):
            return fail("conference_invite_failed", 409)
        deps["log_security_event"]("conference_participant_invited", user.email, f"room={room_id};participant={email}")
        return jsonify({"ok": True, "participant": {"email": email, "name": participant.name, "avatar": deps["get_avatar_url"](email)}}), 201

    return api
