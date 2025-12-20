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
        data = await cls.get_user(user_id)
        try:
            cid = int(cid)
        except:
            pass
            
        if any(c['id'] == cid for c in data['channels']):
            return False
        data['channels'].append({"id": cid, "title": title})
        await cls.save()
        return True

    @classmethod
    async def add_feed(cls, user_id, url, channel_id, source_title, last_hash):
        data = await cls.get_user(user_id)
        feed_id = str(uuid.uuid4())[:8]
        
        new_feed = {
            "id": feed_id,
            "url": url,
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