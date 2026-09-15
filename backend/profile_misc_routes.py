from flask import Blueprint, render_template


def create_profile_misc_routes(deps):
    profile_misc = Blueprint("profile_misc_routes", __name__)

    def copy_for(user):
        ui = deps["translation_bundle"](deps["get_current_language"](user))
        language = ui.get("language_code", "en")
        copy = {
            "ru": {
                "title": "Заблокированные", "intro": "Здесь находятся пользователи, которых вы заблокировали.",
                "unblock": "Разблокировать", "empty": "Чёрный список пуст.",
                "hashtag_intro": "Публикации по выбранному хэштегу.", "empty_prefix": "По хэштегу", "empty_suffix": "пока нет публикаций.",
            },
            "de": {
                "title": "Blockierte Personen", "intro": "Hier sehen Sie blockierte Personen.",
                "unblock": "Entsperren", "empty": "Die Blockierliste ist leer.",
                "hashtag_intro": "Beiträge zum ausgewählten Hashtag.", "empty_prefix": "Für den Hashtag", "empty_suffix": "gibt es noch keine Beiträge.",
            },
            "en": {
                "title": "Blocked people", "intro": "People you have blocked appear here.",
                "unblock": "Unblock", "empty": "The block list is empty.",
                "hashtag_intro": "Posts using the selected hashtag.", "empty_prefix": "There are no posts for", "empty_suffix": "yet.",
            },
            "tr": {
                "title": "Engellenen kişiler", "intro": "Engellediğiniz kişiler burada görünür.",
                "unblock": "Engeli kaldır", "empty": "Engellenenler listesi boş.",
                "hashtag_intro": "Seçilen etiketi kullanan gönderiler.", "empty_prefix": "Şu etiket için henüz gönderi yok:", "empty_suffix": "",
            },
        }.get(language)
        return ui, copy or {}

    @profile_misc.route("/blocked/<identifier>")
    @deps["login_required"]
    def blocked_users_page(identifier):
        user = deps["find_user_by_identifier"](identifier)
        if user is None:
            return "User not found", 404
        if deps["normalize_email"](deps["current_session_email"]()) != deps["normalize_email"](user.email):
            return "Forbidden", 403
        email = user.email
        ui, copy = copy_for(user)
        blocked_users = []
        for blocked_email in deps["get_blocked_users"](user.email):
            blocked = deps["find_user_by_email"](blocked_email)
            if blocked is not None:
                blocked_users.append({
                    "name": blocked.name,
                    "email": blocked.email,
                    "avatar_url": deps["get_avatar_url"](blocked.email),
                })
        return render_template(
            "blocked_users.html", ui=ui, copy=copy, email=user.email,
            blocked_users=blocked_users, csrf_token_input=deps["csrf_input"](),
        )

    @profile_misc.route("/hashtag/<identifier>/<tag>")
    @deps["login_required"]
    def hashtag_page(identifier, tag):
        user = deps["find_user_by_identifier"](identifier)
        if user is None:
            return "User not found", 404
        if deps["normalize_email"](deps["current_session_email"]()) != deps["normalize_email"](user.email):
            return "Forbidden", 403
        email = user.email
        ui, copy = copy_for(user)
        tag_lower = str(tag or "").lower()
        matching_posts = []
        feed_posts = deps["load_feed"]().get("posts", [])
        for post in reversed(feed_posts if isinstance(feed_posts, list) else []):
            if tag_lower not in [str(item).lower() for item in post.get("hashtags", [])]:
                continue
            author = deps["find_user_by_email"](post.get("email"))
            matching_posts.append({
                "author_name": author.name if author else "Unknown user",
                "date": post.get("date", ""),
                "text": post.get("text", ""),
            })
        hashtag_copy = {
            "intro": copy["hashtag_intro"],
            "empty_prefix": copy["empty_prefix"],
            "empty_suffix": copy["empty_suffix"],
        }
        return render_template(
            "hashtag.html", ui=ui, copy=hashtag_copy, email=user.email,
            tag=tag, posts=matching_posts,
        )

    return profile_misc
