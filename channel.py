"""
Уникальные invite-ссылки в закрытый канал через Telegram Bot API.

Требования:
- Бот добавлен в канал как администратор
- Право «Приглашать пользователей» (can_invite_users)
- CHANNEL_ID в .env (@username канала или -100xxxxxxxxxx)
"""

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from config import CHANNEL_ID, CHANNEL_INVITE_LINK, CHANNEL_TEST_INVITE_LINK


def is_channel_invite_configured() -> bool:
    """True, если задан ID канала для генерации ссылок через API."""
    return bool(CHANNEL_ID)


def _fallback_invite_link() -> str:
    """Запасная статическая ссылка, если API недоступен."""
    return CHANNEL_INVITE_LINK or CHANNEL_TEST_INVITE_LINK


async def create_unique_invite_link(
    bot: Bot,
    telegram_id: int,
    username: str | None = None,
) -> str:
    """
    Создаёт одноразовую invite-ссылку (member_limit=1) для конкретного пользователя.
    Имя ссылки — для удобства в списке приглашений канала.
    """
    if not CHANNEL_ID:
        raise ValueError("CHANNEL_ID не задан в .env")

    # Имя ссылки в Telegram — до 32 символов
    link_name = f"paid_{telegram_id}"
    if username:
        link_name = f"@{username}"[:32]

    invite = await bot.create_chat_invite_link(
        chat_id=CHANNEL_ID,
        name=link_name,
        member_limit=1,
    )
    return invite.invite_link


async def issue_channel_access(
    bot: Bot,
    telegram_id: int,
    username: str | None = None,
) -> tuple[str, bool]:
    """
    Выдаёт ссылку в канал.

    :return: (invite_link, is_unique) — is_unique=True, если ссылка создана через API
    """
    if not is_channel_invite_configured():
        return _fallback_invite_link(), False

    try:
        link = await create_unique_invite_link(bot, telegram_id, username)
        return link, True
    except TelegramAPIError as exc:
        print(f"create_chat_invite_link error: {exc}")
        return _fallback_invite_link(), False
