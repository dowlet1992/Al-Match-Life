from flask import Blueprint, request

from backend.services import profile_access_service
from backend.services import profile_actions_service
from backend.services import profile_posts_service
from backend.services import profile_render_service


def create_profile_routes(deps):
    profile_routes = Blueprint("profile_routes", __name__)

    @profile_routes.route("/profile/<email>")
    @deps["profile_view_required"]
    def profile(email):
        user = deps["find_user_by_email"](email)

        if user is None:
            return "User not found"

        viewer_email = request.args.get("viewer", email)
        viewer = deps["find_user_by_email"](viewer_email)

        if viewer is None:
            viewer = user

        ui = deps["translation_bundle"](deps["get_current_language"](viewer))
        target_settings = deps["normalize_user_ai_settings"](user.email)
        profile_view_status = profile_access_service.profile_view_status(
            viewer.email,
            user.email,
            target_settings,
            deps["is_blocked"],
            deps["are_friends"],
        )

        if profile_view_status["status"] == "viewer_blocked_owner":
            return render_viewer_blocked_owner_page(user, viewer, deps)

        if profile_view_status["status"] == "owner_blocked_viewer":
            return deps["simple_page"](
                "🚫 Профиль недоступен",
                "Этот пользователь ограничил доступ к своему профилю.",
                viewer.email,
            )

        is_own_profile = profile_view_status["is_own_profile"]
        viewer_blocked_user = profile_view_status["status"] == "viewer_blocked_owner"

        if profile_view_status["status"] == "deactivated":
            viewer_ui = deps["translation_bundle"](deps["get_current_language"](viewer))
            return deps["simple_page"](
                deps["safe_text"](viewer_ui.get("account_deactivated_badge", "Account deactivated")),
                deps["safe_text"](viewer_ui.get("account_temporarily_unavailable", "This profile is temporarily unavailable.")),
                viewer.email,
            ), 404

        if profile_view_status["status"] == "private":
            return deps["simple_page"](
                "Профиль закрыт",
                "Этот пользователь сделал профиль приватным.",
                viewer.email,
            )

        if profile_view_status["status"] == "friends_only":
            return deps["simple_page"](
                "Профиль только для друзей",
                "Этот профиль доступен только друзьям пользователя.",
                viewer.email,
            )

        feed_data = deps["load_feed"]()
        posts = feed_data.get("posts", [])
        if not isinstance(posts, list):
            posts = []

        profile_post_summary = profile_posts_service.profile_post_summary(posts, user.email, request.args.get("tab", "all"), {
            "clean_text": deps["clean_text"],
            "normalize_email": deps["normalize_email"],
        })
        current_tab = profile_post_summary["current_tab"]
        filtered_posts = profile_post_summary["filtered_posts"]
        profile_tab_counts = profile_post_summary["counts"]
        posts_html = profile_render_service.render_profile_posts(
            filtered_posts,
            current_tab,
            viewer.email,
            deps["clean_text"],
            deps["safe_text"],
        )

        viewer_is_friend = deps["are_friends"](viewer.email, user.email) if not is_own_profile else False
        actions_html = profile_actions_service.render_profile_actions({
            "are_friends": viewer_is_friend,
            "has_hidden_stories": deps["has_hidden_stories_from"](viewer.email, user.email) if not is_own_profile else False,
            "is_own_profile": is_own_profile,
            "is_restricted": deps["is_restricted"](viewer.email, user.email) if not is_own_profile else False,
            "message_permission": deps["clean_text"](target_settings.get("message_permission", "everyone")),
            "owner_email": user.email,
            "viewer_blocked_user": viewer_blocked_user,
            "viewer_email": viewer.email,
            "viewer_follows_user": deps["is_following"](viewer.email, user.email) if not is_own_profile else False,
            "viewer_verified": getattr(viewer, "verified", False),
        }, deps["safe_text"], ui, deps["csrf_input"]())

        show_profile_activity = is_own_profile or target_settings.get("show_activity_status", True) is True

        if show_profile_activity:
            tabs_html = profile_render_service.render_profile_tabs(
                current_tab,
                profile_tab_counts,
                user.email,
                viewer.email,
                deps["safe_text"],
            )
        else:
            tabs_html = '<div class="profile-empty-mini">Пользователь скрыл активность профиля.</div>'
            posts_html = '<div class="profile-empty-card"><h3>Активность скрыта</h3><p>Этот пользователь не показывает публичную активность профиля.</p></div>'

        profile_stats_html = profile_render_service.render_profile_stats(
            user.email,
            viewer.email,
            profile_tab_counts,
            deps["count_following"](user.email),
            deps["count_followers"](user.email),
            show_profile_activity,
            deps["safe_text"],
        )
        profile_meta_html, profile_bio_html = profile_render_service.render_profile_header_text(
            user,
            deps["clean_text"],
            deps["safe_text"],
        )
        profile_info_html = profile_render_service.render_profile_info(user, deps["clean_text"], deps["safe_text"])

        return render_profile_page(
            user=user,
            viewer=viewer,
            actions_html=actions_html,
            posts_html=posts_html,
            profile_bio_html=profile_bio_html,
            profile_info_html=profile_info_html,
            profile_meta_html=profile_meta_html,
            profile_stats_html=profile_stats_html,
            tabs_html=tabs_html,
            deps=deps,
        )

    return profile_routes


