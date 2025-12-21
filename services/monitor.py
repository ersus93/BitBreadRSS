import asyncio
import json
import time
from telegram.constants import ParseMode
from core.database import DB
from services.parser import RSSParser
from services.resolver import RSSResolver
from services.iv_generator import create_instant_view_link
from utils.logger import log
from utils.common import truncate_text
import logging

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram.ext").setLevel(logging.ERROR)

# Plantilla Base
DEFAULT_TEMPLATE = (
    "<b>📰 #title#</b>\n\n"
    "<i>#description#</i>\n\n"
    "<i><b>🔗 Fuente:</b><a href='#link#'> #source#</a></i>"
)

class RSSMonitor:
    def __init__(self, bot):
        self.bot = bot
        self.running = False
        self.semaphore = asyncio.Semaphore(3) # Máximo 3 peticiones a la vez

    async def start(self):
        self.running = True
        log("🔄 Monitor RSS iniciado")
        while self.running:
            try:
                await self._check_feeds()
                # Pausa breve para liberar control al loop
                await asyncio.sleep(60) 
            except Exception as e:
                log(f"❌ Error crítico en el bucle del monitor: {e}", "error")
                await asyncio.sleep(60) 

    async def _check_feeds(self):
        data = await DB.load()

        # Iteramos sobre los usuarios y sus feeds
        for user_id, user_data in list(data.items()):
            for feed in user_data.get('feeds', []):
                # --- INICIO DEL BLOQUE DE PROTECCIÓN ---
                try: 
                    if not feed.get('active'): continue

                    # Validar intervalo de tiempo
                    ahora = time.time()
                    ultimo_check = feed.get('last_check', 0)
                    intervalo_segundos = int(feed.get('interval', 10)) * 60
                    
                    errores_consecutivos = feed.get('stats', {}).get('errors', 0)
                    # Corregido: 'errors' -> 'errores'
                    if errores_consecutivos > 0:
                        # Asegúrate de usar la misma variable aquí dentro también
                        multiplicador = min(errores_consecutivos, 4)
                        intervalo_segundos *= multiplicador

                    if ahora - ultimo_check < intervalo_segundos:
                        continue

                    async with self.semaphore:
                        parsed, error = await RSSParser.parse(feed['url'])

                        # Lógica de Auto-Reparación (WAF 403)
                        if error and "403" in str(error):
                            log(f"🛡️ WAF detectado en {feed['url']}. Intentando bypass...", "warning")
                            new_url, new_title, res_err = await RSSResolver.find_best_feed(feed['original_url'])
                            
                            if new_url and new_url != feed['url']:
                                log(f"✅ Feed reparado: {new_url}")
                                await DB.update_feed_url(user_id, feed['id'], new_url)
                                parsed, error = await RSSParser.parse(new_url)
                            else:
                                log(f"❌ Falló reparación automática: {res_err}", "error")

                    # Procesamiento de resultados
                    if error:
                        feed['stats']['errors'] = feed.get('stats', {}).get('errors', 0) + 1
                        log(f"⚠️ Fallo en {feed['url']}: {error}", "warning")
                        continue
                    
                    # Éxito
                    feed['stats']['errors'] = 0 
                    history = feed.get('history', [])
                    new_entries = []
                    
                    for entry in reversed(parsed['entries']):
                        if entry['hash'] not in history:
                            new_entries.append(entry)

                    if new_entries:
                        feed['last_check'] = ahora
                        for entry in new_entries:
                            success = await self._send_entry(feed, entry)
                            if success:
                                feed['history'].append(entry['hash'])
                                feed['stats']['sent'] += 1
                                if len(feed['history']) > 50: feed['history'].pop(0)
                        
                        await DB.save()
                    
                    await asyncio.sleep(1)

                except Exception as e:
                    # Esto evita que un feed corrupto detenga todo el bot
                    log(f"❌ Error procesando feed {feed.get('url', 'desconocido')}: {e}", "error")
                    continue
                # --- FIN DEL BLOQUE DE PROTECCIÓN ---

                # 4. Procesamiento de resultados (Misma lógica que tenías, pero manejando errores)
                if error:
                    feed['stats']['errors'] = feed.get('stats', {}).get('errors', 0) + 1
                    log(f"⚠️ Fallo en {feed['url']}: {error}", "warning")
                    continue
                
                # Si tuvo éxito, reseteamos contador de errores
                feed['stats']['errors'] = 0 
                
                history = feed.get('history', [])
                new_entries = []
                
                for entry in reversed(parsed['entries']):
                    if entry['hash'] not in history:
                        new_entries.append(entry)

                if new_entries:
                    feed['last_check'] = ahora
                    for entry in new_entries:
                        success = await self._send_entry(feed, entry)
                        if success:
                            feed['history'].append(entry['hash'])
                            feed['stats']['sent'] += 1
                            if len(feed['history']) > 50: feed['history'].pop(0)
                    
                    await DB.save()
                
                await asyncio.sleep(1)

    async def _send_entry(self, feed, entry):
        template = feed.get('template') or DEFAULT_TEMPLATE
        style = feed.get('style', 'bitbread') 

        # --- LÓGICA INSTANT VIEW ---
        user_rhash = feed.get('rhash')

        # 2. Generamos el link (el generador ahora es inteligente)
        iv_link = create_instant_view_link(entry['link'], user_rhash)

        # 3. Reemplazamos en la plantilla de mensaje
        text = template.replace("#title#", entry['title'])\
                       .replace("#description#", entry['description'])\
                       .replace("#link#", entry['link'])\
                       .replace("#source#", entry['source'])\
                       .replace("#sourceiv#", iv_link)
        
        desc = entry['description']
        text = text.replace("#description#", desc)

        # Calculamos el límite real restando la longitud extra del enlace IV
        # Un enlace IV añade aprox 150-250 caracteres ocultos en HTML [cite: 78]
        offset = len(iv_link) - len(entry['link']) if user_rhash else 0
        limit_caption = 1024 - max(0, offset) 
        limit_text = 4090 - max(0, offset)

        # 1. Intentar enviar FOTO (Estilo BitBread)
        if style == 'bitbread' and entry['image']:
            try:
                safe_caption = truncate_text(text, limit=int(limit_caption))
                await self.bot.send_photo(
                    chat_id=feed['channel_id'],
                    photo=entry['image'],
                    caption=safe_caption,
                    parse_mode=ParseMode.HTML
                )
                return True
            except Exception as e:
                # Si falla la foto, hacemos log y dejamos que baje a enviar TEXTO
                log(f"⚠️ Falló foto en {feed['channel_id']}, intentando texto. Err: {e}", "warning")

        # 2. Fallback a TEXTO (Estilo Texto o si falló la foto)
        try:
            safe_text = truncate_text(text, limit=int(limit_text))
            await self.bot.send_message(
                chat_id=feed['channel_id'],
                text=safe_text,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=False 
            )
            return True
        except Exception as e:
            log(f"❌ Error fatal enviando a {feed['channel_id']}: {e}", "error")
            return False
        
    async def force_check(self, user_id, feed_id):
        data = await DB.get_user(user_id)
        feed = next((f for f in data['feeds'] if f['id'] == feed_id), None)
        if not feed: return False, "Feed no encontrado."
        
        parsed, error = await RSSParser.parse(feed['url'])
        if error or not parsed['entries']: return False, "No se pudo leer el feed."
        
        latest = parsed['entries'][0]
        success = await self._send_entry(feed, latest)
        return success, "Noticia de prueba enviada." if success else "Error enviando al canal."