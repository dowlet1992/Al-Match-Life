from flask import Flask, send_from_directory, request, redirect, render_template_string, session, abort, jsonify
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from twilio.rest import Client
import os
import json
import base64
import mimetypes
import secrets
import hashlib
import bleach
import smtplib
import urllib.parse
import urllib.request
import urllib.error
import ssl
from email.message import EmailMessage
from functools import wraps
from backend.social import follow_user, unfollow_user, is_following, send_friend_request, accept_friend_request, decline_friend_request, remove_friend, are_friends, has_friend_request, count_friends, count_followers, count_following, get_friends, get_followers, get_following, get_friend_requests, load_social, save_social
from datetime import datetime, timedelta
from backend.notifications import add_notification, get_notifications, load_notifications, save_notifications
from backend.messages import load_messages as repository_load_messages, save_messages as repository_save_messages
from backend.security_store import append_security_event, load_security_events as repository_load_security_events, load_login_attempts as repository_load_login_attempts, save_login_attempts as repository_save_login_attempts
from backend.social_safety_store import load_blocks as repository_load_blocks, load_hidden_stories as repository_load_hidden_stories, load_reports as repository_load_reports, load_restrictions as repository_load_restrictions, save_blocks as repository_save_blocks, save_hidden_stories as repository_save_hidden_stories, save_reports as repository_save_reports, save_restrictions as repository_save_restrictions
from backend.storage import save_users_to_json, load_users_from_json
from backend.stories_store import load_stories as repository_load_stories, save_stories as repository_save_stories
from backend.user_ai_settings_store import load_user_ai_settings as repository_load_user_ai_settings, save_user_ai_settings as repository_save_user_ai_settings
from backend.verification_store import load_verification_codes as repository_load_verification_codes, save_verification_codes as repository_save_verification_codes
from backend.language import get_translations
from backend.i18n import LANGUAGE_CATALOG, SUPPORTED_LANGUAGES, detect_language as detect_ui_language, translation_bundle
from backend.models import User
from backend.trust import calculate_trust_score
from backend.search import find_user_by_email_and_password
from backend.recommendations import find_best_matches
from backend.explanations import explain_match
from backend.match_level import get_match_level
from database.users_data import users
from backend.proof import load_proofs, save_proofs
from backend.privacy import get_user_privacy, update_user_privacy
from backend.realtime_status import load_presence_status as repository_load_presence_status, load_typing_status as repository_load_typing_status, save_presence_status as repository_save_presence_status, save_typing_status as repository_save_typing_status
from backend.feed import load_feed, save_feed
from backend.serializers import user_payload, post_payload, message_payload
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
from backend.api.i18n import create_i18n_api
from backend.api.system import system_api
from backend.api.auth import create_auth_api
from backend.api.profile import create_profile_api
from backend.api.feed import create_feed_api
from backend.api.messages import create_messages_api
from backend.api.social import create_social_api
from backend.api.notifications import create_notifications_api
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
from backend.config import is_admin_email
from backend.auth_tokens import DEFAULT_ACCESS_TOKEN_SECONDS, create_access_token as create_signed_access_token, verify_access_token
 

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
app.register_blueprint(system_api)
app.register_blueprint(create_i18n_api())
 
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "").strip()
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "").strip()
TWILIO_VERIFY_SERVICE_SID = os.environ.get("TWILIO_VERIFY_SERVICE_SID", "").strip()
twilio_client = None

if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN:
    twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
from backend.ai_engine import analyze_user_profile, explain_user_match, generate_feed_idea, analyze_proof_profile, generate_life_radar
from backend.ai_memory_store import load_ai_core_memory as repository_load_ai_core_memory, load_ai_feed_learning as repository_load_ai_feed_learning, save_ai_core_memory as repository_save_ai_core_memory, save_ai_feed_learning as repository_save_ai_feed_learning
from backend.call_signals_store import load_call_signals as repository_load_call_signals, save_call_signals as repository_save_call_signals
from backend.news_store import load_news as repository_load_news, save_news as repository_save_news
UPLOAD_FOLDER = "static/uploads"
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
        return True

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

        logged_user = find_user_by_email(logged_email)
        if logged_user is None:
            session.clear()
            return redirect("/")

        if not is_session_version_current(logged_user):
            log_security_event("stale_session_rejected", logged_user.email, "Session version is no longer current")
            session.clear()
            return redirect("/")

        if email and logged_email.strip().lower() != email.strip().lower():
            if request.path.startswith("/settings/"):
                abort(403)

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
    return repository_load_login_attempts()


def save_login_attempts(data):
    repository_save_login_attempts(data)


def load_security_events():
    return repository_load_security_events()


def user_owns_settings_route(route_email):
    return normalize_email(session.get("user_email", "")) == normalize_email(route_email)


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
    return f'<input type="hidden" name="csrf_token" value="{get_csrf_token()}">'



# --- Multilanguage helpers ---
# Interface and content language catalogs come from backend.i18n as the single source of truth.
CONTENT_LANGUAGES = dict(LANGUAGE_CATALOG)
CONTENT_LANGUAGES["unknown"] = "Unknown"

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


def normalize_language_code(language_value):
    return detect_ui_language(language_value, default=DEFAULT_LANGUAGE)


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
        ui = translation_bundle(get_current_language())
        return render_template_string(html, csrf_token_input=csrf_input(), ui=ui)

    return None


