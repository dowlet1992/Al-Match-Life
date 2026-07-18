from datetime import datetime

from flask import Blueprint


def create_realtime_routes(deps):
    realtime_routes = Blueprint("realtime_routes", __name__)

    @realtime_routes.route("/typing/<sender_email>/<receiver_email>", methods=["POST"])
    @deps["login_required"]
    def typing_status(sender_email, receiver_email):
        deps["validate_csrf_token"]()
        data = deps["load_typing_status"]()
        data[f"{sender_email}->{receiver_email}"] = datetime.now().timestamp()
        deps["save_typing_status"](data)
        return "OK"

    @realtime_routes.route("/presence/<email>", methods=["POST"])
    @deps["login_required"]
    def presence_status(email):
        deps["validate_csrf_token"]()
        data = deps["load_presence_status"]()
        data[email] = datetime.now().timestamp()
        deps["save_presence_status"](data)
        return "OK"

    return realtime_routes
