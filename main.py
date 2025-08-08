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
import gspread
from google.oauth2.service_account import Credentials

TOKEN = os.getenv("TOKEN")

SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
CREDS_FILE = 'credentials.json'
SPREADSHEET_ID = "1JhIhbMrBU-V9_OGpWMiwrCFhzx0blInGP6-6G_TCyFw"

creds = Credentials.from_service_account_file(CREDS_FILE, scopes=SCOPES)
gc = gspread.authorize(creds)
sheet = gc.open_by_key(SPREADSHEET_ID).sheet1

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

def carica_da_google_sheet():
    global dati_giocatori
    dati_giocatori = {}
    rows = sheet.get_all_records()
    for row in rows:
        try:
            user_id = int(row.get("user_id"))
        except:
            continue
        dati_giocatori[user_id] = {
            "nome": row.get("nome", ""),
            "username": row.get("username", ""),
            "tag": row.get("tag", ""),
            "user_lang": row.get("user_lang", ""),
            "nel_benvenuto": True if str(row.get("family", "")).lower() == "sì" else False,
            "last_message_id": None,
            "gestione_message_id": None,
            "data_ingresso": row.get("data_ingresso", "") 
        }

carica_da_google_sheet()

def salva_su_google_sheet(user_id):
    dati = dati_giocatori.get(user_id)
    if not dati:
        return
    rows = sheet.get_all_records()
    riga_da_aggiornare = None
    for i, row in enumerate(rows, start=2):
        if str(row.get("user_id")) == str(user_id):
            riga_da_aggiornare = i
            break
    valori = [
        str(user_id),
        dati.get("nome", ""),
        dati.get("username", ""),
        dati.get("tag", ""),
        dati.get("user_lang", ""),
        "Sì" if dati.get("nel_benvenuto", False) else "No",
        dati.get("data_ingresso", "")
    ]
    if riga_da_aggiornare:
        sheet.update(f"A{riga_da_aggiornare}:G{riga_da_aggiornare}", [valori])
    else:
        valori_da_aggiungere = valori.copy()
        if not valori_da_aggiungere[6]:
            from datetime import datetime
            valori_da_aggiungere[6] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            dati["data_ingresso"] = valori_da_aggiungere[6]
        sheet.append_row(valori_da_aggiungere)