def render_viewer_blocked_owner_page(user, viewer, deps):
    safe_text = deps["safe_text"]
    return f"""
        <!DOCTYPE html>
        <html lang="ru">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Пользователь заблокирован</title>
            <style>
                *{{box-sizing:border-box}}
                body{{margin:0;background:#0f172a;color:white;font-family:Arial,sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh;padding:24px;}}
                .blocked-card{{max-width:620px;width:100%;background:#1e293b;border:1px solid rgba(148,163,184,0.14);border-radius:30px;padding:30px;text-align:center;box-shadow:0 24px 70px rgba(0,0,0,0.32);}}
                .blocked-avatar{{width:96px;height:96px;border-radius:50%;object-fit:cover;border:4px solid #334155;margin-bottom:16px;background:#334155;}}
                h1{{margin:0 0 12px 0;font-size:28px;}}
                p{{color:#cbd5e1;line-height:1.55;margin:0 0 20px 0;}}
                .blocked-actions{{display:flex;gap:10px;justify-content:center;flex-wrap:wrap;}}
                .blocked-action{{display:inline-flex;align-items:center;justify-content:center;background:#334155;color:white;text-decoration:none;border-radius:15px;padding:12px 16px;font-weight:bold;}}
                .blocked-action.primary{{background:#2563eb;}}
            </style>
        </head>
        <body>
            <main class="blocked-card">
                <img class="blocked-avatar" src="{deps["get_avatar_url"](user.email)}" alt="Avatar">
                <h1>Пользователь заблокирован</h1>
                <p>Вы заблокировали {safe_text(user.name)}. Этот пользователь не может писать вам и открывать ваш профиль. Вы можете разблокировать его в любой момент.</p>
                <div class="blocked-actions">
                    <a class="blocked-action" href="/dashboard/{safe_text(viewer.email)}">← На главную</a>
                    <form method="POST" action="/unblock_user/{safe_text(viewer.email)}/{safe_text(user.email)}">
                        {deps["csrf_input"]()}
                        <button class="blocked-action primary" type="submit">Разблокировать</button>
                    </form>
                </div>
            </main>
        </body>
        </html>
        """


