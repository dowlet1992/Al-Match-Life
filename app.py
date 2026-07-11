from flask import Flask, send_from_directory, request, redirect, render_template_string, session, abort
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from twilio.rest import Client
import os
import json
import base64
import mimetypes
import secrets
import bleach
import smtplib
import urllib.parse
import urllib.request
import urllib.error
import ssl
from email.message import EmailMessage
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
 

def load_local_env_file(filename=".env"):
    if not os.path.exists(filename):
        return

    try:
        with open(filename, "r", encoding="utf-8") as file:
            for line in file:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue

                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")

                if key and key not in os.environ:
                    os.environ[key] = value
    except Exception as error:
        print(f"Could not load .env file: {error}")


load_local_env_file()
def get_app_secret_key():
    env_secret = os.environ.get("FLASK_SECRET_KEY")
    if env_secret:
        return env_secret

    secret_file = ".dev_secret_key"
    try:
        if os.path.exists(secret_file):
            with open(secret_file, "r", encoding="utf-8") as file:
                saved_secret = file.read().strip()
                if saved_secret:
                    return saved_secret

        new_secret = secrets.token_hex(32)
        with open(secret_file, "w", encoding="utf-8") as file:
            file.write(new_secret)
        return new_secret
    except:
        return "dev-only-change-before-production-ai-match-life-secret"

app = Flask(__name__)
app.secret_key = get_app_secret_key()
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("FLASK_ENV") == "production"
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=30)
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024
 
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "").strip()
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "").strip()
TWILIO_VERIFY_SERVICE_SID = os.environ.get("TWILIO_VERIFY_SERVICE_SID", "").strip()
twilio_client = None

if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN:
    twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
from backend.ai_engine import analyze_user_profile, explain_user_match, generate_feed_idea, analyze_proof_profile, generate_life_radar
UPLOAD_FOLDER = "static/uploads"
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp", "mp4", "webm", "mov", "mp3", "m4a", "wav", "ogg"}

LOGIN_ATTEMPTS_FILE = "login_attempts.json"
SECURITY_LOG_FILE = "security_log.json"
NEWS_FILE = "news.json"
MAX_LOGIN_ATTEMPTS = 5
LOGIN_ATTEMPT_WINDOW_MINUTES = 10
LOGIN_LOCK_MINUTES = 15
LOGIN_2FA_ENABLED = os.environ.get("LOGIN_2FA_ENABLED", "false").strip().lower() == "true"

# --- Verification code settings ---
VERIFICATION_CODES_FILE = "verification_codes.json"
VERIFICATION_CODE_MINUTES = 10
VERIFICATION_CODE_LENGTH = 6
MAX_VERIFICATION_ATTEMPTS = 5
VERIFICATION_RESEND_SECONDS = 60

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

loaded_users = load_users_from_json()
if loaded_users is not None:
    users = loaded_users



def find_user_by_email(email):
    for user in users:
        if user.email.strip().lower() == email.strip().lower():
            return user
    return None

# --- Password recovery helper ---

def find_user_by_contact(contact_type, contact_value):
    contact_type = str(contact_type or "").strip().lower()

    if contact_type == "email":
        return find_user_by_email(normalize_email(contact_value))

    if contact_type == "phone":
        normalized_phone = normalize_phone(contact_value)
        for user in users:
            if normalize_phone(getattr(user, "phone", "")) == normalized_phone:
                return user

    return None


def find_user_by_login(login_value):
    login_value = str(login_value or "").strip()

    if not login_value:
        return None, "", ""

    if "@" in login_value:
        normalized_email = normalize_email(login_value)
        return find_user_by_email(normalized_email), "email", normalized_email

    normalized_phone = normalize_phone(login_value)
    return find_user_by_contact("phone", normalized_phone), "phone", normalized_phone


def is_account_verified(user):
    if user is None:
        return False
    return getattr(user, "account_verified", True) is True


def mark_account_verified(user, contact_type="email"):
    if user is None:
        return False
    user.account_verified = True
    user.account_verified_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    user.account_verified_via = clean_text(contact_type)
    save_users_to_json(users)
    return True


# --- 2FA helper for login ---
def get_user_2fa_contact(user):
    if user is None:
        return "email", ""

    phone_value = normalize_phone(getattr(user, "phone", ""))
    if phone_value:
        return "phone", phone_value

    return "email", normalize_email(getattr(user, "email", ""))

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

def log_security_event(event_type, email="", details=""):
    try:
        try:
            with open(SECURITY_LOG_FILE, "r", encoding="utf-8") as file:
                data = json.load(file)
        except:
            data = []

        if not isinstance(data, list):
            data = []

        ip = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown")
        ip = ip.split(",")[0].strip()

        data.append({
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "event": clean_text(event_type),
            "email": clean_text(email),
            "ip": clean_text(ip),
            "details": clean_text(details)
        })

        with open(SECURITY_LOG_FILE, "w", encoding="utf-8") as file:
            json.dump(data[-1000:], file, indent=4, ensure_ascii=False)
    except:
        pass       


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
        log_security_event("login_locked", email, "Temporary login lock is active")
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
        log_security_event("login_failed", email, f"Failed attempts: {len(clean_attempts)}")
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



# --- Multilanguage helpers ---
SUPPORTED_LANGUAGES = {
    "ru": "Русский",
    "en": "English",
    "de": "Deutsch",
    "tr": "Türkçe"
}

# Языки интерфейса переводим отдельно и качественно.
# Языки контента нужны шире: посты, видео, новости, AI Discover.
CONTENT_LANGUAGES = {
    "af": "Afrikaans",
    "am": "አማርኛ",
    "ar": "العربية",
    "az": "Azərbaycanca",
    "be": "Беларуская",
    "bg": "Български",
    "bn": "বাংলা",
    "bs": "Bosanski",
    "ca": "Català",
    "cs": "Čeština",
    "da": "Dansk",
    "de": "Deutsch",
    "el": "Ελληνικά",
    "en": "English",
    "es": "Español",
    "et": "Eesti",
    "fa": "فارسی",
    "fi": "Suomi",
    "fr": "Français",
    "he": "עברית",
    "hi": "हिन्दी",
    "hr": "Hrvatski",
    "hu": "Magyar",
    "hy": "Հայերեն",
    "id": "Bahasa Indonesia",
    "it": "Italiano",
    "ja": "日本語",
    "ka": "ქართული",
    "kk": "Қазақша",
    "km": "ភាសាខ្មែរ",
    "ko": "한국어",
    "ky": "Кыргызча",
    "lt": "Lietuvių",
    "lv": "Latviešu",
    "mk": "Македонски",
    "mn": "Монгол",
    "ms": "Bahasa Melayu",
    "nl": "Nederlands",
    "no": "Norsk",
    "pa": "ਪੰਜਾਬੀ",
    "pl": "Polski",
    "ps": "پښتو",
    "pt": "Português",
    "ro": "Română",
    "ru": "Русский",
    "sk": "Slovenčina",
    "sl": "Slovenščina",
    "sq": "Shqip",
    "sr": "Српски",
    "sv": "Svenska",
    "sw": "Kiswahili",
    "ta": "தமிழ்",
    "te": "తెలుగు",
    "tg": "Тоҷикӣ",
    "th": "ไทย",
    "tk": "Türkmençe",
    "tr": "Türkçe",
    "uk": "Українська",
    "ur": "اردو",
    "uz": "Oʻzbekcha",
    "vi": "Tiếng Việt",
    "zh": "中文",
    "unknown": "Unknown"
}

DEFAULT_LANGUAGE = "ru"

UI_TRANSLATIONS = {
    "ru": {
        "back": "← Назад",
        "dashboard": "Главная",
        "profile": "Профиль",
        "settings": "Настройки",
        "messages": "Сообщения",
        "notifications": "Уведомления",
        "ai_discover": "AI Discover",
        "ai_discover_subtitle": "Умная лента видео, идей, проектов, мест и людей. AI показывает контент по вашим целям, интересам, языкам, локации и активности.",
        "create_post": "Создать публикацию",
        "publish": "Опубликовать",
        "post_placeholder": "Что хотите показать миру? Идея, видео, место, бизнес, проект...",
        "city_country": "Город / страна",
        "why_ai_showed": "🧠 Почему AI показал:",
        "write": "Написать",
        "unavailable": "Недоступно",
        "open": "Открыть",
        "empty_feed_title": "Пока нет публикаций",
        "empty_feed_text": "Создайте первый пост, идею, видео или проект. AI Discover начнёт строить умную ленту вокруг интересов пользователей."
    },
    "en": {
        "back": "← Back",
        "dashboard": "Dashboard",
        "profile": "Profile",
        "settings": "Settings",
        "messages": "Messages",
        "notifications": "Notifications",
        "ai_discover": "AI Discover",
        "ai_discover_subtitle": "A smart feed of videos, ideas, projects, places and people. AI shows content based on your goals, interests, languages, location and activity.",
        "create_post": "Create post",
        "publish": "Publish",
        "post_placeholder": "What do you want to show the world? Idea, video, place, business, project...",
        "city_country": "City / country",
        "why_ai_showed": "🧠 Why AI showed this:",
        "write": "Message",
        "unavailable": "Unavailable",
        "open": "Open",
        "empty_feed_title": "No posts yet",
        "empty_feed_text": "Create the first post, idea, video or project. AI Discover will start building a smart feed around user interests."
    },
    "de": {
        "back": "← Zurück",
        "dashboard": "Startseite",
        "profile": "Profil",
        "settings": "Einstellungen",
        "messages": "Nachrichten",
        "notifications": "Benachrichtigungen",
        "ai_discover": "AI Discover",
        "ai_discover_subtitle": "Ein smarter Feed mit Videos, Ideen, Projekten, Orten und Menschen. AI zeigt Inhalte basierend auf Zielen, Interessen, Sprachen, Standort und Aktivität.",
        "create_post": "Beitrag erstellen",
        "publish": "Veröffentlichen",
        "post_placeholder": "Was möchten Sie der Welt zeigen? Idee, Video, Ort, Business, Projekt...",
        "city_country": "Stadt / Land",
        "why_ai_showed": "🧠 Warum AI das zeigt:",
        "write": "Schreiben",
        "unavailable": "Nicht verfügbar",
        "open": "Öffnen",
        "empty_feed_title": "Noch keine Beiträge",
        "empty_feed_text": "Erstellen Sie den ersten Beitrag, eine Idee, ein Video oder ein Projekt. AI Discover beginnt dann, einen smarten Feed rund um Interessen aufzubauen."
    },
    "tr": {
        "back": "← Geri",
        "dashboard": "Ana sayfa",
        "profile": "Profil",
        "settings": "Ayarlar",
        "messages": "Mesajlar",
        "notifications": "Bildirimler",
        "ai_discover": "AI Discover",
        "ai_discover_subtitle": "Videolar, fikirler, projeler, yerler ve insanlar için akıllı akış. AI; hedeflere, ilgi alanlarına, dillere, konuma ve aktiviteye göre içerik gösterir.",
        "create_post": "Gönderi oluştur",
        "publish": "Yayınla",
        "post_placeholder": "Dünyaya ne göstermek istiyorsunuz? Fikir, video, yer, iş, proje...",
        "city_country": "Şehir / ülke",
        "why_ai_showed": "🧠 AI bunu neden gösterdi:",
        "write": "Mesaj yaz",
        "unavailable": "Kullanılamaz",
        "open": "Aç",
        "empty_feed_title": "Henüz gönderi yok",
        "empty_feed_text": "İlk gönderiyi, fikri, videoyu veya projeyi oluşturun. AI Discover kullanıcı ilgi alanlarına göre akıllı akış oluşturmaya başlayacak."
    }
}


def normalize_language_code(language_value):
    language_value = str(language_value or "").strip().lower()

    if not language_value:
        return DEFAULT_LANGUAGE

    language_value = language_value.split(",")[0].split(";")[0].strip()
    language_value = language_value.split("-")[0].split("_")[0].strip()

    if language_value in SUPPORTED_LANGUAGES:
        return language_value

    return DEFAULT_LANGUAGE


def normalize_content_language_code(language_value):
    language_value = str(language_value or "").strip().lower()

    if not language_value:
        return "unknown"

    language_value = language_value.split(",")[0].split(";")[0].strip()
    language_value = language_value.split("-")[0].split("_")[0].strip()

    if language_value in CONTENT_LANGUAGES:
        return language_value

    return "unknown"


def get_current_language(user=None):
    session_language = normalize_language_code(session.get("language", ""))
    if session_language in SUPPORTED_LANGUAGES and session.get("language"):
        return session_language

    if user is not None:
        saved_language = normalize_language_code(getattr(user, "language", ""))
        if saved_language in SUPPORTED_LANGUAGES and getattr(user, "language", ""):
            return saved_language

    return normalize_language_code(request.headers.get("Accept-Language", DEFAULT_LANGUAGE))


def t(key, language=None):
    language = normalize_language_code(language or get_current_language())
    return UI_TRANSLATIONS.get(language, UI_TRANSLATIONS[DEFAULT_LANGUAGE]).get(
        key,
        UI_TRANSLATIONS[DEFAULT_LANGUAGE].get(key, key)
    )


# --- Content language / AI feed language helpers ---
LANGUAGE_KEYWORDS = {
    "ru": ["и", "это", "как", "что", "для", "если", "человек", "бизнес", "ресторан", "работа", "деньги", "можно"],
    "en": ["the", "and", "for", "you", "with", "business", "startup", "restaurant", "money", "people", "work"],
    "de": ["und", "der", "die", "das", "für", "mit", "nicht", "arbeit", "geschäft", "restaurant", "menschen"],
    "tr": ["ve", "bir", "için", "ile", "de", "da", "insan", "iş", "restoran", "para", "nasıl", "güzel"],
    "tk": ["we", "üçin", "bilen", "adam", "iş", "pul", "nädip", "ýaly", "men", "sen", "restoran"],
    "uz": ["va", "uchun", "bilan", "odam", "ish", "pul", "qanday", "men", "siz", "restoran"],
    "ar": ["و", "في", "من", "على", "هذا", "عمل", "مطعم", "ناس", "مال", "كيف"],
    "es": ["el", "la", "de", "que", "para", "con", "negocio", "restaurante", "trabajo", "dinero"],
    "fr": ["le", "la", "de", "pour", "avec", "entreprise", "restaurant", "travail", "argent", "personnes"],
    "it": ["il", "la", "di", "per", "con", "business", "ristorante", "lavoro", "soldi", "persone"],
    "pt": ["o", "a", "de", "para", "com", "negócio", "restaurante", "trabalho", "dinheiro", "pessoas"],
    "pl": ["i", "dla", "jest", "biznes", "restauracja", "praca", "pieniądze", "ludzie"],
    "nl": ["en", "de", "het", "voor", "met", "bedrijf", "restaurant", "werk", "geld", "mensen"],
    "sv": ["och", "för", "med", "företag", "restaurang", "arbete", "pengar", "människor"],
    "id": ["dan", "untuk", "dengan", "bisnis", "restoran", "kerja", "uang", "orang"],
    "ms": ["dan", "untuk", "dengan", "bisnes", "restoran", "kerja", "wang", "orang"],
    "sw": ["na", "kwa", "biashara", "mgahawa", "kazi", "pesa", "watu"]
}

CYRILLIC_LANGUAGE_HINTS = {"ru", "be", "bg", "kk", "ky", "mk", "mn", "sr", "tg", "uk"}
LATIN_LANGUAGE_HINTS = {"af", "az", "bs", "ca", "cs", "da", "de", "en", "es", "et", "fi", "fr", "hr", "hu", "id", "it", "lt", "lv", "ms", "nl", "no", "pl", "pt", "ro", "sk", "sl", "sq", "sv", "sw", "tk", "tr", "uz", "vi"}


def detect_content_language(text_value):
    text_value = clean_text(text_value).lower()

    if not text_value:
        return "unknown"

    arabic_chars = sum(1 for char in text_value if "\u0600" <= char <= "\u06FF")
    if arabic_chars >= 3:
        return "ar"

    hebrew_chars = sum(1 for char in text_value if "\u0590" <= char <= "\u05FF")
    if hebrew_chars >= 3:
        return "he"

    devanagari_chars = sum(1 for char in text_value if "\u0900" <= char <= "\u097F")
    if devanagari_chars >= 3:
        return "hi"

    bengali_chars = sum(1 for char in text_value if "\u0980" <= char <= "\u09FF")
    if bengali_chars >= 3:
        return "bn"

    punjabi_chars = sum(1 for char in text_value if "\u0A00" <= char <= "\u0A7F")
    if punjabi_chars >= 3:
        return "pa"

    tamil_chars = sum(1 for char in text_value if "\u0B80" <= char <= "\u0BFF")
    if tamil_chars >= 3:
        return "ta"

    telugu_chars = sum(1 for char in text_value if "\u0C00" <= char <= "\u0C7F")
    if telugu_chars >= 3:
        return "te"

    thai_chars = sum(1 for char in text_value if "\u0E00" <= char <= "\u0E7F")
    if thai_chars >= 3:
        return "th"

    khmer_chars = sum(1 for char in text_value if "\u1780" <= char <= "\u17FF")
    if khmer_chars >= 3:
        return "km"

    korean_chars = sum(1 for char in text_value if "\uAC00" <= char <= "\uD7AF")
    if korean_chars >= 3:
        return "ko"

    japanese_chars = sum(1 for char in text_value if "\u3040" <= char <= "\u30FF")
    if japanese_chars >= 3:
        return "ja"

    chinese_chars = sum(1 for char in text_value if "\u4E00" <= char <= "\u9FFF")
    if chinese_chars >= 3:
        return "zh"

    cyrillic_chars = sum(1 for char in text_value if "\u0400" <= char <= "\u04FF")
    latin_chars = sum(1 for char in text_value if "a" <= char <= "z" or "ç" <= char <= "ž")

    language_scores = {}
    words = [word.strip(".,!?;:()[]{}\"'") for word in text_value.split()]

    for language_code, keywords in LANGUAGE_KEYWORDS.items():
        score = 0
        for word in words:
            if word in keywords:
                score += 3
            for keyword in keywords:
                if len(keyword) >= 4 and keyword in word:
                    score += 1

        language_scores[language_code] = score

    if cyrillic_chars > latin_chars and cyrillic_chars >= 4:
        language_scores["ru"] = language_scores.get("ru", 0) + 4

    best_language = max(language_scores, key=language_scores.get)
    best_score = language_scores.get(best_language, 0)

    if best_score <= 0:
        if cyrillic_chars >= 4:
            return "ru"
        if latin_chars >= 4:
            return "en"
        return "unknown"

    return best_language


def get_user_language_signals(user):
    signals = []

    ui_language = get_current_language(user)
    if ui_language:
        signals.append(ui_language)

    raw_languages = getattr(user, "languages", [])
    if isinstance(raw_languages, str):
        language_items = raw_languages.split(",")
    elif isinstance(raw_languages, list):
        language_items = raw_languages
    else:
        language_items = []

    language_aliases = {
        "russian": "ru", "русский": "ru", "rus": "ru",
        "english": "en", "английский": "en", "eng": "en",
        "german": "de", "deutsch": "de", "немецкий": "de",
        "turkish": "tr", "türkçe": "tr", "турецкий": "tr",
        "turkmen": "tk", "türkmençe": "tk", "туркменский": "tk",
        "uzbek": "uz", "oʻzbekcha": "uz", "узбекский": "uz",
        "arabic": "ar", "арабский": "ar", "العربية": "ar",
        "spanish": "es", "español": "es", "испанский": "es",
        "french": "fr", "français": "fr", "французский": "fr",
        "italian": "it", "italiano": "it", "итальянский": "it",
        "portuguese": "pt", "português": "pt", "португальский": "pt",
        "polish": "pl", "polski": "pl", "польский": "pl",
        "ukrainian": "uk", "українська": "uk", "украинский": "uk",
        "chinese": "zh", "中文": "zh", "китайский": "zh",
        "japanese": "ja", "日本語": "ja", "японский": "ja",
        "korean": "ko", "한국어": "ko", "корейский": "ko"
    }

    for language_item in language_items:
        raw_language = clean_text(language_item).lower()
        normalized = language_aliases.get(raw_language, normalize_content_language_code(raw_language))
        if normalized and normalized != "unknown" and normalized not in signals:
            signals.append(normalized)

    return [item for item in signals if item and item != "unknown"]


def score_language_match(user, content_language):
    content_language = normalize_content_language_code(content_language)
    user_languages = get_user_language_signals(user)

    if content_language in user_languages:
        return 30, "Контент на понятном для вас языке"

    if content_language == "unknown":
        return 0, "Язык контента не определён"

    if content_language == "en":
        return 4, "Английский контент показан ниже, если язык не основной"

    return -12, "Контент на другом языке, AI может перевести его позже"


@app.route("/set_language/<email>/<language>")
@login_required
def set_language_route(email, language):
    user = find_user_by_email(email)

    if user is None:
        return "User not found"

    language = normalize_language_code(language)
    session["language"] = language
    user.language = language
    save_users_to_json(users)

    redirect_to = request.headers.get("Referer", f"/dashboard/{user.email}")
    return redirect(redirect_to)