async def nuovo_utente(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for member in update.message.new_chat_members:
        user_id = member.id
        utenti_in_attesa[user_id] = {"group_id": update.effective_chat.id, "nome": member.full_name, "username": member.username}
        await context.bot.restrict_chat_member(
            chat_id=update.effective_chat.id,
            user_id=user_id,
            permissions=permessi_bloccati
        )
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
    dati = dati_giocatori.get(user_id)
    if not dati:
        return
    group_id = reclutamento_group_id
    nome = dati.get("nome", "Utente")
    username = dati.get("username")
    username_display = f"@{username}" if username else "nessun username"
    tag = dati.get("tag", "sconosciuto")
    user_lang = dati.get("user_lang", None)
    if user_lang:
        paese = codice_to_paese.get(user_lang, "non identificato")
        lang_line = f"🌍 Lingua: {user_lang.upper()}"
        paese_line = f"📍 Provenienza: {paese}"
    else:
        lang_line = ""
        paese_line = ""
    link = f"https://royaleapi.com/player/{tag}"
    messaggio = f"""👤 {nome} ({username_display})

{lang_line}
{paese_line}

🔗 Profilo giocatore: {link}"""
    msg = await context.bot.send_message(chat_id=group_id, text=messaggio)
    dati["last_message_id"] = msg.message_id
    if not username:
        if paese == "Italia":
            avviso = f"⚠️ {nome}, inserisci un username Telegram per facilitare il tuo reclutamento."
        else:
            avviso = f"⚠️ {nome}, please set a Telegram username to make your recruitment easier."
        await context.bot.send_message(chat_id=group_id, text=avviso, reply_to_message_id=msg.message_id)
    salva_su_google_sheet(user_id)

async def invia_resoconto_gestione(user_id, context, vecchio_tag=None):
    dati = dati_giocatori.get(user_id)
    if not dati:
        return
    nome = dati.get("nome", "Utente")
    username = dati.get("username")
    username_display = f"@{username}" if username else "nessun username"
    tag = dati.get("tag", "sconosciuto")
    user_lang = dati.get("user_lang", None)
    nel_benvenuto = dati.get("nel_benvenuto", False)
    if user_lang:
        paese = codice_to_paese.get(user_lang, "non identificato")
        lang_line = f"🌍 Lingua: {user_lang.upper()}"
        paese_line = f"📍 Provenienza: {paese}"
    else:
        lang_line = ""
        paese_line = ""
    link = f"https://royaleapi.com/player/{tag}"
    avviso_tag_modificato = ""
    if vecchio_tag and vecchio_tag != tag:
        avviso_tag_modificato = f"\n⚠️ Tag precedente: https://royaleapi.com/player/{vecchio_tag}"
    messaggio = f"""👤 {nome} ({username_display})

{lang_line}
{paese_line}
🔗 Profilo giocatore: {link}{avviso_tag_modificato}
📥 Presente nel gruppo Family: {"✅ Sì" if nel_benvenuto else "❌ No"}"""
    old_msg_id = dati.get("gestione_message_id")
    if old_msg_id:
        try:
            await context.bot.delete_message(chat_id=gestione_group_id, message_id=old_msg_id)
        except:
            pass
    msg = await context.bot.send_message(
        chat_id=gestione_group_id,
        text=messaggio,
        message_thread_id=gestione_topic_id
    )
    dati["gestione_message_id"] = msg.message_id
    salva_su_google_sheet(user_id)

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
                "last_message_id": None,
                "gestione_message_id": None,
                "nel_benvenuto": False,
                "data_ingresso": ""
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
        await context.bot.restrict_chat_member(
            chat_id=update.effective_chat.id,
            user_id=user_id,
            permissions=permessi_bloccati
        )
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
            messaggio = benv
            await context.bot.send_message(chat_id=benvenuto_group_id, text=messaggio, message_thread_id=benvenuto_topic_id)
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
    if user_id is not None:
        vecchio_tag = dati_giocatori[user_id].get("tag")
        dati_giocatori[user_id]["tag"] = tag_arg
        await invia_resoconto(user_id, context)
        await invia_resoconto_gestione(user_id, context, vecchio_tag=vecchio_tag)
        await update.message.reply_text(f"Tag aggiornato per @{username_arg} a #{tag_arg} e resoconti rigenerati.")
        return
    for uid, dati in utenti_in_attesa.items():
        if dati.get("username", "").lower() == username_arg.lower():
            user_id = uid
            dati_giocatori[user_id] = {
                "nome": dati.get("nome", username_arg),
                "username": dati.get("username", username_arg),
                "tag": tag_arg,
                "user_lang": "sconosciuta",
                "last_message_id": None,
                "gestione_message_id": None,
                "nel_benvenuto": False,
                "data_ingresso": ""
            }
            await invia_resoconto(user_id, context)
            await invia_resoconto_gestione(user_id, context)
            await update.message.reply_text(f"Tag aggiornato per @{username_arg} a #{tag_arg} e resoconti rigenerati.")
            return
    fake_user_id = - (len(dati_giocatori) + len(utenti_in_attesa) + 1)
    dati_giocatori[fake_user_id] = {
        "nome": username_arg,
        "username": username_arg,
        "tag": tag_arg,
        "user_lang": None,
        "last_message_id": None,
        "gestione_message_id": None,
        "nel_benvenuto": False,
        "data_ingresso": ""
    }
    await invia_resoconto(fake_user_id, context)
    await invia_resoconto_gestione(fake_user_id, context)
    await update.message.reply_text(f"Nuovo profilo creato per @{username_arg} con tag #{tag_arg} e resoconti rigenerati.")

app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS & filters.Chat(benvenuto_group_id), benvenuto_secondo_gruppo))
app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS & filters.Chat(reclutamento_group_id), nuovo_utente))
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.TEXT & (~filters.COMMAND), ricevi_tag_privato))
app.add_handler(MessageHandler(filters.Chat(reclutamento_group_id) & filters.TEXT & (~filters.COMMAND), monitora_username))
app.add_handler(CommandHandler("updatetag", updatetag, filters.Chat(reclutamento_group_id)))

async def aggiorna_dati_tag_scraping(user_id, context):
    import requests
    dati = dati_giocatori.get(user_id)
    if not dati:
        return
    tag = dati.get("tag")
    if not tag:
        return
    url = f"https://royaleapi.com/player/{tag}"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code != 200:
            return
        testo = r.text
        match_nome = re.search(r'<h1[^>]*>([^<]+)</h1>', testo)
        if match_nome:
            nome_estratto = match_nome.group(1).strip()
            dati["nome"] = nome_estratto
        match_tag = re.search(r'Tag: #([A-Z0-9]+)', testo)
        if match_tag:
            tag_estratto = match_tag.group(1)
            if tag_estratto != tag:
                dati["tag"] = tag_estratto
    except:
        return
    salva_su_google_sheet(user_id)
    await invia_resoconto(user_id, context)
    await invia_resoconto_gestione(user_id, context)

async def aggiorna_tutti_i_dati_scraping(context):
    for user_id in list(dati_giocatori.keys()):
        await aggiorna_dati_tag_scraping(user_id, context)

async def comando_aggiorna_tutti(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    try:
        member = await context.bot.get_chat_member(chat.id, user.id)
        if not (member.status in ['administrator', 'creator']):
            await update.message.reply_text("❌ Solo admin possono usare questo comando.")
            return
    except:
        await update.message.reply_text("Errore nel verificare i permessi.")
        return
    await update.message.reply_text("Aggiornamento dati in corso...")
    await aggiorna_tutti_i_dati_scraping(context)
    await update.message.reply_text("Aggiornamento dati completato.")

app.add_handler(CommandHandler("aggiornatutti", comando_aggiorna_tutti, filters.Chat(gestione_group_id)))

print("✅ Bot in esecuzione con polling...")
app.run_polling()