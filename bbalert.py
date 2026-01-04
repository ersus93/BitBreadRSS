import logging
import asyncio
import warnings
import os
import sys
import platform
import html
import json
import traceback
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ConversationHandler
from telegram.constants import ParseMode
from telegram import ReplyKeyboardMarkup, KeyboardButton, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.warnings import PTBUserWarning
warnings.filterwarnings("ignore", category=PTBUserWarning)
from core.config import TOKEN, ADMIN_ID, BOT_VERSION
from services.monitor import RSSMonitor
from handlers.menus import start, help_command, menu_handler
from handlers.admin import stats, logs_command, ms_handler
from handlers.conversation import (
    start_add_channel, process_channel, WAITING_CHANNEL,
    start_add_feed, process_feed_url, save_feed_channel, WAITING_FEED_URL, WAITING_FEED_CHANNEL,
    start_edit_template, save_template, WAITING_TEMPLATE, cancel, start_set_rhash, save_rhash, WAITING_RHASH
)


logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Manejador global de errores."""
    logging.error(msg="Excepción capturada:", exc_info=context.error)
    
    if isinstance(update, Update) and update.effective_message:
        text = "❌ Ocurrió un error interno. Intenta de nuevo."
        try:
            if update.callback_query:
                await update.callback_query.answer(text, show_alert=True)
            else:
                await update.effective_message.reply_text(text)
        except:
            pass

async def post_init(application):
    """Acciones al iniciar."""
    monitor = RSSMonitor(application.bot)
    application.bot_data['monitor'] = monitor
    application.bot_data['monitor_task'] = asyncio.create_task(monitor.start())
    
    if ADMIN_ID:
        pid = os.getpid()
        py_ver = platform.python_version()
        msg = (
            f"📰 <b>BitBread Online</b>\n"
            f"————————————————————\n"
            f"🤖 <b>Versión:</b> <i>{BOT_VERSION}</i>\n"
            f"🪪 <b>PID:</b> <code>{pid}</code>\n"
            f"🐍 <b>Python:</b> v{py_ver}\n"
        )
        try:
            await application.bot.send_message(chat_id=ADMIN_ID, text=msg, parse_mode=ParseMode.HTML)
        except Exception as e:
            logging.error(f"Error enviando mensaje de inicio: {e}")

async def post_shutdown(application):
    logging.info("🛑 Deteniendo monitor RSS...")
    monitor = application.bot_data.get('monitor')
    if monitor:
        monitor.running = False
    
    task = application.bot_data.get('monitor_task')
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    logging.info("✅ Bot detenido correctamente.")

def main():
    if not TOKEN:
        print("❌ ERROR: Configura el TELEGRAM_TOKEN en el archivo .env")
        return

    # IMPORTANTE: concurrent_updates=True permite que el bot responda
    # a botones mientras el monitor está trabajando.
    app = ApplicationBuilder().token(TOKEN)\
        .post_init(post_init)\
        .post_shutdown(post_shutdown)\
        .concurrent_updates(True)\
        .build()
    
    app.add_error_handler(error_handler)
    
    conv_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_add_channel, pattern="^add_channel$"),
            CallbackQueryHandler(start_add_feed, pattern="^add_feed$"),
            CallbackQueryHandler(start_edit_template, pattern="^tmpl_feed_"),
            CallbackQueryHandler(start_set_rhash, pattern="^set_iv_")
        ],
        states={
            WAITING_RHASH: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_rhash)],
            WAITING_CHANNEL: [MessageHandler(filters.ALL & ~filters.COMMAND, process_channel)],
            WAITING_FEED_URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_feed_url)],
            WAITING_FEED_CHANNEL: [CallbackQueryHandler(save_feed_channel, pattern="^sel_ch_")],
            WAITING_TEMPLATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_template)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CallbackQueryHandler(cancel, pattern="^cancel_conv$") 
        ]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Text("🏠 Mostrar menú inicio"), start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("logs", logs_command))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CallbackQueryHandler(stats, pattern="^admin_refresh_stats$"))
    app.add_handler(ms_handler)
    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(menu_handler))

    app.run_polling()

if __name__ == "__main__":
    main()