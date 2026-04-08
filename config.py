import os
from dotenv import load_dotenv

load_dotenv()

LINE_CHANNEL_SECRET = os.environ["LINE_CHANNEL_SECRET"]
LINE_CHANNEL_ACCESS_TOKEN = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
DATABASE_PATH = os.environ.get("DATABASE_PATH", "./inventory.db")
ALERT_HOUR = int(os.environ.get("ALERT_HOUR", "7"))
PORT = int(os.environ.get("PORT", "5000"))
