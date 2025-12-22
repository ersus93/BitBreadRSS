import feedparser
import re
import hashlib
import random
from curl_cffi.requests import AsyncSession
from bs4 import BeautifulSoup
from utils.logger import log

class RSSParser:
    # Simulamos un navegador real (Chrome 110+)
    PROFILES = ["chrome120", "chrome110"]
    HEADERS = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
        "Referer": "https://www.google.com/", # Referer de confianza ayuda a evitar bloqueos
        "Upgrade-Insecure-Requests": "1"
    }

    @staticmethod
    def _clean_html(raw_html):
        if not raw_html: return ""
        text = raw_html.replace("<br>", "\n").replace("<p>", "").replace("</p>", "\n\n")
        text = re.sub(r'<(?!\/?(b|strong|i|em|u|s|a|code|pre)\b)[^>]*>', '', text, flags=re.IGNORECASE)
        return text.strip()

    @staticmethod
    def _extract_image(entry):
        # 1. Media Content
        if 'media_content' in entry:
            for m in entry.media_content:
                if 'image' in m.get('type', '') or m.get('medium') == 'image':
                    return m['url']
        # 2. Media Thumbnail
        if 'media_thumbnail' in entry and len(entry.media_thumbnail) > 0:
            return entry.media_thumbnail[0]['url']
        # 3. Enclosures
        if 'links' in entry:
            for l in entry.links:
                if l.get('rel') == 'enclosure' and 'image' in l.get('type', ''):
                    return l['href']
        # 4. Parsing HTML content
        content_html = ""
        if 'content' in entry:
            for c in entry.content:
                content_html += c.value
        full_html = content_html + (entry.get('summary') or "")
        
        if full_html:
            try:
                soup = BeautifulSoup(full_html, 'lxml')
                img = soup.find('img')
                if img and img.get('src'):
                    src = img.get('src')
                    if not any(x in src for x in ["pixel", "emoji", ".gif"]):
                        return src
            except:
                pass
        return None

    @staticmethod
    def _get_hash(entry):
        raw = f"{entry.get('link', '')}{entry.get('title', '')}"
        return hashlib.md5(raw.encode()).hexdigest()

    @classmethod
    async def fetch_content(cls, url):
        """Método robusto con rotación de huellas digitales."""
        # Seleccionamos un perfil aleatorio inicial
        current_profile = random.choice(cls.PROFILES)
        
        try:
            async with AsyncSession(impersonate=current_profile, headers=cls.HEADERS) as session:
                response = await session.get(url, timeout=60)
                
                # Si recibimos 403 (Forbidden) o 503 (Service Unavailable - común en Cloudflare)
                if response.status_code in [403, 503, 429]:
                    log(f"🛡️ Bloqueo detectado ({response.status_code}) con {current_profile}. Rotando identidad...", "warning")
                    
                    # Intentamos con un perfil específico de Safari (suelen tener mejor paso en CF)
                    fallback_profile = "safari_15_3" if current_profile != "safari_15_3" else "chrome110"
                    
                    async with AsyncSession(impersonate=fallback_profile, headers=cls.HEADERS) as s2:
                        resp2 = await s2.get(url, timeout=30)
                        if resp2.status_code == 200:
                            return resp2.content, None
                        return None, f"Bloqueo persistente (HTTP {resp2.status_code})"

                if response.status_code not in [200, 301, 302]:
                     return None, f"HTTP {response.status_code}"
                
                return response.content, None

        except Exception as e:
            return None, str(e)

    @classmethod
    async def parse(cls, url):
        """
        Intenta parsear la URL. Si falla, el Resolver debe encargarse de encontrar la URL correcta.
        Aquí asumimos que 'url' es un feed válido o una redirección directa.
        """
        content, error = await cls.fetch_content(url)
        if error:
            log(f"Error fetching {url}: {error}", "warning")
            return None, error

        try:
            # feedparser procesa bytes mejor que strings con encoding incorrecto
            feed = feedparser.parse(content)
            
            if feed.bozo and not feed.entries:
                if b"Cloudflare" in content or b"Just a moment" in content:
                    return None, "Bloqueo Cloudflare JS"
                return None, "XML inválido o bloqueado"

            entries = []
            for entry in feed.entries[:10]:
                entries.append({
                    "title": cls._clean_html(entry.get('title', 'Sin título')),
                    "link": entry.get('link', ''),
                    "description": cls._clean_html(entry.get('summary', entry.get('description', ''))),
                    "image": cls._extract_image(entry),
                    "hash": cls._get_hash(entry),
                    "source": feed.feed.get('title', 'RSS Source')
                })
            
            return {"title": feed.feed.get('title', 'Feed'), "entries": entries}, None

        except Exception as e:
            log(f"Error parsing logic {url}: {e}", "error")
            return None, f"Excepción interna: {str(e)}"