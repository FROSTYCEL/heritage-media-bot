import os
import re
import logging
from datetime import datetime

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
WEBHOOK_URL = os.environ["WEBHOOK_URL"]  # e.g. https://your-app-name.onrender.com
PORT = int(os.environ.get("PORT", 8080))

# ---------- STATE ----------
# Tracks which form each user is currently filling in. Resets if the bot restarts,
# which is fine for this use case (user just picks the option again).
pending = {}

# ---------- TEMPLATES ----------
MEDIA_LOAN_FIELDS = [
    "Name/Rank",
    "Unit",
    "Item(s) Requested",
    "Loan Start Date",
    "Loan End Date",
    "Purpose/Event",
    "POC Contact",
]

PHOTOG_FIELDS = [
    "Event Name",
    "Date",
    "Time",
    "Location",
    "Requesting Unit/POC",
    "Number of Photographers Needed",
    "Deliverables Expected",
]

FORM_CONFIG = {
    "media_loan": {
        "label": "MEDIA LOAN REQUEST",
        "fields": MEDIA_LOAN_FIELDS,
    },
    "photog_request": {
        "label": "PHOTOGRAPHER REQUEST",
        "fields": PHOTOG_FIELDS,
    },
}


def build_template(request_type: str) -> str:
    cfg = FORM_CONFIG[request_type]
    lines = [cfg["label"]]
    lines += [f"{field}: " for field in cfg["fields"]]
    return "\n".join(lines)


# ---------- HANDLERS ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📦 Media Loan", callback_data="media_loan")],
        [InlineKeyboardButton("📸 Photographer Request", callback_data="photog_request")],
    ]
    await update.message.reply_text(
        "UAV Command Heritage Media Team Bot\n\nWhat would you like to do?",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    request_type = query.data
    user_id = query.from_user.id
    pending[user_id] = request_type

    template = build_template(request_type)
    label = FORM_CONFIG[request_type]["label"]

    await query.message.reply_text(
        f"Copy the template below, fill in every field after the colon, "
        f"then paste the whole thing back to me as ONE message.\n\n({label})"
    )
    await query.message.reply_text(template)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id not in pending:
        await update.message.reply_text(
            "Please use /start and choose Media Loan or Photographer Request first."
        )
        return

    request_type = pending[user_id]
    cfg = FORM_CONFIG[request_type]
    text = update.message.text or ""

    parsed = {}
    missing = []
    for field in cfg["fields"]:
        pattern = rf"{re.escape(field)}:\s*(.+)"
        match = re.search(pattern, text)
        if match and match.group(1).strip():
            parsed[field] = match.group(1).strip()
        else:
            missing.append(field)

    if missing:
        await update.message.reply_text(
            "A few fields are missing or empty:\n- "
            + "\n- ".join(missing)
            + "\n\nPlease resend the complete filled-in template."
        )
        return

    request_id = f"HM-{datetime.now().strftime('%y%m%d-%H%M%S')}
