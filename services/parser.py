import feedparser
import aiohttp
import re
import hashlib
import ssl
from bs4 import BeautifulSoup
from utils.logger import log

class RSSParser:
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    }

    @staticmethod
    def _clean_html(raw_html):
        if not raw_html: return ""
        text = raw_html.replace("<br>", "\n").replace("<p>", "").replace("</p>", "\n\n")
        text = re.sub(r'<(?!\/?(b|strong|i|em|u|s|a|code|pre)\b)[^>]*>', '', text, flags=re.IGNORECASE)
        return text.strip()

    @staticmethod
    def _extract_image(entry):
        """Busca imágenes en orden de prioridad: Media > Enclosure > Content > Summary"""
        
        # 1. Media Content (Estándar RSS multimedia)
        if 'media_content' in entry:
            for m in entry.media_content:
                if 'image' in m.get('type', '') or m.get('medium') == 'image':
                    return m['url']

        # 2. Media Thumbnail
        if 'media_thumbnail' in entry and len(entry.media_thumbnail) > 0:
            return entry.media_thumbnail[0]['url']

        # 3. Links Enclosures (Podcasts/Attachments)
        if 'links' in entry:
            for l in entry.links:
                if l.get('rel') == 'enclosure' and 'image' in l.get('type', ''):
                    return l['href']

        # 4. Buscar en el HTML (Content o Summary)
        # Unimos content y summary para buscar en ambos
        content_html = ""
        if 'content' in entry:
            for c in entry.content:
                content_html += c.value
        
        full_html = content_html + (entry.get('summary') or "")
        
        if full_html:
            soup = BeautifulSoup(full_html, 'html.parser')
            images = soup.find_all('img')
            for img in images:
                src = img.get('src')
                if src:
                    # Filtros básicos para evitar pixeles de tracking o emojis
                    if "pixel" in src or "emoji" in src or ".gif" in src:
                        continue
                    return src
        return None

    @staticmethod
    def _get_hash(entry):
        # Usamos link + title para generar ID único
        raw = f"{entry.get('link', '')}{entry.get('title', '')}"
        return hashlib.md5(raw.encode()).hexdigest()

    @classmethod
    async def parse(cls, url):
        try:
            ssl_ctx = ssl.create_default_context()
            ssl_ctx.check_hostname = False
            ssl_ctx.verify_mode = ssl.CERT_NONE
            jar = aiohttp.CookieJar(unsafe=True)

            async with aiohttp.ClientSession(headers=cls.HEADERS, cookie_jar=jar) as session:
                async with session.get(url, timeout=20, ssl=ssl_ctx) as response:
                    if response.status not in [200, 301, 302]:
                        return None, f"⚠️ Error HTTP: {response.status}"
                    content = await response.read()

            feed = feedparser.parse(content)
            
            if feed.bozo and not feed.entries:
                return None, "No es un XML válido o está bloqueado."

            entries = []
            for entry in feed.entries[:10]:
                entries.append({
                    "title": cls._clean_html(entry.get('title', 'Sin título')),
                    "link": entry.get('link', ''),
                    "description": cls._clean_html(entry.get('summary', entry.get('description', ''))),
                    "image": cls._extract_image(entry), # Nueva lógica de extracción
                    "hash": cls._get_hash(entry),
                    "source": feed.feed.get('title', 'RSS Source')
                })
            
            return {"title": feed.feed.get('title', 'Feed'), "entries": entries}, None

        except Exception as e:
            log(f"Error parsing {url}: {e}", "error")
            return None, f"Excepción: {str(e)}"