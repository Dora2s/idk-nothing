import asyncio
import html
import logging
import os
import random
import string
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import quote

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    LinkPreviewOptions,
)

TOKEN = os.getenv("BOT_TOKEN")
PHOTO_URL = "https://i.ibb.co/xq818Hvw/0-02-05-afde0a0fb3dfc0a82821bbcd988a8dfc86c745490877efdacac2bf204fa39f19-b5fce59ed1df9bb-2.jpg"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MAIN_ADMIN_IDS = {8883652898, 5156707493}

ADMINS_FILE = os.path.join(BASE_DIR, "admins.txt")
USERS_FILE = os.path.join(BASE_DIR, "users.txt")
RECIPIENTS_FILE = os.path.join(BASE_DIR, "recipients.txt")
MAINTENANCE_FILE = os.path.join(BASE_DIR, "maintenance.txt")


def init_files():
    files = [
        (ADMINS_FILE, ""),
        (USERS_FILE, ""),
        (RECIPIENTS_FILE, ""),
        (MAINTENANCE_FILE, "0"),
    ]
    for filepath, default_content in files:
        if not os.path.exists(filepath):
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(default_content)


init_files()


def load_admins() -> set[int]:
    admins = set()
    if os.path.exists(ADMINS_FILE):
        with open(ADMINS_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.isdigit():
                    admins.add(int(line))
    return admins


def save_admins(admins: set[int]):
    with open(ADMINS_FILE, "w", encoding="utf-8") as f:
        for uid in admins:
            f.write(f"{uid}\n")


def load_users() -> set[int]:
    users = set()
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.isdigit():
                    users.add(int(line))
    return users


def save_users(users: set[int]):
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        for uid in users:
            f.write(f"{uid}\n")


def load_recipients() -> dict[int, str]:
    recs = {}
    if os.path.exists(RECIPIENTS_FILE):
        with open(RECIPIENTS_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if ":" in line:
                    uid_str, username = line.strip().split(":", 1)
                    if uid_str.isdigit():
                        recs[int(uid_str)] = username
    return recs


def save_recipients(recs: dict[int, str]):
    with open(RECIPIENTS_FILE, "w", encoding="utf-8") as f:
        for uid, username in recs.items():
            f.write(f"{uid}:{username}\n")


def load_maintenance() -> bool:
    if os.path.exists(MAINTENANCE_FILE):
        with open(MAINTENANCE_FILE, "r", encoding="utf-8") as f:
            return f.read().strip() == "1"
    return False


def save_maintenance(state: bool):
    with open(MAINTENANCE_FILE, "w", encoding="utf-8") as f:
        f.write("1" if state else "0")


regular_admins = load_admins()
allowed_users = load_users()
user_recipients = load_recipients()
maintenance_mode = load_maintenance()

orders: dict[str, dict] = {}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger(__name__)

bot = Bot(
    TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
dp = Dispatcher()


def h(value) -> str:
    return html.escape(str(value), quote=False)


def get_user_status(user_id: int) -> str:
    if user_id in MAIN_ADMIN_IDS:
        return "Главный админ"
    if user_id in regular_admins:
        return "Админ"
    if user_id in allowed_users:
        return "Пользователь"
    return "Нет доступа"


def is_allowed(user_id: int) -> bool:
    if maintenance_mode:
        return user_id in MAIN_ADMIN_IDS
    return (
        user_id in MAIN_ADMIN_IDS
        or user_id in regular_admins
        or user_id in allowed_users
    )


async def check_access(message: Message) -> bool:
    if not is_allowed(message.from_user.id):
        return False
    return True


def order_id() -> str:
    return "TG-" + "".join(
        random.choices(string.ascii_uppercase + string.digits, k=8)
    )


def display_nft(name: str) -> str:
    if "-" not in name:
        return name

    base, number = name.rsplit("-", 1)
    readable = "".join(
        (" " + c if c.isupper() and i else c)
        for i, c in enumerate(base)
    )
    return f"{readable} #{number}".strip()


def nft_url(name: str) -> str:
    return "https://t.me/nft/" + quote(name, safe="-_")


def parse_buy(text: str) -> Optional[dict]:
    parts = (text or "").strip().split()

    if len(parts) < 4:
        return None

    if parts[0].lower() not in ("купить", "buy"):
        return None

    try:
        amount = int(parts[2])
        if amount <= 0:
            return None
    except ValueError:
        return None

    return {
        "nft_name": parts[1],
        "amount": amount,
        "currency": parts[3].lower(),
        "language": parts[4].lower() if len(parts) > 4 else "ru",
    }


def currency_label(currency: str, lang: str = "ru") -> str:
    c = currency.lower()
    is_en = lang in ("en", "eng", "english")
    if c in ("stars", "звёзд", "звезды", "star"):
        return "Stars ⭐" if is_en else "Звёзд ⭐"
    if c == "usdt":
        return "USDT"
    if c == "ton":
        return "TON"
    return currency.upper()


async def send_order_message(
    order: dict,
    text: str,
    keyboard=None,
    link_preview_options=None,
):
    kwargs = {
        "chat_id": order["chat_id"],
        "text": text,
        "reply_markup": (
            InlineKeyboardMarkup(inline_keyboard=keyboard)
            if keyboard else None
        ),
    }

    if order.get("business_connection_id"):
        kwargs["business_connection_id"] = order["business_connection_id"]

    if link_preview_options is not None:
        kwargs["link_preview_options"] = link_preview_options

    await bot.send_message(**kwargs)


@dp.message(Command("start"))
async def start(message: Message):
    if not await check_access(message):
        return

    status = get_user_status(message.from_user.id)
    rec = user_recipients.get(message.from_user.id)
    recipient_str = f"@{rec}" if rec else "не указан"

    caption = (
        "NFT OFFER BOT\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"Ваш статус: <b>{status}</b>\n"
        f"Получатель: {h(recipient_str)}\n\n"
        "Формат: купить NFT-имя сумма валюта язык\n\n"
        "Пример: купить LibertyFigure-211081 950 stars ru\n\n"
        "/settings · /help · /orders"
    )

    await message.answer_photo(
        photo=PHOTO_URL,
        caption=caption,
    )


@dp.message(Command("help"))
async def help_cmd(message: Message):
    if not await check_access(message):
        return

    await message.answer(
        "HELP\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "1. Подключи бота в Telegram Business, если используешь Business.\n\n"
        "2. Отправь команду покупки в формате:\n"
        "купить NFT-имя сумма валюта язык\n\n"
        "Пример: buy LibertyFigure-211081 950 stars ru\n\n"
        "3. Бот создаст оффер с кнопками."
    )


@dp.message(Command("settings"))
async def settings_cmd(message: Message):
    if not await check_access(message):
        return

    user_id = message.from_user.id
    status = get_user_status(user_id)
    rec = user_recipients.get(user_id)
    recipient_str = f"@{rec}" if rec else "не указан"

    text = (
        "Настройки\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"Ваш статус: <b>{status}</b>\n"
        f"Получатель: <b>{h(recipient_str)}</b>\n"
    )

    if user_id in MAIN_ADMIN_IDS:
        m_status = "ВКЛ (Доступ только главным)" if maintenance_mode else "ВЫКЛ (Обычный режим)"
        text += (
            "\n<b>Панель Главного Администратора:</b>\n"
            f"Технический режим: {m_status}\n"
            f"Обычных админов: {len(regular_admins)}\n"
            f"Пользователей с доступом: {len(allowed_users)}\n\n"
            "Команды:\n"
            "<code>/add ID</code> — Добавить пользователя\n"
            "<code>/remove ID</code> — Удалить пользователя\n"
            "<code>/addadmin ID</code> — Назначить админа\n"
            "<code>/removeadmin ID</code> — Снять админа\n"
            "<code>/lock</code> — Включить/выключить тех. режим"
        )
    elif user_id in regular_admins:
        text += (
            "\n<b>Панель Администратора:</b>\n"
            f"Пользователей с доступом: {len(allowed_users)}\n\n"
            "Команды:\n"
            "<code>/add ID</code> — Добавить пользователя\n"
            "<code>/remove ID</code> — Удалить пользователя"
        )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Изменить получателя",
                    callback_data="set_recipient",
                )
            ]
        ]
    )

    await message.answer(text, reply_markup=keyboard)


