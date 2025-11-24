from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Iterable, List, Set

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import TelegramError
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    ChatMemberHandler,
    CommandHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .storage import ChatStore, ChatRecord

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

logger = logging.getLogger("broadcast-bot")

MESSAGE, SELECT = range(2)


class BotContext:
    def __init__(self, admin_id: int, chat_store: ChatStore) -> None:
        self.admin_id = admin_id
        self.chat_store = chat_store


def require_admin(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        bot_ctx: BotContext = context.bot_data["ctx"]
        user = update.effective_user
        if not user or user.id != bot_ctx.admin_id:
            target = update.effective_message or update.effective_chat
            if target:
                await target.reply_text("Команда доступна только владельцу бота.")
            return ConversationHandler.END if isinstance(context.application.handlers[0], ConversationHandler) else None
        return await func(update, context)

def build_selection_keyboard(records: Iterable[ChatRecord], selected: Set[int]) -> InlineKeyboardMarkup:
    buttons: List[List[InlineKeyboardButton]] = []
    for record in records:
        status = "✅" if record.chat_id in selected else "☑️"
        label = f"{status} {record.title}"
        buttons.append([InlineKeyboardButton(label[:60], callback_data=f"toggle:{record.chat_id}")])
    buttons.append(
        [
            InlineKeyboardButton("Отправить", callback_data="send"),
            InlineKeyboardButton("Отменить", callback_data="cancel"),
        ]
    )
    return InlineKeyboardMarkup(buttons)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Привет! Используй /broadcast для рассылки и /chats чтобы управлять списком чатов."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "/broadcast — запустить рассылку.\n"
        "/chats — показать список чатов.\n"
        "/enable <chat_id> — включить чат в рассылку по умолчанию.\n"
        "/disable <chat_id> — отключить чат.\n"
        "/forget <chat_id> — удалить чат из базы."
    )
async def list_chats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    bot_ctx: BotContext = context.bot_data["ctx"]
    rows = []
    for record in bot_ctx.chat_store.list_all():
        status = "ON" if record.enabled else "OFF"
        rows.append(f"{status} | {record.title} | {record.chat_id}")
    if not rows:
        await update.message.reply_text("Список чатов пуст. Добавь бота в нужные чаты.")
        return
    text = "\n".join(rows)
    await update.message.reply_text(text)


async def set_chat_enabled(update: Update, context: ContextTypes.DEFAULT_TYPE, *, enabled: bool) -> None:
    bot_ctx: BotContext = context.bot_data["ctx"]
    if not context.args:
        await update.message.reply_text("Укажи chat_id, например /enable -123456")
        return
    try:
        chat_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("chat_id должен быть числом")
        return
    updated = bot_ctx.chat_store.set_enabled(chat_id, enabled)
    if not updated:
        await update.message.reply_text("Чат не найден в базе")
        return
    status = "включён" if enabled else "отключён"
    await update.message.reply_text(f"Чат {chat_id} {status} для рассылок.")


async def forget_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    bot_ctx: BotContext = context.bot_data["ctx"]
    if not context.args:
        await update.message.reply_text("Укажи chat_id, например /forget -123456")
        return
    try:
        chat_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("chat_id должен быть числом")
        return
    bot_ctx.chat_store.remove(chat_id)
    await update.message.reply_text("Чат удалён из базы.")


async def broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Пришли сообщение, которое нужно разослать. Можно с медиа.")
    return MESSAGE


