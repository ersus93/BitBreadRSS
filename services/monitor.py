import asyncio
import time
from telegram.constants import ParseMode
from core.database import DB
from services.parser import RSSParser
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
        data = await DB.load() # Async Load
        
        # Iterar sobre copia para evitar problemas si cambia durante la iteración
        for user_id, user_data in list(data.items()):
            for feed in user_data.get('feeds', []):
                if not feed.get('active'): continue

                ahora = time.time()
                ultimo_check = feed.get('last_check', 0)
                intervalo_segundos = int(feed.get('interval', 10)) * 60

                if ahora - ultimo_check < intervalo_segundos:
                    continue 
                
                try:
                    parsed, error = await RSSParser.parse(feed['url'])
                    if error:
                        log(f"⚠️ Error en feed {feed['url']}: {error}", "warning")
                        continue
                except Exception as e:
                    log(f"⚠️ Crash parseando {feed['url']}: {e}", "error")
                    continue

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
                            
                    # Guardamos despues de procesar el feed completo
                    await DB.save()
                    
                await asyncio.sleep(1) # Breve pausa entre feeds para no saturar CPU

    async def _send_entry(self, feed, entry):
        template = feed.get('template') or DEFAULT_TEMPLATE
        style = feed.get('style', 'bitbread') 
        
        text = template.replace("#title#", entry['title'])\
                       .replace("#link#", entry['link'])\
                       .replace("#source#", entry['source'])
        
        desc = entry['description']
        text = text.replace("#description#", desc)

        # 1. Intentar enviar FOTO (Estilo BitBread)
        if style == 'bitbread' and entry['image']:
            try:
                safe_caption = truncate_text(text, limit=1024)
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
            safe_text = truncate_text(text, limit=4090)
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