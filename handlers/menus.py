from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from core.database import DB
import html

# --- MENÚ DE INICIO ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = (
        "🤖 *BitBread RSS Bot*\n"
        "Gestiona tus noticias y automatiza tus canales.\n\n"
        "1️⃣ Añade un Canal (hazme admin primero).\n"
        "2️⃣ Añade un Feed RSS.\n"
        "3️⃣ Personaliza el formato."
    )
    
    kb_inline = [
        [InlineKeyboardButton("📺 Mis Canales", callback_data="menu_channels")],
        [InlineKeyboardButton("🔗 Mis Feeds", callback_data="menu_feeds")],
        [InlineKeyboardButton("❓ Ayuda", callback_data="help")]
    ]
    
    kb_reply = ReplyKeyboardMarkup(
        [[KeyboardButton("🏠 Mostrar menú inicio")]], 
        resize_keyboard=True
    )

    if update.callback_query:
        await update.callback_query.edit_message_text(
            txt, 
            reply_markup=InlineKeyboardMarkup(kb_inline), 
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        if update.message and update.message.text == "/start":
            await update.message.reply_text("Activando teclado...", reply_markup=kb_reply)
        
        await update.message.reply_text(
            txt, 
            reply_markup=InlineKeyboardMarkup(kb_inline), 
            parse_mode=ParseMode.MARKDOWN
        )

# --- UTILS DE RENDERIZADO ---
async def show_feeds_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra la lista de feeds (refactorizado para reuso)."""
    user_id = update.effective_user.id
    user_data = await DB.get_user(user_id)
    
    kb = []
    if not user_data['feeds']:
        txt = "🔗 *Mis Feeds*\nNo tienes feeds configurados."
    else:
        txt = "🔗 *Mis Feeds*\nSelecciona uno para editar."
        for f in user_data['feeds']:
            style_icon = "🖼️" if f.get('style', 'bitbread') == 'bitbread' else "📄"
            title_short = (f['title'][:25] + '..') if len(f['title']) > 25 else f['title']
            # Usamos IDs seguros en callback data
            kb.append([InlineKeyboardButton(f"{style_icon} {title_short}", callback_data=f"feed_opt_{f['id']}")])
    
    kb.append([InlineKeyboardButton("➕ Añadir Feed", callback_data="add_feed")])
    kb.append([InlineKeyboardButton("🔙 Inicio", callback_data="start")])
    
    # Decidir si editar o enviar nuevo según origen
    markup = InlineKeyboardMarkup(kb)
    if update.callback_query:
        await update.callback_query.edit_message_text(txt, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)
    else:
        await update.effective_message.reply_text(txt, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)

# --- MANEJADORES DE MENÚS ---

async def show_channels_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    data = await DB.get_user(user_id)
    channels = data.get('channels', [])
    
    txt = "📺 *Tus Canales*\nSelecciona uno para eliminar o añade uno nuevo."
    kb = []
    for c in channels:
        kb.append([InlineKeyboardButton(f"🗑 {c['title']}", callback_data=f"del_chan_{c['id']}")])
    
    kb.append([InlineKeyboardButton("➕ Añadir Canal", callback_data="add_channel")])
    kb.append([InlineKeyboardButton("🔙 Volver", callback_data="start")])
    
    markup = InlineKeyboardMarkup(kb)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(txt, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)
    else:
        await update.effective_message.reply_text(txt, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)

async def show_feed_options(update: Update, context: ContextTypes.DEFAULT_TYPE, feed_id: str):
    user_id = update.effective_user.id
    data = await DB.get_user(user_id)
    feed = next((f for f in data['feeds'] if f['id'] == feed_id), None)
    
    if not feed:
        error_txt = "❌ *Error:* No se encuentra el feed solicitado."
        if update.callback_query:
            await update.callback_query.edit_message_text(error_txt, parse_mode=ParseMode.MARKDOWN)
        return
    
    # Buscar nombre del canal actual para mostrarlo
    current_ch_id = feed.get('channel_id')
    channel_name = "Desconocido/Eliminado"
    for c in data['channels']:
        if c['id'] == current_ch_id:
            channel_name = c['title']
            break

    title_safe = html.escape(feed.get('title', 'Sin Título'))
    url_safe = html.escape(feed.get('url', '...'))
    style_label = "🖼️ FOTO (BitBread)" if feed.get('style') == 'bitbread' else "📄 TEXTO"
    interval = feed.get('interval', 10)
    
    txt = (
        f"⚙️ <b>Configuración de Feed</b>\n\n"
        f"📰 <b>Nombre:</b> {title_safe}\n"
        f"🎨 <b>Estilo:</b> {style_label}\n"
        f"⏱ <b>Frecuencia:</b> Cada {interval} min\n"
        f"📢 <b>Destino:</b> {html.escape(channel_name)}\n"
        f"🔗 <b>URL:</b> {url_safe}\n"
    )

    kb = [
        [InlineKeyboardButton("📢 Cambiar Destino", callback_data=f"move_feed_{feed_id}")], # NUEVO BOTÓN
        [InlineKeyboardButton("🎨 Cambiar Estilo", callback_data=f"toggle_style_{feed_id}")],
        [InlineKeyboardButton("⏱ Frecuencia", callback_data=f"menu_time_{feed_id}")],
        [InlineKeyboardButton("📝 Editar Plantilla", callback_data=f"tmpl_feed_{feed_id}")],
        [InlineKeyboardButton("⚡ Probar Envío", callback_data=f"test_feed_{feed_id}")],
        [InlineKeyboardButton("🗑 Eliminar Feed", callback_data=f"del_feed_{feed_id}")],
        [InlineKeyboardButton("🔙 Volver a la lista", callback_data="menu_feeds")]
    ]
    
    markup = InlineKeyboardMarkup(kb)
    
    try:
        if update.callback_query:
            await update.callback_query.edit_message_text(txt, reply_markup=markup, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        else:
            await update.effective_message.reply_text(txt, reply_markup=markup, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    except Exception as e:
        # Ignorar error si el contenido es identico
        pass

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = (
        "📚 *Guía Rápida*\n\n"
        "*1. Vincular Canal:*\n"
        "Ve a 'Mis Canales' -> 'Nuevo'. Haz admin al bot en tu canal y reenvía un mensaje aquí.\n\n"
        "*2. Añadir Feed:*\n"
        "Ve a 'Mis Feeds' -> 'Nuevo'. Pega el enlace RSS.\n\n"
        "*Plantillas:*\n"
        "`#title#`, `#link#`, `#description#`, `#source#`.\n"
        "Usa HTML (`<b>`, `<a>`) para dar formato."
    )
    kb = [[InlineKeyboardButton("🔙 Volver", callback_data="start")]]
    
    if update.callback_query:
        await update.callback_query.edit_message_text(txt, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text(txt, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)


async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    # IMPORTANTE: Responder SIEMPRE primero para desbloquear el botón
    try:
        await query.answer()
    except:
        pass 

    data = query.data
    user_id = query.from_user.id
    
    if data == "start":
        await start(update, context)
        
    elif data == "help":
        await help_command(update, context)
        
    elif data == "menu_channels":
        await show_channels_menu(update, context)
        
    elif data.startswith("del_chan_"):
        try:
            cid = int(data.split("_")[2])
            await DB.delete_channel(user_id, cid)
            await show_channels_menu(update, context)
        except Exception as e:
            print(f"Error borrando canal: {e}")
        
    # --- MENÚ DE FEEDS ---
    elif data == "menu_feeds":
        await show_feeds_list(update, context)

    # --- OPCIONES DEL FEED ---
    elif data.startswith("feed_opt_"):
        fid = data.split("_")[2]
        await show_feed_options(update, context, fid)

    # === NUEVA LÓGICA: CAMBIAR DESTINO ===
    if data.startswith("move_feed_"):
        fid = data.split("_")[2]
        user_data = await DB.get_user(user_id)
        
        if not user_data['channels']:
            await query.answer("⚠️ No tienes canales. Añade uno primero.", show_alert=True)
            return

        kb = []
        for ch in user_data['channels']:
            # Callback format: set_dest_FEEDID_CHANNELID
            kb.append([InlineKeyboardButton(f"📢 {ch['title']}", callback_data=f"set_dest_{fid}_{ch['id']}")])
        
        kb.append([InlineKeyboardButton("🔙 Cancelar", callback_data=f"feed_opt_{fid}")])
        
        await query.edit_message_text(
            "📍 *Selecciona el nuevo canal de destino:*",
            reply_markup=InlineKeyboardMarkup(kb),
            parse_mode=ParseMode.MARKDOWN
        )

    elif data.startswith("set_dest_"):
        parts = data.split("_")
        fid = parts[2]
        new_cid = parts[3]
        
        if await DB.update_feed_channel(user_id, fid, new_cid):
            # Volvemos al menú del feed para confirmar visualmente
            await show_feed_options(update, context, fid)
        else:
            await query.answer("❌ Error cambiando el canal.", show_alert=True)

    # --- SUBMENU: FRECUENCIA ---
    elif data.startswith("menu_time_"):
        fid = data.split("_")[2]
        keyboard = [
            [InlineKeyboardButton("5 min", callback_data=f"set_t_{fid}_5"), 
             InlineKeyboardButton("15 min", callback_data=f"set_t_{fid}_15")],
            [InlineKeyboardButton("30 min", callback_data=f"set_t_{fid}_30"),
             InlineKeyboardButton("1 hora", callback_data=f"set_t_{fid}_60")],
             [InlineKeyboardButton("6 horas", callback_data=f"set_t_{fid}_360"),
             InlineKeyboardButton("12 horas", callback_data=f"set_t_{fid}_720")],
            [InlineKeyboardButton("⬅️ Volver", callback_data=f"feed_opt_{fid}")]
        ]
        await query.edit_message_text(f"⏱ *Frecuencia de actualización*\nSelecciona cada cuánto tiempo buscar noticias nuevas:", 
                                    reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)

    elif data.startswith("set_t_"): 
        parts = data.split("_")
        fid = parts[2]
        minutes = int(parts[3])
        
        if await DB.update_interval(user_id, fid, minutes):
            await show_feed_options(update, context, fid)

    # --- ACCIONES DIRECTAS ---
    elif data.startswith("toggle_style_"):
        fid = data.split("_")[2]
        await DB.toggle_style(user_id, fid)
        await show_feed_options(update, context, fid)

    elif data.startswith("del_feed_"):
        fid = data.split("_")[2]
        await DB.delete_feed(user_id, fid)
        # No llamar recursivamente a menu_handler, llamar directo al renderizador
        await show_feeds_list(update, context)
        
    elif data.startswith("test_feed_"):
        fid = data.split("_")[2]
        monitor = context.bot_data.get('monitor')
        if monitor:
            await query.edit_message_text("⏳ *Enviando prueba al canal...*", parse_mode=ParseMode.MARKDOWN)
            ok, msg = await monitor.force_check(user_id, fid)
            
            kb = [[InlineKeyboardButton("🔙 Volver al Feed", callback_data=f"feed_opt_{fid}")]]
            res_icon = "✅" if ok else "❌"
            await query.edit_message_text(f"{res_icon} *Resultado:* {msg}", reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)