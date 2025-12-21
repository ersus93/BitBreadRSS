import json
import os
import uuid
import asyncio
from datetime import datetime
from core.config import RSS_DATA_FILE
from utils.logger import log

class DB:
    _data = None
    _lock = asyncio.Lock()  # Semáforo para controlar acceso concurrente

    @classmethod
    async def load(cls):
        """Carga la DB de forma asíncrona (thread-safe)."""
        if cls._data is not None: 
            return cls._data
            
        if not os.path.exists(RSS_DATA_FILE):
            cls._data = {}
            return cls._data

        # Ejecutar lectura en un hilo separado para no bloquear el loop
        try:
            cls._data = await asyncio.to_thread(cls._load_sync)
        except Exception as e:
            log(f"Error cargando DB: {e}", "error")
            cls._data = {}
        return cls._data

    @staticmethod
    def _load_sync():
        """Método síncrono interno para lectura."""
        with open(RSS_DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)

    @classmethod
    async def save(cls):
        """Guarda la DB usando atomic write en un hilo separado."""
        if cls._data is None: return
        
        async with cls._lock:  # Asegurar que solo uno escriba a la vez
            try:
                await asyncio.to_thread(cls._save_sync, cls._data.copy())
            except Exception as e:
                log(f"Error guardando DB: {e}", "error")

    @staticmethod
    def _save_sync(data_copy):
        """Método síncrono interno para escritura atómica."""
        temp = f"{RSS_DATA_FILE}.tmp"
        with open(temp, 'w', encoding='utf-8') as f:
            json.dump(data_copy, f, indent=4, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno()) 
        os.replace(temp, RSS_DATA_FILE)

    @classmethod
    async def get_user(cls, user_id):
        await cls.load()
        uid = str(user_id)
        if uid not in cls._data:
            cls._data[uid] = {
                "channels": [],
                "feeds": [],
                "settings": {"active": True}
            }
            await cls.save()
        return cls._data[uid]

    @classmethod
    async def add_channel(cls, user_id, cid, title):
        """
        Añade un canal verificando primero que NO exista en NINGÚN usuario.
        """
        await cls.load() # Asegurar carga
        try:
            cid = int(cid)
        except:
            pass
            
        # 1. Validación Global: Recorremos todos los usuarios para ver si el canal ya existe
        for uid, udata in cls._data.items():
            for ch in udata.get('channels', []):
                if ch['id'] == cid:
                    # Si el canal ya existe, verificamos si es del mismo usuario o de otro
                    return "exist_global" # Código interno para indicar duplicado global

        # 2. Si no existe, lo añadimos al usuario actual
        user_data = await cls.get_user(user_id)
        user_data['channels'].append({"id": cid, "title": title})
        await cls.save()
        return "success"

   
    @classmethod
    async def add_feed(cls, user_id, original_url, resolved_url, channel_id, source_title, last_hash):
        """
        Añade un feed guardando tanto la URL original como la resuelta (XML).
        """
        data = await cls.get_user(user_id)
        
        # Validación de duplicados usando la URL RESUELTA (limpia)
        clean_resolved = resolved_url.strip()
        for f in data['feeds']:
            if f.get('url', '').strip() == clean_resolved:
                return None 
        
        feed_id = str(uuid.uuid4())[:8]
        
        new_feed = {
            "id": feed_id,
            "url": clean_resolved,        # La URL técnica (XML) que usa el Monitor
            "original_url": original_url, # La URL que ingresó el usuario
            "channel_id": channel_id,
            "title": source_title,
            "active": True,
            "style": "bitbread", 
            "template": None, 
            "last_hash": last_hash,
            "history": [last_hash],
            "stats": {"sent": 0, "errors": 0},
            "interval": 10,
            "created_at": datetime.now().isoformat()
        }
        data['feeds'].append(new_feed)
        await cls.save()
        return new_feed
    
    @classmethod
    async def update_feed_channel(cls, user_id, feed_id, new_channel_id):
        """
        Actualiza el ID del canal de destino para un feed específico.
        """
        data = await cls.get_user(user_id)
        new_channel_id = int(new_channel_id)
        
        # Verificamos que el canal exista en la lista del usuario (seguridad)
        channel_exists = any(c['id'] == new_channel_id for c in data['channels'])
        if not channel_exists:
            return False

        for feed in data['feeds']:
            if feed['id'] == feed_id:
                feed['channel_id'] = new_channel_id
                await cls.save()
                return True
        return False
    
    @classmethod
    async def delete_feed(cls, user_id, feed_id):
        data = await cls.get_user(user_id)
        data['feeds'] = [f for f in data['feeds'] if f['id'] != feed_id]
        await cls.save()

    @classmethod
    async def delete_channel(cls, user_id, channel_id):
        data = await cls.get_user(user_id)
        cid_str = str(channel_id)
        data['channels'] = [c for c in data['channels'] if str(c['id']) != cid_str]
        await cls.save()

    @classmethod
    async def update_template(cls, user_id, feed_id, template):
        data = await cls.get_user(user_id)
        for feed in data['feeds']:
            if feed['id'] == feed_id:
                feed['template'] = template
                await cls.save()
                return True
        return False

    @classmethod
    async def toggle_style(cls, user_id, feed_id):
        data = await cls.get_user(user_id)
        for feed in data['feeds']:
            if feed['id'] == feed_id:
                current = feed.get('style', 'bitbread')
                feed['style'] = 'text' if current == 'bitbread' else 'bitbread'
                await cls.save()
                return feed['style']
        return None
    
    @classmethod
    async def update_interval(cls, user_id, feed_id, minutes):
        data = await cls.get_user(user_id)
        for feed in data['feeds']:
            if feed['id'] == feed_id:
                feed['interval'] = int(minutes)
                feed['last_check'] = 0 
                await cls.save()
                return True
        return False
    
    @classmethod
    async def update_feed_url(cls, user_id, feed_id, new_url):
        data = await cls.get_user(user_id)
        for feed in data['feeds']:
            if feed['id'] == feed_id:
                feed['url'] = new_url
                await cls.save()
                return True
        return False
    
    @classmethod
    async def update_feed_rhash(cls, user_id, feed_id, rhash):
        """Guarda el identificador rhash para Instant View."""
        data = await cls.get_user(user_id)
        for feed in data['feeds']:
            if feed['id'] == feed_id:
                # Si el rhash es "none" o vacío, lo eliminamos
                if not rhash or rhash.lower() == 'none':
                    feed.pop('rhash', None)
                else:
                    feed['rhash'] = rhash
                await cls.save()
                return True
        return False