@dp.message(Command("recipient"))
async def set_recipient_cmd(message: Message):
    if not await check_access(message):
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) > 1:
        rec = parts[1].strip().lstrip("@")
        user_recipients[message.from_user.id] = rec
        save_recipients(user_recipients)
        await message.answer(f"Получатель успешно установлен: @{h(rec)}")
    else:
        await message.answer("Укажите username получателя:\n<code>/recipient username</code>")


@dp.message(Command("add"))
async def add_user_cmd(message: Message):
    if not await check_access(message):
        return

    user_id = message.from_user.id
    if user_id not in MAIN_ADMIN_IDS and user_id not in regular_admins:
        return

    parts = message.text.split()
    if len(parts) > 1 and parts[1].isdigit():
        uid = int(parts[1])
        allowed_users.add(uid)
        save_users(allowed_users)
        await message.answer(f"Доступ предоставлен пользователю <code>{uid}</code>")
    else:
        await message.answer("Формат команды: <code>/add ID</code>")


@dp.message(Command("remove"))
async def remove_user_cmd(message: Message):
    if not await check_access(message):
        return

    user_id = message.from_user.id
    if user_id not in MAIN_ADMIN_IDS and user_id not in regular_admins:
        return

    parts = message.text.split()
    if len(parts) > 1 and parts[1].isdigit():
        uid = int(parts[1])

        if uid in MAIN_ADMIN_IDS:
            await message.answer("Нельзя удалить Главного администратора!")
            return

        if uid in regular_admins and user_id not in MAIN_ADMIN_IDS:
            await message.answer("Обычные админы не могут удалять других админов!")
            return

        allowed_users.discard(uid)
        save_users(allowed_users)
        await message.answer(f"Доступ закрыт пользователю <code>{uid}</code>")
    else:
        await message.answer("Формат команды: <code>/remove ID</code>")


