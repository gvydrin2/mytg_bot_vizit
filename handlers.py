"""
Обработчики Telegram-бота: демо-воронка продаж.
"""

import asyncio

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram import Bot
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    User,
)

from ai import generate_funnel
from calendar_slots import (
    create_booking_event,
    format_date_label,
    get_available_dates,
    get_available_times,
)
from calendar_utils import build_google_calendar_url
from channel import issue_channel_access
from config import (
    CONTACT_URL,
    DELAY_AFTER_AI_SEC,
    DELAY_BETWEEN_STEPS_SEC,
    LEAD_MAGNET_PATH,
    PAID_CONSULTATION_PRICE_RUB,
    PAYMENT_POLL_INTERVAL_SEC,
    PAYMENT_POLL_TIMEOUT_SEC,
)
from payment import (
    build_payment_url,
    is_yoomoney_configured,
    make_payment_label,
    verify_payment,
)
from sheets import save_user_stage, save_user_start, update_user_comment

router = Router()

# Активные фоновые проверки оплаты (по label)
_active_payment_polls: set[str] = set()

CONSULT_PITCH = (
    "Хоть ИИ иногда и может предложить неплохое решение, но реализовывать его "
    "на 99% всё равно придётся человеку.\n\n"
    "Запишитесь на консультацию, чтобы мы могли обсудить ваши идеи более "
    "подробно и найти путь к их реализации."
)


class FunnelState(StatesGroup):
    waiting_niche = State()
    waiting_niche_paid = State()


# ---------------------------------------------------------------------------
# Клавиатуры
# ---------------------------------------------------------------------------
def kb_checklist() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Получить чек-лист", callback_data="get_checklist")]
        ]
    )


def kb_dates(dates: list[tuple[str, str]], paid: bool = False) -> InlineKeyboardMarkup:
    prefix = "paid_date" if paid else "date"
    buttons = [
        [InlineKeyboardButton(text=label, callback_data=f"{prefix}:{iso}")]
        for iso, label in dates
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def kb_times(iso_date: str, times: list[str], paid: bool = False) -> InlineKeyboardMarkup:
    prefix = "paid_time" if paid else "time"
    buttons = [
        [InlineKeyboardButton(text=t, callback_data=f"{prefix}:{iso_date}:{t}")]
        for t in times
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def kb_paid_mechanics() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Посмотреть механику оплаты",
                    callback_data="paid_demo_start",
                )
            ]
        ]
    )


def kb_check_consult_payment() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Я оплатил — подтвердить запись",
                    callback_data="check_consult_payment",
                )
            ]
        ]
    )


def kb_contact() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Связаться со мной", url=CONTACT_URL)]
        ]
    )


