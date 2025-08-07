from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CommandHandler,
    ContextTypes,
    filters,
)
from telegram.error import BadRequest
import os
import re

TOKEN = os.getenv("TOKEN")

utenti_in_attesa = {}
dati_giocatori = {}

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
gestione_group_id = -1002020527955
gestione_topic_id = 76313

permessi_bloccati = ChatPermissions(can_send_messages=False)
permessi_sbloccati = ChatPermissions(
    can_send_messages=True,
    can_send_other_messages=True,
    can_add_web_page_previews=True
)

async def nuovo_utente(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for member in update.message.new_chat_members:
        user_id = member.id
        group_id = update.effective_chat.id
        nome = member.full_name
        username = member.username

        utenti_in_attesa[user_id] = {
            "group_id": group_id,
            "nome": nome,
            "username": username
        }

        await context.bot.restrict_chat_member(
            chat_id=group_id,
            user_id=user_id,
            permissions=permessi_bloccati
        )

        if user_id in dati_giocatori:
            dati = dati_giocatori[user_id]
            vecchio_tag = dati.get("tag")
            old_msg_id = dati.get("gestione_message_id")
            if old_msg_id:
                try:
                    await context.bot.delete_message(chat_id=gestione_group_id, message_id=old_msg_id)
                except:
                    pass
            dati["nome"] = nome
            dati["username"] = username
            dati["nel_benvenuto"] = False
            dati["vecchio_tag"] = vecchio_tag

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("clicca qua / click here", url=f"https://t.me/{context.bot.username}?start=join")]
        ])
        username_display = f"@{username}" if username else "nessun username"
        messaggio = f"""👋 Benvenuto/a {nome} ({username_display})!

🇮🇹 Questo è il gruppo di reclutamento della nostra grande Family!

⬇️ Clicca sul pulsante qui sotto per iniziare il tuo reclutamento.

—

🇬🇧 This is the recruitment group of our great Family!

⬇️ Click the button below to start your recruitment."""
        await context.bot.send_message(chat_id=group_id, text=messaggio, reply_markup=keyboard)

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
        if paese == "Italia":
            avviso = f"⚠️ {nome}, inserisci un username Telegram per facilitare il tuo reclutamento."
        else:
            avviso = f"⚠️ {nome}, please set a Telegram username to make your recruitment easier."
        await context.bot.send_message(chat_id=group_id, text=avviso, reply_to_message_id=msg.message_id)

async def invia_resoconto_gestione(user_id, context):
    if user_id not in dati_giocatori:
        return
    dati = dati_giocatori[user_id]
    nome = dati["nome"]
    username = dati["username"]
    username_display = f"@{username}" if username else "nessun username"
    tag = dati["tag"]
    user_lang = dati.get("user_lang", "sconosciuta")
    paese = codice_to_paese.get(user_lang, "non identificato")
    nel_benvenuto = dati.get("nel_benvenuto", False)
    link = f"https://royaleapi.com/player/{tag}"
    messaggio = f"""👤 {nome} ({username_display})

🌍 Lingua: {user_lang.upper()}
📍 Provenienza: {paese}
📥 Presente nel gruppo Family: {"✅ Sì" if nel_benvenuto else "❌ No"}
🔗 Profilo giocatore: {link}"""
    if dati.get("tag_modificato"):
        vecchio_tag = dati.get("vecchio_tag")
        if vecchio_tag and vecchio_tag != tag:
            old_link = f"https://royaleapi.com/player/{vecchio_tag}"
            messaggio += f"\n🔄 *Cambio tag rilevato:*\n🧾 Vecchio: {old_link}\n🆕 Nuovo: {link}"
    old_msg_id = dati.get("gestione_message_id")
    if old_msg_id:
        try:
            await context.bot.delete_message(chat_id=gestione_group_id, message_id=old_msg_id)
        except:
            pass
    msg = await context.bot.send_message(
        chat_id=gestione_group_id,
        text=messaggio,
        message_thread_id=gestione_topic_id,
        parse_mode="Markdown"
    )
    dati["gestione_message_id"] = msg.message_id

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
            if user_id in dati_giocatori:
                vecchio_tag = dati_giocatori[user_id].get("tag")
                dati_giocatori[user_id]["vecchio_tag"] = vecchio_tag
                if vecchio_tag and vecchio_tag != tag:
                    dati_giocatori[user_id]["tag"] = tag
                    dati_giocatori[user_id]["tag_modificato"] = True
                else:
                    dati_giocatori[user_id]["tag"] = tag
                    dati_giocatori[user_id]["tag_modificato"] = False
            else:
                dati_giocatori[user_id] = {
                    "nome": nome,
                    "username": username,
                    "tag": tag,
                    "user_lang": user_lang,
                    "last_message_id": None,
                    "gestione_message_id": None,
                    "nel_benvenuto": False,
                    "vecchio_tag": None,
                    "tag_modificato": False
                }
            await invia_resoconto(user_id, context)
            await invia_resoconto_gestione(user_id, context)
            await context.bot.restrict_chat_member(
                chat_id=reclutamento_group_id,
                user_id=user_id,
                permissions=permessi_sbloccati
            )
            del utenti_in_attesa[user_id]
        else:
            await update.message.reply_text("❗Per favore, scrivimi il tuo tag in game (es: #VPJJPQCPG).\n\nPlease write me your player tag (like #VPJJPQCPG). ")
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
            await invia_resoconto_gestione(user.id, context)

