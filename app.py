from flask import Flask, send_from_directory, request, redirect, render_template, session, abort, jsonify, has_request_context
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.serving import WSGIRequestHandler
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from twilio.rest import Client
import os
import json
import secrets
import hashlib
import bleach
import smtplib
import urllib.parse
import urllib.request
import urllib.error
import ssl
import gzip
import hmac
import re
from email.message import EmailMessage
from functools import wraps
from backend.social import follow_user, unfollow_user, is_following, send_friend_request, accept_friend_request, decline_friend_request, remove_friend, are_friends, has_friend_request, count_friends, count_followers, count_following, get_friends, get_followers, get_following, get_friend_requests, load_social, save_social
from datetime import datetime, timedelta, timezone
from backend.notifications import add_notification, get_notifications, load_notifications, mark_notifications_read, save_notifications
from backend.messages import load_messages as repository_load_messages, save_messages as repository_save_messages
from backend.security_store import append_security_event, load_security_events as repository_load_security_events, load_login_attempts as repository_load_login_attempts, save_login_attempts as repository_save_login_attempts
from backend.social_safety_store import load_blocks as repository_load_blocks, load_hidden_stories as repository_load_hidden_stories, load_reports as repository_load_reports, load_restrictions as repository_load_restrictions, save_blocks as repository_save_blocks, save_hidden_stories as repository_save_hidden_stories, save_reports as repository_save_reports, save_restrictions as repository_save_restrictions
from backend.storage import save_users_to_json, load_users_from_json
from backend.stories_store import load_stories as repository_load_stories, save_stories as repository_save_stories
from backend.user_ai_settings_store import load_user_ai_settings as repository_load_user_ai_settings, save_user_ai_settings as repository_save_user_ai_settings
from backend.verification_store import load_verification_codes as repository_load_verification_codes, save_verification_codes as repository_save_verification_codes
from backend.language import get_translations
from backend.i18n import LANGUAGE_CATALOG, SUPPORTED_LANGUAGES, UI_LANGUAGES, detect_language as detect_ui_language, translation_bundle
from backend.models import User
from backend.trust import calculate_trust_score
from backend.recommendations import find_best_matches
from backend.explanations import explain_match
from backend.match_level import get_match_level
from database.users_data import users
from backend.proof import load_proofs, save_proofs
from backend.privacy import get_user_privacy, update_user_privacy
from backend.realtime_status import load_presence_status as repository_load_presence_status, load_typing_status as repository_load_typing_status, save_presence_status as repository_save_presence_status, save_typing_status as repository_save_typing_status
from backend.feed import load_feed, save_feed
from backend.serializers import compact_user_payload, user_payload, post_payload, message_payload
from backend.services import feed_service as feed_service_module
from backend.services import message_service as message_service_module
from backend.services import moderation_service
from backend.services import social_service
from backend.services import profile_service, privacy_service
from backend.services.security_activity_service import security_event_display
from backend.services import stories_privacy_service
from backend.services import feed_privacy_service
from backend.services import device_security_service
from backend.services import account_data_service
from backend.services import notification_privacy_service
from backend.services import profile_access_service
from backend.services import settings_form_service
from backend.services import feed_ranking_service
from backend.services import feed_translation_service
from backend.services import message_translation_service
from backend.services import call_caption_service
from backend.services import call_quality_service
from backend.services import call_signal_security_service
from backend.services import device_push_service
from backend.services import speech_transcription_service
from backend.services import realtime_speech_service
from backend.services import mobile_speech_contract_service
from backend.services import refresh_token_service
from backend.services.turn_credential_service import TurnCredentialService
from backend.repositories import get_refresh_session_repository
from backend.repositories.rate_limit_repository import get_rate_limit_repository
from backend.repositories.call_signal_repository import call_cancel_push_event
from backend.repositories.device_push_repository import get_device_push_repository
from backend.api.i18n import create_i18n_api
from backend.api.system import system_api
from backend.observability import finish_request_trace, start_request_trace
from backend.services.knowledge_retrieval_service import retrieve_verified_context
from backend.proof_privacy_routes import create_proof_privacy_routes
from backend.account_page_routes import create_account_page_routes
from backend.dashboard_routes import create_dashboard_routes
from backend.messaging_routes import create_messaging_routes
from backend.chat_call_routes import chat_call_routes, configure_chat_call_routes
from backend.api.errors import handle_http_exception, handle_unexpected_error
from backend.api.auth import create_auth_api
from backend.api.call_captions import create_call_captions_api
from backend.api.call_signals import create_call_signals_api
from backend.api.conferences import create_conferences_api
from backend.api.mobile import create_mobile_api
from backend.api.profile import create_profile_api
from backend.api.feed import create_feed_api
from backend.api.messages import create_messages_api
from backend.api.social import create_social_api
from backend.api.notifications import create_notifications_api
from backend.api.device_push import create_device_push_api
from backend.api.matches import create_matches_api
from backend.api.stories import create_stories_api
from backend.api.admin import create_admin_api
from backend.settings_security_routes import create_settings_security_blueprint
from backend.social_routes import create_social_routes
from backend.notification_routes import create_notification_routes
from backend.discovery_routes import create_discovery_routes
from backend.media_routes import create_media_routes
from backend.feed_routes import create_feed_routes
from backend.feed_interaction_routes import create_feed_interaction_routes
from backend.story_routes import create_story_routes
from backend.profile_routes import create_profile_routes
from backend.profile_safety_routes import create_profile_safety_routes
from backend.admin_routes import create_admin_routes
from backend.profile_misc_routes import create_profile_misc_routes
from backend.realtime_routes import create_realtime_routes
from backend.news_routes import create_news_routes
from backend.ai_core_routes import create_ai_core_routes
from backend.auth_page_routes import create_auth_page_routes
from backend.auth_security_routes import create_auth_security_routes
from backend.config import is_admin_email, is_production_environment, is_truthy, load_environment, read_secret
from backend.csrf import render_csrf_input
from backend.auth_tokens import DEFAULT_ACCESS_TOKEN_SECONDS, create_access_token as create_signed_access_token, verify_access_token, verify_refresh_token
from backend.ai_provider import AIProviderError, get_ai_provider, provider_status
 

def load_local_env_file(filename=".env"):
    try:
        return load_environment(os.environ, filename)
    except Exception as error:
        print(f"Could not load .env file: {error}")
        return os.environ


load_local_env_file()
def get_app_secret_key():
    env_secret = read_secret(os.environ, "FLASK_SECRET_KEY", "FLASK_SECRET_KEY_FILE")
    if env_secret:
        if is_production_environment() and len(env_secret) < 32:
            raise RuntimeError("FLASK_SECRET_KEY must contain at least 32 characters in production")
        return env_secret

    if is_production_environment():
        raise RuntimeError("FLASK_SECRET_KEY or FLASK_SECRET_KEY_FILE is required in production")

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
    except OSError:
        return "dev-only-change-before-production-ai-match-life-secret"

app = Flask(__name__, template_folder="frontend")
if is_truthy(os.environ.get("TRUST_PROXY")):
    # Enable only behind a trusted reverse proxy which overwrites these headers.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
app.secret_key = get_app_secret_key()
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Strict"
app.config["SESSION_COOKIE_SECURE"] = is_production_environment()
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=30)
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024
app.register_error_handler(HTTPException, handle_http_exception)
app.register_error_handler(Exception, handle_unexpected_error)
app.register_blueprint(system_api)
app.register_blueprint(create_i18n_api({
    "get_current_user": lambda: get_api_current_user(),
    "load_user_settings": lambda email: normalize_user_ai_settings(email),
    "save_user_settings": lambda email, settings: save_user_raw_settings(email, settings),
}))
 
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "").strip()
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "").strip()
TWILIO_VERIFY_SERVICE_SID = os.environ.get("TWILIO_VERIFY_SERVICE_SID", "").strip()
twilio_client = None

if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN:
    twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
turn_credential_service = TurnCredentialService(twilio_client)
call_signal_poll_limiter = call_signal_security_service.PollRateLimiter(
    repository=get_rate_limit_repository(),
)
call_speech_limiter = call_signal_security_service.PollRateLimiter(
    limit=6, window_seconds=60, repository=get_rate_limit_repository(),
)
ai_assistant_limiter = call_signal_security_service.PollRateLimiter(
    limit=12, window_seconds=60, repository=get_rate_limit_repository(),
)
from backend.ai_engine import analyze_user_profile, explain_user_match, generate_feed_idea, analyze_proof_profile, generate_life_radar
from backend.services import ai_copilot_service
from backend.ai_memory_store import load_ai_core_memory as repository_load_ai_core_memory, load_ai_feed_learning as repository_load_ai_feed_learning, save_ai_core_memory as repository_save_ai_core_memory, save_ai_feed_learning as repository_save_ai_feed_learning
from backend.call_signals_store import acknowledge_call_signals as repository_acknowledge_call_signals, append_call_caption as repository_append_call_caption, append_call_quality_sample as repository_append_call_quality_sample, append_call_signal as repository_append_call_signal, delete_call_rooms_for_participant as repository_delete_call_rooms_for_participant, expire_call_signal_room as repository_expire_call_signal_room, expire_due_call_rooms as repository_expire_due_call_rooms, get_call_signal_room as repository_get_call_signal_room, load_call_signals as repository_load_call_signals, prune_expired_call_rooms as repository_prune_expired_call_rooms, purge_call_caption_data as repository_purge_call_caption_data, reserve_call_transcription as repository_reserve_call_transcription, save_call_signals as repository_save_call_signals, set_call_caption_translation as repository_set_call_caption_translation
from backend.news_store import load_news as repository_load_news, save_news as repository_save_news
from backend.media_access_cache import MediaAccessCache
from backend.media_validation import UPLOAD_SIZE_LIMITS, allowed_mime_type
from backend.services.media_access_service import can_access_media_file as evaluate_media_access
UPLOAD_FOLDER = os.environ.get("MEDIA_UPLOAD_FOLDER", "uploads").strip() or "uploads"
LEGACY_UPLOAD_FOLDER = "static/uploads"
try:
    media_access_cache_ttl = float(os.environ.get("MEDIA_ACCESS_CACHE_TTL_SECONDS", "2"))
except (TypeError, ValueError):
    media_access_cache_ttl = 2.0
try:
    media_access_cache_max_entries = int(os.environ.get("MEDIA_ACCESS_CACHE_MAX_ENTRIES", "4096"))
except (TypeError, ValueError):
    media_access_cache_max_entries = 4096
media_access_cache = MediaAccessCache(media_access_cache_ttl, media_access_cache_max_entries)
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp", "mp4", "webm", "mov", "mp3", "m4a", "wav", "ogg"}

MAX_LOGIN_ATTEMPTS = 5
LOGIN_ATTEMPT_WINDOW_MINUTES = 10
LOGIN_LOCK_MINUTES = 15
LOGIN_2FA_ENABLED = os.environ.get("LOGIN_2FA_ENABLED", "false").strip().lower() == "true"

# --- Verification code settings ---
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


def find_user_by_identifier(identifier):
    value = str(identifier or "").strip()
    if not value:
        return None
    normalized_value = normalize_email(value)
    for user in users:
        if str(getattr(user, "id", "")).strip() == value:
            return user
        if normalize_email(getattr(user, "email", "")) == normalized_value:
            return user
    return None


@app.context_processor
def inject_application_shell_context():
    session_user = find_user_by_email(session.get("user_email", ""))
    unread_notifications = 0
    if session_user:
        unread_notifications = sum(
            1 for item in get_notifications(session_user.email)
            if isinstance(item, dict) and not item.get("read", False)
        )
    return {
        "shell_profile_id": getattr(session_user, "id", "") if session_user else "",
        "shell_is_admin": is_admin_email(getattr(session_user, "email", "")) if session_user else False,
        "shell_unread_notifications": unread_notifications,
    }


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


def user_requires_login_2fa(user):
    if LOGIN_2FA_ENABLED:
        # A device that the user explicitly trusted has already completed the
        # second factor. Keep updating its activity instead of challenging on
        # every login; unknown devices still require verification.
        return not is_current_device_trusted(user)

    if user is None:
        return False

    settings = normalize_user_ai_settings(getattr(user, "email", ""))
    return settings.get("two_factor_required") is True


def user_requires_sensitive_action_2fa(user):
    if user is None:
        return False

    settings = normalize_user_ai_settings(getattr(user, "email", ""))
    return settings.get("two_factor_required") is True


def send_sensitive_action_code(user, purpose):
    if user is None:
        return False

    contact_type, contact_value = get_user_2fa_contact(user)
    code = create_verification_code(purpose, contact_type, contact_value)
    if not code:
        return False

    sent = send_verification_code(contact_type, contact_value, code)
    log_security_event("sensitive_action_code_sent", user.email, f"purpose={purpose};type={contact_type}")
    return sent


def verify_sensitive_action_code(user, purpose, code):
    if not user_requires_sensitive_action_2fa(user):
        return True

    contact_type, contact_value = get_user_2fa_contact(user)
    return verify_contact_code(purpose, contact_type, contact_value, code)


def is_password_hashed(password_value):
    if not password_value:
        return False
    return str(password_value).startswith("scrypt:") or str(password_value).startswith("pbkdf2:")


def set_user_password(user, raw_password):
    user.password = generate_password_hash(raw_password, method="scrypt:32768:8:1", salt_length=16)


def verify_user_password(user, raw_password):
    if user is None:
        return False

    stored_password = getattr(user, "password", "")

    if is_password_hashed(stored_password):
        valid = check_password_hash(stored_password, raw_password)
        if valid and not str(stored_password).startswith("scrypt:"):
            set_user_password(user, raw_password)
            save_users_to_json(users)
        return valid

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

        logged_user = find_user_by_email(logged_email)
        if logged_user is None:
            session.clear()
            return redirect("/")

        if not is_session_version_current(logged_user):
            log_security_event("stale_session_rejected", logged_user.email, "Session version is no longer current")
            session.clear()
            return redirect("/")

        route_user = find_user_by_identifier(email) if email else None
        route_email = route_user.email if route_user is not None else email
        if route_email and normalize_email(logged_email) != normalize_email(route_email):
            if request.path.startswith("/settings/"):
                abort(403)

            return (
                simple_page(
                    "🔒 Доступ закрыт",
                    "Вы не можете открыть страницу другого пользователя без входа в его аккаунт.",
                    logged_email,
                ),
                403,
            )

        return route_function(*args, **kwargs)

    return wrapper


def profile_view_required(route_function):
    @wraps(route_function)
    def wrapper(*args, **kwargs):
        logged_email = session.get("user_email")

        if not logged_email:
            return redirect("/")

        viewer_identifier = request.args.get("viewer") or logged_email
        viewer = find_user_by_identifier(viewer_identifier)

        if viewer is None or normalize_email(logged_email) != normalize_email(viewer.email):
            return simple_page(
                "🔒 Доступ закрыт",
                "Вы не можете открыть профиль от имени другого пользователя.",
                logged_email
            )

        return route_function(*args, **kwargs)

    return wrapper


def load_login_attempts():
    return repository_load_login_attempts()


def save_login_attempts(data):
    repository_save_login_attempts(data)


def load_security_events():
    return repository_load_security_events()


def user_owns_settings_route(route_identifier):
    route_user = find_user_by_identifier(route_identifier)
    return route_user is not None and normalize_email(session.get("user_email", "")) == normalize_email(route_user.email)


def user_security_events(email, limit=25):
    email = normalize_email(email)
    events = load_security_events()
    if not isinstance(events, list):
        return []

    matched_events = []
    for event in reversed(events):
        if not isinstance(event, dict):
            continue
        if normalize_email(event.get("email", "")) != email:
            continue
        matched_events.append(event)
        if len(matched_events) >= limit:
            break

    return matched_events


def users_from_email_list(email_list):
    result = []
    for email in email_list if isinstance(email_list, list) else []:
        user = find_user_by_email(email)
        if user is not None:
            result.append(user)
    return result

def log_security_event(event_type, email="", details=""):
    try:
        ip = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown")
        ip = ip.split(",")[0].strip()

        append_security_event({
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "event": clean_text(event_type),
            "email": clean_text(email),
            "ip": clean_text(ip),
            "details": clean_text(details)
        })
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
    return render_csrf_input(get_csrf_token())



# --- Multilanguage helpers ---
# Interface and content language catalogs come from backend.i18n as the single source of truth.
CONTENT_LANGUAGES = dict(LANGUAGE_CATALOG)
CONTENT_LANGUAGES["unknown"] = "Unknown"

