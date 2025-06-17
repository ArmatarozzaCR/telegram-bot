from flask import Flask, request
from telegram import Update, Bot
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, filters
import asyncio
import re

# --- CONFIGURAZIONE TOKEN ---
TOKEN = "8193058864:AAFbZmo4wVFvUcXOoVETYGngX4ExjNSMk0I"

# --- VARIABILE GLOBALE ---
utenti_in_attesa = {}

# --- HANDLERS ---
async def nuovo_utente(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for member in update.message.new_chat_members:
        user_id = member.id
        utenti_in_attesa[user_id] = update.effective_chat.id

        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="""🇮🇹 Benvenuto/a nel gruppo telegram di passaggio per far parte della nostra grande Family. Aiutaci a scalare le classifiche italiane e mondiali a suon di guerre tra clan💪😉   
Per favore, scrivi qua sotto il tuo nome in game e il tuo tag player, in modo da permetterci di dare un'occhiata al tuo account.

🇬🇧 Welcome to the "check-in" telegram group of our great Family. Help us climb the Italian and world rankings with clan wars💪😉 
Please, write your in-game name and your player tag, so that we can take a look at your account."""
        )

async def ricevi_tag(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    match = re.search(r"#([A-Z0-9]+)", text.upper())

    if match and user_id in utenti_in_attesa:
        tag = match.group(1)
        url = f"https://royaleapi.com/player/{tag}"

        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"🔗 Ecco il profilo del giocatore: {url}"
        )
        del utenti_in_attesa[user_id]
    elif match is None and user_id in utenti_in_attesa:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="❗ Per favore, includi il tag del giocatore che inizia con # nel testo."
        )

# --- FLASK APP ---
app_web = Flask(__name__)

@app_web.route("/", methods=["GET"])
def home():
    return "Bot is running!"

@app_web.route(f"/{TOKEN}", methods=["POST"])
async def webhook():
    update = Update.de_json(request.get_json(force=True), bot)
    await application.process_update(update)
    return "OK"

# --- SETUP ---
if __name__ == "__main__":
    # 1️⃣ Costruisci l'app telegram
    application = ApplicationBuilder().token(TOKEN).build()

    # 2️⃣ Registra i due handlers
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, nuovo_utente))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), ricevi_tag))

    # 3️⃣ Istanzia il bot
    bot = Bot(token=TOKEN)

    # 4️⃣ Webhook URL
    WEBHOOK_URL = f"https://telegram-bot-delicate-dream-3318.fly.dev/{TOKEN}"

    # 5️⃣ Imposta il webhook
    asyncio.run(bot.delete_webhook())
    asyncio.run(bot.set_webhook(url=WEBHOOK_URL))

    print("✅ Webhook impostato:", WEBHOOK_URL)
    print("🚀 Avvio server Flask su porta 8080")

    # 6️⃣ Avvia server Flask
    app_web.run(host="0.0.0.0", port=8080)