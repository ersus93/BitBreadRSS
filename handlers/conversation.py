from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import ConversationHandler, ContextTypes
from telegram.constants import ParseMode
from core.database import DB
from services.parser import RSSParser
from services.resolver import RSSResolver
from handlers.menus import show_feed_options, show_channels_menu, start

# Estados
WAITING_CHANNEL = 1
WAITING_FEED_URL = 2
WAITING_FEED_CHANNEL = 3
WAITING_TEMPLATE = 4

def get_cancel_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancelar y Volver", callback_data="cancel_conv")]])

# --- AÑADIR CANAL ---
async def start_add_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "➕ *Nuevo Canal*\n\n"
        "1. Añade al bot como *Admin* en tu canal.\n"
        "2. *Reenvía* un mensaje del canal aquí o escribe el ID.\n",
        reply_markup=get_cancel_kb(),
        parse_mode=ParseMode.MARKDOWN
    )
    return WAITING_CHANNEL

async def process_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg: return WAITING_CHANNEL
    
    if msg.text and msg.text.lower() == '/cancel':
        await msg.reply_text("❌ Operación cancelada.")
        return ConversationHandler.END

    cid, title = None, None
    
    if msg.forward_origin:
        origin = msg.forward_origin
        if hasattr(origin, 'chat'):
            cid = origin.chat.id
            title = origin.chat.title
    
    elif msg.text:
        text = msg.text.strip()
        if text.startswith("-100") or text.startswith("@"):
            try:
                chat = await context.bot.get_chat(text)
                cid = chat.id
                title = chat.title
            except Exception as e:
                await msg.reply_text(f"❌ No encontré el canal. Asegúrate de que el bot sea admin.\nError: {e}")
                return WAITING_CHANNEL

    if not cid:
        await msg.reply_text("❌ No detecté un canal válido. Reenvía un mensaje del canal o escribe su ID.")
        return WAITING_CHANNEL

    try:
        member = await context.bot.get_chat_member(cid, context.bot.id)
        if member.status not in ['administrator', 'creator']:
            await msg.reply_text(f"⚠️ El bot detecta el canal '{title}', pero NO es *Administrador*. Dale permisos y vuelve a intentarlo.")
            return WAITING_CHANNEL
    except Exception as e:
        await msg.reply_text(f"⚠️ Error verificando permisos: {e}")
        return WAITING_CHANNEL
    
    result = await DB.add_channel(update.effective_user.id, cid, title)
    
    if result == "success":
        await msg.reply_text(f"✅ Canal *{title}* vinculado correctamente.")
    elif result == "exist_global":
        await msg.reply_text(f"⛔ *Error:* El canal *{title}* ya está registrado en el bot (por ti u otro usuario).\nNo se permiten canales duplicados para evitar saturación.")
    else:
        await msg.reply_text(f"⚠️ Ocurrió un error desconocido guardando el canal.")
    
    await show_channels_menu(update, context)
    return ConversationHandler.END

# --- AÑADIR FEED ---
async def start_add_feed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_data = await DB.get_user(update.effective_user.id) # Async call
    if not user_data['channels']:
        await query.answer("⚠️ ¡Primero debes añadir un canal!", show_alert=True)
        return ConversationHandler.END
        
    await query.edit_message_text(
        "🔗 *Nuevo Feed RSS*\n\n"
        "Envía ahora la *URL del Feed* que quieres monitorear.",
        reply_markup=get_cancel_kb(),
        parse_mode=ParseMode.MARKDOWN
    )
    return WAITING_FEED_URL

async def process_feed_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    url = msg.text.strip()

    if url.lower() == '/cancel':
        await msg.reply_text("❌ Operación cancelada.")
        return ConversationHandler.END
    
    # Notificar al usuario que estamos "Pensando"
    status_msg = await msg.reply_text("🔍 <b>Analizando sitio...</b>\nBuscando feeds RSS y validando acceso.", parse_mode=ParseMode.HTML)
    
    # --- FASE DE RESOLUCIÓN (Auditoria: Discovery Layer) ---
    resolved_url, title, error = await RSSResolver.find_best_feed(url)
    
    if error or not resolved_url:
        await status_msg.edit_text(
            f"❌ <b>No se encontró un feed.</b>\n"
            f"Motivo: {error}\n\n"
            f"Intenta con el enlace directo al RSS o escribe /cancel.",
            parse_mode=ParseMode.HTML
        )
        return WAITING_FEED_URL 
    
    # Obtenemos el hash inicial para evitar spam del histórico
    # Como ya resolvimos la URL, hacemos un parse rápido para sacar el hash
    parsed, _ = await RSSParser.parse(resolved_url)
    first_hash = parsed['entries'][0]['hash'] if parsed and parsed['entries'] else "init"

    # Guardamos en contexto temporal
    context.user_data['temp_feed'] = {
        "original_url": url,
        "resolved_url": resolved_url,
        "title": title or parsed['title'],
        "hash": first_hash
    }
    
    # --- SELECCIÓN DE CANAL ---
    user_data = await DB.get_user(update.effective_user.id)
    kb = []
    for ch in user_data['channels']:
        kb.append([InlineKeyboardButton(f"📢 {ch['title']}", callback_data=f"sel_ch_{ch['id']}")])
    
    kb.append([InlineKeyboardButton("❌ Cancelar", callback_data="cancel_process")])

    text_success = (
        f"✅ <b>Feed Detectado</b>\n"
        f"🗞 <b>Fuente:</b> {title}\n"
        f"🔗 <b>RSS URL:</b> {resolved_url}\n\n"
        f"¿A qué canal quieres enviar las noticias?"
    )

    await status_msg.edit_text(
        text_success,
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode=ParseMode.HTML
    )
    return WAITING_FEED_CHANNEL