@dp.message(Command("addadmin"))
async def add_admin_cmd(message: Message):
    if not await check_access(message):
        return

    if message.from_user.id not in MAIN_ADMIN_IDS:
        return

    parts = message.text.split()
    if len(parts) > 1 and parts[1].isdigit():
        uid = int(parts[1])
        regular_admins.add(uid)
        save_admins(regular_admins)
        await message.answer(f"Администратор <code>{uid}</code> успешно добавлен!")
    else:
        await message.answer("Формат команды: <code>/addadmin ID</code>")


@dp.message(Command("removeadmin"))
async def remove_admin_cmd(message: Message):
    if not await check_access(message):
        return

    if message.from_user.id not in MAIN_ADMIN_IDS:
        return

    parts = message.text.split()
    if len(parts) > 1 and parts[1].isdigit():
        uid = int(parts[1])
        if uid in MAIN_ADMIN_IDS:
            await message.answer("Нельзя снять Главного администратора!")
            return
        regular_admins.discard(uid)
        save_admins(regular_admins)
        await message.answer(f"Администратор <code>{uid}</code> успешно снят!")
    else:
        await message.answer("Формат команды: <code>/removeadmin ID</code>")


@dp.message(Command("lock"))
async def toggle_maintenance_cmd(message: Message):
    if not await check_access(message):
        return

    global maintenance_mode
    if message.from_user.id not in MAIN_ADMIN_IDS:
        return

    maintenance_mode = not maintenance_mode
    save_maintenance(maintenance_mode)

    if maintenance_mode:
        await message.answer("🔒 <b>Технический режим ВКЛЮЧЕН.</b>\nДоступ закрыт для всех, кроме главных админов.")
    else:
        await message.answer("🔓 <b>Технический режим ВЫКЛЮЧЕН.</b>\nДоступ открыт всем авторизованным пользователям.")


@dp.message(Command("orders"))
async def orders_cmd(message: Message):
    if not await check_access(message):
        return

    if not orders:
        await message.answer("📋 Заказов пока нет.")
        return

    icons = {
        "pending": "⏳",
        "accepted": "✅",
        "completed": "🏁",
        "cancelled": "❌",
        "failed": "❌",
    }

    lines = ["📋 <b>Заказы:</b>\n"]

    for oid, order in orders.items():
        if order.get("user_id") == message.from_user.id or message.from_user.id in MAIN_ADMIN_IDS or message.from_user.id in regular_admins:
            lines.append(
                f"{icons.get(order['status'], '❓')} "
                f"<code>{h(oid)}</code> · "
                f"{h(display_nft(order['nft_name']))}\n"
                f"Сумма: <b>{order['amount']} "
                f"{h(currency_label(order['currency'], order.get('language', 'ru')))}</b>\n"
                f"Статус: {h(order['status'])}\n"
            )

    await message.answer("\n".join(lines))


