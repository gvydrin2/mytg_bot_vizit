"""
Генерация ссылки Google Calendar (без API).
Событие добавляется в календарь клиента по клику на ссылку.
"""

from datetime import datetime, timedelta
from urllib.parse import quote

from config import CONSULTATION_DURATION_MINUTES, CONSULTATION_TITLE


def build_google_calendar_url(
    iso_date: str,
    time_str: str,
    title: str = CONSULTATION_TITLE,
    description: str = "Консультация по разработке чат-бота. Ссылка на встречу будет отправлена отдельно.",
) -> str:
    """
    Формирует ссылку action=TEMPLATE для добавления события в Google Calendar.

    :param iso_date: дата в формате YYYY-MM-DD (например, 2026-06-17)
    :param time_str: время в формате HH:MM (например, 10:00)
    """
    start = datetime.strptime(f"{iso_date} {time_str}", "%Y-%m-%d %H:%M")
    end = start + timedelta(minutes=CONSULTATION_DURATION_MINUTES)

    # Формат Google Calendar: YYYYMMDDTHHMMSS (локальное время, без Z)
    fmt = "%Y%m%dT%H%M%S"
    dates = f"{start.strftime(fmt)}/{end.strftime(fmt)}"

    base = "https://calendar.google.com/calendar/render"
    params = (
        f"?action=TEMPLATE"
        f"&text={quote(title)}"
        f"&dates={dates}"
        f"&details={quote(description)}"
    )

    return base + params