DEFAULT_LANGUAGE = "ru"

_LEGACY_UI_TRANSLATIONS = {
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
    "es": {
        "back": "← Atrás",
        "dashboard": "Inicio",
        "profile": "Perfil",
        "settings": "Ajustes",
        "messages": "Mensajes",
        "notifications": "Notificaciones",
        "ai_discover": "AI Discover",
        "ai_discover_subtitle": "Un feed inteligente de videos, ideas, proyectos, lugares y personas. AI muestra contenido según tus objetivos, intereses, idiomas, ubicación y actividad.",
        "create_post": "Crear publicación",
        "publish": "Publicar",
        "post_placeholder": "¿Qué quieres mostrar al mundo? Idea, video, lugar, negocio, proyecto...",
        "city_country": "Ciudad / país",
        "why_ai_showed": "🧠 Por qué AI mostró esto:",
        "write": "Escribir",
        "unavailable": "No disponible",
        "open": "Abrir",
        "empty_feed_title": "Aún no hay publicaciones",
        "empty_feed_text": "Crea la primera publicación, idea, video o proyecto. AI Discover empezará a construir un feed inteligente alrededor de los intereses."
    },
    "fr": {
        "back": "← Retour",
        "dashboard": "Accueil",
        "profile": "Profil",
        "settings": "Paramètres",
        "messages": "Messages",
        "notifications": "Notifications",
        "ai_discover": "AI Discover",
        "ai_discover_subtitle": "Un fil intelligent de vidéos, idées, projets, lieux et personnes. AI affiche du contenu selon vos objectifs, intérêts, langues, localisation et activité.",
        "create_post": "Créer une publication",
        "publish": "Publier",
        "post_placeholder": "Que voulez-vous montrer au monde ? Idée, vidéo, lieu, business, projet...",
        "city_country": "Ville / pays",
        "why_ai_showed": "🧠 Pourquoi AI a montré ceci :",
        "write": "Écrire",
        "unavailable": "Indisponible",
        "open": "Ouvrir",
        "empty_feed_title": "Aucune publication pour le moment",
        "empty_feed_text": "Créez la première publication, idée, vidéo ou projet. AI Discover commencera à construire un fil intelligent autour des intérêts."
    },
    "pt": {
        "back": "← Voltar",
        "dashboard": "Início",
        "profile": "Perfil",
        "settings": "Definições",
        "messages": "Mensagens",
        "notifications": "Notificações",
        "ai_discover": "AI Discover",
        "ai_discover_subtitle": "Um feed inteligente de vídeos, ideias, projetos, lugares e pessoas. AI mostra conteúdo com base nos seus objetivos, interesses, idiomas, localização e atividade.",
        "create_post": "Criar publicação",
        "publish": "Publicar",
        "post_placeholder": "O que quer mostrar ao mundo? Ideia, vídeo, lugar, negócio, projeto...",
        "city_country": "Cidade / país",
        "why_ai_showed": "🧠 Porque AI mostrou isto:",
        "write": "Escrever",
        "unavailable": "Indisponível",
        "open": "Abrir",
        "empty_feed_title": "Ainda não há publicações",
        "empty_feed_text": "Crie a primeira publicação, ideia, vídeo ou projeto. AI Discover começará a criar um feed inteligente em torno dos interesses."
    },
    "it": {
        "back": "← Indietro",
        "dashboard": "Home",
        "profile": "Profilo",
        "settings": "Impostazioni",
        "messages": "Messaggi",
        "notifications": "Notifiche",
        "ai_discover": "AI Discover",
        "ai_discover_subtitle": "Un feed intelligente di video, idee, progetti, luoghi e persone. AI mostra contenuti in base a obiettivi, interessi, lingue, posizione e attività.",
        "create_post": "Crea post",
        "publish": "Pubblica",
        "post_placeholder": "Cosa vuoi mostrare al mondo? Idea, video, luogo, business, progetto...",
        "city_country": "Città / paese",
        "why_ai_showed": "🧠 Perché AI ha mostrato questo:",
        "write": "Scrivi",
        "unavailable": "Non disponibile",
        "open": "Apri",
        "empty_feed_title": "Ancora nessun post",
        "empty_feed_text": "Crea il primo post, idea, video o progetto. AI Discover inizierà a costruire un feed intelligente intorno agli interessi."
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
    "hi": {
        "back": "← वापस",
        "dashboard": "होम",
        "profile": "प्रोफ़ाइल",
        "settings": "सेटिंग्स",
        "messages": "संदेश",
        "notifications": "सूचनाएँ",
        "ai_discover": "AI Discover",
        "ai_discover_subtitle": "वीडियो, विचार, प्रोजेक्ट, स्थान और लोगों की स्मार्ट फ़ीड। AI आपके लक्ष्यों, रुचियों, भाषाओं, स्थान और गतिविधि के आधार पर सामग्री दिखाता है।",
        "create_post": "पोस्ट बनाएँ",
        "publish": "प्रकाशित करें",
        "post_placeholder": "आप दुनिया को क्या दिखाना चाहते हैं? विचार, वीडियो, स्थान, बिज़नेस, प्रोजेक्ट...",
        "city_country": "शहर / देश",
        "why_ai_showed": "🧠 AI ने यह क्यों दिखाया:",
        "write": "लिखें",
        "unavailable": "उपलब्ध नहीं",
        "open": "खोलें",
        "empty_feed_title": "अभी कोई पोस्ट नहीं",
        "empty_feed_text": "पहली पोस्ट, विचार, वीडियो या प्रोजेक्ट बनाएँ। AI Discover रुचियों के आधार पर स्मार्ट फ़ीड बनाना शुरू करेगा।"
    },
    "id": {
        "back": "← Kembali",
        "dashboard": "Beranda",
        "profile": "Profil",
        "settings": "Pengaturan",
        "messages": "Pesan",
        "notifications": "Notifikasi",
        "ai_discover": "AI Discover",
        "ai_discover_subtitle": "Feed cerdas berisi video, ide, proyek, tempat, dan orang. AI menampilkan konten berdasarkan tujuan, minat, bahasa, lokasi, dan aktivitas Anda.",
        "create_post": "Buat postingan",
        "publish": "Publikasikan",
        "post_placeholder": "Apa yang ingin Anda tampilkan ke dunia? Ide, video, tempat, bisnis, proyek...",
        "city_country": "Kota / negara",
        "why_ai_showed": "🧠 Mengapa AI menampilkan ini:",
        "write": "Tulis",
        "unavailable": "Tidak tersedia",
        "open": "Buka",
        "empty_feed_title": "Belum ada postingan",
        "empty_feed_text": "Buat postingan, ide, video, atau proyek pertama. AI Discover akan mulai membangun feed cerdas berdasarkan minat."
    },
    "zh": {
        "back": "← 返回",
        "dashboard": "首页",
        "profile": "个人资料",
        "settings": "设置",
        "messages": "消息",
        "notifications": "通知",
        "ai_discover": "AI Discover",
        "ai_discover_subtitle": "由视频、想法、项目、地点和人物组成的智能动态。AI 会根据你的目标、兴趣、语言、位置和活动显示内容。",
        "create_post": "创建动态",
        "publish": "发布",
        "post_placeholder": "你想向世界展示什么？想法、视频、地点、业务、项目...",
        "city_country": "城市 / 国家",
        "why_ai_showed": "🧠 AI 为什么显示这个：",
        "write": "写消息",
        "unavailable": "不可用",
        "open": "打开",
        "empty_feed_title": "还没有动态",
        "empty_feed_text": "创建第一条动态、想法、视频或项目。AI Discover 将开始围绕兴趣构建智能动态。"
    },
    "ja": {
        "back": "← 戻る",
        "dashboard": "ホーム",
        "profile": "プロフィール",
        "settings": "設定",
        "messages": "メッセージ",
        "notifications": "通知",
        "ai_discover": "AI Discover",
        "ai_discover_subtitle": "動画、アイデア、プロジェクト、場所、人々のスマートフィード。AI は目標、興味、言語、場所、活動に基づいてコンテンツを表示します。",
        "create_post": "投稿を作成",
        "publish": "公開",
        "post_placeholder": "世界に何を見せたいですか？アイデア、動画、場所、ビジネス、プロジェクト...",
        "city_country": "都市 / 国",
        "why_ai_showed": "🧠 AI がこれを表示した理由:",
        "write": "書く",
        "unavailable": "利用不可",
        "open": "開く",
        "empty_feed_title": "まだ投稿がありません",
        "empty_feed_text": "最初の投稿、アイデア、動画、プロジェクトを作成してください。AI Discover が興味に基づいてスマートフィードを作り始めます。"
    },
    "ko": {
        "back": "← 뒤로",
        "dashboard": "홈",
        "profile": "프로필",
        "settings": "설정",
        "messages": "메시지",
        "notifications": "알림",
        "ai_discover": "AI Discover",
        "ai_discover_subtitle": "동영상, 아이디어, 프로젝트, 장소, 사람을 위한 스마트 피드입니다. AI는 목표, 관심사, 언어, 위치, 활동을 바탕으로 콘텐츠를 보여줍니다.",
        "create_post": "게시물 만들기",
        "publish": "게시",
        "post_placeholder": "세상에 무엇을 보여주고 싶나요? 아이디어, 동영상, 장소, 비즈니스, 프로젝트...",
        "city_country": "도시 / 국가",
        "why_ai_showed": "🧠 AI가 이것을 보여준 이유:",
        "write": "쓰기",
        "unavailable": "사용할 수 없음",
        "open": "열기",
        "empty_feed_title": "아직 게시물이 없습니다",
        "empty_feed_text": "첫 게시물, 아이디어, 동영상 또는 프로젝트를 만들어 보세요. AI Discover가 관심사를 중심으로 스마트 피드를 만들기 시작합니다."
    },
    "pl": {
        "back": "← Wstecz",
        "dashboard": "Strona główna",
        "profile": "Profil",
        "settings": "Ustawienia",
        "messages": "Wiadomości",
        "notifications": "Powiadomienia",
        "ai_discover": "AI Discover",
        "ai_discover_subtitle": "Inteligentny feed filmów, pomysłów, projektów, miejsc i ludzi. AI pokazuje treści na podstawie celów, zainteresowań, języków, lokalizacji i aktywności.",
        "create_post": "Utwórz post",
        "publish": "Opublikuj",
        "post_placeholder": "Co chcesz pokazać światu? Pomysł, film, miejsce, biznes, projekt...",
        "city_country": "Miasto / kraj",
        "why_ai_showed": "🧠 Dlaczego AI to pokazał:",
        "write": "Napisz",
        "unavailable": "Niedostępne",
        "open": "Otwórz",
        "empty_feed_title": "Nie ma jeszcze postów",
        "empty_feed_text": "Utwórz pierwszy post, pomysł, film lub projekt. AI Discover zacznie budować inteligentny feed wokół zainteresowań."
    },
    "nl": {
        "back": "← Terug",
        "dashboard": "Start",
        "profile": "Profiel",
        "settings": "Instellingen",
        "messages": "Berichten",
        "notifications": "Meldingen",
        "ai_discover": "AI Discover",
        "ai_discover_subtitle": "Een slimme feed met video's, ideeën, projecten, plekken en mensen. AI toont content op basis van doelen, interesses, talen, locatie en activiteit.",
        "create_post": "Post maken",
        "publish": "Publiceren",
        "post_placeholder": "Wat wil je de wereld laten zien? Idee, video, plek, business, project...",
        "city_country": "Stad / land",
        "why_ai_showed": "🧠 Waarom AI dit toonde:",
        "write": "Schrijven",
        "unavailable": "Niet beschikbaar",
        "open": "Openen",
        "empty_feed_title": "Nog geen posts",
        "empty_feed_text": "Maak de eerste post, idee, video of project. AI Discover begint een slimme feed rond interesses te bouwen."
    },
    "uk": {
        "back": "← Назад",
        "dashboard": "Головна",
        "profile": "Профіль",
        "settings": "Налаштування",
        "messages": "Повідомлення",
        "notifications": "Сповіщення",
        "ai_discover": "AI Discover",
        "ai_discover_subtitle": "Розумна стрічка відео, ідей, проєктів, місць і людей. AI показує контент за вашими цілями, інтересами, мовами, локацією та активністю.",
        "create_post": "Створити допис",
        "publish": "Опублікувати",
        "post_placeholder": "Що хочете показати світу? Ідея, відео, місце, бізнес, проєкт...",
        "city_country": "Місто / країна",
        "why_ai_showed": "🧠 Чому AI це показав:",
        "write": "Написати",
        "unavailable": "Недоступно",
        "open": "Відкрити",
        "empty_feed_title": "Поки немає дописів",
        "empty_feed_text": "Створіть перший допис, ідею, відео або проєкт. AI Discover почне будувати розумну стрічку навколо інтересів."
    },
    "ro": {
        "back": "← Înapoi",
        "dashboard": "Acasă",
        "profile": "Profil",
        "settings": "Setări",
        "messages": "Mesaje",
        "notifications": "Notificări",
        "ai_discover": "AI Discover",
        "ai_discover_subtitle": "Un feed inteligent de videoclipuri, idei, proiecte, locuri și oameni. AI afișează conținut pe baza obiectivelor, intereselor, limbilor, locației și activității.",
        "create_post": "Creează postare",
        "publish": "Publică",
        "post_placeholder": "Ce vrei să arăți lumii? Idee, video, loc, business, proiect...",
        "city_country": "Oraș / țară",
        "why_ai_showed": "🧠 De ce AI a afișat asta:",
        "write": "Scrie",
        "unavailable": "Indisponibil",
        "open": "Deschide",
        "empty_feed_title": "Nu există încă postări",
        "empty_feed_text": "Creează prima postare, idee, video sau proiect. AI Discover va începe să construiască un feed inteligent în jurul intereselor."
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
    },
    "ar": {
        "back": "← رجوع",
        "dashboard": "الرئيسية",
        "profile": "الملف الشخصي",
        "settings": "الإعدادات",
        "messages": "الرسائل",
        "notifications": "الإشعارات",
        "ai_discover": "AI Discover",
        "ai_discover_subtitle": "خلاصة ذكية للفيديوهات والأفكار والمشاريع والأماكن والأشخاص. يعرض AI المحتوى حسب أهدافك واهتماماتك ولغاتك وموقعك ونشاطك.",
        "create_post": "إنشاء منشور",
        "publish": "نشر",
        "post_placeholder": "ماذا تريد أن تعرض للعالم؟ فكرة، فيديو، مكان، عمل، مشروع...",
        "city_country": "المدينة / الدولة",
        "why_ai_showed": "🧠 لماذا عرض AI هذا:",
        "write": "اكتب",
        "unavailable": "غير متاح",
        "open": "فتح",
        "empty_feed_title": "لا توجد منشورات بعد",
        "empty_feed_text": "أنشئ أول منشور أو فكرة أو فيديو أو مشروع. سيبدأ AI Discover في بناء خلاصة ذكية حول الاهتمامات."
    }
}

# Runtime interface copy has a single canonical source in backend.i18n.
UI_TRANSLATIONS = {
    language_code: translation_bundle(language_code)
    for language_code in SUPPORTED_LANGUAGES
}


def normalize_language_code(language_value):
    language = detect_ui_language(language_value, default=DEFAULT_LANGUAGE)
    return language if language in UI_LANGUAGES else DEFAULT_LANGUAGE


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
    if user is not None:
        settings_language_value = normalize_user_ai_settings(
            getattr(user, "email", "")
        ).get("interface_language", "")
        if settings_language_value:
            settings_language = normalize_language_code(settings_language_value)
            if settings_language in UI_LANGUAGES:
                return settings_language
        saved_language = normalize_language_code(getattr(user, "language", ""))
        if saved_language in UI_LANGUAGES and getattr(user, "language", ""):
            return saved_language

    session_language = normalize_language_code(session.get("language", ""))
    if session_language in UI_LANGUAGES and session.get("language"):
        return session_language

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


def safe_redirect_target(candidate, fallback="/"):
    candidate = str(candidate or "").strip()
    if not candidate:
        return fallback
    parsed = urllib.parse.urlsplit(candidate)
    if parsed.scheme or parsed.netloc:
        if parsed.scheme not in {"http", "https"} or parsed.netloc.lower() != request.host.lower():
            return fallback
        path = urllib.parse.urlunsplit(("", "", parsed.path or "/", parsed.query, ""))
        return path if path.startswith("/") and not path.startswith("//") else fallback
    return candidate if candidate.startswith("/") and not candidate.startswith("//") else fallback

class CsrfValidationError(Exception):
    pass


def validate_csrf_token():
    session_token = session.get("csrf_token")
    form_token = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")

    if (
        not session_token
        or not form_token
        or not secrets.compare_digest(str(session_token), str(form_token))
    ):
        log_security_event("csrf_failed", session.get("user_email", ""), request.path)
        raise CsrfValidationError("Сессия устарела. Пожалуйста, повторите действие")


@app.errorhandler(CsrfValidationError)
def handle_csrf_error(error):
    user_email = session.get("user_email", "")
    ui = translation_bundle(get_current_language(find_user_by_email(user_email)))
    return render_template(
        "error_page.html",
        language_code=ui.get("language_code", "ru"),
        text_direction=ui.get("text_direction", "ltr"),
        title=ui["session_expired_title"],
        heading=f"⏳ {ui['session_expired_title']}",
        message=ui["session_expired_message"],
        action_url=f"/dashboard/{urllib.parse.quote(user_email, safe='@')}" if user_email else "/",
        action_label=ui["return_to_feed"],
    ), 403


@app.before_request
def begin_request_observability():
    start_request_trace()


@app.before_request
def restrict_options_requests():
    if request.method != "OPTIONS":
        return None

    origin = request.headers.get("Origin", "").strip()
    if origin:
        parsed_origin = urllib.parse.urlsplit(origin)
        if parsed_origin.scheme not in {"http", "https"} or parsed_origin.netloc.lower() != request.host.lower():
            abort(403)

    # This application intentionally has no cross-origin browser API. Handling
    # OPTIONS here avoids Flask's route-specific Allow header disclosure.
    return app.response_class(status=204)


@app.before_request
def allow_local_home_page_during_development():
    host = str(request.host or "").lower().strip()
    host_name = host.split(":")[0]
    local_hosts = {"localhost", "127.0.0.1", "::1", "[::1]"}

    if request.method == "GET" and request.path == "/" and host_name in local_hosts:
        session_email = normalize_email(session.get("user_email", ""))
        session_user = find_user_by_email(session_email) if session_email else None
        if session_user is not None:
            return redirect(
                f"/dashboard/{urllib.parse.quote(session_user.email, safe='@')}",
                code=302,
            )
        ui = translation_bundle(get_current_language())
        return render_template("index.html", csrf_token_input=csrf_input(), ui=ui)

    return None


@app.errorhandler(403)
def forbidden_page(error):
    ui = translation_bundle(get_current_language())
    return render_template(
        "error_page.html",
        language_code=ui.get("language_code", "ru"),
        text_direction=ui.get("text_direction", "ltr"),
        title="403",
        heading="🔒 Доступ запрещён",
        message="Сработала защита. Для локального теста откройте главную страницу заново.",
        action_url="/",
        action_label="Открыть главную",
    ), 403


@app.errorhandler(404)
def not_found_page(error):
    if request.path.startswith("/api/"):
        return handle_http_exception(error)
    ui = translation_bundle(get_current_language())
    language = ui.get("language_code", "en")
    copy = {
        "ru": ("Страница не найдена", "Проверьте адрес или вернитесь на главную страницу NOVIX.", "На главную"),
        "de": ("Seite nicht gefunden", "Prüfen Sie die Adresse oder kehren Sie zur NOVIX-Startseite zurück.", "Zur Startseite"),
        "en": ("Page not found", "Check the address or return to the NOVIX home page.", "Go home"),
    }.get(language, ("Page not found", "Check the address or return to the NOVIX home page.", "Go home"))
    return render_template(
        "error_page.html",
        language_code=language,
        text_direction=ui.get("text_direction", "ltr"),
        title="404",
        heading=f"404 · {copy[0]}",
        message=copy[1],
        action_url="/",
        action_label=copy[2],
    ), 404


@app.after_request
def add_security_headers(response):
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(self), microphone=(self), geolocation=(self)"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
    response.headers["Cross-Origin-Embedder-Policy"] = "require-corp"
    response.headers["X-Permitted-Cross-Domain-Policies"] = "none"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "img-src 'self' https:; "
        "style-src 'self' 'unsafe-inline'; "
        "script-src 'self'; "
        "script-src-attr 'none'; "
        "media-src 'self' https:; "
        "connect-src 'self' https: wss:; "
        "font-src 'self' data:; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "form-action 'self'; "
        "frame-ancestors 'self';"
    )
    response.headers.pop("X-Powered-By", None)
    response.headers.pop("Server", None)
    if is_production_environment() and request.is_secure:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"

    if request.path.startswith("/static/"):
        response.headers.setdefault("Cache-Control", "public, max-age=86400")
    elif request.method == "GET" and response.mimetype == "text/html":
        response.headers.setdefault("Cache-Control", "private, no-cache")

    if (
        request.method == "GET"
        and response.status_code == 200
        and not response.direct_passthrough
        and "ETag" not in response.headers
    ):
        response.set_etag(hashlib.sha256(response.get_data()).hexdigest(), weak=True)
        response.make_conditional(request)

    compressible_types = {
        "text/html",
        "text/css",
        "text/javascript",
        "application/javascript",
        "application/json",
        "image/svg+xml",
    }
    accepts_gzip = "gzip" in request.headers.get("Accept-Encoding", "").lower()
    if (
        accepts_gzip
        and response.status_code == 200
        and response.mimetype in compressible_types
        and not response.direct_passthrough
        and "Content-Encoding" not in response.headers
    ):
        payload = response.get_data()
        if len(payload) >= 1024:
            compressed = gzip.compress(payload, compresslevel=6)
            if len(compressed) < len(payload):
                response.set_data(compressed)
                response.headers["Content-Encoding"] = "gzip"
                response.headers["Content-Length"] = str(len(compressed))
                response.vary.add("Accept-Encoding")
    return finish_request_trace(response, app.logger)
    

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def avatar_file_stems(email):
    user = find_user_by_email(email)
    uuid_stem = secure_filename(str(getattr(user, "id", "") or "")) if user else ""
    safe_email = secure_filename(email.replace("@", "_at_").replace(".", "_"))
    return [stem for stem in (uuid_stem, safe_email) if stem]


