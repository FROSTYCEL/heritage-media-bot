import os
import re
import logging
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------- CONFIG (set these as environment variables on Render, not in this file) ----------
BOT_TOKEN = os.environ["BOT_TOKEN"]
GROUP_CHAT_ID = int(os.environ["GROUP_CHAT_ID"])
PORT = int(os.environ.get("PORT", 8080))


# ---------- TINY HEALTH-CHECK WEB SERVER
