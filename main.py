from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CommandHandler,
    ContextTypes,
    filters,
)
import os
import re

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
        utenti_in_attesa[user_id] = {
            "group_id": update.effective_chat.id,
            "nome": member.full_name,
            "username": member.username
        }
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(
                "Inizia il tuo reclutamento / Start your recruitment",
                url=f"https://t.me/{context.bot.username}?start=join"
            )]
        ])
        messaggio = f"""👋 Benvenuto/a {member.full_name} (@{member.username or 'nessun username'})!

🇮🇹 Questo è il gruppo di reclutamento della nostra grande Family!

⬇ Clicca sul pulsante qui sotto per iniziare il tuo reclutamento.

—

🇬🇧 This is the recruitment group of our great Family!

⬇ Click the button below to start your recruitment."""
        await context.bot.send_message(chat_id=update.effective_chat.id, text=messaggio, reply_markup=keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if context.args and context.args[0] == "join" and user_id in utenti_in_attesa:
        await update.message.reply_text("Per favore, scrivi il tuo tag giocatore (es: #ABC123).")
    else:
        await update.message.reply_text("Benvenuto! Usa il gruppo per unirti e inizia il reclutamento.")

async def ricevi_tag_privato(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    if user_id in utenti_in_attesa:
        match = re.search(r"#([A-Z0-9]+)", text.upper())
        if match:
            tag = match.group(1)
            user_lang = update.effective_user.language_code or "sconosciuta"
            paese = codice_to_paese.get(user_lang, "non identificato")
            group_id = utenti_in_attesa[user_id]["group_id"]
            nome = utenti_in_attesa[user_id]["nome"]
            username = utenti_in_attesa[user_id]["username"]
            link = f"https://royaleapi.com/player/{tag}"
            messaggio = f"""👤 {nome} (@{username or 'nessun username'})

🌍 Lingua Telegram: {user_lang.upper()}
📍 Provenienza stimata: {paese}

🔗 Profilo giocatore: {link}"""
            await context.bot.send_message(chat_id=group_id, text=messaggio)
            del utenti_in_attesa[user_id]
        else:
            await update.message.reply_text("❗ Per favore, mandaci il tag in game che inizia con #.")
    else:
        await update.message.reply_text("Non risulti tra i nuovi utenti. Unisciti al gruppo prima di iniziare il reclutamento.")

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, nuovo_utente))
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PRIVATE & filters.TEXT & (~filters.COMMAND), ricevi_tag_privato))

    print("✅ Bot in esecuzione con polling...")
    app.run_polling()