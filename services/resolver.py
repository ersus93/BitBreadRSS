import asyncio
import urllib.parse
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from services.parser import RSSParser
from utils.logger import log

class RSSResolver:
    """
    Encargado de descubrir la URL real del RSS.
    Implementa lógica de contingencia ante errores 403/WAF.
    """
    
    # Rutas comunes para Fuerza Bruta
    COMMON_PATHS = [
        "feed", "feed/", "rss", "rss.xml", "atom.xml", "feed.xml", 
        "index.xml", "feeds/posts/default", "?feed=rss2", "rss/"
    ]

    @classmethod
    async def find_best_feed(cls, url):
        """
        Retorna: (resolved_url, title, error_msg)
        """
        url = url.strip().rstrip('/')
        if not url.startswith("http"):
            url = f"https://{url}"

        log(f"🔍 Resolviendo feed para: {url}")
        
        candidates = []
        domain_error = None

        # 1. Intento Directo en la URL dada (Home o URL completa)
        content, error = await RSSParser.fetch_content(url)
        
        # Si funciona la URL base, analizamos
        if not error:
            # A. Verificamos si YA es un XML válido
            import feedparser
            d = feedparser.parse(content)
            if not d.bozo and len(d.entries) > 0:
                return url, d.feed.get('title', 'Feed'), None

            # B. Descubrimiento Heurístico (HTML Scraping)
            try:
                soup = BeautifulSoup(content, 'lxml')
                # Buscar etiquetas <link rel="alternate">
                links = soup.find_all("link", rel=["alternate", "service.feed"])
                for link in links:
                    t = link.get("type", "").lower()
                    href = link.get("href")
                    if href and ("rss" in t or "atom" in t or "xml" in t):
                        candidates.append(urljoin(url, href))

                # Buscar etiquetas <a> con palabras clave
                if not candidates:
                    a_tags = soup.find_all("a", href=True)
                    for a in a_tags:
                        href = a.get("href")
                        if any(x in href.lower() for x in ["/rss", "/feed", ".xml"]):
                            candidates.append(urljoin(url, href))
            except Exception as e:
                log(f"Error parseando HTML: {e}", "warning")
        else:
            # Si falla la home, guardamos el error pero CONTINUAMOS a fuerza bruta
            domain_error = error
            log(f"⚠️ Falló acceso a home ({error}), intentando fuerza bruta...", "warning")

        # 2. Fuerza Bruta (Common Paths)
        # Se ejecuta siempre si no hemos encontrado nada seguro, incluso si la home dio 403
        if not candidates:
            base = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
            
            # Si la URL original ya parecía una ruta completa (ej. eltoque.com/feed), la probamos primero
            if url != base and url != base + "/":
                candidates.append(url)
            
            # Añadimos rutas comunes a la base
            for path in cls.COMMON_PATHS:
                candidates.append(urljoin(base + "/", path))

        # 3. Verificación de Candidatos (Testing)
        # Probamos los candidatos únicos. Priorizamos los que parecen feeds.
        unique_candidates = list(set(candidates))
        await asyncio.sleep(2) # Esperamos un poco para no ser bloqueados por WAF
        
        for cand in unique_candidates[:6]: # Probamos máx 6 para no tardar tanto
            log(f"   👉 Probando candidato: {cand}")
            c_content, c_err = await RSSParser.fetch_content(cand)
            
            if not c_err:
                d_cand = feedparser.parse(c_content)
                if not d_cand.bozo and len(d_cand.entries) > 0:
                    return cand, d_cand.feed.get('title', 'Feed Detectado'), None
            elif "403" in str(c_err) or "429" in str(c_err):
                log(f"   🚫 Bloqueo WAF en {cand}", "warning")

        # 4. Fallback Final (Si todo falla)
        fail_msg = f"No se pudo detectar el feed. Error inicial: {domain_error}" if domain_error else "No se encontraron feeds válidos."
        return None, None, fail_msg