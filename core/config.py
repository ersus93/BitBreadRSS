import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TELEGRAM_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
RSS_DATA_FILE = os.path.join(DATA_DIR, "rss_data.json")
TEMPLATES_JSON_FILE = os.path.join(DATA_DIR, "global_templates.json")

if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

try:
    with open(os.path.join(BASE_DIR, "version.txt"), "r") as f:
        BOT_VERSION = f.read().strip()
except Exception as e:
    print(f"⚠️ No se pudo leer version.txt: {e}")
    BOT_VERSION = "0.0.0"
    