async def create_offer(
    chat_id: int,
    user_id: int,
    business_id: Optional[str],
    parsed: dict,
):
    oid = order_id()
    now = datetime.now()

    order = {
        **parsed,
        "user_id": user_id,
        "status": "pending",
        "chat_id": chat_id,
        "business_connection_id": business_id,
        "created_at": now,
        "expires_at": now + timedelta(hours=6),
    }
    orders[oid] = order

    nft_name = parsed["nft_name"]
    nft_title = h(display_nft(nft_name))
    url = nft_url(nft_name)
    amount = parsed["amount"]
    lang = parsed.get("language", "ru").lower()
    is_en = lang in ("en", "eng", "english")
    currency = h(currency_label(parsed["currency"], lang))

    if is_en:
        text = (
            "<b>Telegram</b>\n"
            f"<b><a href=\"{h(url)}\">{nft_title}</a></b>\n\n"
            "✈️ An offer has been sent to you:\n"
            f"⭐ <b>{amount} {currency}</b>\n\n"
            "⏰ Offer duration: 6 hours.\n"
            "Click \"Accept\" to proceed.\n\n"
            "The bot does not verify payment and NFT transfer."
        )
        keyboard = [
            [
                InlineKeyboardButton(
                    text="⊗ Decline",
                    callback_data=f"decline_{oid}",
                ),
                InlineKeyboardButton(
                    text="⊙ Accept",
                    callback_data=f"accept_{oid}",
                ),
            ]
        ]
    else:
        text = (
            "<b>Telegram</b>\n"
            f"<b><a href=\"{h(url)}\">{nft_title}</a></b>\n\n"
            "✈️ Вам направлено предложение:\n"
            f"⭐ <b>{amount} {currency}</b>\n\n"
            "⏰ Срок предложения: 6 часов.\n"
            "Нажмите «Принять» для продолжения.\n\n"
            "Оплату и передачу NFT бот не проверяет."
        )
        keyboard = [
            [
                InlineKeyboardButton(
                    text="⊗ Отклонить",
                    callback_data=f"decline_{oid}",
                ),
                InlineKeyboardButton(
                    text="⊙ Принять",
                    callback_data=f"accept_{oid}",
                ),
            ]
        ]

    preview = LinkPreviewOptions(
        is_disabled=False,
        url=url,
        show_above_text=True,
        prefer_large_media=True,
    )

    await send_order_message(
        order,
        text,
        keyboard,
        link_preview_options=preview,
    )

    log.info("Создан оффер %s для NFT %s", oid, nft_name)


@dp.business_message(F.text)
async def business_message(message: Message):
    if not await check_access(message):
        return

    parsed = parse_buy(message.text or "")

    if not parsed or not message.business_connection_id:
        return

    try:
        await bot.delete_business_messages(
            business_connection_id=message.business_connection_id,
            message_ids=[message.message_id],
        )
    except (TelegramAPIError, AttributeError) as exc:
        log.warning("Не удалось удалить исходное сообщение: %s", exc)

    try:
        await create_offer(
            message.chat.id,
            message.from_user.id,
            message.business_connection_id,
            parsed,
        )
    except TelegramAPIError:
        log.exception("Не удалось отправить Business-оффер")


@dp.message(F.chat.type == "private", F.text, ~F.text.startswith("/"))
async def private_text(message: Message):
    if not await check_access(message):
        return

    parsed = parse_buy(message.text or "")

    if parsed:
        await create_offer(message.chat.id, message.from_user.id, None, parsed)


async def delete_offer_message(query: CallbackQuery, order: dict):
    if not query.message:
        return

    business_id = order.get("business_connection_id")
    try:
        if business_id:
            await bot.delete_business_messages(
                business_connection_id=business_id,
                message_ids=[query.message.message_id],
            )
        else:
            await bot.delete_message(
                chat_id=query.message.chat.id,
                message_id=query.message.message_id,
            )
    except TelegramAPIError:
        log.exception("Не удалось удалить сообщение")


@dp.callback_query(F.data == "set_recipient")
async def set_recipient_cb(query: CallbackQuery):
    if not is_allowed(query.from_user.id):
        return

    await query.answer()

    if query.message:
        await query.message.answer(
            "Чтобы изменить получателя, отправьте команду:\n"
            "<code>/recipient ваш_username</code>"
        )