@app.errorhandler(403)
def forbidden_page(error):
    ui = translation_bundle(get_current_language())
    return f"""
    <html lang="{safe_text(ui.get('language_code', 'ru'))}" dir="{safe_text(ui.get('text_direction', 'ltr'))}">
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


def settings_control_css(max_width="720px"):
    return f"""
    <style>
        *{{box-sizing:border-box}}
        body{{margin:0;background:#0f172a;color:white;font-family:Arial,sans-serif;padding:28px;}}
        .page{{max-width:{max_width};margin:auto;}}
        .back{{display:inline-flex;align-items:center;background:#111827;border:1px solid rgba(148,163,184,0.14);color:white;text-decoration:none;border-radius:8px;padding:11px 14px;font-weight:900;margin-bottom:18px;}}
        .hero,.card,.row-card,.empty-state{{background:#1e293b;border:1px solid rgba(148,163,184,0.14);border-radius:8px;padding:22px;margin-bottom:14px;box-shadow:0 14px 34px rgba(0,0,0,0.16);}}
        .hero h1,.card h1{{margin:0 0 8px 0;font-size:30px;letter-spacing:0;}}
        .card h2{{margin:0 0 8px 0;font-size:21px;letter-spacing:0;}}
        p{{color:#cbd5e1;line-height:1.5;margin:0 0 12px 0;}}
        label{{display:block;color:#cbd5e1;font-weight:900;margin:14px 0 7px 0;}}
        input{{width:100%;background:#0f172a;color:white;border:1px solid #334155;border-radius:8px;padding:13px 14px;font-size:15px;outline:none;}}
        input:focus{{border-color:#60a5fa;box-shadow:0 0 0 3px rgba(96,165,250,0.14);}}
        button,.button-link{{display:inline-flex;align-items:center;justify-content:center;width:100%;margin-top:18px;background:#2563eb;color:white;border:none;border-radius:8px;padding:14px 16px;font-weight:900;cursor:pointer;text-decoration:none;}}
        button:hover,.button-link:hover{{background:#1d4ed8;}}
        .danger-button{{background:#b91c1c;}}
        .danger-button:hover{{background:#991b1b;}}
        .message{{color:#facc15;font-weight:900;}}
        .success{{color:#22c55e;}}
        .warning{{background:#450a0a;border:1px solid rgba(248,113,113,0.32);border-radius:8px;padding:14px;color:#fecaca;font-weight:900;margin:12px 0;}}
        .muted-card{{background:#111827;border:1px solid rgba(148,163,184,0.14);border-radius:8px;padding:16px;margin-top:12px;}}
        .row-card{{display:flex;align-items:center;justify-content:space-between;gap:14px;background:#111827;}}
        .row-card p{{margin:0;}}
        .row-card form{{margin:0;}}
        .row-card button{{width:auto;margin:0;padding:11px 13px;white-space:nowrap;}}
        .two-column{{display:grid;grid-template-columns:1fr 1fr;gap:14px;}}
        @media(max-width:680px){{body{{padding:18px}}.two-column{{grid-template-columns:1fr}}.row-card{{display:block}}.row-card button{{width:100%;margin-top:12px}}}}
    </style>
    """


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
    return repository_load_news()


def save_news(news_items):
    repository_save_news(news_items)


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


@app.route("/onboarding/<email>", methods=["GET", "POST"])
@login_required
def onboarding_page(email):
    user = find_user_by_email(email)

    if user is None:
        return "User not found", 404

    if request.method == "POST":
        validate_csrf_token()
        action = clean_text(request.form.get("action", "save"))

        if action == "skip":
            profile_service.skip_onboarding(user)
            save_users_to_json(users)
            log_security_event("onboarding_skipped", user.email, "User skipped optional onboarding")
            return redirect(f"/dashboard/{safe_text(user.email)}", code=303)

        save_onboarding_answers(user, request.form)
        log_security_event("onboarding_completed", user.email, "User completed optional onboarding")
        return redirect(f"/matches/{safe_text(user.email)}", code=303)

    ui = translation_bundle(get_current_language(user))
    ai_hint = analyze_user_profile(user)

    return f"""
    <!DOCTYPE html>
    <html lang="{safe_text(ui.get('language_code', 'ru'))}" dir="{safe_text(ui.get('text_direction', 'ltr'))}">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{safe_text(ui.get('onboarding_page_title', 'AI Match Life'))}</title>
        <style>
            @media (max-width: 640px) {{
                body {{ padding:16px !important; align-items:flex-start !important; }}
                main {{ border-radius:22px !important; padding:20px !important; }}
                .onboarding-head {{ align-items:flex-start !important; }}
                .onboarding-fields {{ grid-template-columns:1fr !important; }}
            }}
        </style>
    </head>
    <body style="margin:0;background:#0f172a;color:white;font-family:Arial,sans-serif;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:24px;">
        <main style="width:100%;max-width:620px;background:#1e293b;border:1px solid rgba(148,163,184,0.16);border-radius:30px;padding:28px;box-shadow:0 24px 80px rgba(0,0,0,0.36);">
            <div class="onboarding-head" style="display:flex;align-items:center;justify-content:space-between;gap:14px;margin-bottom:18px;">
                <div>
                    <h1 style="margin:0 0 8px 0;font-size:28px;">{safe_text(ui.get('onboarding_title', 'Quick start'))}</h1>
                    <p style="margin:0;color:#cbd5e1;line-height:1.5;">{safe_text(ui.get('onboarding_intro', ''))}</p>
                </div>
                <div style="background:#0f172a;border:1px solid rgba(96,165,250,0.22);border-radius:18px;padding:12px 14px;color:#93c5fd;font-weight:bold;white-space:nowrap;">AI</div>
            </div>

            <div style="background:#0f172a;border:1px solid rgba(148,163,184,0.12);border-radius:20px;padding:16px;margin-bottom:18px;color:#dbeafe;line-height:1.55;">
                {safe_text(ai_hint.get("summary", ui.get("onboarding_hint_default", "")))}
            </div>

            <form method="POST">
                {csrf_input()}

                <label style="display:block;color:#cbd5e1;font-weight:bold;margin:0 0 8px 0;">{safe_text(ui.get('looking_for_question', ''))}</label>
                <input name="looking_for" value="{safe_text(getattr(user, "looking_for", ""))}" placeholder="{safe_text(ui.get('looking_for_placeholder', ''))}" style="width:100%;box-sizing:border-box;background:#0f172a;color:white;border:1px solid #334155;border-radius:14px;padding:13px 14px;margin-bottom:14px;">

                <label style="display:block;color:#cbd5e1;font-weight:bold;margin:0 0 8px 0;">{safe_text(ui.get('profession_label', ''))}</label>
                <input name="profession" value="{safe_text(getattr(user, "profession", ""))}" placeholder="{safe_text(ui.get('profession_placeholder', ''))}" style="width:100%;box-sizing:border-box;background:#0f172a;color:white;border:1px solid #334155;border-radius:14px;padding:13px 14px;margin-bottom:14px;">

                <label style="display:block;color:#cbd5e1;font-weight:bold;margin:0 0 8px 0;">{safe_text(ui.get('goals_label', ''))}</label>
                <input name="goals" value="{safe_text(", ".join(getattr(user, "goals", []) or []))}" placeholder="{safe_text(ui.get('goals_placeholder', ''))}" style="width:100%;box-sizing:border-box;background:#0f172a;color:white;border:1px solid #334155;border-radius:14px;padding:13px 14px;margin-bottom:14px;">

                <label style="display:block;color:#cbd5e1;font-weight:bold;margin:0 0 8px 0;">{safe_text(ui.get('interests_label', ''))}</label>
                <input name="interests" value="{safe_text(", ".join(getattr(user, "interests", []) or []))}" placeholder="{safe_text(ui.get('interests_placeholder', ''))}" style="width:100%;box-sizing:border-box;background:#0f172a;color:white;border:1px solid #334155;border-radius:14px;padding:13px 14px;margin-bottom:14px;">

                <label style="display:block;color:#cbd5e1;font-weight:bold;margin:0 0 8px 0;">{safe_text(ui.get('skills_languages_label', ''))}</label>
                <div class="onboarding-fields" style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:18px;">
                    <input name="skills" value="{safe_text(", ".join(getattr(user, "skills", []) or []))}" placeholder="{safe_text(ui.get('skills_placeholder', ''))}" style="width:100%;box-sizing:border-box;background:#0f172a;color:white;border:1px solid #334155;border-radius:14px;padding:13px 14px;">
                    <input name="languages" value="{safe_text(", ".join(getattr(user, "languages", []) or []))}" placeholder="{safe_text(ui.get('languages_placeholder', ''))}" style="width:100%;box-sizing:border-box;background:#0f172a;color:white;border:1px solid #334155;border-radius:14px;padding:13px 14px;">
                </div>

                <button name="action" value="save" type="submit" style="width:100%;background:#2563eb;color:white;border:none;border-radius:16px;padding:14px 18px;font-weight:bold;cursor:pointer;margin-bottom:10px;">{safe_text(ui.get('show_my_ai_matches', 'AI Matches'))}</button>
                <button name="action" value="skip" type="submit" style="width:100%;background:#334155;color:white;border:none;border-radius:16px;padding:13px 18px;font-weight:bold;cursor:pointer;">{safe_text(ui.get('skip_now', 'Skip'))}</button>
            </form>
        </main>
    </body>
    </html>
    """


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
    ui = translation_bundle(get_current_language(user))
    user_settings = normalize_user_ai_settings(user.email)
    feed_autoplay_enabled = user_settings.get("autoplay_video", True) is True
    feed_video_status_text = "Автовидео" if feed_autoplay_enabled else "Нажмите ▶"

    feed_data = load_feed()
    posts = feed_data.get("posts", [])
    activity_count = sum(1 for post in posts if normalize_email(post.get("email", post.get("author_email", ""))) == normalize_email(user.email))

    posts_html = ""


    if posts:
        for post in reversed(posts):
            if not can_view_feed_post(user.email, post):
                continue

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
                            <div class="feed-video-status" style="position:absolute;left:12px;bottom:12px;background:rgba(15,23,42,0.65);color:white;border-radius:999px;padding:8px 12px;font-size:13px;font-weight:bold;">{safe_text(feed_video_status_text)}</div>
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
    const feedAutoplayEnabled = __FEED_AUTOPLAY_ENABLED__;

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

        if (!feedAutoplayEnabled) {
            videos.forEach(function(video) {
                video.dataset.userPaused = 'true';
                const status = video.parentElement.querySelector('.feed-video-status');
                if (status) status.innerText = 'Нажмите ▶';
            });
            return;
        }

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
    """.replace("__FEED_AUTOPLAY_ENABLED__", "true" if feed_autoplay_enabled else "false")

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

            if story_email not in connected_emails and not can_view_user_stories(user.email, story_email):
                continue

            story_user = find_user_by_email(story_email)
            if story_user is None:
                continue

            if not can_view_user_stories(user.email, story_user.email):
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
    admin_menu_html = ""
    if is_admin_email(user.email):
        admin_menu_html = (
            f'<a class="admin-link" href="/admin/moderation/{safe_text(user.email)}">'
            '<span class="menu-icon" aria-hidden="true"><svg viewBox="0 0 24 24">'
            '<path d="M12 3l8 4v5c0 5-3.4 8.2-8 9-4.6-.8-8-4-8-9V7l8-4z"/>'
            '<path d="M9 12l2 2 4-4"/></svg></span>'
            f'<span>{safe_text(ui.get("moderation", "Moderation"))}</span></a>'
        )

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
        ui=ui,
        avatar_url=get_avatar_url(user.email),
        notifications_count=notifications_count,
        matches_count=matches_count,
        friends_count=count_friends(user.email),
        followers_count=count_followers(user.email),
        following_count=count_following(user.email),
        admin_menu_html=admin_menu_html,
        csrf_token_input=csrf_input()
    ) 
  
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


def delete_account_data(email):
    normalized_email = normalize_email(email)
    global users

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

    call_signals = load_call_signals()
    if isinstance(call_signals, dict):
        save_call_signals({
            key: value for key, value in call_signals.items()
            if normalized_email not in key
        })


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
        ui.get(notification_key, "New login to your AI Match Life account."),
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


@app.route("/settings/<email>")
@login_required
def settings_page(email):
    user = find_user_by_email(email)

    if user is None:
        return "User not found"

    settings = normalize_user_ai_settings(user.email)
    html = open_html("settings.html")
    current_language = get_current_language(user)
    ui = translation_bundle(current_language)

    return render_template_string(
        html,
        email=safe_text(user.email),
        settings=settings,
        user=user,
        current_language=current_language,
        supported_languages=SUPPORTED_LANGUAGES,
        ui=ui,
        csrf_token_input=csrf_input()
    )


@app.route("/settings/<email>/privacy_ai", methods=["POST"])
@login_required
def update_privacy_ai_settings(email):
    validate_csrf_token()
    user = find_user_by_email(email)

    if user is None:
        return "User not found"

    new_settings, language = settings_form_service.parse_privacy_ai_form(
        request.form,
        normalize_language_code,
        SUPPORTED_LANGUAGES,
    )
    if language:
        user.language = language
        session["language"] = language
        save_users_to_json(users)

    save_user_ai_settings(user.email, new_settings)
    return redirect(f"/settings/{user.email}")


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
    return find_user_by_email(logged_email)


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
    "create_verification_code": lambda purpose, contact_type, contact_value: create_verification_code(purpose, contact_type, contact_value),
    "create_access_token": lambda email: create_signed_access_token(email, app.secret_key),
    "access_token_seconds": DEFAULT_ACCESS_TOKEN_SECONDS,
    "find_user_by_contact": lambda contact_type, contact_value: find_user_by_contact(contact_type, contact_value),
    "find_user_by_email": lambda email: find_user_by_email(email),
    "find_user_by_login": lambda login_value: find_user_by_login(login_value),
    "get_user_2fa_contact": lambda user: get_user_2fa_contact(user),
    "get_users": lambda: users,
    "is_account_verified": lambda user: is_account_verified(user),
    "is_login_temporarily_locked": lambda email: is_login_temporarily_locked(email),
    "log_security_event": lambda event_type, email="", details="": log_security_event(event_type, email, details),
    "make_internal_phone_email": lambda phone_value: make_internal_phone_email(phone_value),
    "mark_account_verified": lambda user, contact_type="email": mark_account_verified(user, contact_type),
    "normalize_email": normalize_email,
    "normalize_phone": normalize_phone,
    "onboarding_redirect_for": lambda user: onboarding_redirect_for(user),
    "parse_short_list": parse_short_list,
    "register_failed_login_attempt": lambda email: register_failed_login_attempt(email),
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
    "get_api_current_user": lambda: get_api_current_user(),
    "get_users": lambda: users,
    "normalize_user_ai_settings": lambda email: normalize_user_ai_settings(email),
    "privacy_service": privacy_service,
    "profile_service": profile_service,
    "save_onboarding_answers": lambda user, data: save_onboarding_answers(user, data),
    "save_user_ai_settings": lambda email, settings: save_user_ai_settings(email, settings),
    "save_users_to_json": lambda users_value: save_users_to_json(users_value),
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
}))


app.register_blueprint(create_messages_api({
    "api_message_payload": lambda message, current_email="": api_message_payload(message, current_email),
    "api_user_payload": lambda user: api_user_payload(user),
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
    "save_messages": lambda data: save_messages(data),
}))


app.register_blueprint(create_social_api({
    "clean_text": clean_text,
    "create_social_notification": lambda to_email, text, notification_type, from_email: create_social_notification(
        to_email,
        text,
        notification_type,
        from_email,
    ),
    "find_user_by_email": lambda email: find_user_by_email(email),
    "get_api_current_user": lambda: get_api_current_user(),
    "is_blocked": lambda one, two: is_blocked(one, two),
    "social_service": social_service,
    "update_friend_request_notification_status": lambda target_email, from_email, status: update_friend_request_notification_status(
        target_email,
        from_email,
        status,
    ),
}))


app.register_blueprint(create_notifications_api({
    "clean_text": clean_text,
    "get_api_current_user": lambda: get_api_current_user(),
    "get_notifications": lambda email: get_notifications(email),
    "normalize_email": normalize_email,
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
    "find_user_by_email": lambda email: find_user_by_email(email),
    "get_api_current_user": lambda: get_api_current_user(),
    "is_story_active": lambda story: is_story_active(story),
    "load_stories": lambda: load_stories(),
    "normalize_email": normalize_email,
    "save_stories": lambda data: save_stories(data),
}))


app.register_blueprint(create_admin_api({
    "clean_text": clean_text,
    "get_api_current_user": lambda: get_api_current_user(),
    "is_admin_email": lambda email: is_admin_email(email),
    "load_reports": lambda: load_reports(),
    "log_security_event": lambda event_type, email="", details="": log_security_event(event_type, email, details),
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
    "explain_match": lambda current_user, matched_user: explain_match(current_user, matched_user),
    "explain_user_match": lambda current_user, matched_user: explain_user_match(current_user, matched_user),
    "find_best_matches": lambda current_user, all_users: find_best_matches(current_user, all_users),
    "find_user_by_email": lambda email: find_user_by_email(email),
    "get_avatar_url": lambda email: get_avatar_url(email),
    "get_current_language": lambda user: get_current_language(user),
    "get_match_level": lambda score: get_match_level(score),
    "get_user_privacy": lambda email: get_user_privacy(email),
    "get_users": lambda: users,
    "is_account_deactivated": lambda user: is_account_deactivated(user),
    "is_blocked": lambda one, two: is_blocked(one, two),
    "is_restricted": lambda one, two: is_restricted(one, two),
    "login_required": login_required,
    "normalize_email": normalize_email,
    "normalize_user_ai_settings": lambda email: normalize_user_ai_settings(email),
    "open_html": lambda filename: open_html(filename),
    "safe_text": safe_text,
    "translation_bundle": lambda language: translation_bundle(language),
    "user_card": lambda user: user_card(user),
    "validate_csrf_token": validate_csrf_token,
}))


app.register_blueprint(create_media_routes({
    "allowed_extensions": lambda: ALLOWED_EXTENSIONS,
    "allowed_file": lambda filename: allowed_file(filename),
    "allowed_mime_type": lambda file: allowed_mime_type(file),
    "avatar_filename": lambda email, extension: avatar_filename(email, extension),
    "csrf_input": csrf_input,
    "find_user_by_email": lambda email: find_user_by_email(email),
    "get_avatar_url": lambda email: get_avatar_url(email),
    "login_required": login_required,
    "log_security_event": lambda event_type, email="", details="": log_security_event(event_type, email, details),
    "safe_text": safe_text,
    "secure_filename": secure_filename,
    "upload_folder": lambda: UPLOAD_FOLDER,
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
    "detect_content_language": lambda text: detect_content_language(text),
    "find_user_by_email": lambda email: find_user_by_email(email),
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
    "csrf_input": csrf_input,
    "default_language": lambda: DEFAULT_LANGUAGE,
    "detect_content_language": lambda text: detect_content_language(text),
    "find_user_by_email": lambda email: find_user_by_email(email),
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
    "validate_csrf_token": validate_csrf_token,
}))


app.register_blueprint(create_story_routes({
    "allowed_mime_type": lambda uploaded_file: allowed_mime_type(uploaded_file),
    "can_view_user_stories": lambda viewer_email, owner_email: can_view_user_stories(viewer_email, owner_email),
    "clean_text": clean_text,
    "find_user_by_email": lambda email: find_user_by_email(email),
    "get_avatar_url": lambda email: get_avatar_url(email),
    "is_blocked": lambda one, two: is_blocked(one, two),
    "is_story_active": lambda story: is_story_active(story),
    "load_stories": lambda: load_stories(),
    "login_required": login_required,
    "log_security_event": lambda event_type, email="", details="": log_security_event(event_type, email, details),
    "normalize_email": normalize_email,
    "safe_text": safe_text,
    "save_stories": lambda stories_data: save_stories(stories_data),
    "simple_page": lambda title, text, email: simple_page(title, text, email),
    "upload_folder": lambda: UPLOAD_FOLDER,
    "validate_csrf_token": validate_csrf_token,
}))


app.register_blueprint(create_profile_routes({
    "are_friends": lambda one, two: are_friends(one, two),
    "clean_text": clean_text,
    "count_followers": lambda email: count_followers(email),
    "count_following": lambda email: count_following(email),
    "find_user_by_email": lambda email: find_user_by_email(email),
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
    "hide_stories_from_user": lambda viewer_email, target_email: hide_stories_from_user(viewer_email, target_email),
    "login_required": login_required,
    "log_security_event": lambda event_type, email="", details="": log_security_event(event_type, email, details),
    "normalize_email": normalize_email,
    "restrict_user_account": lambda restrictor_email, restricted_email: restrict_user_account(restrictor_email, restricted_email),
    "safe_text": safe_text,
    "show_stories_from_user": lambda viewer_email, target_email: show_stories_from_user(viewer_email, target_email),
    "simple_page": lambda title, text, email: simple_page(title, text, email),
    "unblock_user_account": lambda blocker_email, blocked_email: unblock_user_account(blocker_email, blocked_email),
    "unrestrict_user_account": lambda restrictor_email, restricted_email: unrestrict_user_account(restrictor_email, restricted_email),
    "validate_csrf_token": validate_csrf_token,
}))


app.register_blueprint(create_admin_routes({
    "clean_text": clean_text,
    "csrf_input": csrf_input,
    "find_user_by_email": lambda email: find_user_by_email(email),
    "is_admin_email": lambda email: is_admin_email(email),
    "load_reports": lambda: load_reports(),
    "login_required": login_required,
    "log_security_event": lambda event_type, email="", details="": log_security_event(event_type, email, details),
    "moderation_service": moderation_service,
    "safe_text": safe_text,
    "save_reports": lambda reports_data: save_reports(reports_data),
    "simple_page": lambda title, text, email: simple_page(title, text, email),
    "validate_csrf_token": validate_csrf_token,
}))


app.register_blueprint(create_profile_misc_routes({
    "find_user_by_email": lambda email: find_user_by_email(email),
    "get_avatar_url": lambda email: get_avatar_url(email),
    "get_blocked_users": lambda email: get_blocked_users(email),
    "load_feed": lambda: load_feed(),
    "login_required": login_required,
    "safe_text": safe_text,
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
    "find_user_by_email": lambda email: find_user_by_email(email),
    "load_news": lambda: load_news(),
    "login_required": login_required,
    "log_security_event": lambda event_type, email="", details="": log_security_event(event_type, email, details),
    "normalize_email": normalize_email,
    "render_ai_text": render_ai_text,
    "safe_text": safe_text,
    "save_news": lambda news_items: save_news(news_items),
    "secure_filename": secure_filename,
    "upload_folder": lambda: UPLOAD_FOLDER,
    "validate_csrf_token": validate_csrf_token,
}))


app.register_blueprint(create_ai_core_routes({
    "clean_text": clean_text,
    "csrf_input": csrf_input,
    "find_user_by_email": lambda email: find_user_by_email(email),
    "generate_ai_copilot_answer": lambda user, question, mode="general": generate_ai_copilot_answer(user, question, mode),
    "get_openai_status": lambda: get_openai_status(),
    "normalize_email": normalize_email,
    "record_ai_core_memory": lambda user_email, mode, question, answer: record_ai_core_memory(user_email, mode, question, answer),
    "render_ai_core_history": lambda user_email, limit=12: render_ai_core_history(user_email, limit=limit),
    "render_ai_text": render_ai_text,
    "render_selected_ai_core_history": lambda user_email, history_index: render_selected_ai_core_history(user_email, history_index),
    "safe_text": safe_text,
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
    "open_html": lambda filename: open_html(filename),
    "page_style": page_style,
    "record_trusted_device_seen": lambda user: record_trusted_device_seen(user),
    "register_failed_login_attempt": lambda email: register_failed_login_attempt(email),
    "safe_text": safe_text,
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
    "get_users": lambda: users,
    "login_required": login_required,
    "log_security_event": lambda event_type, email="", details="": log_security_event(event_type, email, details),
    "normalize_email": normalize_email,
    "normalize_phone": normalize_phone,
    "onboarding_redirect_for": lambda user: onboarding_redirect_for(user),
    "page_style": page_style,
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
    safe_title = safe_text(title)
    safe_body = safe_text(text)
    safe_email = safe_text(email)

    return f"""
    <html lang="{safe_text(ui.get('language_code', 'ru'))}" dir="{safe_text(ui.get('text_direction', 'ltr'))}">
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
        "log_security_event": lambda event_type, email="", details="": log_security_event(event_type, email, details),
        "normalize_content_language_code": lambda value: normalize_content_language_code(value),
    })


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

@app.route("/messages/<email>")
@login_required
def messages_page(email):
    current_user = find_user_by_email(email)

    if current_user is None:
        return "User not found"

    ui = translation_bundle(get_current_language(current_user))

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

        other_user = find_user_by_email(other_email)
        if other_user is None:
            continue

        if is_blocked(current_user.email, other_user.email) or is_blocked(other_user.email, current_user.email):
            continue

        if is_restricted(current_user.email, other_user.email) or is_restricted(other_user.email, current_user.email):
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
                    {safe_text(ui.get("open_chat", "Open chat"))}
                </a>
            </div>
            """
    else:
        dialogs_html = f"""
        <div style="background:#1e293b;padding:24px;border-radius:22px;color:#cbd5e1;text-align:center;">
            {safe_text(ui.get("no_active_dialogs", "No active conversations yet."))}
        </div>
        """

    users_html = ""

    for user in users:
        if user.email.strip().lower() == current_user.email.strip().lower():
            continue
        if is_blocked(current_user.email, user.email) or is_blocked(user.email, current_user.email):
            continue

        if is_restricted(current_user.email, user.email) or is_restricted(user.email, current_user.email):
            continue

        avatar_url = get_avatar_url(user.email)
        can_write, block_title, block_text = get_message_permission_status(current_user, user)

        if can_write:
            message_action_html = f"""
            <a href="/chat/{safe_text(current_user.email)}/{safe_text(user.email)}" style="background:#16a34a;color:white;text-decoration:none;padding:10px 14px;border-radius:14px;font-weight:bold;white-space:nowrap;">
                {safe_text(ui.get("write_message", "Write"))}
            </a>
            """
            permission_note_html = ""
        else:
            message_action_html = f"""
            <span title="{safe_text(block_text)}" style="background:#475569;color:#cbd5e1;text-decoration:none;padding:10px 14px;border-radius:14px;font-weight:bold;cursor:not-allowed;white-space:nowrap;">
                {safe_text(ui.get("unavailable", "Unavailable"))}
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
    <html lang="{safe_text(ui.get('language_code', 'ru'))}" dir="{safe_text(ui.get('text_direction', 'ltr'))}">
    <head>
        <meta charset="UTF-8">
        <title>{safe_text(ui.get("messages", "Messages"))} - AI Match Life</title>
    </head>

    <body style="margin:0;background:#0f172a;color:white;font-family:Arial,sans-serif;padding:32px;">
        <div style="max-width:920px;margin:auto;">

            <a href="/dashboard/{safe_text(current_user.email)}" style="display:inline-block;color:white;text-decoration:none;background:#334155;padding:12px 16px;border-radius:14px;margin-bottom:18px;font-weight:bold;">
                ← {safe_text(ui.get("back", "Back"))}
            </a>

            <div style="background:#1e293b;padding:28px;border-radius:26px;margin-bottom:22px;">
                <h1 style="margin:0;">💬 {safe_text(ui.get("messages", "Messages"))}</h1>
                <p style="color:#cbd5e1;margin-bottom:0;">{safe_text(ui.get("messages_intro", "Active conversations and new contacts."))}</p>
            </div>

            <h2>{safe_text(ui.get("active_dialogs", "Active conversations"))}</h2>
            {dialogs_html}

            <h2 style="margin-top:30px;">{safe_text(ui.get("new_conversation", "New conversation"))}</h2>
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


def get_call_room_id(email_one, email_two, call_type):
    participants = sorted([normalize_email(email_one), normalize_email(email_two)])
    raw_room = "__".join(participants + [clean_text(call_type)])
    return secure_filename(raw_room.replace("@", "_at_").replace(".", "_"))


def load_call_signals():
    return repository_load_call_signals()


def save_call_signals(data):
    repository_save_call_signals(data)


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

def find_pending_call_for_chat(current_email, other_email):
    current_email = normalize_email(current_email)
    other_email = normalize_email(other_email)
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
                room["messages"].append({
                    "id": secrets.token_urlsafe(10),
                    "type": "missed",
                    "from": other_email,
                    "to": current_email,
                    "payload": {"call_type": call_type, "missed_at": datetime.now().isoformat()},
                    "created_at": datetime.now().timestamp()
                })
                room["messages"] = room["messages"][-300:]
                room["status"] = "missed"
                room["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                signals_data[call_id] = room
                save_call_signals(signals_data)
                record_call_chat_event(other_email, current_email, call_type, "missed")
                continue

            if latest_pending is None or created_at > latest_pending.get("created_at", 0):
                latest_pending = {
                    "call_id": secure_filename(call_id),
                    "call_type": call_type,
                    "created_at": created_at
                }

    return latest_pending


@app.route("/pending_call/<current_email>/<other_email>")
@login_required
def pending_call(current_email, other_email):
    current_user = find_user_by_email(current_email)
    other_user = find_user_by_email(other_email)

    if current_user is None or other_user is None:
        return {"ok": False, "pending": False}

    if is_blocked(current_user.email, other_user.email) or is_blocked(other_user.email, current_user.email):
        return {"ok": True, "pending": False}

    if is_restricted(current_user.email, other_user.email) or is_restricted(other_user.email, current_user.email):
        return {"ok": True, "pending": False}

    pending = find_pending_call_for_chat(current_user.email, other_user.email)
    if not pending:
        return {"ok": True, "pending": False}

    call_type = pending.get("call_type", "audio")
    accept_url = f"/{call_type}_call/{safe_text(current_user.email)}/{safe_text(other_user.email)}?mode=receiver"
    decline_url = f"/decline_call/{safe_text(current_user.email)}/{safe_text(other_user.email)}/{safe_text(call_type)}"

    return {
        "ok": True,
        "pending": True,
        "call_id": pending.get("call_id", ""),
        "call_type": call_type,
        "caller_name": safe_text(other_user.name),
        "caller_avatar": get_avatar_url(other_user.email),
        "accept_url": accept_url,
        "decline_url": decline_url
    }


@app.route("/decline_call/<current_email>/<other_email>/<call_type>", methods=["POST", "GET"])
@login_required
def decline_call(current_email, other_email, call_type):
    current_user = find_user_by_email(current_email)
    other_user = find_user_by_email(other_email)

    if current_user is None or other_user is None:
        return {"ok": False, "error": "user_not_found"}, 404

    call_type = clean_text(call_type)
    if call_type not in {"audio", "video"}:
        call_type = "audio"

    call_id = get_call_room_id(current_user.email, other_user.email, call_type)
    signals_data = load_call_signals()
    room = signals_data.get(call_id, {"messages": [], "status": "active", "updated_at": ""})
    if not isinstance(room, dict):
        room = {"messages": [], "status": "active", "updated_at": ""}
    if not isinstance(room.get("messages"), list):
        room["messages"] = []

    room["messages"].append({
        "id": secrets.token_urlsafe(10),
        "type": "declined",
        "from": normalize_email(current_user.email),
        "to": normalize_email(other_user.email),
        "payload": {"declined_at": datetime.now().isoformat()},
        "created_at": datetime.now().timestamp()
    })
    room["messages"] = room["messages"][-300:]
    room["status"] = "declined"
    room["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    signals_data[call_id] = room
    save_call_signals(signals_data)
    record_call_chat_event(other_user.email, current_user.email, call_type, "declined")

    if request.method == "GET":
        return redirect(f"/chat/{current_user.email}/{other_user.email}")

    return {"ok": True}


@app.route("/call_signal/<call_id>", methods=["GET", "POST"])
@login_required
def call_signal(call_id):
    call_id = secure_filename(call_id)
    signals_data = load_call_signals()
    room = signals_data.get(call_id, {"messages": [], "status": "active", "updated_at": ""})

    if not isinstance(room, dict):
        room = {"messages": [], "status": "active", "updated_at": ""}

    if not isinstance(room.get("messages"), list):
        room["messages"] = []

    if request.method == "POST":
        payload = request.get_json(silent=True) or {}
        signal_type = clean_text(payload.get("type", ""))
        sender_email = normalize_email(payload.get("from", ""))
        receiver_email = normalize_email(payload.get("to", ""))
        signal_payload = payload.get("payload", {})

        allowed_types = {"offer", "answer", "ice", "ringing", "accepted", "declined", "ended", "missed"}
        if signal_type not in allowed_types:
            return {"ok": False, "error": "invalid_signal_type"}, 400

        if not sender_email or not receiver_email:
            return {"ok": False, "error": "missing_participants"}, 400

        if is_blocked(sender_email, receiver_email) or is_blocked(receiver_email, sender_email):
            return {"ok": False, "error": "blocked"}, 403

        if is_restricted(sender_email, receiver_email) or is_restricted(receiver_email, sender_email):
            log_security_event("call_signal_restricted", sender_email, f"Restricted call signal to {receiver_email}")
            return {"ok": False, "error": "restricted"}, 403

        now_timestamp = datetime.now().timestamp()
        room["messages"].append({
            "id": secrets.token_urlsafe(10),
            "type": signal_type,
            "from": sender_email,
            "to": receiver_email,
            "payload": signal_payload,
            "created_at": now_timestamp
        })
        room["messages"] = room["messages"][-300:]
        room["status"] = signal_type if signal_type in {"declined", "ended"} else "active"
        room["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        signals_data[call_id] = room
        save_call_signals(signals_data)

        if signal_type in {"ended", "declined"}:
            call_type = clean_text(signal_payload.get("call_type", "")) if isinstance(signal_payload, dict) else ""
            if call_type not in {"audio", "video"}:
                call_type = "video" if "video" in call_id else "audio"

            duration_seconds = 0
            if signal_type == "ended":
                accepted_times = []
                for signal_message in room.get("messages", []):
                    if clean_text(signal_message.get("type", "")) == "accepted":
                        try:
                            accepted_times.append(float(signal_message.get("created_at", 0) or 0))
                        except Exception:
                            continue
                if accepted_times:
                    duration_seconds = max(0, now_timestamp - max(accepted_times))

            record_call_chat_event(sender_email, receiver_email, call_type, signal_type, duration_seconds)

        return {"ok": True}

    current_user_email = normalize_email(request.args.get("user", ""))
    after = clean_text(request.args.get("after", "0"))
    try:
        after_value = float(after)
    except Exception:
        after_value = 0

    messages = []
    for message in room.get("messages", []):
        if float(message.get("created_at", 0) or 0) <= after_value:
            continue
        if current_user_email and normalize_email(message.get("from", "")) == current_user_email:
            continue
        messages.append(message)

    return {
        "ok": True,
        "status": room.get("status", "active"),
        "messages": messages,
        "server_time": datetime.now().timestamp()
    }


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

    if is_restricted(receiver.email, sender.email) or is_restricted(sender.email, receiver.email):
        log_security_event("call_restricted", sender.email, f"Restricted audio call attempt to {receiver.email}")
        return simple_page(
            "Звонок недоступен",
            "Звонок невозможен, потому что один из пользователей ограничил связь.",
            sender.email
        )

    call_role = clean_text(request.args.get("mode", "caller"))
    if call_role not in {"caller", "receiver"}:
        call_role = "caller"

    return render_call_page(sender, receiver, "audio", call_role)


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

    if is_restricted(receiver.email, sender.email) or is_restricted(sender.email, receiver.email):
        log_security_event("call_restricted", sender.email, f"Restricted video call attempt to {receiver.email}")
        return simple_page(
            "Звонок недоступен",
            "Звонок невозможен, потому что один из пользователей ограничил связь.",
            sender.email
        )

    call_role = clean_text(request.args.get("mode", "caller"))
    if call_role not in {"caller", "receiver"}:
        call_role = "caller"

    return render_call_page(sender, receiver, "video", call_role)


def render_call_page(sender, receiver, call_type, call_role="caller"):
    is_video = call_type == "video"
    title = "Видеозвонок" if is_video else "Аудиозвонок"
    icon = "🎥" if is_video else "📞"
    receiver_avatar = get_avatar_url(receiver.email)
    sender_avatar = get_avatar_url(sender.email)
    call_id = get_call_room_id(sender.email, receiver.email, call_type)
    need_video = "true" if is_video else "false"
    is_caller = "true" if call_role == "caller" else "false"

    if is_video:
        main_area = f"""
        <div class="video-stage">
            <video id="remoteVideo" autoplay playsinline></video>
            <div class="remote-fallback" id="remoteFallback">
                <div class="remote-avatar-wrap">
                    <img src="{receiver_avatar}" alt="Receiver">
                </div>
                <h2>{safe_text(receiver.name)}</h2>
                <p id="callStatus">Звонок...</p>
            </div>
            <video id="localVideo" autoplay playsinline muted></video>
        </div>
        """
        camera_button = '<button type="button" id="cameraBtn" class="call-control" onclick="toggleCamera()" title="Камера"><span class="control-icon">🎥</span></button>'
        flip_button = '<button type="button" id="flipBtn" class="call-control" onclick="flipCamera()" title="Перевернуть камеру"><span class="control-icon">🔄</span></button>'
    else:
        main_area = f"""
        <div class="audio-card">
            <div class="call-avatar-ring">
                <img src="{receiver_avatar}" alt="Receiver">
            </div>
            <h2>{safe_text(receiver.name)}</h2>
            <p id="callStatus">Звонок...</p>
            <audio id="remoteAudio" autoplay playsinline></audio>
        </div>
        """
        camera_button = ""
        flip_button = ""

    speaker_button = '<button type="button" id="speakerBtn" class="call-control" onclick="toggleSpeaker()" title="Динамик"><span class="control-icon" id="speakerIcon">🔊</span></button>'

    return f"""
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0">
        <title>{title}</title>
        <style>
            *{{box-sizing:border-box}}
            body{{margin:0;background:#020617;color:white;font-family:Arial,sans-serif;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:18px;}}
            .call-shell{{width:100%;max-width:980px;min-height:720px;background:linear-gradient(145deg,#020617,#0f172a 45%,#111827);border-radius:34px;padding:22px;box-shadow:0 28px 90px rgba(0,0,0,0.50);border:1px solid rgba(148,163,184,0.14);display:flex;flex-direction:column;}}
            .call-top{{display:flex;align-items:center;justify-content:space-between;gap:16px;margin-bottom:16px;}}
            .call-user{{display:flex;align-items:center;gap:13px;}}
            .call-user img{{width:54px;height:54px;border-radius:50%;object-fit:cover;border:3px solid rgba(255,255,255,0.16);}}
            .call-top h1{{margin:0;font-size:24px;}}
            .call-top p{{margin:5px 0 0;color:#cbd5e1;font-size:14px;}}
            .back-link{{background:rgba(51,65,85,0.92);color:white;text-decoration:none;padding:11px 14px;border-radius:14px;font-weight:bold;}}
            .video-stage{{position:relative;flex:1;min-height:520px;background:#000;border-radius:30px;overflow:hidden;border:1px solid rgba(148,163,184,0.14);}}
            #remoteVideo{{width:100%;height:100%;min-height:520px;object-fit:cover;background:#000;display:block;}}
            #localVideo{{position:absolute;right:18px;bottom:18px;width:190px;height:250px;border-radius:24px;object-fit:cover;background:#0f172a;border:2px solid rgba(255,255,255,0.22);box-shadow:0 18px 50px rgba(0,0,0,0.45);z-index:5;}}
            .remote-fallback{{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;background:radial-gradient(circle at top,#1e3a8a 0,#020617 58%);z-index:3;}}
            .remote-fallback.connected{{display:none;}}
            .remote-avatar-wrap{{width:136px;height:136px;border-radius:50%;padding:4px;background:linear-gradient(135deg,#22c55e,#2563eb,#8b5cf6,#ec4899);margin-bottom:16px;box-shadow:0 0 70px rgba(37,99,235,0.36);}}
            .remote-avatar-wrap img{{width:100%;height:100%;border-radius:50%;object-fit:cover;border:4px solid #020617;}}
            .audio-card{{flex:1;min-height:520px;background:radial-gradient(circle at top,#1e3a8a 0,#020617 58%);border-radius:30px;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;border:1px solid rgba(148,163,184,0.14);}}
            .call-avatar-ring{{width:168px;height:168px;border-radius:50%;padding:5px;background:linear-gradient(135deg,#22c55e,#2563eb,#8b5cf6,#ec4899);margin-bottom:20px;box-shadow:0 0 76px rgba(99,102,241,0.38);animation:pulseRing 1.8s infinite;}}
            .call-avatar-ring img{{width:100%;height:100%;border-radius:50%;object-fit:cover;border:5px solid #020617;}}
            @keyframes pulseRing{{0%{{transform:scale(1);}}50%{{transform:scale(1.035);}}100%{{transform:scale(1);}}}}
            .controls{{display:flex;gap:14px;flex-wrap:wrap;justify-content:center;align-items:center;margin-top:18px;}}
            .call-control,.end-call{{border:none;text-decoration:none;color:white;background:rgba(51,65,85,0.94);border-radius:999px;width:68px;height:68px;padding:0;font-weight:bold;cursor:pointer;text-align:center;display:flex;align-items:center;justify-content:center;font-size:24px;box-shadow:0 16px 38px rgba(0,0,0,0.32);transition:0.18s ease;}}
            .call-control:hover,.end-call:hover{{transform:translateY(-2px);background:#475569;}}
            .control-icon{{display:block;font-size:25px;line-height:1;}}
            .end-call{{background:#dc2626!important;}}
            .end-call:hover{{background:#ef4444!important;}}
            .call-control.off{{background:#f8fafc!important;color:#020617!important;}}
            .call-note{{margin-top:12px;color:#94a3b8;text-align:center;font-size:14px;line-height:1.5;min-height:20px;}}
            @media(max-width:800px){{body{{padding:0}}.call-shell{{min-height:100vh;border-radius:0;padding:14px}}.call-top h1{{font-size:20px}}.back-link{{font-size:13px;padding:9px 11px}}.video-stage,#remoteVideo,.audio-card{{min-height:calc(100vh - 190px)}}#localVideo{{width:118px;height:158px;right:12px;bottom:12px;border-radius:18px}}.call-control,.end-call{{width:62px;height:62px}}}}
        </style>
    </head>
    <body onload="startCall()">
        <div class="call-shell">
            <div class="call-top">
                <div class="call-user">
                    <img src="{sender_avatar}" alt="Sender">
                    <div>
                        <h1>{icon} {title}</h1>
                        <p>{safe_text(sender.name)} → {safe_text(receiver.name)}</p>
                    </div>
                </div>
                <a class="back-link" href="/chat/{safe_text(sender.email)}/{safe_text(receiver.email)}">← Назад в чат</a>
            </div>

            {main_area}

            <div class="controls">
                <button type="button" id="muteBtn" class="call-control" onclick="toggleMute()" title="Микрофон"><span class="control-icon" id="muteIcon">🎙️</span></button>
                {speaker_button}
                {camera_button}
                {flip_button}
                <button type="button" class="end-call" onclick="endCall()" title="Завершить звонок"><span class="control-icon">📵</span></button>
            </div>

            <div class="call-note" id="callNote"></div>
        </div>

        <script>
            let localStream = null;
            let peerConnection = null;
            let speakerOn = true;
            let cameraFacing = 'user';
            let pollingTimer = null;
            let lastSignalTime = 0;
            let callStartedAt = null;
            let callTimer = null;
            const needVideo = {need_video};
            const isCaller = {is_caller};
            const callId = "{call_id}";
            const currentUser = "{safe_text(sender.email)}";
            const otherUser = "{safe_text(receiver.email)}";
            const chatUrl = "/chat/{safe_text(sender.email)}/{safe_text(receiver.email)}";
            const signalingUrl = "/call_signal/" + encodeURIComponent(callId);
            const rtcConfig = {{ iceServers: [{{ urls: 'stun:stun.l.google.com:19302' }}, {{ urls: 'stun:stun1.l.google.com:19302' }}] }};

            function setStatus(text) {{
                const status = document.getElementById('callStatus');
                const note = document.getElementById('callNote');
                if (status) status.innerText = text;
                if (note) note.innerText = text;
            }}

            function setConnected() {{
                const fallback = document.getElementById('remoteFallback');
                if (fallback) fallback.classList.add('connected');
                if (!callStartedAt) {{
                    callStartedAt = Date.now();
                    callTimer = setInterval(function() {{
                        const seconds = Math.floor((Date.now() - callStartedAt) / 1000);
                        const minutes = String(Math.floor(seconds / 60)).padStart(2, '0');
                        const rest = String(seconds % 60).padStart(2, '0');
                        setStatus('Идёт звонок · ' + minutes + ':' + rest);
                    }}, 1000);
                }}
            }}

            async function sendSignal(type, payload) {{
                await fetch(signalingUrl, {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ type: type, from: currentUser, to: otherUser, payload: payload || {{}} }})
                }}).catch(function(error) {{ console.warn('signal send failed', error); }});
            }}

            async function pollSignals() {{
                try {{
                    const response = await fetch(signalingUrl + '?user=' + encodeURIComponent(currentUser) + '&after=' + encodeURIComponent(lastSignalTime));
                    const data = await response.json();

                    if (data.status === 'ended' || data.status === 'declined') {{
                        stopEverything();
                        window.location.href = chatUrl;
                        return;
                    }}

                    if (data.server_time) lastSignalTime = Math.max(lastSignalTime, Number(data.server_time) - 1);

                    for (const message of data.messages || []) {{
                        if (message.created_at) lastSignalTime = Math.max(lastSignalTime, Number(message.created_at));
                        await handleSignal(message);
                    }}
                }} catch (error) {{
                    console.warn('signal poll failed', error);
                }}
            }}

            async function handleSignal(message) {{
                if (!peerConnection) return;
                const type = message.type;
                const payload = message.payload || {{}};

                if (type === 'offer') {{
                    setStatus('Соединение...');
                    await peerConnection.setRemoteDescription(new RTCSessionDescription(payload));
                    const answer = await peerConnection.createAnswer();
                    await peerConnection.setLocalDescription(answer);
                    await sendSignal('answer', answer);
                }} else if (type === 'answer') {{
                    if (!peerConnection.currentRemoteDescription) {{
                        await peerConnection.setRemoteDescription(new RTCSessionDescription(payload));
                    }}
                }} else if (type === 'ice') {{
                    if (payload && payload.candidate) {{
                        await peerConnection.addIceCandidate(new RTCIceCandidate(payload)).catch(function(error) {{ console.warn('ice failed', error); }});
                    }}
                }} else if (type === 'ended' || type === 'declined') {{
                    stopEverything();
                    window.location.href = chatUrl;
                }}
            }}

            async function startCall() {{
                try {{
                    setStatus('Запрос доступа к камере/микрофону...');
                    if (localStream) localStream.getTracks().forEach(track => track.stop());

                    const constraints = needVideo ? {{ audio: true, video: {{ facingMode: cameraFacing }} }} : {{ audio: true, video: false }};
                    localStream = await navigator.mediaDevices.getUserMedia(constraints);

                    const localVideo = document.getElementById('localVideo');
                    if (localVideo) localVideo.srcObject = localStream;

                    peerConnection = new RTCPeerConnection(rtcConfig);

                    localStream.getTracks().forEach(function(track) {{
                        peerConnection.addTrack(track, localStream);
                    }});

                    peerConnection.ontrack = function(event) {{
                        const remoteStream = event.streams[0];
                        const remoteVideo = document.getElementById('remoteVideo');
                        const remoteAudio = document.getElementById('remoteAudio');
                        if (remoteVideo) remoteVideo.srcObject = remoteStream;
                        if (remoteAudio) remoteAudio.srcObject = remoteStream;
                        setConnected();
                    }};

                    peerConnection.onicecandidate = function(event) {{
                        if (event.candidate) sendSignal('ice', event.candidate);
                    }};

                    peerConnection.onconnectionstatechange = function() {{
                        if (!peerConnection) return;
                        const state = peerConnection.connectionState;
                        if (state === 'connected') setConnected();
                        if (state === 'failed') setStatus('Соединение не удалось. Нужен TURN-сервер для стабильной связи.');
                        if (state === 'disconnected') setStatus('Соединение прервано...');
                        if (state === 'closed') setStatus('Звонок завершён');
                    }};

                    if (isCaller) {{
                        setStatus('Звонок... Ожидаем ответа.');
                        await sendSignal('ringing', {{ call_type: needVideo ? 'video' : 'audio' }});

                        const offer = await peerConnection.createOffer();
                        await peerConnection.setLocalDescription(offer);
                        await sendSignal('offer', offer);
                    }} else {{
                        setStatus('Подключение к входящему звонку...');
                        await sendSignal('accepted', {{ accepted_at: new Date().toISOString(), call_type: needVideo ? 'video' : 'audio' }});
                    }}

                    pollingTimer = setInterval(pollSignals, 1000);
                    await pollSignals();
                }} catch (error) {{
                    console.error(error);
                    setStatus('Нет доступа к микрофону/камере или устройство недоступно.');
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
                    if (track.enabled) {{ if (cameraBtn) cameraBtn.classList.remove('off'); }}
                    else {{ if (cameraBtn) cameraBtn.classList.add('off'); }}
                }});
            }}

            function toggleSpeaker() {{
                const speakerBtn = document.getElementById('speakerBtn');
                const speakerIcon = document.getElementById('speakerIcon');
                speakerOn = !speakerOn;
                const mediaElements = [document.getElementById('remoteVideo'), document.getElementById('remoteAudio')].filter(Boolean);
                mediaElements.forEach(function(element) {{ element.muted = !speakerOn; }});
                if (speakerOn) {{
                    if (speakerBtn) speakerBtn.classList.remove('off');
                    if (speakerIcon) speakerIcon.innerText = '🔊';
                }} else {{
                    if (speakerBtn) speakerBtn.classList.add('off');
                    if (speakerIcon) speakerIcon.innerText = '🔈';
                }}
            }}

            async function flipCamera() {{
                if (!needVideo || !localStream || !peerConnection) return;
                cameraFacing = cameraFacing === 'user' ? 'environment' : 'user';
                const newStream = await navigator.mediaDevices.getUserMedia({{ audio: true, video: {{ facingMode: cameraFacing }} }});
                const newVideoTrack = newStream.getVideoTracks()[0];
                const oldVideoTrack = localStream.getVideoTracks()[0];
                if (oldVideoTrack) oldVideoTrack.stop();
                localStream.removeTrack(oldVideoTrack);
                localStream.addTrack(newVideoTrack);
                const senderTrack = peerConnection.getSenders().find(item => item.track && item.track.kind === 'video');
                if (senderTrack) senderTrack.replaceTrack(newVideoTrack);
                const localVideo = document.getElementById('localVideo');
                if (localVideo) localVideo.srcObject = localStream;
            }}

            function stopEverything() {{
                if (pollingTimer) clearInterval(pollingTimer);
                if (callTimer) clearInterval(callTimer);
                if (localStream) localStream.getTracks().forEach(track => track.stop());
                if (peerConnection) peerConnection.close();
                localStream = null;
                peerConnection = null;
            }}

            async function endCall() {{
                await sendSignal('ended', {{ ended_at: new Date().toISOString(), call_type: needVideo ? 'video' : 'audio' }});
                stopEverything();
                window.location.href = chatUrl;
            }}

            window.addEventListener('beforeunload', function() {{
                if (localStream) localStream.getTracks().forEach(track => track.stop());
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

    ui = translation_bundle(get_current_language(sender))

    can_write, block_title, block_text = get_message_permission_status(sender, receiver)
    if not can_write:
        log_security_event("chat_permission_blocked", sender.email, f"Blocked chat attempt to {receiver.email}: {block_title}")
        return simple_page(block_title, block_text, sender.email)

    sender_restricted_receiver = is_restricted(sender.email, receiver.email)
    receiver_restricted_sender = is_restricted(receiver.email, sender.email)

    if receiver_restricted_sender:
        log_security_event("chat_restricted_blocked", sender.email, f"Restricted chat attempt to {receiver.email}")
        return simple_page(
            ui.get("messages_unavailable", "Messages unavailable"),
            ui.get("messages_restricted_intro", "This user limited communication with you."),
            sender.email
        )

    restriction_notice_html = ""
    if sender_restricted_receiver:
        restriction_notice_html = f"""
        <div class="restriction-notice">
            <div>
                <strong>{safe_text(ui.get("restricted_user", "Restricted user"))}</strong>
                <p>{safe_text(ui.get("restricted_user_notice", "Their new messages should not arrive as regular notifications. You can remove the restriction at any time."))}</p>
            </div>
            <a href="/unrestrict_user/{safe_text(sender.email)}/{safe_text(receiver.email)}">{safe_text(ui.get("unrestrict", "Unrestrict"))}</a>
        </div>
        """

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
    receiver_status_text = format_visible_last_seen(sender.email, receiver.email, presence_data.get(receiver.email))
    typing_status_text = f"✍️ {safe_text(ui.get('typing_message', 'typing...'))}"


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
        pinned_text = safe_text(last_pinned.get("message", ui.get("media_file", "Media file")))
        pinned_html = f"""
        <div class="pinned-box" onclick="scrollToMessage('{last_pinned.get('id')}')">
            <div>
                <strong>📌 {safe_text(ui.get("pinned", "Pinned"))}</strong>
                <p>{pinned_text}</p>
            </div>
            <a href="/unpin_message/{sender.email}/{receiver.email}/{last_pinned.get('id')}" onclick="event.stopPropagation()">{safe_text(ui.get("unpin", "Unpin"))}</a>
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
                <div style="font-weight:bold;margin-bottom:8px;">🎤 {safe_text(ui.get("voice_message", "Voice message"))}</div>
                <audio controls style="width:100%;">
                    <source src="{media_url}">
                </audio>
            </div>
            """
        elif media_type == "call_event" or msg.get("message_type") == "call_event":
            call_type = clean_text(msg.get("call_type", "audio"))
            call_event = clean_text(msg.get("call_event", "ended"))
            call_icon = "🎥" if call_type == "video" else "📞"
            call_title = ui.get("video_call", "Video call") if call_type == "video" else ui.get("audio_call", "Audio call")

            if call_event == "missed":
                call_status = ui.get("call_missed", "Missed")
            elif call_event == "declined":
                call_status = ui.get("call_declined", "Declined")
            elif call_event == "ended":
                call_status = ui.get("call_ended", "Ended")
            elif call_event == "accepted":
                call_status = ui.get("call_accepted", "Accepted")
            else:
                call_status = ui.get("call", "Call")

            call_duration = clean_text(msg.get("call_duration_text", ""))
            call_time = safe_text(msg.get("time", ""))
            call_meta = call_time
            if call_duration:
                call_meta = f"{call_time} · {safe_text(call_duration)}"

            media_html = f"""
            <div class="call-event-card">
                <div class="call-event-icon">{call_icon}</div>
                <div>
                    <div class="call-event-title">{safe_text(call_status)} · {safe_text(call_title)}</div>
                    <div class="call-event-meta">{call_meta}</div>
                </div>
            </div>
            """

        reply_html = ""
        reply_id = str(msg.get("reply_to", ""))
        if reply_id and reply_id in messages_by_id:
            replied_msg = messages_by_id[reply_id]
            reply_author = ui.get("you", "You") if replied_msg.get("from") == sender.email else safe_text(receiver.name)
            reply_text = safe_text(replied_msg.get("message", ui.get("media_file", "Media file")))
            reply_html = f"""
            <div class="reply-preview">
                <strong>{reply_author}</strong>
                <span>{reply_text}</span>
            </div>
            """

        message_text = "" if (media_type == "call_event" or msg.get("message_type") == "call_event") else (safe_text(msg.get("message")) if msg.get("message") else "")
        # Insert forwarded_html logic
        forwarded_html = ""
        if msg.get("forwarded") == True:
            forwarded_html = f'<div style="font-size:12px;color:#cbd5e1;margin-bottom:4px;">↪ {safe_text(ui.get("forwarded_message", "Forwarded message"))}</div>'
        edited_html = ""
        if msg.get("edited") == True:
            edited_html = f'<span> · {safe_text(ui.get("edited", "edited"))}</span>'
        if msg.get("status") == "read":
            message_status = '<span class="read-indicator">●</span>'
        else:
            message_status = '<span class="sent-indicator">●</span>'
        reactions = msg.get("reactions", {})
        reactions_html = ""

        for emoji, users_list in reactions.items():
            reactions_html += f'<span class="reaction-pill">{emoji} {len(users_list)}</span>'
        delete_button = f"""
            <a href="/delete_message/{sender.email}/{receiver.email}/{msg_id}/me" class="menu-action danger">🗑 {safe_text(ui.get("delete_for_me", "Delete for me"))}</a>
        """

        if msg.get("from") == sender.email:
            delete_button += f"""
            <a href="/delete_message/{sender.email}/{receiver.email}/{msg_id}/all" class="menu-action danger">🔥 {safe_text(ui.get("delete_for_everyone", "Delete for everyone"))}</a>
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
                    <button type="button" class="menu-action" onclick="replyToMessage('{msg_id}', `{message_text}`)">↩ {safe_text(ui.get("reply", "Reply"))}</button>
                    <button type="button" class="menu-action" onclick="startEditMessage('{msg_id}', `{message_text}`)">✏️ {safe_text(ui.get("edit", "Edit"))}</button>
                    <a href="/forward_message_select/{sender.email}/{receiver.email}/{msg_id}" class="menu-action">↪ {safe_text(ui.get("forward", "Forward"))}</a>
                    <button type="button" class="menu-action" onclick="copyMessageText(`{message_text}`)">📋 {safe_text(ui.get("copy", "Copy"))}</button>
                    <button type="button" class="menu-action" onclick="alert(CHAT_I18N.aiTranslationNotice)">🌐 {safe_text(ui.get("translate", "Translate"))}</button>
                    <a href="/pin_message/{sender.email}/{receiver.email}/{msg_id}" class="menu-action">📌 {safe_text(ui.get("pin", "Pin"))}</a>
                    <button type="button" class="menu-action" onclick="alert(CHAT_I18N.sentAt + ' {safe_text(msg.get("time", ""))}')">ℹ {safe_text(ui.get("info", "Info"))}</button>
                    {delete_button}
                </div>
            </div>
        </div>
        """

    chat_i18n = {
        "aiTranslationNotice": ui.get("ai_message_translation_notice", "AI message translation will be connected after API key setup."),
        "sentAt": ui.get("sent_at", "Sent:"),
        "incomingVideoCall": ui.get("incoming_video_call", "Incoming video call"),
        "incomingAudioCall": ui.get("incoming_audio_call", "Incoming audio call"),
        "user": ui.get("user", "User"),
        "isCallingYou": ui.get("is_calling_you", "is calling you"),
        "mediaFile": ui.get("media_file", "Media file"),
        "message": ui.get("message", "Message"),
        "enterSearchText": ui.get("enter_search_text", "Enter text to search"),
        "searchNoResults": ui.get("search_no_results", "Nothing found"),
        "searchFound": ui.get("search_found", "Found"),
        "searchCurrent": ui.get("search_current", "current"),
        "voiceRecording": ui.get("voice_recording", "Recording voice message..."),
        "voiceNotSupported": ui.get("voice_not_supported", "Your browser does not support voice recording."),
        "microphoneError": ui.get("microphone_error", "Could not enable the microphone. Check browser permission."),
        "voiceSending": ui.get("voice_sending", "Voice message is being sent..."),
    }
    chat_i18n_json = json.dumps(chat_i18n, ensure_ascii=False)

    return f"""
    <html lang="{safe_text(ui.get('language_code', 'ru'))}" dir="{safe_text(ui.get('text_direction', 'ltr'))}">
    <head>
    <meta charset="UTF-8">
    <title>{safe_text(ui.get("messages", "Messages"))} - AI Match Life</title>
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
    .incoming-call-panel{{
        display:none;
        align-items:center;
        justify-content:space-between;
        gap:14px;
        background:linear-gradient(135deg,#064e3b,#065f46,#0f172a);
        border:1px solid rgba(34,197,94,0.32);
        border-radius:24px;
        padding:14px 16px;
        margin-bottom:14px;
        box-shadow:0 18px 44px rgba(0,0,0,0.32);
    }}
    .incoming-call-panel.open{{display:flex;}}
    .incoming-call-left{{display:flex;align-items:center;gap:12px;min-width:0;}}
    .incoming-call-left img{{width:54px;height:54px;border-radius:50%;object-fit:cover;border:3px solid rgba(255,255,255,0.18);}}
    .incoming-call-title{{font-weight:bold;font-size:16px;margin-bottom:4px;}}
    .incoming-call-subtitle{{color:#d1fae5;font-size:13px;}}
    .incoming-call-actions{{display:flex;gap:10px;align-items:center;}}
    .incoming-accept,.incoming-decline{{border:none;border-radius:999px;width:48px;height:48px;color:white;font-size:20px;cursor:pointer;font-weight:bold;display:flex;align-items:center;justify-content:center;text-decoration:none;}}
    .incoming-accept{{background:#22c55e;}}
    .incoming-decline{{background:#ef4444;}}
    .restriction-notice{{background:linear-gradient(135deg,#312e81,#1e293b);border:1px solid rgba(129,140,248,0.34);border-radius:22px;padding:14px 16px;margin-bottom:14px;display:flex;align-items:center;justify-content:space-between;gap:14px;box-shadow:0 14px 34px rgba(0,0,0,0.28);}}
    .restriction-notice strong{{display:block;margin-bottom:4px;}}
    .restriction-notice p{{margin:0;color:#cbd5e1;font-size:13px;line-height:1.45;}}
    .restriction-notice a{{background:#334155;color:white;text-decoration:none;border-radius:14px;padding:10px 12px;font-weight:bold;white-space:nowrap;}}
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
    .call-event-card{{
        display:flex;
        align-items:center;
        gap:10px;
        background:rgba(15,23,42,0.58);
        border:1px solid rgba(148,163,184,0.16);
        border-radius:16px;
        padding:10px 12px;
        margin-bottom:8px;
        min-width:210px;
    }}
    .call-event-icon{{
        width:34px;
        height:34px;
        border-radius:50%;
        display:flex;
        align-items:center;
        justify-content:center;
        background:rgba(37,99,235,0.18);
        font-size:16px;
        flex:none;
    }}
    .call-event-title{{font-weight:bold;font-size:14px;margin-bottom:3px;}}
    .call-event-meta{{color:#cbd5e1;font-size:12px;}}
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
        <button class="back top-back" onclick="window.location.href='/messages/{sender.email}'">← {safe_text(ui.get("back", "Back"))}</button>

        <div class="header">
            <img class="avatar" src="{get_avatar_url(receiver.email)}">

            <div class="header-info">
                <h1>{safe_text(receiver.name)}</h1>
                <p class="status-line" id="typingStatus">{typing_status_text if receiver_typing else receiver_status_text}</p>
            </div>
            <div class="header-actions">
                <button class="icon-btn" onclick="toggleChatSearch()" title="{safe_text(ui.get("chat_search", "Search chat"))}">🔍</button>

                <button class="icon-btn call-btn"
                onclick="window.location.href='/audio_call/{sender.email}/{receiver.email}'"
                title="{safe_text(ui.get("audio_call", "Audio call"))}">📞</button>

                <button class="icon-btn video-btn"
                onclick="window.location.href='/video_call/{sender.email}/{receiver.email}'"
                title="{safe_text(ui.get("video_call", "Video call"))}">🎥</button>

                <button class="icon-btn" onclick="alert('{safe_text(ui.get("ai_message_translation_notice", "AI message translation will be connected after API key setup."))}')" title="{safe_text(ui.get("ai_translation", "AI translation"))}">🌐</button>
            </div>
            
               
        </div>

        {restriction_notice_html}

        <div class="incoming-call-panel" id="incomingCallPanel">
            <div class="incoming-call-left">
                <img id="incomingCallAvatar" src="{get_avatar_url(receiver.email)}" alt="Caller">
                <div>
                    <div class="incoming-call-title" id="incomingCallTitle">{safe_text(ui.get("incoming_call", "Incoming call"))}</div>
                    <div class="incoming-call-subtitle" id="incomingCallSubtitle">{safe_text(ui.get("user_is_calling", "User is calling you"))}</div>
                </div>
            </div>
            <div class="incoming-call-actions">
                <a href="#" id="incomingAcceptBtn" class="incoming-accept" title="{safe_text(ui.get("accept", "Accept"))}">📞</a>
                <button type="button" id="incomingDeclineBtn" class="incoming-decline" title="{safe_text(ui.get("decline", "Decline"))}" onclick="declineIncomingCall()">✕</button>
            </div>
        </div>

        <div class="search-panel" id="chatSearchPanel">
            <input id="chatSearchInput" type="text" placeholder="{safe_text(ui.get("search_messages", "Search messages..."))}" oninput="searchChatMessages()">
            <div class="search-actions">
                <button type="button" onclick="goToPreviousSearchResult()">⬆ {safe_text(ui.get("previous", "Previous"))}</button>
                <button type="button" onclick="goToNextSearchResult()">⬇ {safe_text(ui.get("next", "Next"))}</button>
                <button type="button" onclick="clearChatSearch()">✕ {safe_text(ui.get("close", "Close"))}</button>
            </div>
            <div class="search-count" id="chatSearchCount">{safe_text(ui.get("enter_search_text", "Enter text to search"))}</div>
        </div>

        <div class="chat" id="chatBox">
            {pinned_html}
            {chat_html}
        </div>

        <div class="reply-bar" id="replyBar">
            <button type="button" onclick="cancelReply()">✕</button>
            <strong>{safe_text(ui.get("reply_to_message", "Reply to message"))}</strong>
            <div id="replyText"></div>
        </div>

        <div class="edit-bar" id="editBar">
            <button type="button" onclick="cancelEdit()">✕</button>
            <strong>{safe_text(ui.get("editing_message", "Editing message"))}</strong>
            <div id="editText"></div>
        </div>

        <div class="voice-panel" id="voicePanel">
            <div class="voice-dot"></div>
            <div class="voice-time" id="voiceTimer">00:00</div>
            <div class="voice-text" id="voiceText">{safe_text(ui.get("voice_recording", "Recording voice message..."))}</div>
            <button type="button" class="voice-cancel" id="cancelVoiceButton">✕ {safe_text(ui.get("cancel", "Cancel"))}</button>
            <button type="button" class="voice-send" id="sendVoiceButton">↑ {safe_text(ui.get("send", "Send"))}</button>
        </div>

        <form method="POST" enctype="multipart/form-data" class="composer" id="messageForm">
            {csrf_input()}
            <input type="hidden" name="reply_to" id="replyToInput">
            <input type="hidden" name="edit_message_id" id="editMessageInput">
            <input type="hidden" name="audio_data" id="audioDataInput">

            <label class="attach-label" title="{safe_text(ui.get("file", "File"))}">
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

            <textarea name="message" id="messageInput" placeholder="{safe_text(ui.get("write_message_placeholder", "Write a message..."))}"></textarea>

            <button type="button" class="mic-btn" id="micButton" title="{safe_text(ui.get("voice_message", "Voice message"))}">🎤</button>
            <button type="submit" class="send-btn" title="{safe_text(ui.get("send", "Send"))}">↑</button>
        </form>
        <div class="hint">{safe_text(ui.get("chat_hint", "You can send text, photo, video, document, and voice message."))}</div>
    </div>

    <script>
    let activeIncomingCall = null;
    const CHAT_I18N = {chat_i18n_json};

    async function checkIncomingCall() {{
        try {{
            const response = await fetch('/pending_call/{safe_text(sender.email)}/{safe_text(receiver.email)}');
            const data = await response.json();
            const panel = document.getElementById('incomingCallPanel');
            if (!panel) return;

            if (!data.ok || !data.pending) {{
                activeIncomingCall = null;
                panel.classList.remove('open');
                return;
            }}

            activeIncomingCall = data;
            document.getElementById('incomingCallAvatar').src = data.caller_avatar || '{get_avatar_url(receiver.email)}';
            document.getElementById('incomingCallTitle').innerText = data.call_type === 'video' ? CHAT_I18N.incomingVideoCall : CHAT_I18N.incomingAudioCall;
            document.getElementById('incomingCallSubtitle').innerText = (data.caller_name || CHAT_I18N.user) + ' ' + CHAT_I18N.isCallingYou;
            document.getElementById('incomingAcceptBtn').href = data.accept_url;
            panel.classList.add('open');
        }} catch (error) {{
            console.warn('incoming call check failed', error);
        }}
    }}

    async function declineIncomingCall() {{
        if (!activeIncomingCall || !activeIncomingCall.decline_url) return;
        await fetch(activeIncomingCall.decline_url, {{ method: 'POST' }}).catch(function(error) {{ console.warn('decline failed', error); }});
        const panel = document.getElementById('incomingCallPanel');
        if (panel) panel.classList.remove('open');
        activeIncomingCall = null;
    }}

    checkIncomingCall();
    setInterval(checkIncomingCall, 2500);

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
        replyText.innerText = text || CHAT_I18N.mediaFile;
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
        editText.innerText = text || CHAT_I18N.message;
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
            if (count) count.innerText = CHAT_I18N.enterSearchText;
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
            if (count) count.innerText = CHAT_I18N.searchNoResults;
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
            count.innerText = CHAT_I18N.searchFound + ': ' + chatSearchResults.length + ' • ' + CHAT_I18N.searchCurrent + ': ' + (chatSearchIndex + 1) + '/' + chatSearchResults.length;
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
        if (count) count.innerText = CHAT_I18N.enterSearchText;
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
        if (voiceText) voiceText.innerText = CHAT_I18N.voiceRecording;
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
            alert(CHAT_I18N.voiceNotSupported);
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
            alert(CHAT_I18N.microphoneError);
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
        if (voiceText) voiceText.innerText = CHAT_I18N.voiceSending;
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
    viewer_user = find_user_by_email(viewer_email)

    if profile_user is None:
        return "User not found"

    ui = translation_bundle(get_current_language(viewer_user or profile_user))
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
    photos_count = 0

    for proof in user_proofs:
        if proof.get("type") == "certificate":
            certificates_count += 1
        elif proof.get("type") in {"document", "certificate"}:
            certificates_count += 1
        elif proof.get("type") == "project":
            projects_count += 1
        elif proof.get("type") == "video":
            videos_count += 1
        elif proof.get("type") == "achievement":
            achievements_count += 1
        elif proof.get("type") == "photo":
            photos_count += 1

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
        photos_count +
        projects_count +
        videos_count +
        achievements_count
)

    proof_summary_template = ui.get(
        "proof_summary",
        "This user uploaded {total} proofs of skills, experience, and achievements.",
    )
    proof_summary = proof_summary_template.format(total=total_proofs)

    html = open_html("proof_profile.html")

    return render_template_string(
        html,
        email=profile_email,
        viewer_email=viewer_email,
        ui=ui,
        proof_score=proof_score,
        certificates_count=certificates_count,
        photos_count=photos_count,
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
    viewer_user = find_user_by_email(viewer_email)

    if profile_user is None:
        return "User not found"

    ui = translation_bundle(get_current_language(viewer_user or profile_user))
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
    <html lang="{safe_text(ui.get('language_code', 'en'))}" dir="{safe_text(ui.get('text_direction', 'ltr'))}">
    <head>
    <meta charset="UTF-8">
    <title>{safe_text(ui.get('add_proof_title', 'Add Proof'))}</title>
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
        <h1>🏆 {safe_text(ui.get('add_proof_title', 'Add Proof'))}</h1>

        <form method="POST">
            {csrf_input()}
            <label>{safe_text(ui.get('title_label', 'Title'))}</label>
            <input name="title" required>

            <label>{safe_text(ui.get('description_label', 'Description'))}</label>
            <textarea name="description" required></textarea>

            <button type="submit">{safe_text(ui.get('save', 'Save'))}</button>
        </form>

        <br>
        <button class="back" onclick="window.location.href='/proof/{viewer_email}/{profile_email}'">{safe_text(ui.get('back', 'Back'))}</button>
    </div>
    </body>
    </html>
    """


@app.route("/privacy/<email>")
def privacy_page(email):
    user = find_user_by_email(email)
    ui = translation_bundle(get_current_language(user))
    settings = get_user_privacy(email)

    html = open_html("privacy.html")

    return render_template_string(
        html,
        email=email,
        ui=ui,

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


app.register_blueprint(create_social_routes({
    "accept_friend_request": lambda viewer_email, profile_email: accept_friend_request(viewer_email, profile_email),
    "create_social_notification": lambda target_email, text, notification_type="social", from_email="": create_social_notification(
        target_email,
        text,
        notification_type,
        from_email,
    ),
    "decline_friend_request": lambda viewer_email, profile_email: decline_friend_request(viewer_email, profile_email),
    "find_user_by_email": lambda email: find_user_by_email(email),
    "follow_user": lambda viewer_email, profile_email: follow_user(viewer_email, profile_email),
    "get_avatar_url": lambda email: get_avatar_url(email),
    "get_followers": lambda email: get_followers(email),
    "get_following": lambda email: get_following(email),
    "get_friend_requests": lambda email: get_friend_requests(email),
    "get_friends": lambda email: get_friends(email),
    "is_blocked": lambda one, two: is_blocked(one, two),
    "login_required": login_required,
    "log_security_event": lambda event_type, email="", details="": log_security_event(event_type, email, details),
    "safe_text": safe_text,
    "send_friend_request": lambda viewer_email, profile_email: send_friend_request(viewer_email, profile_email),
    "simple_page": lambda title, message, email=None: simple_page(title, message, email),
    "unfollow_user": lambda viewer_email, profile_email: unfollow_user(viewer_email, profile_email),
    "update_friend_request_notification_status": lambda target_email, from_email, status: update_friend_request_notification_status(
        target_email,
        from_email,
        status,
    ),
}))


app.register_blueprint(create_notification_routes({
    "find_user_by_email": lambda email: find_user_by_email(email),
    "get_avatar_url": lambda email: get_avatar_url(email),
    "get_notifications": lambda email: get_notifications(email),
    "login_required": login_required,
    "normalize_email": normalize_email,
    "safe_text": safe_text,
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
    "settings_control_css": settings_control_css,
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

if __name__ == "__main__":

    app.run(debug=True, port=5001)
