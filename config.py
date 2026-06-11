"""
Конфигурация Telegram-бота-визитки.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
CREDENTIALS_DIR = BASE_DIR / "credentials"

BOT_TOKEN = os.getenv("BOT_TOKEN")
CONTACT_USERNAME = os.getenv("CONTACT_USERNAME", "your_username")
CONTACT_URL = os.getenv("CONTACT_URL", f"https://t.me/{CONTACT_USERNAME}")

# --- OpenRouter ---
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODELS = [
    "openai/gpt-oss-120b:free",
    "meta-llama/llama-3.3-70b-instruct:free",
]
# Лимит только в промпте для ИИ (в коде ответ не обрезаем)
AI_PROMPT_MAX_LENGTH = 400

# --- Google Sheets (CRM) ---
GOOGLE_SHEETS_ID = os.getenv("GOOGLE_SHEETS_ID")
GOOGLE_CREDENTIALS_PATH = os.getenv(
    "GOOGLE_CREDENTIALS_PATH",
    str(CREDENTIALS_DIR / "service_account.json"),
)
SHEET_HEADERS = [
    "дата",
    "telegram_id",
    "username",
    "имя",
    "этап воронки",
    "комментарий",
    "дата записи",
    "время записи",
]

# --- Google Calendar ---
# Расшарьте календарь на сервисный аккаунт с правом «Вносить изменения»
GOOGLE_CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID", "")
BOOKING_TIMEZONE = os.getenv("BOOKING_TIMEZONE", "Europe/Moscow")
BOOKING_WORK_START_HOUR = int(os.getenv("BOOKING_WORK_START_HOUR", "10"))
BOOKING_WORK_END_HOUR = int(os.getenv("BOOKING_WORK_END_HOUR", "18"))
BOOKING_SLOT_MINUTES = int(os.getenv("BOOKING_SLOT_MINUTES", "60"))
BOOKING_DAYS_AHEAD = int(os.getenv("BOOKING_DAYS_AHEAD", "3"))

CONSULTATION_DURATION_MINUTES = 60
CONSULTATION_TITLE = "Консультация по чат-боту"

# --- Лид-магнит ---
LEAD_MAGNET_PATH = DATA_DIR / "lead_magnet.pdf"

# --- Закрытый канал ---
CHANNEL_ID = os.getenv("CHANNEL_ID", "")
CHANNEL_TEST_INVITE_LINK = os.getenv(
    "CHANNEL_TEST_INVITE_LINK",
    "https://t.me/+test_channel_invite",
)
CHANNEL_INVITE_LINK = os.getenv("CHANNEL_INVITE_LINK", "")

# --- ЮMoney ---
YOOMONEY_WALLET = os.getenv("YOOMONEY_WALLET", "")
YOOMONEY_TOKEN = os.getenv("YOOMONEY_TOKEN", "")
PAID_CONSULTATION_PRICE_RUB = 5

# Автопроверка оплаты ЮMoney (секунды)
PAYMENT_POLL_INTERVAL_SEC = 5
PAYMENT_POLL_TIMEOUT_SEC = 600

# --- Тайминги воронки (секунды) ---
DELAY_AFTER_AI_SEC = 8
DELAY_BETWEEN_STEPS_SEC = 8
