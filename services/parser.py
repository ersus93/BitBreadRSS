import feedparser
import re
import asyncio
import hashlib
import random
from urllib.parse import urlparse, urljoin
from curl_cffi.requests import AsyncSession
from bs4 import BeautifulSoup
from utils.logger import log

class RSSParser:
    # Simulamos un navegador real (Chrome 110+)
    PROFILES = ["chrome120", "safari17_0", "safari15_5", "chrome110"]
    HEADERS = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,es;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": "https://www.google.com/",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "cross-site",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    NITTER_INSTANCES = [
        "https://nitter.privacyredirect.com", # Muy estable, pero a veces tiene problemas con WAF)
        "https://nitter.net",            # Estable, pero a veces tiene problemas con WAF)
        "https://xcancel.com",           # Suele ser la más estable
        "https://nitter.poast.org",      # Estricta, pero a veces funciona
        "https://nitter.privacydev.net", # A veces bloquea rangos de IP
        "https://nitter.soopy.moe",
        "https://nitter.lucabased.xyz",
        "https://lightbrd.com",
        "https://nitter.space",
        "https://nitter.tiekoetter.com",
        "https://nuku.trabun.org",
        "https://nitter.catsarch.com",
        "https://nitter.0000",
        "https://nitter.net",
        "https://nitter.kavin.rocks",
        "https://nitter.koyu.space",    # A veces tiene problemas con WAF)
        "https://nitter.nixnet.services", # A veces tiene problemas con WAF)
        "https://nitter.kavin.app",
        "https://twiiit.com/",
    ]

    @staticmethod
    def is_valid_xml(content):
        """Verifica si el contenido es XML válido y NO una página de bloqueo."""
        if not content: return False
        try:
            text = content.decode('utf-8', errors='ignore') if isinstance(content, bytes) else content
            
            # Detección de bloqueos comunes
            block_keywords = [
                "<!DOCTYPE html>", "<html", "Cloudflare", "Rate limit", 
                "Just a moment", "Access denied", "403 Forbidden"
            ]
            
            # Si empieza como HTML o contiene bloqueos, rechazamos, A MENOS que tenga tags RSS explícitos
            is_html = text.strip().startswith(('<!DOCTYPE html>', '<html'))
            has_rss_tags = ('<rss' in text or '<feed' in text or '<?xml' in text)
            
            if is_html and not has_rss_tags:
                return False

            if any(k in text for k in ["Rate limit exceeded", "Instance has been rate limited"]):
                return False

            return has_rss_tags
        except:
            return False

    @classmethod
    def _get_twitter_username(cls, url):
        match = re.search(r"(?:twitter\.com|x\.com|nitter\.[a-z\.]+)/([a-zA-Z0-9_]+)", url)
        if not match and "nitter" in url:
            parts = url.rstrip('/').split('/')
            if len(parts) > 0: return parts[-1]
        return match.group(1) if match else None

    @classmethod
    async def find_best_feed(cls, url):
        """
        Retorna: (resolved_url, title, error_msg)
        """
        url = url.strip().rstrip('/')
        if not url.startswith("http"):
            url = f"https://{url}"

        # --- CORRECCIÓN: Interceptamos X/Twitter ---
        if "twitter.com" in url or "x.com" in url or "nitter" in url:
            # Extraemos usuario (soporta input tipo twitter.com/user o nitter.net/user)
            username = RSSParser._get_twitter_username(url)
            
            # Si la URL de entrada ya era nitter, extraemos el user de ahí
            if not username and "nitter" in url:
                parts = url.rstrip('/').split('/')
                # Asumimos estructura nitter.net/usuario
                if len(parts) > 3: username = parts[-1]

            if username:
                log(f"🐦 Buscando instancia Nitter activa para @{username}...")
                
                # ROTACIÓN INTELIGENTE: Probamos instancias hasta que una responda 200 OK
                # Aleatorizamos la lista para no saturar siempre a la primera
                instances = RSSParser.NITTER_INSTANCES.copy()
                random.shuffle(instances)

                for nitter_base in instances:
                    nitter_url = f"{nitter_base}/{username}/rss"
                    log(f"   👉 Probando: {nitter_base}...")
                    
                    content, error = await RSSParser.fetch_content(nitter_url)
                    if not error:
                        # VALIDACIÓN EXTRA: A veces devuelven 200 pero dicen "Instance has been rate limited"
                        if b"Rate limit" in content or b"Error" in content[0:100]:
                            continue
                            
                        log(f"   ✅ ¡Éxito en {nitter_base}!")
                        return nitter_url, f"Twitter: @{username}", None
                
                return None, None, "Todas las instancias de Nitter fallaron o están bloqueadas."
        # -----------------------------------------------------------

        log(f"🔍 Resolviendo feed para: {url}")
        
        candidates = []
        domain_error = None

    @staticmethod
    def _clean_html(raw_html):
        if not raw_html: return ""
        text = raw_html.replace("<br>", "\n").replace("<p>", "").replace("</p>", "\n\n")
        text = re.sub(r'<(?!\/?(b|strong|i|em|u|s|a|code|pre)\b)[^>]*>', '', text, flags=re.IGNORECASE)
        return text.strip()

    @staticmethod
    def _extract_image(entry):
        """Lógica avanzada: Reconstruye URLs relativas de Nitter."""
        # 1. Media Content (Estándar RSS)
        if 'media_content' in entry:
            for m in entry.media_content:
                if 'image' in m.get('type', '') or m.get('medium') == 'image':
                    return m['url']
        
        # 2. Enclosures (Estándar RSS)
        if 'links' in entry:
            for l in entry.links:
                if l.get('rel') == 'enclosure' and 'image' in l.get('type', ''):
                    return l['href']

        # 3. HTML Scraping (Aquí es donde arreglamos Nitter)
        content = entry.get('summary', '') or entry.get('description', '') or ""
        if 'content' in entry:
            for c in entry.content:
                content += c.value

        # -- OBTENER EL DOMINIO BASE DEL POST --
        # Si el post es https://nitter.net/usuario/status/123, base es https://nitter.net
        base_url = ""
        if entry.get('link'):
            parsed = urlparse(entry['link'])
            base_url = f"{parsed.scheme}://{parsed.netloc}"

        if content:
            try:
                soup = BeautifulSoup(content, 'lxml')
                imgs = soup.find_all('img')
                
                for img in imgs:
                    src = img.get('src')
                    if not src: continue
                    
                    # CORRECCIÓN PRINCIPAL:
                    # Si viene como "/pic/orig/..." le pegamos el dominio delante
                    if src.startswith('/'):
                        src = base_url + src

                    # Filtros de basura
                    keywords_basura = ["emoji", "pixel", "tracking", "avatar", "icon"]
                    if any(x in src.lower() for x in keywords_basura):
                        continue
                        
                    # Aceptar explícitamente rutas de Nitter y Twitter
                    if "pbs.twimg" in src or "/pic/" in src or "media" in src:
                        return src
                    
                    # Última validación: tiene que ser http
                    if src.startswith("http"):
                        return src
            except Exception:
                pass
        return None
    
    @staticmethod
    def _extract_video(entry):
        """Busca videos y corrige rutas relativas."""
        # Preparar base url por si acaso
        base_url = ""
        if entry.get('link'):
            parsed = urlparse(entry['link'])
            base_url = f"{parsed.scheme}://{parsed.netloc}"

        # 1. Media Content
        if 'media_content' in entry:
            for m in entry.media_content:
                t = m.get('type', '')
                if 'video' in t or 'mp4' in t:
                    url = m['url']
                    return base_url + url if url.startswith('/') else url
        
        # 2. Enclosures
        if 'links' in entry:
            for l in entry.links:
                if l.get('rel') == 'enclosure':
                    t = l.get('type', '')
                    if 'video' in t or 'mp4' in t:
                        url = l['href']
                        return base_url + url if url.startswith('/') else url

        # 3. HTML Scraping (Para Nitter)
        content = entry.get('summary', '') or entry.get('description', '')
        if content and "<video" in content:
            try:
                soup = BeautifulSoup(content, 'lxml')
                video = soup.find('video')
                if video:
                    # Buscar en src del video o en source
                    src = video.get('src')
                    if not src:
                        source = video.find('source')
                        if source: src = source.get('src')
                    
                    if src:
                        return base_url + src if src.startswith('/') else src
            except:
                pass
        return None

    @staticmethod
    def _get_hash(entry):
        raw = f"{entry.get('link', '')}{entry.get('title', '')}"
        return hashlib.md5(raw.encode()).hexdigest()

    @classmethod
    async def fetch_content(cls, url):
        profiles = list(cls.PROFILES)
        random.shuffle(profiles)
        
        for profile in profiles[:2]:
            try:
                async with AsyncSession(impersonate=profile, headers=cls.HEADERS) as session:
                    response = await session.get(url, timeout=15)
                    if response.status_code == 200:
                        return response.content, None
                    if response.status_code in [403, 429, 503]:
                        await asyncio.sleep(1)
                        continue
            except Exception as e:
                log(f"Error conexión ({profile}) en {url}: {e}", "debug")
                continue # Si falla DNS, prueba el siguiente perfil/reintento

        return None, "Error de conexión o Bloqueo WAF persistente"

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
                    "image": cls._extract_image(entry), # Nueva lógica aplicada aquí
                    "video": cls._extract_video(entry),
                    "hash": cls._get_hash(entry),
                    "source": feed.feed.get('title', 'RSS Source')
                })
            
            return {"title": feed.feed.get('title', 'Feed'), "entries": entries}, None

        except Exception as e:
            log(f"Error parsing logic {url}: {e}", "error")
            return None, f"Excepción interna: {str(e)}"