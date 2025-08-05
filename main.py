from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, filters
import re
import os

TOKEN = os.getenv("TOKEN")
utenti_in_attesa = {}

codice_to_paese = {
    "it": "Italia",
    "en": "Paesi anglofoni",
    "fr": "Francia",
    "de": "Germania",
    "es": "Spagna / Sud America",
    "pt": "Portogallo / Brasile",
    "ru": "Russia",
    "ar": "Paesi arabi",
    "tr": "Turchia",
    "zh": "Cina",
    "ja": "Giappone",
    "ko": "Corea del Sud"
}

async def nuovo_utente(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for member in update.message.new_chat_members:
        user_id = member.id
        utenti_in_attesa[user_id] = update.effective_chat.id

        nome = member.full_name
        username = f"@{member.username}" if member.username else "nessun username"
        lingua = member.language_code or "sconosciuta"
        paese = codice_to_paese.get(lingua, "non identificato")

        if lingua == "it":
            messaggio = f"""👋 Benvenuto/a {nome} ({username})!

🌍 Lingua del tuo Telegram: **{lingua.upper()}**
📍 Provenienza stimata: **{paese}**

🇮🇹 Questo è il gruppo di passaggio per far parte della nostra grande Family. Aiutaci a scalare le classifiche italiane e mondiali a suon di guerre tra clan 💪😉  
Per favore, scrivi qua sotto il tuo nome in game e il tuo tag player in modo da permetterci di dare un'occhiata al tuo account."""
        else:
            messaggio = f"""👋 Welcome {nome} ({username})!

🌍 Telegram language: **{lingua.upper()}**
📍 Estimated location: **{paese}**

🇬🇧 Welcome to the "check-in" telegram group of our great Family. Help us climb the Italian and world rankings with clan wars 💪😉  
Please write your in-game name and player tag below, so we can take a look at your account."""

        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=messaggio
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

app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, nuovo_utente))
app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), ricevi_tag))
print("✅ Bot in esecuzione con polling...")
app.run_polling()
