import os
import time
import psutil 
import platform
import sys
import asyncio
import warnings
from datetime import timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, MessageHandler, filters, CallbackQueryHandler
from telegram.constants import ParseMode
from telegram.warnings import PTBUserWarning
warnings.filterwarnings("ignore", category=PTBUserWarning)
from core.database import DB
from core.config import ADMIN_ID, BOT_VERSION
from utils.logger import LOG_FILE_PATH

# --- ESTADOS DE LA CONVERSACIÓN ---
AWAITING_CONTENT = 1
AWAITING_CONFIRMATION = 2
AWAITING_ADDITIONAL_TEXT = 3
AWAITING_ADDITIONAL_PHOTO = 4

def is_admin(user_id):
    return str(user_id) == str(ADMIN_ID)


# --- FUNCIÓN AUXILIAR DE FORMATO ---
def _get_progress_bar(percent, length=10):
    """Genera una barra de progreso visual"""
    filled = int(length * percent / 100)
    return "▓" * filled + "░" * (length - filled)

# --- COMANDOS DE INFORMACIÓN (STATS / LOGS) ---
# Inicializamos el proceso global para monitoreo de CPU
proc_global = psutil.Process(os.getpid())
# Hacemos una primera lectura "falsa" al arrancar para iniciar el contador
proc_global.cpu_percent(interval=None)

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Panel de Control Avanzado (Dashboard)
    """
    user_id = update.effective_user.id
    if str(user_id) != str(ADMIN_ID): return

    # 1. Obtener métricas del Sistema (Infraestructura)
    process = psutil.Process(os.getpid())
    
    # Cálculo de Uptime
    uptime_seconds = time.time() - process.create_time()
    uptime_str = str(timedelta(seconds=int(uptime_seconds)))
    
    # Recursos
    mem_usage = process.memory_info().rss / 1024 / 1024 # MB
    cpu_percent = proc_global.cpu_percent(interval=None) # Instantáneo
    
    # 2. Obtener métricas de Negocio (Base de Datos)
    s = await DB.get_stats()
    
    # Cálculos derivados
    total_ops = s['total_sent'] + s['total_errors']
    success_rate = (s['total_sent'] / total_ops * 100) if total_ops > 0 else 100
    error_rate = 100 - success_rate
    
    # Estado de Salud (Semáforo)
    if error_rate < 5: status_icon = "🟢 Excelente"
    elif error_rate < 20: status_icon = "🟠 Atento"
    else: status_icon = "🔴 Crítico"

    # 3. Construcción del Mensaje (HTML)
    msg = (
        f"<b>📊 BITBREAD CONTROL CENTER</b>\n"
        f"———————————————————\n\n"
        
        f"<b>🖥️ ESTADO DEL SISTEMA</b>\n"
        f"├ <b>Versión:</b> <i>v{BOT_VERSION}</i>\n"
        f"├ <b>Estado:</b> {status_icon}\n"
        f"├ <b>Uptime:</b> <code>{uptime_str}</code>\n"
        f"├ <b>RAM:</b> <code>{mem_usage:.1f} MB</code>\n"
        f"└ <b>CPU:</b> <code>{cpu_percent}%</code>\n\n"
        
        f"<b>📡 RED DE NOTICIAS</b>\n"
        f"├ <b>Usuarios:</b> {s['users']}\n"
        f"├ <b>Canales:</b> {s['channels']}\n"
        f"└ <b>Feeds Activos:</b> {s['feeds_active']} / {s['feeds']}\n\n"
        
        f"<b>📈 RENDIMIENTO (Ciclo de vida)</b>\n"
        f"├ <b>Noticias Enviadas:</b> {s['total_sent']}\n"
        f"├ <b>Errores/Bloqueos:</b> {s['total_errors']}\n"
        f"└ <b>Tasa de Éxito:</b> {success_rate:.1f}%\n"
        f"   [{_get_progress_bar(success_rate)}] \n\n"
        
        f"<b>💾 ALMACENAMIENTO</b>\n"
        f"└ <b>DB Size:</b> <code>{s['db_size']:.2f} KB</code>"
    )
    
    # Botón de refresco
    kb = [[InlineKeyboardButton("🔄 Actualizar Datos", callback_data="admin_refresh_stats")]]
    reply_markup = InlineKeyboardMarkup(kb)

    if update.callback_query:
        # Si viene de un botón, editamos para evitar spam
        try:
            await update.callback_query.edit_message_text(msg, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
        except Exception:
            pass # Si el contenido es igual, Telegram da error, lo ignoramos
    else:
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML, reply_markup=reply_markup)

async def logs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra datos técnicos y las últimas líneas del log."""
    if not is_admin(update.effective_user.id): return

    process = psutil.Process(os.getpid())
    ram_usage = process.memory_info().rss / 1024 / 1024  # en MB
    
    tech_info = (
        "⚙️ *Datos Técnicos*\n"
        f"🆔 *PID:* `{os.getpid()}`\n"
        f"🧠 *RAM:* `{ram_usage:.2f} MB`\n"
        f"📂 *Ruta Log:* `{LOG_FILE_PATH}`\n\n"
    )

    log_tail = ""
    if os.path.exists(LOG_FILE_PATH):
        with open(LOG_FILE_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()
            log_tail = "".join(lines[-25:])
    else:
        log_tail = "Archivo de log no encontrado."

    full_msg = f"{tech_info}📝 *Últimos registros:*\n```text\n{log_tail}\n```"
    if len(full_msg) > 4000: full_msg = full_msg[-4000:]

    await update.message.reply_text(full_msg, parse_mode=ParseMode.MARKDOWN)

# --- SISTEMA DE MENSAJES MASIVOS AVANZADO (/ms) ---

async def ms_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inicia la conversación para el mensaje masivo."""
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END

    # Limpiamos datos previos
    context.user_data.pop('ms_text', None)
    context.user_data.pop('ms_photo_id', None)

    await update.message.reply_text(
        "✍️ *Creación de Mensaje Masivo*\n\n"
        "Envía el contenido principal:\n"
        "• Solo Texto\n"
        "• Solo Imagen\n"
        "• Imagen con Texto (Caption)\n\n"
        "Usa /cancel para salir.",
        parse_mode=ParseMode.MARKDOWN
    )
    return AWAITING_CONTENT

async def handle_initial_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Captura el primer contenido enviado."""
    message = update.message
    
    if message.text:
        context.user_data['ms_text'] = message.text_html # Guardamos como HTML para mantener formato
        
        kb = [
            [InlineKeyboardButton("🖼️ Añadir Imagen", callback_data="ms_add_photo")],
            [InlineKeyboardButton("🚀 Enviar Solo Texto", callback_data="ms_send_final")],
            [InlineKeyboardButton("❌ Cancelar", callback_data="ms_cancel")]
        ]
        await message.reply_text(
            "✅ *Texto recibido.*\n¿Quieres adjuntar una imagen o enviar ya?", 
            reply_markup=InlineKeyboardMarkup(kb),
            parse_mode=ParseMode.MARKDOWN
        )

    elif message.photo:
        context.user_data['ms_photo_id'] = message.photo[-1].file_id
        if message.caption:
            context.user_data['ms_text'] = message.caption_html # Guardamos caption HTML

        kb = [
            [InlineKeyboardButton("✍️ Editar/Añadir Texto", callback_data="ms_add_text")],
            [InlineKeyboardButton("🚀 Enviar Ahora", callback_data="ms_send_final")],
            [InlineKeyboardButton("❌ Cancelar", callback_data="ms_cancel")]
        ]
        await message.reply_text(
            "✅ *Imagen recibida.*\n¿Quieres modificar el texto o enviar?",
            reply_markup=InlineKeyboardMarkup(kb),
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await message.reply_text("⚠️ Por favor, envía texto o una imagen.")
        return AWAITING_CONTENT

    return AWAITING_CONFIRMATION

async def handle_confirmation_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestiona los botones del menú de confirmación."""
    query = update.callback_query
    await query.answer()
    choice = query.data

    if choice == "ms_add_text":
        await query.edit_message_text("✍️ *Envía el nuevo texto/pie de foto:*", parse_mode=ParseMode.MARKDOWN)
        return AWAITING_ADDITIONAL_TEXT
        
    elif choice == "ms_add_photo":
        await query.edit_message_text("🖼️ *Envía la imagen que quieres adjuntar:*", parse_mode=ParseMode.MARKDOWN)
        return AWAITING_ADDITIONAL_PHOTO
        
    elif choice == "ms_send_final":
        return await send_broadcast(query, context)
        
    elif choice == "ms_cancel":
        await query.edit_message_text("❌ Operación cancelada.")
        context.user_data.clear()
        return ConversationHandler.END

async def receive_additional_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['ms_text'] = update.message.text_html
    kb = [[InlineKeyboardButton("🚀 Enviar Todo", callback_data="ms_send_final")]]
    await update.message.reply_text("✅ Texto actualizado. Pulsa para enviar.", reply_markup=InlineKeyboardMarkup(kb))
    return AWAITING_CONFIRMATION

async def receive_additional_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['ms_photo_id'] = update.message.photo[-1].file_id
    kb = [[InlineKeyboardButton("🚀 Enviar Todo", callback_data="ms_send_final")]]
    await update.message.reply_text("✅ Imagen actualizada. Pulsa para enviar.", reply_markup=InlineKeyboardMarkup(kb))
    return AWAITING_CONFIRMATION

async def send_broadcast(query, context: ContextTypes.DEFAULT_TYPE):
    """Ejecuta el envío masivo usando la base de datos de BitBread."""
    await query.edit_message_text("⏳ *Iniciando difusión...* Por favor espera.", parse_mode=ParseMode.MARKDOWN)
    
    text = context.user_data.get('ms_text')
    photo_id = context.user_data.get('ms_photo_id')
    
    # Obtenemos usuarios de TU base de datos
    user_ids = await DB.get_all_user_ids()
    
    exitos = 0
    fallidos = 0
    bloqueados = 0
    
    for uid in user_ids:
        try:
            if photo_id:
                await context.bot.send_photo(
                    chat_id=uid, 
                    photo=photo_id, 
                    caption=text, 
                    parse_mode=ParseMode.HTML
                )
            elif text:
                await context.bot.send_message(
                    chat_id=uid, 
                    text=text, 
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=False
                )
            exitos += 1
            await asyncio.sleep(0.05) # Evitar flood limits de Telegram
            
        except Exception as e:
            if "Forbidden" in str(e) or "blocked" in str(e):
                bloqueados += 1
            else:
                fallidos += 1
                
    msg_final = (
        f"✅ *Difusión Completada*\n\n"
        f"📤 *Total:* {len(user_ids)}\n"
        f"✅ *Recibidos:* {exitos}\n"
        f"🚫 *Bloqueados:* {bloqueados}\n"
        f"⚠️ *Errores:* {fallidos}"
    )
    
    # Enviamos el reporte al admin (o editamos el mensaje anterior)
    try:
        await query.message.reply_text(msg_final, parse_mode=ParseMode.MARKDOWN)
    except:
        await context.bot.send_message(chat_id=query.from_user.id, text=msg_final, parse_mode=ParseMode.MARKDOWN)

    context.user_data.clear()
    return ConversationHandler.END

async def ms_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Cancelado.")
    context.user_data.clear()
    return ConversationHandler.END

# Definición del Handler
ms_handler = ConversationHandler(
    entry_points=[CommandHandler("ms", ms_start)],
    states={
        AWAITING_CONTENT: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_initial_content),
            MessageHandler(filters.PHOTO, handle_initial_content)
        ],
        AWAITING_CONFIRMATION: [CallbackQueryHandler(handle_confirmation_choice)],
        AWAITING_ADDITIONAL_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_additional_text)],
        AWAITING_ADDITIONAL_PHOTO: [MessageHandler(filters.PHOTO, receive_additional_photo)],
    },
    fallbacks=[CommandHandler("cancel", ms_cancel)]
)