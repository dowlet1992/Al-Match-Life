from flask import Flask, send_from_directory, request, redirect, render_template_string, session, abort
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import os
import json
import base64
import mimetypes
import secrets
from functools import wraps
from backend.social import follow_user, unfollow_user, is_following, send_friend_request, accept_friend_request, decline_friend_request, remove_friend, are_friends, has_friend_request, count_friends, count_followers, count_following, get_friends, get_followers, get_following, get_friend_requests
from datetime import datetime, timedelta
from backend.notifications import add_notification, get_notifications
from backend.storage import save_users_to_json, load_users_from_json
from backend.language import get_translations
from backend.models import User
from backend.trust import calculate_trust_score
from backend.search import find_user_by_email_and_password
from backend.recommendations import find_best_matches
from backend.explanations import explain_match
from backend.match_level import get_match_level
from database.users_data import users
from backend.proof import load_proofs, save_proofs
from backend.privacy import get_user_privacy, update_user_privacy
from backend.feed import load_feed, save_feed
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", secrets.token_hex(32))
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = False
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024 * 1024
from backend.ai_engine import analyze_user_profile, explain_user_match, generate_feed_idea, analyze_proof_profile, generate_life_radar
UPLOAD_FOLDER = "static/uploads"
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}

LOGIN_ATTEMPTS_FILE = "login_attempts.json"
MAX_LOGIN_ATTEMPTS = 5
LOGIN_ATTEMPT_WINDOW_MINUTES = 10
LOGIN_LOCK_MINUTES = 15

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

loaded_users = load_users_from_json()
if loaded_users is not None:
    users = loaded_users


def find_user_by_email(email):
    for user in users:
        if user.email.strip().lower() == email.strip().lower():
            return user
    return None

def is_password_hashed(password_value):
    if not password_value:
        return False
    return str(password_value).startswith("scrypt:") or str(password_value).startswith("pbkdf2:")


def set_user_password(user, raw_password):
    user.password = generate_password_hash(raw_password)


def verify_user_password(user, raw_password):
    if user is None:
        return False

    stored_password = getattr(user, "password", "")

    if is_password_hashed(stored_password):
        return check_password_hash(stored_password, raw_password)

    if stored_password == raw_password:
        set_user_password(user, raw_password)
        save_users_to_json(users)
        return True

    return False


def login_required(route_function):
    @wraps(route_function)
    def wrapper(*args, **kwargs):
        email = (
            kwargs.get("email")
            or kwargs.get("sender_email")
            or kwargs.get("viewer_email")
            or kwargs.get("profile_email")
       )
        logged_email = session.get("user_email")

        if not logged_email:
            return redirect("/")

        if email and logged_email.strip().lower() != email.strip().lower():
            return simple_page(
                "🔒 Доступ закрыт",
                "Вы не можете открыть страницу другого пользователя без входа в его аккаунт.",
                logged_email
            )

        return route_function(*args, **kwargs)

    return wrapper


def profile_view_required(route_function):
    @wraps(route_function)
    def wrapper(*args, **kwargs):
        logged_email = session.get("user_email")

        if not logged_email:
            return redirect("/")

        viewer_email = request.args.get("viewer", kwargs.get("email", ""))

        if viewer_email and logged_email.strip().lower() != viewer_email.strip().lower():
            return simple_page(
                "🔒 Доступ закрыт",
                "Вы не можете открыть профиль от имени другого пользователя.",
                logged_email
            )

        return route_function(*args, **kwargs)

    return wrapper


def load_login_attempts():
    try:
        with open(LOGIN_ATTEMPTS_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)
            if isinstance(data, dict):
                return data
            return {}
    except:
        return {}


def save_login_attempts(data):
    with open(LOGIN_ATTEMPTS_FILE, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4, ensure_ascii=False)


def get_login_attempt_key(email):
    ip_address = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown")
    ip_address = ip_address.split(",")[0].strip()
    return f"{email.strip().lower()}::{ip_address}"


def is_login_temporarily_locked(email):
    attempts_data = load_login_attempts()
    key = get_login_attempt_key(email)
    item = attempts_data.get(key)

    if not item:
        return False, 0

    locked_until = item.get("locked_until")
    if not locked_until:
        return False, 0

    try:
        locked_until_time = datetime.strptime(locked_until, "%Y-%m-%d %H:%M:%S")
    except:
        return False, 0

    if datetime.now() < locked_until_time:
        seconds_left = int((locked_until_time - datetime.now()).total_seconds())
        minutes_left = max(1, seconds_left // 60)
        return True, minutes_left

    item["locked_until"] = None
    item["attempts"] = []
    attempts_data[key] = item
    save_login_attempts(attempts_data)
    return False, 0


def register_failed_login_attempt(email):
    attempts_data = load_login_attempts()
    key = get_login_attempt_key(email)
    now = datetime.now()
    window_start = now - timedelta(minutes=LOGIN_ATTEMPT_WINDOW_MINUTES)

    item = attempts_data.get(key, {"attempts": [], "locked_until": None})
    clean_attempts = []

    for attempt_time_text in item.get("attempts", []):
        try:
            attempt_time = datetime.strptime(attempt_time_text, "%Y-%m-%d %H:%M:%S")
            if attempt_time >= window_start:
                clean_attempts.append(attempt_time_text)
        except:
            pass

    clean_attempts.append(now.strftime("%Y-%m-%d %H:%M:%S"))
    item["attempts"] = clean_attempts

    if len(clean_attempts) >= MAX_LOGIN_ATTEMPTS:
        item["locked_until"] = (now + timedelta(minutes=LOGIN_LOCK_MINUTES)).strftime("%Y-%m-%d %H:%M:%S")

    attempts_data[key] = item
    save_login_attempts(attempts_data)


def clear_login_attempts(email):
    attempts_data = load_login_attempts()
    key = get_login_attempt_key(email)

    if key in attempts_data:
        del attempts_data[key]
        save_login_attempts(attempts_data)


def get_csrf_token():
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


def csrf_input():
    return f'<input type="hidden" name="csrf_token" value="{get_csrf_token()}">'


def validate_csrf_token():
    session_token = session.get("csrf_token")
    form_token = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")

    if not session_token or not form_token or session_token != form_token:
        abort(403)

@app.after_request
def add_security_headers(response):
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "img-src 'self' data: https:; "
        "style-src 'self' 'unsafe-inline'; "
        "script-src 'self' 'unsafe-inline'; "
        "media-src 'self' data: https:;"
    )
    return response
    

def open_html(filename):
    with open(f"frontend/{filename}", "r", encoding="utf-8") as file:
        return file.read()


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def allowed_mime_type(file):
    mime_type, _ = mimetypes.guess_type(file.filename)

    allowed_types = {
        "image/jpeg",
        "image/png",
        "image/gif",
        "image/webp",
        "video/mp4",
        "video/webm",
        "video/quicktime",
        "audio/mpeg",
        "audio/mp4",
        "audio/wav",
        "audio/ogg"
    }

    return mime_type in allowed_types

def avatar_filename(email, extension):
    safe_email = secure_filename(email.replace("@", "_at_").replace(".", "_"))
    return f"{safe_email}.{extension}"


def get_avatar_url(email):
    safe_email = secure_filename(email.replace("@", "_at_").replace(".", "_"))

    for ext in ALLOWED_EXTENSIONS:
        path = f"{UPLOAD_FOLDER}/{safe_email}.{ext}"
        if os.path.exists(path):
            return f"/static/uploads/{safe_email}.{ext}"

    return "https://via.placeholder.com/160"
    

def load_messages():
    try:
        with open("messages.json", "r", encoding="utf-8") as file:
            return json.load(file)
    except:
        return []


def save_messages(messages):
    with open("messages.json", "w", encoding="utf-8") as file:
        json.dump(messages, file, indent=4, ensure_ascii=False)


# --- Stories helpers ---
def load_stories():
    try:
        with open("stories.json", "r", encoding="utf-8") as file:
            return json.load(file)
    except:
        return {"stories": []}


