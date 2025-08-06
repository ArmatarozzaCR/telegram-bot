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
reclutamento_group_id = -1002544640127
benvenuto_group_id = -1001834238708
benvenuto_topic_id = 60864
dati_giocatori = {}

async def nuovo_utente(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for member in update.message.new_chat_members:
        user_id = member.id
        utenti_in_attesa[user_id] = {"group_id": update.effective_chat.id, "nome": member.full_name, "username": member.username}
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("clicca qua / click here", url=f"https://t.me/{context.bot.username}?start=join")]
        ])
        username_display = f"@{member.username}" if member.username else "nessun username"
        messaggio = f"""👋 Benvenuto/a {member.full_name} ({username_display})!

🇮🇹 Questo è il gruppo di reclutamento della nostra grande Family!

⬇️ Clicca sul pulsante qui sotto per iniziare il tuo reclutamento.

—

🇬🇧 This is the recruitment group of our great Family!

⬇️ Click the button below to start your recruitment."""
        await context.bot.send_message(chat_id=update.effective_chat.id, text=messaggio, reply_markup=keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if context.args and context.args[0] == "join" and user_id in utenti_in_attesa:
        await update.message.reply_text("Benvenuto, mandami il tuo tag in game che inizia con # e prosegui il reclutamento nel gruppo.\n\n Welcome, send me your in-game tag starting with # and continue the recruitment process in the group.")
    else:
        await update.message.reply_text("Benvenuto! Usa il gruppo @reclutarozzi per unirti e iniziare il reclutamento.\n\nWelcome! Use the group @reclutarozzi to join and start recruitment.")

async def invia_resoconto(user_id, context):
    if user_id not in dati_giocatori:
        return
    dati = dati_giocatori[user_id]
    group_id = reclutamento_group_id
    nome = dati["nome"]
    username = dati["username"]
    username_display = f"@{username}" if username else "nessun username"
    tag = dati["tag"]
    user_lang = dati.get("user_lang", "sconosciuta")
    paese = codice_to_paese.get(user_lang, "non identificato")
    link = f"https://royaleapi.com/player/{tag}"
    messaggio = f"""👤 {nome} ({username_display})

🌍 Lingua: {user_lang.upper()}
📍 Provenienza: {paese}

🔗 Profilo giocatore: {link}"""
    msg = await context.bot.send_message(chat_id=group_id, text=messaggio)
    dati["last_message_id"] = msg.message_id
    if not username:
        await context.bot.send_message(chat_id=group_id, text=f"❗ @{nome}, inserisci un username Telegram per facilitare il tuo reclutamento", reply_to_message_id=msg.message_id)

async def ricevi_tag_privato(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    if user_id in utenti_in_attesa:
        match = re.search(r"#([A-Z0-9]+)", text.upper())
        if match:
            tag = match.group(1)
            user_lang = update.effective_user.language_code or "sconosciuta"
            nome = utenti_in_attesa[user_id]["nome"]
            username = utenti_in_attesa[user_id]["username"]
            dati_giocatori[user_id] = {
                "nome": nome,
                "username": username,
                "tag": tag,
                "user_lang": user_lang,
                "last_message_id": None
            }
            await invia_resoconto(user_id, context)
            del utenti_in_attesa[user_id]
        else:
            await update.message.reply_text("❗Per favore, scrivimi il tuo tag giocatore (es: #ABC123).\n\nPlease write me your player tag (like #ABC123). ")
    else:
        await update.message.reply_text("Continua il reclutamento nel gruppo @reclutarozzi, dopo un attenta valutazione del profilo ti diremo in quale clan verrai ammesso.")

async def monitora_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != reclutamento_group_id:
        return
    user = update.effective_user
    if user.id in dati_giocatori:
        vecchio_username = dati_giocatori[user.id].get("username")
        nuovo_username = user.username
        if vecchio_username != nuovo_username:
            dati_giocatori[user.id]["username"] = nuovo_username
            msg_id = dati_giocatori[user.id].get("last_message_id")
            if msg_id:
                try:
                    await context.bot.delete_message(chat_id=reclutamento_group_id, message_id=msg_id)
                except:
                    pass
            await invia_resoconto(user.id, context)

async def benvenuto_secondo_gruppo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for member in update.message.new_chat_members:
        user_id = member.id
        if user_id in dati_giocatori:
            dati = dati_giocatori[user_id]
            nome = dati["nome"]
            username = dati["username"]
            username_display = f"@{username}" if username else "nessun username"
            tag = dati["tag"]
            link = f"https://royaleapi.com/player/{tag}"
            messaggio = f"👋 Benvenuto/a {nome} ({username_display})!\n\n🔗 Profilo giocatore: {link}"
            await context.bot.send_message(chat_id=benvenuto_group_id, text=messaggio, message_thread_id=benvenuto_topic_id)
        else:
            mention = f"[{member.full_name}](tg://user?id={user_id})"
            messaggio = f"❗ Ciao {mention}, per favore unisciti prima al gruppo @reclutarozzi per completare il reclutamento."
            await context.bot.send_message(chat_id=benvenuto_group_id, text=messaggio, parse_mode="Markdown", message_thread_id=benvenuto_topic_id)

app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS & filters.Chat(benvenuto_group_id), benvenuto_secondo_gruppo))
app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS & filters.Chat(reclutamento_group_id), nuovo_utente))
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.TEXT & (~filters.COMMAND), ricevi_tag_privato))
app.add_handler(MessageHandler(filters.Chat(reclutamento_group_id) & filters.TEXT & (~filters.COMMAND), monitora_username))

print("✅ Bot in esecuzione con polling...")
app.run_polling()