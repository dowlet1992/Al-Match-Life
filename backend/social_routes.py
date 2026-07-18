from flask import Blueprint, redirect


def create_social_routes(deps):
    social_routes = Blueprint("social_routes", __name__)

    def social_list_page(title, email, list_emails):
        profile_user = deps["find_user_by_email"](email)

        if profile_user is None:
            return "User not found"

        cards_html = ""

        for item_email in list_emails:
            item_user = deps["find_user_by_email"](item_email)

            if item_user is None:
                continue

            avatar_url = deps["get_avatar_url"](item_user.email)

            cards_html += f"""
            <div style="background:#1e293b;padding:18px;border-radius:22px;margin-bottom:14px;display:flex;align-items:center;gap:16px;">
                <img src="{avatar_url}" style="width:66px;height:66px;border-radius:50%;object-fit:cover;background:#334155;border:3px solid #334155;">

                <div style="flex:1;">
                    <h3 style="margin:0 0 6px 0;font-size:20px;">{item_user.name}</h3>
                    <p style="margin:0 0 6px 0;color:#cbd5e1;">{deps["safe_text"](item_user.profession)}</p>
                    <p style="margin:0;color:#22c55e;font-weight:bold;">Trust Score: {item_user.trust_score}</p>
                </div>

                <a href="/profile/{item_user.email}?viewer={email}" style="background:#2563eb;color:white;text-decoration:none;padding:12px 16px;border-radius:14px;font-weight:bold;">
                    Открыть профиль
                </a>
            </div>
            """

        if cards_html == "":
            cards_html = """
            <div style="background:#1e293b;padding:28px;border-radius:22px;color:#cbd5e1;text-align:center;">
                Пока список пуст.
            </div>
            """

        return f"""
        <!DOCTYPE html>
        <html lang="ru">
        <head>
            <meta charset="UTF-8">
            <title>{title} - AI Match Life</title>
        </head>

        <body style="margin:0;background:#0f172a;color:white;font-family:Arial,sans-serif;padding:32px;">
            <div style="max-width:920px;margin:auto;">

                <a href="/profile/{email}?viewer={email}" style="display:inline-block;color:white;text-decoration:none;background:#334155;padding:12px 16px;border-radius:14px;margin-bottom:18px;font-weight:bold;">
                    ← Назад
                </a>

                <div style="background:#1e293b;padding:28px;border-radius:26px;margin-bottom:22px;">
                    <h1 style="margin:0;">{title}</h1>
                </div>

                {cards_html}

            </div>
        </body>
        </html>
        """

    @social_routes.route("/follow/<viewer_email>/<profile_email>")
    @deps["login_required"]
    def follow_route(viewer_email, profile_email):
        viewer = deps["find_user_by_email"](viewer_email)
        profile = deps["find_user_by_email"](profile_email)

        if viewer is None or profile is None:
            return "User not found", 404

        if viewer_email == profile_email:
            return redirect(f"/profile/{profile_email}?viewer={viewer_email}")

        if deps["is_blocked"](viewer_email, profile_email) or deps["is_blocked"](profile_email, viewer_email):
            deps["log_security_event"]("follow_blocked", viewer_email, f"Blocked follow attempt to {profile_email}")
            return deps["simple_page"](
                "🚫 Действие недоступно",
                "Подписка невозможна, потому что один из пользователей заблокировал другого.",
                viewer_email,
            )

        if deps["follow_user"](viewer_email, profile_email):
            deps["create_social_notification"](
                profile_email,
                f"{viewer.name} подписался на вас.",
                "follow",
                viewer_email,
            )

        return redirect(f"/profile/{profile_email}?viewer={viewer_email}")

    @social_routes.route("/unfollow/<viewer_email>/<profile_email>")
    @deps["login_required"]
    def unfollow_route(viewer_email, profile_email):
        viewer = deps["find_user_by_email"](viewer_email)
        profile = deps["find_user_by_email"](profile_email)

        if viewer is None or profile is None:
            return "User not found", 404

        if deps["is_blocked"](viewer_email, profile_email) or deps["is_blocked"](profile_email, viewer_email):
            deps["log_security_event"]("unfollow_blocked", viewer_email, f"Blocked unfollow attempt to {profile_email}")
            return deps["simple_page"]("🚫 Действие недоступно", "Операция недоступна.", viewer_email)

        deps["unfollow_user"](viewer_email, profile_email)
        return redirect(f"/profile/{profile_email}?viewer={viewer_email}")

    @social_routes.route("/send_friend_request/<viewer_email>/<profile_email>")
    @deps["login_required"]
    def send_friend_request_route(viewer_email, profile_email):
        viewer = deps["find_user_by_email"](viewer_email)
        profile = deps["find_user_by_email"](profile_email)

        if viewer is None or profile is None:
            return "User not found", 404

        if viewer_email == profile_email:
            return redirect(f"/profile/{profile_email}?viewer={viewer_email}")

        if deps["is_blocked"](viewer_email, profile_email) or deps["is_blocked"](profile_email, viewer_email):
            deps["log_security_event"]("friend_request_blocked", viewer_email, f"Blocked friend request attempt to {profile_email}")
            return deps["simple_page"](
                "🚫 Действие недоступно",
                "Заявку в друзья нельзя отправить, потому что один из пользователей заблокировал другого.",
                viewer_email,
            )

        if deps["send_friend_request"](viewer_email, profile_email):
            deps["create_social_notification"](
                profile_email,
                f"{viewer.name} отправил вам заявку в друзья.",
                "friend_request",
                viewer_email,
            )

        return redirect(f"/profile/{profile_email}?viewer={viewer_email}")

    @social_routes.route("/accept_friend_request/<viewer_email>/<profile_email>")
    @deps["login_required"]
    def accept_friend_request_route(viewer_email, profile_email):
        viewer = deps["find_user_by_email"](viewer_email)
        profile = deps["find_user_by_email"](profile_email)

        if viewer is None or profile is None:
            return "User not found", 404

        if deps["is_blocked"](viewer_email, profile_email) or deps["is_blocked"](profile_email, viewer_email):
            deps["log_security_event"]("friend_accept_blocked", viewer_email, f"Blocked friend accept with {profile_email}")
            return deps["simple_page"](
                "🚫 Действие недоступно",
                "Подтверждение дружбы невозможно, потому что один из пользователей заблокировал другого.",
                viewer_email,
            )

        if deps["accept_friend_request"](viewer_email, profile_email):
            deps["update_friend_request_notification_status"](viewer_email, profile_email, "accepted")
            deps["create_social_notification"](
                profile_email,
                f"{viewer.name} принял вашу заявку в друзья.",
                "friend_request_accepted",
                viewer_email,
            )

        return redirect(f"/profile/{profile_email}?viewer={viewer_email}")

    @social_routes.route("/friends/<email>")
    @deps["login_required"]
    def friends_page(email):
        return social_list_page("Друзья", email, deps["get_friends"](email))

    @social_routes.route("/followers/<email>")
    @deps["login_required"]
    def followers_page(email):
        return social_list_page("Подписчики", email, deps["get_followers"](email))

    @social_routes.route("/following/<email>")
    @deps["login_required"]
    def following_page(email):
        return social_list_page("Подписки", email, deps["get_following"](email))

    @social_routes.route("/friend_requests/<email>")
    @deps["login_required"]
    def friend_requests_page(email):
        user = deps["find_user_by_email"](email)

        if user is None:
            return "User not found"

        requests = deps["get_friend_requests"](email)
        requests_html = ""

        for request_item in requests:
            sender_email = request_item.get("from")
            sender = deps["find_user_by_email"](sender_email)

            if sender is None:
                continue

            avatar_url = deps["get_avatar_url"](sender.email)

            requests_html += f"""
            <div style="background:#1e293b;padding:18px;border-radius:20px;margin-bottom:14px;display:flex;align-items:center;gap:16px;">
                <img src="{avatar_url}" style="width:64px;height:64px;border-radius:50%;object-fit:cover;background:#334155;">
                <div style="flex:1;">
                    <h3 style="margin:0 0 6px 0;">{sender.name}</h3>
                    <p style="margin:0;color:#cbd5e1;">хочет добавить вас в друзья</p>
                </div>

                <a href="/accept_friend_request/{email}/{sender.email}" style="background:#16a34a;color:white;text-decoration:none;padding:10px 14px;border-radius:12px;font-weight:bold;">
                    Принять
                </a>

                <a href="/decline_friend_request/{email}/{sender.email}" style="background:#dc2626;color:white;text-decoration:none;padding:10px 14px;border-radius:12px;font-weight:bold;">
                    Отклонить
                </a>
            </div>
            """

        if requests_html == "":
            requests_html = """
            <div style="background:#1e293b;padding:24px;border-radius:20px;color:#cbd5e1;">
                Заявок пока нет.
            </div>
            """

        return f"""
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Заявки в друзья</title>
        </head>
        <body style="margin:0;background:#0f172a;color:white;font-family:Arial;padding:32px;">
            <div style="max-width:900px;margin:auto;">
                <a href="/dashboard/{email}" style="display:inline-block;color:white;text-decoration:none;background:#334155;padding:12px 16px;border-radius:14px;margin-bottom:18px;">
                    ← Назад
                </a>

                <div style="background:#1e293b;padding:28px;border-radius:26px;margin-bottom:22px;">
                    <h1 style="margin:0;">👥 Заявки в друзья</h1>
                </div>

                {requests_html}
            </div>
        </body>
        </html>
        """

    @social_routes.route("/decline_friend_request/<viewer_email>/<profile_email>")
    @deps["login_required"]
    def decline_friend_request_route(viewer_email, profile_email):
        viewer = deps["find_user_by_email"](viewer_email)
        profile = deps["find_user_by_email"](profile_email)

        if viewer is None or profile is None:
            return "User not found", 404

        if deps["is_blocked"](viewer_email, profile_email) or deps["is_blocked"](profile_email, viewer_email):
            deps["log_security_event"]("friend_decline_blocked", viewer_email, f"Blocked friend decline with {profile_email}")
            return deps["simple_page"](
                "🚫 Действие недоступно",
                "Отклонение заявки недоступно, потому что один из пользователей заблокировал другого.",
                viewer_email,
            )

        deps["decline_friend_request"](viewer_email, profile_email)
        deps["update_friend_request_notification_status"](viewer_email, profile_email, "declined")
        deps["create_social_notification"](
            profile_email,
            f"{viewer.name} отклонил вашу заявку в друзья.",
            "friend_request_declined",
            viewer_email,
        )

        return redirect(f"/friend_requests/{viewer_email}")

    return social_routes