def validate_csrf_token():
    session_token = session.get("csrf_token")
    form_token = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")

    if not session_token or not form_token or session_token != form_token:
        log_security_event("csrf_failed", session.get("user_email", ""), request.path)
        abort(403)

@app.before_request
def allow_local_home_page_during_development():
    host = str(request.host or "").lower().strip()
    local_hosts = {
        "localhost",
        "localhost:5000",
        "127.0.0.1",
        "127.0.0.1:5000",
    }

    if request.method == "GET" and request.path == "/" and host in local_hosts:
        html = open_html("index.html")
        return render_template_string(html, csrf_token_input=csrf_input())

    return None


@app.errorhandler(403)
def forbidden_page(error):
    return f"""
    <html>
    <head>
        <meta charset="UTF-8">
        <title>403</title>
        {page_style()}
    </head>
    <body>
        <div class="card">
            <h1>🔒 Доступ запрещён</h1>
            <p>Сработала защита. Для локального теста откройте главную страницу заново.</p>
            <button onclick="window.location.href='/'">Открыть главную</button>
        </div>
    </body>
    </html>
    """, 403


@app.after_request
def add_security_headers(response):
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(self), microphone=(self), geolocation=(self)"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "img-src 'self' data: https:; "
        "style-src 'self' 'unsafe-inline'; "
        "script-src 'self' 'unsafe-inline'; "
        "media-src 'self' data: https:;"
    )
    if request.is_secure:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
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

    if mime_type not in allowed_types:
        return False

    try:
        current_position = file.stream.tell()
        file.stream.seek(0)
        header = file.stream.read(64)
        file.stream.seek(current_position)
    except:
        return False

    if mime_type == "image/jpeg":
        return header.startswith(b"\xff\xd8\xff")

    if mime_type == "image/png":
        return header.startswith(b"\x89PNG\r\n\x1a\n")

    if mime_type == "image/gif":
        return header.startswith(b"GIF87a") or header.startswith(b"GIF89a")

    if mime_type == "image/webp":
        return header.startswith(b"RIFF") and header[8:12] == b"WEBP"

    if mime_type in {"video/mp4", "video/quicktime", "audio/mp4"}:
        return b"ftyp" in header[:32]

    if mime_type == "video/webm":
        return header.startswith(b"\x1a\x45\xdf\xa3")

    if mime_type == "audio/mpeg":
        return header.startswith(b"ID3") or (len(header) >= 2 and header[0] == 0xFF and (header[1] & 0xE0) == 0xE0)

    if mime_type == "audio/wav":
        return header.startswith(b"RIFF") and header[8:12] == b"WAVE"

    if mime_type == "audio/ogg":
        return header.startswith(b"OggS")

    return False

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


# --- Email / SMS verification helpers ---
def load_verification_codes():
    try:
        with open(VERIFICATION_CODES_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)
            if isinstance(data, dict):
                return data
            return {}
    except:
        return {}


def save_verification_codes(data):
    with open(VERIFICATION_CODES_FILE, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4, ensure_ascii=False)


def normalize_email(email):
    return str(email or "").strip().lower()


def normalize_phone(phone):
    value = str(phone or "").strip()
    value = value.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    return value


# --- Internal phone email helpers ---
def make_internal_phone_email(phone_value):
    phone_value = normalize_phone(phone_value)
    digits = "".join(ch for ch in phone_value if ch.isdigit())

    if not digits:
        return ""

    return f"phone_{digits}@phone.local"


def is_internal_phone_email(email_value):
    email_value = normalize_email(email_value)
    return email_value.startswith("phone_") and email_value.endswith("@phone.local")


def get_user_public_contact(user):
    if user is None:
        return ""

    phone_value = normalize_phone(getattr(user, "phone", ""))
    email_value = normalize_email(getattr(user, "email", ""))

    if email_value and not is_internal_phone_email(email_value):
        return email_value

    if phone_value:
        return phone_value

    return email_value


def generate_verification_code():
    return "".join(str(secrets.randbelow(10)) for _ in range(VERIFICATION_CODE_LENGTH))


def create_verification_code(purpose, contact_type, contact_value):
    contact_type = str(contact_type or "").strip().lower()
    if contact_type == "email":
        contact_value = normalize_email(contact_value)
    elif contact_type == "phone":
        contact_value = normalize_phone(contact_value)
    else:
        return None

    if not contact_value:
        return None

    data = load_verification_codes()
    code = generate_verification_code()
    key = f"{purpose}:{contact_type}:{contact_value}"

    existing_item = data.get(key)
    if existing_item:
        try:
            created_at = datetime.strptime(existing_item.get("created_at", ""), "%Y-%m-%d %H:%M:%S")
            seconds_since_created = int((datetime.now() - created_at).total_seconds())
            if seconds_since_created < VERIFICATION_RESEND_SECONDS:
                log_security_event("verification_resend_limited", contact_value, f"purpose={purpose};type={contact_type}")
                return None
        except:
            pass

    data[key] = {
        "code": code,
        "purpose": str(purpose or "").strip().lower(),
        "contact_type": contact_type,
        "contact_value": contact_value,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "expires_at": (datetime.now() + timedelta(minutes=VERIFICATION_CODE_MINUTES)).strftime("%Y-%m-%d %H:%M:%S"),
        "used": False,
        "attempts": 0
    }

    save_verification_codes(data)
    return code


def verify_contact_code(purpose, contact_type, contact_value, code):
    contact_type = str(contact_type or "").strip().lower()
    if contact_type == "email":
        contact_value = normalize_email(contact_value)
    elif contact_type == "phone":
        contact_value = normalize_phone(contact_value)
        if purpose in {"account_verify", "login_2fa", "password_reset"}:
            if not twilio_client or not TWILIO_VERIFY_SERVICE_SID:
                print("TWILIO ERROR: Verify settings are missing in .env")
                return False

            try:
                verification_check = twilio_client.verify.v2.services(
                    TWILIO_VERIFY_SERVICE_SID
                ).verification_checks.create(
                    to=contact_value,
                    code=str(code or "").strip()
                )

                if verification_check.status == "approved":
                    log_security_event("twilio_verify_approved", contact_value, f"purpose={purpose}")
                    return True

                log_security_event("twilio_verify_rejected", contact_value, f"purpose={purpose};status={verification_check.status}")
                return False
            except Exception as error:
                print("TWILIO VERIFY CHECK ERROR:", error)
                log_security_event("twilio_verify_check_failed", contact_value, str(error))
                return False
    else:
        return False

    key = f"{purpose}:{contact_type}:{contact_value}"
    data = load_verification_codes()
    item = data.get(key)

    if not item or item.get("used"):
        return False

    attempts = int(item.get("attempts", 0))
    if attempts >= MAX_VERIFICATION_ATTEMPTS:
        log_security_event("verification_attempts_locked", contact_value, f"purpose={purpose};type={contact_type}")
        return False

    try:
        expires_at = datetime.strptime(item.get("expires_at", ""), "%Y-%m-%d %H:%M:%S")
    except:
        return False

    if datetime.now() > expires_at:
        return False

    if not secrets.compare_digest(str(item.get("code", "")).strip(), str(code or "").strip()):
        item["attempts"] = attempts + 1
        data[key] = item
        save_verification_codes(data)
        log_security_event("verification_code_failed", contact_value, f"purpose={purpose};type={contact_type};attempt={item['attempts']}")
        return False

    item["used"] = True
    data[key] = item
    save_verification_codes(data)
    return True



def send_email_verification_code(email_address, code):
    smtp_host = os.environ.get("SMTP_HOST", "").strip()
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER", "").strip()
    smtp_password = os.environ.get("SMTP_PASSWORD", "").strip()
    smtp_from = os.environ.get("SMTP_FROM", smtp_user).strip()

    if not smtp_host or not smtp_user or not smtp_password or not smtp_from:
        print("GMAIL ERROR: SMTP settings are missing in .env")
        return False

    message = EmailMessage()
    message["Subject"] = "AI Match Life verification code"
    message["From"] = smtp_from
    message["To"] = email_address
    message.set_content(
        f"Ваш код подтверждения AI Match Life: {code}\n\n"
        "Код действует ограниченное время. Если вы не запрашивали этот код, просто игнорируйте письмо."
    )

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.send_message(message)
        print(f"GMAIL SENT: code sent to {email_address}")
        return True
    except Exception as error:
        print("GMAIL ERROR:", error)
        log_security_event("email_send_failed", email_address, str(error))
        return False


def send_sms_verification_code(phone_number, code=None):
    phone_number = normalize_phone(phone_number)

    if not phone_number:
        return False

    if not twilio_client or not TWILIO_VERIFY_SERVICE_SID:
        print("TWILIO ERROR: Verify settings are missing in .env")
        return False

    try:
        verification = twilio_client.verify.v2.services(
            TWILIO_VERIFY_SERVICE_SID
        ).verifications.create(
            to=phone_number,
            channel="sms"
        )
        print(f"TWILIO VERIFY SENT: {phone_number} status={verification.status}")
        return True
    except Exception as error:
        print("TWILIO VERIFY ERROR:", error)
        log_security_event("twilio_verify_send_failed", phone_number, str(error))
        return False


def send_verification_code(contact_type, contact_value, code):
    contact_type = str(contact_type or "").strip().lower()
    sent = False

    if contact_type == "email":
        sent = send_email_verification_code(normalize_email(contact_value), code)
    elif contact_type == "phone":
        sent = send_sms_verification_code(normalize_phone(contact_value))

    if sent:
        log_security_event("verification_code_sent", contact_value, f"type={contact_type}")
        return True

    # Local development fallback: show code in terminal when real provider is not configured.
    log_security_event("verification_code_created", contact_value, f"type={contact_type};delivery=terminal_fallback")
    print(f"VERIFICATION CODE for {contact_type} {contact_value}: {code}")
    return False


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
@login_required
def typing_status(sender_email, receiver_email):
    validate_csrf_token()
    data = load_typing_status()

    data[f"{sender_email}->{receiver_email}"] = datetime.now().timestamp()

    save_typing_status(data)

    return "OK"


# --- Presence status route ---
@app.route("/presence/<email>", methods=["POST"])
@login_required
def presence_status(email):
    validate_csrf_token()
    data = load_presence_status()
    data[email] = datetime.now().timestamp()
    save_presence_status(data)
    return "OK"
        



def safe_text(value):
    if value is None or value == "":
        return "Nicht angegeben"
    return clean_text(value)


def render_ai_text(value):
    text = clean_text(value)
    text = text.replace("**", "__BOLD__", 1) if text.count("**") == 1 else text

    parts = text.split("**")
    rendered = ""
    for index, part in enumerate(parts):
        safe_part = clean_text(part)
        if index % 2 == 1:
            rendered += f"<strong>{safe_part}</strong>"
        else:
            rendered += safe_part

    rendered = rendered.replace("\n", "<br>")
    rendered = rendered.replace("__BOLD__", "**")
    return rendered


def clean_text(value):
    return bleach.clean(str(value or "").strip(), tags=[], strip=True)


def safe_list(values):
    if values is None or len(values) == 0:
        return "Nicht angegeben"
    return ", ".join(clean_text(item) for item in values)


def load_ai_core_memory():
    try:
        with open("ai_core_memory.json", "r", encoding="utf-8") as file:
            data = json.load(file)
            if isinstance(data, dict):
                return data
            return {}
    except Exception:
        return {}


def save_ai_core_memory(data):
    with open("ai_core_memory.json", "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4, ensure_ascii=False)


def record_ai_core_memory(user_email, mode, question, answer):
    user_email = normalize_email(user_email)

    if not user_email:
        return

    try:
        data = load_ai_core_memory()
        user_items = data.get(user_email, [])
        if not isinstance(user_items, list):
            user_items = []

        user_items.append({
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "mode": clean_text(mode),
            "question": clean_text(question),
            "answer": clean_text(answer)
        })

        data[user_email] = user_items[-100:]
        save_ai_core_memory(data)
    except Exception as error:
        log_security_event("ai_core_memory_failed", user_email, str(error))


def get_recent_ai_core_memory(user_email, limit=5):
    user_email = normalize_email(user_email)

    try:
        data = load_ai_core_memory()
        user_items = data.get(user_email, [])
        if not isinstance(user_items, list):
            return ""

        recent_items = user_items[-limit:]
        memory_lines = []
        for item in recent_items:
            memory_lines.append(
                "\n".join([
                    f"Time: {clean_text(item.get('time', ''))}",
                    f"Mode: {clean_text(item.get('mode', ''))}",
                    f"Question: {clean_text(item.get('question', ''))}",
                    f"Answer: {clean_text(item.get('answer', ''))[:900]}"
                ])
            )

        return "\n\n---\n\n".join(memory_lines)
    except Exception:
        return ""


# Render AI Core history as HTML for the user
def render_ai_core_history(user_email, limit=12):
    user_email = normalize_email(user_email)

    try:
        data = load_ai_core_memory()
        user_items = data.get(user_email, [])
        if not isinstance(user_items, list) or not user_items:
            return """
            <aside style="background:#1e293b;border:1px solid rgba(148,163,184,0.10);border-radius:26px;padding:18px;height:fit-content;position:sticky;top:18px;">
                <h2 style="margin:0 0 12px 0;font-size:20px;">История</h2>
                <p style="margin:0;color:#94a3b8;line-height:1.45;font-size:14px;">Пока нет прошлых диалогов.</p>
            </aside>
            """

        history_html = ""
        total_items = len(user_items)
        visible_items = list(enumerate(user_items[-limit:], start=max(total_items - limit, 0)))

        for item_index, item in reversed(visible_items):
            mode_title = get_ai_core_mode_config(item.get("mode", "general")).get("title", "AI Core")
            question_text = clean_text(item.get("question", ""))
            if len(question_text) > 95:
                question_text = question_text[:95] + "..."

            history_html += f"""
            <a href="/ai_copilot/{safe_text(user_email)}?history={item_index}" style="display:block;background:#0f172a;border:1px solid rgba(96,165,250,0.14);border-radius:18px;padding:13px;margin-bottom:10px;cursor:pointer;text-decoration:none;">
                <div style="color:#bfdbfe;font-weight:bold;font-size:13px;margin-bottom:6px;">{safe_text(mode_title)}</div>
                <div style="color:#e5e7eb;font-size:14px;line-height:1.45;">{safe_text(question_text)}</div>
                <div style="color:#64748b;font-size:12px;margin-top:8px;">{safe_text(item.get('time', ''))}</div>
            </a>
            """

        return f"""
        <aside style="background:#1e293b;border:1px solid rgba(148,163,184,0.10);border-radius:26px;padding:18px;height:fit-content;position:sticky;top:18px;max-height:calc(100vh - 36px);overflow:auto;">
            <h2 style="margin:0 0 12px 0;font-size:20px;">История</h2>
            <p style="margin:0 0 14px 0;color:#94a3b8;line-height:1.45;font-size:14px;">Последние диалоги AI Core.</p>
            {history_html}
        </aside>
        """
    except Exception as error:
        log_security_event("ai_core_history_render_failed", user_email, str(error))
        return ""


# --- Render selected AI Core history item ---
def render_selected_ai_core_history(user_email, history_index):
    user_email = normalize_email(user_email)

    try:
        history_index = int(history_index)
    except Exception:
        return ""

    try:
        data = load_ai_core_memory()
        user_items = data.get(user_email, [])
        if not isinstance(user_items, list):
            return ""

        if history_index < 0 or history_index >= len(user_items):
            return ""

        item = user_items[history_index]
        mode_title = get_ai_core_mode_config(item.get("mode", "general")).get("title", "AI Core")

        return f"""
        <div style="background:#0f172a;border:1px solid rgba(96,165,250,0.22);border-radius:24px;padding:22px;margin-top:18px;">
            <div style="display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-bottom:14px;">
                <h2 style="margin:0;color:#bfdbfe;">Открытый диалог</h2>
                <span style="color:#64748b;font-size:13px;">{safe_text(item.get('time', ''))}</span>
            </div>
            <div style="color:#93c5fd;font-size:13px;font-weight:bold;margin-bottom:12px;">{safe_text(mode_title)}</div>
            <div style="background:#1e293b;border-radius:18px;padding:14px;margin-bottom:14px;color:#e5e7eb;line-height:1.6;">
                <b>Вы:</b> {safe_text(item.get('question', ''))}
            </div>
            <div style="line-height:1.7;color:#dbeafe;font-size:16px;">{render_ai_text(item.get('answer', ''))}</div>
        </div>
        """
    except Exception as error:
        log_security_event("ai_core_selected_history_failed", user_email, str(error))
        return ""



def get_openai_status():
    openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
    openai_model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"

    return {
        "enabled": openai_key.startswith("sk-"),
        "key": openai_key,
        "model": openai_model
    }

def get_openai_ssl_context():
    try:
        import certifi
        import ssl
        return ssl.create_default_context(cafile=certifi.where())
    except Exception as error:
        print("OPENAI SSL CONTEXT ERROR:", error)
        return None

def call_openai_chat(messages, temperature=0.2, max_tokens=900):
    status = get_openai_status()

    if not status.get("enabled"):
        return "AI Core пока работает в резервном режиме: OPENAI_API_KEY не подключён."

    payload = {
        "model": status.get("model", "gpt-4o-mini"),
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens
    }

    try:
        request_data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=request_data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {status.get('key')}"
            },
            method="POST"
        )

        with urllib.request.urlopen(req, timeout=35, context=get_openai_ssl_context()) as response:
            result = json.loads(response.read().decode("utf-8"))
            return clean_text(result["choices"][0]["message"]["content"])

    except urllib.error.HTTPError as error:
        status_code = getattr(error, "code", "unknown")
        reason = getattr(error, "reason", "")
        error_body = ""

        try:
            error_body = error.read().decode("utf-8", errors="replace")
        except Exception:
            error_body = ""

        error_text = f"HTTP {status_code} {reason}. {error_body}".strip()
        print("OPENAI API HTTP ERROR:", error_text)
        log_security_event("openai_core_http_failed", session.get("user_email", ""), error_text)

        lowered_error = error_text.lower()

        if "insufficient_quota" in lowered_error or "quota" in lowered_error or "billing" in lowered_error:
            return "OpenAI ключ найден, но у аккаунта нет доступной квоты/баланса или не включён Billing. Проверьте OpenAI → Billing / Usage."

        if "invalid_api_key" in lowered_error or "incorrect api key" in lowered_error or "401" in lowered_error:
            return "OpenAI ключ неправильный, удалён или больше не работает. Нужно создать новый API key и заменить его в .env."

        if "model" in lowered_error and ("not found" in lowered_error or "does not exist" in lowered_error or "not supported" in lowered_error):
            return f"OpenAI ключ работает, но модель недоступна: {safe_text(status.get('model'))}. Проверьте OPENAI_MODEL в .env."

        if "rate_limit" in lowered_error or "429" in lowered_error:
            return "OpenAI ограничил запросы. Возможные причины: нет баланса, превышен лимит или слишком много запросов. Проверьте Usage / Limits."

        clean_error = clean_text(error_text)
        if not clean_error:
            clean_error = f"HTTP {status_code} {reason}"

        return f"AI Core получил ошибку от OpenAI: {clean_error[:1200]}"

    except urllib.error.URLError as error:
        error_text = str(getattr(error, "reason", error))
        print("OPENAI API NETWORK ERROR:", error_text)
        log_security_event("openai_core_network_failed", session.get("user_email", ""), error_text)
        return f"AI Core не смог подключиться к OpenAI. Проверьте интернет/DNS/VPN. Деталь: {safe_text(error_text)[:500]}"

    except Exception as error:
        error_text = str(error)
        print("OPENAI API UNKNOWN ERROR:", error_text)
        log_security_event("openai_core_failed", session.get("user_email", ""), error_text)

        if not error_text:
            error_text = "unknown error"

        return f"AI Core получил внутреннюю ошибку: {safe_text(error_text)[:800]}"


