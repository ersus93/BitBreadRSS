import re

def clean_html(raw_html):
    """Limpia etiquetas HTML complejas dejando solo las básicas para Telegram."""
    if not raw_html: 
        return ""
    
    # Reemplazar saltos de línea HTML por saltos de texto
    text = raw_html.replace("<br>", "\n").replace("<br/>", "\n").replace("<p>", "").replace("</p>", "\n\n")
    
    # Eliminar scripts y estilos
    text = re.sub(r'<(script|style).*?>.*?</\1>', '', text, flags=re.DOTALL)
    
    # Eliminar todas las etiquetas excepto las soportadas por Telegram
    # (b, strong, i, em, u, s, a, code, pre)
    text = re.sub(r'<(?!\/?(b|strong|i|em|u|s|a|code|pre)\b)[^>]*>', '', text, flags=re.IGNORECASE)
    
    # Eliminar espacios múltiples
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    return text.strip()

def truncate_text(text, limit=1000):
    """Corta el texto si excede el límite (1024 para captions de fotos)."""
    if len(text) <= limit:
        return text
    return text[:limit-3] + "..."