def render_profile_page(
    user,
    viewer,
    actions_html,
    posts_html,
    profile_bio_html,
    profile_info_html,
    profile_meta_html,
    profile_stats_html,
    tabs_html,
    deps,
):
    safe_text = deps["safe_text"]
    return f"""
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{safe_text(user.name)} — AI Match Life</title>
        <style>
            *{{box-sizing:border-box}}
            body{{margin:0;background:#0f172a;color:white;font-family:Arial,sans-serif;}}
            a{{color:inherit}}
            .profile-page{{max-width:1180px;margin:auto;padding:28px;}}
            .back-link{{display:inline-flex;align-items:center;gap:8px;background:#1e293b;color:white;text-decoration:none;padding:12px 16px;border-radius:14px;font-weight:bold;margin-bottom:18px;}}
            .profile-hero{{background:linear-gradient(135deg,#111827,#172554 52%,#312e81);border:1px solid rgba(148,163,184,0.14);border-radius:34px;padding:28px;display:grid;grid-template-columns:auto 1fr;gap:24px;box-shadow:0 24px 70px rgba(0,0,0,0.30);}}
            .profile-avatar-wrap{{width:156px;height:156px;border-radius:50%;padding:4px;background:linear-gradient(135deg,#2563eb,#8b5cf6,#ec4899,#f59e0b);}}
            .profile-avatar{{width:100%;height:100%;border-radius:50%;object-fit:cover;border:5px solid #0f172a;background:#334155;}}
            .profile-main h1{{margin:0;font-size:34px;line-height:1.1;}}
            .profile-sub{{color:#cbd5e1;margin:8px 0 0 0;line-height:1.5;}}
            .profile-badges{{display:flex;flex-wrap:wrap;gap:9px;margin-top:14px;}}
            .profile-badge{{background:rgba(15,23,42,0.55);border:1px solid rgba(148,163,184,0.18);border-radius:999px;padding:8px 11px;color:#dbeafe;font-weight:bold;font-size:13px;}}
            .profile-relation{{display:inline-flex;align-items:center;gap:8px;margin-top:12px;border-radius:999px;padding:9px 12px;font-weight:bold;font-size:13px;border:1px solid rgba(148,163,184,0.18);}}
            .profile-relation.own{{background:rgba(37,99,235,0.20);color:#bfdbfe;}}
            .profile-relation.friends{{background:rgba(34,197,94,0.18);color:#bbf7d0;}}
            .profile-relation.mutual{{background:rgba(20,184,166,0.18);color:#ccfbf1;}}
            .profile-relation.following{{background:rgba(96,165,250,0.18);color:#dbeafe;}}
            .profile-relation.follower{{background:rgba(168,85,247,0.18);color:#ede9fe;}}
            .profile-relation.pending{{background:rgba(250,204,21,0.16);color:#fef3c7;}}
            .profile-relation.none{{background:rgba(100,116,139,0.18);color:#e2e8f0;}}
            .profile-stats{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-top:18px;max-width:520px;}}
            .profile-stat{{background:rgba(15,23,42,0.55);border:1px solid rgba(148,163,184,0.15);border-radius:20px;padding:14px;text-decoration:none;}}
            .profile-stat span{{display:block;color:#cbd5e1;font-size:13px;margin-bottom:5px;}}
            .profile-stat strong{{font-size:24px;}}
            .profile-actions{{display:flex;flex-wrap:wrap;gap:10px;margin-top:18px;}}
            .profile-action{{background:#334155;color:white;text-decoration:none;border:none;border-radius:15px;padding:11px 14px;font-weight:bold;display:inline-flex;align-items:center;justify-content:center;}}
            .profile-action.primary{{background:#2563eb;}}
            .profile-action.green{{background:#16a34a;}}
            .profile-action.danger{{background:#991b1b;}}
            .profile-action.disabled{{background:#475569;color:#cbd5e1;}}
            .profile-more-menu{{position:relative;display:inline-block;}}
            .profile-more-menu summary{{list-style:none;background:#334155;color:white;border-radius:15px;padding:11px 16px;font-weight:bold;cursor:pointer;min-width:48px;text-align:center;}}
            .profile-more-menu summary::-webkit-details-marker{{display:none;}}
            .profile-more-menu[open]::before{{content:"";position:fixed;inset:0;background:rgba(2,6,23,0.62);backdrop-filter:blur(5px);z-index:9998;}}
            .profile-more-list{{position:fixed;left:50%;bottom:22px;transform:translateX(-50%);z-index:9999;background:#020617;border:1px solid rgba(148,163,184,0.24);border-radius:24px;width:min(420px,calc(100vw - 28px));box-shadow:0 30px 90px rgba(0,0,0,0.58);overflow:hidden;animation:profileSheetUp .16s ease-out;}}
            @keyframes profileSheetUp{{from{{opacity:0;transform:translateX(-50%) translateY(18px) scale(.98)}}to{{opacity:1;transform:translateX(-50%) translateY(0) scale(1)}}}}
            .profile-more-list a{{display:flex;align-items:center;justify-content:center;min-height:52px;padding:14px 18px;color:white;text-decoration:none;font-weight:bold;border-bottom:1px solid rgba(148,163,184,0.10);font-size:15px;}}
            .profile-more-list a:hover{{background:#1e293b;}}
            .profile-more-list .danger-link{{color:#fecaca;}}
            .profile-more-list .cancel-link{{background:#111827;color:#e5e7eb;}}
            .profile-empty-mini{{color:#94a3b8;line-height:1.5;background:#0f172a;border:1px solid rgba(148,163,184,0.12);border-radius:18px;padding:16px;}}
            .profile-grid{{display:grid;grid-template-columns:360px 1fr;gap:18px;margin-top:18px;}}
            .profile-card{{background:#1e293b;border:1px solid rgba(148,163,184,0.12);border-radius:28px;padding:22px;}}
            .profile-card h2{{margin:0 0 12px 0;}}
            .profile-info-row{{margin-bottom:13px;}}
            .profile-info-label{{color:#93c5fd;font-weight:bold;font-size:13px;margin-bottom:4px;}}
            .profile-info-value{{color:#e5e7eb;line-height:1.5;}}
            .profile-ai{{background:linear-gradient(135deg,rgba(37,99,235,0.28),rgba(124,58,237,0.20));border:1px solid rgba(96,165,250,0.22);}}
            .profile-tabs{{display:flex;gap:10px;overflow:auto;padding-bottom:8px;margin-bottom:16px;}}
            .profile-tab{{white-space:nowrap;text-decoration:none;background:#0f172a;border:1px solid rgba(148,163,184,0.14);border-radius:999px;padding:10px 13px;display:flex;gap:8px;align-items:center;color:#cbd5e1;font-weight:bold;}}
            .profile-tab.active{{background:#2563eb;color:white;border-color:#60a5fa;}}
            .profile-tab strong{{background:rgba(255,255,255,0.16);border-radius:999px;padding:3px 7px;font-size:12px;}}
            .profile-post-card{{background:#0f172a;border:1px solid rgba(148,163,184,0.14);border-radius:24px;padding:18px;margin-bottom:14px;}}
            .profile-post-top{{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:10px;}}
            .profile-post-type{{color:#60a5fa;font-weight:bold;}}
            .profile-post-date{{color:#94a3b8;font-size:13px;margin-top:4px;}}
            .profile-post-open{{background:#334155;color:white;text-decoration:none;border-radius:12px;padding:9px 11px;font-weight:bold;font-size:13px;}}
            .profile-post-text{{white-space:pre-wrap;color:#e5e7eb;line-height:1.55;font-size:15px;}}
            .profile-post-media{{width:100%;max-height:420px;object-fit:cover;border-radius:18px;margin-top:12px;background:#020617;}}
            .profile-tags{{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px;}}
            .profile-tag{{background:rgba(37,99,235,0.16);color:#bfdbfe;border-radius:999px;padding:6px 9px;font-weight:bold;font-size:12px;}}
            .profile-post-actions{{display:flex;gap:12px;color:#cbd5e1;margin-top:14px;font-weight:bold;}}
            .profile-empty-card{{background:#0f172a;border:1px solid rgba(148,163,184,0.14);border-radius:24px;padding:26px;color:#cbd5e1;text-align:center;}}
            @media(max-width:900px){{.profile-page{{padding:16px}}.profile-hero{{grid-template-columns:1fr;text-align:center}}.profile-avatar-wrap{{margin:auto}}.profile-stats{{max-width:none}}.profile-actions{{justify-content:center}}.profile-grid{{grid-template-columns:1fr}}}}
        </style>
    </head>
    <body>
        <main class="profile-page">
            <a class="back-link" href="/dashboard/{safe_text(viewer.email)}">← Назад</a>

            <section class="profile-hero">
                <div class="profile-avatar-wrap">
                    <img class="profile-avatar" src="{deps["get_avatar_url"](user.email)}" alt="Avatar">
                </div>
                <div class="profile-main">
                    <h1>{safe_text(user.name)}</h1>
                    {profile_meta_html}
                    {profile_bio_html}

                    {profile_stats_html}

                    <div class="profile-actions">{actions_html}</div>
                </div>
            </section>

            <section class="profile-grid">
                <aside class="profile-card">
                    <h2>О человеке</h2>
                    {profile_info_html}
                </aside>

                <section>
                    <div class="profile-card">
                        <div class="profile-tabs">{tabs_html}</div>
                        {posts_html}
                    </div>
                </section>
            </section>
        </main>
    </body>
    </html>
    """
