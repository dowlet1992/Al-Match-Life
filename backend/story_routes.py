from flask import Blueprint, redirect, request

from backend.services import story_creation_service, story_view_service


def create_story_routes(deps):
    story_routes = Blueprint("story_routes", __name__)

    @story_routes.route("/create_story/<email>", methods=["POST"])
    @deps["login_required"]
    def create_story(email):
        deps["validate_csrf_token"]()
        user = deps["find_user_by_email"](email)

        if user is None:
            return "User not found"

        uploaded_files = request.files.getlist("story_media")
        if not uploaded_files:
            return redirect(f"/dashboard/{user.email}")

        upload_folder = deps["upload_folder"]() if callable(deps["upload_folder"]) else deps["upload_folder"]
        result = story_creation_service.create_stories(user, uploaded_files, deps["load_stories"](), {
            "allowed_mime_type": deps["allowed_mime_type"],
            "log_security_event": deps["log_security_event"],
            "upload_folder": upload_folder,
        })
        deps["save_stories"](result["stories_data"])

        if result.get("created_count", 0) == 0:
            return deps["simple_page"](
                "Story не добавлена",
                "Файл не подходит. Добавьте фото или видео.",
                user.email,
            )

        return redirect(f"/dashboard/{user.email}")

    @story_routes.route("/story/<viewer_email>/<owner_email>")
    @deps["login_required"]
    def view_story(viewer_email, owner_email):
        viewer = deps["find_user_by_email"](viewer_email)
        owner = deps["find_user_by_email"](owner_email)

        if viewer is None or owner is None:
            return "User not found"

        view_result = story_view_service.prepare_story_view(viewer, owner, deps["load_stories"](), {
            "can_view_user_stories": deps["can_view_user_stories"],
            "is_blocked": deps["is_blocked"],
            "is_story_active": deps["is_story_active"],
            "log_security_event": deps["log_security_event"],
            "normalize_email": deps["normalize_email"],
        })

        if view_result.get("status") == "blocked":
            return deps["simple_page"](
                "🚫 Story недоступна",
                "Нельзя просматривать Story этого пользователя, потому что один из пользователей заблокировал другого.",
                viewer.email,
            )

        if view_result.get("status") == "restricted":
            return deps["simple_page"](
                "Story недоступна",
                "Этот пользователь ограничил аудиторию своих Stories.",
                viewer.email,
            )

        if view_result.get("changed"):
            deps["save_stories"](view_result["stories_data"])

        owner_stories = view_result.get("owner_stories", [])

        if view_result.get("status") == "empty":
            return deps["simple_page"](
                "Историй пока нет",
                "У этого пользователя нет активных историй за последние 24 часа.",
                viewer.email,
            )

        return render_story_viewer(
            owner_stories,
            owner_avatar=deps["get_avatar_url"](owner.email),
            owner_name=deps["safe_text"](owner.name),
            back_url=f"/dashboard/{deps['safe_text'](viewer.email)}",
            story_count_text=view_result.get("story_count_text", f"{len(owner_stories)} историй"),
            clean_text=deps["clean_text"],
            safe_text=deps["safe_text"],
        )

    return story_routes


