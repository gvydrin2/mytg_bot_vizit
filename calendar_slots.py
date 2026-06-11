"""
Google Calendar: свободные слоты (FreeBusy) и создание встречи при записи.
Календарь gvydrin2@gmail.com должен быть расшарен на сервисный аккаунт
с правом вносить изменения — тогда слот занимает автоматически.
"""

from datetime import date, datetime, time, timedelta
import json
import os
from zoneinfo import ZoneInfo

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

from config import (
    BOOKING_DAYS_AHEAD,
    BOOKING_SLOT_MINUTES,
    BOOKING_TIMEZONE,
    BOOKING_WORK_END_HOUR,
    BOOKING_WORK_START_HOUR,
    CONSULTATION_TITLE,
    GOOGLE_CALENDAR_ID,
    GOOGLE_CREDENTIALS_PATH,
)

# Чтение занятости + создание событий при записи
_SCOPES = ["https://www.googleapis.com/auth/calendar"]

_MONTHS_RU = (
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
)


def _tz() -> ZoneInfo:
    return ZoneInfo(BOOKING_TIMEZONE)


def _get_service():
    if not GOOGLE_CALENDAR_ID:
        raise ValueError("GOOGLE_CALENDAR_ID не задан в .env")
        
    # Сначала пытаемся прочитать JSON-строку из переменных окружения (для Railway)
    service_account_info = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    
    if service_account_info:
        # Если переменная на хостинге заполнена, авторизуемся через неё из памяти
        info = json.loads(service_account_info)
        creds = Credentials.from_service_account_info(info, scopes=_SCOPES)
    else:
        # Если переменной нет, читаем локальный файл на ПК
        creds = Credentials.from_service_account_file(
            GOOGLE_CREDENTIALS_PATH,
            scopes=_SCOPES,
        )
        
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def format_date_label(iso_date: str) -> str:
    d = date.fromisoformat(iso_date)
    return f"{d.day} {_MONTHS_RU[d.month - 1]}"


def _parse_busy_period(start_iso: str, end_iso: str, tz: ZoneInfo) -> tuple[datetime, datetime]:
    start = datetime.fromisoformat(start_iso.replace("Z", "+00:00")).astimezone(tz)
    end = datetime.fromisoformat(end_iso.replace("Z", "+00:00")).astimezone(tz)
    return start, end


def _fetch_busy_ranges(time_min: datetime, time_max: datetime) -> list[tuple[datetime, datetime]]:
    service = _get_service()
    body = {
        "timeMin": time_min.isoformat(),
        "timeMax": time_max.isoformat(),
        "timeZone": BOOKING_TIMEZONE,
        "items": [{"id": GOOGLE_CALENDAR_ID}],
    }
    result = service.freebusy().query(body=body).execute()
    busy_raw = result.get("calendars", {}).get(GOOGLE_CALENDAR_ID, {}).get("busy", [])
    tz = _tz()
    return [_parse_busy_period(b["start"], b["end"], tz) for b in busy_raw]


def _slot_overlaps_busy(
    slot_start: datetime,
    slot_end: datetime,
    busy_ranges: list[tuple[datetime, datetime]],
) -> bool:
    for busy_start, busy_end in busy_ranges:
        if slot_start < busy_end and slot_end > busy_start:
            return True
    return False


def _iter_candidate_slots(
    day: date,
    busy_ranges: list[tuple[datetime, datetime]],
    now: datetime,
) -> list[datetime]:
    tz = _tz()
    slots: list[datetime] = []
    start_hour = BOOKING_WORK_START_HOUR
    end_limit = BOOKING_WORK_END_HOUR * 60  # минуты от полуночи

    minute = start_hour * 60
    while minute + BOOKING_SLOT_MINUTES <= end_limit:
        h, m = divmod(minute, 60)
        slot_start = datetime.combine(day, time(h, m), tzinfo=tz)
        slot_end = slot_start + timedelta(minutes=BOOKING_SLOT_MINUTES)
        if slot_start > now and not _slot_overlaps_busy(slot_start, slot_end, busy_ranges):
            slots.append(slot_start)
        minute += BOOKING_SLOT_MINUTES

    return slots


def get_available_dates() -> list[tuple[str, str]]:
    """
    Возвращает список (iso_date, подпись для кнопки) с хотя бы одним свободным слотом.
    """
    tz = _tz()
    now = datetime.now(tz)
    range_start = now
    range_end = now + timedelta(days=BOOKING_DAYS_AHEAD)

    busy_ranges = _fetch_busy_ranges(range_start, range_end)

    dates: list[tuple[str, str]] = []
    for offset in range(BOOKING_DAYS_AHEAD + 1):
        day = (now.date() + timedelta(days=offset))
        slots = _iter_candidate_slots(day, busy_ranges, now)
        if slots:
            iso = day.isoformat()
            dates.append((iso, format_date_label(iso)))

    return dates


def get_available_times(iso_date: str) -> list[str]:
    """Свободные слоты на конкретную дату в формате HH:MM."""
    tz = _tz()
    now = datetime.now(tz)
    day = date.fromisoformat(iso_date)
    range_start = datetime.combine(day, time.min, tzinfo=tz)
    range_end = range_start + timedelta(days=1)

    busy_ranges = _fetch_busy_ranges(range_start, range_end)
    slots = _iter_candidate_slots(day, busy_ranges, now)
    return [s.strftime("%H:%M") for s in slots]


def is_slot_available(iso_date: str, time_str: str) -> bool:
    """Проверяет, свободен ли слот прямо сейчас (перед созданием встречи)."""
    return time_str in get_available_times(iso_date)


def create_booking_event(
    iso_date: str,
    time_str: str,
    client_name: str,
    client_username: str | None = None,
    *,
    paid: bool = False,
) -> str:
    """
    Создаёт встречу в календаре эксперта и занимает слот.
    Возвращает id события в Google Calendar.
    """
    if not is_slot_available(iso_date, time_str):
        raise ValueError("Слот уже занят")

    tz = _tz()
    start = datetime.strptime(f"{iso_date} {time_str}", "%Y-%m-%d %H:%M").replace(tzinfo=tz)
    end = start + timedelta(minutes=BOOKING_SLOT_MINUTES)

    title = CONSULTATION_TITLE
    if paid:
        title = f"{title} (оплачено)"

    description_lines = [f"Клиент: {client_name}"]
    if client_username:
        description_lines.append(f"Telegram: @{client_username}")
    description_lines.append("Запись через Telegram-бот")

    event_body = {
        "summary": title,
        "description": "\n".join(description_lines),
        "start": {"dateTime": start.isoformat(), "timeZone": BOOKING_TIMEZONE},
        "end": {"dateTime": end.isoformat(), "timeZone": BOOKING_TIMEZONE},
    }

    service = _get_service()
    created = (
        service.events()
        .insert(calendarId=GOOGLE_CALENDAR_ID, body=event_body)
        .execute()
    )
    return created["id"]
