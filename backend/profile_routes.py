from flask import Blueprint, render_template, request

from backend.services import profile_access_service
from backend.services import profile_actions_service
from backend.services import profile_posts_service
from backend.services import profile_render_service


def create_profile_routes(deps):
    profile_routes = Blueprint("profile_routes", __name__)

    @profile_routes.route("/profile/<identifier>")
    @deps["profile_view_required"]
    def profile(identifier):
        user = deps["find_user_by_identifier"](identifier)

        if user is None:
            return "User not found"

        viewer_identifier = request.args.get("viewer") or deps["current_session_email"]() or identifier
        viewer = deps["find_user_by_identifier"](viewer_identifier)

        if viewer is None:
            viewer = user

        ui = deps["translation_bundle"](deps["get_current_language"](viewer))
        access_copy = profile_access_copy(ui.get("language_code", "en"))
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
                f"🚫 {access_copy['blocked_title']}",
                access_copy["blocked_message"],
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
                access_copy["private_title"],
                access_copy["private_message"],
                viewer.email,
            )

        if profile_view_status["status"] == "friends_only":
            return deps["simple_page"](
                access_copy["friends_title"],
                access_copy["friends_message"],
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
        profile_posts = profile_render_service.build_profile_posts(filtered_posts, deps["clean_text"])

        viewer_is_friend = deps["are_friends"](viewer.email, user.email) if not is_own_profile else False
        actions = profile_actions_service.build_profile_actions({
            "are_friends": viewer_is_friend,
            "has_hidden_stories": deps["has_hidden_stories_from"](viewer.email, user.email) if not is_own_profile else False,
            "is_own_profile": is_own_profile,
            "is_restricted": deps["is_restricted"](viewer.email, user.email) if not is_own_profile else False,
            "message_permission": deps["clean_text"](target_settings.get("message_permission", "everyone")),
            "owner_email": user.email,
            "owner_id": user.id,
            "viewer_blocked_user": viewer_blocked_user,
            "viewer_email": viewer.email,
            "viewer_id": viewer.id,
            "viewer_follows_user": deps["is_following"](viewer.email, user.email) if not is_own_profile else False,
            "viewer_verified": getattr(viewer, "verified", False),
        }, ui)

        show_profile_activity = is_own_profile or target_settings.get("show_activity_status", True) is True

        if show_profile_activity:
            profile_tabs = profile_render_service.build_profile_tabs(current_tab, profile_tab_counts)
        else:
            profile_tabs = []
            profile_posts = []

        profile_stats = profile_render_service.build_profile_stats(
            profile_tab_counts,
            deps["count_following"](user.email),
            deps["count_followers"](user.email),
            show_profile_activity,
        )
        language = ui.get("language_code", "en")
        profile_copy = profile_page_copy(language)
        profile_header = profile_render_service.build_profile_header(user, deps["clean_text"])
        profile_info = profile_render_service.build_profile_info(user, deps["clean_text"], profile_copy["labels"])

        return render_profile_page(
            user=user,
            viewer=viewer,
            actions=actions,
            current_tab=current_tab,
            profile_copy=profile_copy,
            profile_header=profile_header,
            profile_info=profile_info,
            profile_posts=profile_posts,
            profile_stats=profile_stats,
            profile_tabs=profile_tabs,
            show_profile_activity=show_profile_activity,
            deps=deps,
        )

    return profile_routes


def profile_access_copy(language):
    copies = {
        "ru": {
            "blocked_title": "Профиль недоступен",
            "blocked_message": "Этот пользователь ограничил доступ к своему профилю.",
            "private_title": "Профиль закрыт",
            "private_message": "Этот пользователь сделал профиль приватным.",
            "friends_title": "Профиль только для друзей",
            "friends_message": "Этот профиль доступен только друзьям пользователя.",
        },
        "de": {
            "blocked_title": "Profil nicht verfügbar",
            "blocked_message": "Diese Person hat den Zugriff auf ihr Profil eingeschränkt.",
            "private_title": "Privates Profil",
            "private_message": "Diese Person hat ihr Profil auf privat gestellt.",
            "friends_title": "Profil nur für Freunde",
            "friends_message": "Dieses Profil ist nur für Freunde der Person sichtbar.",
        },
        "en": {
            "blocked_title": "Profile unavailable",
            "blocked_message": "This person has restricted access to their profile.",
            "private_title": "Private profile",
            "private_message": "This person has made their profile private.",
            "friends_title": "Friends-only profile",
            "friends_message": "This profile is available only to the person's friends.",
        },
        "tr": {
            "blocked_title": "Profil kullanılamıyor",
            "blocked_message": "Bu kişi profiline erişimi kısıtladı.",
            "private_title": "Gizli profil",
            "private_message": "Bu kişi profilini gizli olarak ayarladı.",
            "friends_title": "Yalnızca arkadaşlara açık profil",
            "friends_message": "Bu profil yalnızca kullanıcının arkadaşları tarafından görülebilir.",
        },
    }
    return copies.get(str(language or "en").lower(), copies["en"])


def render_viewer_blocked_owner_page(user, viewer, deps):
    ui = deps["translation_bundle"](deps["get_current_language"](viewer))
    language = ui.get("language_code", "en")
    copies = {
        "ru": {
            "title": "Пользователь заблокирован",
            "message": "Вы заблокировали {name}. Этот пользователь не может писать вам и открывать ваш профиль. Вы можете разблокировать его в любой момент.",
            "home": "На главную",
            "unblock": "Разблокировать",
        },
        "de": {
            "title": "Person blockiert",
            "message": "Sie haben {name} blockiert. Diese Person kann Ihnen nicht schreiben oder Ihr Profil öffnen. Sie können die Blockierung jederzeit aufheben.",
            "home": "Zur Startseite",
            "unblock": "Entsperren",
        },
        "en": {
            "title": "Person blocked",
            "message": "You blocked {name}. This person cannot message you or open your profile. You can unblock them at any time.",
            "home": "Back home",
            "unblock": "Unblock",
        },
        "tr": {
            "title": "Kullanıcı engellendi",
            "message": "{name} adlı kullanıcıyı engellediniz. Bu kullanıcı size mesaj gönderemez veya profilinizi açamaz. Engeli istediğiniz zaman kaldırabilirsiniz.",
            "home": "Ana sayfaya dön",
            "unblock": "Engeli kaldır",
        },
    }
    copy = copies.get(language, copies["en"])
    return render_template(
        "profile_blocked.html",
        ui=ui,
        copy=copy,
        email=viewer.email,
        blocked_email=user.email,
        blocked_name=user.name,
        blocked_avatar=deps["get_avatar_url"](user.email),
        csrf_token_input=deps["csrf_input"](),
    )


def render_profile_page(
    user,
    viewer,
    actions,
    current_tab,
    profile_copy,
    profile_header,
    profile_info,
    profile_posts,
    profile_stats,
    profile_tabs,
    show_profile_activity,
    deps,
):
    ui = deps["translation_bundle"](deps["get_current_language"](viewer))
    return render_template(
        "profile_page.html",
        ui=ui,
        email=viewer.email,
        user=user,
        avatar_url=deps["get_avatar_url"](user.email),
        copy=profile_copy,
        actions=actions,
        csrf_token_input=deps["csrf_input"](),
        current_tab=current_tab,
        profile_header=profile_header,
        profile_info=profile_info,
        profile_posts=profile_posts,
        profile_stats=profile_stats,
        profile_tabs=profile_tabs,
        show_profile_activity=show_profile_activity,
    )


def profile_page_copy(language):
    copies = {
        "ru": {
            "about": "О человеке", "empty_info": "Профиль пока без подробной информации.",
            "activity": "Активность", "following": "Подписки", "followers": "Подписчики",
            "tabs": {"all": "Все", "news": "Новости", "projects": "Проекты", "media": "Фото/Видео", "proof": "Proof"},
            "open": "Открыть", "empty": "Пусто", "hidden": "Активность скрыта",
            "hidden_help": "Этот пользователь не показывает публичную активность профиля.",
            "empty_tabs": {"all": "Пока нет активности в этом разделе.", "news": "Пока нет новостей, мыслей или идей.", "projects": "Пока нет проектов или поиска партнёров.", "media": "Пока нет фото или видео.", "proof": "Пока нет Proof-публикаций."},
            "labels": {"age": "Возраст", "languages": "Языки", "goals": "Цели", "interests": "Интересы", "skills": "Навыки"},
        },
        "de": {
            "about": "Über die Person", "empty_info": "Noch keine ausführlichen Profilinformationen.",
            "activity": "Aktivität", "following": "Abonniert", "followers": "Follower",
            "tabs": {"all": "Alle", "news": "Neuigkeiten", "projects": "Projekte", "media": "Foto/Video", "proof": "Proof"},
            "open": "Öffnen", "empty": "Leer", "hidden": "Aktivität verborgen",
            "hidden_help": "Diese Person zeigt keine öffentliche Profilaktivität.",
            "empty_tabs": {"all": "Noch keine Aktivität.", "news": "Noch keine Neuigkeiten.", "projects": "Noch keine Projekte.", "media": "Noch keine Fotos oder Videos.", "proof": "Noch keine Proof-Beiträge."},
            "labels": {"age": "Alter", "languages": "Sprachen", "goals": "Ziele", "interests": "Interessen", "skills": "Fähigkeiten"},
        },
        "tr": {
            "about": "Kişi hakkında", "empty_info": "Henüz ayrıntılı profil bilgisi yok.",
            "activity": "Etkinlik", "following": "Takip edilenler", "followers": "Takipçiler",
            "tabs": {"all": "Tümü", "news": "Haberler", "projects": "Projeler", "media": "Fotoğraf/Video", "proof": "Proof"},
            "open": "Aç", "empty": "Boş", "hidden": "Etkinlik gizli",
            "hidden_help": "Bu kişi herkese açık profil etkinliğini göstermiyor.",
            "empty_tabs": {"all": "Henüz etkinlik yok.", "news": "Henüz haber, düşünce veya fikir yok.", "projects": "Henüz proje veya ortak arayışı yok.", "media": "Henüz fotoğraf veya video yok.", "proof": "Henüz Proof gönderisi yok."},
            "labels": {"age": "Yaş", "languages": "Diller", "goals": "Hedefler", "interests": "İlgi alanları", "skills": "Beceriler"},
        },
    }
    return copies.get(language, {
        "about": "About", "empty_info": "No detailed profile information yet.",
        "activity": "Activity", "following": "Following", "followers": "Followers",
        "tabs": {"all": "All", "news": "News", "projects": "Projects", "media": "Photo/Video", "proof": "Proof"},
        "open": "Open", "empty": "Empty", "hidden": "Activity hidden",
        "hidden_help": "This person does not show public profile activity.",
        "empty_tabs": {"all": "No activity yet.", "news": "No news yet.", "projects": "No projects yet.", "media": "No photos or videos yet.", "proof": "No Proof posts yet."},
        "labels": {"age": "Age", "languages": "Languages", "goals": "Goals", "interests": "Interests", "skills": "Skills"},
    })