def render_story_viewer(owner_stories, owner_avatar, owner_name, back_url, story_count_text, clean_text, safe_text):
    slides_html = ""
    progress_html = ""

    for index, story in enumerate(owner_stories):
        media_url = safe_text(story.get("media_url", ""))
        media_type = clean_text(story.get("media_type", ""))
        active_class = "active" if index == 0 else ""

        if media_type == "video":
            media_html = f"""
            <video class="story-media" playsinline muted autoplay>
                <source src="{media_url}">
            </video>
            """
        else:
            media_html = f"""
            <img class="story-media" src="{media_url}" alt="Story">
            """

        slides_html += f"""
        <div class="story-slide {active_class}" data-index="{index}">
            {media_html}
        </div>
        """

        progress_html += """
        <div class="story-progress-item"><span class="story-progress-fill"></span></div>
        """

    return f"""
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0">
        <title>Story — AI Match Life</title>
        <style>
            *{{box-sizing:border-box}}
            body{{margin:0;background:#020617;color:white;font-family:Arial,sans-serif;min-height:100vh;display:flex;align-items:center;justify-content:center;}}
            .story-shell{{width:min(430px,100vw);height:min(760px,100vh);background:#000;border-radius:28px;overflow:hidden;position:relative;box-shadow:0 30px 90px rgba(0,0,0,0.55);}}
            @media(max-width:640px){{.story-shell{{width:100vw;height:100vh;border-radius:0;}}}}
            .story-progress{{position:absolute;top:12px;left:12px;right:12px;display:flex;gap:5px;z-index:10;}}
            .story-progress-item{{height:3px;flex:1;background:rgba(255,255,255,0.28);border-radius:999px;overflow:hidden;}}
            .story-progress-fill{{display:block;width:0%;height:100%;background:white;border-radius:999px;}}
            .story-header{{position:absolute;top:24px;left:14px;right:14px;display:flex;align-items:center;gap:10px;z-index:11;padding-top:8px;}}
            .story-header img{{width:38px;height:38px;border-radius:50%;object-fit:cover;border:2px solid white;}}
            .story-name{{font-weight:bold;text-shadow:0 2px 8px rgba(0,0,0,0.6);}}
            .story-count{{font-size:12px;color:#cbd5e1;margin-top:2px;text-shadow:0 2px 8px rgba(0,0,0,0.6);}}
            .story-close{{margin-left:auto;color:white;text-decoration:none;background:rgba(15,23,42,0.45);border:1px solid rgba(255,255,255,0.18);width:38px;height:38px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:22px;}}
            .story-slide{{position:absolute;inset:0;display:none;background:#000;}}
            .story-slide.active{{display:block;}}
            .story-media{{width:100%;height:100%;object-fit:cover;background:#000;}}
            .tap-zone{{position:absolute;top:92px;bottom:0;width:50%;z-index:9;background:transparent;border:none;cursor:pointer;}}
            .tap-left{{left:0;}}
            .tap-right{{right:0;}}
            .story-footer{{position:absolute;left:16px;right:16px;bottom:18px;z-index:12;display:flex;gap:10px;align-items:center;}}
            .story-footer input{{flex:1;background:rgba(15,23,42,0.65);border:1px solid rgba(255,255,255,0.25);border-radius:999px;color:white;padding:13px 16px;outline:none;}}
            .story-footer button{{background:rgba(37,99,235,0.85);color:white;border:none;border-radius:999px;padding:13px 16px;font-weight:bold;}}
        </style>
    </head>
    <body>
        <main class="story-shell">
            <div class="story-progress">{progress_html}</div>

            <div class="story-header">
                <img src="{owner_avatar}" alt="Avatar">
                <div>
                    <div class="story-name">{owner_name}</div>
                    <div class="story-count">{safe_text(story_count_text)}</div>
                </div>
                <a class="story-close" href="{back_url}">×</a>
            </div>

            {slides_html}

            <button class="tap-zone tap-left" onclick="prevStory()" aria-label="Previous story"></button>
            <button class="tap-zone tap-right" onclick="nextStory()" aria-label="Next story"></button>

            <form class="story-footer" onsubmit="return false;">
                <input placeholder="Ответить..." disabled>
                <button disabled>➤</button>
            </form>
        </main>

        <script>
            const slides = Array.from(document.querySelectorAll('.story-slide'));
            const fills = Array.from(document.querySelectorAll('.story-progress-fill'));
            let current = 0;
            let timer = null;
            const duration = 5000;

            function showStory(index) {{
                if (index < 0) index = 0;
                if (index >= slides.length) {{
                    window.location.href = "{back_url}";
                    return;
                }}

                slides.forEach((slide, i) => {{
                    slide.classList.toggle('active', i === index);
                    const video = slide.querySelector('video');
                    if (video) {{
                        if (i === index) {{
                            video.currentTime = 0;
                            video.play().catch(() => {{}});
                        }} else {{
                            video.pause();
                        }}
                    }}
                }});

                fills.forEach((fill, i) => {{
                    fill.style.transition = 'none';
                    fill.style.width = i < index ? '100%' : '0%';
                }});

                current = index;
                clearTimeout(timer);

                requestAnimationFrame(() => {{
                    fills[current].style.transition = `width ${{duration}}ms linear`;
                    fills[current].style.width = '100%';
                }});

                timer = setTimeout(() => nextStory(), duration);
            }}

            function nextStory() {{ showStory(current + 1); }}
            function prevStory() {{ showStory(current - 1); }}

            document.addEventListener('keydown', function(event) {{
                if (event.key === 'ArrowRight') nextStory();
                if (event.key === 'ArrowLeft') prevStory();
                if (event.key === 'Escape') window.location.href = "{back_url}";
            }});

            showStory(0);
        </script>
    </body>
    </html>
    """
