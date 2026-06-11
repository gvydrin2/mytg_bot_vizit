"""
Оплата через ЮMoney (физлицо): Quickpay + проверка по API.
"""

import uuid
from urllib.parse import urlencode

import requests

from config import YOOMONEY_TOKEN, YOOMONEY_WALLET

YOOMONEY_API_URL = "https://yoomoney.ru/api/operation-history"
QUICKPAY_URL = "https://yoomoney.ru/quickpay/confirm.xml"


def is_yoomoney_configured() -> bool:
    return bool(YOOMONEY_WALLET and YOOMONEY_TOKEN)


def make_payment_label(telegram_id: int, prefix: str = "consult") -> str:
    short_uid = uuid.uuid4().hex[:8]
    return f"{prefix}_{telegram_id}_{short_uid}"


def build_payment_url(
    label: str,
    amount: int,
    description: str = "Консультация по чат-боту",
) -> str:
    params = {
        "receiver": YOOMONEY_WALLET,
        "quickpay-form": "shop",
        "targets": description,
        "paymentType": "AC",
        "sum": f"{amount:.2f}",
        "label": label,
    }
    return f"{QUICKPAY_URL}?{urlencode(params)}"


def _fetch_operations(label: str) -> list[dict]:
    headers = {"Authorization": f"Bearer {YOOMONEY_TOKEN}"}
    response = requests.get(
        YOOMONEY_API_URL,
        headers=headers,
        params={"label": label, "records": 50, "details": "true"},
        timeout=20,
    )
    response.raise_for_status()
    return response.json().get("operations", [])


def verify_payment(label: str, amount: int) -> bool:
    """
    Проверяет входящую оплату с нужным label и суммой.
    Сумма сравнивается с допуском (комиссии/округление).
    """
    if not YOOMONEY_TOKEN:
        raise ValueError("YOOMONEY_TOKEN не задан в .env")

    operations = _fetch_operations(label)
    min_amount = float(amount) - 0.5

    for operation in operations:
        if operation.get("status") != "success":
            continue
        if operation.get("direction") != "in":
            continue

        op_label = operation.get("label") or ""
        if op_label != label:
            continue

        if float(operation.get("amount", 0)) >= min_amount:
            return True

    # Диагностика: если label не пришёл в операции — смотрим message
    if not operations:
        print(f"YooMoney: операций с label={label!r} не найдено")

    return False
