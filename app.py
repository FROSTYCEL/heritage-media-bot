import os
import re
import logging
import asyncio
from datetime import datetime

from aiohttp import web
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

# httpx (used internally by the bot library) logs every API request URL at INFO level,
# which includes your bot token. Quiet it down so the token never appears in logs.
logging.getLogger("httpx").setLevel(logging.WARNING)

# ---------- CONFIG (set these as environment variables on Render, not in this file) ----------
BOT_TOKEN = os.environ["BOT_TOKEN"]
GROUP_CHAT_ID = int(os.environ["GROUP_CHAT_ID"])
WEBHOOK_URL = os.environ["WEBHOOK_URL"]  # e.g. https://your-app-name.onrender.com
PORT = int(os.environ.get("PORT", 8080))

# ---------- STATE ----------
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

    date_part = datetime.now().strftime("%y%m%d-%H%M%S")
    request_id = "HM-" + date_part
    timestamp = datetime.now().strftime("%d %b %Y, %H:%M")
    requester = update.effective_user.full_name
    label = cfg["label"]

    if update.effective_user.username:
        username = "@" + update.effective_user.username
    else:
        username = "(no username)"

    summary_lines = [
        "NEW " + label + " - " + request_id,
        "Submitted by: " + requester + " " + username,
        "Time: " + timestamp,
        "",
    ]
    for field in cfg["fields"]:
        summary_lines.append(f"{field}: {parsed[field]}")

    summary = "\n".join(summary_lines)

    await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=summary)
    await update.message.reply_text(
        f"✅ Submitted! Your request ID is {request_id}.\n"
        f"The Heritage Media Team has been notified in the group chat."
    )

    del pending[user_id]


async def health(request):
    return web.Response(text="Heritage Media Bot is running")


async def telegram_webhook(request):
    application = request.app["bot_application"]
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return web.Response(text="OK")


async def main():
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    await application.initialize()
    await application.bot.set_webhook(url=f"{WEBHOOK_URL}/{BOT_TOKEN}")
    await application.start()

    web_app = web.Application()
    web_app["bot_application"] = application
    # Health check: Render pings this to confirm the service is alive.
    web_app.router.add_get("/", health)
    # Real Telegram traffic lands here.
    web_app.router.add_post(f"/{BOT_TOKEN}", telegram_webhook)

    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()

    logger.info("Bot is up and listening on port %s", PORT)

    # Keep the process alive indefinitely
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
