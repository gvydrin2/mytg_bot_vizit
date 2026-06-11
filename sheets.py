"""
CRM на Google Sheets.
"""

from datetime import datetime

import gspread
from google.oauth2.service_account import Credentials

from config import GOOGLE_CREDENTIALS_PATH, GOOGLE_SHEETS_ID, SHEET_HEADERS

_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def _get_worksheet():
    if not GOOGLE_SHEETS_ID:
        raise ValueError("GOOGLE_SHEETS_ID не задан в .env")

    creds = Credentials.from_service_account_file(
        GOOGLE_CREDENTIALS_PATH,
        scopes=_SCOPES,
    )
    client = gspread.authorize(creds)
    try:
        worksheet = client.open_by_key(GOOGLE_SHEETS_ID).sheet1
    except PermissionError as exc:
        cause = exc.__cause__
        if cause:
            raise RuntimeError(f"Google Sheets: {cause}") from exc
        raise RuntimeError(
            "Google Sheets: нет доступа. Включите Sheets API и дайте доступ "
            "сервисному аккаунту к таблице."
        ) from exc

    if not worksheet.row_values(1):
        worksheet.append_row(SHEET_HEADERS, value_input_option="USER_ENTERED")

    return worksheet


def _find_user_row(worksheet, telegram_id: int) -> int | None:
    # gspread 6.x: find() возвращает None, если ячейка не найдена
    cell = worksheet.find(str(telegram_id))
    return cell.row if cell else None


def _pad_row(row: list) -> list:
    while len(row) < len(SHEET_HEADERS):
        row.append("")
    return row[: len(SHEET_HEADERS)]


def _update_row(worksheet, row_num: int, row: list) -> None:
    worksheet.update(
        f"A{row_num}:H{row_num}",
        [_pad_row(row)],
        value_input_option="USER_ENTERED",
    )


def save_user_start(
    telegram_id: int,
    username: str | None,
    name: str | None,
) -> None:
    """Этап /start: имя и username в CRM."""
    worksheet = _get_worksheet()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    row_data = [
        now,
        str(telegram_id),
        username or "",
        name or "",
        "старт",
        "",
        "",
        "",
    ]
    existing_row = _find_user_row(worksheet, telegram_id)
    if existing_row:
        current = _pad_row(worksheet.row_values(existing_row))
        current[0] = now
        current[2] = username or current[2]
        current[3] = name or current[3]
        current[4] = "старт"
        _update_row(worksheet, existing_row, current)
    else:
        worksheet.append_row(row_data, value_input_option="USER_ENTERED")


def update_user_comment(telegram_id: int, comment: str, stage: str = "AI-консультация") -> None:
    worksheet = _get_worksheet()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    existing_row = _find_user_row(worksheet, telegram_id)

    if existing_row:
        current = _pad_row(worksheet.row_values(existing_row))
        current[0] = now
        current[4] = stage
        current[5] = comment
        _update_row(worksheet, existing_row, current)
    else:
        worksheet.append_row(
            [now, str(telegram_id), "", "", stage, comment, "", ""],
            value_input_option="USER_ENTERED",
        )


def save_user_stage(
    telegram_id: int,
    username: str | None,
    name: str | None,
    stage: str,
    comment: str = "",
    booking_date: str = "",
    booking_time: str = "",
) -> None:
    worksheet = _get_worksheet()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    existing_row = _find_user_row(worksheet, telegram_id)

    row_data = [
        now,
        str(telegram_id),
        username or "",
        name or "",
        stage,
        comment,
        booking_date,
        booking_time,
    ]

    if existing_row:
        current = _pad_row(worksheet.row_values(existing_row))
        current[0] = now
        current[4] = stage
        if username:
            current[2] = username
        if name:
            current[3] = name
        if comment:
            current[5] = comment
        if booking_date:
            current[6] = booking_date
        if booking_time:
            current[7] = booking_time
        _update_row(worksheet, existing_row, current)
    else:
        worksheet.append_row(row_data, value_input_option="USER_ENTERED")