async def broadcast_capture(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    bot_ctx: BotContext = context.bot_data["ctx"]
    records = bot_ctx.chat_store.list_all()
    if not records:
        await update.message.reply_text("Нет чатов для рассылки. Добавь бота в чаты и попробуй снова.")
        return ConversationHandler.END
    context.user_data["source_chat_id"] = update.effective_chat.id
    context.user_data["source_message_id"] = update.message.message_id
    selected = {record.chat_id for record in records if record.enabled}
    if not selected:
        selected = {record.chat_id for record in records}
    context.user_data["selected"] = selected
    keyboard = build_selection_keyboard(records, selected)
    prompt = await update.message.reply_text(
        "Выбери чаты для рассылки (нажми Отправить когда готов).",
        reply_markup=keyboard,
    )
    context.user_data["selection_message_id"] = prompt.message_id
    return SELECT


async def broadcast_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    chat_id = int(query.data.split(":", 1)[1])
    selected: Set[int] = context.user_data.get("selected", set())
    if chat_id in selected:
        selected.remove(chat_id)
    else:
        selected.add(chat_id)
    bot_ctx: BotContext = context.bot_data["ctx"]
    keyboard = build_selection_keyboard(bot_ctx.chat_store.list_all(), selected)
    await query.edit_message_reply_markup(reply_markup=keyboard)
    return SELECT


async def broadcast_send(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    selected: Set[int] = context.user_data.get("selected", set())
    if not selected:
        await query.edit_message_text("Не выбрано ни одного чата, рассылка отменена.")
        return ConversationHandler.END
    src_chat = context.user_data.get("source_chat_id")
    src_message = context.user_data.get("source_message_id")
    success = 0
    failures: List[str] = []
    for chat_id in selected:
        try:
            await context.bot.copy_message(chat_id=chat_id, from_chat_id=src_chat, message_id=src_message)
            success += 1
        except TelegramError as exc:
            logger.exception("Не удалось отправить сообщение в чат %s", chat_id)
            failures.append(f"{chat_id}: {exc}")
    summary = [f"Сообщение отправлено в {success} чат(ов)."]
    if failures:
        summary.append("Ошибки:\n" + "\n".join(failures))
    await query.edit_message_text("\n".join(summary))
    context.user_data.clear()
    return ConversationHandler.END


async def broadcast_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        await update.callback_query.answer("Рассылка отменена")
        await update.callback_query.edit_message_text("Рассылка отменена.")
    else:
        await update.message.reply_text("Рассылка отменена.")
    context.user_data.clear()
    return ConversationHandler.END


async def handle_my_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.my_chat_member:
        return
    chat = update.effective_chat
    new_status = update.my_chat_member.new_chat_member.status
    bot_ctx: BotContext = context.bot_data["ctx"]
    if new_status in {"member", "administrator"}:
        record = bot_ctx.chat_store.upsert(chat_id=chat.id, title=chat.title or str(chat.id), chat_type=chat.type)
        logger.info("Бот добавлен в чат %s (%s)", record.title, record.chat_id)
    elif new_status in {"left", "kicked"}:
        bot_ctx.chat_store.remove(chat.id)
        logger.info("Бот удалён из чата %s", chat.id)


async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Неизвестная команда. Используй /help")


def build_application() -> Application:
    load_dotenv()
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("Не указан BOT_TOKEN")
    admin_id = os.getenv("ADMIN_USER_ID")
    if not admin_id:
        raise RuntimeError("Не указан ADMIN_USER_ID")
    admin_id_int = int(admin_id)
    store_path = Path(os.getenv("CHAT_STORE_PATH", "data/chats.json"))
    chat_store = ChatStore(store_path)
    app = ApplicationBuilder().token(token).build()
    app.bot_data["ctx"] = BotContext(admin_id_int, chat_store)

    app.add_handler(CommandHandler("start", start, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("help", help_command, filters=filters.ChatType.PRIVATE))

    admin_filter = filters.ChatType.PRIVATE & filters.User(user_id=admin_id_int)
    async def enable_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await set_chat_enabled(update, context, enabled=True)

    async def disable_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await set_chat_enabled(update, context, enabled=False)

    app.add_handler(CommandHandler("chats", list_chats, filters=admin_filter))
    app.add_handler(CommandHandler("enable", enable_command, filters=admin_filter))
    app.add_handler(CommandHandler("disable", disable_command, filters=admin_filter))
    app.add_handler(CommandHandler("forget", forget_chat, filters=admin_filter))

    conv = ConversationHandler(
        entry_points=[CommandHandler("broadcast", broadcast_start, filters=admin_filter)],
        states={
            MESSAGE: [MessageHandler(filters.ALL & filters.ChatType.PRIVATE, broadcast_capture)],
            SELECT: [
                CallbackQueryHandler(broadcast_toggle, pattern=r"^toggle:"),
                CallbackQueryHandler(broadcast_send, pattern="^send$"),
                CallbackQueryHandler(broadcast_cancel, pattern="^cancel$"),
            ],
        },
        fallbacks=[CommandHandler("cancel", broadcast_cancel, filters=admin_filter)],
    )
    app.add_handler(conv)

    app.add_handler(ChatMemberHandler(handle_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))

    app.add_handler(MessageHandler(filters.COMMAND, unknown))
    return app


def main() -> None:
    application = build_application()
    logger.info("Запускаю бота...")
    application.run_polling(close_loop=False)


if __name__ == "__main__":
    main()