def build_user_ai_context(user):
    if user is None:
        return "Пользователь не найден."

    learning_data = {}
    try:
        all_learning = load_ai_feed_learning()
        learning_data = all_learning.get(normalize_email(user.email), {})
        if not isinstance(learning_data, dict):
            learning_data = {}
    except Exception:
        learning_data = {}

    top_languages = learning_data.get("languages", {}) if isinstance(learning_data.get("languages", {}), dict) else {}
    top_types = learning_data.get("types", {}) if isinstance(learning_data.get("types", {}), dict) else {}
    top_hashtags = learning_data.get("hashtags", {}) if isinstance(learning_data.get("hashtags", {}), dict) else {}
    top_locations = learning_data.get("locations", {}) if isinstance(learning_data.get("locations", {}), dict) else {}
    recent_ai_core_memory = get_recent_ai_core_memory(getattr(user, "email", ""), limit=10)

    return "\n".join([
        f"Name: {clean_text(getattr(user, 'name', ''))}",
        f"Profession: {clean_text(getattr(user, 'profession', ''))}",
        f"Country: {clean_text(getattr(user, 'country', ''))}",
        f"Looking for: {clean_text(getattr(user, 'looking_for', ''))}",
        f"Bio: {clean_text(getattr(user, 'bio', ''))}",
        f"Languages: {safe_list(getattr(user, 'languages', []))}",
        f"Goals: {safe_list(getattr(user, 'goals', []))}",
        f"Interests: {safe_list(getattr(user, 'interests', []))}",
        f"Skills: {safe_list(getattr(user, 'skills', []))}",
        f"Trust score: {getattr(user, 'trust_score', 0)}",
        f"AI feed learned languages: {json.dumps(top_languages, ensure_ascii=False)}",
        f"AI feed learned content types: {json.dumps(top_types, ensure_ascii=False)}",
        f"AI feed learned hashtags: {json.dumps(top_hashtags, ensure_ascii=False)}",
        f"AI feed learned locations: {json.dumps(top_locations, ensure_ascii=False)}",
        f"Recent AI Core memory: {recent_ai_core_memory if recent_ai_core_memory else 'No previous AI Core memory yet'}"
    ])


def get_ai_core_mode_config(mode):
    mode = clean_text(mode).strip().lower()

    modes = {
        "profile": {
            "title": "AI Profile Coach",
            "instruction": "Analyze the user's profile and give practical steps to improve trust, clarity, attractiveness, and usefulness inside AI Match Life. Focus on profile quality, positioning, goals, skills, and what to add or rewrite."
        },
        "match": {
            "title": "AI Match Advisor",
            "instruction": "Help the user understand what kind of people they should meet: friends, mentors, business partners, clients, investors, local contacts, or communities. Give matching logic and concrete next steps."
        },
        "business": {
            "title": "AI Business Helper",
            "instruction": "Help the user with business development, networking, finding partners, clients, sponsors, project positioning, and step-by-step execution. Be realistic and practical."
        },
        "content": {
            "title": "AI Content Ideas",
            "instruction": "Create useful content ideas for AI Discover based on the user's goals, interests, profession, languages, and learned feed behavior. Give post ideas, hooks, hashtags, and why each idea can work."
        },
        "life": {
            "title": "AI Life Assistant",
            "instruction": "Help the user with personal planning, learning, discipline, daily progress, priorities, and clear next actions. Be supportive but realistic."
        },
        "general": {
            "title": "AI Core General",
            "instruction": "Answer the user's question as the main AI assistant inside AI Match Life. Use context, be honest, practical, and structured."
        }
    }

    return modes.get(mode, modes["general"])


def generate_ai_copilot_answer(user, user_question, mode="general"):
    user_question = clean_text(user_question)
    mode_config = get_ai_core_mode_config(mode)

    if not user_question:
        return "Напишите вопрос или задачу для AI."

    user_context = build_user_ai_context(user)

    system_prompt = (
        "You are AI Match Life Core Assistant. "
        "You are the intelligent layer of the app, not a generic chatbot. "
        "Use the user's profile, goals, interests, skills, languages, trust signals, and AI Discover learning. "
        "Do not invent facts. If something is missing, say what is missing and what the user should add. "
        "Be practical, structured, and honest. Answer in Russian unless the user clearly asks another language. "
        f"Current mode: {mode_config.get('title')}. "
        f"Mode instruction: {mode_config.get('instruction')}"
    )

    user_prompt = (
        "User profile and AI memory context:\n"
        f"{user_context}\n\n"
        "User question:\n"
        f"{user_question}\n\n"
        "Give a professional answer with clear next steps."
    )

    return call_openai_chat([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ], temperature=0.25, max_tokens=1200)


# --- News module helpers ---
def load_news():
    try:
        with open(NEWS_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)
            if isinstance(data, list):
                return data
            return []
    except Exception:
        return []


def save_news(news_items):
    with open(NEWS_FILE, "w", encoding="utf-8") as file:
        json.dump(news_items[-500:], file, indent=4, ensure_ascii=False)


def render_news_items(news_items):
    if not news_items:
        return """
        <div style="background:#1e293b;border:1px solid rgba(148,163,184,0.10);border-radius:26px;padding:24px;color:#94a3b8;line-height:1.6;">
            Пока новостей нет.
        </div>
        """

    def render_news_media(media_items):
        if not isinstance(media_items, list) or not media_items:
            return ""

        media_html = ""
        for media in media_items:
            media_url = safe_text(media.get("url", ""))
            media_type = clean_text(media.get("type", ""))

            if not media_url or media_url == "Nicht angegeben":
                continue

            if media_type == "video":
                media_html += f"""
                <video controls playsinline style="width:100%;max-height:520px;border-radius:22px;margin-top:16px;background:#020617;object-fit:cover;">
                    <source src="{media_url}">
                </video>
                """
            else:
                media_html += f"""
                <img src="{media_url}" alt="News media" style="width:100%;max-height:520px;border-radius:22px;margin-top:16px;object-fit:cover;background:#020617;">
                """

        return media_html

    html = ""

    for item in reversed(news_items):
        title = safe_text(item.get("title", ""))
        body = render_ai_text(item.get("body", ""))
        author = safe_text(item.get("author_name", "AI Match Life"))
        created_at = safe_text(item.get("created_at", ""))
        source = clean_text(item.get("source", ""))
        location = clean_text(item.get("location", ""))
        media_html = render_news_media(item.get("media", []))
        source_html = ""
        location_html = ""

        if source:
            source_html = f"""
            <a href="{safe_text(source)}" target="_blank" rel="noopener noreferrer" style="display:inline-block;margin-top:14px;color:#93c5fd;text-decoration:none;font-weight:bold;">Источник</a>
            """

        if location:
            location_html = f"""
            <div style="display:inline-flex;margin-top:12px;background:#0f172a;color:#cbd5e1;border:1px solid rgba(148,163,184,0.14);border-radius:999px;padding:8px 12px;font-size:13px;font-weight:bold;">📍 {safe_text(location)}</div>
            """

        html += f"""
        <article style="background:#1e293b;border:1px solid rgba(148,163,184,0.10);border-radius:28px;padding:24px;margin-bottom:16px;box-shadow:0 18px 42px rgba(0,0,0,0.20);">
            <div style="display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-bottom:12px;">
                <span style="color:#94a3b8;font-size:13px;">{author}</span>
                <span style="color:#64748b;font-size:13px;">{created_at}</span>
            </div>
            <h2 style="margin:0 0 12px 0;color:#f8fafc;line-height:1.25;font-size:24px;">{title}</h2>
            <div style="color:#cbd5e1;line-height:1.75;font-size:16px;">{body}</div>
            {media_html}
            {location_html}
            {source_html}
        </article>
        """

    return html


