from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import ConversationHandler, ContextTypes
from telegram.constants import ParseMode
from core.database import DB
from services.parser import RSSParser
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
        "1. Añade al bot como **Admin** en tu canal.\n"
        "2. **Reenvía** un mensaje del canal aquí o escribe el ID.\n",
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
            await msg.reply_text(f"⚠️ El bot detecta el canal '{title}', pero NO es **Administrador**. Dale permisos y vuelve a intentarlo.")
            return WAITING_CHANNEL
    except Exception as e:
        await msg.reply_text(f"⚠️ Error verificando permisos: {e}")
        return WAITING_CHANNEL
    
    if await DB.add_channel(update.effective_user.id, cid, title): # Async call
        await msg.reply_text(f"✅ Canal **{title}** vinculado correctamente.")
    else:
        await msg.reply_text(f"⚠️ El canal **{title}** ya estaba vinculado.")
    
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
        "Envía ahora la **URL del Feed** que quieres monitorear.",
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

    status_msg = await msg.reply_text("⏳ Analizando feed, espera un momento...")
    
    parsed, error = await RSSParser.parse(url)
    if error:
        await status_msg.edit_text(f"❌ **Error:** No se pudo leer el RSS.\nMotivo: {error}\n\nIntenta con otro link o escribe /cancel.")
        return WAITING_FEED_URL 
        
    context.user_data['temp_feed'] = {
        "url": url, 
        "title": parsed['title'],
        "hash": parsed['entries'][0]['hash'] if parsed['entries'] else "init"
    }
    
    user_data = await DB.get_user(update.effective_user.id) # Async Call
    kb = []
    for ch in user_data['channels']:
        kb.append([InlineKeyboardButton(f"📢 {ch['title']}", callback_data=f"sel_ch_{ch['id']}")])
    
    kb.append([InlineKeyboardButton("❌ Cancelar", callback_data="cancel_process")])

    await status_msg.edit_text(
        f"✅ **Feed Encontrado:** {parsed['title']}\n\n"
        f"¿A qué canal quieres enviar las noticias?",
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
        cid_str = data.replace("sel_ch_", "") 
        cid = int(cid_str)
    except:
        await query.edit_message_text("❌ Error interno identificando el canal.")
        return ConversationHandler.END
    
    temp = context.user_data.get('temp_feed')
    if not temp:
        await query.edit_message_text("❌ La sesión expiró. Por favor inicia de nuevo.")
        return ConversationHandler.END

    # Async Call
    new_feed = await DB.add_feed(query.from_user.id, temp['url'], cid, temp['title'], temp['hash'])
    
    await show_feed_options(update, context, new_feed['id'])
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
        "`#source#` - Fuente\n\n"
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