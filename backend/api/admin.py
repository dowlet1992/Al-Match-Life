from flask import Blueprint, jsonify, request


def create_admin_api(deps):
    admin_api = Blueprint("admin_api", __name__)

    def api_error(message, status_code=400):
        response = jsonify({
            "ok": False,
            "error": deps["clean_text"](message),
        })
        response.status_code = status_code
        return response

    def current_admin_or_error():
        user = deps["get_api_current_user"]()
        if user is None:
            return None, api_error("Authentication required", 401)
        if not deps["is_admin_email"](user.email):
            return None, api_error("Admin access required", 403)
        return user, None

    @admin_api.route("/api/admin/moderation/reports")
    def api_admin_reports():
        user, error = current_admin_or_error()
        if error:
            return error

        status = deps["clean_text"](request.args.get("status", ""))
        target_email = deps["normalize_email"](request.args.get("target_email", ""))
        reporter_email = deps["normalize_email"](request.args.get("reporter_email", ""))
        reports_data = deps["load_reports"]()
        reports = deps["moderation_service"].list_reports(
            reports_data,
            status=status,
            target_email=target_email,
            reporter_email=reporter_email,
        )

        deps["log_security_event"]("admin_reports_viewed", user.email, f"status={status or 'all'}")
        return jsonify({
            "ok": True,
            "summary": deps["moderation_service"].summarize_reports(reports_data),
            "reports": reports,
        })

    @admin_api.route("/api/admin/moderation/reports/<report_id>", methods=["PATCH", "POST"])
    def api_admin_update_report(report_id):
        user, error = current_admin_or_error()
        if error:
            return error

        data = request.get_json(silent=True) or {}
        status = deps["clean_text"](data.get("status", "reviewing"))
        note = deps["clean_text"](data.get("note", data.get("moderation_note", "")))
        action = deps["clean_text"](data.get("action", ""))
        reports_data = deps["load_reports"]()

        try:
            report = deps["moderation_service"].update_report_status(
                reports_data,
                report_id,
                status,
                moderator_email=user.email,
                note=note,
                action=action or status,
            )
        except ValueError as error:
            return api_error(str(error), 400)
        except LookupError as error:
            return api_error(str(error), 404)

        deps["save_reports"](reports_data)
        deps["log_security_event"](
            "admin_report_status_updated",
            user.email,
            f"report={report_id}; status={status}; action={action or status}",
        )

        return jsonify({
            "ok": True,
            "report": report,
            "summary": deps["moderation_service"].summarize_reports(reports_data),
        })

    return admin_api