async def benvenuto_secondo_gruppo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for member in update.message.new_chat_members:
        user_id = member.id
        if user_id in dati_giocatori:
            dati = dati_giocatori[user_id]
            dati["nel_benvenuto"] = True
            await invia_resoconto_gestione(user_id, context)
            nome = dati["nome"]
            username = dati["username"]
            username_display = f"@{username}" if username else "nessun username"
            tag = dati["tag"]
            link = f"https://royaleapi.com/player/{tag}"
            if codice_to_paese.get(dati["user_lang"], "") == "Italia":
                benv = f"👋 Benvenuto/a {nome} ({username_display})!\n\n🔗 Profilo giocatore: {link}"
            else:
                benv = f"👋 Welcome {nome} ({username_display})!\n\n🔗 Player profile: {link}"
            await context.bot.send_message(chat_id=benvenuto_group_id, text=benv, message_thread_id=benvenuto_topic_id)
        else:
            mention = f"[{member.full_name}](tg://user?id={user_id})"
            messaggio = f"❗ Ciao {mention}, unisciti prima al gruppo @reclutarozzi per iniziare il tuo reclutamento."
            await context.bot.send_message(chat_id=benvenuto_group_id, text=messaggio, parse_mode="Markdown", message_thread_id=benvenuto_topic_id)

async def updatetag(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    try:
        member = await context.bot.get_chat_member(chat.id, user.id)
        if not (member.status in ['administrator', 'creator']):
            await update.message.reply_text("❌ Solo admin possono usare questo comando.")
            return
    except BadRequest:
        await update.message.reply_text("Errore nel verificare i permessi.")
        return
    if len(context.args) != 2:
        await update.message.reply_text("Uso corretto: /updatetag @username #TAG")
        return
    username_arg = context.args[0]
    tag_arg = context.args[1].upper()
    if username_arg.startswith("@"):
        username_arg = username_arg[1:]
    if not re.match(r"#?[A-Z0-9]+", tag_arg):
        await update.message.reply_text("Tag non valido. Deve iniziare con # e contenere lettere/numeri.")
        return
    tag_arg = tag_arg.lstrip("#")
    user_id = None
    for uid, dati in dati_giocatori.items():
        if dati.get("username", "").lower() == username_arg.lower():
            user_id = uid
            break
    if user_id is None:
        await update.message.reply_text(f"Utente @{username_arg} non trovato tra i giocatori registrati.")
        return
    vecchio_tag = dati_giocatori[user_id].get("tag")
    dati_giocatori[user_id]["vecchio_tag"] = vecchio_tag
    dati_giocatori[user_id]["tag"] = tag_arg
    dati_giocatori[user_id]["tag_modificato"] = vecchio_tag != tag_arg
    await invia_resoconto(user_id, context)
    await invia_resoconto_gestione(user_id, context)
    await update.message.reply_text(f"Tag aggiornato per @{username_arg} a #{tag_arg} e resoconti rigenerati.")

app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS & filters.Chat(benvenuto_group_id), benvenuto_secondo_gruppo))
app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS & filters.Chat(reclutamento_group_id), nuovo_utente))
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.TEXT & (~filters.COMMAND), ricevi_tag_privato))
app.add_handler(MessageHandler(filters.Chat(reclutamento_group_id) & filters.TEXT & (~filters.COMMAND), monitora_username))
app.add_handler(CommandHandler("updatetag", updatetag, filters.Chat(reclutamento_group_id)))

print("✅ Bot in esecuzione con polling...")
app.run_polling()