async def save_feed_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    if data == "cancel_process":
        await query.edit_message_text("❌ Operación cancelada.")
        return ConversationHandler.END

    try:
        cid = int(data.replace("sel_ch_", ""))
    except:
        await query.edit_message_text("❌ Error interno.")
        return ConversationHandler.END
    
    temp = context.user_data.get('temp_feed')
    if not temp:
        await query.edit_message_text("❌ Sesión expirada.")
        return ConversationHandler.END

    # Usamos el nuevo método de DB con resolved_url
    new_feed = await DB.add_feed(
        user_id=query.from_user.id, 
        original_url=temp['original_url'],
        resolved_url=temp['resolved_url'],
        channel_id=cid, 
        source_title=temp['title'], 
        last_hash=temp['hash']
    )
    
    if new_feed:
        await show_feed_options(update, context, new_feed['id'])
    else:
        await query.edit_message_text("⚠️ Este feed ya está configurado.")
        
    return ConversationHandler.END

# --- EDITAR PLANTILLA ---
async def start_edit_template(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    fid = query.data.split("_")[2]
    context.user_data['edit_fid'] = fid
    
    await query.edit_message_text(
        "📝 *Editar Plantilla*\n\n"
        "Envía el nuevo formato en un mensaje. Variables disponibles:\n"
        "`#title#` - Título\n"
        "`#link#` - Enlace\n"
        "`#description#` - Resumen\n"
        "`#source#` - Fuente\n"
        "`#sourceiv#` - Enlace Instant View ⚡\n\n"
        "⚠️ *Soporta HTML* (negrita `<b>`, cursiva `<i>`, enlaces `<a href='...'>`).\n\n"
        "Escribe /cancel para cancelar.",
        reply_markup=get_cancel_kb(),
        parse_mode=ParseMode.MARKDOWN
    )
    return WAITING_TEMPLATE

async def save_template(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if msg.text and msg.text.lower() == '/cancel':
        await msg.reply_text("Operación cancelada.")
        return ConversationHandler.END

    fid = context.user_data.get('edit_fid')
    # Async call
    if await DB.update_template(update.effective_user.id, fid, msg.text):
        await msg.reply_text("✅ Plantilla guardada exitosamente.")
        await show_feed_options(update, context, fid)
    else:
        await msg.reply_text("❌ Error: No se encontró el feed.")
        
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer("Operación cancelada")
        await start(update, context)
    else:
        await update.message.reply_text("❌ Operación cancelada.")
        
    return ConversationHandler.END

# Nuevo Estado
WAITING_RHASH = 5

# --- CONFIGURAR INSTANT VIEW ---
async def start_set_rhash(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    fid = query.data.split("_")[2]
    context.user_data['edit_fid'] = fid
    
    await query.edit_message_text(
        "⚡ *Configurar Instant View*\n\n"
        "Envía el código *rhash* de tu plantilla de Telegram.\n"
        "_(Ejemplo: abcdef123456)_\n\n"
        "Si no sabes qué es esto, visita `instantview.telegram.org`.\n"
        "Envía 'none' para desactivarlo o /cancel para salir.",
        parse_mode=ParseMode.MARKDOWN
    )
    return WAITING_RHASH

async def save_rhash(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    rhash_input = msg.text.strip()

    if rhash_input.lower() == '/cancel':
        await msg.reply_text("Operación cancelada.")
        return ConversationHandler.END

    fid = context.user_data.get('edit_fid')
    
    # Validación básica (alfanumérico) [cite: 56]
    if not rhash_input.isalnum() and rhash_input.lower() != 'none':
        await msg.reply_text("⚠️ El rhash solo debe contener letras y números. Intenta de nuevo.")
        return WAITING_RHASH

    if await DB.update_feed_rhash(update.effective_user.id, fid, rhash_input):
        status = "desactivado" if rhash_input.lower() == 'none' else "activado"
        await msg.reply_text(f"✅ Instant View {status} correctamente.\nRecuerda usar `#sourceiv#` en tu plantilla.")
        await show_feed_options(update, context, fid)
    else:
        await msg.reply_text("❌ Error: No se encontró el feed.")
        
    return ConversationHandler.END