def avatar_filename(email, extension):
    stems = avatar_file_stems(email)
    if not stems:
        raise ValueError("Cannot create an avatar filename without a user identifier")
    return f"{stems[0]}.{extension}"


def get_avatar_url(email):
    for stem in avatar_file_stems(email):
        for folder in (UPLOAD_FOLDER, LEGACY_UPLOAD_FOLDER):
            for ext in ALLOWED_EXTENSIONS:
                path = os.path.join(folder, f"{stem}.{ext}")
                if os.path.exists(path):
                    return f"/media-files/{stem}.{ext}"

    return "https://via.placeholder.com/160"


def can_access_media_file(filename):
    return evaluate_media_access(filename, session.get("user_email", ""), {
        "cache": media_access_cache,
        "can_view_feed_post": can_view_feed_post,
        "can_view_user_stories": can_view_user_stories,
        "load_feed": load_feed,
        "load_messages": load_messages,
        "load_stories": load_stories,
        "normalize_email": normalize_email,
    })
    

def load_messages():
    return repository_load_messages()


def save_messages(messages):
    repository_save_messages(messages)


# --- Email / SMS verification helpers ---
def load_verification_codes():
    return repository_load_verification_codes()


def save_verification_codes(data):
    repository_save_verification_codes(data)


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


def verification_code_digest(purpose, contact_type, contact_value, code):
    message = f"{purpose}:{contact_type}:{contact_value}:{str(code or '').strip()}".encode("utf-8")
    return hmac.new(app.secret_key.encode("utf-8"), message, hashlib.sha256).hexdigest()


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
        "code_hash": verification_code_digest(purpose, contact_type, contact_value, code),
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

    expected_hash = str(item.get("code_hash", "")).strip()
    if expected_hash:
        valid_code = secrets.compare_digest(
            expected_hash,
            verification_code_digest(purpose, contact_type, contact_value, code),
        )
    else:
        # One-time compatibility path for records created before hashed storage.
        valid_code = secrets.compare_digest(str(item.get("code", "")).strip(), str(code or "").strip())

    if not valid_code:
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
    message["Subject"] = "NOVIX verification code"
    message["From"] = smtp_from
    message["To"] = email_address
    message.set_content(
        f"Ваш код подтверждения NOVIX: {code}\n\n"
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
    return repository_load_stories()


def save_stories(data):
    repository_save_stories(data)



def is_story_active(story):
    return stories_privacy_service.is_story_active(story)


# --- Block / blacklist helpers ---
def load_blocks():
    return repository_load_blocks()


def save_blocks(data):
    repository_save_blocks(data)


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


def load_reports():
    return repository_load_reports()


def save_reports(data):
    repository_save_reports(data)


def add_profile_report(reporter_email, target_email, reason, details):
    data = load_reports()
    data["reports"].append(moderation_service.create_profile_report(
        reporter_email,
        target_email,
        clean_text(reason),
        clean_text(details),
    ))
    data["reports"] = data["reports"][-1000:]
    save_reports(data)
    return True


def load_restrictions():
    return repository_load_restrictions()


def save_restrictions(data):
    repository_save_restrictions(data)


def is_restricted(restrictor_email, restricted_email):
    restrictor_email = normalize_email(restrictor_email)
    restricted_email = normalize_email(restricted_email)
    data = load_restrictions()
    return restricted_email in data.get("restrictions", {}).get(restrictor_email, [])


def restrict_user_account(restrictor_email, restricted_email):
    restrictor_email = normalize_email(restrictor_email)
    restricted_email = normalize_email(restricted_email)
    if not restrictor_email or not restricted_email or restrictor_email == restricted_email:
        return False

    data = load_restrictions()
    restrictions = data.get("restrictions", {})
    restricted_list = restrictions.get(restrictor_email, [])
    if restricted_email not in restricted_list:
        restricted_list.append(restricted_email)
    restrictions[restrictor_email] = restricted_list
    data["restrictions"] = restrictions
    save_restrictions(data)
    return True


def unrestrict_user_account(restrictor_email, restricted_email):
    restrictor_email = normalize_email(restrictor_email)
    restricted_email = normalize_email(restricted_email)
    data = load_restrictions()
    restrictions = data.get("restrictions", {})
    restricted_list = restrictions.get(restrictor_email, [])
    if restricted_email in restricted_list:
        restricted_list.remove(restricted_email)
    restrictions[restrictor_email] = restricted_list
    data["restrictions"] = restrictions
    save_restrictions(data)
    return True


def load_hidden_stories():
    return repository_load_hidden_stories()


def save_hidden_stories(data):
    repository_save_hidden_stories(data)


def has_hidden_stories_from(viewer_email, target_email):
    return stories_privacy_service.has_hidden_stories_from(
        viewer_email,
        target_email,
        load_hidden_stories(),
    )


def hide_stories_from_user(viewer_email, target_email):
    data, changed = stories_privacy_service.hide_stories_from_user(
        viewer_email,
        target_email,
        load_hidden_stories(),
    )
    if changed:
        save_hidden_stories(data)
    return changed


def show_stories_from_user(viewer_email, target_email):
    data, changed = stories_privacy_service.show_stories_from_user(
        viewer_email,
        target_email,
        load_hidden_stories(),
    )
    if changed:
        save_hidden_stories(data)
    return changed


# --- Typing status helpers ---
def load_typing_status():
    return repository_load_typing_status()


def save_typing_status(data):
    repository_save_typing_status(data)
# --- Presence / online status helpers ---
def load_presence_status():
    return repository_load_presence_status()


def save_presence_status(data):
    repository_save_presence_status(data)


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


def can_view_user_stories(viewer_email, owner_email):
    return stories_privacy_service.can_view_user_stories(
        viewer_email,
        owner_email,
        normalize_user_ai_settings(owner_email),
        load_hidden_stories(),
        is_blocked,
        are_friends,
    )


def format_visible_last_seen(viewer_email, owner_email, timestamp_value):
    return profile_access_service.visible_last_seen_text(
        viewer_email,
        owner_email,
        normalize_user_ai_settings(owner_email),
        timestamp_value,
        format_last_seen,
    )
def safe_text(value):
    if value is None or value == "":
        return "Nicht angegeben"
    return clean_text(value)


def clean_text(value):
    return bleach.clean(str(value or "").strip(), tags=[], strip=True)


def mask_contact_value(contact_type, contact_value):
    value = clean_text(contact_value)
    if contact_type == "email" and "@" in value:
        name, domain = value.split("@", 1)
        return f"{name[:2]}***@{domain}"
    if contact_type == "phone" and len(value) > 4:
        return f"***{value[-4:]}"
    return value


def safe_account_payload(user):
    return account_data_service.safe_account_payload(user)


def safe_list(values):
    if values is None or len(values) == 0:
        return "Nicht angegeben"
    return ", ".join(clean_text(item) for item in values)


def parse_short_list(value, limit=6):
    return profile_service.parse_short_list(value, limit=limit)


def user_needs_onboarding(user):
    return profile_service.user_needs_onboarding(user)


def onboarding_redirect_for(user):
    if user_needs_onboarding(user):
        return f"/onboarding/{safe_text(user.email)}"
    return f"/dashboard/{safe_text(user.email)}"


def save_onboarding_answers(user, form_data):
    if not profile_service.apply_onboarding(user, form_data):
        return False
    calculate_trust_score(user)
    save_users_to_json(users)
    return True


def load_ai_core_memory():
    return repository_load_ai_core_memory()


def save_ai_core_memory(data):
    repository_save_ai_core_memory(data)


AI_RESPONSE_VERSION = "2026-08-rag2"


def record_ai_core_memory(user_email, mode, question, answer):
    user_email = normalize_email(user_email)

    if not user_email:
        return

    try:
        data = load_ai_core_memory()
        user_items = data.get(user_email, [])
        if not isinstance(user_items, list):
            user_items = []

        model_name = get_ai_provider_status().get("model", "")
        if user_items:
            last_item = user_items[-1]
            if (
                clean_text(last_item.get("mode", "general")) == clean_text(mode)
                and clean_text(last_item.get("question", "")) == clean_text(question)
                and clean_text(last_item.get("answer", "")) == clean_text(answer)
                and clean_text(last_item.get("model", "")) == clean_text(model_name)
                and clean_text(last_item.get("response_version", "")) == AI_RESPONSE_VERSION
            ):
                return

        user_items.append({
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "mode": clean_text(mode),
            "question": clean_text(question),
            "answer": clean_text(answer),
            "model": clean_text(model_name),
            "response_version": AI_RESPONSE_VERSION,
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
                    f"Answer: {clean_text(item.get('answer', ''))[:450]}"
                ])
            )

        return "\n\n---\n\n".join(memory_lines)
    except Exception:
        return ""


def cached_ai_core_answer(user_email, mode, question):
    normalized_email = normalize_email(user_email)
    normalized_mode = clean_text(mode)
    normalized_question = " ".join(clean_text(question).split()).casefold()
    current_model = clean_text(get_ai_provider_status().get("model", ""))
    if not normalized_email or not normalized_question or not current_model:
        return ""
    try:
        items = load_ai_core_memory().get(normalized_email, [])
        for item in reversed(items[-30:] if isinstance(items, list) else []):
            if (
                clean_text(item.get("mode", "general")) == normalized_mode
                and " ".join(clean_text(item.get("question", "")).split()).casefold() == normalized_question
                and clean_text(item.get("model", "")) == current_model
                and clean_text(item.get("response_version", "")) == AI_RESPONSE_VERSION
            ):
                return clean_text(item.get("answer", ""))
    except Exception:
        return ""
    return ""


def render_ai_core_history(user_email, limit=12):
    user_email = normalize_email(user_email)

    try:
        data = load_ai_core_memory()
        user_items = data.get(user_email, [])
        if not isinstance(user_items, list) or not user_items:
            return []

        total_items = len(user_items)
        visible_items = list(enumerate(user_items[-limit:], start=max(total_items - limit, 0)))
        history_items = []
        for item_index, item in reversed(visible_items):
            mode_title = get_ai_core_mode_config(item.get("mode", "general")).get("title", "AI Core")
            question_text = clean_text(item.get("question", ""))
            if len(question_text) > 95:
                question_text = question_text[:95] + "..."
            history_items.append({
                "index": item_index,
                "mode_title": mode_title,
                "question": question_text,
                "time": clean_text(item.get("time", "")),
            })
        return history_items
    except Exception as error:
        log_security_event("ai_core_history_render_failed", user_email, str(error))
        return []


