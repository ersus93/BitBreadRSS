import urllib.parse
import json
import os
from urllib.parse import urlparse
from core.config import TEMPLATES_JSON_FILE

def load_global_templates():
    """Carga las plantillas desde el JSON externo."""
    if not os.path.exists(TEMPLATES_JSON_FILE):
        return {}
    try:
        with open(TEMPLATES_JSON_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}

def find_best_rhash(url):
    """Busca la mejor plantilla en el JSON."""
    templates = load_global_templates()
    domain = urlparse(url).netloc.lower().replace("www.", "")
    
    # 1. Buscar coincidencia exacta
    if domain in templates:
        return templates[domain]
    
    # 2. Buscar coincidencia de subdominio (ej: tecnologia.elpais.com -> elpais.com)
    for key, rhash in templates.items():
        if not key.startswith("_") and domain.endswith(key):
            return rhash
            
    # 3. Fallback al rhash universal del JSON
    return templates.get("_universal")

def create_instant_view_link(original_url, user_rhash=None, custom_label=None):
    """Genera el link usando la jerarquía de rhashes."""
    # Prioridad: 1. El del usuario, 2. El del buscador JSON
    rhash = user_rhash if user_rhash and user_rhash.lower() != 'none' else find_best_rhash(original_url)

    if not rhash:
        return original_url

    encoded_url = urllib.parse.quote(original_url, safe='')
    iv_url = f"https://t.me/iv?url={encoded_url}&rhash={rhash}"
    
    label = custom_label if custom_label else "Leer en Telegram ⚡"
    return f'<a href="{iv_url}">{label}</a>'