@app.route("/news/<email>", methods=["GET", "POST"])
@login_required
def news_page(email):
    user = find_user_by_email(email)

    if user is None:
        return "User not found"

    message = ""

    if request.method == "POST":
        validate_csrf_token()
        title = clean_text(request.form.get("title", ""))
        body = clean_text(request.form.get("body", ""))
        source = clean_text(request.form.get("source", ""))
        location = clean_text(request.form.get("location", ""))
        media_items = []

        try:
            files = request.files.getlist("media")
            for uploaded_file in files:
                if uploaded_file and uploaded_file.filename and allowed_file(uploaded_file.filename) and allowed_mime_type(uploaded_file):
                    original_name = secure_filename(uploaded_file.filename)
                    extension = original_name.rsplit(".", 1)[1].lower() if "." in original_name else ""
                    stored_name = f"news_{secrets.token_urlsafe(10)}_{original_name}"
                    file_path = os.path.join(UPLOAD_FOLDER, stored_name)
                    uploaded_file.save(file_path)
                    media_type = "video" if extension in {"mp4", "webm", "mov"} else "image"
                    media_items.append({
                        "url": f"/static/uploads/{stored_name}",
                        "type": media_type,
                        "filename": stored_name
                    })
        except Exception as error:
            log_security_event("news_media_upload_failed", normalize_email(user.email), str(error))

        if not title or not body:
            message = "Заполните заголовок и текст."
        else:
            news_items = load_news()
            news_items.append({
                "id": secrets.token_urlsafe(10),
                "author_email": normalize_email(user.email),
                "author_name": clean_text(getattr(user, "name", "AI Match Life")),
                "title": title,
                "body": body,
                "source": source,
                "location": location,
                "media": media_items,
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
            save_news(news_items)
            return redirect(f"/news/{safe_text(user.email)}")

    news_items = load_news()
    news_html = render_news_items(news_items)

    return f"""
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>News - AI Match Life</title>
    </head>
    <body style="margin:0;background:#0f172a;color:white;font-family:Arial,sans-serif;padding:28px;">
        <div style="max-width:1120px;margin:auto;">
            <a href="/dashboard/{safe_text(user.email)}" style="display:inline-block;color:white;text-decoration:none;background:#334155;padding:12px 16px;border-radius:14px;margin-bottom:18px;font-weight:bold;">← Назад</a>

            <section style="background:linear-gradient(135deg,#1e293b,#111827);border:1px solid rgba(148,163,184,0.14);border-radius:30px;padding:30px;margin-bottom:22px;">
                <h1 style="margin:0;font-size:34px;">🗞 News</h1>
            </section>

            <div style="display:grid;grid-template-columns:minmax(280px,360px) minmax(0,1fr);gap:18px;align-items:start;">
                <aside style="background:#1e293b;border:1px solid rgba(148,163,184,0.10);border-radius:28px;padding:22px;position:sticky;top:18px;">
                    <h2 style="margin:0 0 14px 0;font-size:20px;">Добавить новость</h2>
                    <p style="color:#facc15;margin:0 0 12px 0;line-height:1.45;">{safe_text(message) if message else ''}</p>
                    <form method="POST" enctype="multipart/form-data">
                        {csrf_input()}
                        <input name="title" placeholder="Заголовок" required style="width:100%;box-sizing:border-box;background:#0f172a;color:white;border:1px solid #334155;border-radius:14px;padding:12px;margin-bottom:10px;">
                        <textarea name="body" placeholder="Текст новости..." required style="width:100%;min-height:170px;box-sizing:border-box;background:#0f172a;color:white;border:1px solid #334155;border-radius:14px;padding:12px;margin-bottom:10px;line-height:1.5;"></textarea>
                        <label style="display:block;background:#0f172a;color:white;border:1px solid #334155;border-radius:14px;padding:12px;margin-bottom:10px;cursor:pointer;font-weight:bold;">
                            📷 Фото / 🎥 Видео
                            <input type="file" name="media" accept="image/*,video/*" capture="environment" multiple style="display:none;">
                        </label>
                        <input name="location" placeholder="📍 Местоположение" style="width:100%;box-sizing:border-box;background:#0f172a;color:white;border:1px solid #334155;border-radius:14px;padding:12px;margin-bottom:10px;">
                        <input name="source" placeholder="Источник / ссылка" style="width:100%;box-sizing:border-box;background:#0f172a;color:white;border:1px solid #334155;border-radius:14px;padding:12px;margin-bottom:12px;">
                        <button type="submit" style="width:100%;background:#2563eb;color:white;border:none;border-radius:14px;padding:13px 16px;font-weight:bold;cursor:pointer;">Опубликовать</button>
                    </form>
                </aside>

                <main>
                    {news_html}
                </main>
            </div>
        </div>
    </body>
    </html>
    """

# AI Copilot route

@app.route("/ai_copilot", methods=["GET", "POST"])
@app.route("/ai_copilot/<email>", methods=["GET", "POST"])
def ai_copilot_page(email=None):
    logged_email = session.get("user_email", "")

    if not logged_email:
        return redirect("/")

    user = find_user_by_email(logged_email)

    if user is None:
        return "User not found"

    if email and normalize_email(email) != normalize_email(logged_email):
        return redirect(f"/ai_copilot/{safe_text(user.email)}")

    answer_html = ""
    question_value = ""
    selected_mode = "general"
    selected_mode_config = get_ai_core_mode_config(selected_mode)
    history_html = ""
    status = get_openai_status()
    ai_status_text = f"Real AI подключён · модель: {status.get('model')}" if status.get("enabled") else "AI Core в резервном режиме · добавьте OPENAI_API_KEY в .env"

    if request.method == "POST":
        validate_csrf_token()
        question_value = clean_text(request.form.get("question", ""))
        answer = generate_ai_copilot_answer(user, question_value, selected_mode)
        record_ai_core_memory(user.email, selected_mode, question_value, answer)
        answer_html = f"""
        <div style="background:#0f172a;border:1px solid rgba(96,165,250,0.22);border-radius:24px;padding:22px;margin-top:18px;">
            <h2 style="margin:0 0 12px 0;color:#bfdbfe;">Ответ AI Core</h2>
            <div style="line-height:1.7;color:#dbeafe;font-size:16px;">{render_ai_text(answer)}</div>
        </div>
        """
    else:
        answer_html = render_selected_ai_core_history(user.email, request.args.get("history", ""))

    history_html = render_ai_core_history(user.email, limit=12)

    return f"""
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>AI Core - AI Match Life</title>
    </head>
    <body style="margin:0;background:#0f172a;color:white;font-family:Arial,sans-serif;padding:28px;">
        <div style="max-width:980px;margin:auto;">
            <a href="/dashboard/{safe_text(user.email)}" style="display:inline-block;color:white;text-decoration:none;background:#334155;padding:12px 16px;border-radius:14px;margin-bottom:18px;font-weight:bold;">← Назад</a>

            <div style="background:linear-gradient(135deg,#1e293b,#172554);padding:30px;border-radius:30px;margin-bottom:22px;border:1px solid rgba(148,163,184,0.14);">
                <h1 style="margin:0 0 10px 0;font-size:34px;">🧠 AI Core</h1>
                <p style="margin:0;color:#cbd5e1;line-height:1.55;">Внутренний AI-ассистент AI Match Life. Он использует профиль, цели, интересы и AI Discover learning, чтобы помогать пользователю умнее.</p>
                <div style="display:inline-flex;margin-top:16px;background:rgba(15,23,42,0.55);border:1px solid rgba(96,165,250,0.26);border-radius:999px;padding:9px 13px;color:#bfdbfe;font-weight:bold;font-size:13px;">{safe_text(ai_status_text)}</div>
            </div>

            <div style="display:grid;grid-template-columns:minmax(230px,300px) minmax(0,1fr);gap:18px;align-items:start;">
                {history_html}

                <main>
                    <div style="background:#1e293b;padding:22px;border-radius:26px;border:1px solid rgba(148,163,184,0.10);">
                        <h2 style="margin:0 0 14px 0;font-size:20px;">💬 AI Chat</h2>

                        <form method="POST">
                            {csrf_input()}
                            <input type="hidden" name="mode" value="general">
                            <textarea name="question" required placeholder="..." style="width:100%;min-height:150px;background:#0f172a;color:white;border:1px solid #334155;border-radius:18px;padding:14px;box-sizing:border-box;line-height:1.5;">{safe_text(question_value) if question_value else ''}</textarea>
                            <button type="submit" style="margin-top:14px;background:#2563eb;color:white;border:none;border-radius:16px;padding:14px 18px;font-weight:bold;cursor:pointer;width:100%;">Отправить в AI Core</button>
                        </form>
                    </div>

                    {answer_html}
                </main>
            </div>
        </div>
    </body>
    </html>
    """



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
        <button onclick="window.location.href='/profile/{safe_text(user.email)}'">Profil öffnen</button>
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
    /* --- Chat message menu and actions --- */
    .message-menu{{
        display:none;
        position:fixed;
        left:50%;
        bottom:104px;
        transform:translateX(-50%);
        z-index:9999;
        background:rgba(15,23,42,0.97);
        border:1px solid rgba(148,163,184,0.22);
        border-radius:18px;
        padding:7px;
        gap:5px;
        flex-direction:column;
        width:min(238px, calc(100vw - 34px));
        box-shadow:0 18px 46px rgba(0,0,0,0.48);
        backdrop-filter:blur(16px);
        animation:messageMenuSlideUp 0.14s ease-out;
    }}
    .message-menu.open{{ display:flex; }}
    @keyframes messageMenuSlideUp{{
        from{{ opacity:0; transform:translateX(-50%) translateY(10px) scale(0.96); }}
        to{{ opacity:1; transform:translateX(-50%) translateY(0) scale(1); }}
    }}
    .menu-action{{
        width:100%;
        box-sizing:border-box;
        background:rgba(51,65,85,0.92);
        color:white;
        border:none;
        border-radius:11px;
        padding:7px 10px;
        cursor:pointer;
        text-decoration:none;
        font-size:12px;
        font-weight:700;
        white-space:nowrap;
        line-height:1.15;
        text-align:left;
        display:block;
    }}
    .menu-action:hover{{
        background:#475569;
        transform:translateY(-1px) scale(1.01);
    }}
    .menu-action.danger{{
        background:rgba(220,38,38,0.92);
    }}
    </style>
    """


@app.route("/")
def home():
    html = open_html("index.html")
    return render_template_string(html, csrf_token_input=csrf_input())


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        validate_csrf_token()

        contact_type = clean_text(request.form.get("contact_type", "email")).lower()
        email_value = normalize_email(request.form.get("email", ""))
        phone_value = normalize_phone(request.form.get("phone", ""))
        raw_password = request.form.get("password", "")

        if contact_type not in {"email", "phone"}:
            return "Invalid registration method", 400

        if contact_type == "email" and not email_value:
            return "Email is required", 400

        if contact_type == "phone" and not phone_value:
            return "Phone number is required", 400

        if email_value and find_user_by_email(email_value) is not None:
            return "Account with this email already exists", 409

        if phone_value and find_user_by_contact("phone", phone_value) is not None:
            return "Account with this phone number already exists", 409

        if contact_type == "phone" and not email_value:
            internal_phone_email = make_internal_phone_email(phone_value)
            if internal_phone_email and find_user_by_email(internal_phone_email) is not None:
                return "Account with this phone number already exists", 409

        if len(raw_password) < 8:
            return "Password must contain at least 8 characters", 400

        account_email_value = email_value
        if contact_type == "phone" and not account_email_value:
            account_email_value = make_internal_phone_email(phone_value)

        if not account_email_value and not phone_value:
            return "Email or phone number is required", 400

        new_user = User(
            clean_text(request.form["name"]),
            int(request.form["age"]),
            account_email_value,
            raw_password,
            clean_text(request.form["country"]),
            clean_text(request.form["bio"]),
            clean_text(request.form["profession"]),
            clean_text(request.form["looking_for"]),
            [clean_text(item) for item in request.form["languages"].split(",") if clean_text(item)],
            [clean_text(item) for item in request.form["goals"].split(",") if clean_text(item)],
            [clean_text(item) for item in request.form["interests"].split(",") if clean_text(item)],
            [clean_text(item) for item in request.form["skills"].split(",") if clean_text(item)]
        )

        new_user.phone = phone_value
        new_user.account_verified = False
        new_user.account_verified_at = ""
        new_user.account_verified_via = ""

        calculate_trust_score(new_user)
        set_user_password(new_user, raw_password)
        users.append(new_user)
        save_users_to_json(users)

        contact_value = new_user.email if contact_type == "email" else phone_value
        code = create_verification_code("account_verify", contact_type, contact_value)
        if code:
            send_verification_code(contact_type, contact_value, code)
            log_security_event("account_verification_code_sent", new_user.email, f"via={contact_type}")

        safe_contact_value = urllib.parse.quote(contact_value, safe="")
        return redirect(f"/verify_account?contact_type={contact_type}&contact_value={safe_contact_value}")

    html = open_html("register.html")
    return render_template_string(html, csrf_token_input=csrf_input())
    
    


# --- Account verification route ---

@app.route("/verify_account", methods=["GET", "POST"])
def verify_account():
    contact_type = clean_text(request.args.get("contact_type", request.form.get("contact_type", "email"))).lower()
    contact_value = request.args.get("contact_value", request.form.get("contact_value", ""))
    if contact_type == "phone" and contact_value and not str(contact_value).strip().startswith("+"):
        digits_only = str(contact_value).strip().replace(" ", "")
        if digits_only.startswith("491") or digits_only.startswith("49"):
            contact_value = "+" + digits_only
    message = ""

    if contact_type not in {"email", "phone"}:
        contact_type = "email"

    if contact_type == "email":
        contact_value = normalize_email(contact_value)
    else:
        contact_value = normalize_phone(contact_value)

    if request.method == "POST":
        validate_csrf_token()
        code = request.form.get("code", "")
        user = find_user_by_contact(contact_type, contact_value)

        if user is not None and verify_contact_code("account_verify", contact_type, contact_value, code):
            mark_account_verified(user, contact_type)
            log_security_event("account_verified", getattr(user, "email", ""), f"via={contact_type}")
            return redirect("/")

        log_security_event("account_verify_failed", contact_value, f"via={contact_type}")
        message = "Неверный или просроченный код."

    return f"""
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Подтверждение аккаунта</title>
        {page_style()}
    </head>
    <body>
        <div class="card">
            <h1>✅ Подтверждение аккаунта</h1>
            <p>Введите 6-значный код подтверждения.</p>
            <p style="color:#94a3b8;">Способ: {safe_text(contact_type)} · {safe_text(contact_value)}</p>
            <p style="color:#facc15;">{safe_text(message)}</p>

            <form method="POST">
                {csrf_input()}
                <input type="hidden" name="contact_type" value="{safe_text(contact_type)}">
                <input type="hidden" name="contact_value" value="{safe_text(contact_value)}">
                <input name="code" placeholder="6-значный код" required style="width:100%;padding:12px;border-radius:10px;margin-bottom:12px;box-sizing:border-box;">
                <button type="submit">Подтвердить</button>
            </form>

            <button class="back" onclick="window.location.href='/'">Назад</button>
        </div>
    </body>
    </html>
    """


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return redirect("/")
    validate_csrf_token()
    login_value = request.form.get("login", request.form.get("email", "")).strip()
    password = request.form["password"]

    user, login_type, normalized_login = find_user_by_login(login_value)
    login_attempt_key = getattr(user, "email", normalized_login) if user is not None else normalized_login

    locked, minutes_left = is_login_temporarily_locked(login_attempt_key)
    if locked:
        return f"Слишком много неправильных попыток входа. Попробуйте через {minutes_left} мин."

    if user is None or not verify_user_password(user, password):
        register_failed_login_attempt(login_attempt_key)
        return "Неверный email/телефон или пароль"

    if not is_account_verified(user):
        contact_type, contact_value = get_user_2fa_contact(user)
        code = create_verification_code("account_verify", contact_type, contact_value)
        if code:
            send_verification_code(contact_type, contact_value, code)
        log_security_event("login_unverified_account", user.email, f"Login blocked until account verification via {contact_type}")
        safe_contact_value = urllib.parse.quote(contact_value, safe="")
        return redirect(f"/verify_account?contact_type={contact_type}&contact_value={safe_contact_value}")

    clear_login_attempts(login_attempt_key)

    csrf_token = session.get("csrf_token")

    if not LOGIN_2FA_ENABLED:
        session.clear()
        session.permanent = True
        if csrf_token:
            session["csrf_token"] = csrf_token
        session["user_email"] = user.email
        session["login_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        session.modified = True
        log_security_event("login_success", user.email, "2FA disabled for MVP/dev mode")
        return redirect(f"/dashboard/{user.email}", code=303)

    contact_type, contact_value = get_user_2fa_contact(user)
    code = create_verification_code("login_2fa", contact_type, contact_value)
    if code:
        send_verification_code(contact_type, contact_value, code)

    session.clear()
    session.permanent = True
    if csrf_token:
        session["csrf_token"] = csrf_token
    session["pending_2fa_email"] = user.email
    session["pending_2fa_contact_type"] = contact_type
    session["pending_2fa_contact_value"] = contact_value
    session.modified = True

    log_security_event("login_2fa_required", user.email, f"via={contact_type}")
    safe_pending_email = urllib.parse.quote(user.email, safe="")
    safe_contact_type = urllib.parse.quote(contact_type, safe="")
    safe_contact_value = urllib.parse.quote(contact_value, safe="")
    return redirect(
        f"/verify_login_2fa?email={safe_pending_email}&contact_type={safe_contact_type}&contact_value={safe_contact_value}",
        code=303
    )


# --- 2FA verification route for login ---
from datetime import datetime

@app.route("/verify_login_2fa", methods=["GET", "POST"])
def verify_login_2fa():
    pending_email = session.get("pending_2fa_email", "") or request.values.get("email", "")
    contact_type = session.get("pending_2fa_contact_type", "email") or request.values.get("contact_type", "email")
    contact_value = session.get("pending_2fa_contact_value", "") or request.values.get("contact_value", "")
    message = ""

    pending_email = normalize_email(pending_email)
    contact_type = clean_text(contact_type).lower()
    if contact_type == "phone":
        contact_value = normalize_phone(contact_value)
    else:
        contact_value = normalize_email(contact_value)

    if pending_email and contact_value:
        session.permanent = True
        session["pending_2fa_email"] = pending_email
        session["pending_2fa_contact_type"] = contact_type
        session["pending_2fa_contact_value"] = contact_value
        session.modified = True

    if not pending_email or not contact_value:
        log_security_event("login_2fa_session_missing", "", "pending 2FA session is missing")
        return "Сессия подтверждения входа не найдена. Вернитесь на главную страницу и войдите заново.", 400

    user = find_user_by_email(pending_email)
    if user is None:
        session.clear()
        return "Пользователь для подтверждения входа не найден. Войдите заново.", 400

    if request.method == "POST":
        validate_csrf_token()
        code = request.form.get("code", "")

        if verify_contact_code("login_2fa", contact_type, contact_value, code):
            csrf_token = session.get("csrf_token")
            session.clear()
            session.permanent = True
            if csrf_token:
                session["csrf_token"] = csrf_token
            session["user_email"] = user.email
            session["login_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            session.modified = True
            log_security_event("login_2fa_success", user.email, f"via={contact_type}")
            return redirect(f"/dashboard/{user.email}", code=303)

        log_security_event("login_2fa_failed", user.email, f"via={contact_type}")
        message = "Неверный или просроченный код."

    return f"""
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Подтверждение входа</title>
        {page_style()}
    </head>
    <body>
        <div class="card">
            <h1>🔐 Подтверждение входа</h1>
            <p>Введите 6-значный код безопасности.</p>
            <p style="color:#94a3b8;">Код отправлен через: {safe_text(contact_type)}</p>
            <p style="color:#facc15;">{safe_text(message)}</p>

            <form method="POST">
                {csrf_input()}
                <input name="code" placeholder="6-значный код" required style="width:100%;padding:12px;border-radius:10px;margin-bottom:12px;box-sizing:border-box;">
                <button type="submit">Подтвердить вход</button>
            </form>

            <button class="back" onclick="window.location.href='/cancel_login_2fa'">Отмена</button>
        </div>
    </body>
    </html>
    """


@app.route("/cancel_login_2fa")
def cancel_login_2fa():
    session.clear()
    return redirect("/")


# --- Password recovery routes ---
@app.route("/forgot_password", methods=["GET", "POST"])
def forgot_password():
    message = ""

    if request.method == "POST":
        validate_csrf_token()
        contact_type = clean_text(request.form.get("contact_type", "email")).lower()
        contact_value = request.form.get("contact_value", "")

        user = find_user_by_contact(contact_type, contact_value)

        if user is not None:
            code = create_verification_code("password_reset", contact_type, contact_value)
            if code:
                send_verification_code(contact_type, contact_value, code)
                log_security_event("password_reset_code_sent", getattr(user, "email", ""), f"via={contact_type}")

        message = "Если аккаунт найден, код восстановления отправлен. Проверьте email/SMS или терминал в режиме разработки."

    return f"""
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Восстановление пароля</title>
        {page_style()}
    </head>
    <body>
        <div class="card">
            <h1>🔐 Восстановление пароля</h1>
            <p>Выберите способ восстановления: email или телефон.</p>
            <p style="color:#22c55e;">{safe_text(message)}</p>

            <form method="POST">
                {csrf_input()}
                <select name="contact_type" style="width:100%;padding:12px;border-radius:10px;margin-bottom:12px;">
                    <option value="email">Email</option>
                    <option value="phone">Телефон</option>
                </select>
                <input name="contact_value" placeholder="Email или номер телефона" required style="width:100%;padding:12px;border-radius:10px;margin-bottom:12px;box-sizing:border-box;">
                <button type="submit">Получить код</button>
            </form>

            <button class="back" onclick="window.location.href='/reset_password'">У меня уже есть код</button>
            <button class="back" onclick="window.location.href='/'">Назад</button>
        </div>
    </body>
    </html>
    """


@app.route("/reset_password", methods=["GET", "POST"])
def reset_password():
    message = ""

    if request.method == "POST":
        validate_csrf_token()
        contact_type = clean_text(request.form.get("contact_type", "email")).lower()
        contact_value = request.form.get("contact_value", "")
        code = request.form.get("code", "")
        new_password = request.form.get("new_password", "")

        user = find_user_by_contact(contact_type, contact_value)

        if user is None:
            message = "Неверный код или аккаунт не найден."
        elif len(new_password) < 8:
            message = "Пароль должен быть минимум 8 символов."
        elif verify_contact_code("password_reset", contact_type, contact_value, code):
            set_user_password(user, new_password)
            save_users_to_json(users)
            clear_login_attempts(getattr(user, "email", ""))
            log_security_event("password_reset_success", getattr(user, "email", ""), f"via={contact_type}")
            message = "Пароль успешно изменён. Теперь можно войти."
        else:
            log_security_event("password_reset_failed", contact_value, f"via={contact_type}")
            message = "Неверный или просроченный код."

    return f"""
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Новый пароль</title>
        {page_style()}
    </head>
    <body>
        <div class="card">
            <h1>🔑 Новый пароль</h1>
            <p style="color:#facc15;">{safe_text(message)}</p>

            <form method="POST">
                {csrf_input()}
                <select name="contact_type" style="width:100%;padding:12px;border-radius:10px;margin-bottom:12px;">
                    <option value="email">Email</option>
                    <option value="phone">Телефон</option>
                </select>
                <input name="contact_value" placeholder="Email или номер телефона" required style="width:100%;padding:12px;border-radius:10px;margin-bottom:12px;box-sizing:border-box;">
                <input name="code" placeholder="6-значный код" required style="width:100%;padding:12px;border-radius:10px;margin-bottom:12px;box-sizing:border-box;">
                <input name="new_password" type="password" placeholder="Новый пароль" required style="width:100%;padding:12px;border-radius:10px;margin-bottom:12px;box-sizing:border-box;">
                <button type="submit">Сменить пароль</button>
            </form>

            <button class="back" onclick="window.location.href='/forgot_password'">Получить новый код</button>
            <button class="back" onclick="window.location.href='/'">Назад</button>
        </div>
    </body>
    </html>
    """


@app.route("/logout")
@login_required
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
    activity_count = sum(1 for post in posts if normalize_email(post.get("email", post.get("author_email", ""))) == normalize_email(user.email))

    posts_html = ""


    if posts:
        for post in reversed(posts):
            author = find_user_by_email(post.get("email"))
            author_name = author.name if author else "Пользователь"
            author_email = author.email if author else post.get("email", "")
            author_avatar = get_avatar_url(author_email) if author_email else "/static/default-avatar.png"
            post_text = safe_text(post.get("text", "")).strip()
            post_type_label = safe_text(post.get("type", "Публикация"))

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
            text_html = f"""
                <div style="font-size:17px;line-height:1.58;color:#e5e7eb;margin:12px 0 14px 0;white-space:pre-wrap;">{post_text}</div>
            """ if post_text else ""

            posts_html += f"""
            <article style="background:#0f172a;border:1px solid rgba(148,163,184,0.14);padding:18px;border-radius:26px;margin-top:18px;box-shadow:0 18px 44px rgba(0,0,0,0.18);">
                <div style="display:flex;gap:13px;align-items:flex-start;">
                    <a href="/profile/{safe_text(author_email)}" style="flex:0 0 auto;text-decoration:none;">
                        <img src="{author_avatar}" alt="Avatar" style="width:52px;height:52px;border-radius:50%;object-fit:cover;background:#334155;border:2px solid rgba(96,165,250,0.35);">
                    </a>

                    <div style="flex:1;min-width:0;">
                        <div style="display:flex;justify-content:space-between;gap:12px;align-items:flex-start;">
                            <div style="min-width:0;">
                                <a href="/profile/{safe_text(author_email)}" style="color:#f8fafc;text-decoration:none;font-size:17px;font-weight:900;display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{safe_text(author_name)}</a>
                                <div style="color:#94a3b8;font-size:13px;margin-top:3px;">{safe_text(post.get("date", ""))}</div>
                            </div>

                            <div style="background:rgba(37,99,235,0.16);color:#93c5fd;border:1px solid rgba(96,165,250,0.28);padding:7px 11px;border-radius:999px;font-size:13px;font-weight:900;white-space:nowrap;">
                                {post_type_label}
                            </div>
                        </div>

                        {text_html}
                        {location_html}
                        {hashtags_html}
                        {media_html}

                        <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;border-top:1px solid rgba(148,163,184,0.14);padding-top:13px;margin-top:15px;align-items:center;">
                            <a href="/like_post/{user.email}/{post_id}" style="color:#e5e7eb;text-decoration:none;font-size:15px;font-weight:800;background:#111827;border:1px solid rgba(148,163,184,0.12);border-radius:14px;padding:10px 8px;text-align:center;">❤️ {likes_count}</a>
                            <button type="button" onclick="toggleCommentBox('{post_id}')" style="background:#111827;border:1px solid rgba(148,163,184,0.12);border-radius:14px;color:#e5e7eb;font-size:15px;font-weight:800;cursor:pointer;padding:10px 8px;">
                                💬 {comments_count}
                            </button>
                            <a href="/share_post/{user.email}/{post_id}" style="color:#e5e7eb;text-decoration:none;font-size:15px;font-weight:800;background:#111827;border:1px solid rgba(148,163,184,0.12);border-radius:14px;padding:10px 8px;text-align:center;">↗️ {shares_count}</a>
                            <a href="/save_post/{user.email}/{post_id}" style="color:#e5e7eb;text-decoration:none;font-size:15px;font-weight:800;background:#111827;border:1px solid rgba(148,163,184,0.12);border-radius:14px;padding:10px 8px;text-align:center;">🔖 {saves_count}</a>
                        </div>

                        <div id="comment-box-{post_id}" style="display:none;margin-top:14px;background:#111827;border:1px solid rgba(148,163,184,0.12);padding:14px;border-radius:20px;">
                            <div style="margin-bottom:12px;max-height:260px;overflow-y:auto;">
                                {''.join([f'<div style="background:#0f172a;padding:10px 12px;border-radius:14px;margin-top:8px;color:#e5e7eb;"><b>{safe_text(comment.get("author_name", "User"))}</b>: {safe_text(comment.get("text", ""))}</div>' for comment in post.get("comments", [])]) if post.get("comments", []) else '<div style="color:#94a3b8;margin-bottom:8px;">Комментариев пока нет.</div>'}
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
                </div>
            </article>
            """
    else:
        posts_html = """
        <div style="background:#0f172a;border:1px solid rgba(148,163,184,0.14);padding:28px;border-radius:26px;margin-top:18px;text-align:center;box-shadow:0 18px 44px rgba(0,0,0,0.18);">
            <div style="font-size:42px;margin-bottom:12px;">🛰️</div>
            <h3 style="margin:0 0 8px 0;font-size:22px;">Лента пока пустая</h3>
            <p style="color:#94a3b8;line-height:1.55;margin:0;">Опубликуйте первую новость, мысль, фото, видео или проект. Здесь будет главная живая лента AI Match Life.</p>
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

    stories_html = ""
    try:
        stories_data = load_stories()
        active_stories = [story for story in stories_data.get("stories", []) if is_story_active(story)]

        connected_emails = set()
        for getter_name in ("get_friends", "get_following", "get_followers"):
            getter = globals().get(getter_name)
            if not callable(getter):
                continue

            try:
                for connected_email in getter(user.email):
                    clean_email = normalize_email(connected_email)
                    if clean_email:
                        connected_emails.add(clean_email)
            except Exception as error:
                log_security_event("dashboard_story_connections_failed", user.email, f"{getter_name}: {error}")

        connected_emails.discard(normalize_email(user.email))

        seen_story_owners = set()
        story_owner_users = []

        for story in reversed(active_stories):
            story_email = normalize_email(story.get("email", ""))

            if not story_email or story_email in seen_story_owners:
                continue

            if story_email not in connected_emails:
                continue

            story_user = find_user_by_email(story_email)
            if story_user is None:
                continue

            if is_blocked(user.email, story_user.email) or is_blocked(story_user.email, user.email):
                continue

            seen_story_owners.add(story_email)
            story_owner_users.append(story_user)

            if len(story_owner_users) >= 12:
                break

        for story_user in story_owner_users:
            stories_html += f"""
                        <a href="/story/{safe_text(user.email)}/{safe_text(story_user.email)}" class="story-mini">
                            <div class="story-mini-avatar">
                                <img src="{get_avatar_url(story_user.email)}" alt="Story">
                            </div>
                            <div style="margin-top:8px;font-weight:bold;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:96px;">{safe_text(story_user.name)}</div>
                            <div style="color:#94a3b8;font-size:12px;">История</div>
                        </a>
            """
    except Exception as error:
        log_security_event("dashboard_stories_failed", user.email, str(error))
        stories_html = ""
    html = open_html("dashboard.html")

    life_radar = generate_life_radar(user)
    openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
    openai_model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"

    if openai_key.startswith("sk-"):
        ai_status_text = f"🟢 Real AI подключён · модель: {openai_model}"
    else:
        ai_status_text = "🟡 AI работает в резервном режиме · добавьте OPENAI_API_KEY в .env"

    if isinstance(life_radar, list):
        life_radar = [ai_status_text] + life_radar
    else:
        life_radar = [ai_status_text, str(life_radar)]

    ai_status_badge_html = f"""
        <div style="margin-top:16px;background:rgba(15,23,42,0.34);border:1px solid rgba(255,255,255,0.18);border-radius:18px;padding:12px 14px;color:white;font-weight:800;font-size:14px;display:inline-flex;align-items:center;gap:8px;box-shadow:0 12px 28px rgba(0,0,0,0.18);">
            {safe_text(ai_status_text)}
        </div>
    """

    html = html.replace(
        "AI подбирает людей, возможности, инвесторов, друзей и партнёров специально для вас.",
        "AI подбирает людей, возможности, инвесторов, друзей и партнёров специально для вас." + ai_status_badge_html
    )

    if safe_text(ai_status_text) not in html:
        floating_ai_status_html = f"""
            <div style="position:fixed;right:22px;bottom:22px;z-index:9999;background:rgba(15,23,42,0.92);border:1px solid rgba(96,165,250,0.34);border-radius:18px;padding:12px 14px;color:white;font-weight:800;font-size:13px;display:flex;align-items:center;gap:8px;box-shadow:0 18px 44px rgba(0,0,0,0.38);backdrop-filter:blur(16px);">
                {safe_text(ai_status_text)}
            </div>
        """
        html = html.replace("</body>", floating_ai_status_html + "</body>")

    seen_match_emails = set()
    matches_count = 0
    for match in find_best_matches(user, users):
        matched_user = match.get("user") if isinstance(match, dict) else None
        matched_email = normalize_email(getattr(matched_user, "email", "")) if matched_user else ""

        if not matched_email or matched_email in seen_match_emails:
            continue

        if not can_show_user_in_ai_recommendations(user.email, matched_user):
            continue

        seen_match_emails.add(matched_email)
        matches_count += 1

    notifications_count=notifications_count
    return render_template_string(
        html,
        name=safe_text(user.name),
        email=safe_text(user.email),
        trust_score=user.trust_score,
        posts=posts_html,
        activity_count=activity_count,
        stories_html=stories_html,
        life_radar=life_radar,
        translations=translations,
        avatar_url=get_avatar_url(user.email),
        notifications_count=notifications_count,
        matches_count=matches_count,
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
            <a href="/settings/{safe_text(user.email)}" style="display:inline-block;color:white;text-decoration:none;background:#334155;padding:12px 16px;border-radius:14px;margin-bottom:18px;font-weight:bold;">← Ayarlar</a>
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
        log_security_event("upload_rejected", email, "Unsupported avatar file extension")
        return "Unsupported avatar file type"
    
    if not allowed_mime_type(file):
        log_security_event("upload_rejected", email, "Invalid avatar file content")
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
            <a href="/dashboard/{safe_text(email)}" style="display:inline-block;color:white;text-decoration:none;background:#334155;padding:12px 16px;border-radius:14px;margin-bottom:18px;font-weight:bold;">← Назад</a>
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

    raw_post_type = clean_text(request.form.get("type", "")).strip()
    text = clean_text(request.form.get("text", "")).strip()
    location = clean_text(request.form.get("location", "")).strip()
    hashtags_raw = clean_text(request.form.get("hashtags", "")).strip()
    content_language = normalize_content_language_code(request.form.get("language", ""))

    post_type_aliases = {
        "news": "Новость",
        "nevs": "Новость",
        "новости": "Новость",
        "новость": "Новость",
        "idea": "Идея",
        "идея": "Идея",
        "мысль": "Идея",
        "project": "Проект",
        "проект": "Проект",
        "partner": "Поиск партнёра",
        "поиск партнёра": "Поиск партнёра",
        "достижение": "Достижение",
        "achievement": "Достижение",
        "proof": "Proof"
    }

    normalized_key = raw_post_type.lower()
    post_type = post_type_aliases.get(normalized_key, raw_post_type)

    allowed_post_types = {"Новость", "Идея", "Проект", "Поиск партнёра", "Достижение", "Proof"}
    if post_type not in allowed_post_types:
        post_type = "Новость"

    if not request.form.get("language", ""):
        content_language = detect_content_language(" ".join([post_type, text, location, hashtags_raw]))

    hashtags = []
    if hashtags_raw:
        for raw_tag in hashtags_raw.replace(",", " ").split():
            clean_tag = clean_text(raw_tag).replace("#", "").strip()
            if clean_tag and clean_tag not in hashtags:
                hashtags.append(clean_tag[:40])

    media_url = ""
    media_type = ""
    media_items = []

    files = request.files.getlist("media")

    image_ext = {"jpg", "jpeg", "png", "webp", "gif"}
    video_ext = {"mp4", "mov", "webm", "m4v"}
    audio_ext = {"mp3", "wav", "m4a", "ogg", "webm"}

    for uploaded_file in files[:10]:
        if not uploaded_file or not uploaded_file.filename:
            continue

        filename = secure_filename(uploaded_file.filename)
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

        current_type = ""
        if ext in image_ext:
            current_type = "image"
        elif ext in video_ext:
            current_type = "video"
        elif ext in audio_ext:
            current_type = "audio"
        else:
            log_security_event("upload_rejected", email, "Unsupported post media file extension")
            continue

        if not allowed_mime_type(uploaded_file):
            log_security_event("upload_rejected", email, "Invalid post media file content")
            continue

        safe_email = secure_filename(user.email.replace("@", "_at_").replace(".", "_"))
        new_filename = f"post_{safe_email}_{secrets.token_urlsafe(8)}_{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{filename}"

        upload_path = os.path.join(UPLOAD_FOLDER, new_filename)
        uploaded_file.save(upload_path)

        current_url = f"/static/uploads/{new_filename}"
        media_items.append({
            "url": current_url,
            "type": current_type,
            "name": filename
        })

    if not text and not media_items:
        return simple_page(
            "Пустая публикация",
            "Добавьте текст, фото, видео или аудио перед публикацией.",
            user.email
        )

    if media_items:
        media_url = media_items[0].get("url", "")
        media_type = media_items[0].get("type", "")

    feed_data = load_feed()
    posts = feed_data.get("posts", [])

    new_id = 1
    numeric_ids = []
    for post in posts:
        try:
            numeric_ids.append(int(post.get("id", 0)))
        except Exception:
            continue

    if numeric_ids:
        new_id = max(numeric_ids) + 1

    now_display = datetime.now().strftime("%d.%m.%Y %H:%M")
    now_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    posts.append({
        "id": new_id,
        "email": user.email,
        "name": user.name,
        "author_email": user.email,
        "author_name": user.name,
        "type": post_type,
        "content_kind": "main_feed_post",
        "text": text,
        "location": location,
        "hashtags": hashtags,
        "language": content_language,
        "media_url": media_url,
        "media_type": media_type,
        "media_items": media_items,
        "date": now_display,
        "created_at": now_iso,
        "likes": [],
        "comments": [],
        "shares": [],
        "saves": [],
        "ai_score": 0,
        "ai_summary": "",
        "ai_reasons": []
    })

    feed_data["posts"] = posts
    save_feed(feed_data)

    return_to = clean_text(request.form.get("return_to", ""))
    referer = request.headers.get("Referer", "")

    if return_to == "dashboard" or f"/dashboard/{user.email}" in referer:
        return redirect(f"/dashboard/{user.email}")

    return redirect(f"/feed/{user.email}")


@app.route("/create_story/<email>", methods=["POST"])
@login_required
def create_story(email):
    validate_csrf_token()
    user = find_user_by_email(email)

    if user is None:
        return "User not found"

    uploaded_files = request.files.getlist("story_media")
    if not uploaded_files:
        return redirect(f"/dashboard/{user.email}")

    stories_data = load_stories()
    stories = stories_data.get("stories", [])
    if not isinstance(stories, list):
        stories = []

    image_ext = {"jpg", "jpeg", "png", "webp", "gif"}
    video_ext = {"mp4", "mov", "webm", "m4v"}
    created_count = 0

    numeric_ids = []
    for story in stories:
        try:
            numeric_ids.append(int(story.get("id", 0)))
        except Exception:
            continue

    next_id = max(numeric_ids) + 1 if numeric_ids else 1

    for uploaded_file in uploaded_files[:10]:
        if not uploaded_file or not uploaded_file.filename:
            continue

        filename = secure_filename(uploaded_file.filename)
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

        if ext in image_ext:
            media_type = "image"
        elif ext in video_ext:
            media_type = "video"
        else:
            log_security_event("story_upload_rejected", user.email, "Unsupported story file extension")
            continue

        if not allowed_mime_type(uploaded_file):
            log_security_event("story_upload_rejected", user.email, "Invalid story media content")
            continue

        safe_email = secure_filename(user.email.replace("@", "_at_").replace(".", "_"))
        stored_name = f"story_{safe_email}_{secrets.token_urlsafe(8)}_{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{filename}"
        upload_path = os.path.join(UPLOAD_FOLDER, stored_name)
        uploaded_file.save(upload_path)

        stories.append({
            "id": next_id,
            "email": user.email,
            "name": user.name,
            "media_url": f"/static/uploads/{stored_name}",
            "media_type": media_type,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "views": []
        })
        next_id += 1
        created_count += 1

    stories_data["stories"] = stories[-1000:]
    save_stories(stories_data)

    if created_count == 0:
        return simple_page(
            "Story не добавлена",
            "Файл не подходит. Добавьте фото или видео.",
            user.email
        )

    return redirect(f"/dashboard/{user.email}")


@app.route("/story/<viewer_email>/<owner_email>")
@login_required
def view_story(viewer_email, owner_email):
    viewer = find_user_by_email(viewer_email)
    owner = find_user_by_email(owner_email)

    if viewer is None or owner is None:
        return "User not found"

    viewer_email_clean = normalize_email(viewer.email)
    owner_email_clean = normalize_email(owner.email)

    if is_blocked(viewer.email, owner.email) or is_blocked(owner.email, viewer.email):
        log_security_event("story_view_blocked", viewer.email, f"Blocked story view attempt to {owner.email}")
        return simple_page(
            "🚫 Story недоступна",
            "Нельзя просматривать Story этого пользователя, потому что один из пользователей заблокировал другого.",
            viewer.email
        )

    if viewer_email_clean != owner_email_clean:
        allowed_to_view = (
            are_friends(viewer.email, owner.email)
            or is_following(viewer.email, owner.email)
            or is_following(owner.email, viewer.email)
        )

        if not allowed_to_view:
            return simple_page(
                "Story недоступна",
                "Вы можете смотреть истории друзей, подписок и подписчиков.",
                viewer.email
            )

    stories_data = load_stories()
    stories = stories_data.get("stories", [])
    if not isinstance(stories, list):
        stories = []

    owner_stories = []
    changed = False

    for story in stories:
        if normalize_email(story.get("email", "")) != owner_email_clean:
            continue

        if not is_story_active(story):
            continue

        views = story.get("views", [])
        if not isinstance(views, list):
            views = []

        normalized_views = [normalize_email(item) for item in views]
        if viewer_email_clean != owner_email_clean and viewer_email_clean not in normalized_views:
            views.append(viewer.email)
            story["views"] = views
            changed = True

        owner_stories.append(story)

    owner_stories.sort(key=lambda item: item.get("created_at", ""))

    if changed:
        stories_data["stories"] = stories
        save_stories(stories_data)

    if not owner_stories:
        return simple_page(
            "Историй пока нет",
            "У этого пользователя нет активных историй за последние 24 часа.",
            viewer.email
        )

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

    views_count = 0
    if owner_email_clean == viewer_email_clean:
        seen_viewers = set()
        for story in owner_stories:
            views = story.get("views", [])
            if isinstance(views, list):
                for item in views:
                    clean_viewer = normalize_email(item)
                    if clean_viewer and clean_viewer != owner_email_clean:
                        seen_viewers.add(clean_viewer)
        views_count = len(seen_viewers)

    owner_avatar = get_avatar_url(owner.email)
    owner_name = safe_text(owner.name)
    back_url = f"/dashboard/{safe_text(viewer.email)}"
    story_count_text = f"{len(owner_stories)} историй"
    if owner_email_clean == viewer_email_clean:
        story_count_text += f" · {views_count} просмотров"

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


@app.route("/comment_post/<email>/<int:post_id>", methods=["POST"])
@login_required
def comment_post(email, post_id):
    validate_csrf_token()
    user = find_user_by_email(email)

    if user is None:
        return "User not found"

    comment_text = clean_text(request.form["comment"])

    feed_data = load_feed()
    posts = feed_data.get("posts", [])

    for post in posts:
        if post.get("id") == post_id:
            post_owner_email = post.get("email", "")
            if post_owner_email and (is_blocked(email, post_owner_email) or is_blocked(post_owner_email, email)):
                log_security_event("comment_blocked", email, f"Blocked comment attempt on post {post_id}")
                return simple_page(
                    "🚫 Комментарий недоступен",
                    "Нельзя комментировать этот пост, потому что один из пользователей заблокировал другого.",
                    email
                )

            comments = post.get("comments", [])

            comments.append({
                "author": user.email,
                "author_name": user.name,
                "text": comment_text,
                "date": datetime.now().strftime("%d.%m.%Y %H:%M")
            })

            post["comments"] = comments
            record_ai_feed_signal(email, post, "comment_post")
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
            post_owner_email = post.get("email", "")

            if post_owner_email and (is_blocked(email, post_owner_email) or is_blocked(post_owner_email, email)):
                log_security_event("like_blocked", email, f"Blocked like attempt on post {post_id}")
                return simple_page(
                    "🚫 Лайк недоступен",
                    "Нельзя ставить лайк этому посту, потому что один из пользователей заблокировал другого.",
                    email
                )

            likes = post.get("likes", [])
            if email in likes:
                likes.remove(email)
            else:
                likes.append(email)

            post["likes"] = likes
            record_ai_feed_signal(email, post, "like_post")
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

    if is_blocked(sender.email, receiver.email) or is_blocked(receiver.email, sender.email):
        log_security_event("share_blocked", sender.email, f"Blocked share attempt to {receiver.email}")
        return simple_page(
            "🚫 Отправка недоступна",
            "Нельзя отправить пост этому пользователю, потому что один из пользователей заблокировал другого.",
            sender.email
        )

    if not are_friends(sender.email, receiver.email):
        log_security_event("share_denied", sender.email, f"Attempted to share post to non-friend {receiver.email}")
        return simple_page(
            "🔒 Доступ закрыт",
            "Пост можно отправить только пользователю из списка друзей.",
            sender.email
        )

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
        "message": clean_text(f"{sender.name} поделился постом: {selected_post.get('text', '')}"),
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
            <strong>{safe_text(comment.get('author_name','User'))}</strong><br>
            <span style="color:#cbd5e1;">{safe_text(comment.get('text',''))}</span><br>
            <small style="color:#94a3b8;">{safe_text(comment.get('date',''))}</small>
        </div>
        """

    return f"""
    <html>
    <head>
        <title>Комментарии</title>
    </head>

    <body style="background:#0f172a;color:white;font-family:Arial;padding:30px;max-width:900px;margin:auto;">

        <a href="/dashboard/{safe_text(email)}" style="color:white;">← Назад</a>

        <h1>💬 Комментарии</h1>

        <div style="background:#1e293b;padding:20px;border-radius:20px;margin-bottom:20px;">
            <h3>{safe_text(current_post.get('type','Публикация'))}</h3>
            <p>{safe_text(current_post.get('text',''))}</p>
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
            post_owner_email = post.get("email", "")
            if post_owner_email and (is_blocked(email, post_owner_email) or is_blocked(post_owner_email, email)):
                log_security_event("save_blocked", email, f"Blocked save attempt on post {post_id}")
                return simple_page(
                    "🚫 Сохранение недоступно",
                    "Нельзя сохранить этот пост, потому что один из пользователей заблокировал другого.",
                    email
                )

            saves = post.get("saves", [])

            if email in saves:
                saves.remove(email)
            else:
                saves.append(email)

            post["saves"] = saves
            record_ai_feed_signal(email, post, "save_post")
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

    record_ai_feed_signal(email, selected_post, "open_post")

    post_owner_email = selected_post.get("email", "")
    if post_owner_email and (is_blocked(email, post_owner_email) or is_blocked(post_owner_email, email)):
        log_security_event("post_view_blocked", email, f"Blocked post view attempt {post_id}")
        return simple_page(
            "🚫 Пост недоступен",
            "Нельзя открыть этот пост, потому что один из пользователей заблокировал другого.",
            email
        )

    author = find_user_by_email(selected_post.get("email"))
    author_name = author.name if author else "Unknown user"

    comments_html = ""

    for comment in selected_post.get("comments", []):
        comments_html += f"""
        <div style="background:#1e293b;padding:14px;border-radius:14px;margin-top:10px;">
            <strong>{safe_text(comment.get("author_name", "User"))}</strong>
            <p>{safe_text(comment.get("text", ""))}</p>
            <small style="color:#94a3b8;">{safe_text(comment.get("date", ""))}</small>
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
        <p><a href="/dashboard/{safe_text(email)}">← Назад</a></p>

        <div class="box">
            <h2>👤 {safe_text(author_name)}</h2>
            <p style="color:#60a5fa;font-weight:bold;">{safe_text(selected_post.get("type", "Публикация"))}</p>
            <p style="font-size:18px;line-height:1.5;">{safe_text(selected_post.get("text", ""))}</p>
            <small style="color:#94a3b8;">{safe_text(selected_post.get("date", ""))}</small>
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
        name=safe_text(user.name),
        age=user.age,
        email=safe_text(user.email),
        ai_summary=safe_text(ai_profile["summary"]),
        viewer_email=safe_text(viewer_email),
        is_following_user=is_following(viewer_email, user.email),
        are_friends_user=are_friends(viewer_email, user.email),
        friend_request_sent=has_friend_request(viewer_email, user.email),
        country=safe_text(user.country),
        bio=safe_text(user.bio),
        profession=safe_text(user.profession),
        looking_for=safe_text(user.looking_for),
        languages=safe_list(user.languages),
        goals=safe_list(user.goals),
        interests=safe_list(user.interests),
        skills=safe_list(user.skills),
        trust_score=user.trust_score,
        verified="YES" if user.verified else "NO",
        friends_count=count_friends(user.email),
        followers_count=count_followers(user.email),
        following_count=count_following(user.email),
        avatar_url=get_avatar_url(user.email)
    )


# --- User AI Privacy/Settings helpers ---

def normalize_user_ai_settings(email):
    email = normalize_email(email)
    privacy_file = "database/privacy_data.json"

    defaults = {
        "show_in_search": True,
        "allow_messages": True,
        "private_profile": False,
        "ai_recommendations": True,
        "ai_life_radar": True,
        "recommend_my_profile": True,
        "ai_activity_analysis": True,
        "notifications_enabled": True,
        "message_permission": "everyone"
    }

    data = {}
    try:
        if os.path.exists(privacy_file):
            with open(privacy_file, "r", encoding="utf-8") as file:
                data = json.load(file)
    except Exception:
        data = {}

    if not isinstance(data, dict):
        data = {}

    settings = data.get(email, {})
    if not isinstance(settings, dict):
        settings = {}

    merged = dict(defaults)
    merged.update(settings)

    if merged.get("allow_messages") is False:
        merged["message_permission"] = "none"
    elif merged.get("verified_only_messages") is True:
        merged["message_permission"] = "verified"
    elif merged.get("friends_only_messages") is True:
        merged["message_permission"] = "friends"
    else:
        merged["message_permission"] = merged.get("message_permission", "everyone")

    return merged


def save_user_ai_settings(email, new_settings):
    email = normalize_email(email)
    privacy_file = "database/privacy_data.json"

    if not email:
        return

    data = {}
    try:
        if os.path.exists(privacy_file):
            with open(privacy_file, "r", encoding="utf-8") as file:
                data = json.load(file)
    except Exception:
        data = {}

    if not isinstance(data, dict):
        data = {}

    current = data.get(email, {})
    if not isinstance(current, dict):
        current = {}

    current.update(new_settings)

    message_permission = current.get("message_permission", "everyone")
    current["allow_messages"] = message_permission != "none"
    current["verified_only_messages"] = message_permission == "verified"
    current["friends_only_messages"] = message_permission == "friends"

    data[email] = current

    os.makedirs(os.path.dirname(privacy_file), exist_ok=True)
    with open(privacy_file, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=4)


@app.route("/settings/<email>")
@login_required
def settings_page(email):
    user = find_user_by_email(email)

    if user is None:
        return "User not found"

    settings = normalize_user_ai_settings(user.email)
    html = open_html("settings.html")

    return render_template_string(
        html,
        email=safe_text(user.email),
        settings=settings,
        csrf_token_input=csrf_input()
    )


@app.route("/settings/<email>/privacy_ai", methods=["POST"])
@login_required
def update_privacy_ai_settings(email):
    validate_csrf_token()
    user = find_user_by_email(email)

    if user is None:
        return "User not found"

    message_permission = request.form.get("message_permission", "everyone")
    if message_permission not in ["everyone", "friends", "verified", "none"]:
        message_permission = "everyone"

    new_settings = {
        "show_in_search": request.form.get("show_in_search") == "on",
        "private_profile": request.form.get("private_profile") == "on",
        "ai_recommendations": request.form.get("ai_recommendations") == "on",
        "ai_life_radar": request.form.get("ai_life_radar") == "on",
        "recommend_my_profile": request.form.get("recommend_my_profile") == "on",
        "ai_activity_analysis": request.form.get("ai_activity_analysis") == "on",
        "notifications_enabled": request.form.get("notifications_enabled") == "on",
        "message_permission": message_permission
    }

    save_user_ai_settings(user.email, new_settings)
    return redirect(f"/settings/{user.email}")

@app.route("/follow/<viewer_email>/<profile_email>")
@login_required
def follow_route(viewer_email, profile_email):
    if is_blocked(viewer_email, profile_email) or is_blocked(profile_email, viewer_email):
        log_security_event("follow_blocked", viewer_email, f"Blocked follow attempt to {profile_email}")
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
    if is_blocked(viewer_email, profile_email) or is_blocked(profile_email, viewer_email):
        log_security_event("unfollow_blocked", viewer_email, f"Blocked unfollow attempt to {profile_email}")
        return simple_page(
            "🚫 Действие недоступно",
            "Операция недоступна.",
            viewer_email
        )

    unfollow_user(viewer_email, profile_email)
    return redirect(f"/profile/{profile_email}?viewer={viewer_email}")


@app.route("/send_friend_request/<viewer_email>/<profile_email>")
@login_required
def send_friend_request_route(viewer_email, profile_email):
    if is_blocked(viewer_email, profile_email) or is_blocked(profile_email, viewer_email):
        log_security_event("friend_request_blocked", viewer_email, f"Blocked friend request attempt to {profile_email}")
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
    if is_blocked(viewer_email, profile_email) or is_blocked(profile_email, viewer_email):
        log_security_event("friend_accept_blocked", viewer_email, f"Blocked friend accept with {profile_email}")
        return simple_page(
            "🚫 Действие недоступно",
            "Подтверждение дружбы невозможно, потому что один из пользователей заблокировал другого.",
            viewer_email
        )

    if accept_friend_request(viewer_email, profile_email):
        viewer = find_user_by_email(viewer_email)

        add_notification(
            profile_email,
            viewer_email,
            "friend_accept",
            f"{viewer.name} принял вашу заявку в друзья"
        )

    return redirect(f"/profile/{profile_email}?viewer={viewer_email}")

def can_show_user_in_ai_recommendations(viewer_email, candidate_user):
    viewer_email = normalize_email(viewer_email)

    if candidate_user is None:
        return False

    candidate_email = normalize_email(getattr(candidate_user, "email", ""))

    if not viewer_email or not candidate_email:
        return False

    if candidate_email == viewer_email:
        return False

    if is_blocked(viewer_email, candidate_email) or is_blocked(candidate_email, viewer_email):
        return False

    candidate_privacy = normalize_user_ai_settings(candidate_email)

    if candidate_privacy.get("show_in_search") is False:
        return False

    if candidate_privacy.get("recommend_my_profile") is False:
        return False

    if candidate_privacy.get("vip_mode") is True:
        return False

    return True

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

        if not can_show_user_in_ai_recommendations(current_user.email, matched_user):
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
                <a href="/profile/{safe_text(matched_user.email)}?viewer={safe_text(current_user.email)}">Открыть профиль</a>
                <a href="/chat/{safe_text(current_user.email)}/{safe_text(matched_user.email)}" class="message">Написать</a>
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
        name=safe_text(current_user.name),
        email=safe_text(current_user.email),
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
        keyword = clean_text(request.form["keyword"]).strip().lower()

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
        email=safe_text(current_user.email),
        results=results_html,
        csrf_token_input=csrf_input()
    )





def simple_page(title, text, email):
    safe_title = safe_text(title)
    safe_body = safe_text(text)
    safe_email = safe_text(email)

    return f"""
    <html>
    <head>
    <meta charset="UTF-8">
    <title>{safe_title}</title>
    {page_style()}
    </head>
    <body>
    <div class="card">
        <h1>{safe_title}</h1>
        <p>{safe_body}</p>
        <button onclick="window.location.href='/dashboard/{safe_email}'">Назад в Dashboard</button>
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

        if file and allowed_file(file.filename) and allowed_mime_type(file):
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
            log_security_event("upload_rejected", email, "Invalid media page avatar upload")
            message = "Ошибка: файл не прошёл проверку безопасности. Разрешены только настоящие PNG, JPG, JPEG, GIF или WEBP."

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
        <p>{safe_text(user.name)}</p>

        <img src="{avatar_url}" alt="Avatar">

        <p class="msg">{safe_text(message)}</p>

        <form method="POST" enctype="multipart/form-data">
            {csrf_input()}
            <input type="file" name="avatar" accept="image/*" required>
            <button type="submit">Загрузить аватар</button>
        </form>

        <button class="back" onclick="window.location.href='/dashboard/{safe_text(email)}'">Назад в Dashboard</button>
    </div>
    </body>
    </html>
    """


def clean_list_items(values):
    if values is None:
        return []

    if isinstance(values, list):
        raw_items = values
    elif isinstance(values, str):
        raw_items = values.replace(";", ",").split(",")
    else:
        raw_items = []

    clean_items = []
    for item in raw_items:
        item = clean_text(item).strip()
        if item and item.lower() not in {"nicht angegeben", "не указано", "none", "null"}:
            clean_items.append(item)

    return clean_items


@app.route("/feed/<email>")
@login_required
def feed_page(email):
    current_user = find_user_by_email(email)

    if current_user is None:
        return "User not found"

    current_settings = normalize_user_ai_settings(current_user.email)
    ai_feed_enabled = current_settings.get("ai_recommendations", True) is True
    ai_activity_enabled = current_settings.get("ai_activity_analysis", True) is True

    feed_data = load_feed()
    posts = feed_data.get("posts", [])
    posts_html = ""
    ranked_posts = []
    feed_changed = False

    user_language_codes = get_user_language_signals(current_user)
    if not user_language_codes:
        user_language_codes = [get_current_language(current_user)]

    user_language_names = []
    for language_code in user_language_codes:
        language_name = CONTENT_LANGUAGES.get(normalize_content_language_code(language_code), SUPPORTED_LANGUAGES.get(language_code, language_code))
        if language_name not in user_language_names:
            user_language_names.append(language_name)

    user_keywords = []
    user_keywords.extend(clean_list_items(getattr(current_user, "interests", [])))
    user_keywords.extend(clean_list_items(getattr(current_user, "goals", [])))
    user_keywords.extend(clean_list_items(getattr(current_user, "skills", [])))
    user_keywords.append(getattr(current_user, "profession", ""))
    user_keywords.append(getattr(current_user, "looking_for", ""))
    user_keywords.append(getattr(current_user, "country", ""))

    normalized_keywords = []
    for keyword in user_keywords:
        keyword = clean_text(keyword).lower()
        if keyword and keyword != "не указано" and len(keyword) > 2:
            normalized_keywords.append(keyword)

    for post in posts:
        author_email = normalize_email(post.get("email", ""))

        if not author_email:
            continue

        if is_blocked(current_user.email, author_email) or is_blocked(author_email, current_user.email):
            continue

        author = find_user_by_email(author_email)
        if author is None:
            continue

        content_language = normalize_content_language_code(post.get("language", ""))
        if content_language == "unknown":
            content_language = detect_content_language(" ".join([
                str(post.get("type", "")),
                str(post.get("text", "")),
                str(post.get("location", "")),
                " ".join(post.get("hashtags", []))
            ]))
            post["language"] = content_language
            feed_changed = True

        language_score, language_reason = score_language_match(current_user, content_language)

        post_text_for_ai = clean_text(" ".join([
            str(post.get("type", "")),
            str(post.get("text", "")),
            str(post.get("location", "")),
            " ".join(post.get("hashtags", []))
        ])).lower()

        interest_score = 0
        interest_reasons = []
        for keyword in normalized_keywords:
            if keyword and keyword in post_text_for_ai:
                interest_score += 18
                if len(interest_reasons) < 3:
                    interest_reasons.append(f"Совпадает с вашим интересом: {keyword}")

        engagement_score = min(len(post.get("likes", [])) * 2, 20)
        engagement_score += min(len(post.get("comments", [])) * 3, 24)
        engagement_score += min(len(post.get("saves", [])) * 4, 28)

        learning_score, learning_reasons = calculate_ai_learning_boost(current_user.email, post, content_language)

        try:
            recency_score = min(int(post.get("id", 0)), 100) / 10
        except Exception:
            recency_score = 0

        own_post_penalty = -8 if author_email == normalize_email(current_user.email) else 0
        final_score = language_score + interest_score + engagement_score + learning_score + recency_score + own_post_penalty

        ai_reasons = []
        if language_reason:
            ai_reasons.append(language_reason)
        ai_reasons.extend(interest_reasons)
        ai_reasons.extend(learning_reasons)
        if engagement_score >= 10:
            ai_reasons.append("Публикация получает активность от пользователей")
        if not ai_reasons:
            ai_reasons.append("AI показывает это как новый контент для изучения ваших интересов")
        if not ai_feed_enabled:
            ai_reasons = ["AI-рекомендации выключены: показана обычная лента"]
        elif not ai_activity_enabled:
            ai_reasons.append("Анализ вашей активности выключен, поэтому персонализация ограничена")

        ranked_posts.append({
            "post": post,
            "author": author,
            "score": final_score,
            "ai_reasons": ai_reasons[:4],
            "content_language": content_language
        })

    if feed_changed:
        feed_data["posts"] = posts
        save_feed(feed_data)

    if ai_feed_enabled:
        ranked_posts.sort(key=lambda item: item.get("score", 0), reverse=True)
    else:
        ranked_posts.reverse()

    for item in ranked_posts:
        post = item.get("post", {})
        author = item.get("author")
        ai_reasons = item.get("ai_reasons", [])
        content_language = normalize_content_language_code(item.get("content_language", post.get("language", "unknown")))
        content_language_name = CONTENT_LANGUAGES.get(content_language, "Unknown")
        author_email = normalize_email(author.email)

        media_html = ""
        media_items = post.get("media_items", [])

        if not media_items and post.get("media_url"):
            media_items = [{"url": post.get("media_url", ""), "type": post.get("media_type", ""), "name": "media"}]

        for media in media_items[:4]:
            media_url = media.get("url", "")
            media_type = media.get("type", "")

            if media_url and media_type == "image":
                media_html += f'<img src="{media_url}" style="width:100%;max-height:420px;object-fit:cover;border-radius:20px;margin-top:14px;">'
            elif media_url and media_type == "video":
                media_html += f'<video src="{media_url}" controls playsinline style="width:100%;max-height:420px;border-radius:20px;margin-top:14px;background:#020617;"></video>'
            elif media_url and media_type == "audio":
                media_html += f'<audio src="{media_url}" controls style="width:100%;margin-top:14px;"></audio>'

        hashtags_html = ""
        for tag in post.get("hashtags", [])[:8]:
            clean_tag = clean_text(tag).replace("#", "")
            hashtags_html += f'<a href="/hashtag/{safe_text(current_user.email)}/{safe_text(clean_tag)}" style="color:#93c5fd;text-decoration:none;background:rgba(37,99,235,0.14);padding:6px 9px;border-radius:999px;font-size:13px;font-weight:bold;">#{safe_text(clean_tag)}</a>'

        ai_reasons_html = ""
        for reason in ai_reasons:
            ai_reasons_html += f'<p style="margin:6px 0 0 0;color:#bfdbfe;">• {safe_text(reason)}</p>'

        message_link = ""
        if author_email != normalize_email(current_user.email):
            can_write, _, _ = get_message_permission_status(current_user, author)
            if can_write:
                message_link = f'<a href="/chat/{safe_text(current_user.email)}/{safe_text(author.email)}" style="background:#16a34a;color:white;text-decoration:none;padding:10px 12px;border-radius:14px;font-weight:bold;">Написать</a>'
            else:
                message_link = '<span style="background:#475569;color:#cbd5e1;padding:10px 12px;border-radius:14px;font-weight:bold;">Недоступно</span>'

        translate_link = ""
        if content_language not in user_language_codes and content_language != "unknown":
            translate_link = f'<a href="/translate_post/{safe_text(current_user.email)}/{post.get("id")}" style="background:#7c3aed;color:white;text-decoration:none;padding:10px 12px;border-radius:14px;font-weight:bold;">🌍 AI перевод</a>'

        posts_html += f"""
        <div style="background:#1e293b;border-radius:28px;padding:22px;margin-bottom:18px;border:1px solid rgba(148,163,184,0.10);">
            <div style="display:flex;align-items:center;justify-content:space-between;gap:14px;margin-bottom:14px;">
                <a href="/profile/{safe_text(author.email)}?viewer={safe_text(current_user.email)}" style="display:flex;align-items:center;gap:13px;color:white;text-decoration:none;">
                    <img src="{get_avatar_url(author.email)}" style="width:56px;height:56px;border-radius:50%;object-fit:cover;background:#334155;border:3px solid #334155;">
                    <div>
                        <strong>{safe_text(author.name)}</strong>
                        <p style="margin:5px 0 0 0;color:#94a3b8;font-size:13px;">{safe_text(author.profession)} · {safe_text(post.get("location", ""))}</p>
                    </div>
                </a>
                <div style="background:linear-gradient(135deg,#2563eb,#7c3aed);border-radius:999px;padding:9px 12px;font-weight:bold;white-space:nowrap;">AI {int(max(0, min(item.get("score", 0), 100)))}%</div>
            </div>

            <div style="color:#60a5fa;font-weight:bold;margin-bottom:8px;">{safe_text(post.get("type", "Публикация"))} · {safe_text(content_language_name)}</div>
            <p style="color:#e5e7eb;line-height:1.55;font-size:16px;white-space:pre-wrap;">{safe_text(post.get("text", ""))}</p>

            {media_html}

            <div style="display:flex;flex-wrap:wrap;gap:8px;margin-top:14px;">
                {hashtags_html}
            </div>

            <div style="background:#0f172a;border:1px solid rgba(96,165,250,0.18);border-radius:20px;padding:14px;margin-top:16px;color:#dbeafe;">
                <strong>🧠 Почему AI показал:</strong>
                {ai_reasons_html}
            </div>

            <div style="display:flex;flex-wrap:wrap;gap:9px;margin-top:16px;">
                <a href="/like_post/{safe_text(current_user.email)}/{post.get("id")}" style="background:#334155;color:white;text-decoration:none;padding:10px 12px;border-radius:14px;font-weight:bold;">♡ {len(post.get("likes", []))}</a>
                <a href="/post_comments/{safe_text(current_user.email)}/{post.get("id")}" style="background:#334155;color:white;text-decoration:none;padding:10px 12px;border-radius:14px;font-weight:bold;">💬 {len(post.get("comments", []))}</a>
                <a href="/save_post/{safe_text(current_user.email)}/{post.get("id")}" style="background:#334155;color:white;text-decoration:none;padding:10px 12px;border-radius:14px;font-weight:bold;">🔖 {len(post.get("saves", []))}</a>
                <a href="/post/{safe_text(current_user.email)}/{post.get("id")}" style="background:#334155;color:white;text-decoration:none;padding:10px 12px;border-radius:14px;font-weight:bold;">Открыть</a>
                {translate_link}
                {message_link}
            </div>
        </div>
        """

    if posts_html == "":
        posts_html = """
        <div style="background:#1e293b;padding:28px;border-radius:26px;color:#cbd5e1;text-align:center;">
            <h2>Пока нет публикаций</h2>
            <p>Создайте первый пост, идею, видео или проект. AI Discover начнёт строить умную ленту вокруг интересов пользователей.</p>
        </div>
        """

    user_languages_text = ", ".join(user_language_names) if user_language_names else "Авто"
    feed_mode_text = "AI-персонализация включена" if ai_feed_enabled else "Обычная лента"

    return f"""
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <title>AI Discover - AI Match Life</title>
    </head>
    <body style="margin:0;background:#0f172a;color:white;font-family:Arial,sans-serif;padding:28px;">
        <div style="max-width:1080px;margin:auto;">
            <a href="/dashboard/{safe_text(current_user.email)}" style="display:inline-block;color:white;text-decoration:none;background:#334155;padding:12px 16px;border-radius:14px;margin-bottom:18px;font-weight:bold;">← Назад</a>

            <div style="background:linear-gradient(135deg,#1e293b,#172554);padding:30px;border-radius:30px;margin-bottom:22px;border:1px solid rgba(148,163,184,0.14);">
                <h1 style="margin:0 0 10px 0;font-size:34px;">🧠 AI Discover</h1>
                <p style="margin:0;color:#cbd5e1;line-height:1.55;">Умная лента видео, идей, проектов, мест и людей. AI сначала поднимает контент на понятном языке, потом учитывает ваши интересы и активность.</p>
                <div style="display:flex;flex-wrap:wrap;gap:10px;margin-top:16px;">
                    <span style="background:rgba(37,99,235,0.22);border:1px solid rgba(96,165,250,0.26);color:#bfdbfe;border-radius:999px;padding:8px 12px;font-weight:bold;font-size:13px;">{safe_text(feed_mode_text)}</span>
                    <span style="background:rgba(15,23,42,0.58);border:1px solid rgba(148,163,184,0.20);color:#cbd5e1;border-radius:999px;padding:8px 12px;font-weight:bold;font-size:13px;">Ваши языки: {safe_text(user_languages_text)}</span>
                </div>
            </div>

            <div style="background:#1e293b;padding:22px;border-radius:26px;margin-bottom:22px;border:1px solid rgba(148,163,184,0.10);">
                <h2 style="margin:0 0 14px 0;">Создать публикацию</h2>
                <form method="POST" action="/create_post/{safe_text(current_user.email)}" enctype="multipart/form-data">
                    <input type="hidden" name="return_to" value="feed">
                    {csrf_input()}
                    <select name="type" style="width:100%;background:#0f172a;color:white;border:1px solid #334155;border-radius:16px;padding:13px 14px;margin-bottom:12px;">
                        <option value="Идея">Идея</option>
                        <option value="Видео">Видео</option>
                        <option value="Бизнес">Бизнес</option>
                        <option value="Ресторан">Ресторан</option>
                        <option value="Стартап">Стартап</option>
                        <option value="Услуга">Услуга</option>
                        <option value="Новость">Новость</option>
                        <option value="Проект">Проект</option>
                    </select>
                    <select name="language" style="width:100%;background:#0f172a;color:white;border:1px solid #334155;border-radius:16px;padding:13px 14px;margin-bottom:12px;">
                        <option value="">Автоопределение языка</option>
                        <option value="ru">Русский</option>
                        <option value="en">English</option>
                        <option value="de">Deutsch</option>
                        <option value="tr">Türkçe</option>
                        <option value="tk">Türkmençe</option>
                        <option value="uz">Oʻzbekcha</option>
                        <option value="ar">العربية</option>
                        <option value="es">Español</option>
                        <option value="fr">Français</option>
                        <option value="it">Italiano</option>
                        <option value="pt">Português</option>
                        <option value="pl">Polski</option>
                        <option value="uk">Українська</option>
                        <option value="zh">中文</option>
                    </select>
                    <input name="location" placeholder="Город / страна" style="width:100%;background:#0f172a;color:white;border:1px solid #334155;border-radius:16px;padding:13px 14px;margin-bottom:12px;">
                    <input name="hashtags" placeholder="#business #restaurant #germany" style="width:100%;background:#0f172a;color:white;border:1px solid #334155;border-radius:16px;padding:13px 14px;margin-bottom:12px;">
                    <textarea name="text" placeholder="Что хотите показать миру? Идея, видео, место, бизнес, проект..." required style="width:100%;min-height:110px;background:#0f172a;color:white;border:1px solid #334155;border-radius:16px;padding:13px 14px;margin-bottom:12px;"></textarea>
                    <input type="file" name="media" multiple accept="image/*,video/*,audio/*" style="width:100%;background:#0f172a;color:white;border:1px solid #334155;border-radius:16px;padding:13px 14px;margin-bottom:12px;">
                    <button type="submit" style="background:#2563eb;color:white;border:none;border-radius:16px;padding:14px 18px;font-weight:bold;cursor:pointer;width:100%;">Опубликовать в AI Discover</button>
                </form>
            </div>

            {posts_html}
        </div>
    </body>
    </html>
    """

def find_post_by_id(post_id):
    post_id = str(post_id or "").strip()
    feed_data = load_feed()

    for post in feed_data.get("posts", []):
        if str(post.get("id", "")).strip() == post_id:
            return post

    return None


def load_ai_feed_learning():
    try:
        with open("ai_feed_learning.json", "r", encoding="utf-8") as file:
            data = json.load(file)
            if isinstance(data, dict):
                return data
            return {}
    except Exception:
        return {}


def save_ai_feed_learning(data):
    with open("ai_feed_learning.json", "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4, ensure_ascii=False)


def record_ai_feed_signal(user_email, post, action_type):
    user_email = normalize_email(user_email)
    action_type = clean_text(action_type)

    if not user_email or not isinstance(post, dict):
        return

    try:
        data = load_ai_feed_learning()
        user_data = data.get(user_email, {
            "languages": {},
            "types": {},
            "hashtags": {},
            "locations": {},
            "actions": [],
            "updated_at": ""
        })

        if not isinstance(user_data, dict):
            user_data = {
                "languages": {},
                "types": {},
                "hashtags": {},
                "locations": {},
                "actions": [],
                "updated_at": ""
            }

        for key in ["languages", "types", "hashtags", "locations"]:
            if not isinstance(user_data.get(key), dict):
                user_data[key] = {}

        if not isinstance(user_data.get("actions"), list):
            user_data["actions"] = []

        content_language = normalize_content_language_code(post.get("language", ""))
        if content_language == "unknown":
            content_language = detect_content_language(" ".join([
                str(post.get("type", "")),
                str(post.get("text", "")),
                str(post.get("location", "")),
                " ".join(post.get("hashtags", []))
            ]))

        post_type = clean_text(post.get("type", "Публикация"))
        post_location = clean_text(post.get("location", ""))

        if content_language and content_language != "unknown":
            user_data["languages"][content_language] = user_data["languages"].get(content_language, 0) + 1

        if post_type:
            user_data["types"][post_type] = user_data["types"].get(post_type, 0) + 1

        if post_location:
            user_data["locations"][post_location] = user_data["locations"].get(post_location, 0) + 1

        for tag in post.get("hashtags", [])[:10]:
            clean_tag = clean_text(tag).replace("#", "").lower()
            if clean_tag:
                user_data["hashtags"][clean_tag] = user_data["hashtags"].get(clean_tag, 0) + 1

        user_data["actions"].append({
            "action": action_type,
            "post_id": str(post.get("id", "")),
            "language": content_language,
            "type": post_type,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        user_data["actions"] = user_data["actions"][-200:]
        user_data["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        data[user_email] = user_data
        save_ai_feed_learning(data)
    except Exception as error:
        log_security_event("ai_feed_learning_failed", user_email, str(error))

def calculate_ai_learning_boost(user_email, post, content_language):
    user_email = normalize_email(user_email)

    if not user_email or not isinstance(post, dict):
        return 0, []

    try:
        data = load_ai_feed_learning()
        user_data = data.get(user_email, {})

        if not isinstance(user_data, dict):
            return 0, []

        boost_score = 0
        boost_reasons = []

        learned_languages = user_data.get("languages", {}) if isinstance(user_data.get("languages", {}), dict) else {}
        learned_types = user_data.get("types", {}) if isinstance(user_data.get("types", {}), dict) else {}
        learned_hashtags = user_data.get("hashtags", {}) if isinstance(user_data.get("hashtags", {}), dict) else {}
        learned_locations = user_data.get("locations", {}) if isinstance(user_data.get("locations", {}), dict) else {}

        language_count = int(learned_languages.get(content_language, 0) or 0)
        if content_language and content_language != "unknown" and language_count > 0:
            boost_score += min(language_count * 4, 24)
            boost_reasons.append("AI заметил интерес к этому языку контента")

        post_type = clean_text(post.get("type", "Публикация"))
        type_count = int(learned_types.get(post_type, 0) or 0)
        if post_type and type_count > 0:
            boost_score += min(type_count * 5, 25)
            boost_reasons.append(f"AI заметил интерес к типу контента: {post_type}")

        post_location = clean_text(post.get("location", ""))
        location_count = int(learned_locations.get(post_location, 0) or 0)
        if post_location and location_count > 0:
            boost_score += min(location_count * 3, 18)
            boost_reasons.append(f"AI заметил интерес к локации: {post_location}")

        matched_tags = []
        for tag in post.get("hashtags", [])[:10]:
            clean_tag = clean_text(tag).replace("#", "").lower()
            tag_count = int(learned_hashtags.get(clean_tag, 0) or 0)
            if clean_tag and tag_count > 0:
                boost_score += min(tag_count * 4, 20)
                if len(matched_tags) < 3:
                    matched_tags.append(clean_tag)

        if matched_tags:
            boost_reasons.append("AI заметил интерес к темам: " + ", ".join(matched_tags))

        return min(boost_score, 60), boost_reasons[:3]
    except Exception as error:
        log_security_event("ai_learning_boost_failed", user_email, str(error))
        return 0, []


def generate_ai_translation_summary(text_value, source_language, target_language):
    text_value = clean_text(text_value)
    source_language = normalize_content_language_code(source_language)
    target_language = normalize_content_language_code(target_language)

    if not text_value:
        return "Текст для перевода не найден."

    openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
    openai_model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"

    source_language_name = CONTENT_LANGUAGES.get(source_language, source_language)
    target_language_name = CONTENT_LANGUAGES.get(target_language, target_language)

    if not openai_key.startswith("sk-"):
        return (
            "AI-перевод пока недоступен: OPENAI_API_KEY не подключён. "
            f"Оригинальный язык: {source_language_name}. Целевой язык: {target_language_name}."
        )

    prompt = (
        "You are an accurate multilingual assistant for a social network feed. "
        "Translate the post into the target language and add a short useful summary. "
        "Keep the meaning. Do not add false facts. Do not advertise anything.\n\n"
        f"Source language: {source_language_name}\n"
        f"Target language: {target_language_name}\n\n"
        f"Post text:\n{text_value}\n\n"
        "Return in this format:\n"
        "Translation:\n...\n\nShort summary:\n..."
    )

    payload = {
        "model": openai_model,
        "messages": [
            {"role": "system", "content": "You translate and summarize social feed posts accurately."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.2,
        "max_tokens": 700
    }

    try:
        import urllib.request

        request_data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=request_data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {openai_key}"
            },
            method="POST"
        )

        with urllib.request.urlopen(req, timeout=25) as response:
            result = json.loads(response.read().decode("utf-8"))
            return clean_text(result["choices"][0]["message"]["content"])
    except Exception as error:
        log_security_event("ai_translation_failed", session.get("user_email", ""), str(error))
        return "AI-перевод временно недоступен. Попробуйте позже."


@app.route("/translate_post/<email>/<post_id>")
@login_required
def translate_post_page(email, post_id):
    current_user = find_user_by_email(email)

    if current_user is None:
        return "User not found"

    post = find_post_by_id(post_id)
    if post is None:
        return simple_page("Пост не найден", "Публикация не найдена или была удалена.", current_user.email)

    author_email = normalize_email(post.get("email", ""))
    if is_blocked(current_user.email, author_email) or is_blocked(author_email, current_user.email):
        return simple_page("Доступ закрыт", "Вы не можете открыть перевод этой публикации.", current_user.email)

    content_language = normalize_content_language_code(post.get("language", ""))
    if content_language == "unknown":
        content_language = detect_content_language(" ".join([
            str(post.get("type", "")),
            str(post.get("text", "")),
            str(post.get("location", "")),
            " ".join(post.get("hashtags", []))
        ]))

    target_language = normalize_content_language_code(get_current_language(current_user))
    if target_language == "unknown":
        target_language = DEFAULT_LANGUAGE

    record_ai_feed_signal(current_user.email, post, "translate_post")

    source_text = post.get("text", "")
    cache_key = f"{content_language}->{target_language}"
    translation_cache = post.get("ai_translations", {})
    cached_translation = translation_cache.get(cache_key, {}) if isinstance(translation_cache, dict) else {}

    if cached_translation.get("source_text") == source_text and cached_translation.get("result"):
        translated_text = cached_translation.get("result", "")
        translation_cache_status = "Готовый AI-перевод загружен из кэша."
    else:
        translated_text = generate_ai_translation_summary(source_text, content_language, target_language)
        translation_cache_status = "AI-перевод создан и сохранён."

        try:
            feed_data = load_feed()
            for saved_post in feed_data.get("posts", []):
                if str(saved_post.get("id", "")).strip() == str(post_id).strip():
                    saved_cache = saved_post.get("ai_translations", {})
                    if not isinstance(saved_cache, dict):
                        saved_cache = {}

                    saved_cache[cache_key] = {
                        "source_text": source_text,
                        "result": translated_text,
                        "source_language": content_language,
                        "target_language": target_language,
                        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }
                    saved_post["ai_translations"] = saved_cache
                    break

            save_feed(feed_data)
        except Exception as error:
            log_security_event("ai_translation_cache_failed", current_user.email, str(error))
            translation_cache_status = "AI-перевод создан, но кэш сохранить не удалось."

    return f"""
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>AI перевод - AI Match Life</title>
    </head>
    <body style="margin:0;background:#0f172a;color:white;font-family:Arial,sans-serif;padding:28px;">
        <div style="max-width:880px;margin:auto;">
            <a href="/feed/{safe_text(current_user.email)}" style="display:inline-block;color:white;text-decoration:none;background:#334155;padding:12px 16px;border-radius:14px;margin-bottom:18px;font-weight:bold;">← Назад в AI Discover</a>

            <div style="background:linear-gradient(135deg,#1e293b,#172554);padding:28px;border-radius:28px;margin-bottom:18px;border:1px solid rgba(148,163,184,0.14);">
                <h1 style="margin:0 0 10px 0;">🌍 AI перевод</h1>
                <p style="margin:0;color:#cbd5e1;line-height:1.55;">AI помогает понять полезный контент, даже если он опубликован на другом языке.</p>
            </div>

            <div style="background:#1e293b;border-radius:24px;padding:22px;margin-bottom:18px;">
                <h2 style="margin:0 0 12px 0;color:#93c5fd;">Оригинал · {safe_text(CONTENT_LANGUAGES.get(content_language, content_language))}</h2>
                <p style="white-space:pre-wrap;line-height:1.6;color:#e5e7eb;">{safe_text(post.get("text", ""))}</p>
            </div>

            <div style="background:#0f172a;border:1px solid rgba(96,165,250,0.22);border-radius:24px;padding:22px;">
                <h2 style="margin:0 0 12px 0;color:#bfdbfe;">AI результат · {safe_text(CONTENT_LANGUAGES.get(target_language, target_language))}</h2>
                <p style="margin:0 0 12px 0;color:#94a3b8;font-size:14px;">{safe_text(translation_cache_status)}</p>
                <p style="white-space:pre-wrap;line-height:1.6;color:#dbeafe;">{safe_text(translated_text)}</p>
            </div>
        </div>
    </body>
    </html>
    """


def get_message_permission_status(sender_user, receiver_user):
    if sender_user is None or receiver_user is None:
        return False, "Пользователь не найден", "Невозможно открыть переписку, потому что один из пользователей не найден."

    sender_email = normalize_email(sender_user.email)
    receiver_email = normalize_email(receiver_user.email)

    if not sender_email or not receiver_email:
        return False, "Сообщения недоступны", "Невозможно проверить настройки сообщений."

    if is_blocked(receiver_email, sender_email):
        return False, "🚫 Сообщение недоступно", "Этот пользователь заблокировал вас. Вы не можете отправить ему сообщение."

    if is_blocked(sender_email, receiver_email):
        return False, "🚫 Пользователь заблокирован", "Вы заблокировали этого пользователя. Разблокируйте его в настройках, если хотите написать сообщение."

    receiver_settings = normalize_user_ai_settings(receiver_email)
    permission = receiver_settings.get("message_permission", "everyone")

    if permission == "none":
        return False, "💬 Сообщения закрыты", "Этот пользователь сейчас не принимает личные сообщения."

    if permission == "friends" and not are_friends(sender_email, receiver_email):
        return False, "👥 Только друзья", "Этот пользователь принимает сообщения только от друзей. Добавьте друг друга в друзья, чтобы начать переписку."

    if permission == "verified" and getattr(sender_user, "verified", False) is False:
        return False, "🛡 Только verified", "Этот пользователь принимает сообщения только от проверенных аккаунтов."

    return True, "", ""


def can_send_message(sender_user, receiver_user):
    allowed, _, _ = get_message_permission_status(sender_user, receiver_user)
    return allowed

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

                <a href="/chat/{safe_text(current_user.email)}/{safe_text(other_user.email)}" style="background:#2563eb;color:white;text-decoration:none;padding:12px 16px;border-radius:14px;font-weight:bold;">
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
        can_write, block_title, block_text = get_message_permission_status(current_user, user)

        if can_write:
            message_action_html = f"""
            <a href="/chat/{safe_text(current_user.email)}/{safe_text(user.email)}" style="background:#16a34a;color:white;text-decoration:none;padding:10px 14px;border-radius:14px;font-weight:bold;white-space:nowrap;">
                Написать
            </a>
            """
            permission_note_html = ""
        else:
            message_action_html = f"""
            <span title="{safe_text(block_text)}" style="background:#475569;color:#cbd5e1;text-decoration:none;padding:10px 14px;border-radius:14px;font-weight:bold;cursor:not-allowed;white-space:nowrap;">
                Недоступно
            </span>
            """
            permission_note_html = f"""
            <p style="margin:6px 0 0 0;color:#94a3b8;font-size:13px;">{safe_text(block_title)}</p>
            """

        users_html += f"""
        <div style="background:#1e293b;padding:18px;border-radius:22px;margin-bottom:14px;display:flex;align-items:center;gap:16px;">
            <img src="{avatar_url}" style="width:58px;height:58px;border-radius:50%;object-fit:cover;background:#334155;border:3px solid #334155;">

            <div style="flex:1;">
                <h3 style="margin:0 0 6px 0;font-size:18px;">{safe_text(user.name)}</h3>
                <p style="margin:0;color:#cbd5e1;">{safe_text(user.profession)}</p>
                {permission_note_html}
            </div>

            {message_action_html}
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

            <a href="/dashboard/{safe_text(current_user.email)}" style="display:inline-block;color:white;text-decoration:none;background:#334155;padding:12px 16px;border-radius:14px;margin-bottom:18px;font-weight:bold;">
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
        log_security_event("call_blocked", sender.email, f"Blocked audio call attempt to {receiver.email}")
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
        log_security_event("call_blocked", sender.email, f"Blocked video call attempt to {receiver.email}")
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

    can_write, block_title, block_text = get_message_permission_status(sender, receiver)
    if not can_write:
        log_security_event("chat_permission_blocked", sender.email, f"Blocked chat attempt to {receiver.email}: {block_title}")
        return simple_page(block_title, block_text, sender.email)

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
            <div class="message-bubble" id="message-{msg_id}" data-message-id="{msg_id}" onclick="handleMessageClick('{msg_id}')" ondblclick="event.stopPropagation(); toggleReactionMenu('{msg_id}')" oncontextmenu="event.preventDefault(); event.stopPropagation(); toggleMessageMenu('{msg_id}')" onmousedown="startMessageLongPress(event, '{msg_id}')" onmouseup="cancelMessageLongPress()" onmouseleave="cancelMessageLongPress()" ontouchstart="startMessageLongPress(event, '{msg_id}')" ontouchend="cancelMessageLongPress()">
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

                <div class="reaction-menu" id="reaction-menu-{msg_id}" onclick="event.stopPropagation()">
                    <a href="/react_message/{sender.email}/{receiver.email}/{msg_id}/❤️" class="reaction-action" onclick="pickReaction(event, this)">❤️</a>
                    <a href="/react_message/{sender.email}/{receiver.email}/{msg_id}/😂" class="reaction-action" onclick="pickReaction(event, this)">😂</a>
                    <a href="/react_message/{sender.email}/{receiver.email}/{msg_id}/👍" class="reaction-action" onclick="pickReaction(event, this)">👍</a>
                    <a href="/react_message/{sender.email}/{receiver.email}/{msg_id}/🔥" class="reaction-action" onclick="pickReaction(event, this)">🔥</a>
                    <a href="/react_message/{sender.email}/{receiver.email}/{msg_id}/😮" class="reaction-action" onclick="pickReaction(event, this)">😮</a>
                </div>

                <div class="message-menu" id="message-menu-{msg_id}" onclick="event.stopPropagation()">
                    <button type="button" class="menu-action" onclick="replyToMessage('{msg_id}', `{message_text}`)">↩ Ответить</button>
                    <button type="button" class="menu-action" onclick="startEditMessage('{msg_id}', `{message_text}`)">✏️ Изменить</button>
                    <a href="/forward_message_select/{sender.email}/{receiver.email}/{msg_id}" class="menu-action">↪ Переслать</a>
                    <button type="button" class="menu-action" onclick="copyMessageText(`{message_text}`)">📋 Копировать</button>
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
    /* --- WhatsApp-style separated reaction bar and action menu --- */
    .reaction-menu{{
        display:none;
        position:absolute;
        bottom:calc(100% + 10px);
        z-index:35;
        background:rgba(15,23,42,0.98);
        border:1px solid rgba(148,163,184,0.24);
        border-radius:999px;
        padding:8px;
        gap:6px;
        align-items:center;
        box-shadow:0 18px 45px rgba(0,0,0,0.42);
        backdrop-filter:blur(14px);
        transform-origin:center bottom;
        animation:reactionMenuPop 0.18s ease-out;
    }}
    .mine .reaction-menu{{ right:0; }}
    .theirs .reaction-menu{{ left:0; }}
    .reaction-menu.open{{ display:flex; }}
    .reaction-action{{
        width:38px;
        height:38px;
        border-radius:50%;
        display:flex;
        align-items:center;
        justify-content:center;
        text-decoration:none;
        background:rgba(51,65,85,0.86);
        font-size:20px;
        transition:0.16s ease;
        transform-origin:center;
        user-select:none;
        -webkit-tap-highlight-color:transparent;
    }}
    .reaction-action:hover{{
        transform:translateY(-4px) scale(1.18);
        background:#475569;
    }}
    .reaction-action.reaction-picked{{
        animation:reactionPicked 0.28s ease-out forwards;
        background:#334155;
    }}
    @keyframes reactionMenuPop{{
        from{{ opacity:0; transform:translateY(8px) scale(0.92); }}
        to{{ opacity:1; transform:translateY(0) scale(1); }}
    }}
    @keyframes reactionPicked{{
        0%{{ transform:scale(1); }}
        45%{{ transform:scale(1.62); }}
        100%{{ transform:scale(0.92); opacity:0.15; }}
    }}
    
     .message-menu{{
        display:none;
        position:fixed;
        left:0;
        top:0;
        transform:none;
        z-index:10050;
        background:rgba(15,23,42,0.98);
        border:1px solid rgba(148,163,184,0.24);
        border-radius:15px;
        padding:5px;
        gap:4px;
        flex-direction:column;
        width:164px;
        max-width:calc(100vw - 24px);
        box-shadow:0 18px 42px rgba(0,0,0,0.50);
        backdrop-filter:blur(18px);
        animation:messageMenuSlideDown 0.13s ease-out;
    }}
    
    .mine .message-menu{{ right:auto; }}
    .theirs .message-menu{{ left:0; }}
    .message-menu.open{{ display:flex !important; }}
    @keyframes messageMenuSlideDown{{
        from{{ opacity:0; transform:translateY(-6px) scale(0.97); }}
        to{{ opacity:1; transform:translateY(0) scale(1); }}
    }}
    .menu-action{{
        width:100%;
        box-sizing:border-box;
        background:rgba(51,65,85,0.92);
        color:white;
        border:none;
        border-radius:9px;
        padding:6px 8px;
        cursor:pointer;
        text-decoration:none;
        font-size:11px;
        font-weight:700;
        white-space:nowrap;
        line-height:1.1;
        text-align:left;
        display:block;
        transition:0.14s ease;
    }}
    .menu-action:hover{{
        background:#475569;
        transform:translateY(-1px) scale(1.01);
    }}
    .menu-action.danger{{
        background:rgba(220,38,38,0.92);
    }}
    
    .message-bubble.menu-open{{
    z-index:80;
    transform:translateY(-2px) scale(1.015);
    box-shadow:0 18px 44px rgba(0,0,0,0.42), 0 0 0 1px rgba(96,165,250,0.30);
    transition:0.16s ease;
}}

body.chat-focus-mode .message-bubble:not(.menu-open){{
    opacity:0.30;
    filter:blur(1px) saturate(0.72);
    transform:scale(0.985);
    transition:0.16s ease;
}}

body.chat-focus-mode .pinned-box,
body.chat-focus-mode .header,
body.chat-focus-mode .composer,
body.chat-focus-mode .hint,
body.chat-focus-mode .search-panel{{
    opacity:0.68;
    filter:saturate(0.74);
    transition:0.16s ease;
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

        closeMessagePopups();
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

        closeMessagePopups();
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

    let messageLongPressTimer = null;
    let messageLongPressTriggered = false;

    function closeMessagePopups() {{
        document.querySelectorAll('.message-menu').forEach(menu => menu.classList.remove('open'));
        document.querySelectorAll('.reaction-menu').forEach(menu => menu.classList.remove('open'));
        document.querySelectorAll('.message-bubble').forEach(bubble => bubble.classList.remove('menu-open'));
        document.body.classList.remove('chat-focus-mode');
    }}

    function toggleMessageMenu(messageId) {{
        const currentMenu = document.getElementById('message-menu-' + messageId);
        const currentBubble = document.getElementById('message-' + messageId);
        if (!currentMenu || !currentBubble) return;

        const willOpen = !currentMenu.classList.contains('open');
        closeMessagePopups();

        if (willOpen) {{
            document.body.classList.add('chat-focus-mode');
            currentBubble.classList.add('menu-open');

            if (currentMenu.parentElement !== document.body) {{
                document.body.appendChild(currentMenu);
            }}

            currentMenu.classList.add('open');

            const bubbleRect = currentBubble.getBoundingClientRect();
            const menuRect = currentMenu.getBoundingClientRect();
            const margin = 8;

            let left = bubbleRect.left;
            if (currentBubble.closest('.mine')) {{
                left = bubbleRect.right - menuRect.width;
            }}

            let top = bubbleRect.bottom + 6;

            if (left < margin) left = margin;
            if (left + menuRect.width > window.innerWidth - margin) {{
                left = window.innerWidth - menuRect.width - margin;
            }}

            if (top + menuRect.height > window.innerHeight - margin) {{
                top = bubbleRect.top - menuRect.height - 6;
            }}

            if (top < margin) top = margin;

            currentMenu.style.left = left + 'px';
            currentMenu.style.top = top + 'px';
        }}
    }}

    function toggleReactionMenu(messageId) {{
        const currentReactionMenu = document.getElementById('reaction-menu-' + messageId);
        const currentBubble = document.getElementById('message-' + messageId);
        if (!currentReactionMenu || !currentBubble) return;

        const willOpen = !currentReactionMenu.classList.contains('open');
        closeMessagePopups();

        if (willOpen) {{
            document.body.classList.add('chat-focus-mode');
            currentReactionMenu.classList.add('open');
            currentBubble.classList.add('menu-open');
        }}
    }}

    function startMessageLongPress(event, messageId) {{
        if (
            event.target.closest('.message-menu') ||
            event.target.closest('.reaction-menu') ||
            event.target.closest('.message-select-check') ||
            event.target.closest('.menu-action') ||
            event.target.closest('.reaction-action')
        ) return;

        messageLongPressTriggered = false;
        clearTimeout(messageLongPressTimer);

        messageLongPressTimer = setTimeout(function() {{
            messageLongPressTriggered = true;
            if (event && event.preventDefault) event.preventDefault();
            toggleMessageMenu(messageId);
        }}, 300);

    }}

    function cancelMessageLongPress() {{
        clearTimeout(messageLongPressTimer);
    }}

    function quickReactMessage(url) {{
        window.location.href = url;
    }}

    function pickReaction(event, element) {{
        event.preventDefault();
        event.stopPropagation();

        if (!element || element.classList.contains('reaction-picked')) return;

        element.classList.add('reaction-picked');

        const menu = element.closest('.reaction-menu');
        const bubble = element.closest('.message-bubble');

        setTimeout(function() {{
            if (menu) menu.classList.remove('open');
            if (bubble) bubble.classList.remove('menu-open');
            document.querySelectorAll('.message-menu').forEach(item => item.classList.remove('open'));
            document.body.classList.remove('chat-focus-mode');
        }}, 180);

        setTimeout(function() {{
            window.location.href = element.href;
        }}, 260);
    }}

    let selectedMessageIds = [];
    let messageSelectionMode = false;

    function handleMessageClick(messageId) {{
        if (messageLongPressTriggered) {{
            messageLongPressTriggered = false;
            return;
        }}

        if (typeof messageSelectionMode !== 'undefined' && messageSelectionMode) {{
            toggleMessageSelected(messageId);
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
            closeMessagePopups();
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
        const menuIsOpen = document.querySelector('.message-menu.open') || document.querySelector('.reaction-menu.open') || document.body.classList.contains('chat-focus-mode');

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




def create_social_notification(target_email, text, notification_type="social", from_email=""):
    target_email = normalize_email(target_email)
    from_email = normalize_email(from_email)

    if not target_email:
        return


    notifications_file = "notifications.json"

    try:
        if os.path.exists(notifications_file):
            with open(notifications_file, "r", encoding="utf-8") as file:
                data = json.load(file)
        else:
            data = {}
    except Exception:
        data = {}

    if isinstance(data, list):
        data = {"notifications": data}

    if "notifications" not in data or not isinstance(data.get("notifications"), list):
        data["notifications"] = []

    now = datetime.now()

    data["notifications"].insert(0, {
        "email": target_email,
        "from": from_email,
        "from_email": from_email,
        "type": notification_type,
        "text": clean_text(text),
        "read": False,
        "created_at": now.strftime("%Y-%m-%d %H:%M"),
        "created_at_iso": now.strftime("%Y-%m-%d %H:%M:%S"),
        "time_label": now.strftime("%H:%M")
    })

    with open(notifications_file, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=4)


def update_friend_request_notification_status(target_email, from_email, status):
    target_email = normalize_email(target_email)
    from_email = normalize_email(from_email)

    if not target_email or not from_email:
        return

    notifications_file = "notifications.json"

    try:
        if os.path.exists(notifications_file):
            with open(notifications_file, "r", encoding="utf-8") as file:
                data = json.load(file)
        else:
            return
    except Exception:
        return

    if isinstance(data, dict):
        notifications = data.get("notifications", [])
    elif isinstance(data, list):
        notifications = data
    else:
        return

    for item in notifications:
        if not isinstance(item, dict):
            continue

        item_email = normalize_email(item.get("email", ""))
        item_from = normalize_email(item.get("from_email") or item.get("from") or "")
        item_type = item.get("type", "")

        if item_email == target_email and item_from == from_email and item_type == "friend_request":
            item["status"] = status
            item["read"] = True
            item["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            break

    try:
        with open(notifications_file, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=4)
    except Exception:
        return


@app.route("/accept_friend_request/<viewer_email>/<profile_email>", endpoint="accept_friend_request_route_social")
def accept_friend_request_route_social(viewer_email, profile_email):
    viewer = find_user_by_email(viewer_email)
    profile = find_user_by_email(profile_email)

    if viewer is None or profile is None:
        return "User not found", 404

    existing_accept = globals().get("accept_friend_request")
    if callable(existing_accept):
        existing_accept(profile_email, viewer_email)

    update_friend_request_notification_status(viewer_email, profile_email, "accepted")

    create_social_notification(
        profile_email,
        f"{viewer.name} принял вашу заявку в друзья.",
        "friend_request_accepted",
        viewer_email
    )

    return redirect(f"/friend_requests/{viewer_email}")


@app.route("/decline_friend_request/<viewer_email>/<profile_email>")
def decline_friend_request_route(viewer_email, profile_email):
    viewer = find_user_by_email(viewer_email)
    profile = find_user_by_email(profile_email)

    if viewer is None or profile is None:
        return "User not found", 404

    existing_decline = globals().get("decline_friend_request")
    if callable(existing_decline):
        existing_decline(profile_email, viewer_email)

    update_friend_request_notification_status(viewer_email, profile_email, "declined")

    create_social_notification(
        profile_email,
        f"{viewer.name} отклонил вашу заявку в друзья.",
        "friend_request_declined",
        viewer_email
    )

    return redirect(f"/friend_requests/{viewer_email}")


@app.route("/follow/<viewer_email>/<profile_email>")
def follow_user_route(viewer_email, profile_email):
    viewer = find_user_by_email(viewer_email)
    profile = find_user_by_email(profile_email)

    if viewer is None or profile is None:
        return "User not found", 404

    if viewer_email == profile_email:
        return redirect(f"/profile/{profile_email}?viewer={viewer_email}")

    existing_follow = globals().get("follow_user")
    if callable(existing_follow):
        existing_follow(viewer_email, profile_email)

    create_social_notification(
        profile_email,
        f"{viewer.name} подписался на вас.",
        "new_follower",
        viewer_email
    )

    return redirect(f"/profile/{profile_email}?viewer={viewer_email}")


@app.route("/unfollow/<viewer_email>/<profile_email>")
def unfollow_user_route(viewer_email, profile_email):
    viewer = find_user_by_email(viewer_email)
    profile = find_user_by_email(profile_email)

    if viewer is None or profile is None:
        return "User not found", 404

    existing_unfollow = globals().get("unfollow_user")
    if callable(existing_unfollow):
        existing_unfollow(viewer_email, profile_email)

    return redirect(f"/profile/{profile_email}?viewer={viewer_email}")


@app.route("/send_friend_request/<viewer_email>/<profile_email>", endpoint="send_friend_request_route_social")
def send_friend_request_route_social(viewer_email, profile_email):
    viewer = find_user_by_email(viewer_email)
    profile = find_user_by_email(profile_email)

    if viewer is None or profile is None:
        return "User not found", 404

    if viewer_email == profile_email:
        return redirect(f"/profile/{profile_email}?viewer={viewer_email}")

    existing_follow = globals().get("follow_user")
    if callable(existing_follow):
        existing_follow(viewer_email, profile_email)

    existing_send_request = globals().get("send_friend_request")
    if callable(existing_send_request):
        existing_send_request(viewer_email, profile_email)

    create_social_notification(
        profile_email,
        f"{viewer.name} отправил вам заявку в друзья.",
        "friend_request",
        viewer_email
    )

    return redirect(f"/profile/{profile_email}?viewer={viewer_email}")


@app.route("/notifications/<email>")
def notifications_page(email):
    user = find_user_by_email(email)

    if user is None:
        return "User not found", 404

    notifications = get_notifications(email)
    cards = ""

    for item in notifications:
        if isinstance(item, dict):
            text = safe_text(item.get("text", ""))
            created_at = safe_text(item.get("time_label") or item.get("created_at") or "")
            from_email = normalize_email(item.get("from_email") or item.get("from") or "")
            notification_type = item.get("type", "social")
        else:
            text = safe_text(item)
            created_at = ""
            from_email = ""
            notification_type = "social"

        if not text and not from_email:
            continue

        sender = find_user_by_email(from_email) if from_email else None

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
            sender_avatar = get_avatar_url(sender.email)
            sender_name = safe_text(sender.name)

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
                    <a href="/accept_friend_request/{email}/{sender.email}" class="mini-btn accept">Принять</a>
                    <a href="/decline_friend_request/{email}/{sender.email}" class="mini-btn decline">Отклонить</a>
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
            .notification-body{{
                min-width:0;
            }}
            .notification-text{{
                font-size:16px;
                line-height:1.35;
                font-weight:850;
                color:#f8fafc;
            }}
            .notification-icon{{
                margin-right:4px;
            }}
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

@app.route("/radar/<email>")
def radar_page(email):
    current_user = find_user_by_email(email)

    if current_user is None:
        return "User not found"

    current_settings = normalize_user_ai_settings(current_user.email)
    radar_enabled = current_settings.get("ai_life_radar", True) is True
    recommendations_enabled = current_settings.get("ai_recommendations", True) is True

    openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
    openai_model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"

    if openai_key.startswith("sk-"):
        ai_status_text = f"🟢 Real AI активен · {openai_model}"
        ai_status_color = "#22c55e"
    else:
        ai_status_text = "🟡 AI fallback mode · добавьте OPENAI_API_KEY"
        ai_status_color = "#f59e0b"

    raw_matches = find_best_matches(current_user, users) if radar_enabled and recommendations_enabled else []
    seen_emails = set()
    cleaned_matches = []

    for match in raw_matches:
        matched_user = match.get("user") if isinstance(match, dict) else None

        if matched_user is None:
            continue

        matched_email = normalize_email(getattr(matched_user, "email", ""))

        if not matched_email or matched_email in seen_emails:
            continue

        if not can_show_user_in_ai_recommendations(current_user.email, matched_user):
            continue

        seen_emails.add(matched_email)
        cleaned_matches.append(match)

    life_actions = [
        {
            "title": "Усилить профиль",
            "text": "Добавьте цели, навыки, интересы и конкретный запрос. AI будет точнее подбирать людей.",
            "url": f"/edit_profile/{current_user.email}",
            "button": "Редактировать"
        },
        {
            "title": "Найти людей по профессии",
            "text": "Откройте AI Matches и посмотрите людей по профессии, интересам и общим целям.",
            "url": f"/matches/{current_user.email}",
            "button": "Найти людей"
        },
        {
            "title": "Добавить Proof Profile",
            "text": "Подтвердите опыт, навыки или достижения, чтобы повысить доверие к профилю.",
            "url": f"/proof/{current_user.email}/{current_user.email}",
            "button": "Повысить Trust"
        }
    ]
    action_cards_html = ""

    for index, action in enumerate(life_actions, start=1):
        action_cards_html += f"""
        <a class="action-card" href="{action['url']}">
            <div class="action-number">{index}</div>
            <div class="action-content">
                <strong>{safe_text(action['title'])}</strong>
                <span>{safe_text(action['text'])}</span>
            </div>
            <div class="action-open">{safe_text(action['button'])}</div>
        </a>
        """

    people_html = ""

    for match in cleaned_matches[:8]:
        matched_user = match["user"]
        score = int(match.get("score", 0))
        avatar_url = get_avatar_url(matched_user.email)

        ai_reasons = explain_user_match(current_user, matched_user)
        fallback_reasons = explain_match(current_user, matched_user)

        reasons = ai_reasons if ai_reasons else fallback_reasons

        reasons_html = ""
        for reason in reasons[:4]:
            reasons_html += f"<li>{safe_text(reason)}</li>"

        if reasons_html == "":
            reasons_html = "<li>AI пока не нашёл сильных объяснений. Заполните цели, интересы и навыки точнее.</li>"

        profession = safe_text(getattr(matched_user, "profession", ""))
        location = safe_text(getattr(matched_user, "location", ""))
        country = safe_text(getattr(matched_user, "country", ""))
        city = safe_text(getattr(matched_user, "city", ""))
        trust_score = safe_text(getattr(matched_user, "trust_score", 0))

        location_parts = []
        if city != "не указано":
            location_parts.append(city)
        if country != "не указано":
            location_parts.append(country)
        if not location_parts and location != "не указано":
            location_parts.append(location)

        location_text = ", ".join(location_parts) if location_parts else "Локация не указана"

        if score >= 80:
            match_label = "Очень сильное совпадение"
            score_class = "score-high"
        elif score >= 55:
            match_label = "Хороший потенциал"
            score_class = "score-mid"
        else:
            match_label = "Можно изучить"
            score_class = "score-low"

        people_html += f"""
        <article class="person-card">
            <div class="person-top">
                <div class="avatar-ring">
                    <img src="{avatar_url}" alt="Avatar">
                </div>

                <div class="person-main">
                    <div class="person-name-row">
                        <h2>{safe_text(matched_user.name)}</h2>
                        <span class="trust-pill">Trust {trust_score}</span>
                    </div>
                    <p class="person-profession">{profession}</p>
                    <p class="person-location">📍 {safe_text(location_text)}</p>
                </div>

                <div class="score-box {score_class}">
                    <div class="score-value">{score}%</div>
                    <div class="score-label">{match_label}</div>
                </div>
            </div>

            <div class="ai-explain-box">
                <div class="ai-explain-head">
                    <span>🧠 AI объяснение</span>
                    <small>{safe_text(ai_status_text)}</small>
                </div>
                <ul>{reasons_html}</ul>
            </div>

            <div class="person-actions">
                <a href="/profile/{matched_user.email}?viewer={current_user.email}" class="primary-action">Открыть профиль</a>
                <a href="/chat/{current_user.email}/{matched_user.email}" class="secondary-action">Написать</a>
            </div>
        </article>
        """

    if people_html == "":
        if not radar_enabled:
            people_html = """
            <div class="empty-card">
                <h2>AI Life Radar выключен</h2>
                <p>Вы отключили AI Life Radar в настройках. Включите его в Settings → AI, чтобы снова получать персональные рекомендации.</p>
            </div>
            """
        elif not recommendations_enabled:
            people_html = """
            <div class="empty-card">
                <h2>AI рекомендации выключены</h2>
                <p>Вы отключили AI рекомендации в настройках. Система не будет подбирать людей, пока вы снова не включите эту функцию.</p>
            </div>
            """
        else:
            people_html = """
            <div class="empty-card">
                <h2>AI Radar пока не нашёл подходящих людей</h2>
                <p>Заполните профиль: цели, интересы, навыки, профессию и кого вы ищете. Также часть пользователей может быть скрыта из-за их Privacy & AI настроек.</p>
            </div>
            """

    return f"""
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>AI Life Radar</title>
        <style>
            body{{
                margin:0;
                background:#0f172a;
                color:white;
                font-family:Arial,sans-serif;
            }}
            .page{{
                max-width:1120px;
                margin:auto;
                padding:30px;
            }}
            .back{{
                display:inline-flex;
                align-items:center;
                gap:8px;
                color:white;
                text-decoration:none;
                background:#1e293b;
                border:1px solid rgba(148,163,184,0.18);
                padding:12px 16px;
                border-radius:16px;
                margin-bottom:18px;
                font-weight:800;
            }}
            .hero{{
                background:radial-gradient(circle at top left,rgba(37,99,235,0.52),transparent 34%),linear-gradient(135deg,#1e293b,#172554 65%,#111827);
                padding:34px;
                border-radius:34px;
                margin-bottom:24px;
                border:1px solid rgba(148,163,184,0.14);
                box-shadow:0 22px 60px rgba(0,0,0,0.28);
            }}
            .hero-top{{
                display:flex;
                justify-content:space-between;
                gap:18px;
                align-items:flex-start;
                flex-wrap:wrap;
            }}
            .hero h1{{
                margin:0 0 10px 0;
                font-size:42px;
                letter-spacing:-1px;
            }}
            .hero p{{
                color:#cbd5e1;
                margin:0;
                font-size:17px;
                line-height:1.55;
                max-width:760px;
            }}
            .ai-status{{
                background:rgba(15,23,42,0.74);
                border:1px solid rgba(148,163,184,0.22);
                color:white;
                border-radius:999px;
                padding:10px 14px;
                font-size:13px;
                font-weight:900;
                display:inline-flex;
                align-items:center;
                gap:8px;
                box-shadow:0 12px 28px rgba(0,0,0,0.25);
            }}
            .status-dot{{
                width:10px;
                height:10px;
                border-radius:50%;
                background:{ai_status_color};
                box-shadow:0 0 0 6px rgba(34,197,94,0.10);
            }}
            .section{{
                background:#1e293b;
                padding:24px;
                border-radius:28px;
                margin-bottom:22px;
                border:1px solid rgba(148,163,184,0.12);
                box-shadow:0 16px 40px rgba(0,0,0,0.20);
            }}
            .section h2{{
                margin:0 0 8px 0;
                font-size:26px;
            }}
            .section p{{
                margin:0;
                color:#cbd5e1;
                line-height:1.5;
            }}
            .actions-grid{{
                display:grid;
                grid-template-columns:repeat(auto-fit,minmax(210px,1fr));
                gap:12px;
                margin-top:18px;
            }}
            .action-card{{
                background:#0f172a;
                border:1px solid rgba(96,165,250,0.16);
                border-radius:18px;
                padding:14px;
                color:#dbeafe;
                font-weight:750;
                line-height:1.45;
                display:flex;
                gap:12px;
                align-items:flex-start;
                text-decoration:none;
                min-height:84px;
                transition:0.16s ease;
            }}
            .action-card:hover{{
                transform:translateY(-2px);
                background:#111c33;
                border-color:rgba(96,165,250,0.34);
                box-shadow:0 14px 30px rgba(0,0,0,0.22);
            }}
            .action-content{{
                flex:1;
                min-width:0;
                display:flex;
                flex-direction:column;
                gap:5px;
            }}
            .action-content strong{{
                color:#f8fafc;
                font-size:15px;
            }}
            .action-content span{{
                color:#cbd5e1;
                font-size:13px;
                line-height:1.35;
            }}
            .action-open{{
                align-self:center;
                background:#2563eb;
                color:white;
                border-radius:999px;
                padding:8px 11px;
                font-size:12px;
                font-weight:900;
                white-space:nowrap;
            }}
            .action-number{{
                min-width:28px;
                height:28px;
                border-radius:50%;
                background:#2563eb;
                display:flex;
                align-items:center;
                justify-content:center;
                font-size:13px;
                font-weight:900;
            }}
            .person-card{{
                background:#1e293b;
                border:1px solid rgba(148,163,184,0.12);
                padding:22px;
                border-radius:28px;
                margin-bottom:18px;
                box-shadow:0 18px 44px rgba(0,0,0,0.22);
            }}
            .person-top{{
                display:flex;
                align-items:center;
                gap:18px;
            }}
            .avatar-ring{{
                width:84px;
                height:84px;
                border-radius:50%;
                padding:3px;
                background:linear-gradient(135deg,#2563eb,#8b5cf6,#ec4899);
                flex-shrink:0;
            }}
            .avatar-ring img{{
                width:100%;
                height:100%;
                border-radius:50%;
                object-fit:cover;
                background:#334155;
                border:3px solid #1e293b;
                box-sizing:border-box;
            }}
            .person-main{{flex:1;min-width:0;}}
            .person-name-row{{display:flex;gap:10px;align-items:center;flex-wrap:wrap;}}
            .person-name-row h2{{margin:0;font-size:25px;}}
            .trust-pill{{
                background:rgba(34,197,94,0.12);
                color:#4ade80;
                border:1px solid rgba(34,197,94,0.22);
                padding:5px 9px;
                border-radius:999px;
                font-size:12px;
                font-weight:900;
            }}
            .person-profession,.person-location{{
                margin:6px 0 0 0;
                color:#cbd5e1;
            }}
            .score-box{{
                min-width:150px;
                text-align:center;
                padding:14px 16px;
                border-radius:22px;
                background:#0f172a;
                border:1px solid rgba(148,163,184,0.12);
            }}
            .score-value{{font-size:30px;font-weight:900;}}
            .score-label{{font-size:12px;color:#cbd5e1;font-weight:800;margin-top:4px;}}
            .score-high .score-value{{color:#22c55e;}}
            .score-mid .score-value{{color:#f59e0b;}}
            .score-low .score-value{{color:#60a5fa;}}
            .ai-explain-box{{
                background:#0f172a;
                border:1px solid rgba(96,165,250,0.12);
                padding:16px;
                border-radius:20px;
                margin-top:18px;
            }}
            .ai-explain-head{{
                display:flex;
                justify-content:space-between;
                gap:12px;
                align-items:center;
                margin-bottom:10px;
                font-weight:900;
            }}
            .ai-explain-head small{{color:#94a3b8;font-weight:800;}}
            .ai-explain-box ul{{
                margin:0;
                padding-left:21px;
                color:#cbd5e1;
                line-height:1.65;
            }}
            .person-actions{{
                display:flex;
                gap:10px;
                flex-wrap:wrap;
                margin-top:16px;
            }}
            .primary-action,.secondary-action{{
                text-decoration:none;
                color:white;
                border-radius:15px;
                padding:12px 16px;
                font-weight:900;
                display:inline-flex;
                align-items:center;
                justify-content:center;
            }}
            .primary-action{{background:#2563eb;}}
            .secondary-action{{background:#334155;}}
            .empty-card{{
                background:#1e293b;
                border:1px solid rgba(148,163,184,0.12);
                padding:28px;
                border-radius:26px;
                text-align:center;
                color:#cbd5e1;
            }}
            @media(max-width:760px){{
                .page{{padding:18px;}}
                .hero{{padding:24px;border-radius:26px;}}
                .hero h1{{font-size:32px;}}
                .person-top{{align-items:flex-start;}}
                .score-box{{min-width:112px;padding:12px;}}
                .score-value{{font-size:24px;}}
            }}
            @media(max-width:560px){{
                .person-top{{flex-direction:column;}}
                .score-box{{width:100%;box-sizing:border-box;}}
                .primary-action,.secondary-action{{width:100%;box-sizing:border-box;}}
                .action-card{{flex-direction:column;}}
                .action-open{{align-self:flex-start;}}
            }}
        </style>
    </head>

    <body>
        <div class="page">
            <a class="back" href="/dashboard/{current_user.email}">← Назад</a>

            <section class="hero">
                <div class="hero-top">
                    <div>
                        <h1>🧠 AI Life Radar</h1>
                        <p>Персональные рекомендации людей, возможностей и действий на основе целей, интересов, навыков, доверия и контекста профиля.</p>
                    </div>
                    <div class="ai-status"><span class="status-dot"></span>{safe_text(ai_status_text)}</div>
                </div>
            </section>

            <section class="section">
                <h2>🎯 Что AI советует сделать сейчас</h2>
                <p>Это быстрые действия, которые усилят профиль и помогут системе находить более точных людей.</p>
                <div class="actions-grid">{action_cards_html}</div>
            </section>

            <section class="section">
                <h2>Люди, которых стоит посмотреть сегодня</h2>
                <p>AI выбрал людей, которые могут быть полезны для бизнеса, развития, дружбы, команды или будущих проектов. Сам пользователь, дубли, заблокированные профили и скрытые по Privacy & AI настройки не показываются.</p>
            </section>

            {people_html}
        </div>
    </body>
    </html>
    """

if __name__ == "__main__":

    app.run(debug=True, port=5001)