def render_selected_ai_core_history(user_email, history_index):
    user_email = normalize_email(user_email)

    try:
        history_index = int(history_index)
    except Exception:
        return None

    try:
        data = load_ai_core_memory()
        user_items = data.get(user_email, [])
        if not isinstance(user_items, list):
            return None

        if history_index < 0 or history_index >= len(user_items):
            return None

        item = user_items[history_index]
        mode_title = get_ai_core_mode_config(item.get("mode", "general")).get("title", "AI Core")

        return {
            "time": clean_text(item.get("time", "")),
            "mode_title": mode_title,
            "question": clean_text(item.get("question", "")),
            "answer": clean_text(item.get("answer", "")),
        }
    except Exception as error:
        log_security_event("ai_core_selected_history_failed", user_email, str(error))
        return None



def get_ai_provider_status():
    return provider_status(check_connection=False)


def call_ai_chat(messages, temperature=0.2, max_tokens=900, strict=False):
    status = get_ai_provider_status()

    if not status.get("enabled"):
        return "" if strict else "AI Assistant временно недоступен."

    try:
        return clean_text(
            get_ai_provider().chat(
                messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        )
    except (AIProviderError, OSError, TypeError, ValueError) as error:
        error_text = str(error)
        actor_email = session.get("user_email", "") if has_request_context() else ""
        log_security_event("ai_provider_failed", actor_email, error_text)
        return "" if strict else "Локальная AI-модель временно недоступна. Проверьте Ollama."


# Temporary compatibility aliases for third-party extensions. Application code
# uses the provider-neutral contract above.
get_openai_status = get_ai_provider_status
call_openai_chat = call_ai_chat


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
    recent_ai_core_memory = get_recent_ai_core_memory(getattr(user, "email", ""), limit=4)

    context = "\n".join([
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
    return context[:6000]


def get_ai_core_mode_config(mode):
    return ai_copilot_service.mode_config(mode, clean_text)


def _numeric_claims(value):
    return ai_copilot_service.numeric_claims(value)


def _grounded_revision(answer, verified_context):
    return ai_copilot_service.grounded_revision(answer, verified_context, call_ai_chat)


def generate_ai_copilot_answer(user, user_question, mode="general"):
    return ai_copilot_service.generate_answer(user, user_question, mode, {
        "build_user_context": build_user_ai_context,
        "cached_answer": cached_ai_core_answer,
        "call_chat": call_ai_chat,
        "clean_text": clean_text,
        "retrieve_verified_context": retrieve_verified_context,
    })


# --- News module helpers ---
def load_news():
    return repository_load_news()


def save_news(news_items):
    repository_save_news(news_items)


def calculate_dashboard_activity_count(user, posts):
    if user is None:
        return 0

    user_email = normalize_email(user.email)
    if not user_email:
        return 0

    authored_posts = 0
    likes_given = 0
    saves_given = 0
    comments_given = 0
    shares_given = 0

    for post in posts or []:
        if normalize_email(post.get("email", post.get("author_email", ""))) == user_email:
            authored_posts += 1

        if isinstance(post.get("likes", []), list):
            likes_given += sum(1 for like_email in post.get("likes", []) if normalize_email(like_email) == user_email)

        if isinstance(post.get("saves", []), list):
            saves_given += sum(1 for save_email in post.get("saves", []) if normalize_email(save_email) == user_email)

        if isinstance(post.get("comments", []), list):
            for comment in post.get("comments", []):
                if normalize_email(comment.get("author") or comment.get("email")) == user_email:
                    comments_given += 1

        if isinstance(post.get("shares", []), list):
            for share in post.get("shares", []):
                if isinstance(share, dict) and normalize_email(share.get("email") or share.get("from") or share.get("sender")) == user_email:
                    shares_given += 1

    return authored_posts + likes_given + saves_given + comments_given + shares_given


# --- User AI Privacy/Settings helpers ---

def normalize_user_ai_settings(email):
    email = normalize_email(email)
    return privacy_service.normalize_settings(repository_load_user_ai_settings(email))


def is_account_deactivated(user_or_email):
    email = getattr(user_or_email, "email", user_or_email)
    return normalize_user_ai_settings(email).get("account_deactivated") is True


def save_user_ai_settings(email, new_settings):
    email = normalize_email(email)

    if not email:
        return

    current = repository_load_user_ai_settings(email)
    current, error = privacy_service.build_update(current, new_settings)
    if error:
        return

    repository_save_user_ai_settings(email, current)


def save_user_raw_settings(email, settings):
    email = normalize_email(email)
    if email:
        repository_save_user_ai_settings(email, settings if isinstance(settings, dict) else {})


def get_user_session_version(email):
    raw_settings = repository_load_user_ai_settings(email)
    return device_security_service.session_version_from_settings(raw_settings)


def bind_session_to_user(user):
    if user is None:
        return

    session["session_version"] = get_user_session_version(user.email)
    session.modified = True


def is_session_version_current(user):
    if user is None:
        return False

    current_version = get_user_session_version(user.email)
    session_version = session.get("session_version")
    if session_version is None:
        session["session_version"] = current_version
        session.modified = True
        return True

    return device_security_service.is_session_version_current(session_version, current_version)


def rotate_user_session_version(email):
    raw_settings = repository_load_user_ai_settings(email)
    raw_settings, new_version = device_security_service.rotate_session_version(
        raw_settings,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )
    save_user_raw_settings(email, raw_settings)
    session["session_version"] = new_version
    session.modified = True
    return new_version


def current_device_fingerprint():
    raw = "|".join([
        request.headers.get("User-Agent", ""),
        request.headers.get("Accept-Language", ""),
        request.headers.get("X-Forwarded-For", request.remote_addr or ""),
    ])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def current_device_payload():
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return {
        "id": current_device_fingerprint(),
        "label": clean_text(request.headers.get("User-Agent", "Browser session"))[:160] or "Browser session",
        "ip": clean_text(request.headers.get("X-Forwarded-For", request.remote_addr or "unknown").split(",")[0].strip()),
        "trusted_at": now,
        "last_seen_at": now,
    }


def record_trusted_device_seen(user):
    if user is None:
        return False

    raw_settings = repository_load_user_ai_settings(user.email)
    raw_settings, updated = device_security_service.update_trusted_device_seen(
        raw_settings,
        current_device_payload(),
    )

    if updated:
        save_user_raw_settings(user.email, raw_settings)

    return updated


def is_current_device_trusted(user):
    if user is None:
        return False

    raw_settings = repository_load_user_ai_settings(user.email)
    return device_security_service.is_device_trusted(
        raw_settings,
        current_device_fingerprint(),
    )


def migrate_user_settings_email(old_email, new_email):
    old_email = normalize_email(old_email)
    new_email = normalize_email(new_email)
    if not old_email or not new_email or old_email == new_email:
        return

    old_settings = repository_load_user_ai_settings(old_email)
    new_settings = repository_load_user_ai_settings(new_email)
    if isinstance(old_settings, dict) and old_settings:
        merged = dict(old_settings)
        if isinstance(new_settings, dict):
            merged.update(new_settings)
        save_user_raw_settings(new_email, merged)


def social_snapshot_for_email(social_data, email):
    return account_data_service.social_snapshot_for_email(social_data, email)


def relationship_snapshot_for_email(data, key, email):
    return account_data_service.relationship_snapshot_for_email(data, key, email)


def account_deletion_snapshot(email):
    normalized_email = normalize_email(email)
    user = find_user_by_email(normalized_email)
    feed_data = load_feed()
    posts = feed_data.get("posts", []) if isinstance(feed_data, dict) else []
    messages = load_messages()
    notifications_data = load_notifications()
    social_data = load_social()
    blocks_data = load_blocks()
    restrictions_data = load_restrictions()
    hidden_stories_data = load_hidden_stories()
    stories_data = load_stories()
    proofs_data = load_proofs()
    reports_data = load_reports()
    ai_core_memory = load_ai_core_memory()
    ai_feed_learning = load_ai_feed_learning()

    return {
        "snapshot_type": "account_deletion",
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "email": normalized_email,
        "account": safe_account_payload(user),
        "settings": repository_load_user_ai_settings(normalized_email),
        "posts": [
            post for post in posts
            if isinstance(post, dict) and normalize_email(post.get("email", post.get("author_email", ""))) == normalized_email
        ],
        "messages": [
            message for message in messages if isinstance(message, dict)
            and normalized_email in {normalize_email(message.get("from", "")), normalize_email(message.get("to", ""))}
        ] if isinstance(messages, list) else [],
        "notifications": [
            item for item in notifications_data if isinstance(item, dict)
            and normalized_email in {normalize_email(item.get("email", "")), normalize_email(item.get("from_email", item.get("from", "")))}
        ] if isinstance(notifications_data, list) else [],
        "social": social_snapshot_for_email(social_data, normalized_email),
        "safety": {
            "blocks": relationship_snapshot_for_email(blocks_data, "blocks", normalized_email)["blocks"],
            "restrictions": relationship_snapshot_for_email(restrictions_data, "restrictions", normalized_email)["restrictions"],
            "hidden_stories": relationship_snapshot_for_email(hidden_stories_data, "hidden_stories", normalized_email)["hidden_stories"],
        },
        "stories": [
            story for story in stories_data.get("stories", [])
            if isinstance(story, dict) and normalize_email(story.get("email", story.get("author_email", ""))) == normalized_email
        ] if isinstance(stories_data, dict) else [],
        "proofs": [
            proof for proof in proofs_data.get("proofs", [])
            if isinstance(proof, dict) and normalize_email(proof.get("email", proof.get("user_email", ""))) == normalized_email
        ] if isinstance(proofs_data, dict) else [],
        "reports": [
            report for report in reports_data.get("reports", [])
            if isinstance(report, dict) and normalized_email in {
                normalize_email(report.get("reporter_email", report.get("reporter", ""))),
                normalize_email(report.get("target_email", report.get("target", ""))),
            }
        ] if isinstance(reports_data, dict) else [],
        "ai_core_memory": ai_core_memory.get(normalized_email, []) if isinstance(ai_core_memory, dict) else [],
        "ai_feed_learning": ai_feed_learning.get(normalized_email, {}) if isinstance(ai_feed_learning, dict) else {},
    }


def save_account_deletion_snapshot(email):
    snapshot = account_deletion_snapshot(email)
    safe_email = secure_filename(normalize_email(email).replace("@", "_at_").replace(".", "_"))
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    directory = os.path.join("backups", "deleted_accounts")
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, f"{safe_email}_{timestamp}.json")
    with open(path, "w", encoding="utf-8") as file:
        json.dump(snapshot, file, indent=2, ensure_ascii=False)
    return path


def revoke_all_push_devices(email):
    return get_device_push_repository().revoke_all(email)


def delete_account_data(email):
    normalized_email = normalize_email(email)
    global users

    revoke_all_push_devices(normalized_email)

    users = [user for user in users if normalize_email(getattr(user, "email", "")) != normalized_email]
    save_users_to_json(users)

    feed_data = load_feed()
    if isinstance(feed_data, dict):
        posts = feed_data.get("posts", [])
        feed_data["posts"] = [
            post for post in posts
            if normalize_email(post.get("email", post.get("author_email", ""))) != normalized_email
        ] if isinstance(posts, list) else []
        save_feed(feed_data)

    messages = load_messages()
    if isinstance(messages, list):
        save_messages([
            message for message in messages
            if normalized_email not in {normalize_email(message.get("from", "")), normalize_email(message.get("to", ""))}
        ])

    notifications_data = load_notifications()
    if isinstance(notifications_data, list):
        save_notifications([
            item for item in notifications_data
            if normalized_email not in {normalize_email(item.get("email", "")), normalize_email(item.get("from_email", item.get("from", "")))}
        ])

    save_user_raw_settings(normalized_email, {})

    social_data = load_social()
    if isinstance(social_data, dict):
        social_data["friends"] = [
            item for item in social_data.get("friends", [])
            if normalized_email not in {normalize_email(item.get("user", "")), normalize_email(item.get("friend", ""))}
        ]
        social_data["follows"] = [
            item for item in social_data.get("follows", [])
            if normalized_email not in {normalize_email(item.get("follower", "")), normalize_email(item.get("following", ""))}
        ]
        social_data["friend_requests"] = [
            item for item in social_data.get("friend_requests", [])
            if normalized_email not in {normalize_email(item.get("from", "")), normalize_email(item.get("to", ""))}
        ]
        save_social(social_data)

    save_blocks(account_data_service.clean_relationship_map(load_blocks(), "blocks", normalized_email))
    save_restrictions(account_data_service.clean_relationship_map(load_restrictions(), "restrictions", normalized_email))
    save_hidden_stories(account_data_service.clean_relationship_map(load_hidden_stories(), "hidden_stories", normalized_email))

    reports_data = load_reports()
    if isinstance(reports_data, dict):
        reports_data["reports"] = [
            report for report in reports_data.get("reports", [])
            if normalized_email not in {
                normalize_email(report.get("reporter_email", report.get("reporter", ""))),
                normalize_email(report.get("target_email", report.get("target", ""))),
            }
        ]
        save_reports(reports_data)

    stories_data = load_stories()
    if isinstance(stories_data, dict):
        stories_data["stories"] = [
            story for story in stories_data.get("stories", [])
            if normalize_email(story.get("email", story.get("author_email", ""))) != normalized_email
        ]
        save_stories(stories_data)

    proofs_data = load_proofs()
    if isinstance(proofs_data, dict):
        proofs_data["proofs"] = [
            proof for proof in proofs_data.get("proofs", [])
            if normalize_email(proof.get("email", proof.get("user_email", ""))) != normalized_email
        ]
        save_proofs(proofs_data)

    ai_core_memory = load_ai_core_memory()
    if isinstance(ai_core_memory, dict):
        ai_core_memory.pop(normalized_email, None)
        save_ai_core_memory(ai_core_memory)

    ai_feed_learning = load_ai_feed_learning()
    if isinstance(ai_feed_learning, dict):
        ai_feed_learning.pop(normalized_email, None)
        save_ai_feed_learning(ai_feed_learning)

    presence_status = load_presence_status()
    if isinstance(presence_status, dict):
        presence_status.pop(normalized_email, None)
        save_presence_status(presence_status)

    typing_status = load_typing_status()
    if isinstance(typing_status, dict):
        save_typing_status({
            key: value for key, value in typing_status.items()
            if normalized_email not in key
        })

    delete_call_rooms_for_participant(normalized_email)


def user_allows_notification(email, notification_type="system", from_email=""):
    return notification_privacy_service.allows_notification(
        normalize_user_ai_settings(email),
        notification_type,
        from_email=from_email,
        target_email=email,
        is_restricted=is_restricted,
    )


def send_login_alert(user):
    if user is None:
        return

    ui = translation_bundle(get_current_language(user))
    notification_key = "login_alert_notification" if is_current_device_trusted(user) else "login_alert_untrusted_notification"
    create_social_notification(
        user.email,
        ui.get(notification_key, "New login to your NOVIX account."),
        "login_alert",
        user.email,
    )


def post_matches_content_filters(user_email, post):
    return feed_privacy_service.post_matches_content_filters(
        normalize_user_ai_settings(user_email),
        post,
    )


def can_view_feed_post(viewer_email, post):
    return feed_privacy_service.can_view_feed_post(
        viewer_email,
        post,
        normalize_user_ai_settings(viewer_email),
        is_blocked,
        is_restricted,
    )


def can_show_user_in_ai_recommendations(viewer_email, candidate_user):
    if candidate_user is None:
        return False

    candidate_email = normalize_email(getattr(candidate_user, "email", ""))
    return profile_access_service.can_show_in_ai_recommendations(
        viewer_email,
        candidate_email,
        normalize_user_ai_settings(candidate_email),
        is_blocked,
        is_restricted,
    )


def api_error(message, status_code=400):
    response = jsonify({
        "ok": False,
        "error": clean_text(message)
    })
    response.status_code = status_code
    return response


def api_user_payload(user):
    return user_payload(user)


def api_compact_user_payload(user):
    payload = compact_user_payload(user)
    if payload is not None:
        payload["avatar_url"] = get_avatar_url(user.email)
    return payload


def get_api_current_user():
    logged_email = session.get("user_email", "")
    if logged_email:
        user = find_user_by_email(logged_email)
        if user is None:
            session.clear()
            return None
        if not is_session_version_current(user):
            log_security_event("stale_api_session_rejected", user.email, "Session version is no longer current")
            session.clear()
            return None
        return user

    auth_header = request.headers.get("Authorization", "")
    prefix = "Bearer "
    if not auth_header.startswith(prefix):
        return None

    token_data = verify_access_token(auth_header[len(prefix):].strip(), app.secret_key)
    if not token_data:
        return None

    logged_email = token_data.get("email", "")
    user = find_user_by_email(logged_email)
    if user is None:
        return None
    if not device_security_service.is_session_version_current(
        token_data.get("session_version"),
        get_user_session_version(user.email),
    ):
        log_security_event("stale_api_token_rejected", user.email, "Bearer token session version is no longer current")
        return None
    return user


def revoke_api_bearer_token():
    auth_header = request.headers.get("Authorization", "")
    prefix = "Bearer "
    if not auth_header.startswith(prefix):
        return False

    token_data = verify_access_token(auth_header[len(prefix):].strip(), app.secret_key)
    if not token_data:
        return False

    user = find_user_by_email(token_data.get("email", ""))
    if user is None:
        return False

    current_version = get_user_session_version(user.email)
    if not device_security_service.is_session_version_current(token_data.get("session_version"), current_version):
        return False

    rotate_user_session_version(user.email)
    log_security_event("api_token_revoked", user.email, "Bearer token revoked by logout")
    return True


def issue_mobile_refresh_token(user):
    return refresh_token_service.issue_refresh_token(
        user.email,
        app.secret_key,
        get_user_session_version(user.email),
        get_refresh_session_repository(),
        device_id=current_device_fingerprint(),
    )


def rotate_mobile_refresh_token(raw_token):
    payload = verify_refresh_token(raw_token, app.secret_key)
    if not payload:
        return {"ok": False, "error": "invalid_refresh_token"}
    user = find_user_by_email(payload.get("email", ""))
    if user is None:
        return {"ok": False, "error": "invalid_refresh_token"}
    return refresh_token_service.rotate_refresh_token(
        raw_token,
        app.secret_key,
        get_user_session_version(user.email),
        get_refresh_session_repository(),
        device_id=current_device_fingerprint(),
    )


def revoke_mobile_refresh_token(raw_token):
    return refresh_token_service.revoke_refresh_token(
        raw_token,
        app.secret_key,
        get_refresh_session_repository(),
    )


def api_login_session(user):
    csrf_token = session.get("csrf_token")
    session.clear()
    session.permanent = True
    if csrf_token:
        session["csrf_token"] = csrf_token
    session["user_email"] = user.email
    session["login_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    bind_session_to_user(user)
    session.modified = True


app.register_blueprint(create_auth_api({
    "User": User,
    "api_login_session": lambda user: api_login_session(user),
    "api_user_payload": lambda user: api_user_payload(user),
    "calculate_trust_score": lambda user: calculate_trust_score(user),
    "clean_text": clean_text,
    "clear_login_attempts": lambda email: clear_login_attempts(email),
    "clear_session": lambda: session.clear(),
    "revoke_bearer_token": lambda: revoke_api_bearer_token(),
    "issue_refresh_token": lambda user: issue_mobile_refresh_token(user),
    "rotate_refresh_token": lambda raw_token: rotate_mobile_refresh_token(raw_token),
    "revoke_refresh_token": lambda raw_token: revoke_mobile_refresh_token(raw_token),
    "create_verification_code": lambda purpose, contact_type, contact_value: create_verification_code(purpose, contact_type, contact_value),
    "create_access_token": lambda email: create_signed_access_token(
        email,
        app.secret_key,
        session_version=get_user_session_version(email),
    ),
    "access_token_seconds": DEFAULT_ACCESS_TOKEN_SECONDS,
    "find_user_by_contact": lambda contact_type, contact_value: find_user_by_contact(contact_type, contact_value),
    "find_user_by_email": lambda email: find_user_by_email(email),
    "find_user_by_identifier": lambda identifier: find_user_by_identifier(identifier),
    "find_user_by_login": lambda login_value: find_user_by_login(login_value),
    "get_user_2fa_contact": lambda user: get_user_2fa_contact(user),
    "get_users": lambda: users,
    "is_account_verified": lambda user: is_account_verified(user),
    "is_login_temporarily_locked": lambda email: is_login_temporarily_locked(email),
    "log_security_event": lambda event_type, email="", details="": log_security_event(event_type, email, details),
    "load_call_signals": lambda: load_call_signals(),
    "make_internal_phone_email": lambda phone_value: make_internal_phone_email(phone_value),
    "mark_account_verified": lambda user, contact_type="email": mark_account_verified(user, contact_type),
    "normalize_email": normalize_email,
    "normalize_phone": normalize_phone,
    "onboarding_redirect_for": lambda user: onboarding_redirect_for(user),
    "parse_short_list": parse_short_list,
    "register_failed_login_attempt": lambda email: register_failed_login_attempt(email),
    "save_language_preference": lambda email, language: save_user_raw_settings(
        email,
        {**normalize_user_ai_settings(email), "interface_language": language},
    ),
    "save_users_to_json": lambda users_value: save_users_to_json(users_value),
    "send_verification_code": lambda contact_type, contact_value, code: send_verification_code(contact_type, contact_value, code),
    "set_user_password": lambda user, raw_password: set_user_password(user, raw_password),
    "verification_code_minutes": VERIFICATION_CODE_MINUTES,
    "verify_contact_code": lambda purpose, contact_type, contact_value, code: verify_contact_code(purpose, contact_type, contact_value, code),
    "verify_user_password": lambda user, raw_password: verify_user_password(user, raw_password),
}))


app.register_blueprint(create_profile_api({
    "api_user_payload": lambda user: api_user_payload(user),
    "calculate_trust_score": lambda user: calculate_trust_score(user),
    "clean_text": clean_text,
    "count_followers": lambda email: count_followers(email),
    "count_following": lambda email: count_following(email),
    "get_api_current_user": lambda: get_api_current_user(),
    "get_users": lambda: users,
    "log_security_event": lambda event_type, email="", details="": log_security_event(event_type, email, details),
    "normalize_user_ai_settings": lambda email: normalize_user_ai_settings(email),
    "privacy_service": privacy_service,
    "profile_service": profile_service,
    "save_onboarding_answers": lambda user, data: save_onboarding_answers(user, data),
    "save_user_ai_settings": lambda email, settings: save_user_ai_settings(email, settings),
    "save_users_to_json": lambda users_value: save_users_to_json(users_value),
    "utc_now_text": lambda: datetime.now(timezone.utc).isoformat(),
}))


app.register_blueprint(create_feed_api({
    "api_post_payload": lambda post: api_post_payload(post),
    "can_view_feed_post": lambda viewer_email, post: can_view_feed_post(viewer_email, post),
    "clean_text": clean_text,
    "detect_content_language": lambda text: detect_content_language(text),
    "feed_service": feed_service_module,
    "get_api_current_user": lambda: get_api_current_user(),
    "is_blocked": lambda one, two: is_blocked(one, two),
    "is_restricted": lambda one, two: is_restricted(one, two),
    "load_feed": lambda: load_feed(),
    "normalize_content_language_code": lambda value: normalize_content_language_code(value),
    "normalize_email": normalize_email,
    "parse_short_list": lambda value, limit=6: parse_short_list(value, limit=limit),
    "record_ai_feed_signal": lambda user_email, post, action_type: record_ai_feed_signal(user_email, post, action_type),
    "save_feed": lambda data: save_feed(data),
    "validate_write_request": lambda: validate_csrf_token() if not request.headers.get("Authorization", "").startswith("Bearer ") else None,
}))


app.register_blueprint(create_messages_api({
    "api_message_payload": lambda message, current_email="": api_message_payload(message, current_email),
    "api_compact_user_payload": lambda user: api_compact_user_payload(user),
    "clean_text": clean_text,
    "create_social_notification": lambda to_email, text, notification_type, from_email: create_social_notification(
        to_email,
        text,
        notification_type,
        from_email,
    ),
    "find_user_by_email": lambda email: find_user_by_email(email),
    "get_api_current_user": lambda: get_api_current_user(),
    "get_message_permission_status": lambda current_user, other_user: get_message_permission_status(current_user, other_user),
    "is_blocked": lambda one, two: is_blocked(one, two),
    "load_messages": lambda: load_messages(),
    "message_service": message_service_module,
    "message_translation_service": message_translation_service,
    "detect_content_language": lambda text: detect_content_language(text),
    "get_current_language": lambda user: get_current_language(user),
    "normalize_content_language_code": lambda value: normalize_content_language_code(value),
    "normalize_user_ai_settings": lambda email: normalize_user_ai_settings(email),
    "save_messages": lambda data: save_messages(data),
    "translate_message_text": lambda text, source, target: translate_message_text(text, source, target),
    "translation_provider_available": lambda: bool(get_ai_provider_status().get("enabled")),
}))


app.register_blueprint(create_call_captions_api({
    "append_call_caption": lambda room_id, segment, **options: append_call_caption(room_id, segment, **options),
    "append_call_quality_sample": lambda room_id, sample, **options: append_call_quality_sample(room_id, sample, **options),
    "call_caption_service": call_caption_service,
    "call_quality_service": call_quality_service,
    "clean_text": clean_text,
    "detect_content_language": lambda text: detect_content_language(text),
    "find_user_by_email": lambda email: find_user_by_email(email),
    "get_api_current_user": lambda: get_api_current_user(),
    "get_call_room_id": lambda one, two, call_type: get_call_room_id(one, two, call_type),
    "get_call_signal_room": lambda room_id: get_call_signal_room(room_id),
    "get_current_language": lambda user: get_current_language(user),
    "is_blocked": lambda one, two: is_blocked(one, two),
    "is_restricted": lambda one, two: is_restricted(one, two),
    "message_translation_service": message_translation_service,
    "normalize_content_language_code": lambda value: normalize_content_language_code(value),
    "normalize_email": normalize_email,
    "normalize_user_ai_settings": lambda email: normalize_user_ai_settings(email),
    "save_user_ai_settings": lambda email, settings: save_user_ai_settings(email, settings),
    "log_security_event": lambda event_type, email="", details="": log_security_event(event_type, email, details),
    "validate_write_request": lambda: validate_csrf_token() if not request.headers.get("Authorization", "").startswith("Bearer ") else None,
    "reserve_call_transcription": lambda room_id, speaker, sequence, now, **options: reserve_call_transcription(room_id, speaker, sequence, now, **options),
    "set_call_caption_translation": lambda room_id, caption_id, language, text: set_call_caption_translation(room_id, caption_id, language, text),
    "secure_call_id": lambda value: secure_filename(value),
    "speech_transcription_service": speech_transcription_service,
    "transcribe_audio_chunk": lambda audio, content_type, language: speech_transcription_service.transcribe_audio_chunk(audio, content_type, language),
    "translate_message_text": lambda text, source, target: translate_message_text(text, source, target),
    "turn_credential_service": turn_credential_service,
    "speech_rate_limiter": call_speech_limiter,
    "create_realtime_transcription_session": lambda language: realtime_speech_service.create_transcription_session(language),
    "synthesize_translated_speech": lambda text, voice: realtime_speech_service.synthesize_speech(text, voice),
}))


app.register_blueprint(create_call_signals_api({
    "acknowledge": lambda room_id, receiver, event_ids, now: acknowledge_call_signals(room_id, receiver, event_ids, now),
    "append_signal": lambda room_id, signal, **options: append_call_signal(room_id, signal, **options),
    "cancel_push_event": call_cancel_push_event,
    "clean_text": clean_text,
    "expire_room": lambda room_id, now: expire_call_signal_room(room_id, now),
    "find_user_by_email": lambda email: find_user_by_email(email),
    "get_api_current_user": lambda: get_api_current_user(),
    "get_call_room_id": lambda one, two, call_type: get_call_room_id(one, two, call_type),
    "get_current_language": get_current_language,
    "get_room": lambda room_id: get_call_signal_room(room_id),
    "is_blocked": lambda one, two: is_blocked(one, two),
    "is_restricted": lambda one, two: is_restricted(one, two),
    "normalize_email": lambda value: normalize_email(value),
    "poll_limiter": call_signal_poll_limiter,
    "record_history": lambda *args: record_call_chat_event(*args),
    "secure_call_id": secure_filename,
    "security": call_signal_security_service,
    "translation_bundle": translation_bundle,
    "validate_write_request": lambda: validate_csrf_token() if not request.headers.get("Authorization", "").startswith("Bearer ") else None,
}))


app.register_blueprint(create_conferences_api({
    "append_call_signal": lambda room_id, signal, **options: append_call_signal(room_id, signal, **options),
    "clean_text": clean_text,
    "find_user_by_email": lambda email: find_user_by_email(email),
    "get_api_current_user": lambda: get_api_current_user(),
    "get_avatar_url": lambda email: get_avatar_url(email),
    "get_call_signal_room": lambda room_id: get_call_signal_room(room_id),
    "get_csrf_token": get_csrf_token,
    "get_current_language": get_current_language,
    "get_users": lambda: users,
    "is_blocked": lambda one, two: is_blocked(one, two),
    "is_restricted": lambda one, two: is_restricted(one, two),
    "log_security_event": lambda event_type, email="", details="": log_security_event(event_type, email, details),
    "load_call_signals": lambda: load_call_signals(),
    "normalize_email": normalize_email,
    "public_user": lambda user: api_compact_user_payload(user),
    "stable_user_id": lambda user: str(getattr(user, "id", "")),
    "translation_bundle": translation_bundle,
    "validate_write_request": lambda: validate_csrf_token() if not request.headers.get("Authorization", "").startswith("Bearer ") else None,
}))


app.register_blueprint(create_mobile_api({
    "api_user_payload": lambda user: api_user_payload(user),
    "get_api_current_user": lambda: get_api_current_user(),
    "get_current_language": lambda user: get_current_language(user),
    "normalize_user_ai_settings": lambda email: normalize_user_ai_settings(email),
    "transcription_provider_available": lambda: speech_transcription_service.provider_available(),
    "translation_provider_available": lambda: bool(get_ai_provider_status().get("enabled")),
    "realtime_speech_provider_available": lambda: realtime_speech_service.provider_available(),
    "build_mobile_speech_contract": mobile_speech_contract_service.build_contract,
}))


app.register_blueprint(create_social_api({
    "api_user_payload": lambda user: api_user_payload(user),
    "are_friends": lambda one, two: are_friends(one, two),
    "clean_text": clean_text,
    "create_social_notification": lambda to_email, text, notification_type, from_email: create_social_notification(
        to_email,
        text,
        notification_type,
        from_email,
    ),
    "find_user_by_email": lambda email: find_user_by_email(email),
    "find_user_by_identifier": lambda identifier: find_user_by_identifier(identifier),
    "get_followers": lambda email: get_followers(email),
    "get_following": lambda email: get_following(email),
    "get_current_language": lambda user: get_current_language(user),
    "get_api_current_user": lambda: get_api_current_user(),
    "is_blocked": lambda one, two: is_blocked(one, two),
    "load_social": lambda: load_social(),
    "normalize_email": normalize_email,
    "normalize_user_ai_settings": lambda email: normalize_user_ai_settings(email),
    "social_service": social_service,
    "update_friend_request_notification_status": lambda target_email, from_email, status: update_friend_request_notification_status(
        target_email,
        from_email,
        status,
    ),
    "validate_write_request": lambda: validate_csrf_token() if not request.headers.get("Authorization", "").startswith("Bearer ") else None,
}))


app.register_blueprint(create_notifications_api({
    "clean_text": clean_text,
    "get_api_current_user": lambda: get_api_current_user(),
    "get_notifications": lambda email: get_notifications(email),
    "normalize_email": normalize_email,
}))


app.register_blueprint(create_device_push_api({
    "clean_text": clean_text,
    "device_push_service": device_push_service,
    "get_api_current_user": lambda: get_api_current_user(),
    "get_device_push_repository": lambda: get_device_push_repository(),
    "validate_write_request": lambda: validate_csrf_token() if not request.headers.get("Authorization", "").startswith("Bearer ") else None,
    "web_push_public_key": lambda: os.environ.get("VAPID_PUBLIC_KEY", "").strip(),
}))


app.register_blueprint(create_matches_api({
    "api_user_payload": lambda user: api_user_payload(user),
    "can_show_user_in_ai_recommendations": lambda viewer_email, candidate_user: can_show_user_in_ai_recommendations(
        viewer_email,
        candidate_user,
    ),
    "clean_text": clean_text,
    "explain_match": lambda current_user, matched_user: explain_match(current_user, matched_user),
    "explain_user_match": lambda current_user, matched_user: explain_user_match(current_user, matched_user),
    "find_best_matches": lambda current_user, all_users: find_best_matches(current_user, all_users),
    "get_api_current_user": lambda: get_api_current_user(),
    "get_match_level": lambda score: get_match_level(score),
    "get_users": lambda: users,
}))


app.register_blueprint(create_stories_api({
    "api_user_payload": lambda user: api_user_payload(user),
    "can_view_user_stories": lambda viewer_email, owner_email: can_view_user_stories(viewer_email, owner_email),
    "clean_text": clean_text,
    "current_session_email": lambda: session.get("user_email", ""),
    "find_user_by_email": lambda email: find_user_by_email(email),
    "find_user_by_identifier": lambda identifier: find_user_by_identifier(identifier),
    "get_api_current_user": lambda: get_api_current_user(),
    "is_story_active": lambda story: is_story_active(story),
    "load_stories": lambda: load_stories(),
    "normalize_email": normalize_email,
    "save_stories": lambda data: save_stories(data),
}))


app.register_blueprint(create_admin_api({
    "call_quality_service": call_quality_service,
    "clean_text": clean_text,
    "get_api_current_user": lambda: get_api_current_user(),
    "is_admin_email": lambda email: is_admin_email(email),
    "load_reports": lambda: load_reports(),
    "load_call_signals": lambda: load_call_signals(),
    "log_security_event": lambda event_type, email="", details="": log_security_event(event_type, email, details),
    "normalize_email": normalize_email,
    "moderation_service": moderation_service,
    "normalize_email": normalize_email,
    "save_reports": lambda data: save_reports(data),
}))


def api_post_payload(post):
    author_email = normalize_email(post.get("email") or post.get("author_email") or "")
    author = find_user_by_email(author_email)
    return post_payload(post, author=author, normalize_language=normalize_content_language_code)


def api_message_payload(message, current_email=""):
    return message_payload(message, current_email=current_email)


app.register_blueprint(create_discovery_routes({
    "can_show_user_in_ai_recommendations": lambda viewer_email, candidate_user: can_show_user_in_ai_recommendations(
        viewer_email,
        candidate_user,
    ),
    "clean_text": clean_text,
    "csrf_input": csrf_input,
    "current_session_email": lambda: session.get("user_email", ""),
    "explain_match": lambda current_user, matched_user: explain_match(current_user, matched_user),
    "explain_user_match": lambda current_user, matched_user: explain_user_match(current_user, matched_user),
    "find_best_matches": lambda current_user, all_users: find_best_matches(current_user, all_users),
    "find_user_by_email": lambda email: find_user_by_email(email),
    "find_user_by_identifier": lambda identifier: find_user_by_identifier(identifier),
    "get_avatar_url": lambda email: get_avatar_url(email),
    "get_current_language": lambda user: get_current_language(user),
    "get_match_level": lambda score: get_match_level(score),
    "get_user_privacy": lambda email: get_user_privacy(email),
    "get_users": lambda: users,
    "is_account_deactivated": lambda user: is_account_deactivated(user),
    "is_blocked": lambda one, two: is_blocked(one, two),
    "is_restricted": lambda one, two: is_restricted(one, two),
    "login_required": login_required,
    "log_security_event": lambda event_type, email="", details="": log_security_event(event_type, email, details),
    "normalize_email": normalize_email,
    "normalize_user_ai_settings": lambda email: normalize_user_ai_settings(email),
    "safe_text": safe_text,
    "translation_bundle": lambda language: translation_bundle(language),
    "validate_csrf_token": validate_csrf_token,
}))


app.register_blueprint(create_media_routes({
    "allowed_extensions": lambda: ALLOWED_EXTENSIONS,
    "allowed_file": lambda filename: allowed_file(filename),
    "allowed_mime_type": lambda file: allowed_mime_type(file),
    "avatar_file_stems": lambda email: avatar_file_stems(email),
    "avatar_filename": lambda email, extension: avatar_filename(email, extension),
    "can_access_media_file": lambda filename: can_access_media_file(filename),
    "csrf_input": csrf_input,
    "current_session_email": lambda: session.get("user_email", ""),
    "find_user_by_email": lambda email: find_user_by_email(email),
    "find_user_by_identifier": lambda identifier: find_user_by_identifier(identifier),
    "get_avatar_url": lambda email: get_avatar_url(email),
    "get_current_language": lambda user: get_current_language(user),
    "login_required": login_required,
    "log_security_event": lambda event_type, email="", details="": log_security_event(event_type, email, details),
    "normalize_email": normalize_email,
    "safe_text": safe_text,
    "upload_folder": lambda: UPLOAD_FOLDER,
    "upload_folders": lambda: (UPLOAD_FOLDER, LEGACY_UPLOAD_FOLDER),
    "translation_bundle": lambda language: translation_bundle(language),
    "validate_csrf_token": validate_csrf_token,
}))


app.register_blueprint(create_feed_routes({
    "allowed_mime_type": lambda uploaded_file: allowed_mime_type(uploaded_file),
    "calculate_ai_learning_boost": lambda user_email, post, content_language: calculate_ai_learning_boost(
        user_email,
        post,
        content_language,
    ),
    "can_view_feed_post": lambda viewer_email, post: can_view_feed_post(viewer_email, post),
    "clean_text": clean_text,
    "content_languages": lambda: CONTENT_LANGUAGES,
    "csrf_input": csrf_input,
    "current_session_email": lambda: session.get("user_email", ""),
    "detect_content_language": lambda text: detect_content_language(text),
    "find_user_by_email": lambda email: find_user_by_email(email),
    "find_user_by_identifier": lambda identifier: find_user_by_identifier(identifier),
    "get_avatar_url": lambda email: get_avatar_url(email),
    "get_current_language": lambda user: get_current_language(user),
    "get_message_permission_status": lambda current_user, author: get_message_permission_status(current_user, author),
    "get_user_language_signals": lambda user: get_user_language_signals(user),
    "load_feed": lambda: load_feed(),
    "login_required": login_required,
    "log_security_event": lambda event_type, email="", details="": log_security_event(event_type, email, details),
    "normalize_content_language_code": lambda value: normalize_content_language_code(value),
    "normalize_email": normalize_email,
    "normalize_user_ai_settings": lambda email: normalize_user_ai_settings(email),
    "record_ai_feed_signal": lambda email, post, action: record_ai_feed_signal(email, post, action),
    "safe_text": safe_text,
    "save_feed": lambda feed_data: save_feed(feed_data),
    "simple_page": lambda title, text, email: simple_page(title, text, email),
    "translation_bundle": translation_bundle,
    "score_language_match": lambda user, content_language: score_language_match(user, content_language),
    "supported_languages": lambda: SUPPORTED_LANGUAGES,
    "translation_bundle": lambda language: translation_bundle(language),
    "upload_folder": lambda: UPLOAD_FOLDER,
    "validate_csrf_token": validate_csrf_token,
}))


app.register_blueprint(create_feed_interaction_routes({
    "are_friends": lambda one, two: are_friends(one, two),
    "clean_text": clean_text,
    "content_languages": lambda: CONTENT_LANGUAGES,
    "current_session_email": lambda: session.get("user_email", ""),
    "csrf_input": csrf_input,
    "default_language": lambda: DEFAULT_LANGUAGE,
    "detect_content_language": lambda text: detect_content_language(text),
    "find_user_by_email": lambda email: find_user_by_email(email),
    "find_user_by_identifier": lambda identifier: find_user_by_identifier(identifier),
    "find_post_by_id": lambda post_id: find_post_by_id(post_id),
    "generate_ai_translation_summary": lambda text, source_language, target_language: generate_ai_translation_summary(
        text,
        source_language,
        target_language,
    ),
    "get_avatar_url": lambda email: get_avatar_url(email),
    "get_current_language": lambda user: get_current_language(user),
    "get_friends": lambda email: get_friends(email),
    "is_blocked": lambda one, two: is_blocked(one, two),
    "is_restricted": lambda one, two: is_restricted(one, two),
    "load_feed": lambda: load_feed(),
    "load_messages": lambda: load_messages(),
    "login_required": login_required,
    "log_security_event": lambda event_type, email="", details="": log_security_event(event_type, email, details),
    "normalize_content_language_code": lambda value: normalize_content_language_code(value),
    "normalize_email": normalize_email,
    "record_ai_feed_signal": lambda email, post, action: record_ai_feed_signal(email, post, action),
    "safe_text": safe_text,
    "save_feed": lambda feed_data: save_feed(feed_data),
    "save_messages": lambda messages: save_messages(messages),
    "simple_page": lambda title, text, email: simple_page(title, text, email),
    "translation_bundle": lambda language: translation_bundle(language),
    "validate_csrf_token": validate_csrf_token,
}))


app.register_blueprint(create_story_routes({
    "allowed_mime_type": lambda uploaded_file: allowed_mime_type(uploaded_file),
    "can_view_user_stories": lambda viewer_email, owner_email: can_view_user_stories(viewer_email, owner_email),
    "clean_text": clean_text,
    "current_session_email": lambda: session.get("user_email", ""),
    "find_user_by_email": lambda email: find_user_by_email(email),
    "find_user_by_identifier": lambda identifier: find_user_by_identifier(identifier),
    "get_avatar_url": lambda email: get_avatar_url(email),
    "get_current_language": lambda user: get_current_language(user),
    "is_blocked": lambda one, two: is_blocked(one, two),
    "is_story_active": lambda story: is_story_active(story),
    "load_stories": lambda: load_stories(),
    "login_required": login_required,
    "log_security_event": lambda event_type, email="", details="": log_security_event(event_type, email, details),
    "normalize_email": normalize_email,
    "safe_text": safe_text,
    "save_stories": lambda stories_data: save_stories(stories_data),
    "simple_page": lambda title, text, email: simple_page(title, text, email),
    "translation_bundle": translation_bundle,
    "upload_folder": lambda: UPLOAD_FOLDER,
    "validate_csrf_token": validate_csrf_token,
}))


app.register_blueprint(create_profile_routes({
    "are_friends": lambda one, two: are_friends(one, two),
    "clean_text": clean_text,
    "count_followers": lambda email: count_followers(email),
    "count_following": lambda email: count_following(email),
    "csrf_input": csrf_input,
    "current_session_email": lambda: session.get("user_email", ""),
    "find_user_by_email": lambda email: find_user_by_email(email),
    "find_user_by_identifier": lambda identifier: find_user_by_identifier(identifier),
    "get_avatar_url": lambda email: get_avatar_url(email),
    "get_current_language": lambda user: get_current_language(user),
    "has_hidden_stories_from": lambda viewer_email, target_email: has_hidden_stories_from(viewer_email, target_email),
    "is_blocked": lambda one, two: is_blocked(one, two),
    "is_following": lambda viewer_email, user_email: is_following(viewer_email, user_email),
    "is_restricted": lambda viewer_email, user_email: is_restricted(viewer_email, user_email),
    "load_feed": lambda: load_feed(),
    "normalize_email": normalize_email,
    "normalize_user_ai_settings": lambda email: normalize_user_ai_settings(email),
    "profile_view_required": profile_view_required,
    "safe_text": safe_text,
    "simple_page": lambda title, text, email: simple_page(title, text, email),
    "translation_bundle": lambda language: translation_bundle(language),
}))


app.register_blueprint(create_profile_safety_routes({
    "add_profile_report": lambda reporter_email, target_email, reason, details: add_profile_report(
        reporter_email,
        target_email,
        reason,
        details,
    ),
    "block_user_account": lambda blocker_email, blocked_email: block_user_account(blocker_email, blocked_email),
    "clean_text": clean_text,
    "csrf_input": csrf_input,
    "find_user_by_email": lambda email: find_user_by_email(email),
    "find_user_by_identifier": lambda identifier: find_user_by_identifier(identifier),
    "get_current_language": lambda user: get_current_language(user),
    "hide_stories_from_user": lambda viewer_email, target_email: hide_stories_from_user(viewer_email, target_email),
    "login_required": login_required,
    "log_security_event": lambda event_type, email="", details="": log_security_event(event_type, email, details),
    "normalize_email": normalize_email,
    "restrict_user_account": lambda restrictor_email, restricted_email: restrict_user_account(restrictor_email, restricted_email),
    "safe_text": safe_text,
    "show_stories_from_user": lambda viewer_email, target_email: show_stories_from_user(viewer_email, target_email),
    "simple_page": lambda title, text, email: simple_page(title, text, email),
    "translation_bundle": translation_bundle,
    "unblock_user_account": lambda blocker_email, blocked_email: unblock_user_account(blocker_email, blocked_email),
    "unrestrict_user_account": lambda restrictor_email, restricted_email: unrestrict_user_account(restrictor_email, restricted_email),
    "validate_csrf_token": validate_csrf_token,
}))


app.register_blueprint(create_admin_routes({
    "clean_text": clean_text,
    "csrf_input": csrf_input,
    "find_user_by_email": lambda email: find_user_by_email(email),
    "get_current_language": lambda user: get_current_language(user),
    "is_admin_email": lambda email: is_admin_email(email),
    "load_reports": lambda: load_reports(),
    "login_required": login_required,
    "log_security_event": lambda event_type, email="", details="": log_security_event(event_type, email, details),
    "moderation_service": moderation_service,
    "safe_text": safe_text,
    "save_reports": lambda reports_data: save_reports(reports_data),
    "simple_page": lambda title, text, email: simple_page(title, text, email),
    "translation_bundle": translation_bundle,
    "validate_csrf_token": validate_csrf_token,
}))


app.register_blueprint(create_profile_misc_routes({
    "csrf_input": csrf_input,
    "current_session_email": lambda: session.get("user_email", ""),
    "find_user_by_email": lambda email: find_user_by_email(email),
    "find_user_by_identifier": lambda identifier: find_user_by_identifier(identifier),
    "get_avatar_url": lambda email: get_avatar_url(email),
    "get_blocked_users": lambda email: get_blocked_users(email),
    "get_current_language": lambda user=None: get_current_language(user),
    "load_feed": lambda: load_feed(),
    "login_required": login_required,
    "normalize_email": normalize_email,
    "safe_text": safe_text,
    "translation_bundle": lambda language: translation_bundle(language),
}))


app.register_blueprint(create_realtime_routes({
    "load_presence_status": lambda: load_presence_status(),
    "load_typing_status": lambda: load_typing_status(),
    "login_required": login_required,
    "save_presence_status": lambda data: save_presence_status(data),
    "save_typing_status": lambda data: save_typing_status(data),
    "validate_csrf_token": validate_csrf_token,
}))


app.register_blueprint(create_news_routes({
    "allowed_file": lambda filename: allowed_file(filename),
    "allowed_mime_type": lambda uploaded_file: allowed_mime_type(uploaded_file),
    "clean_text": clean_text,
    "csrf_input": csrf_input,
    "current_session_email": lambda: session.get("user_email", ""),
    "find_user_by_email": lambda email: find_user_by_email(email),
    "find_user_by_identifier": lambda identifier: find_user_by_identifier(identifier),
    "get_current_language": lambda user: get_current_language(user),
    "load_news": lambda: load_news(),
    "login_required": login_required,
    "log_security_event": lambda event_type, email="", details="": log_security_event(event_type, email, details),
    "normalize_email": normalize_email,
    "safe_text": safe_text,
    "save_news": lambda news_items: save_news(news_items),
    "secure_filename": secure_filename,
    "translation_bundle": translation_bundle,
    "upload_folder": lambda: UPLOAD_FOLDER,
    "validate_csrf_token": validate_csrf_token,
}))


app.register_blueprint(create_ai_core_routes({
    "clean_text": clean_text,
    "csrf_input": csrf_input,
    "find_user_by_email": lambda email: find_user_by_email(email),
    "find_user_by_identifier": lambda identifier: find_user_by_identifier(identifier),
    "generate_ai_copilot_answer": lambda user, question, mode="general": generate_ai_copilot_answer(user, question, mode),
    "get_current_language": lambda user=None: get_current_language(user),
    "get_ai_provider_status": lambda: get_ai_provider_status(),
    "normalize_email": normalize_email,
    "request_limiter": ai_assistant_limiter,
    "record_ai_core_memory": lambda user_email, mode, question, answer: record_ai_core_memory(user_email, mode, question, answer),
    "render_ai_core_history": lambda user_email, limit=12: render_ai_core_history(user_email, limit=limit),
    "render_selected_ai_core_history": lambda user_email, history_index: render_selected_ai_core_history(user_email, history_index),
    "safe_text": safe_text,
    "translation_bundle": lambda language: translation_bundle(language),
    "validate_csrf_token": validate_csrf_token,
}))


app.register_blueprint(create_auth_page_routes({
    "User": User,
    "bind_session_to_user": lambda user: bind_session_to_user(user),
    "calculate_trust_score": lambda user: calculate_trust_score(user),
    "clean_text": clean_text,
    "clear_login_attempts": lambda email: clear_login_attempts(email),
    "create_verification_code": lambda purpose, contact_type, contact_value: create_verification_code(
        purpose,
        contact_type,
        contact_value,
    ),
    "csrf_input": csrf_input,
    "find_user_by_contact": lambda contact_type, contact_value: find_user_by_contact(contact_type, contact_value),
    "find_user_by_email": lambda email: find_user_by_email(email),
    "find_user_by_login": lambda login_value: find_user_by_login(login_value),
    "get_current_language": lambda user=None: get_current_language(user),
    "get_user_2fa_contact": lambda user: get_user_2fa_contact(user),
    "get_users": lambda: users,
    "is_account_deactivated": lambda user: is_account_deactivated(user),
    "is_account_verified": lambda user: is_account_verified(user),
    "is_login_temporarily_locked": lambda email: is_login_temporarily_locked(email),
    "log_security_event": lambda event_type, email="", details="": log_security_event(event_type, email, details),
    "make_internal_phone_email": lambda phone_value: make_internal_phone_email(phone_value),
    "mark_account_verified": lambda user, contact_type="email": mark_account_verified(user, contact_type),
    "normalize_email": normalize_email,
    "normalize_phone": normalize_phone,
    "onboarding_redirect_for": lambda user: onboarding_redirect_for(user),
    "record_trusted_device_seen": lambda user: record_trusted_device_seen(user),
    "register_failed_login_attempt": lambda email: register_failed_login_attempt(email),
    "safe_text": safe_text,
    "save_language_preference": lambda email, language: save_user_raw_settings(
        email,
        {**normalize_user_ai_settings(email), "interface_language": language},
    ),
    "save_user_ai_settings": lambda email, settings: save_user_ai_settings(email, settings),
    "save_users_to_json": lambda users_value: save_users_to_json(users_value),
    "send_login_alert": lambda user: send_login_alert(user),
    "send_verification_code": lambda contact_type, contact_value, code: send_verification_code(
        contact_type,
        contact_value,
        code,
    ),
    "set_user_password": lambda user, raw_password: set_user_password(user, raw_password),
    "translation_bundle": lambda language: translation_bundle(language),
    "user_requires_login_2fa": lambda user: user_requires_login_2fa(user),
    "validate_csrf_token": validate_csrf_token,
    "verify_contact_code": lambda purpose, contact_type, contact_value, code: verify_contact_code(
        purpose,
        contact_type,
        contact_value,
        code,
    ),
    "verify_user_password": lambda user, raw_password: verify_user_password(user, raw_password),
}))


app.register_blueprint(create_auth_security_routes({
    "bind_session_to_user": lambda user: bind_session_to_user(user),
    "clean_text": clean_text,
    "clear_login_attempts": lambda email: clear_login_attempts(email),
    "create_verification_code": lambda purpose, contact_type, contact_value: create_verification_code(
        purpose,
        contact_type,
        contact_value,
    ),
    "csrf_input": csrf_input,
    "find_user_by_contact": lambda contact_type, contact_value: find_user_by_contact(contact_type, contact_value),
    "find_user_by_email": lambda email: find_user_by_email(email),
    "get_current_language": lambda user=None: get_current_language(user),
    "get_users": lambda: users,
    "login_required": login_required,
    "log_security_event": lambda event_type, email="", details="": log_security_event(event_type, email, details),
    "normalize_email": normalize_email,
    "normalize_phone": normalize_phone,
    "onboarding_redirect_for": lambda user: onboarding_redirect_for(user),
    "record_trusted_device_seen": lambda user: record_trusted_device_seen(user),
    "safe_text": safe_text,
    "save_users_to_json": lambda users_value: save_users_to_json(users_value),
    "send_login_alert": lambda user: send_login_alert(user),
    "send_verification_code": lambda contact_type, contact_value, code: send_verification_code(
        contact_type,
        contact_value,
        code,
    ),
    "set_user_password": lambda user, raw_password: set_user_password(user, raw_password),
    "translation_bundle": lambda language: translation_bundle(language),
    "validate_csrf_token": validate_csrf_token,
    "verify_contact_code": lambda purpose, contact_type, contact_value, code: verify_contact_code(
        purpose,
        contact_type,
        contact_value,
        code,
    ),
}))


def simple_page(title, text, email):
    user = find_user_by_email(email)
    ui = translation_bundle(get_current_language(user))
    return render_template(
        "simple_page.html",
        ui=ui,
        title=safe_text(title),
        body=safe_text(text),
        email=safe_text(email),
        back=ui.get("back_to_dashboard", ui.get("back", "Back")),
    )


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


def find_post_by_id(post_id):
    post_id = str(post_id or "").strip()
    feed_data = load_feed()

    for post in feed_data.get("posts", []):
        if str(post.get("id", "")).strip() == post_id:
            return post

    return None


def load_ai_feed_learning():
    return repository_load_ai_feed_learning()


def save_ai_feed_learning(data):
    repository_save_ai_feed_learning(data)


def record_ai_feed_signal(user_email, post, action_type):
    user_email = normalize_email(user_email)
    action_type = clean_text(action_type)

    if not user_email or not isinstance(post, dict):
        return

    user_settings = normalize_user_ai_settings(user_email)
    if user_settings.get("ai_feed_learning") is False or user_settings.get("ai_activity_analysis") is False:
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

    user_settings = normalize_user_ai_settings(user_email)
    if user_settings.get("ai_feed_learning") is False or user_settings.get("ai_activity_analysis") is False:
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
    return feed_translation_service.generate_ai_translation_summary(text_value, source_language, target_language, {
        "clean_text": clean_text,
        "content_languages": lambda: CONTENT_LANGUAGES,
        "current_session_email": lambda: session.get("user_email", ""),
        "provider_available": lambda: bool(provider_status(check_connection=False).get("enabled")),
        "chat": call_ai_chat,
        "log_security_event": lambda event_type, email="", details="": log_security_event(event_type, email, details),
        "normalize_content_language_code": lambda value: normalize_content_language_code(value),
    })


def translate_message_text(text_value, source_language, target_language):
    if not get_ai_provider_status().get("enabled"):
        return ""
    normalized_source = normalize_content_language_code(source_language)
    normalized_target = normalize_content_language_code(target_language)
    if normalized_target == "unknown":
        return ""
    if normalized_source == normalized_target:
        return clean_text(text_value)
    source_name = CONTENT_LANGUAGES.get(normalized_source, normalized_source)
    target_name = CONTENT_LANGUAGES.get(normalized_target, normalized_target)
    messages = [
        {
            "role": "system",
            "content": (
                "You are the translation engine for private social-network messages. "
                "Translate accurately, preserve tone, names, emoji and formatting. "
                "Never answer the message or add facts. Keep numbers, URLs, @mentions and line breaks unchanged. "
                "Use natural native phrasing in the target language and preserve the speaker's level of formality. "
                "Return only the translated message without notes or quotation marks."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Source language: {source_name} ({normalized_source})\n"
                f"Target language: {target_name} ({normalized_target})\n"
                f"Text to translate, delimited as data:\n<text>{text_value}</text>"
            ),
        },
    ]
    translation_environment = dict(os.environ)
    translation_environment["OLLAMA_MODEL"] = os.environ.get("OLLAMA_TRANSLATION_MODEL", "qwen2.5:1.5b")
    try:
        return clean_text(get_ai_provider(translation_environment).chat(messages, temperature=0.05, max_tokens=600))
    except (AIProviderError, OSError, TypeError, ValueError) as error:
        actor_email = session.get("user_email", "") if has_request_context() else ""
        log_security_event("translation_provider_failed", actor_email, str(error))
        return ""


def get_message_permission_status(sender_user, receiver_user):
    if sender_user is None or receiver_user is None:
        return False, "Пользователь не найден", "Невозможно открыть переписку, потому что один из пользователей не найден."

    return profile_access_service.message_permission_status(
        sender_user.email,
        receiver_user.email,
        getattr(sender_user, "verified", False) is True,
        normalize_user_ai_settings(receiver_user.email),
        is_blocked,
        is_restricted,
        are_friends,
    )


def can_send_message(sender_user, receiver_user):
    allowed, _, _ = get_message_permission_status(sender_user, receiver_user)
    return allowed

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


def get_call_room_id(email_one, email_two, call_type):
    participants = sorted([normalize_email(email_one), normalize_email(email_two)])
    raw_room = "__".join(participants + [clean_text(call_type)])
    return secure_filename(raw_room.replace("@", "_at_").replace(".", "_"))


def load_call_signals():
    return repository_load_call_signals()


def save_call_signals(data):
    repository_save_call_signals(data)


def get_call_signal_room(room_id):
    return repository_get_call_signal_room(room_id)


def append_call_signal(room_id, signal, **options):
    return repository_append_call_signal(room_id, signal, **options)


def acknowledge_call_signals(room_id, receiver_email, event_ids, acknowledged_at):
    return repository_acknowledge_call_signals(room_id, receiver_email, event_ids, acknowledged_at)


def expire_call_signal_room(room_id, now, **options):
    return repository_expire_call_signal_room(room_id, now, **options)


def expire_due_call_rooms(now, **options):
    return repository_expire_due_call_rooms(now, **options)


def delete_call_rooms_for_participant(email):
    return repository_delete_call_rooms_for_participant(email)


def prune_expired_call_rooms(**options):
    return repository_prune_expired_call_rooms(**options)


def append_call_caption(room_id, segment, **options):
    return repository_append_call_caption(room_id, segment, **options)


def append_call_quality_sample(room_id, sample, **options):
    return repository_append_call_quality_sample(room_id, sample, **options)


def set_call_caption_translation(room_id, caption_id, language, translated_text):
    return repository_set_call_caption_translation(room_id, caption_id, language, translated_text)


def reserve_call_transcription(room_id, speaker_email, sequence, now, **options):
    return repository_reserve_call_transcription(room_id, speaker_email, sequence, now, **options)


def purge_call_caption_data(room_id):
    return repository_purge_call_caption_data(room_id)


def format_call_duration(seconds_value):
    try:
        seconds_value = int(max(0, float(seconds_value)))
    except Exception:
        seconds_value = 0

    minutes = seconds_value // 60
    seconds = seconds_value % 60
    return f"{minutes:02d}:{seconds:02d}"


def record_call_chat_event(sender_email, receiver_email, call_type, event_type, duration_seconds=0):
    sender = find_user_by_email(sender_email)
    receiver = find_user_by_email(receiver_email)

    if sender is None or receiver is None:
        return False

    call_type = clean_text(call_type)
    if call_type not in {"audio", "video"}:
        call_type = "audio"

    event_type = clean_text(event_type)
    if event_type not in {"ringing", "accepted", "declined", "ended", "missed"}:
        event_type = "ended"

    icon = "🎥" if call_type == "video" else "📞"
    readable_type = "Видеозвонок" if call_type == "video" else "Аудиозвонок"

    if event_type == "missed":
        title = f"{icon} Пропущенный {readable_type.lower()}"
    elif event_type == "declined":
        title = f"{icon} {readable_type}: отклонён"
    elif event_type == "ended":
        title = f"{icon} {readable_type}: завершён"
    elif event_type == "accepted":
        title = f"{icon} {readable_type}: принят"
    else:
        title = f"{icon} {readable_type}: звонок"

    duration_text = format_call_duration(duration_seconds) if event_type == "ended" and duration_seconds else ""
    now_date = datetime.now().strftime("%d.%m.%Y %H:%M")

    try:
        messages = load_messages()
        if not isinstance(messages, list):
            messages = []

        numeric_ids = []
        for message in messages:
            try:
                numeric_ids.append(int(message.get("id", 0)))
            except Exception:
                continue
        next_id = max(numeric_ids) + 1 if numeric_ids else 1

        event_key = f"call::{normalize_email(sender.email)}::{normalize_email(receiver.email)}::{call_type}::{event_type}::{datetime.now().strftime('%Y%m%d%H%M%S')}"

        messages.append({
            "id": next_id,
            "from": sender.email,
            "to": receiver.email,
            "sender": sender.email,
            "receiver": receiver.email,
            "message": title,
            "media_url": "",
            "media_type": "call_event",
            "media_name": "",
            "message_type": "call_event",
            "call_type": call_type,
            "call_event": event_type,
            "call_duration_seconds": int(max(0, float(duration_seconds or 0))),
            "call_duration_text": duration_text,
            "call_event_key": event_key,
            "time": now_date,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "status": "sent",
            "reactions": {},
            "reply_to": "",
            "deleted_for": []
        })
        save_messages(messages)
        return True
    except Exception as error:
        log_security_event("call_chat_event_failed", sender_email, str(error))
        return False


def run_call_maintenance(now=None, batch_size=200):
    """Run one bounded maintenance pass and return PII-free operational counts."""
    now = float(now if now is not None else datetime.now().timestamp())
    batch_size = min(max(int(batch_size), 1), 1000)
    expired_rooms = expire_due_call_rooms(now, batch_size=batch_size)
    history_events = 0
    for result in expired_rooms:
        transition = result.get("transition") if isinstance(result, dict) else None
        if not isinstance(transition, dict):
            continue
        payload = transition.get("payload", {}) if isinstance(transition.get("payload"), dict) else {}
        if record_call_chat_event(
            transition.get("from", ""),
            transition.get("to", ""),
            payload.get("call_type", "audio"),
            transition.get("type", "ended"),
        ):
            history_events += 1

    pruned_rooms = prune_expired_call_rooms(now=now)
    limiter_repository = getattr(call_signal_poll_limiter, "repository", None)
    expired_buckets = limiter_repository.cleanup_expired() if limiter_repository is not None else 0
    return {
        "expired_call_rooms": len(expired_rooms),
        "call_history_events": history_events,
        "pruned_call_rooms": int(pruned_rooms or 0),
        "expired_rate_limit_buckets": int(expired_buckets or 0),
    }


def find_pending_call_for_chat(current_email, other_email):
    current_email = normalize_email(current_email)
    other_email = normalize_email(other_email)
    prune_expired_call_rooms()
    signals_data = load_call_signals()
    latest_pending = None

    for call_id, room in signals_data.items():
        if not isinstance(room, dict):
            continue

        messages = room.get("messages", [])
        if not isinstance(messages, list):
            continue

        latest_ringing = None
        closed_after_ringing = False
        accepted_after_ringing = False

        for message in messages:
            message_type = clean_text(message.get("type", ""))
            message_from = normalize_email(message.get("from", ""))
            message_to = normalize_email(message.get("to", ""))
            created_at = float(message.get("created_at", 0) or 0)

            if message_type == "ringing" and message_from == other_email and message_to == current_email:
                latest_ringing = message
                closed_after_ringing = False
                accepted_after_ringing = False
                continue

            if latest_ringing and created_at >= float(latest_ringing.get("created_at", 0) or 0):
                if message_type in {"declined", "ended", "missed"}:
                    closed_after_ringing = True
                if message_type == "accepted":
                    accepted_after_ringing = True

        if latest_ringing and not closed_after_ringing and not accepted_after_ringing:
            created_at = float(latest_ringing.get("created_at", 0) or 0)
            payload = latest_ringing.get("payload", {}) if isinstance(latest_ringing.get("payload"), dict) else {}
            call_type = clean_text(payload.get("call_type", "audio"))
            if call_type not in {"audio", "video"}:
                call_type = "audio"

            if datetime.now().timestamp() - created_at > 45:
                missed_signal = {
                    "id": secrets.token_urlsafe(10),
                    "type": "missed",
                    "from": other_email,
                    "to": current_email,
                    "payload": {"call_type": call_type, "missed_at": datetime.now().isoformat()},
                    "created_at": datetime.now().timestamp()
                }
                closed_room = append_call_signal(
                    call_id,
                    missed_signal,
                    status="missed",
                    updated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    close=True,
                    enforce_transition=True,
                )
                if isinstance(closed_room, dict):
                    record_call_chat_event(other_email, current_email, call_type, "missed")
                continue

            if latest_pending is None or created_at > latest_pending.get("created_at", 0):
                latest_pending = {
                    "call_id": secure_filename(call_id),
                    "call_type": call_type,
                    "created_at": created_at
                }

    return latest_pending



def create_social_notification(target_email, text, notification_type="social", from_email=""):
    target_email = normalize_email(target_email)
    from_email = normalize_email(from_email)

    if not target_email:
        return

    if not user_allows_notification(target_email, notification_type, from_email):
        return

    add_notification(target_email, clean_text(text), notification_type, from_email)


def update_friend_request_notification_status(target_email, from_email, status):
    target_email = normalize_email(target_email)
    from_email = normalize_email(from_email)

    if not target_email or not from_email:
        return

    data = load_notifications()
    notifications = data.get("notifications", [])
    if not isinstance(notifications, list):
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

    data["notifications"] = notifications
    save_notifications(data)


configure_chat_call_routes({
    "acknowledge_call_signals": lambda *args, **kwargs: acknowledge_call_signals(*args, **kwargs),
    "allowed_mime_type": lambda uploaded: allowed_mime_type(uploaded),
    "append_call_signal": lambda *args, **kwargs: append_call_signal(*args, **kwargs),
    "call_cancel_push_event": call_cancel_push_event,
    "get_call_signal_poll_limiter": lambda: call_signal_poll_limiter,
    "call_signal_security_service": call_signal_security_service,
    "clean_text": clean_text,
    "csrf_input": csrf_input,
    "detect_content_language": detect_content_language,
    "expire_call_signal_room": lambda *args, **kwargs: expire_call_signal_room(*args, **kwargs),
    "find_pending_call_for_chat": lambda *args, **kwargs: find_pending_call_for_chat(*args, **kwargs),
    "find_user_by_email": lambda email: find_user_by_email(email),
    "find_user_by_identifier": lambda identifier: find_user_by_identifier(identifier),
    "format_visible_last_seen": lambda *args, **kwargs: format_visible_last_seen(*args, **kwargs),
    "get_ai_provider_status": get_ai_provider_status,
    "get_avatar_url": lambda email: get_avatar_url(email),
    "get_call_room_id": get_call_room_id,
    "get_call_signal_room": lambda room: get_call_signal_room(room),
    "get_csrf_token": get_csrf_token,
    "get_current_language": get_current_language,
    "get_message_permission_status": lambda *args: get_message_permission_status(*args),
    "is_blocked": lambda *args: is_blocked(*args),
    "is_restricted": lambda *args: is_restricted(*args),
    "load_messages": lambda: load_messages(),
    "load_presence_status": lambda: load_presence_status(),
    "load_typing_status": lambda: load_typing_status(),
    "log_security_event": lambda *args, **kwargs: log_security_event(*args, **kwargs),
    "login_required": login_required,
    "message_translation_service": message_translation_service,
    "normalize_content_language_code": normalize_content_language_code,
    "normalize_email": normalize_email,
    "normalize_user_ai_settings": lambda email: normalize_user_ai_settings(email),
    "realtime_speech_service": realtime_speech_service,
    "record_call_chat_event": lambda *args, **kwargs: record_call_chat_event(*args, **kwargs),
    "safe_text": safe_text,
    "save_messages": lambda messages: save_messages(messages),
    "save_presence_status": lambda data: save_presence_status(data),
    "simple_page": simple_page,
    "translate_message_text": lambda *args, **kwargs: translate_message_text(*args, **kwargs),
    "translation_bundle": translation_bundle,
    "get_upload_folder": lambda: UPLOAD_FOLDER,
    "get_users": lambda: users,
    "validate_csrf_token": validate_csrf_token,
})
app.register_blueprint(chat_call_routes)


app.register_blueprint(create_messaging_routes({
    "blocked_or_restricted": lambda one, two: is_blocked(one, two) or is_blocked(two, one) or is_restricted(one, two) or is_restricted(two, one),
    "current_session_email": lambda: session.get("user_email", ""),
    "find_user_by_email": lambda email: find_user_by_email(email),
    "find_user_by_identifier": lambda identifier: find_user_by_identifier(identifier),
    "get_avatar_url": lambda email: get_avatar_url(email),
    "get_current_language": lambda user: get_current_language(user),
    "get_users": lambda: users,
    "load_messages": lambda: load_messages(),
    "login_required": login_required,
    "log_security_event": lambda event_type, email="", details="": log_security_event(event_type, email, details),
    "message_permission_status": lambda sender, receiver: get_message_permission_status(sender, receiver),
    "normalize_email": normalize_email,
    "translation_bundle": translation_bundle,
}))


app.register_blueprint(create_dashboard_routes({
    "calculate_activity_count": lambda user, posts: calculate_dashboard_activity_count(user, posts),
    "can_show_user_in_ai_recommendations": lambda viewer, candidate: can_show_user_in_ai_recommendations(viewer, candidate),
    "can_view_feed_post": lambda viewer, post: can_view_feed_post(viewer, post),
    "can_view_user_stories": lambda viewer, owner: can_view_user_stories(viewer, owner),
    "connection_getters": (lambda email: get_friends(email), lambda email: get_following(email), lambda email: get_followers(email)),
    "count_followers": count_followers,
    "count_following": count_following,
    "count_friends": count_friends,
    "csrf_input": csrf_input,
    "current_session_email": lambda: session.get("user_email", ""),
    "find_best_matches": lambda user: find_best_matches(user, users),
    "find_user_by_email": lambda email: find_user_by_email(email),
    "find_user_by_identifier": lambda identifier: find_user_by_identifier(identifier),
    "generate_life_radar": lambda user: generate_life_radar(user),
    "get_avatar_url": lambda email: get_avatar_url(email),
    "get_current_language": lambda user: get_current_language(user),
    "get_notifications": lambda email: get_notifications(email),
    "get_translations": get_translations,
    "is_admin": is_admin_email,
    "is_story_active": lambda story: is_story_active(story),
    "load_feed": lambda: load_feed(),
    "load_stories": lambda: load_stories(),
    "login_required": login_required,
    "log_security_event": log_security_event,
    "normalize_email": normalize_email,
    "normalize_user_ai_settings": lambda email: normalize_user_ai_settings(email),
    "safe_text": safe_text,
    "translation_bundle": translation_bundle,
}))


app.register_blueprint(create_account_page_routes({
    "analyze_user_profile": lambda user: analyze_user_profile(user),
    "apply_transcription_consent": privacy_service.apply_server_transcription_consent_metadata,
    "apply_voice_consent": privacy_service.apply_ai_voice_consent_metadata,
    "build_privacy_update": privacy_service.build_update,
    "clean_text": clean_text,
    "csrf_input": csrf_input,
    "current_session_email": lambda: session.get("user_email", ""),
    "find_user_by_email": lambda email: find_user_by_email(email),
    "find_user_by_identifier": lambda identifier: find_user_by_identifier(identifier),
    "get_current_language": lambda user: get_current_language(user),
    "login_required": login_required,
    "log_security_event": lambda event_type, email="", details="": log_security_event(event_type, email, details),
    "normalize_language_code": normalize_language_code,
    "normalize_user_ai_settings": lambda email: normalize_user_ai_settings(email),
    "parse_privacy_ai_form": lambda form: settings_form_service.parse_privacy_ai_form(
        form, normalize_language_code, UI_LANGUAGES, LANGUAGE_CATALOG,
    ),
    "safe_redirect_target": safe_redirect_target,
    "safe_text": safe_text,
    "save_onboarding_answers": lambda user, form: save_onboarding_answers(user, form),
    "save_language_preference": lambda email, language: save_user_raw_settings(
        email,
        {**normalize_user_ai_settings(email), "interface_language": language},
    ),
    "save_user_ai_settings": lambda email, settings: save_user_ai_settings(email, settings),
    "save_users": lambda: save_users_to_json(users),
    "skip_onboarding": profile_service.skip_onboarding,
    "translation_bundle": translation_bundle,
    "translation_languages": LANGUAGE_CATALOG,
    "ui_languages": UI_LANGUAGES,
    "user_owns_settings_route": user_owns_settings_route,
    "validate_csrf_token": validate_csrf_token,
}))


app.register_blueprint(create_proof_privacy_routes({
    "clean_text": clean_text,
    "csrf_input": csrf_input,
    "current_session_email": lambda: session.get("user_email", ""),
    "find_user_by_email": lambda email: find_user_by_email(email),
    "get_current_language": lambda user: get_current_language(user),
    "get_user_privacy": lambda email: get_user_privacy(email),
    "load_proofs": lambda: load_proofs(),
    "login_required": login_required,
    "normalize_email": normalize_email,
    "save_proofs": lambda data: save_proofs(data),
    "translation_bundle": translation_bundle,
    "update_user_privacy": lambda email, setting, value: update_user_privacy(email, setting, value),
    "validate_csrf_token": validate_csrf_token,
}))


app.register_blueprint(create_social_routes({
    "accept_friend_request": lambda viewer_email, profile_email: accept_friend_request(viewer_email, profile_email),
    "csrf_input": csrf_input,
    "create_social_notification": lambda target_email, text, notification_type="social", from_email="": create_social_notification(
        target_email,
        text,
        notification_type,
        from_email,
    ),
    "count_followers": lambda email: count_followers(email),
    "current_session_email": lambda: session.get("user_email", ""),
    "decline_friend_request": lambda viewer_email, profile_email: decline_friend_request(viewer_email, profile_email),
    "find_user_by_email": lambda email: find_user_by_email(email),
    "find_user_by_identifier": lambda identifier: find_user_by_identifier(identifier),
    "follow_user": lambda viewer_email, profile_email: follow_user(viewer_email, profile_email),
    "get_avatar_url": lambda email: get_avatar_url(email),
    "get_followers": lambda email: get_followers(email),
    "get_following": lambda email: get_following(email),
    "get_current_language": lambda user: get_current_language(user),
    "get_friend_requests": lambda email: get_friend_requests(email),
    "get_friends": lambda email: get_friends(email),
    "is_blocked": lambda one, two: is_blocked(one, two),
    "login_required": login_required,
    "log_security_event": lambda event_type, email="", details="": log_security_event(event_type, email, details),
    "normalize_email": normalize_email,
    "safe_text": safe_text,
    "send_friend_request": lambda viewer_email, profile_email: send_friend_request(viewer_email, profile_email),
    "simple_page": lambda title, message, email=None: simple_page(title, message, email),
    "translation_bundle": translation_bundle,
    "unfollow_user": lambda viewer_email, profile_email: unfollow_user(viewer_email, profile_email),
    "validate_csrf_token": validate_csrf_token,
    "update_friend_request_notification_status": lambda target_email, from_email, status: update_friend_request_notification_status(
        target_email,
        from_email,
        status,
    ),
}))


app.register_blueprint(create_notification_routes({
    "csrf_input": csrf_input,
    "current_session_email": lambda: session.get("user_email", ""),
    "find_user_by_email": lambda email: find_user_by_email(email),
    "find_user_by_identifier": lambda identifier: find_user_by_identifier(identifier),
    "get_avatar_url": lambda email: get_avatar_url(email),
    "get_current_language": lambda user: get_current_language(user),
    "get_notifications": lambda email: get_notifications(email),
    "login_required": login_required,
    "log_security_event": lambda event_type, email="", details="": log_security_event(event_type, email, details),
    "mark_notifications_read": lambda email: mark_notifications_read(email),
    "normalize_email": normalize_email,
    "safe_text": safe_text,
    "translation_bundle": translation_bundle,
}))


app.register_blueprint(create_settings_security_blueprint({
    "clean_text": clean_text,
    "clear_login_attempts": lambda email: clear_login_attempts(email),
    "create_verification_code": lambda purpose, contact_type, contact_value: create_verification_code(purpose, contact_type, contact_value),
    "csrf_input": csrf_input,
    "current_device_fingerprint": lambda: current_device_fingerprint(),
    "current_device_payload": lambda: current_device_payload(),
    "current_session_email": lambda: session.get("user_email", ""),
    "delete_account_data": lambda email: delete_account_data(email),
    "find_user_by_email": lambda email: find_user_by_email(email),
    "find_user_by_identifier": lambda identifier: find_user_by_identifier(identifier),
    "find_user_by_contact": lambda contact_type, contact_value: find_user_by_contact(contact_type, contact_value),
    "get_current_language": lambda user: get_current_language(user),
    "get_avatar_url": lambda email: get_avatar_url(email),
    "get_notifications": lambda email: get_notifications(email),
    "get_user_2fa_contact": lambda user: get_user_2fa_contact(user),
    "get_users": lambda: users,
    "login_required": login_required,
    "load_blocks": lambda: load_blocks(),
    "load_feed": lambda: load_feed(),
    "load_hidden_stories": lambda: load_hidden_stories(),
    "load_messages": lambda: load_messages(),
    "load_restrictions": lambda: load_restrictions(),
    "log_security_event": lambda event_type, email="", details="": log_security_event(event_type, email, details),
    "mask_contact_value": lambda contact_type, contact_value: mask_contact_value(contact_type, contact_value),
    "migrate_user_settings_email": lambda old_email, new_email: migrate_user_settings_email(old_email, new_email),
    "normalize_email": normalize_email,
    "normalize_phone": normalize_phone,
    "normalize_user_ai_settings": lambda email: normalize_user_ai_settings(email),
    "repository_load_user_ai_settings": lambda email: repository_load_user_ai_settings(email),
    "response_class": app.response_class,
    "rotate_user_session_version": lambda email: rotate_user_session_version(email),
    "safe_text": safe_text,
    "safe_account_payload": safe_account_payload,
    "save_account_deletion_snapshot": lambda email: save_account_deletion_snapshot(email),
    "save_user_ai_settings": lambda email, settings: save_user_ai_settings(email, settings),
    "save_users_to_json": lambda users_value: save_users_to_json(users_value),
    "security_event_display": security_event_display,
    "send_sensitive_action_code": lambda user, purpose: send_sensitive_action_code(user, purpose),
    "send_verification_code": lambda contact_type, contact_value, code: send_verification_code(contact_type, contact_value, code),
    "set_user_password": lambda user, raw_password: set_user_password(user, raw_password),
    "keep_only_trusted_device": lambda settings, current_device_id: device_security_service.keep_only_trusted_device(settings, current_device_id),
    "save_user_raw_settings": lambda email, settings: save_user_raw_settings(email, settings),
    "show_stories_from_user": lambda email, target_email: show_stories_from_user(email, target_email),
    "translation_bundle": lambda language: translation_bundle(language),
    "unblock_user_account": lambda email, target_email: unblock_user_account(email, target_email),
    "unrestrict_user_account": lambda email, target_email: unrestrict_user_account(email, target_email),
    "user_owns_settings_route": lambda route_email: user_owns_settings_route(route_email),
    "user_requires_sensitive_action_2fa": lambda user: user_requires_sensitive_action_2fa(user),
    "user_security_events": lambda email, limit=25: user_security_events(email, limit=limit),
    "users_from_email_list": lambda email_list: users_from_email_list(email_list),
    "validate_csrf_token": validate_csrf_token,
    "verify_contact_code": lambda purpose, contact_type, contact_value, code: verify_contact_code(purpose, contact_type, contact_value, code),
    "verify_sensitive_action_code": lambda user, purpose, code: verify_sensitive_action_code(user, purpose, code),
    "verify_user_password": lambda user, password: verify_user_password(user, password),
}))


class PrivateServerRequestHandler(WSGIRequestHandler):
    """Development-only handler which does not advertise Werkzeug/Python."""

    def send_response(self, code, message=None):
        self.log_request(code)
        self.send_response_only(code, message)
        self.send_header("Date", self.date_time_string())


if __name__ == "__main__":
    development_host = os.environ.get("APP_HOST", "127.0.0.1").strip() or "127.0.0.1"
    development_port = int(os.environ.get("APP_PORT", "5001"))
    print(f"NOVIX is available at http://{development_host}:{development_port}")
    app.run(
        host=development_host,
        debug=False,
        use_reloader=False,
        port=development_port,
        request_handler=PrivateServerRequestHandler,
    )