def kb_client_calendar(iso_date: str, time_str: str) -> InlineKeyboardMarkup:
    """Ссылка для добавления встречи в календарь клиента."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📆 Добавить в Google Calendar",
                    url=build_google_calendar_url(iso_date, time_str),
                )
            ]
        ]
    )


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------
async def _save_from_callback(callback: CallbackQuery, stage: str, **kwargs) -> None:
    if not callback.from_user:
        return
    try:
        save_user_stage(
            telegram_id=callback.from_user.id,
            username=callback.from_user.username,
            name=callback.from_user.full_name or "",
            stage=stage,
            **kwargs,
        )
    except Exception as exc:
        print(f"Sheets error: {exc!r}")


async def _after_ai_response(message: Message, state: FSMContext, paid: bool = False) -> None:
    """Пауза 5 сек → текст → кнопка выбора даты."""
    await asyncio.sleep(DELAY_AFTER_AI_SEC)
    await message.answer(CONSULT_PITCH)

    try:
        dates = get_available_dates()
    except Exception as exc:
        print(f"Calendar error: {exc!r}")
        await message.answer(
            "⚠️ Не удалось загрузить свободные даты. Напишите мне напрямую.",
            reply_markup=kb_contact(),
        )
        return

    if not dates:
        await message.answer(
            "Сейчас нет свободных слотов для записи. Напишите мне напрямую.",
            reply_markup=kb_contact(),
        )
        return

    await state.update_data(booking_paid=paid)
    await message.answer(
        "Выберите свободную дату:",
        reply_markup=kb_dates(dates, paid=paid),
    )


async def _send_summary(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    steps = []
    if data.get("got_lead_magnet"):
        steps.append("✅ Получил лид-магнит.")
    if data.get("got_ai_recommendation"):
        steps.append("✅ Получил персональную рекомендацию.")
    if data.get("booked_free_consultation"):
        steps.append("✅ Записался на бесплатную консультацию.")

    text = (
        "🎯 Итог демонстрации\n\n"
        + ("\n".join(steps) if steps else "✅ Демо-воронка пройдена.")
        + "\n\nИменно такие системы я создаю для экспертов под ключ."
    )
    await message.answer(text, reply_markup=kb_contact())


async def _send_free_channel(message: Message, callback: CallbackQuery, state: FSMContext) -> None:
    user = callback.from_user
    invite_link, is_unique = await issue_channel_access(
        bot=callback.bot,
        telegram_id=user.id if user else 0,
        username=user.username if user else None,
    )
    await state.update_data(got_channel_access=True)
    await _save_from_callback(callback, stage="бесплатный доступ в канал")

    note = "Ссылка одноразовая — только для тебя." if is_unique else ""
    await message.answer(
        "Пока ждём консультацию, можешь получить доступ к закрытому каналу "
        "с механиками продаж через чат-ботов.\n\n"
        "Для участников демонстрации доступ бесплатный."
        + (f"\n\n{note}" if note else ""),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Перейти в канал", url=invite_link)]
            ]
        ),
    )


def _book_calendar_slot_for_user(
    user: User | None,
    iso_date: str,
    time_str: str,
    paid: bool = False,
) -> bool:
    """Занимает слот в календаре эксперта. False — слот уже занят."""
    try:
        create_booking_event(
            iso_date,
            time_str,
            client_name=user.full_name if user else "Клиент",
            client_username=user.username if user else None,
            paid=paid,
        )
        return True
    except ValueError:
        return False
    except Exception as exc:
        print(f"Calendar create error: {exc!r}")
        return False


async def _send_booking_confirmation(
    message: Message,
    iso_date: str,
    time_str: str,
    *,
    paid: bool = False,
) -> None:
    date_label = format_date_label(iso_date)
    prefix = "✅ Оплата получена! Запись подтверждена." if paid else "✅ Запись подтверждена!"
    await message.answer(
        f"{prefix}\n\n"
        f"📅 {date_label}, {time_str}\n\n"
        "Я свяжусь с тобой за день до консультации, чтобы напомнить о встрече.\n\n"
        "Можешь добавить встречу в свой календарь:",
        reply_markup=kb_client_calendar(iso_date, time_str),
    )


async def _complete_paid_booking(
    bot: Bot,
    chat_id: int,
    user: User,
    state: FSMContext,
    booking: dict,
    label: str,
) -> bool:
    """Подтверждает платную запись после оплаты. True — успех."""
    data = await state.get_data()
    if data.get("consult_payment_confirmed"):
        return True
    if data.get("consult_payment_label") != label:
        return False

    if not _book_calendar_slot_for_user(
        user, booking["iso_date"], booking["time"], paid=True
    ):
        await bot.send_message(
            chat_id,
            "Оплата получена, но слот уже занят. Напишите мне — подберём другое время.",
            reply_markup=kb_contact(),
        )
        await state.update_data(consult_payment_label=None, pending_paid_booking=None)
        return False

    try:
        save_user_stage(
            telegram_id=user.id,
            username=user.username,
            name=user.full_name or "",
            stage="платная запись подтверждена",
            booking_date=booking["date"],
            booking_time=booking["time"],
        )
    except Exception as exc:
        print(f"Sheets error: {exc!r}")
    await state.update_data(
        booked_paid_consultation=True,
        consult_payment_confirmed=True,
        pending_paid_booking=None,
        consult_payment_label=None,
    )

    msg = await bot.send_message(chat_id, "⏳ Подтверждаю запись...")
    await _send_booking_confirmation(
        msg, booking["iso_date"], booking["time"], paid=True
    )
    await bot.send_message(
        chat_id,
        "Это демонстрация механики: запись подтверждается только после оплаты.",
        reply_markup=kb_contact(),
    )
    return True


async def _auto_poll_payment(
    bot: Bot,
    chat_id: int,
    user: User,
    state: FSMContext,
    label: str,
    booking: dict,
) -> None:
    """Фоновая проверка оплаты ЮMoney без нажатия кнопки."""
    if label in _active_payment_polls:
        return
    _active_payment_polls.add(label)

    try:
        elapsed = 0
        while elapsed < PAYMENT_POLL_TIMEOUT_SEC:
            await asyncio.sleep(PAYMENT_POLL_INTERVAL_SEC)
            elapsed += PAYMENT_POLL_INTERVAL_SEC

            data = await state.get_data()
            if data.get("consult_payment_label") != label:
                return

            try:
                if verify_payment(label, PAID_CONSULTATION_PRICE_RUB):
                    await _complete_paid_booking(bot, chat_id, user, state, booking, label)
                    return
            except Exception as exc:
                print(f"Payment poll error: {exc!r}")

        data = await state.get_data()
        if data.get("consult_payment_label") == label:
            await bot.send_message(
                chat_id,
                "Оплата ещё не поступила. Если вы уже оплатили — подождите минуту "
                "или нажмите кнопку ниже:",
                reply_markup=kb_check_consult_payment(),
            )
    finally:
        _active_payment_polls.discard(label)


async def _finish_free_booking(
    callback: CallbackQuery, state: FSMContext, iso_date: str, time_str: str
) -> None:
    if not _book_calendar_slot_for_user(
        callback.from_user, iso_date, time_str, paid=False
    ):
        await callback.message.answer(
            "К сожалению, этот слот только что заняли. Выберите другое время."
        )
        return

    date_label = format_date_label(iso_date)

    await _save_from_callback(
        callback,
        stage="бесплатная запись на консультацию",
        booking_date=date_label,
        booking_time=time_str,
    )
    await state.update_data(booked_free_consultation=True)

    await _send_booking_confirmation(
        callback.message, iso_date, time_str, paid=False
    )

    await asyncio.sleep(DELAY_BETWEEN_STEPS_SEC)
    await _send_summary(callback.message, state)

    await asyncio.sleep(DELAY_BETWEEN_STEPS_SEC)
    await _send_free_channel(callback.message, callback, state)

    await asyncio.sleep(DELAY_BETWEEN_STEPS_SEC)
    await callback.message.answer(
        "Ты также можешь посмотреть другие механики чат-бота — "
        "в том числе с оплатой продукта или доступа к каналу.\n\n"
        "Если интересно, нажми кнопку ниже:",
        reply_markup=kb_paid_mechanics(),
    )


async def _show_times(callback: CallbackQuery, iso_date: str, paid: bool) -> None:
    try:
        times = get_available_times(iso_date)
    except Exception as exc:
        print(f"Calendar error: {exc!r}")
        await callback.message.answer("⚠️ Не удалось загрузить время. Попробуйте позже.")
        return

    if not times:
        await callback.message.answer(
            "На эту дату свободных слотов нет. Выберите другую дату."
        )
        return

    await callback.message.answer(
        "Выберите свободное время:",
        reply_markup=kb_times(iso_date, times, paid=paid),
    )


# ---------------------------------------------------------------------------
# /start
# ---------------------------------------------------------------------------
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    if message.from_user:
        try:
            save_user_start(
                telegram_id=message.from_user.id,
                username=message.from_user.username,
                name=message.from_user.full_name,
            )
        except Exception as exc:
            print(f"Sheets error: {exc!r}")

    await message.answer(
        "Привет 👋\n\n"
        "Сейчас я покажу тебе на практике, как работает автоматизированная "
        "воронка продаж для эксперта.\n\n"
        "Для начала забери бесплатный чек-лист.",
        reply_markup=kb_checklist(),
    )


# ---------------------------------------------------------------------------
# Лид-магнит
# ---------------------------------------------------------------------------
@router.callback_query(F.data == "get_checklist")
async def on_get_checklist(callback: CallbackQuery, state: FSMContext):
    await callback.answer()

    if not LEAD_MAGNET_PATH.exists():
        await callback.message.answer("⚠️ Файл чек-листа не найден.")
        return

    await callback.message.answer_document(
        FSInputFile(LEAD_MAGNET_PATH),
        caption="🎁 Твой чек-лист по автоворонкам для экспертов",
    )
    await _save_from_callback(callback, stage="лид-магнит")
    await state.update_data(got_lead_magnet=True)

    await state.set_state(FunnelState.waiting_niche)
    await callback.message.answer(
        "Выдача лид-магнита — только начало автоматизации.\n\n"
        "Теперь расскажи, чем ты занимаешься и какую задачу хотел бы решить "
        "с помощью чат-бота."
    )


# ---------------------------------------------------------------------------
# AI + запись
# ---------------------------------------------------------------------------
@router.message(FunnelState.waiting_niche, F.text)
async def on_niche_answer(message: Message, state: FSMContext):
    niche = message.text.strip()
    if not niche:
        await message.answer("Напиши, пожалуйста, чем ты занимаешься.")
        return

    await message.answer("🧠 Анализирую твою нишу...")

    try:
        ai_response = generate_funnel(niche)
    except Exception as exc:
        print(f"AI error: {exc}")
        await message.answer("⚠️ Не удалось получить рекомендацию. Попробуй позже.")
        return

    if message.from_user:
        try:
            update_user_comment(message.from_user.id, niche)
        except Exception as exc:
            print(f"Sheets error: {exc!r}")

    await state.update_data(got_ai_recommendation=True, niche=niche)
    await state.set_state(None)

    await message.answer(ai_response)
    await _after_ai_response(message, state, paid=False)


@router.message(FunnelState.waiting_niche_paid, F.text)
async def on_niche_answer_paid(message: Message, state: FSMContext):
    niche = message.text.strip()
    if not niche:
        await message.answer("Напиши, пожалуйста, чем ты занимаешься.")
        return

    await message.answer("🧠 Анализирую твою нишу...")

    try:
        ai_response = generate_funnel(niche)
    except Exception as exc:
        print(f"AI error: {exc}")
        await message.answer("⚠️ Не удалось получить рекомендацию. Попробуй позже.")
        return

    if message.from_user:
        try:
            update_user_comment(
                message.from_user.id,
                f"[платная воронка] {niche}",
                stage="AI-консультация (платная)",
            )
        except Exception as exc:
            print(f"Sheets error: {exc!r}")

    await state.set_state(None)
    await message.answer(ai_response, parse_mode="Markdown")
    await _after_ai_response(message, state, paid=True)


# ---------------------------------------------------------------------------
# Бесплатная запись (даты из Google Calendar)
# ---------------------------------------------------------------------------
@router.callback_query(F.data.startswith("date:"))
async def on_pick_date(callback: CallbackQuery):
    await callback.answer()
    iso_date = callback.data.removeprefix("date:")
    await _show_times(callback, iso_date, paid=False)


@router.callback_query(F.data.startswith("time:"))
async def on_pick_time(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    parts = callback.data.removeprefix("time:").split(":", 1)
    if len(parts) != 2:
        return

    iso_date, time_str = parts
    available = get_available_times(iso_date)
    if time_str not in available:
        await callback.message.answer("Этот слот уже занят. Выберите другое время.")
        return

    await _finish_free_booking(callback, state, iso_date, time_str)


# ---------------------------------------------------------------------------
# Платная воронка
# ---------------------------------------------------------------------------
@router.callback_query(F.data == "paid_demo_start")
async def on_paid_demo_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.answer(
        "Сейчас покажу механику оплаты перед записью.\n\n"
        "Повторим ключевые шаги воронки:"
    )
    await callback.message.answer(
        "✅ Шаг 1. Чек-лист ты уже получил — повторно не отправляю."
    )
    await state.set_state(FunnelState.waiting_niche_paid)
    await callback.message.answer(
        "🔄 Шаг 2. Снова расскажи, чем занимаешься и какую задачу "
        "хотел бы решить с помощью чат-бота:"
    )


@router.callback_query(F.data.startswith("paid_date:"))
async def on_pick_paid_date(callback: CallbackQuery):
    await callback.answer()
    iso_date = callback.data.removeprefix("paid_date:")
    await _show_times(callback, iso_date, paid=True)


@router.callback_query(F.data.startswith("paid_time:"))
async def on_pick_paid_time(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    parts = callback.data.removeprefix("paid_time:").split(":", 1)
    if len(parts) != 2:
        return

    iso_date, time_str = parts
    available = get_available_times(iso_date)
    if time_str not in available:
        await callback.message.answer("Этот слот уже занят. Выберите другое время.")
        return

    if not is_yoomoney_configured():
        await callback.message.answer(
            "⚠️ Оплата временно недоступна.",
            reply_markup=kb_contact(),
        )
        return

    date_label = format_date_label(iso_date)
    label = make_payment_label(callback.from_user.id, prefix="consult")
    payment_url = build_payment_url(
        label,
        PAID_CONSULTATION_PRICE_RUB,
        description="Платная консультация по чат-боту",
    )

    booking = {
        "iso_date": iso_date,
        "date": date_label,
        "time": time_str,
    }

    await state.update_data(
        pending_paid_booking=booking,
        consult_payment_label=label,
        consult_payment_confirmed=False,
    )

    await callback.message.answer(
        f"📅 Вы выбрали: {date_label}, {time_str}\n\n"
        f"Стоимость консультации — {PAID_CONSULTATION_PRICE_RUB} ₽.\n"
        "Запись подтвердится только после оплаты.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=f"💳 Оплатить {PAID_CONSULTATION_PRICE_RUB} ₽",
                        url=payment_url,
                    )
                ]
            ],
        ),
    )
    await callback.message.answer(
        "Оплата проверяется автоматически — обычно это занимает до 1–2 минут.\n"
        "Если нужно вручную — нажми кнопку ниже:",
        reply_markup=kb_check_consult_payment(),
    )

    asyncio.create_task(
        _auto_poll_payment(
            callback.bot,
            callback.message.chat.id,
            callback.from_user,
            state,
            label,
            booking,
        )
    )


@router.callback_query(F.data == "check_consult_payment")
async def on_check_consult_payment(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    label = data.get("consult_payment_label")
    booking = data.get("pending_paid_booking")

    if not label or not booking:
        await callback.message.answer("Сначала выбери дату и время.")
        return

    if data.get("consult_payment_confirmed"):
        await callback.message.answer("Запись уже подтверждена ✅")
        return

    await callback.message.answer("⏳ Проверяю оплату...")

    try:
        paid = verify_payment(label, PAID_CONSULTATION_PRICE_RUB)
    except Exception as exc:
        print(f"YooMoney error: {exc!r}")
        await callback.message.answer("⚠️ Не удалось проверить оплату.")
        return

    if not paid:
        await callback.message.answer(
            "Оплата пока не найдена. Подожди 1–2 минуты — бот тоже проверяет автоматически.",
            reply_markup=kb_check_consult_payment(),
        )
        return

    await _complete_paid_booking(
        callback.bot,
        callback.message.chat.id,
        callback.from_user,
        state,
        booking,
        label,
    )
