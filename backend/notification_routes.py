from flask import Blueprint


def create_notification_routes(deps):
    notification_routes = Blueprint("notification_routes", __name__)

    @notification_routes.route("/notifications/<email>")
    @deps["login_required"]
    def notifications_page(email):
        user = deps["find_user_by_email"](email)

        if user is None:
            return "User not found", 404

        notifications = deps["get_notifications"](email)
        cards = ""

        for item in notifications:
            if isinstance(item, dict):
                text = deps["safe_text"](item.get("text", ""))
                created_at = deps["safe_text"](item.get("time_label") or item.get("created_at") or "")
                from_email = deps["normalize_email"](item.get("from_email") or item.get("from") or "")
                notification_type = item.get("type", "social")
            else:
                text = deps["safe_text"](item)
                created_at = ""
                from_email = ""
                notification_type = "social"

            if not text and not from_email:
                continue

            sender = deps["find_user_by_email"](from_email) if from_email else None

            icon = "🔔"
            if notification_type == "friend_request":
                icon = "👥"
            elif notification_type == "new_follower":
                icon = "➕"
            elif notification_type == "friend_request_accepted":
                icon = "✅"
            elif notification_type == "friend_request_declined":
                icon = "🚫"
            elif notification_type == "comment":
                icon = "💬"

            if sender is not None:
                sender_avatar = deps["get_avatar_url"](sender.email)
                sender_name = deps["safe_text"](sender.name)

                request_status = item.get("status", "pending") if isinstance(item, dict) else "pending"

                action_buttons = f"""
                    <a href="/profile/{sender.email}?viewer={email}" class="mini-btn profile">Профиль</a>
                """

                if notification_type == "friend_request":
                    if request_status == "accepted":
                        action_buttons += """
                        <span class="mini-status accepted">✅ Принято</span>
                        """
                    elif request_status == "declined":
                        action_buttons += """
                        <span class="mini-status declined">🚫 Отклонено</span>
                        """
                    else:
                        action_buttons += f"""
                        <form method="POST" action="/accept_friend_request/{email}/{sender.email}">{deps["csrf_input"]()}<button type="submit" class="mini-btn accept">Принять</button></form>
                        <form method="POST" action="/decline_friend_request/{email}/{sender.email}">{deps["csrf_input"]()}<button type="submit" class="mini-btn decline">Отклонить</button></form>
                        """

                cards += f"""
                <div class="notification-card">
                    <a href="/profile/{sender.email}?viewer={email}" class="avatar-link" title="Открыть профиль">
                        <img src="{sender_avatar}" class="notification-avatar">
                    </a>

                    <div class="notification-body">
                        <div class="notification-text"><span class="notification-icon">{icon}</span> {text}</div>
                        <div class="notification-meta">{created_at} · {sender_name}</div>
                    </div>

                    <div class="notification-actions">
                        {action_buttons}
                    </div>
                </div>
                """
            else:
                cards += f"""
                <div class="notification-card">
                    <div class="notification-avatar notification-icon-avatar">{icon}</div>
                    <div class="notification-body">
                        <div class="notification-text">{text}</div>
                        <div class="notification-meta">{created_at}</div>
                    </div>
                    <div class="notification-actions"></div>
                </div>
                """

        if cards == "":
            cards = """
            <div class="empty-card">
                <div style="font-size:42px;margin-bottom:12px;">🔕</div>
                <h2>Уведомлений пока нет</h2>
                <p>Когда кто-то подпишется, отправит заявку, примет дружбу или прокомментирует — всё появится здесь.</p>
            </div>
            """

        return f"""
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Уведомления</title>
            <style>
                body{{
                    margin:0;
                    background:#0f172a;
                    color:white;
                    font-family:Arial,sans-serif;
                }}
                .page{{
                    max-width:960px;
                    margin:auto;
                    padding:34px 22px;
                }}
                .back{{
                    display:inline-flex;
                    color:white;
                    text-decoration:none;
                    font-weight:800;
                    margin-bottom:22px;
                    background:#1e293b;
                    border:1px solid rgba(148,163,184,0.16);
                    padding:11px 14px;
                    border-radius:14px;
                }}
                .header{{
                    display:flex;
                    align-items:center;
                    gap:12px;
                    margin-bottom:24px;
                }}
                .header h1{{
                    margin:0;
                    font-size:34px;
                    letter-spacing:-0.5px;
                }}
                .notification-card{{
                    display:grid;
                    grid-template-columns:56px minmax(0,1fr) auto;
                    align-items:center;
                    gap:14px;
                    background:#1e293b;
                    border:1px solid rgba(148,163,184,0.14);
                    border-radius:22px;
                    padding:14px 16px;
                    margin-bottom:12px;
                    color:white;
                    box-shadow:0 14px 34px rgba(0,0,0,0.18);
                }}
                .avatar-link{{
                    display:block;
                    width:56px;
                    height:56px;
                    border-radius:50%;
                }}
                .notification-avatar{{
                    width:56px;
                    height:56px;
                    border-radius:50%;
                    object-fit:cover;
                    background:#334155;
                    border:2px solid rgba(96,165,250,0.34);
                    box-sizing:border-box;
                    display:block;
                }}
                .notification-icon-avatar{{
                    display:flex;
                    align-items:center;
                    justify-content:center;
                    font-size:22px;
                }}
                .notification-body{{min-width:0;}}
                .notification-text{{
                    font-size:16px;
                    line-height:1.35;
                    font-weight:850;
                    color:#f8fafc;
                }}
                .notification-icon{{margin-right:4px;}}
                .notification-meta{{
                    margin-top:6px;
                    color:#94a3b8;
                    font-size:13px;
                    font-weight:700;
                }}
                .notification-actions{{
                    display:flex;
                    gap:8px;
                    align-items:center;
                    justify-content:flex-end;
                    flex-wrap:wrap;
                }}
                .mini-btn{{
                    text-decoration:none;
                    color:white;
                    padding:9px 12px;
                    border-radius:12px;
                    font-size:13px;
                    font-weight:900;
                    white-space:nowrap;
                    transition:0.14s ease;
                }}
                .mini-btn:hover{{
                    transform:translateY(-1px);
                    filter:brightness(1.08);
                }}
                .mini-btn.profile{{background:#2563eb;}}
                .mini-btn.accept{{background:#16a34a;}}
                .mini-btn.decline{{background:#dc2626;}}
                .mini-status{{
                    display:inline-flex;
                    align-items:center;
                    justify-content:center;
                    padding:9px 12px;
                    border-radius:12px;
                    font-size:13px;
                    font-weight:900;
                    white-space:nowrap;
                }}
                .mini-status.accepted{{
                    background:rgba(22,163,74,0.16);
                    color:#86efac;
                    border:1px solid rgba(34,197,94,0.28);
                }}
                .mini-status.declined{{
                    background:rgba(220,38,38,0.14);
                    color:#fca5a5;
                    border:1px solid rgba(248,113,113,0.28);
                }}
                .empty-card{{
                    text-align:center;
                    background:#1e293b;
                    border:1px solid rgba(148,163,184,0.12);
                    border-radius:26px;
                    padding:34px;
                    color:#cbd5e1;
                }}
                .empty-card h2{{
                    margin:0 0 8px 0;
                    color:white;
                }}
                .empty-card p{{
                    margin:0;
                    line-height:1.5;
                }}
                @media(max-width:680px){{
                    .page{{padding:22px 14px;}}
                    .header h1{{font-size:28px;}}
                    .notification-card{{
                        grid-template-columns:48px minmax(0,1fr);
                        align-items:flex-start;
                        padding:14px;
                    }}
                    .avatar-link,.notification-avatar{{width:48px;height:48px;}}
                    .notification-actions{{
                        grid-column:2;
                        justify-content:flex-start;
                        margin-top:8px;
                    }}
                }}
            </style>
        </head>

        <body>
            <div class="page">
                <a href="/dashboard/{email}" class="back">← Назад</a>
                <div class="header">
                    <div style="font-size:34px;">🔔</div>
                    <h1>Уведомления</h1>
                </div>
                {cards}
            </div>
        </body>
        </html>
        """

    return notification_routes