@dp.callback_query(F.data.startswith("accept_"))
async def accept(query: CallbackQuery):
    if not is_allowed(query.from_user.id):
        return

    oid = (query.data or "")[7:]
    order = orders.get(oid)

    if not order or order["status"] != "pending":
        await query.answer(
            "Заказ не найден или уже обработан",
            show_alert=True,
        )
        return

    await query.answer()
    order["status"] = "accepted"
    await delete_offer_message(query, order)

    creator_id = order.get("user_id")
    raw_recipient = user_recipients.get(creator_id, "")
    lang = order.get("language", "ru").lower()
    is_en = lang in ("en", "eng", "english")
    recipient_tag = f"@{raw_recipient.lstrip('@')}" if raw_recipient else ("@not_specified" if is_en else "@не указан")

    nft_title = h(display_nft(order["nft_name"]))
    currency = h(currency_label(order["currency"], lang))
    amount = order["amount"]

    if is_en:
        text = (
            "💸 <b>NFT Deal</b>\n\n"
            f"Order #{h(oid)}\n\n"
            f"The buyer has reserved {amount} {currency}.\n"
            "Crediting upon transfer.\n\n"
            "Instructions:\n"
            f"1. Send gift to: {h(recipient_tag)}\n"
            f"2. Click \"Send gift\" and select {nft_title}\n"
            "3. Confirm\n\n"
            "⚠️ Transferring to someone else — cancellation.\n\n"
            f"Payment {amount} {currency} instantly.\n\n"
            "Reserve 24h."
        )
        keyboard = []
        if raw_recipient:
            keyboard.append([
                InlineKeyboardButton(
                    text="Send gift",
                    url=f"tg://send_gift?to={quote(raw_recipient.lstrip('@'), safe='')}",
                )
            ])
        keyboard.append([
            InlineKeyboardButton(
                text="Confirm",
                callback_data=f"confirm_{oid}",
            )
        ])
    else:
        text = (
            "💸 <b>Сделка NFT</b>\n\n"
            f"Заказ #{h(oid)}\n\n"
            f"Покупатель зарезервировал {amount} {currency}.\n"
            "Зачисление после передачи.\n\n"
            "Инструкция:\n"
            f"1. Передайте подарок: {h(recipient_tag)}\n"
            f"2. Нажмите «Передать подарок» и выберите {nft_title}\n"
            "3. потвердите\n\n"
            "⚠️ Передача другому — аннулирование.\n\n"
            f"Оплата {amount} {currency} моментально.\n\n"
            "Резерв 24ч."
        )
        keyboard = []
        if raw_recipient:
            keyboard.append([
                InlineKeyboardButton(
                    text="Передать подарок",
                    url=f"tg://send_gift?to={quote(raw_recipient.lstrip('@'), safe='')}",
                )
            ])
        keyboard.append([
            InlineKeyboardButton(
                text="Подтвердить",
                callback_data=f"confirm_{oid}",
            )
        ])

    await send_order_message(order, text, keyboard)


@dp.callback_query(F.data.startswith("decline_"))
async def decline(query: CallbackQuery):
    if not is_allowed(query.from_user.id):
        return

    oid = (query.data or "")[8:]
    order = orders.get(oid)

    if not order or order["status"] != "pending":
        await query.answer(
            "Заказ не найден или уже обработан",
            show_alert=True,
        )
        return

    await query.answer()
    order["status"] = "cancelled"
    await delete_offer_message(query, order)

    lang = order.get("language", "ru").lower()
    is_en = lang in ("en", "eng", "english")

    decline_text = "❌ Offer declined." if is_en else "❌ Предложение отклонено."

    await send_order_message(
        order,
        decline_text,
    )


@dp.callback_query(F.data.startswith("confirm_"))
async def confirm(query: CallbackQuery):
    if not is_allowed(query.from_user.id):
        return

    oid = (query.data or "")[8:]
    order = orders.get(oid)

    if not order:
        await query.answer(
            "Заказ не найден",
            show_alert=True,
        )
        return

    await query.answer()

    lang = order.get("language", "ru").lower()
    is_en = lang in ("en", "eng", "english")

    err_text = (
        "❌ <b>Error</b>\n\nNothing transferred. NFT not found."
        if is_en
        else "❌ <b>Ошибка</b>\n\nНичего не передано. NFT не найден."
    )

    await send_order_message(
        order,
        err_text,
    )


async def main():
    if not TOKEN:
        raise RuntimeError(
            "Не задан BOT_TOKEN. Укажи токен через переменную окружения."
        )

    await dp.start_polling(
        bot,
        allowed_updates=dp.resolve_used_update_types(),
    )


if __name__ == "__main__":
    asyncio.run(main())