def save_stories(data):
    with open("stories.json", "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4, ensure_ascii=False)



def is_story_active(story):
    try:
        created_at = datetime.strptime(story.get("created_at", ""), "%Y-%m-%d %H:%M:%S")
        hours_passed = (datetime.now() - created_at).total_seconds() / 3600
        return hours_passed <= 24
    except:
        return False


# --- Block / blacklist helpers ---
def load_blocks():
    try:
        with open("blocks.json", "r", encoding="utf-8") as file:
            data = json.load(file)
            if isinstance(data, dict) and "blocks" in data:
                return data
            if isinstance(data, dict):
                return {"blocks": data}
            return {"blocks": {}}
    except:
        return {"blocks": {}}


def save_blocks(data):
    with open("blocks.json", "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4, ensure_ascii=False)


def get_blocked_users(email):
    data = load_blocks()
    return data.get("blocks", {}).get(email, [])


def is_blocked(blocker_email, blocked_email):
    return blocked_email in get_blocked_users(blocker_email)


def block_user_account(blocker_email, blocked_email):
    if blocker_email == blocked_email:
        return False

    data = load_blocks()
    blocks = data.get("blocks", {})
    blocked_list = blocks.get(blocker_email, [])

    if blocked_email not in blocked_list:
        blocked_list.append(blocked_email)

    blocks[blocker_email] = blocked_list
    data["blocks"] = blocks
    save_blocks(data)

    try:
        remove_friend(blocker_email, blocked_email)
        unfollow_user(blocker_email, blocked_email)
        unfollow_user(blocked_email, blocker_email)
    except:
        pass

    return True


def unblock_user_account(blocker_email, blocked_email):
    data = load_blocks()
    blocks = data.get("blocks", {})
    blocked_list = blocks.get(blocker_email, [])

    if blocked_email in blocked_list:
        blocked_list.remove(blocked_email)

    blocks[blocker_email] = blocked_list
    data["blocks"] = blocks
    save_blocks(data)
    return True


# --- Typing status helpers ---
def load_typing_status():
    try:
        with open("typing_status.json", "r", encoding="utf-8") as file:
            return json.load(file)
    except:
        return {}


def save_typing_status(data):
    with open("typing_status.json", "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4, ensure_ascii=False)
# --- Presence / online status helpers ---
def load_presence_status():
    try:
        with open("presence_status.json", "r", encoding="utf-8") as file:
            return json.load(file)
    except:
        return {}


def save_presence_status(data):
    with open("presence_status.json", "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4, ensure_ascii=False)


def format_last_seen(timestamp_value):
    if not timestamp_value:
        return "был(а) онлайн недавно"

    seconds = int(datetime.now().timestamp() - timestamp_value)

    if seconds < 15:
        return "🟢 онлайн"

    if seconds < 60:
        return "был(а) онлайн только что"

    minutes = seconds // 60
    if minutes < 60:
        return f"был(а) онлайн {minutes} мин. назад"

    hours = minutes // 60
    if hours < 24:
        return f"был(а) онлайн {hours} ч. назад"

    days = hours // 24
    return f"был(а) онлайн {days} дн. назад"
# --- Typing status route ---


# Add typing status route before chat_page
from flask import jsonify

@app.route("/typing/<sender_email>/<receiver_email>", methods=["POST"])
def typing_status(sender_email, receiver_email):
    data = load_typing_status()

    data[f"{sender_email}->{receiver_email}"] = datetime.now().timestamp()

    save_typing_status(data)

    return "OK"


# --- Presence status route ---
@app.route("/presence/<email>", methods=["POST"])
def presence_status(email):
    data = load_presence_status()
    data[email] = datetime.now().timestamp()
    save_presence_status(data)
    return "OK"
        


def safe_text(value):
    if value is None or value == "":
        return "Nicht angegeben"
    return value


def safe_list(values):
    if values is None or len(values) == 0:
        return "Nicht angegeben"
    return ", ".join(values)


def user_card(user):
    return f"""
    <div class="person-card">
        <h2>{safe_text(user.name)}</h2>
        <p><b>Beruf:</b> {safe_text(user.profession)}</p>
        <p><b>Auf der Suche nach:</b> {safe_text(user.looking_for)}</p>
        <p><b>Land:</b> {safe_text(user.country)}</p>
        <p><b>Kurzbiografie:</b> {safe_text(user.bio)}</p>
        <p><b>Sprachen:</b> {safe_list(user.languages)}</p>
        <p><b>Ziele:</b> {safe_list(user.goals)}</p>
        <p><b>Interessen:</b> {safe_list(user.interests)}</p>
        <p><b>Fähigkeiten:</b> {safe_list(user.skills)}</p>
        <button onclick="window.location.href='/profile/{user.email}'">Profil öffnen</button>
    </div>
    """


def page_style():
    return """
    <style>
    body{background:#0f172a;color:white;font-family:Arial;padding:40px}
    .container{max-width:1000px;margin:auto}
    .header{background:#1e293b;padding:30px;border-radius:20px;margin-bottom:20px}
    .person-card{background:#1e293b;padding:25px;border-radius:20px;margin-bottom:20px}
    .card{background:#1e293b;padding:30px;border-radius:20px;max-width:800px;margin:auto}
    p{line-height:1.5}
    button{padding:12px 20px;border:none;border-radius:10px;background:#2563eb;color:white;cursor:pointer;margin-top:10px}
    .back{background:#334155}
    </style>
    """


@app.route("/")
def home():
    return send_from_directory("frontend", "index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        new_user = User(
            request.form["name"],
            int(request.form["age"]),
            request.form["email"],
            request.form["password"],
            request.form["country"],
            request.form["bio"],
            request.form["profession"],
            request.form["looking_for"],
            [item.strip() for item in request.form["languages"].split(",")],
            [item.strip() for item in request.form["goals"].split(",")],
            [item.strip() for item in request.form["interests"].split(",")],
            [item.strip() for item in request.form["skills"].split(",")]
        )

        calculate_trust_score(new_user)
        set_user_password(new_user, request.form["password"])
        users.append(new_user)
        save_users_to_json(users)

        return redirect("/")

    return send_from_directory("frontend", "register.html")
    
    

@app.route("/login", methods=["POST"])
def login():
    email = request.form["email"].strip().lower()
    password = request.form["password"]

    locked, minutes_left = is_login_temporarily_locked(email)
    if locked:
        return f"Слишком много неправильных попыток входа. Попробуйте через {minutes_left} мин."

    user = find_user_by_email(email)

    if user is None or not verify_user_password(user, password):
        register_failed_login_attempt(email)
        return "Wrong email or password"

    clear_login_attempts(email)
    session["user_email"] = user.email
    return redirect(f"/dashboard/{user.email}")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


@app.route("/dashboard/<email>")
@login_required
def dashboard(email):
    user = find_user_by_email(email)
    notifications_count = len(get_notifications(email))
    translations = get_translations(
    request.headers.get("Accept-Language")
)
    if user is None:
        return "User not found"

    feed_data = load_feed()
    posts = feed_data.get("posts", [])

    posts_html = ""


    if posts:
        for post in reversed(posts):
            author = find_user_by_email(post.get("email"))
            author_name = author.name if author else "Unknown user"

            post_id = post.get("id")
            likes_count = len(post.get("likes", []))
            comments_count = len(post.get("comments", []))
            shares_count = len(post.get("shares", []))
            saves_count = len(post.get("saves", []))
            media_html = ""
            location_html = ""
            if post.get("location"):
                location_html = f"""
                <div style="display:inline-flex;align-items:center;gap:6px;background:#1e293b;color:#cbd5e1;padding:8px 12px;border-radius:999px;margin:0 8px 12px 0;font-size:14px;font-weight:bold;">
                    📍 {safe_text(post.get("location"))}
                </div>
                """

            hashtags_html = ""
            hashtags = post.get("hashtags", [])
            if hashtags:
                hashtags_html += '<div style="display:flex;gap:8px;flex-wrap:wrap;margin:0 0 14px 0;">'
                for tag in hashtags:
                    clean_tag = safe_text(tag)
                    hashtags_html += f'<a href="/hashtag/{user.email}/{clean_tag}" style="background:#172554;color:#93c5fd;text-decoration:none;padding:7px 11px;border-radius:999px;font-size:14px;font-weight:bold;">#{clean_tag}</a>'
                hashtags_html += '</div>'
            media_items = post.get("media_items", [])

            if not media_items and post.get("media_url"):
                media_items = [{"url": post.get("media_url", ""), "type": post.get("media_type", "")}]

            if media_items:
                grid_style = "display:grid;grid-template-columns:1fr;gap:10px;margin-top:14px;"
                if len(media_items) == 2:
                    grid_style = "display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:14px;"
                elif len(media_items) >= 3:
                    grid_style = "display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:14px;"

                media_html += f'<div class="post-media-grid" style="{grid_style}">'

                for item in media_items[:10]:
                    item_url = item.get("url", "")
                    item_type = item.get("type", "")

                    if item_type == "image":
                        media_html += f"""
                        <img src="{item_url}" style="width:100%;height:100%;max-height:520px;min-height:240px;object-fit:cover;border-radius:18px;background:#0f172a;">
                        """
                    elif item_type == "video":
                        media_html += f"""
                        <div style="position:relative;border-radius:18px;overflow:hidden;background:#000;">
                            <video class="feed-auto-video" muted playsinline preload="metadata" onclick="toggleFeedVideo(this)" style="width:100%;height:100%;max-height:520px;min-height:240px;object-fit:cover;border-radius:18px;background:#000;display:block;cursor:pointer;">
                                <source src="{item_url}">
                            </video>
                            <button type="button" onclick="toggleFeedSound(event, this)" style="position:absolute;right:12px;bottom:12px;background:rgba(15,23,42,0.75);color:white;border:none;border-radius:999px;width:42px;height:42px;cursor:pointer;font-size:18px;">🔇</button>
                            <div class="feed-video-status" style="position:absolute;left:12px;bottom:12px;background:rgba(15,23,42,0.65);color:white;border-radius:999px;padding:8px 12px;font-size:13px;font-weight:bold;">Автовидео</div>
                        </div>
                        """
                    elif item_type == "audio":
                        media_html += f"""
                        <div style="background:#111827;border:1px solid #334155;border-radius:18px;padding:18px;min-height:120px;display:flex;flex-direction:column;justify-content:center;gap:10px;">
                            <div style="font-weight:bold;color:white;font-size:16px;">🎵 Аудио / музыка</div>
                            <audio controls style="width:100%;">
                                <source src="{item_url}">
                            </audio>
                        </div>
                        """

                media_html += "</div>"
            posts_html += f"""
            <div style="background:#0f172a;padding:22px;border-radius:24px;margin-top:20px;">

                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;">
                    <strong style="font-size:18px;">👤 {author_name}</strong>
                    <span style="color:#94a3b8;font-size:14px;">{post.get("date", "")}</span>
                </div>

                <div style="display:inline-block;background:#1e293b;color:#60a5fa;padding:8px 13px;border-radius:14px;margin-bottom:14px;font-weight:bold;">
                    {post.get("type", "Публикация")}
                </div>

                <p style="font-size:17px;line-height:1.5;margin-bottom:14px;">
                    {post.get("text", "")}
                </p>
                {location_html}
                {hashtags_html}
                {media_html}
                <div style="display:flex;gap:18px;border-top:1px solid #334155;padding-top:14px;margin-top:14px;align-items:center;">
                    <a href="/like_post/{user.email}/{post_id}" style="color:white;text-decoration:none;font-size:18px;">❤️ {likes_count}</a>
                    <button type="button" onclick="toggleCommentBox('{post_id}')" style="background:none;border:none;color:white;font-size:18px;cursor:pointer;padding:0;">
                        💬 {comments_count}
                    </button>
                    <a href="/share_post/{user.email}/{post_id}" style="color:white;text-decoration:none;font-size:18px;">📤 {shares_count}</a>
                    <a href="/save_post/{user.email}/{post_id}" style="color:white;text-decoration:none;font-size:18px;">🔖 {saves_count}</a>
                </div>
                <div id="comment-box-{post_id}" style="display:none;margin-top:14px;background:#1e293b;padding:14px;border-radius:18px;">
                    <div style="margin-bottom:12px;max-height:260px;overflow-y:auto;">
                        {''.join([f'<div style="background:#0f172a;padding:10px 12px;border-radius:14px;margin-top:8px;"><b>{comment.get("author_name", "User")}</b>: {comment.get("text", "")}</div>' for comment in post.get("comments", [])]) if post.get("comments", []) else '<div style="color:#94a3b8;margin-bottom:8px;">Комментариев пока нет.</div>'}
                    </div>

                    <form method="POST" action="/comment_post/{user.email}/{post_id}" style="display:flex;gap:10px;align-items:flex-start;">
                        {csrf_input()}
                        <textarea name="comment" required placeholder="Написать комментарий..." style="flex:1;height:54px;padding:12px;border:none;border-radius:14px;background:#0f172a;color:white;resize:none;outline:none;"></textarea>
                        <button type="submit" style="background:#2563eb;color:white;border:none;border-radius:14px;padding:13px 16px;font-weight:bold;cursor:pointer;">
                            Отправить
                        </button>
                    </form>
                </div>
            </div>
            """
    else:
        posts_html = """
        <div style="background:#0f172a;padding:20px;border-radius:20px;margin-top:18px;">
            <h3>Будущая публикация</h3>
            <p>Здесь будут фото, видео, идеи, проекты и Proof Profile материалы пользователей.</p>
        </div>
        """

    inline_comment_script = """
    <script>
    function toggleCommentBox(postId) {
        const box = document.getElementById('comment-box-' + postId);
        if (!box) return;

        if (box.style.display === 'none' || box.style.display === '') {
            box.style.display = 'block';
            const input = box.querySelector('textarea');
            if (input) input.focus();
        } else {
            box.style.display = 'none';
        }
    }

    function pauseAllFeedVideos(exceptVideo) {
        document.querySelectorAll('.feed-auto-video').forEach(function(video) {
            if (video !== exceptVideo) {
                video.pause();
                video.dataset.userPaused = 'false';
                const status = video.parentElement.querySelector('.feed-video-status');
                if (status) status.innerText = 'Пауза';
            }
        });
    }

    function playFeedVideo(video) {
        if (!video) return;
        pauseAllFeedVideos(video);
        video.play().then(function() {
            const status = video.parentElement.querySelector('.feed-video-status');
            if (status) status.innerText = 'Идёт видео';
        }).catch(function() {
            const status = video.parentElement.querySelector('.feed-video-status');
            if (status) status.innerText = 'Нажмите ▶';
        });
    }

    function toggleFeedVideo(video) {
        if (!video) return;

        if (video.paused) {
            video.dataset.userPaused = 'false';
            playFeedVideo(video);
        } else {
            video.dataset.userPaused = 'true';
            video.pause();
            const status = video.parentElement.querySelector('.feed-video-status');
            if (status) status.innerText = 'Пауза';
        }
    }

    function toggleFeedSound(event, button) {
        event.stopPropagation();
        const box = button.closest('div');
        const video = box ? box.querySelector('.feed-auto-video') : null;
        if (!video) return;

        video.muted = !video.muted;
        button.innerText = video.muted ? '🔇' : '🔊';
    }

    function setupFeedVideoAutoplay() {
        const videos = document.querySelectorAll('.feed-auto-video');
        if (!videos.length) return;

        const observer = new IntersectionObserver(function(entries) {
            entries.forEach(function(entry) {
                const video = entry.target;
                const status = video.parentElement.querySelector('.feed-video-status');

                if (entry.isIntersecting && entry.intersectionRatio >= 0.65) {
                    if (video.dataset.userPaused !== 'true') {
                        playFeedVideo(video);
                    }
                } else {
                    video.pause();
                    if (status) status.innerText = 'Пауза';
                }
            });
        }, { threshold: [0, 0.35, 0.65, 1] });

        videos.forEach(function(video) {
            video.dataset.userPaused = 'false';
            observer.observe(video);
        });
    }

    document.addEventListener('DOMContentLoaded', setupFeedVideoAutoplay);
    </script>
    """

    posts_html += inline_comment_script
    html = open_html("dashboard.html")
    life_radar = generate_life_radar(user)
    notifications_count=notifications_count
    return render_template_string(
        html,
        name=user.name,
        email=user.email,
        trust_score=user.trust_score,
        posts=posts_html,
        life_radar=life_radar,
        translations=translations,
        avatar_url=get_avatar_url(user.email),
        notifications_count=notifications_count,
        friends_count=count_friends(user.email),
        followers_count=count_followers(user.email),
        following_count=count_following(user.email),
        csrf_token_input=csrf_input()
    ) 
  
@app.route("/block_user/<viewer_email>/<profile_email>")
@login_required
def block_user_route(viewer_email, profile_email):
    viewer = find_user_by_email(viewer_email)
    profile_user = find_user_by_email(profile_email)

    if viewer is None or profile_user is None:
        return "User not found"

    block_user_account(viewer.email, profile_user.email)
    return redirect(f"/blocked/{viewer.email}")


@app.route("/unblock_user/<viewer_email>/<profile_email>")
@login_required
def unblock_user_route(viewer_email, profile_email):
    viewer = find_user_by_email(viewer_email)
    profile_user = find_user_by_email(profile_email)

    if viewer is None or profile_user is None:
        return "User not found"

    unblock_user_account(viewer.email, profile_user.email)
    return redirect(f"/blocked/{viewer.email}")


@app.route("/blocked/<email>")
@login_required
def blocked_users_page(email):
    user = find_user_by_email(email)

    if user is None:
        return "User not found"

    blocked_html = ""

    for blocked_email in get_blocked_users(user.email):
        blocked_user_obj = find_user_by_email(blocked_email)
        if blocked_user_obj is None:
            continue

        blocked_html += f"""
        <div style="background:#1e293b;padding:18px;border-radius:22px;margin-bottom:14px;display:flex;align-items:center;gap:16px;box-shadow:0 12px 28px rgba(0,0,0,0.18);">
            <img src="{get_avatar_url(blocked_user_obj.email)}" style="width:62px;height:62px;border-radius:50%;object-fit:cover;background:#334155;border:3px solid #334155;">
            <div style="flex:1;min-width:0;">
                <div style="font-size:18px;font-weight:bold;margin-bottom:4px;">{safe_text(blocked_user_obj.name)}</div>
                <div style="color:#94a3b8;font-size:14px;">{safe_text(blocked_user_obj.email)}</div>
            </div>
            <a href="/unblock_user/{user.email}/{blocked_user_obj.email}" style="background:#16a34a;color:white;text-decoration:none;padding:10px 14px;border-radius:13px;font-weight:bold;">Разблокировать</a>
        </div>
        """

    if blocked_html == "":
        blocked_html = """
        <div style="background:#1e293b;padding:28px;border-radius:24px;color:#cbd5e1;text-align:center;">
            Чёрный список пуст.
        </div>
        """

    return f"""
    <!DOCTYPE html>
    <html lang="ru">
    <head><meta charset="UTF-8"><title>Engellenenler</title></head>
    <body style="margin:0;background:#0f172a;color:white;font-family:Arial,sans-serif;padding:32px;">
        <div style="max-width:900px;margin:auto;">
            <a href="/settings/{user.email}" style="display:inline-block;color:white;text-decoration:none;background:#334155;padding:12px 16px;border-radius:14px;margin-bottom:18px;font-weight:bold;">← Ayarlar</a>
            <div style="background:linear-gradient(135deg,#1e293b,#172554);padding:30px;border-radius:28px;margin-bottom:22px;box-shadow:0 18px 45px rgba(0,0,0,0.24);">
                <h1 style="margin:0 0 8px 0;">🚫 Engellenenler</h1>
                <p style="color:#cbd5e1;margin:0;">Здесь находятся пользователи, которых вы заблокировали.</p>
            </div>
            {blocked_html}
        </div>
    </body>
    </html>
    """


@app.route("/quick_avatar/<email>", methods=["POST"])
@login_required
def quick_avatar(email):
    validate_csrf_token()
    user = find_user_by_email(email)

    if user is None:
        return "User not found"

    file = request.files.get("avatar")

    if not file or not file.filename:
        return redirect(f"/dashboard/{email}")

    if not allowed_file(file.filename):
        return "Unsupported avatar file type"
    
    if not allowed_mime_type(file):
        return "Invalid file content"

    extension = file.filename.rsplit(".", 1)[1].lower()
    filename = avatar_filename(email, extension)

    safe_email = secure_filename(email.replace("@", "_at_").replace(".", "_"))

    for old_ext in ALLOWED_EXTENSIONS:
        old_path = f"{UPLOAD_FOLDER}/{safe_email}.{old_ext}"
        if os.path.exists(old_path):
            os.remove(old_path)

    file.save(f"{UPLOAD_FOLDER}/{filename}")

    return redirect(f"/dashboard/{email}")


@app.route("/hashtag/<email>/<tag>")
@login_required
def hashtag_page(email, tag):
    user = find_user_by_email(email)

    if user is None:
        return "User not found"

    feed_data = load_feed()
    posts = feed_data.get("posts", [])
    tag_lower = tag.lower()
    results_html = ""

    for post in reversed(posts):
        post_tags = [str(item).lower() for item in post.get("hashtags", [])]
        if tag_lower not in post_tags:
            continue

        author = find_user_by_email(post.get("email"))
        author_name = author.name if author else "Unknown user"

        results_html += f"""
        <div style="background:#1e293b;padding:20px;border-radius:22px;margin-bottom:16px;">
            <div style="display:flex;justify-content:space-between;gap:12px;margin-bottom:10px;">
                <strong>👤 {safe_text(author_name)}</strong>
                <span style="color:#94a3b8;font-size:14px;">{safe_text(post.get("date", ""))}</span>
            </div>
            <div style="color:#60a5fa;font-weight:bold;margin-bottom:8px;">#{safe_text(tag)}</div>
            <p style="line-height:1.5;">{safe_text(post.get("text", ""))}</p>
        </div>
        """

    if results_html == "":
        results_html = f"""
        <div style="background:#1e293b;padding:24px;border-radius:22px;color:#cbd5e1;">
            По хэштегу #{safe_text(tag)} пока нет публикаций.
        </div>
        """

    return f"""
    <html>
    <head><meta charset="UTF-8"><title>#{safe_text(tag)}</title></head>
    <body style="margin:0;background:#0f172a;color:white;font-family:Arial,sans-serif;padding:32px;">
        <div style="max-width:860px;margin:auto;">
            <a href="/dashboard/{email}" style="display:inline-block;color:white;text-decoration:none;background:#334155;padding:12px 16px;border-radius:14px;margin-bottom:18px;font-weight:bold;">← Назад</a>
            <div style="background:#1e293b;padding:28px;border-radius:26px;margin-bottom:20px;">
                <h1 style="margin:0;"># {safe_text(tag)}</h1>
                <p style="color:#cbd5e1;margin-bottom:0;">Публикации по выбранному хэштегу.</p>
            </div>
            {results_html}
        </div>
    </body>
    </html>
    """


@app.route("/create_post/<email>", methods=["POST"])
@login_required
def create_post(email):
    validate_csrf_token()
    user = find_user_by_email(email)

    if user is None:
        return "User not found"

    post_type = request.form.get("type", "").strip()
    text = request.form.get("text", "").strip()
    location = request.form.get("location", "").strip()
    hashtags_raw = request.form.get("hashtags", "").strip()

    hashtags = []
    if hashtags_raw:
        hashtags = [
            tag.strip().replace("#", "")
            for tag in hashtags_raw.split()
            if tag.strip()
        ]

    media_url = ""
    media_type = ""
    media_items = []

    files = request.files.getlist("media")

    image_ext = ["jpg", "jpeg", "png", "webp", "gif"]
    video_ext = ["mp4", "mov", "webm", "m4v"]
    audio_ext = ["mp3", "wav", "m4a", "ogg", "webm"]

    for file in files[:10]:
        if not file or not file.filename:
            continue

        filename = secure_filename(file.filename)
        if not allowed_mime_type(file):
            continue
        ext = filename.rsplit(".", 1)[-1].lower()

        current_type = ""
        if ext in image_ext:
            current_type = "image"
        elif ext in video_ext:
            current_type = "video"
        elif ext in audio_ext:
            current_type = "audio"
        else:
            continue

        safe_email = user.email.replace("@", "_").replace(".", "_")
        new_filename = f"post_{safe_email}_{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{filename}"

        upload_path = os.path.join(UPLOAD_FOLDER, new_filename)
        file.save(upload_path)

        current_url = f"/static/uploads/{new_filename}"
        media_items.append({"url": current_url, "type": current_type, "name": filename})

    if media_items:
        media_url = media_items[0].get("url", "")
        media_type = media_items[0].get("type", "")

    feed_data = load_feed()
    posts = feed_data.get("posts", [])

    new_id = 1
    if posts:
        new_id = max(post.get("id", 0) for post in posts) + 1

    posts.append({
        "id": new_id,
        "email": user.email,
        "name": user.name,
        "type": post_type,
        "text": text,
        "location": location,
        "hashtags": hashtags,
        "media_url": media_url,
        "media_type": media_type,
        "media_items": media_items,
        "date": datetime.now().strftime("%d.%m.%Y %H:%M"),
        "likes": [],
        "comments": [],
        "shares": [],
        "saves": []
    })

    feed_data["posts"] = posts
    save_feed(feed_data)

    return redirect(f"/dashboard/{user.email}")

@app.route("/create_story/<email>", methods=["POST"])
@login_required
def create_story(email):
    validate_csrf_token()
    user = find_user_by_email(email)

    if user is None:
        return "User not found"

    file = request.files.get("story_media")

    if not file or not file.filename:
        return redirect(f"/dashboard/{email}")

    filename = secure_filename(file.filename)
    ext = filename.rsplit(".", 1)[-1].lower()
    if not allowed_mime_type(file):
        return "Invalid file content"

    image_ext = ["jpg", "jpeg", "png", "webp", "gif"]
    video_ext = ["mp4", "mov", "webm", "m4v"]
    audio_ext = ["mp3", "wav", "m4a", "ogg", "webm"]

    if ext in image_ext:
        media_type = "image"
    elif ext in video_ext:
        media_type = "video"
    elif ext in audio_ext:
        media_type = "audio"
    else:
        return "Unsupported story file type"

    safe_email = user.email.replace("@", "_").replace(".", "_")
    new_filename = f"story_{safe_email}_{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{filename}"
    upload_path = os.path.join(UPLOAD_FOLDER, new_filename)
    file.save(upload_path)

    stories_data = load_stories()
    stories = stories_data.get("stories", [])

    new_id = 1
    if stories:
        new_id = max(story.get("id", 0) for story in stories) + 1

    stories.append({
        "id": new_id,
        "email": user.email,
        "name": user.name,
        "media_url": f"/static/uploads/{new_filename}",
        "media_type": media_type,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "views": []
    })

    stories_data["stories"] = stories
    save_stories(stories_data)

    return redirect(f"/dashboard/{email}")


@app.route("/story/<viewer_email>/<owner_email>")
@login_required
def view_story(viewer_email, owner_email):
    viewer = find_user_by_email(viewer_email)
    owner = find_user_by_email(owner_email)

    if viewer is None or owner is None:
        return "User not found"

    stories_data = load_stories()
    stories = [story for story in stories_data.get("stories", []) if story.get("email") == owner_email and is_story_active(story)]

    if not stories:
        return redirect(f"/dashboard/{viewer_email}")

    story = stories[-1]

    if viewer_email not in story.get("views", []):
        story["views"].append(viewer_email)
        save_stories(stories_data)

    media_html = ""
    if story.get("media_type") == "image":
        media_html = f'<img src="{story.get("media_url")}" style="max-width:100%;max-height:78vh;border-radius:26px;object-fit:contain;">'
    elif story.get("media_type") == "video":
        media_html = f'<video src="{story.get("media_url")}" controls autoplay playsinline style="max-width:100%;max-height:78vh;border-radius:26px;background:#000;"></video>'
    elif story.get("media_type") == "audio":
        media_html = f'''
        <div style="height:68vh;border-radius:26px;background:linear-gradient(135deg,#111827,#1e293b);display:flex;flex-direction:column;align-items:center;justify-content:center;padding:28px;box-sizing:border-box;">
            <div style="font-size:64px;margin-bottom:18px;">🎵</div>
            <div style="font-size:22px;font-weight:bold;margin-bottom:18px;">Аудио Story</div>
            <audio src="{story.get("media_url")}" controls autoplay style="width:100%;max-width:420px;"></audio>
        </div>
        '''

    return f"""
    <html>
    <head><meta charset="UTF-8"><title>Story</title></head>
    <body style="margin:0;background:#020617;color:white;font-family:Arial,sans-serif;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:24px;box-sizing:border-box;">
        <div style="width:100%;max-width:520px;">
            <div style="display:flex;align-items:center;gap:12px;margin-bottom:16px;">
                <a href="/dashboard/{viewer_email}" style="background:#334155;color:white;text-decoration:none;padding:10px 13px;border-radius:14px;font-weight:bold;">←</a>
                <img src="{get_avatar_url(owner_email)}" style="width:46px;height:46px;border-radius:50%;object-fit:cover;background:#334155;">
                <div>
                    <div style="font-weight:bold;">{safe_text(owner.name)}</div>
                    <div style="color:#94a3b8;font-size:13px;">История · 24 часа</div>
                </div>
            </div>
            <div style="background:#0f172a;border-radius:30px;padding:12px;text-align:center;box-shadow:0 20px 50px rgba(0,0,0,0.35);">
                {media_html}
            </div>
            <div style="color:#94a3b8;margin-top:12px;text-align:center;font-size:13px;">Просмотры: {len(story.get("views", []))}</div>
        </div>
    </body>
    </html>
    """


@app.route("/comment_post/<email>/<int:post_id>", methods=["POST"])
@login_required
def comment_post(email, post_id):
    validate_csrf_token()
    user = find_user_by_email(email)

    if user is None:
        return "User not found"

    comment_text = request.form["comment"]

    feed_data = load_feed()
    posts = feed_data.get("posts", [])

    for post in posts:
        if post.get("id") == post_id:
            comments = post.get("comments", [])

            comments.append({
                "author": user.email,
                "author_name": user.name,
                "text": comment_text,
                "date": datetime.now().strftime("%d.%m.%Y %H:%M")
            })

            post["comments"] = comments
            break

    feed_data["posts"] = posts
    save_feed(feed_data)

    return redirect(f"/dashboard/{user.email}")

@app.route("/like_post/<email>/<int:post_id>")
@login_required
def like_post(email, post_id):
    feed_data = load_feed()
    posts = feed_data.get("posts", [])

    for post in posts:
        if post.get("id") == post_id:
            likes = post.get("likes", [])

            if email in likes:
                likes.remove(email)
            else:
                likes.append(email)

            post["likes"] = likes
            break

    feed_data["posts"] = posts
    save_feed(feed_data)

    return redirect(f"/dashboard/{email}")

# --- Share Post routes ---
@app.route("/share_post/<email>/<int:post_id>")
@login_required
def share_post(email, post_id):
    current_user = find_user_by_email(email)

    if current_user is None:
        return "User not found"

    feed_data = load_feed()
    posts = feed_data.get("posts", [])

    selected_post = None
    for post in posts:
        if post.get("id") == post_id:
            selected_post = post
            break

    if selected_post is None:
        return "Post not found"

    friend_emails = get_friends(email)
    people_html = ""

    for friend_email in friend_emails:
        friend = find_user_by_email(friend_email)

        if friend is None:
            continue

        avatar_url = get_avatar_url(friend.email)

        people_html += f"""
        <div style="background:#1e293b;padding:16px;border-radius:20px;margin-bottom:12px;display:flex;align-items:center;gap:14px;">
            <img src="{avatar_url}" style="width:56px;height:56px;border-radius:50%;object-fit:cover;background:#334155;">

            <div style="flex:1;">
                <div style="font-weight:bold;font-size:18px;">{safe_text(friend.name)}</div>
                <div style="color:#94a3b8;font-size:14px;">{safe_text(friend.profession)}</div>
            </div>

            <a href="/send_shared_post/{email}/{post_id}/{friend.email}" style="background:#2563eb;color:white;text-decoration:none;padding:11px 15px;border-radius:14px;font-weight:bold;">
                Отправить
            </a>
        </div>
        """

    if people_html == "":
        people_html = """
        <div style="background:#1e293b;padding:24px;border-radius:20px;color:#cbd5e1;text-align:center;">
            Пока нет друзей для отправки поста.
        </div>
        """

    return f"""
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <title>Поделиться постом</title>
    </head>

    <body style="margin:0;background:#0f172a;color:white;font-family:Arial,sans-serif;padding:32px;">
        <div style="max-width:760px;margin:auto;">

            <a href="/dashboard/{email}" style="display:inline-block;color:white;text-decoration:none;background:#334155;padding:12px 16px;border-radius:14px;margin-bottom:18px;font-weight:bold;">
                ← Назад
            </a>

            <div style="background:#1e293b;padding:28px;border-radius:26px;margin-bottom:20px;">
                <h1 style="margin:0 0 8px 0;">📤 Поделиться постом</h1>
                <p style="color:#cbd5e1;margin:0;">Выберите друга, которому хотите отправить публикацию.</p>
            </div>

            <div style="background:#0f172a;padding:18px;border-radius:22px;margin-bottom:20px;border:1px solid #334155;">
                <div style="color:#60a5fa;font-weight:bold;margin-bottom:8px;">{safe_text(selected_post.get('type', 'Публикация'))}</div>
                <div style="color:#e5e7eb;line-height:1.5;">{safe_text(selected_post.get('text', ''))}</div>
            </div>

            {people_html}

        </div>
    </body>
    </html>
    """


@app.route("/send_shared_post/<email>/<int:post_id>/<receiver_email>")
@login_required
def send_shared_post(email, post_id, receiver_email):
    sender = find_user_by_email(email)
    receiver = find_user_by_email(receiver_email)

    if sender is None or receiver is None:
        return "User not found"

    feed_data = load_feed()
    posts = feed_data.get("posts", [])

    selected_post = None
    for post in posts:
        if post.get("id") == post_id:
            selected_post = post
            shares = post.get("shares", [])
            shares.append({
                "email": email,
                "to": receiver_email,
                "date": datetime.now().strftime("%d.%m.%Y %H:%M")
            })
            post["shares"] = shares
            break

    if selected_post is None:
        return "Post not found"

    feed_data["posts"] = posts
    save_feed(feed_data)

    messages = load_messages()
    messages.append({
        "from": sender.email,
        "to": receiver.email,
        "message": f"{sender.name} поделился постом: {selected_post.get('text', '')}",
        "shared_post_id": post_id,
        "time": datetime.now().strftime("%d.%m.%Y %H:%M")
    })
    save_messages(messages)

    return redirect(f"/chat/{sender.email}/{receiver.email}")


@app.route("/post_comments/<email>/<int:post_id>")
@login_required
def post_comments(email, post_id):

    user = find_user_by_email(email)

    if user is None:
        return "User not found"

    feed_data = load_feed()
    posts = feed_data.get("posts", [])

    current_post = None

    for post in posts:
        if post.get("id") == post_id:
            current_post = post
            break

    if current_post is None:
        return "Post not found"

    comments_html = ""

    for comment in current_post.get("comments", []):
        comments_html += f"""
        <div style="background:#1e293b;padding:16px;border-radius:16px;margin-bottom:12px;">
            <strong>{comment.get('author_name','User')}</strong><br>
            <span style="color:#cbd5e1;">{comment.get('text','')}</span><br>
            <small style="color:#94a3b8;">{comment.get('date','')}</small>
        </div>
        """

    return f"""
    <html>
    <head>
        <title>Комментарии</title>
    </head>

    <body style="background:#0f172a;color:white;font-family:Arial;padding:30px;max-width:900px;margin:auto;">

        <a href="/dashboard/{email}" style="color:white;">← Назад</a>

        <h1>💬 Комментарии</h1>

        <div style="background:#1e293b;padding:20px;border-radius:20px;margin-bottom:20px;">
            <h3>{current_post.get('type','Публикация')}</h3>
            <p>{current_post.get('text','')}</p>
        </div>

        <form method="POST" action="/comment_post/{email}/{post_id}">
            {csrf_input()}
            <textarea
                name="comment"
                required
                placeholder="Написать комментарий..."
                style="width:100%;height:100px;padding:12px;border-radius:12px;">
            </textarea>

            <br><br>

            <button type="submit">
                Отправить комментарий
            </button>
        </form>

        <br>

        {comments_html}

    </body>
    </html>
    """




@app.route("/save_post/<email>/<int:post_id>")
@login_required
def save_post_route(email, post_id):
    feed_data = load_feed()
    posts = feed_data.get("posts", [])

    for post in posts:
        if post.get("id") == post_id:
            saves = post.get("saves", [])

            if email in saves:
                saves.remove(email)
            else:
                saves.append(email)

            post["saves"] = saves
            break

    feed_data["posts"] = posts
    save_feed(feed_data)

    return redirect(f"/dashboard/{email}")


@app.route("/post/<email>/<int:post_id>")
@login_required
def post_page(email, post_id):
    user = find_user_by_email(email)

    if user is None:
        return "User not found"

    feed_data = load_feed()
    posts = feed_data.get("posts", [])

    selected_post = None

    for post in posts:
        if post.get("id") == post_id:
            selected_post = post
            break

    if selected_post is None:
        return "Post not found"

    author = find_user_by_email(selected_post.get("email"))
    author_name = author.name if author else "Unknown user"

    comments_html = ""

    for comment in selected_post.get("comments", []):
        comments_html += f"""
        <div style="background:#1e293b;padding:14px;border-radius:14px;margin-top:10px;">
            <strong>{comment.get("author_name", "User")}</strong>
            <p>{comment.get("text", "")}</p>
            <small style="color:#94a3b8;">{comment.get("date", "")}</small>
        </div>
        """

    if comments_html == "":
        comments_html = "<p style='color:#94a3b8;'>Пока нет комментариев.</p>"

    return f"""
    <html>
    <head>
    <meta charset="UTF-8">
    <title>Пост</title>
    <style>
    body{{background:#0f172a;color:white;font-family:Arial;padding:40px}}
    .container{{max-width:800px;margin:auto}}
    .card{{background:#0f172a;padding:24px;border-radius:24px;margin-bottom:20px}}
    .box{{background:#1e293b;padding:24px;border-radius:24px;margin-bottom:20px}}
    textarea{{width:100%;height:100px;padding:14px;border:none;border-radius:14px;background:#1e293b;color:white;resize:none}}
    button{{background:#2563eb;color:white;border:none;border-radius:14px;padding:12px 18px;font-weight:bold;margin-top:10px;cursor:pointer}}
    a{{color:white;text-decoration:none}}
    </style>
    </head>
    <body>
    <div class="container">
        <p><a href="/dashboard/{email}">← Назад</a></p>

        <div class="box">
            <h2>👤 {author_name}</h2>
            <p style="color:#60a5fa;font-weight:bold;">{selected_post.get("type", "Публикация")}</p>
            <p style="font-size:18px;line-height:1.5;">{selected_post.get("text", "")}</p>
            <small style="color:#94a3b8;">{selected_post.get("date", "")}</small>
        </div>

        <div class="box">
            <h2>💬 Комментарии</h2>

            {comments_html}

            <form method="POST" action="/comment_post/{email}/{post_id}">
                {csrf_input()}
                <textarea name="comment" placeholder="Написать комментарий..." required></textarea>
                <button type="submit">Отправить</button>
            </form>
        </div>
    </div>
    </body>
    </html>
    """


@app.route("/profile/<email>")
@profile_view_required
def profile(email):
    user = find_user_by_email(email)
    ai_profile = analyze_user_profile(user)
    if user is None:
        return "User not found"

    html = open_html("profile.html")
    viewer_email = request.args.get("viewer", email)
    return render_template_string(
        html,
        name=user.name,
        age=user.age,
        email=user.email,
        ai_summary=ai_profile["summary"],
        viewer_email=viewer_email,
        is_following_user=is_following(viewer_email, user.email),
        are_friends_user=are_friends(viewer_email, user.email),
        friend_request_sent=has_friend_request(viewer_email, user.email),
        country=user.country,
        bio=user.bio,
        profession=user.profession,
        looking_for=user.looking_for,
        languages=", ".join(user.languages),
        goals=", ".join(user.goals),
        interests=", ".join(user.interests),
        skills=", ".join(user.skills),
        trust_score=user.trust_score,
        verified="YES" if user.verified else "NO",
        friends_count=count_friends(user.email),
followers_count=count_followers(user.email),
following_count=count_following(user.email),
        avatar_url=get_avatar_url(user.email)
    )

@app.route("/settings/<email>")
@login_required
def settings_page(email):
    user = find_user_by_email(email)

    if user is None:
        return "User not found"

    html = open_html("settings.html")

    return render_template_string(
        html,
        email=user.email
    )

@app.route("/follow/<viewer_email>/<profile_email>")
@login_required
def follow_route(viewer_email, profile_email):
    if is_blocked(viewer_email, profile_email) or is_blocked(profile_email, viewer_email):
        return simple_page("🚫 Действие недоступно", "Подписка невозможна, потому что один из пользователей заблокировал другого.", viewer_email)

    if follow_user(viewer_email, profile_email):
        viewer = find_user_by_email(viewer_email)
        add_notification(
            profile_email,
            viewer_email,
            "follow",
            f"{viewer.name} подписался на вас"
        )

    return redirect(f"/profile/{profile_email}?viewer={viewer_email}")


@app.route("/unfollow/<viewer_email>/<profile_email>")
@login_required
def unfollow_route(viewer_email, profile_email):
    unfollow_user(viewer_email, profile_email)
    return redirect(f"/profile/{profile_email}?viewer={viewer_email}")


@app.route("/send_friend_request/<viewer_email>/<profile_email>")
@login_required
def send_friend_request_route(viewer_email, profile_email):
    if is_blocked(viewer_email, profile_email) or is_blocked(profile_email, viewer_email):
        return simple_page("🚫 Действие недоступно", "Заявку в друзья нельзя отправить, потому что один из пользователей заблокировал другого.", viewer_email)

    if send_friend_request(viewer_email, profile_email):
        viewer = find_user_by_email(viewer_email)
        add_notification(
            profile_email,
            viewer_email,
            "friend_request",
            f"{viewer.name} отправил вам заявку в друзья"
        )

    return redirect(f"/profile/{profile_email}?viewer={viewer_email}")


@app.route("/accept_friend_request/<viewer_email>/<profile_email>")
@login_required
def accept_friend_request_route(viewer_email, profile_email):

    if accept_friend_request(viewer_email, profile_email):

        viewer = find_user_by_email(viewer_email)

        add_notification(
            profile_email,
            viewer_email,
            "friend_accept",
            f"{viewer.name} принял вашу заявку в друзья"
        )

    return redirect(f"/profile/{profile_email}?viewer={viewer_email}")


@app.route("/matches/<email>")
@login_required
def matches(email):
    current_user = find_user_by_email(email)

    if current_user is None:
        return "User not found"

    matches_list = find_best_matches(current_user, users)
    matches_html = ""

    for match in matches_list:
        matched_user = match["user"]

        if matched_user.email.strip().lower() == current_user.email.strip().lower():
            continue

        score = match["score"]
        reasons = explain_match(current_user, matched_user)
        level = get_match_level(score)
        avatar_url = get_avatar_url(matched_user.email)

        reasons_html = ""

        for reason in reasons:
            reasons_html += f"<li>{safe_text(reason)}</li>"

        matches_html += f"""
        <div class="match-card">
            <div class="match-top">
                <img class="avatar" src="{avatar_url}" alt="Avatar">

                <div class="match-info">
                    <h2>{safe_text(matched_user.name)}</h2>
                    <p>{safe_text(matched_user.profession)}</p>
                    <p class="country">{safe_text(matched_user.country)}</p>
                </div>

                <div class="score-box">
                    <div class="score">{score}%</div>
                    <div class="level">{safe_text(level)}</div>
                </div>
            </div>

            <div class="details">
                <p><b>Ищет:</b> {safe_text(matched_user.looking_for)}</p>
                <p><b>Цели:</b> {safe_text(", ".join(matched_user.goals))}</p>
                <p><b>Интересы:</b> {safe_text(", ".join(matched_user.interests))}</p>
                <p><b>Навыки:</b> {safe_text(", ".join(matched_user.skills))}</p>
            </div>

            <div class="reasons">
                <h3>Почему AI рекомендует этого человека:</h3>
                <ul>{reasons_html}</ul>
            </div>

            <div class="actions">
                <a href="/profile/{matched_user.email}?viewer={current_user.email}">Открыть профиль</a>
                <a href="/chat/{current_user.email}/{matched_user.email}" class="message">Написать</a>
            </div>
        </div>
        """

    if matches_html == "":
        matches_html = """
        <div class="empty-card">
            Пока нет подходящих AI Matches. Заполните профиль, цели, интересы и навыки.
        </div>
        """

    html = open_html("matches.html")

    return render_template_string(
        html,
        name=current_user.name,
        email=current_user.email,
        matches=matches_html
    )

@app.route("/search/<email>", methods=["GET", "POST"])
@login_required
def search_page(email):
    current_user = find_user_by_email(email)
    if current_user is None:
        return "User not found"

    results_html = ""

    if request.method == "POST":
        validate_csrf_token()
        keyword = request.form["keyword"].strip().lower()

        for user in users:
            if user.email.strip().lower() == current_user.email.strip().lower():
                continue

            privacy = get_user_privacy(user.email)

            if privacy.get("show_in_search") == False:
                continue

            if privacy.get("vip_mode") == True:
                continue

            searchable_text = (
                str(user.name) + " " +
                str(user.country) + " " +
                str(user.bio) + " " +
                str(user.profession) + " " +
                str(user.looking_for) + " " +
                " ".join(user.languages) + " " +
                " ".join(user.goals) + " " +
                " ".join(user.interests) + " " +
                " ".join(user.skills)
            ).lower()

            if keyword in searchable_text:
                results_html += user_card(user)

        if results_html == "":
            results_html = "<div class='card'><p>Ничего не найдено.</p></div>"

    html = open_html("search.html")

    return render_template_string(
        html,
        email=current_user.email,
        results=results_html,
        csrf_token_input=csrf_input()
    )





def simple_page(title, text, email):
    return f"""
    <html>
    <head>
    <meta charset="UTF-8">
    <title>{title}</title>
    {page_style()}
    </head>
    <body>
    <div class="card">
        <h1>{title}</h1>
        <p>{text}</p>
        <button onclick="window.location.href='/dashboard/{email}'">Назад в Dashboard</button>
    </div>
    </body>
    </html>
    """


@app.route("/media/<email>", methods=["GET", "POST"])
@login_required
def media_page(email):
    user = find_user_by_email(email)
    if user is None:
        return "User not found"

    message = ""

    if request.method == "POST":
        validate_csrf_token()
        file = request.files.get("avatar")

        if file and allowed_file(file.filename):
            extension = file.filename.rsplit(".", 1)[1].lower()
            filename = avatar_filename(email, extension)

            safe_email = secure_filename(email.replace("@", "_at_").replace(".", "_"))

            for ext in ALLOWED_EXTENSIONS:
                old_path = f"{UPLOAD_FOLDER}/{safe_email}.{ext}"
                if os.path.exists(old_path):
                    os.remove(old_path)

            file.save(f"{UPLOAD_FOLDER}/{filename}")
            message = "Аватар успешно загружен."
        else:
            message = "Ошибка: выбери файл PNG, JPG, JPEG, GIF или WEBP."

    avatar_url = get_avatar_url(user.email)

    return f"""
    <html>
    <head>
    <meta charset="UTF-8">
    <title>Аватар и медиа</title>
    <style>
    body{{background:#0f172a;color:white;font-family:Arial;padding:40px}}
    .card{{background:#1e293b;padding:30px;border-radius:20px;max-width:600px;margin:auto;text-align:center}}
    img{{width:220px;height:220px;border-radius:50%;object-fit:cover;border:4px solid #334155;margin-bottom:25px}}
    input{{margin:20px 0}}
    button{{width:100%;padding:12px;border:none;border-radius:10px;background:#2563eb;color:white;cursor:pointer;margin-top:10px}}
    .back{{background:#334155}}
    .msg{{color:#22c55e}}
    </style>
    </head>
    <body>
    <div class="card">
        <h1>📸 Аватар и медиа</h1>
        <p>{user.name}</p>

        <img src="{avatar_url}" alt="Avatar">

        <p class="msg">{message}</p>

        <form method="POST" enctype="multipart/form-data">
            {csrf_input()}
            <input type="file" name="avatar" accept="image/*" required>
            <button type="submit">Загрузить аватар</button>
        </form>

        <button class="back" onclick="window.location.href='/dashboard/{email}'">Назад в Dashboard</button>
    </div>
    </body>
    </html>
    """


@app.route("/feed/<email>")
@login_required
def feed_page(email):
    return simple_page("📰 Лента", "Здесь будет лента фото, видео, идей и проектов.", email)


@app.route("/messages/<email>")
@login_required
def messages_page(email):
    current_user = find_user_by_email(email)

    if current_user is None:
        return "User not found"

    messages = load_messages()
    dialogs = {}
    unread_counts = {}

    for msg in messages:
        sender = msg.get("from")
        receiver = msg.get("to")

        if sender == current_user.email:
            other_email = receiver
        elif receiver == current_user.email:
            other_email = sender
            if msg.get("status") != "read":
                unread_counts[other_email] = unread_counts.get(other_email, 0) + 1
        else:
            continue

        dialogs[other_email] = msg

    dialogs_html = ""

    if dialogs:
        for other_email, last_msg in dialogs.items():
            other_user = find_user_by_email(other_email)

            if other_user is None:
                continue

            avatar_url = get_avatar_url(other_user.email)
            unread_count = unread_counts.get(other_user.email, 0)
            unread_badge = ""
            if unread_count > 0:
                unread_badge = f"""
                <div style="min-width:28px;height:28px;border-radius:999px;background:#ef4444;color:white;display:flex;align-items:center;justify-content:center;font-weight:bold;font-size:13px;box-shadow:0 0 0 6px rgba(239,68,68,0.14);">
                    {unread_count}
                </div>
                """

            dialogs_html += f"""
            <div style="background:#1e293b;padding:18px;border-radius:22px;margin-bottom:14px;display:flex;align-items:center;gap:16px;">
                <img src="{avatar_url}" style="width:66px;height:66px;border-radius:50%;object-fit:cover;background:#334155;border:3px solid #334155;">

                <div style="flex:1;">
                    <h3 style="margin:0 0 6px 0;font-size:20px;">{safe_text(other_user.name)}</h3>
                    <p style="margin:0 0 6px 0;color:#cbd5e1;">{safe_text(other_user.profession)}</p>
                    <p style="margin:0;color:#94a3b8;font-size:14px;">{safe_text(last_msg.get("message"))}</p>
                </div>

                {unread_badge}

                <a href="/chat/{current_user.email}/{other_user.email}" style="background:#2563eb;color:white;text-decoration:none;padding:12px 16px;border-radius:14px;font-weight:bold;">
                    Открыть чат
                </a>
            </div>
            """
    else:
        dialogs_html = """
        <div style="background:#1e293b;padding:24px;border-radius:22px;color:#cbd5e1;text-align:center;">
            Пока нет активных диалогов.
        </div>
        """

    users_html = ""

    for user in users:
        if user.email.strip().lower() == current_user.email.strip().lower():
            continue
        if is_blocked(current_user.email, user.email) or is_blocked(user.email, current_user.email):
            continue

        avatar_url = get_avatar_url(user.email)

        users_html += f"""
        <div style="background:#1e293b;padding:18px;border-radius:22px;margin-bottom:14px;display:flex;align-items:center;gap:16px;">
            <img src="{avatar_url}" style="width:58px;height:58px;border-radius:50%;object-fit:cover;background:#334155;border:3px solid #334155;">

            <div style="flex:1;">
                <h3 style="margin:0 0 6px 0;font-size:18px;">{safe_text(user.name)}</h3>
                <p style="margin:0;color:#cbd5e1;">{safe_text(user.profession)}</p>
            </div>

            <a href="/chat/{current_user.email}/{user.email}" style="background:#16a34a;color:white;text-decoration:none;padding:10px 14px;border-radius:14px;font-weight:bold;">
                Написать
            </a>
        </div>
        """

    return f"""
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <title>Сообщения - AI Match Life</title>
    </head>

    <body style="margin:0;background:#0f172a;color:white;font-family:Arial,sans-serif;padding:32px;">
        <div style="max-width:920px;margin:auto;">

            <a href="/dashboard/{current_user.email}" style="display:inline-block;color:white;text-decoration:none;background:#334155;padding:12px 16px;border-radius:14px;margin-bottom:18px;font-weight:bold;">
                ← Назад
            </a>

            <div style="background:#1e293b;padding:28px;border-radius:26px;margin-bottom:22px;">
                <h1 style="margin:0;">💬 Сообщения</h1>
                <p style="color:#cbd5e1;margin-bottom:0;">Активные диалоги и новые контакты.</p>
            </div>

            <h2>Активные диалоги</h2>
            {dialogs_html}

            <h2 style="margin-top:30px;">Новая переписка</h2>
            {users_html}

        </div>
    </body>
    </html>
    """
def add_call_history_message(sender_email, receiver_email, call_type):
    messages = load_messages()

    next_id = 1
    if messages:
        next_id = max(int(msg.get("id", 0)) for msg in messages) + 1

    title = "📹 Видеозвонок" if call_type == "video" else "📞 Аудиозвонок"

    messages.append({
        "id": next_id,
        "from": sender_email,
        "to": receiver_email,
        "message": title,
        "media_url": "",
        "media_type": "call",
        "call_type": call_type,
        "time": datetime.now().strftime("%d.%m.%Y %H:%M"),
        "status": "sent"
    })

    save_messages(messages)


@app.route("/audio_call/<sender_email>/<receiver_email>")
@login_required
def audio_call_page(sender_email, receiver_email):
    sender = find_user_by_email(sender_email)
    receiver = find_user_by_email(receiver_email)

    if sender is None or receiver is None:
        return "User not found"

    if is_blocked(receiver.email, sender.email) or is_blocked(sender.email, receiver.email):
        return simple_page(
            "🚫 Звонок недоступен",
            "Звонок невозможен, потому что один из пользователей заблокировал другого.",
            sender.email
        )

    return render_call_page(sender, receiver, "audio")


@app.route("/video_call/<sender_email>/<receiver_email>")
@login_required
def video_call_page(sender_email, receiver_email):
    sender = find_user_by_email(sender_email)
    receiver = find_user_by_email(receiver_email)

    if sender is None or receiver is None:
        return "User not found"

    if is_blocked(receiver.email, sender.email) or is_blocked(sender.email, receiver.email):
        return simple_page(
            "🚫 Звонок недоступен",
            "Звонок невозможен, потому что один из пользователей заблокировал другого.",
            sender.email
        )

    return render_call_page(sender, receiver, "video")


def render_call_page(sender, receiver, call_type):
    is_video = call_type == "video"
    title = "Видеозвонок" if is_video else "Аудиозвонок"
    icon = "🎥" if is_video else "📞"
    receiver_avatar = get_avatar_url(receiver.email)

    if is_video:
        main_area = f"""
        <div class="video-grid">
            <video id="localVideo" autoplay playsinline muted></video>
            <div class="remote-placeholder">
                <div class="remote-avatar-wrap">
                    <img src="{receiver_avatar}" alt="Receiver">
                </div>
                <h2>{safe_text(receiver.name)}</h2>
                <p>Ожидание соединения...</p>
            </div>
        </div>
        """
        camera_button = '<button type="button" id="cameraBtn" class="call-control" onclick="toggleCamera()" title="Камера"><span class="control-icon">🎥</span></button>'
        flip_button = '<button type="button" id="flipBtn" class="call-control" onclick="flipCamera()" title="Перевернуть камеру"><span class="control-icon">🔄</span></button>'
        need_video = "true"
    else:
        main_area = f"""
        <div class="audio-card">
            <div class="call-avatar-ring">
                <img src="{receiver_avatar}" alt="Receiver">
            </div>
            <h2>{safe_text(receiver.name)}</h2>
            <p id="callStatus">Звонок...</p>
        </div>
        """
        camera_button = ""
        flip_button = ""
        need_video = "false"

    speaker_button = '<button type="button" id="speakerBtn" class="call-control" onclick="toggleSpeaker()" title="Динамик"><span class="control-icon" id="speakerIcon">🔊</span></button>'

    return f"""
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{title}</title>
        <style>
            *{{box-sizing:border-box}}
            body{{margin:0;background:#020617;color:white;font-family:Arial,sans-serif;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:24px;}}
            .call-shell{{width:100%;max-width:980px;background:linear-gradient(135deg,#1e293b,#111827);border-radius:32px;padding:28px;box-shadow:0 24px 70px rgba(0,0,0,0.38);border:1px solid rgba(148,163,184,0.12);}}
            .call-top{{display:flex;align-items:center;justify-content:space-between;gap:16px;margin-bottom:22px;}}
            .call-top h1{{margin:0;font-size:30px;}}
            .call-top p{{margin:6px 0 0;color:#cbd5e1;}}
            .back-link{{background:#334155;color:white;text-decoration:none;padding:12px 16px;border-radius:14px;font-weight:bold;}}
            .video-grid{{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-bottom:24px;}}
            video{{width:100%;height:420px;background:#0f172a;border-radius:26px;object-fit:cover;border:1px solid rgba(148,163,184,0.12);}}
            .remote-placeholder{{height:420px;background:#0f172a;border-radius:26px;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;border:1px solid rgba(148,163,184,0.12);}}
            .remote-avatar-wrap{{width:128px;height:128px;border-radius:50%;padding:4px;background:linear-gradient(135deg,#2563eb,#8b5cf6,#ec4899,#f59e0b);margin-bottom:16px;}}
            .remote-avatar-wrap img{{width:100%;height:100%;border-radius:50%;object-fit:cover;border:4px solid #0f172a;}}
            .audio-card{{background:#0f172a;border-radius:30px;min-height:430px;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;border:1px solid rgba(148,163,184,0.12);margin-bottom:24px;}}
            .call-avatar-ring{{width:150px;height:150px;border-radius:50%;padding:5px;background:linear-gradient(135deg,#2563eb,#8b5cf6,#ec4899,#f59e0b);margin-bottom:18px;box-shadow:0 0 60px rgba(99,102,241,0.34);}}
            .call-avatar-ring img{{width:100%;height:100%;border-radius:50%;object-fit:cover;border:5px solid #0f172a;}}
            .controls{{display:flex;gap:18px;flex-wrap:wrap;justify-content:center;align-items:center;margin-top:6px;}}
            .call-control,.end-call{{border:none;text-decoration:none;color:white;background:rgba(51,65,85,0.92);border-radius:999px;width:70px;height:70px;padding:0;font-weight:bold;cursor:pointer;text-align:center;display:flex;flex-direction:column;align-items:center;justify-content:center;font-size:24px;box-shadow:0 16px 38px rgba(0,0,0,0.28);transition:0.18s ease;}}
            .call-control:hover,.end-call:hover{{transform:translateY(-2px);background:#475569;}}
            .control-icon{{display:block;font-size:25px;line-height:1;margin-bottom:4px;}}
            .control-label{{display:none;}}
            .start-call{{background:#16a34a!important;}}
            .start-call:hover{{background:#22c55e!important;}}
            .end-call{{background:#dc2626!important;}}
            .end-call:hover{{background:#ef4444!important;}}
            .call-control.off{{background:#f8fafc!important;color:#020617!important;}}
            .call-control.off .control-label{{color:#020617!important;}}
            .call-control.off .control-icon{{filter:none;}}
            .call-note{{margin-top:18px;color:#94a3b8;text-align:center;font-size:14px;line-height:1.5;}}
            @media(max-width:800px){{.video-grid{{grid-template-columns:1fr}}video,.remote-placeholder{{height:320px}}.call-top{{display:block}}.back-link{{display:inline-block;margin-top:14px}}}}
        </style>
    </head>
    <body onload="startCall()">
        <div class="call-shell">
            <div class="call-top">
                <div>
                    <h1>{icon} {title}</h1>
                    <p>{safe_text(sender.name)} → {safe_text(receiver.name)}</p>
                </div>
                <a class="back-link" href="/chat/{sender.email}/{receiver.email}">← Назад в чат</a>
            </div>

            {main_area}

            <div class="controls">
                <button type="button" id="muteBtn" class="call-control" onclick="toggleMute()" title="Микрофон">
                    <span class="control-icon" id="muteIcon">🎙️</span>
                </button>

                {speaker_button}
                {camera_button}
                {flip_button}

                <a class="end-call" href="/chat/{sender.email}/{receiver.email}" title="Завершить звонок">
                    <span class="control-icon">📵</span>
                </a>
            </div>

            <div class="call-note" id="callNote"></div>
        </div>

        <script>
            let localStream = null;
            let speakerOn = true;
            let cameraFacing = 'user';
            const needVideo = {need_video};

            async function startCall() {{
                try {{
                    if (localStream) {{
                        localStream.getTracks().forEach(function(track) {{ track.stop(); }});
                    }}

                    const constraints = needVideo
                        ? {{ audio: true, video: {{ facingMode: cameraFacing }} }}
                        : {{ audio: true, video: false }};

                    localStream = await navigator.mediaDevices.getUserMedia(constraints);

                    const localVideo = document.getElementById('localVideo');
                    if (localVideo) {{
                        localVideo.srcObject = localStream;
                    }}

                    const status = document.getElementById('callStatus');
                    if (status) status.innerText = 'Звонок...';

                    const note = document.getElementById('callNote');
                    if (note) note.innerText = '';
                }} catch (error) {{
                    alert('Браузер не дал доступ к микрофону/камере или устройство недоступно.');
                }}
            }}

            function toggleMute() {{
                const muteBtn = document.getElementById('muteBtn');
                const muteIcon = document.getElementById('muteIcon');

                if (!localStream) return;

                localStream.getAudioTracks().forEach(function(track) {{
                    track.enabled = !track.enabled;

                    if (track.enabled) {{
                        if (muteBtn) muteBtn.classList.remove('off');
                        if (muteIcon) muteIcon.innerText = '🎙️';
                    }} else {{
                        if (muteBtn) muteBtn.classList.add('off');
                        if (muteIcon) muteIcon.innerText = '🔇';
                    }}
                }});
            }}

            function toggleCamera() {{
                const cameraBtn = document.getElementById('cameraBtn');

                if (!localStream) return;

                localStream.getVideoTracks().forEach(function(track) {{
                    track.enabled = !track.enabled;

                    if (track.enabled) {{
                        if (cameraBtn) cameraBtn.classList.remove('off');
                    }} else {{
                        if (cameraBtn) cameraBtn.classList.add('off');
                    }}
                }});
            }}

            function toggleSpeaker() {{
                const speakerBtn = document.getElementById('speakerBtn');
                const speakerIcon = document.getElementById('speakerIcon');

                speakerOn = !speakerOn;

                if (speakerOn) {{
                    if (speakerBtn) speakerBtn.classList.remove('off');
                    if (speakerIcon) speakerIcon.innerText = '🔊';
                }} else {{
                    if (speakerBtn) speakerBtn.classList.add('off');
                    if (speakerIcon) speakerIcon.innerText = '🔈';
                }}
            }}

            async function flipCamera() {{
                if (!needVideo) return;
                cameraFacing = cameraFacing === 'user' ? 'environment' : 'user';
                await startCall();
            }}

            window.addEventListener('beforeunload', function() {{
                if (localStream) {{
                    localStream.getTracks().forEach(function(track) {{ track.stop(); }});
                }}
            }});
        </script>
    </body>
    </html>
    """


@app.route("/chat/<sender_email>/<receiver_email>", methods=["GET", "POST"])
@login_required
def chat_page(sender_email, receiver_email):
    sender = find_user_by_email(sender_email)
    receiver = find_user_by_email(receiver_email)

    if sender is None or receiver is None:
        return "User not found"
    if is_blocked(receiver.email, sender.email):
        return simple_page(
            "🚫 Сообщение недоступно",
            "Этот пользователь заблокировал вас. Вы не можете отправить ему сообщение.",
            sender.email
        )

    if is_blocked(sender.email, receiver.email):
        return simple_page(
            "🚫 Пользователь заблокирован",
            "Вы заблокировали этого пользователя. Разблокируйте его в настройках, если хотите написать сообщение.",
            sender.email
        )

    privacy = get_user_privacy(receiver.email)

    # --- Typing status logic ---
    typing_data = load_typing_status()
    typing_key = f"{receiver.email}->{sender.email}"
    receiver_typing = False
    if typing_key in typing_data:
        last_typing = typing_data.get(typing_key, 0)
        if datetime.now().timestamp() - last_typing < 4:
            receiver_typing = True

    presence_data = load_presence_status()
    presence_data[sender.email] = datetime.now().timestamp()
    save_presence_status(presence_data)
    receiver_status_text = format_last_seen(presence_data.get(receiver.email))

    if privacy.get("allow_messages") == False:
        return simple_page(
            "💬 Сообщения отключены",
            "Этот пользователь сейчас не принимает личные сообщения.",
            sender.email
        )

    if privacy.get("verified_only_messages") == True and sender.verified == False:
        return simple_page(
            "🛡 Только проверенные пользователи",
            "Этот пользователь принимает сообщения только от проверенных аккаунтов.",
            sender.email
        )

    messages = load_messages()
    changed = False

    for index, msg in enumerate(messages):
        if "id" not in msg:
            msg["id"] = index + 1
            changed = True

        if msg.get("to") == sender.email and msg.get("from") == receiver.email and msg.get("status") != "read":
            msg["status"] = "read"
            changed = True

    if changed:
        save_messages(messages)

    if request.method == "POST":
        validate_csrf_token()
        text = request.form.get("message", "").strip()
        reply_to = request.form.get("reply_to", "").strip()
        edit_message_id = request.form.get("edit_message_id", "").strip()
        audio_data = request.form.get("audio_data", "").strip()
        file = request.files.get("media")

        if edit_message_id and text:
            for msg in messages:
                if str(msg.get("id")) == edit_message_id and msg.get("from") == sender.email:
                    msg["message"] = text
                    msg["edited"] = True
                    msg["edited_time"] = datetime.now().strftime("%d.%m.%Y %H:%M")
                    break

            save_messages(messages)
            return redirect(f"/chat/{sender.email}/{receiver.email}")

        media_url = ""
        media_type = ""
        media_name = ""

        if audio_data:
            try:
                if "," in audio_data:
                    audio_data = audio_data.split(",", 1)[1]

                audio_bytes = base64.b64decode(audio_data)
                safe_sender = sender.email.replace("@", "_").replace(".", "_")
                new_filename = f"voice_{safe_sender}_{datetime.now().strftime('%Y%m%d%H%M%S')}.webm"
                upload_path = os.path.join(UPLOAD_FOLDER, new_filename)

                with open(upload_path, "wb") as audio_file:
                    audio_file.write(audio_bytes)

                media_url = f"/static/uploads/{new_filename}"
                media_type = "audio"
                media_name = "voice_message.webm"
            except Exception:
                return "Voice message upload failed"

        if file and file.filename:
            original_filename = secure_filename(file.filename)
            ext = original_filename.rsplit(".", 1)[-1].lower()

            image_ext = ["jpg", "jpeg", "png", "webp", "gif"]
            video_ext = ["mp4", "mov", "webm", "m4v"]
            document_ext = ["pdf", "doc", "docx", "xls", "xlsx", "txt", "zip"]
            audio_ext = ["mp3", "wav", "m4a", "ogg", "webm"]

            if ext in image_ext:
                media_type = "image"
            elif ext in video_ext:
                media_type = "video"
            elif ext in document_ext:
                media_type = "document"
            elif ext in audio_ext:
                media_type = "audio"
            else:
                return "Unsupported file type"

            safe_sender = sender.email.replace("@", "_").replace(".", "_")
            new_filename = f"chat_{safe_sender}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{original_filename}"
            upload_path = os.path.join(UPLOAD_FOLDER, new_filename)
            file.save(upload_path)

            media_url = f"/static/uploads/{new_filename}"
            media_name = original_filename

        if text != "" or media_url != "":
            next_id = 1
            if messages:
                next_id = max(int(msg.get("id", 0)) for msg in messages) + 1

            messages.append({
                "id": next_id,
                "from": sender.email,
                "to": receiver.email,
                "message": text,
                "media_url": media_url,
                "media_type": media_type,
                "media_name": media_name,
                "reply_to": reply_to,
                "time": datetime.now().strftime("%d.%m.%Y %H:%M"),
                "status": "sent"
            })
            save_messages(messages)

        return redirect(f"/chat/{sender.email}/{receiver.email}")

    visible_messages = []

    for msg in messages:
        if msg.get("deleted_for_everyone") == True:
            continue

        if sender.email in msg.get("deleted_for", []):
            continue

        if (
            msg.get("from") == sender.email and msg.get("to") == receiver.email
        ) or (
            msg.get("from") == receiver.email and msg.get("to") == sender.email
        ):
            visible_messages.append(msg)

    messages_by_id = {str(msg.get("id")): msg for msg in visible_messages}
    pinned_messages = []
    for msg in visible_messages:
        if msg.get("pinned") == True:
            pinned_messages.append(msg)

    pinned_html = ""
    if pinned_messages:
        last_pinned = pinned_messages[-1]
        pinned_text = safe_text(last_pinned.get("message", "Медиафайл"))
        pinned_html = f"""
        <div class="pinned-box" onclick="scrollToMessage('{last_pinned.get('id')}')">
            <div>
                <strong>📌 Закреплено</strong>
                <p>{pinned_text}</p>
            </div>
            <a href="/unpin_message/{sender.email}/{receiver.email}/{last_pinned.get('id')}" onclick="event.stopPropagation()">Открепить</a>
        </div>
        """
    chat_html = ""

    for msg in visible_messages:
        css_class = "mine" if msg.get("from") == sender.email else "theirs"
        media_html = ""
        media_url = msg.get("media_url", "")
        media_type = msg.get("media_type", "")
        media_name = msg.get("media_name", "")
        msg_id = msg.get("id")

        if media_url and media_type == "image":
            media_html = f"""
            <img src="{media_url}" class="chat-media-image">
            """
        elif media_url and media_type == "video":
            media_html = f"""
            <video controls class="chat-media-video">
                <source src="{media_url}">
            </video>
            """
        elif media_url and media_type == "document":
            media_html = f"""
            <a href="{media_url}" target="_blank" class="chat-document">
                📄 {safe_text(media_name)}
            </a>
            """
        elif media_url and media_type == "audio":
            media_html = f"""
            <div class="chat-audio-box">
                <div style="font-weight:bold;margin-bottom:8px;">🎤 Голосовое сообщение</div>
                <audio controls style="width:100%;">
                    <source src="{media_url}">
                </audio>
            </div>
            """

        reply_html = ""
        reply_id = str(msg.get("reply_to", ""))
        if reply_id and reply_id in messages_by_id:
            replied_msg = messages_by_id[reply_id]
            reply_author = "Вы" if replied_msg.get("from") == sender.email else safe_text(receiver.name)
            reply_text = safe_text(replied_msg.get("message", "Медиафайл"))
            reply_html = f"""
            <div class="reply-preview">
                <strong>{reply_author}</strong>
                <span>{reply_text}</span>
            </div>
            """

        message_text = safe_text(msg.get("message")) if msg.get("message") else ""
        # Insert forwarded_html logic
        forwarded_html = ""
        if msg.get("forwarded") == True:
            forwarded_html = '<div style="font-size:12px;color:#cbd5e1;margin-bottom:4px;">↪ Пересланное сообщение</div>'
        edited_html = ""
        if msg.get("edited") == True:
            edited_html = '<span> · изменено</span>'
        if msg.get("status") == "read":
            message_status = '<span class="read-indicator">●</span>'
        else:
            message_status = '<span class="sent-indicator">●</span>'
        reactions = msg.get("reactions", {})
        reactions_html = ""

        for emoji, users_list in reactions.items():
            reactions_html += f'<span class="reaction-pill">{emoji} {len(users_list)}</span>'
        delete_button = f"""
            <a href="/delete_message/{sender.email}/{receiver.email}/{msg_id}/me" class="menu-action danger">🗑 Удалить у меня</a>
        """

        if msg.get("from") == sender.email:
            delete_button += f"""
            <a href="/delete_message/{sender.email}/{receiver.email}/{msg_id}/all" class="menu-action danger">🔥 Удалить у всех</a>
            """

        chat_html += f"""
        <div class="message-row {css_class}">
            <div class="message-bubble" id="message-{msg_id}" data-message-id="{msg_id}" onclick="handleMessageClick('{msg_id}')">
                <button type="button" class="message-select-check" onclick="event.stopPropagation(); toggleMessageSelected('{msg_id}')">✓</button>
                {forwarded_html}
                {reply_html}
                {media_html}
                <p>{message_text}</p>
                <div class="reactions-row">{reactions_html}</div>

                <div class="message-meta">
                    <span>{safe_text(msg.get("time", ""))}{edited_html}</span>
                    {message_status if msg.get("from") == sender.email else ""}
                </div>

                <div class="message-menu" id="message-menu-{msg_id}" onclick="event.stopPropagation()">
                    <button type="button" class="menu-action" onclick="replyToMessage('{msg_id}', `{message_text}`)">↩ Ответить</button>
                    <button type="button" class="menu-action" onclick="startEditMessage('{msg_id}', `{message_text}`)">✏️ Изменить</button>
                    <a href="/forward_message_select/{sender.email}/{receiver.email}/{msg_id}" class="menu-action">↪ Переслать</a>
                    <button type="button" class="menu-action" onclick="copyMessageText(`{message_text}`)">📋 Копировать</button>
                    <a href="/react_message/{sender.email}/{receiver.email}/{msg_id}/👍" class="menu-action">👍</a>
                    <a href="/react_message/{sender.email}/{receiver.email}/{msg_id}/❤️" class="menu-action">❤️</a>
                    <a href="/react_message/{sender.email}/{receiver.email}/{msg_id}/🔥" class="menu-action">🔥</a>
                    <a href="/react_message/{sender.email}/{receiver.email}/{msg_id}/😂" class="menu-action">😂</a>
                    <a href="/react_message/{sender.email}/{receiver.email}/{msg_id}/😮" class="menu-action">😮</a>
                    <button type="button" class="menu-action" onclick="alert('Перевод сообщения будет подключён через AI-модуль.')">🌐 Перевести</button>
                    <a href="/pin_message/{sender.email}/{receiver.email}/{msg_id}" class="menu-action">📌 Закрепить</a>
                    <button type="button" class="menu-action" onclick="alert('Отправлено: {safe_text(msg.get("time", ""))}')">ℹ Инфо</button>
                    {delete_button}
                </div>
            </div>
        </div>
        """

    return f"""
    <html>
    <head>
    <meta charset="UTF-8">
    <title>Chat</title>
    <style>
    body{{
        background:#0f172a;
        color:white;
        font-family:Arial,sans-serif;
        margin:0;
        padding:0;
    }}
    .container{{
        max-width:900px;
        margin:auto;
        min-height:100vh;
        display:flex;
        flex-direction:column;
        padding:24px;
        box-sizing:border-box;
    }}
    .top-back{{
        align-self:flex-start;
        margin-bottom:14px;
    }}
    .header{{
        background:linear-gradient(135deg,#1e293b,#172554);
        padding:18px 22px;
        border-radius:26px;
        margin-bottom:18px;
        display:flex;
        align-items:center;
        gap:14px;
    }}
    .avatar{{
        width:58px;
        height:58px;
        border-radius:50%;
        object-fit:cover;
        background:#334155;
        border:3px solid #334155;
    }}
    .header-info{{flex:1;}}
    .header-actions{{
        display:flex;
        align-items:center;
        gap:10px;
    }}
    .status-line{{
        margin:5px 0 0 0;
        color:#cbd5e1;
        font-size:14px;
    }}
    .header-info h1{{margin:0;font-size:24px;}}
    .back{{
        background:#334155;
        color:white;
        border:none;
        border-radius:14px;
        padding:12px 15px;
        cursor:pointer;
        font-weight:bold;
        white-space:nowrap;
    }}
    .icon-btn{{
        background:#334155;
        color:white;
        border:none;
        border-radius:50%;
        width:48px;
        height:48px;
        cursor:pointer;
        font-weight:bold;
        display:flex;
        align-items:center;
        justify-content:center;
        font-size:20px;
        box-shadow:0 12px 26px rgba(0,0,0,0.22);
        transition:0.16s ease;
    }}
    .icon-btn:hover{{
        transform:scale(1.08);
    }}
    .call-btn{{
        background:#16a34a!important;
        color:white!important;
    }}
    .video-btn{{
        background:#2563eb!important;
        color:white!important;
    }}
    .search-panel{{
        display:none;
        background:#1e293b;
        border:1px solid rgba(96,165,250,0.28);
        padding:14px;
        border-radius:22px;
        margin-bottom:14px;
        box-shadow:0 10px 26px rgba(0,0,0,0.20);
    }}
    .search-panel.open{{
        display:block;
    }}
    .search-panel input{{
        width:100%;
        box-sizing:border-box;
        background:#0f172a;
        color:white;
        border:1px solid #334155;
        border-radius:16px;
        padding:13px 14px;
        outline:none;
        font-size:15px;
        margin-bottom:10px;
    }}
    .search-actions{{
        display:flex;
        gap:8px;
        flex-wrap:wrap;
        margin-bottom:8px;
    }}
    .search-actions button{{
        background:#334155;
        color:white;
        border:none;
        border-radius:12px;
        padding:9px 11px;
        cursor:pointer;
        font-weight:bold;
    }}
    .search-count{{
        color:#94a3b8;
        font-size:13px;
    }}
    .message-bubble.search-match{{
        outline:2px solid #facc15;
        box-shadow:0 0 0 5px rgba(250,204,21,0.12), 0 8px 24px rgba(0,0,0,0.18);
    }}
    .message-bubble.search-active{{
        outline:3px solid #22c55e;
        box-shadow:0 0 0 6px rgba(34,197,94,0.16), 0 8px 24px rgba(0,0,0,0.18);
    }}
    .chat{{
        background:#1e293b;
        padding:22px;
        border-radius:26px;
        min-height:460px;
        margin-bottom:16px;
        overflow-y:auto;
        flex:1;
    }}
    .pinned-box{{
        background:linear-gradient(135deg,#334155,#1e3a8a);
        border:1px solid rgba(96,165,250,0.35);
        padding:14px 16px;
        border-radius:20px;
        margin-bottom:14px;
        display:flex;
        align-items:center;
        justify-content:space-between;
        gap:14px;
        cursor:pointer;
        box-shadow:0 10px 26px rgba(0,0,0,0.22);
    }}
    .pinned-box p{{
        margin:5px 0 0 0;
        color:#cbd5e1;
        max-height:38px;
        overflow:hidden;
    }}
    .pinned-box a{{
        background:#0f172a;
        color:white;
        text-decoration:none;
        padding:8px 10px;
        border-radius:12px;
        font-size:12px;
        font-weight:bold;
        white-space:nowrap;
    }}
    .message-row{{
        display:flex;
        margin-bottom:12px;
    }}
    .message-row.mine{{justify-content:flex-end;}}
    .message-row.theirs{{justify-content:flex-start;}}
    .message-bubble{{
        padding:12px 14px;
        border-radius:20px;
        max-width:70%;
        line-height:1.45;
        box-shadow:0 8px 24px rgba(0,0,0,0.18);
        cursor:pointer;
        position:relative;
    }}
    .message-bubble.selection-mode{{
        padding-left:48px;
    }}

    .message-bubble.selected-message{{
        outline:2px solid #22c55e;
        box-shadow:0 0 0 6px rgba(34,197,94,0.14), 0 8px 24px rgba(0,0,0,0.18);
    }}

    .message-select-check{{
        display:none;
        position:absolute;
        left:12px;
        top:50%;
        transform:translateY(-50%);
        width:26px;
        height:26px;
        border-radius:50%;
        border:2px solid #64748b;
        background:#0f172a;
        color:transparent;
        cursor:pointer;
        font-weight:bold;
    }}

    .message-bubble.selection-mode .message-select-check{{
        display:flex;
        align-items:center;
        justify-content:center;
    }}

    .message-bubble.selected-message .message-select-check{{
        background:#22c55e;
        border-color:#22c55e;
        color:white;
    }}
    .mine .message-bubble{{
        background:#2563eb;
        border-bottom-right-radius:6px;
    }}
    .theirs .message-bubble{{
        background:#334155;
        border-bottom-left-radius:6px;
    }}
    .message-bubble p{{
        margin:8px 0 4px 0;
        white-space:pre-wrap;
        word-break:break-word;
    }}
    .reply-preview{{
        background:rgba(15,23,42,0.45);
        border-left:3px solid #60a5fa;
        padding:8px 10px;
        border-radius:10px;
        margin-bottom:8px;
        display:flex;
        flex-direction:column;
        gap:3px;
        font-size:13px;
    }}
    .reply-preview span{{
        color:#cbd5e1;
        max-height:38px;
        overflow:hidden;
    }}
    /* --- Reaction menu and message menu styles --- */
    .message-menu{{
        display:none;
        position:absolute;
        bottom:calc(100% + 8px);
        z-index:20;
        background:rgba(15,23,42,0.96);
        border:1px solid rgba(148,163,184,0.22);
        border-radius:18px;
        padding:8px;
        gap:6px;
        flex-wrap:wrap;
        width:260px;
        box-shadow:0 18px 45px rgba(0,0,0,0.38);
        backdrop-filter:blur(12px);
    }}
    .mine .message-menu{{ right:0; }}
    .theirs .message-menu{{ left:0; }}

    .message-menu.open{{ display:flex; }}

    .menu-action{{
        background:rgba(51,65,85,0.95);
        color:white;
        border:none;
        border-radius:999px;
        padding:8px 10px;
        cursor:pointer;
        text-decoration:none;
        font-size:12px;
        font-weight:bold;
        white-space:nowrap;
        line-height:1;
    }}

    .menu-action:hover{{
        background:#475569;
        transform:translateY(-1px);
    }}

    .menu-action.danger{{
        background:rgba(220,38,38,0.92);
    }}

    .message-bubble.menu-open{{
        z-index:30;
    }}
    .reactions-row{{
        display:flex;
        gap:6px;
        flex-wrap:wrap;
        margin-top:6px;
    }}

    .reaction-pill{{
        background:rgba(15,23,42,0.45);
        color:white;
        border-radius:999px;
        padding:4px 8px;
        font-size:12px;
        font-weight:bold;
    }}
    .message-meta{{
        display:flex;
        gap:8px;
        justify-content:flex-end;
        color:#cbd5e1;
        font-size:12px;
        margin-top:6px;
    }}

    .sent-indicator{{
        color:#94a3b8;
        font-size:10px;
        font-weight:bold;
    }}

    .read-indicator{{
        color:#22c55e;
        font-size:10px;
        font-weight:bold;
        border:1.8px solid #22c55e;
        border-radius:50%;
        width:12px;
        height:12px;
        display:inline-flex;
        align-items:center;
        justify-content:center;
        line-height:1;
    }}
    .chat-media-image{{
        width:100%;
        max-width:360px;
        max-height:420px;
        object-fit:cover;
        border-radius:16px;
        display:block;
    }}
    .chat-media-video{{
        width:100%;
        max-width:380px;
        max-height:420px;
        border-radius:16px;
        background:#000;
        display:block;
    }}
    .chat-document{{
        display:block;
        background:rgba(15,23,42,0.55);
        color:white;
        text-decoration:none;
        padding:12px;
        border-radius:14px;
        font-weight:bold;
        margin-bottom:6px;
    }}
    .chat-audio-box{{
        background:rgba(15,23,42,0.55);
        padding:12px;
        border-radius:14px;
        margin-bottom:6px;
        min-width:260px;
    }}
    .composer{{
        background:#1e293b;
        border-radius:24px;
        padding:14px;
        display:flex;
        gap:10px;
        align-items:flex-end;
    }}
    .attach-label{{
        background:#334155;
        width:48px;
        height:48px;
        border-radius:16px;
        cursor:pointer;
        font-weight:bold;
        white-space:nowrap;
        display:flex;
        align-items:center;
        justify-content:center;
        font-size:18px;
    }}
    .composer textarea{{
        flex:1;
        height:52px;
        max-height:120px;
        padding:14px;
        border:none;
        border-radius:16px;
        box-sizing:border-box;
        background:#0f172a;
        color:white;
        resize:none;
        outline:none;
        font-size:15px;
    }}
    .send-btn, .mic-btn{{
        width:48px;
        height:48px;
        border:none;
        border-radius:16px;
        background:#2563eb;
        color:white;
        cursor:pointer;
        font-weight:bold;
        display:flex;
        align-items:center;
        justify-content:center;
        font-size:20px;
    }}
    .mic-btn{{
        background:#334155;
    }}
    .mic-btn.recording{{
        background:#dc2626;
        box-shadow:0 0 0 6px rgba(220,38,38,0.22);
        animation:pulseRecord 1s infinite;
    }}
    @keyframes pulseRecord{{
        0%{{transform:scale(1);}}
        50%{{transform:scale(1.05);}}
        100%{{transform:scale(1);}}
    }}
    .reply-bar, .edit-bar{{
        display:none;
        background:#1e293b;
        border-radius:18px;
        padding:10px 14px;
        margin-bottom:10px;
        color:#cbd5e1;
        border-left:4px solid #60a5fa;
    }}
    .edit-bar{{
        border-left-color:#f59e0b;
    }}
    .reply-bar button, .edit-bar button{{
        float:right;
        background:none;
        border:none;
        color:white;
        cursor:pointer;
        font-weight:bold;
    }}
    .hint{{
        color:#94a3b8;
        font-size:13px;
        margin-top:8px;
        padding-left:8px;
    }}
    .voice-panel{{
        display:none;
        background:linear-gradient(135deg,#1e293b,#0f172a);
        border:1px solid rgba(96,165,250,0.25);
        border-radius:20px;
        padding:12px 14px;
        margin-bottom:10px;
        align-items:center;
        gap:12px;
        box-shadow:0 10px 24px rgba(0,0,0,0.22);
    }}
    .voice-dot{{
        width:12px;
        height:12px;
        border-radius:50%;
        background:#ef4444;
        box-shadow:0 0 0 6px rgba(239,68,68,0.18);
        animation:pulseRecord 1s infinite;
    }}
    .voice-time{{
        font-weight:bold;
        color:white;
        min-width:54px;
    }}
    .voice-text{{
        color:#cbd5e1;
        flex:1;
        font-size:14px;
    }}
    .voice-cancel{{
        background:#334155;
        color:white;
        border:none;
        border-radius:12px;
        padding:9px 12px;
        cursor:pointer;
        font-weight:bold;
    }}
    .voice-send{{
        background:#2563eb;
        color:white;
        border:none;
        border-radius:12px;
        padding:9px 12px;
        cursor:pointer;
        font-weight:bold;
    }}
    </style>
    </head>
    <body>
    <div class="container">
        <button class="back top-back" onclick="window.location.href='/messages/{sender.email}'">← Назад</button>

        <div class="header">
            <img class="avatar" src="{get_avatar_url(receiver.email)}">

            <div class="header-info">
                <h1>{safe_text(receiver.name)}</h1>
                <p class="status-line" id="typingStatus">{'✍️ печатает сообщение...' if receiver_typing else receiver_status_text}</p>
            </div>
            <div class="header-actions">
                <button class="icon-btn" onclick="toggleChatSearch()" title="Поиск по чату">🔍</button>

                <button class="icon-btn call-btn"
                onclick="window.location.href='/audio_call/{sender.email}/{receiver.email}'"
                title="Аудиозвонок">📞</button>

                <button class="icon-btn video-btn"
                onclick="window.location.href='/video_call/{sender.email}/{receiver.email}'"
                title="Видеозвонок">🎥</button>

                <button class="icon-btn" onclick="alert('AI-перевод сообщений будет подключён после настройки API-ключа.')" title="AI перевод">🌐</button>
            </div>
            
               
        </div>

        <div class="search-panel" id="chatSearchPanel">
            <input id="chatSearchInput" type="text" placeholder="Поиск сообщений..." oninput="searchChatMessages()">
            <div class="search-actions">
                <button type="button" onclick="goToPreviousSearchResult()">⬆ Предыдущее</button>
                <button type="button" onclick="goToNextSearchResult()">⬇ Следующее</button>
                <button type="button" onclick="clearChatSearch()">✕ Закрыть</button>
            </div>
            <div class="search-count" id="chatSearchCount">Введите текст для поиска</div>
        </div>

        <div class="chat" id="chatBox">
            {pinned_html}
            {chat_html}
        </div>

        <div class="reply-bar" id="replyBar">
            <button type="button" onclick="cancelReply()">✕</button>
            <strong>Ответ на сообщение</strong>
            <div id="replyText"></div>
        </div>

        <div class="edit-bar" id="editBar">
            <button type="button" onclick="cancelEdit()">✕</button>
            <strong>Изменение сообщения</strong>
            <div id="editText"></div>
        </div>

        <div class="voice-panel" id="voicePanel">
            <div class="voice-dot"></div>
            <div class="voice-time" id="voiceTimer">00:00</div>
            <div class="voice-text" id="voiceText">Идёт запись голосового сообщения...</div>
            <button type="button" class="voice-cancel" id="cancelVoiceButton">✕ Отменить</button>
            <button type="button" class="voice-send" id="sendVoiceButton">↑ Отправить</button>
        </div>

        <form method="POST" enctype="multipart/form-data" class="composer" id="messageForm">
            {csrf_input()}
            <input type="hidden" name="reply_to" id="replyToInput">
            <input type="hidden" name="edit_message_id" id="editMessageInput">
            <input type="hidden" name="audio_data" id="audioDataInput">

            <label class="attach-label" title="Файл">
                📎
                <input type="file" name="media" accept="image/*,video/*,audio/*,.pdf,.doc,.docx,.xls,.xlsx,.txt,.zip" style="display:none;">
            <div id="selectedFileName"
                style="
                color:#94a3b8;
                font-size:12px;
                max-width:160px;
                overflow:hidden;
                text-overflow:ellipsis;
                white-space:nowrap;">
            </div>
                    
            </label>

            <textarea name="message" id="messageInput" placeholder="Написать сообщение..."></textarea>

            <button type="button" class="mic-btn" id="micButton" title="Голосовое сообщение">🎤</button>
            <button type="submit" class="send-btn" title="Отправить">↑</button>
        </form>
        <div class="hint">Можно отправить текст, фото, видео, документ и голосовое сообщение. 🎤 начинает запись, затем можно отправить или отменить.</div>
    </div>

    <script>
    const chatBox = document.getElementById('chatBox');
    if (chatBox) {{
        chatBox.scrollTop = chatBox.scrollHeight;
        const fileInput = document.querySelector('input[name="media"]');
        const fileNameBox = document.getElementById('selectedFileName');

        if (fileInput && fileNameBox) {{
            fileInput.addEventListener('change', function() {{
                if (this.files.length > 0) {{
                    fileNameBox.innerText = this.files[0].name;
                }} else {{
                    fileNameBox.innerText = '';
                }}
            }});
        }}
    }}

    function replyToMessage(messageId, text) {{
        const replyBar = document.getElementById('replyBar');
        const replyText = document.getElementById('replyText');
        const replyToInput = document.getElementById('replyToInput');
        const messageInput = document.getElementById('messageInput');

        replyToInput.value = messageId;
        replyText.innerText = text || 'Медиафайл';
        replyBar.style.display = 'block';
        messageInput.focus();
    }}

    function cancelReply() {{
        document.getElementById('replyToInput').value = '';
        document.getElementById('replyText').innerText = '';
        document.getElementById('replyBar').style.display = 'none';
    }}

    function startEditMessage(messageId, text) {{
        const editBar = document.getElementById('editBar');
        const editText = document.getElementById('editText');
        const editInput = document.getElementById('editMessageInput');
        const messageInput = document.getElementById('messageInput');
        const replyInput = document.getElementById('replyToInput');

        replyInput.value = '';
        document.getElementById('replyBar').style.display = 'none';

        editInput.value = messageId;
        editText.innerText = text || 'Сообщение';
        messageInput.value = text || '';
        editBar.style.display = 'block';
        messageInput.focus();
    }}

    function cancelEdit() {{
        document.getElementById('editMessageInput').value = '';
        document.getElementById('editText').innerText = '';
        document.getElementById('editBar').style.display = 'none';
        document.getElementById('messageInput').value = '';
    }}

    function toggleMessageMenu(messageId) {{
        const currentMenu = document.getElementById('message-menu-' + messageId);
        if (!currentMenu) return;

        document.querySelectorAll('.message-menu').forEach(menu => {{
            if (menu !== currentMenu) menu.classList.remove('open');
        }});

        currentMenu.classList.toggle('open');
    }}

    let selectedMessageIds = [];
    let messageSelectionMode = false;

    function handleMessageClick(messageId) {{
        if (messageSelectionMode) {{
            toggleMessageSelected(messageId);
        }} else {{
            toggleMessageMenu(messageId);
        }}
    }}

    function toggleMessageSelected(messageId) {{
        const idText = String(messageId);
        const bubble = document.getElementById('message-' + idText);
        if (!bubble) return;

        if (!messageSelectionMode) {{
            toggleMessageMenu(messageId);
            return;
        }}

        if (selectedMessageIds.includes(idText)) {{
            selectedMessageIds = selectedMessageIds.filter(item => item !== idText);
            bubble.classList.remove('selected-message');
        }} else {{
            selectedMessageIds.push(idText);
            bubble.classList.add('selected-message');
        }}
    }}

    function copyMessageText(text) {{
        if (!text) return;
        navigator.clipboard.writeText(text);
    }}

    function scrollToMessage(messageId) {{
        const message = document.getElementById('message-' + messageId);
        if (!message) return;
        message.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
        message.style.outline = '2px solid #60a5fa';
        setTimeout(() => {{ message.style.outline = 'none'; }}, 1500);
    }}

    let chatSearchResults = [];
    let chatSearchIndex = -1;

    function toggleChatSearch() {{
        const panel = document.getElementById('chatSearchPanel');
        const input = document.getElementById('chatSearchInput');
        if (!panel || !input) return;

        panel.classList.toggle('open');

        if (panel.classList.contains('open')) {{
            setTimeout(() => input.focus(), 100);
        }} else {{
            clearChatSearch();
        }}
    }}

    function searchChatMessages() {{
        const input = document.getElementById('chatSearchInput');
        const count = document.getElementById('chatSearchCount');
        const query = input ? input.value.trim().toLowerCase() : '';

        document.querySelectorAll('.message-bubble').forEach(bubble => {{
            bubble.classList.remove('search-match');
            bubble.classList.remove('search-active');
        }});

        chatSearchResults = [];
        chatSearchIndex = -1;

        if (!query) {{
            if (count) count.innerText = 'Введите текст для поиска';
            return;
        }}

        document.querySelectorAll('.message-bubble').forEach(bubble => {{
            const text = bubble.innerText.toLowerCase();
            if (text.includes(query)) {{
                bubble.classList.add('search-match');
                chatSearchResults.push(bubble);
            }}
        }});

        if (chatSearchResults.length === 0) {{
            if (count) count.innerText = 'Ничего не найдено';
            return;
        }}

        chatSearchIndex = 0;
        activateSearchResult();
    }}

    function activateSearchResult() {{
        const count = document.getElementById('chatSearchCount');

        chatSearchResults.forEach(item => item.classList.remove('search-active'));

        if (chatSearchResults.length === 0 || chatSearchIndex < 0) return;

        const active = chatSearchResults[chatSearchIndex];
        active.classList.add('search-active');
        active.scrollIntoView({{ behavior:'smooth', block:'center' }});

        if (count) {{
            count.innerText = 'Найдено: ' + chatSearchResults.length + ' • сейчас: ' + (chatSearchIndex + 1) + '/' + chatSearchResults.length;
        }}
    }}

    function goToNextSearchResult() {{
        if (chatSearchResults.length === 0) return;
        chatSearchIndex = (chatSearchIndex + 1) % chatSearchResults.length;
        activateSearchResult();
    }}

    function goToPreviousSearchResult() {{
        if (chatSearchResults.length === 0) return;
        chatSearchIndex = (chatSearchIndex - 1 + chatSearchResults.length) % chatSearchResults.length;
        activateSearchResult();
    }}

    function clearChatSearch() {{
        const panel = document.getElementById('chatSearchPanel');
        const input = document.getElementById('chatSearchInput');
        const count = document.getElementById('chatSearchCount');

        if (input) input.value = '';
        if (count) count.innerText = 'Введите текст для поиска';
        if (panel) panel.classList.remove('open');

        document.querySelectorAll('.message-bubble').forEach(bubble => {{
            bubble.classList.remove('search-match');
            bubble.classList.remove('search-active');
        }});

        chatSearchResults = [];
        chatSearchIndex = -1;
    }}

    document.addEventListener('click', function(event) {{
        if (!event.target.closest('.message-bubble')) {{
            document.querySelectorAll('.message-menu').forEach(menu => menu.classList.remove('open'));
        }}
    }});

    // --- Chat background refresh ---
    let lastChatHtml = chatBox ? chatBox.innerHTML : '';

    async function refreshChatInBackground() {{
        const input = document.getElementById('messageInput');
        const replyBar = document.getElementById('replyBar');
        const editBar = document.getElementById('editBar');

        const userIsTyping = input && input.value.trim() !== '';
        const replyIsOpen = replyBar && replyBar.style.display === 'block';
        const editIsOpen = editBar && editBar.style.display === 'block';
        const menuIsOpen = document.querySelector('.message-menu.open');

        if (userIsTyping || replyIsOpen || editIsOpen || menuIsOpen) return;

        try {{
            const response = await fetch(window.location.href, {{ cache: 'no-store' }});
            const html = await response.text();
            const parser = new DOMParser();
            const doc = parser.parseFromString(html, 'text/html');
            const newChatBox = doc.getElementById('chatBox');

            if (!newChatBox || !chatBox) return;

            if (newChatBox.innerHTML !== lastChatHtml) {{
                const nearBottom = chatBox.scrollHeight - chatBox.scrollTop - chatBox.clientHeight < 120;
                chatBox.innerHTML = newChatBox.innerHTML;
                lastChatHtml = newChatBox.innerHTML;

                if (nearBottom) {{
                    chatBox.scrollTop = chatBox.scrollHeight;
                }}
            }}
        }} catch (error) {{
            console.log('Chat refresh skipped');
        }}
    }}

    const messageInput = document.getElementById('messageInput');
    const messageForm = document.getElementById('messageForm');
    const micButton = document.getElementById('micButton');
    const audioDataInput = document.getElementById('audioDataInput');
    const voicePanel = document.getElementById('voicePanel');
    const voiceTimer = document.getElementById('voiceTimer');
    const voiceText = document.getElementById('voiceText');
    const cancelVoiceButton = document.getElementById('cancelVoiceButton');
    const sendVoiceButton = document.getElementById('sendVoiceButton');
    let mediaRecorder = null;
    let recordedChunks = [];
    let voiceStream = null;
    let recordingStartedAt = null;
    let recordingTimerInterval = null;
    let shouldSendVoice = false;

    function formatVoiceTime(totalSeconds) {{
        const minutes = Math.floor(totalSeconds / 60).toString().padStart(2, '0');
        const seconds = Math.floor(totalSeconds % 60).toString().padStart(2, '0');
        return minutes + ':' + seconds;
    }}

    function startVoiceTimer() {{
        recordingStartedAt = Date.now();
        if (voiceTimer) voiceTimer.innerText = '00:00';
        recordingTimerInterval = setInterval(function() {{
            const seconds = Math.floor((Date.now() - recordingStartedAt) / 1000);
            if (voiceTimer) voiceTimer.innerText = formatVoiceTime(seconds);
        }}, 500);
    }}

    function stopVoiceTimer() {{
        if (recordingTimerInterval) {{
            clearInterval(recordingTimerInterval);
            recordingTimerInterval = null;
        }}
    }}

    function resetVoiceUi() {{
        stopVoiceTimer();
        if (voicePanel) voicePanel.style.display = 'none';
        if (voiceText) voiceText.innerText = 'Идёт запись голосового сообщения...';
        if (voiceTimer) voiceTimer.innerText = '00:00';
        if (micButton) {{
            micButton.classList.remove('recording');
            micButton.innerText = '🎤';
        }}
    }}

    function stopVoiceTracks() {{
        if (voiceStream) {{
            voiceStream.getTracks().forEach(track => track.stop());
            voiceStream = null;
        }}
    }}

    async function toggleVoiceRecording() {{
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {{
            alert('Ваш браузер не поддерживает запись голоса.');
            return;
        }}

        if (mediaRecorder && mediaRecorder.state === 'recording') {{
            shouldSendVoice = false;
            mediaRecorder.stop();
            return;
        }}

        try {{
            voiceStream = await navigator.mediaDevices.getUserMedia({{ audio: true }});
            recordedChunks = [];
            shouldSendVoice = false;
            mediaRecorder = new MediaRecorder(voiceStream);

            mediaRecorder.ondataavailable = function(event) {{
                if (event.data.size > 0) {{
                    recordedChunks.push(event.data);
                }}
            }};

            mediaRecorder.onstop = function() {{
                stopVoiceTimer();
                stopVoiceTracks();

                if (!shouldSendVoice) {{
                    recordedChunks = [];
                    resetVoiceUi();
                    return;
                }}

                const audioBlob = new Blob(recordedChunks, {{ type: 'audio/webm' }});
                const reader = new FileReader();

                reader.onloadend = function() {{
                    audioDataInput.value = reader.result;
                    resetVoiceUi();
                    messageForm.submit();
                }};

                reader.readAsDataURL(audioBlob);
            }};

            mediaRecorder.start();
            startVoiceTimer();
            if (voicePanel) voicePanel.style.display = 'flex';
            micButton.classList.add('recording');
            micButton.innerText = '■';
        }} catch (error) {{
            resetVoiceUi();
            alert('Не удалось включить микрофон. Проверьте разрешение браузера.');
        }}
    }}

    function cancelVoiceRecording() {{
        shouldSendVoice = false;
        if (mediaRecorder && mediaRecorder.state === 'recording') {{
            mediaRecorder.stop();
        }} else {{
            resetVoiceUi();
            stopVoiceTracks();
        }}
    }}

    function sendVoiceRecording() {{
        if (!mediaRecorder || mediaRecorder.state !== 'recording') return;
        shouldSendVoice = true;
        if (voiceText) voiceText.innerText = 'Голосовое отправляется...';
        mediaRecorder.stop();
    }}

    if (micButton) {{
        micButton.addEventListener('click', toggleVoiceRecording);
    }}

    if (cancelVoiceButton) {{
        cancelVoiceButton.addEventListener('click', cancelVoiceRecording);
    }}

    if (sendVoiceButton) {{
        sendVoiceButton.addEventListener('click', sendVoiceRecording);
    }}

    function sendPresencePing() {{
        fetch('/presence/{sender.email}', {{ method: 'POST' }});
    }}

    sendPresencePing();
    setInterval(sendPresencePing, 10000);

    if (messageInput) {{
        messageInput.addEventListener('input', function() {{
            sendPresencePing();
            fetch('/typing/{sender.email}/{receiver.email}', {{
                method: 'POST'
            }});
        }});
    }}

    setInterval(refreshChatInBackground, 3500);
    </script>
    </body>
    </html>
    """

@app.route("/react_message/<sender_email>/<receiver_email>/<int:message_id>/<emoji>")
def react_message(sender_email, receiver_email, message_id, emoji):
    messages = load_messages()

    for msg in messages:
        if msg.get("id") == message_id:
            same_chat = (
                (msg.get("from") == sender_email and msg.get("to") == receiver_email) or
                (msg.get("from") == receiver_email and msg.get("to") == sender_email)
            )

            if not same_chat:
                continue

            reactions = msg.get("reactions", {})

            for reaction_name in list(reactions.keys()):
                if sender_email in reactions.get(reaction_name, []):
                    reactions[reaction_name].remove(sender_email)
                    if len(reactions[reaction_name]) == 0:
                        del reactions[reaction_name]

            users_list = reactions.get(emoji, [])
            if sender_email not in users_list:
                users_list.append(sender_email)
                reactions[emoji] = users_list

            msg["reactions"] = reactions
            break

    save_messages(messages)
    return redirect(f"/chat/{sender_email}/{receiver_email}")


# New route for deleting a message
@app.route("/delete_message/<sender_email>/<receiver_email>/<int:message_id>/<mode>")
def delete_message(sender_email, receiver_email, message_id, mode):
    messages = load_messages()

    for msg in messages:
        if msg.get("id") == message_id:
            same_chat = (
                (msg.get("from") == sender_email and msg.get("to") == receiver_email) or
                (msg.get("from") == receiver_email and msg.get("to") == sender_email)
            )

            if not same_chat:
                continue

            if mode == "me":
                deleted_for = msg.get("deleted_for", [])
                if sender_email not in deleted_for:
                    deleted_for.append(sender_email)
                msg["deleted_for"] = deleted_for

            elif mode == "all" and msg.get("from") == sender_email:
                msg["deleted_for_everyone"] = True

            break

    save_messages(messages)

    return redirect(f"/chat/{sender_email}/{receiver_email}")

# --- Pin/unpin message routes ---
@app.route("/pin_message/<sender_email>/<receiver_email>/<int:message_id>")
def pin_message(sender_email, receiver_email, message_id):
    messages = load_messages()

    for msg in messages:
        same_chat = (
            (msg.get("from") == sender_email and msg.get("to") == receiver_email) or
            (msg.get("from") == receiver_email and msg.get("to") == sender_email)
        )

        if same_chat:
            msg["pinned"] = False

        if msg.get("id") == message_id:
            msg["pinned"] = True

    save_messages(messages)

    return redirect(f"/chat/{sender_email}/{receiver_email}")


@app.route("/unpin_message/<sender_email>/<receiver_email>/<int:message_id>")
def unpin_message(sender_email, receiver_email, message_id):
    messages = load_messages()

    for msg in messages:
        if msg.get("id") == message_id:
            msg["pinned"] = False
            break

    save_messages(messages)

    return redirect(f"/chat/{sender_email}/{receiver_email}")

# --- Forward message select route ---
@app.route("/forward_message_select/<sender_email>/<receiver_email>/<int:message_id>")
def forward_message_select(sender_email, receiver_email, message_id):
    current_user = find_user_by_email(sender_email)

    if current_user is None:
        return "User not found"

    users_html = ""

    for user in users:
        if user.email == sender_email:
            continue

        users_html += f'''
        <div style="background:#1e293b;padding:16px;border-radius:18px;margin-bottom:12px;display:flex;justify-content:space-between;align-items:center;">
            <div>
                <strong>{safe_text(user.name)}</strong><br>
                <span style="color:#94a3b8;">{safe_text(user.profession)}</span>
            </div>
            <a href="/forward_message/{sender_email}/{message_id}/{user.email}" style="background:#2563eb;color:white;text-decoration:none;padding:10px 14px;border-radius:12px;">Отправить</a>
        </div>
        '''

    return f'''
    <html>
    <body style="background:#0f172a;color:white;font-family:Arial;padding:30px;">
        <h1>↪ Переслать сообщение</h1>
        <a href="/chat/{sender_email}/{receiver_email}" style="color:white;">← Назад в чат</a>
        <div style="margin-top:20px;">{users_html}</div>
    </body>
    </html>
    '''


# --- Forward message action route ---
@app.route("/forward_message/<sender_email>/<int:message_id>/<target_email>")
def forward_message(sender_email, message_id, target_email):
    messages = load_messages()

    original_message = None

    for msg in messages:
        if msg.get("id") == message_id:
            original_message = msg
            break

    if original_message is None:
        return "Message not found"

    next_id = 1
    if messages:
        next_id = max(int(m.get("id", 0)) for m in messages) + 1

    messages.append({
        "id": next_id,
        "from": sender_email,
        "to": target_email,
        "message": original_message.get("message", ""),
        "media_url": original_message.get("media_url", ""),
        "media_type": original_message.get("media_type", ""),
        "media_name": original_message.get("media_name", ""),
        "time": datetime.now().strftime("%d.%m.%Y %H:%M"),
        "status": "sent",
        "forwarded": True
    })

    save_messages(messages)

    return redirect(f"/chat/{sender_email}/{target_email}")

@app.route("/proof/<viewer_email>/<profile_email>")
def proof_profile_page(viewer_email, profile_email):
    profile_user = find_user_by_email(profile_email)

    if profile_user is None:
        return "User not found"

    data = load_proofs()
    proofs = data.get("proofs", [])

    user_proofs = []
    for proof in proofs:
        if proof.get("email") == profile_email:
            user_proofs.append(proof)

    certificates_count = 0
    projects_count = 0
    videos_count = 0
    achievements_count = 0

    for proof in user_proofs:
        if proof.get("type") == "certificate":
            certificates_count += 1
        elif proof.get("type") == "project":
            projects_count += 1
        elif proof.get("type") == "video":
            videos_count += 1
        elif proof.get("type") == "achievement":
            achievements_count += 1

    proof_score = min(
        100,
        certificates_count * 15 +
        projects_count * 20 +
        videos_count * 20 +
        achievements_count * 15
    )
    
    documents_count = certificates_count

    total_proofs = (
        certificates_count +
        projects_count +
        videos_count +
        achievements_count
)

    proof_summary = (
        f"Пользователь загрузил {total_proofs} подтверждений навыков, опыта и достижений."
)

    html = open_html("proof_profile.html")

    return render_template_string(
        html,
        email=profile_email,
        viewer_email=viewer_email,
        proof_score=proof_score,
        certificates_count=certificates_count,
        documents_count=certificates_count,
        projects_count=projects_count,
        videos_count=videos_count,
        achievements_count=achievements_count,
        total_proofs=total_proofs,
        proof_summary=proof_summary
    )


@app.route("/add_proof/<viewer_email>/<profile_email>/<proof_type>", methods=["GET", "POST"])
def add_proof_page(viewer_email, profile_email, proof_type):
    profile_user = find_user_by_email(profile_email)

    if profile_user is None:
        return "User not found"

    if request.method == "POST":
        validate_csrf_token()
        title = request.form["title"]
        description = request.form["description"]

        data = load_proofs()

        data["proofs"].append({
            "email": profile_email,
            "type": proof_type,
            "title": title,
            "description": description,
            "date": datetime.now().strftime("%d.%m.%Y %H:%M")
        })

        save_proofs(data)

        return redirect(f"/proof/{viewer_email}/{profile_email}")

    return f"""
    <html>
    <head>
    <meta charset="UTF-8">
    <title>Добавить Proof</title>
    <style>
    body{{background:#0f172a;color:white;font-family:Arial;padding:40px}}
    .card{{background:#1e293b;padding:30px;border-radius:20px;max-width:700px;margin:auto}}
    input,textarea{{width:100%;padding:14px;margin-top:10px;margin-bottom:15px;border:none;border-radius:10px}}
    textarea{{height:140px}}
    button{{padding:14px 20px;border:none;border-radius:12px;background:#2563eb;color:white;cursor:pointer}}
    .back{{background:#334155}}
    </style>
    </head>
    <body>
    <div class="card">
        <h1>🏆 Добавить Proof</h1>

        <form method="POST">
            {csrf_input()}
            <label>Название</label>
            <input name="title" required>

            <label>Описание</label>
            <textarea name="description" required></textarea>

            <button type="submit">Сохранить</button>
        </form>

        <br>
        <button class="back" onclick="window.location.href='/proof/{viewer_email}/{profile_email}'">Назад</button>
    </div>
    </body>
    </html>
    """


@app.route("/privacy/<email>")
def privacy_page(email):
    settings = get_user_privacy(email)

    html = open_html("privacy.html")

    return render_template_string(
        html,
        email=email,

        receive_text="ON" if settings["receive_recommendations"] else "OFF",
        receive_class="on" if settings["receive_recommendations"] else "off",

        show_text="ON" if settings["show_me_to_others"] else "OFF",
        show_class="on" if settings["show_me_to_others"] else "off",

        search_text="ON" if settings["show_in_search"] else "OFF",
        search_class="on" if settings["show_in_search"] else "off",

        messages_text="ON" if settings["allow_messages"] else "OFF",
        messages_class="on" if settings["allow_messages"] else "off",

        verified_text="ON" if settings["verified_only_messages"] else "OFF",
        verified_class="on" if settings["verified_only_messages"] else "off",

        vip_text="ON" if settings["vip_mode"] else "OFF",
        vip_class="on" if settings["vip_mode"] else "off"
    )


@app.route("/toggle_privacy/<email>/<setting>")
def toggle_privacy(email, setting):
    settings = get_user_privacy(email)

    current_value = settings.get(setting, False)

    update_user_privacy(
        email,
        setting,
        not current_value
    )

    return redirect(f"/privacy/{email}")

def social_list_page(title, email, list_emails):
    profile_user = find_user_by_email(email)

    if profile_user is None:
        return "User not found"

    cards_html = ""

    for item_email in list_emails:
        item_user = find_user_by_email(item_email)

        if item_user is None:
            continue

        avatar_url = get_avatar_url(item_user.email)

        cards_html += f"""
        <div style="background:#1e293b;padding:18px;border-radius:22px;margin-bottom:14px;display:flex;align-items:center;gap:16px;">
            <img src="{avatar_url}" style="width:66px;height:66px;border-radius:50%;object-fit:cover;background:#334155;border:3px solid #334155;">

            <div style="flex:1;">
                <h3 style="margin:0 0 6px 0;font-size:20px;">{item_user.name}</h3>
                <p style="margin:0 0 6px 0;color:#cbd5e1;">{safe_text(item_user.profession)}</p>
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


@app.route("/friends/<email>")
def friends_page(email):
    return social_list_page(
        "Друзья",
        email,
        get_friends(email)
    )


@app.route("/followers/<email>")
def followers_page(email):
    return social_list_page(
        "Подписчики",
        email,
        get_followers(email)
    )


@app.route("/following/<email>")
def following_page(email):
    return social_list_page(
        "Подписки",
        email,
        get_following(email)
    )

@app.route("/friend_requests/<email>")
def friend_requests_page(email):
    user = find_user_by_email(email)

    if user is None:
        return "User not found"

    requests = get_friend_requests(email)

    requests_html = ""

    for request_item in requests:
        sender_email = request_item.get("from")
        sender = find_user_by_email(sender_email)

        if sender is None:
            continue

        avatar_url = get_avatar_url(sender.email)

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


@app.route("/decline_friend_request/<viewer_email>/<profile_email>")
def decline_friend_request_route(viewer_email, profile_email):
    decline_friend_request(profile_email, viewer_email)
    return redirect(f"/friend_requests/{viewer_email}")


@app.route("/notifications/<email>")
def notifications_page(email):

    notifications = get_notifications(email)

    cards = ""

    for item in notifications:

        cards += f"""
        <div style="
            background:#1e293b;
            padding:18px;
            border-radius:18px;
            margin-bottom:12px;
        ">
            <div style="font-weight:bold;">
                {item["text"]}
            </div>

            <div style="
                color:#94a3b8;
                margin-top:8px;
                font-size:14px;
            ">
                {item["created_at"]}
            </div>
        </div>
        """

    if cards == "":
        cards = """
        <div style="
            background:#1e293b;
            padding:20px;
            border-radius:18px;
        ">
            Уведомлений пока нет.
        </div>
        """

    return f"""
    <html>
    <head>
        <title>Уведомления</title>
    </head>

    <body style="
        background:#0f172a;
        color:white;
        font-family:Arial;
        padding:30px;
    ">

        <div style="max-width:900px;margin:auto;">

            <a href="/dashboard/{email}"
               style="
               color:white;
               text-decoration:none;
               ">
               ← Назад
            </a>

            <h1>🔔 Уведомления</h1>

            {cards}

        </div>

    </body>
    </html>
    """

@app.route("/radar/<email>")
def radar_page(email):
    current_user = find_user_by_email(email)

    if current_user is None:
        return "User not found"

    matches_list = find_best_matches(current_user, users)

    people_html = ""

    for match in matches_list[:5]:
        matched_user = match["user"]
        score = match["score"]
        reasons = explain_match(current_user, matched_user)
        avatar_url = get_avatar_url(matched_user.email)

        reasons_html = ""
        for reason in reasons[:3]:
            reasons_html += f"<li>{safe_text(reason)}</li>"

        people_html += f"""
        <div style="background:#1e293b;padding:22px;border-radius:24px;margin-bottom:18px;">
            <div style="display:flex;align-items:center;gap:18px;">
                <img src="{avatar_url}" style="width:76px;height:76px;border-radius:50%;object-fit:cover;background:#334155;border:3px solid #334155;">

                <div style="flex:1;">
                    <h2 style="margin:0 0 6px 0;">{safe_text(matched_user.name)}</h2>
                    <p style="margin:0;color:#cbd5e1;">{safe_text(matched_user.profession)}</p>
                    <p style="margin:6px 0 0 0;color:#22c55e;font-weight:bold;">AI Match: {score}%</p>
                </div>

                <a href="/profile/{matched_user.email}?viewer={current_user.email}" style="background:#2563eb;color:white;text-decoration:none;padding:12px 16px;border-radius:14px;font-weight:bold;">
                    Открыть профиль
                </a>
            </div>

            <div style="background:#0f172a;padding:16px;border-radius:18px;margin-top:18px;">
                <h3 style="margin-top:0;">Почему сейчас</h3>
                <ul style="color:#cbd5e1;line-height:1.6;">
                    {reasons_html}
                </ul>
            </div>
        </div>
        """

    if people_html == "":
        people_html = """
        <div style="background:#1e293b;padding:24px;border-radius:22px;color:#cbd5e1;text-align:center;">
            Пока AI Radar не нашёл подходящих людей. Заполните цели, интересы и навыки.
        </div>
        """

    return f"""
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <title>AI Life Radar</title>
    </head>

    <body style="margin:0;background:#0f172a;color:white;font-family:Arial,sans-serif;padding:32px;">
        <div style="max-width:1100px;margin:auto;">

            <a href="/dashboard/{current_user.email}" style="display:inline-block;color:white;text-decoration:none;background:#334155;padding:12px 16px;border-radius:14px;margin-bottom:18px;font-weight:bold;">
                ← Назад
            </a>

            <section style="background:linear-gradient(135deg,#1e293b,#172554);padding:32px;border-radius:30px;margin-bottom:24px;">
                <h1 style="margin:0 0 10px 0;font-size:38px;">🧠 AI Life Radar</h1>
                <p style="color:#cbd5e1;margin:0;font-size:17px;">
                    Персональные рекомендации людей, возможностей и действий на основе целей, интересов, навыков и профиля.
                </p>
            </section>

            <section style="background:#1e293b;padding:24px;border-radius:26px;margin-bottom:22px;">
                <h2 style="margin-top:0;">Люди, которых стоит посмотреть сегодня</h2>
                <p style="color:#cbd5e1;">
                    AI выбрал людей, которые могут быть полезны для бизнеса, развития, дружбы, команды или будущих проектов.
                </p>
            </section>

            {people_html}

        </div>
    </body>
    </html>
    """

if __name__ == "__main__":

    app.run(debug=True, port=5001)