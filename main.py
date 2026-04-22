from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions, CallbackQuery
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CommandHandler,
    CallbackQueryHandler,
    ChatMemberHandler,
    ContextTypes,
    filters,
)
from telegram.error import BadRequest
import os
import re
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
import logging
import time
import asyncio

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("TOKEN")

SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
CREDS_FILE = 'credentials.json'
SPREADSHEET_ID = "1JhIhbMrBU-V9_OGpWMiwrCFhzx0blInGP6-6G_TCyFw"

creds = Credentials.from_service_account_file(CREDS_FILE, scopes=SCOPES)
gc = gspread.authorize(creds)
sheet = gc.open_by_key(SPREADSHEET_ID).sheet1

war_group_id = -1001996604986
war_topic_id = 8543

# ⬇️ Sostituisci con il tuo ID Telegram numerico (scrivi /start a @userinfobot per trovarlo)
admin_log_chat_id = 8285233207

try:
    warn_sheet = gc.open_by_key(SPREADSHEET_ID).worksheet("Ammonizioni")
except:
    warn_sheet = gc.open_by_key(SPREADSHEET_ID).add_worksheet(title="Ammonizioni", rows="1000", cols="6")
    warn_sheet.append_row(["user_id", "username", "admin_who_warned", "data_warn", "data_scadenza", "active"])

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
gestione_group_id = -1002248491846
gestione_topic_id = 29730

permessi_bloccati = ChatPermissions(can_send_messages=False)
permessi_sbloccati = ChatPermissions(
    can_send_messages=True,
    can_send_other_messages=True,
    can_add_web_page_previews=True
)

def carica_da_google_sheet():
    global dati_giocatori
    dati_giocatori = {}
    try:
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
            }
        logger.info(f"Caricati {len(dati_giocatori)} giocatori da Google Sheet.")
    except Exception as e:
        logger.error(f"Errore caricamento Google Sheet: {e}")

carica_da_google_sheet()

def salva_su_google_sheet(user_id):
    dati = dati_giocatori.get(user_id)
    if not dati:
        return
    try:
        rows = sheet.get_all_records()
        riga_da_aggiornare = None
        data_ingresso_presente = None
        for i, row in enumerate(rows, start=2):
            if str(row.get("user_id")) == str(user_id):
                riga_da_aggiornare = i
                data_ingresso_presente = row.get("data_ingresso", None)
                break
        if not data_ingresso_presente:
            data_ingresso_presente = datetime.now().strftime("%Y-%m-%d")
        valori = [
            str(user_id),
            dati.get("nome", ""),
            dati.get("username", ""),
            dati.get("tag", ""),
            dati.get("user_lang", ""),
            "Sì" if dati.get("nel_benvenuto", False) else "No",
            data_ingresso_presente
        ]
        if riga_da_aggiornare:
            sheet.update(values=[valori], range_name=f"A{riga_da_aggiornare}:G{riga_da_aggiornare}")
        else:
            sheet.append_row(valori)
    except Exception as e:
        logger.error(f"Errore salvataggio Google Sheet per user_id={user_id}: {e}")

def pulisci_warn_scaduti():
    try:
        rows = warn_sheet.get_all_records()
        oggi = datetime.now()
        da_aggiornare = False
        nuove_righe = [["user_id", "username", "admin_who_warned", "data_warn", "data_scadenza", "active"]]
        for row in rows:
            scadenza_str = row.get("data_scadenza")
            try:
                scadenza = datetime.strptime(scadenza_str, "%Y-%m-%d")
                if oggi <= scadenza:
                    nuove_righe.append([
                        row["user_id"], row["username"], row["admin_who_warned"],
                        row["data_warn"], row["data_scadenza"], row.get("active", 1)
                    ])
                else:
                    da_aggiornare = True
            except:
                continue
        if da_aggiornare:
            warn_sheet.clear()
            warn_sheet.update(range_name="A1", values=nuove_righe)
    except Exception as e:
        logger.error(f"Errore pulizia warn: {e}")

async def sblocca_utente_con_retry(context, user_id, max_tentativi=3):
    for tentativo in range(1, max_tentativi + 1):
        try:
            await context.bot.restrict_chat_member(
                chat_id=reclutamento_group_id,
                user_id=user_id,
                permissions=permessi_sbloccati
            )
            return True
        except Exception:
            if tentativo < max_tentativi:
                await asyncio.sleep(1)
    return False

async def nuovo_utente(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for member in update.message.new_chat_members:
        user_id = member.id
        utenti_in_attesa[user_id] = {"group_id": update.effective_chat.id, "nome": member.full_name, "username": member.username}
        try:
            await context.bot.restrict_chat_member(
                chat_id=update.effective_chat.id,
                user_id=user_id,
                permissions=permessi_bloccati
            )
        except Exception as e:
            logger.error(f"Errore restrict_chat_member: {e}")
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
        try:
            await context.bot.send_message(chat_id=update.effective_chat.id, text=messaggio, reply_markup=keyboard)
        except Exception as e:
            logger.error(f"Errore invio messaggio benvenuto: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if context.args and context.args[0] == "join" and user_id in utenti_in_attesa:
        await update.message.reply_text("Benvenuto, mandami il tuo tag in game che inizia con # e prosegui il reclutamento nel gruppo.\n\nWelcome, send me your in-game tag starting with # and continue the recruitment process in the group.")
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
    if "prev_tag" in dati and dati["prev_tag"] != tag:
        messaggio += f"\n\n⚠️ Attenzione: il tag in game è stato aggiornato da #{dati['prev_tag']} a #{tag}."
    dati["prev_tag"] = tag
    old_msg_id = dati.get("last_message_id")
    if old_msg_id:
        try:
            await context.bot.delete_message(chat_id=group_id, message_id=old_msg_id)
        except Exception as e:
            logger.warning(f"Impossibile eliminare messaggio: {e}")
    try:
        msg = await context.bot.send_message(chat_id=group_id, text=messaggio)
        dati["last_message_id"] = msg.message_id
        if not username:
            if paese == "Italia":
                avviso = f"⚠️ {nome}, inserisci un username Telegram per facilitare il tuo reclutamento."
            else:
                avviso = f"⚠️ {nome}, please set a Telegram username to make your recruitment easier."
            await context.bot.send_message(chat_id=group_id, text=avviso, reply_to_message_id=msg.message_id)
        salva_su_google_sheet(user_id)
    except Exception as e:
        logger.error(f"Errore invio resoconto: {e}")

async def invia_resoconto_gestione(user_id, context):
    dati = dati_giocatori.get(user_id)
    if not dati:
        return
    nome = dati.get("nome", "Utente")
    username = dati.get("username")
    username_display = f"@{username}" if username else "nessun username"
    tag = dati.get("tag", "sconosciuto")
    prev_tag = dati.get("prev_tag", None)
    user_lang = dati.get("user_lang", None)
    nel_benvenuto = dati.get("nel_benvenuto", False)
    if user_lang:
        paese = codice_to_paese.get(user_lang, "non identificato")
        lang_line = f"🌍 Lingua: {user_lang.upper()}"
        paese_line = f"📍 Provenienza: {paese}"
    else:
        lang_line = ""
        paese_line = ""
    if prev_tag and prev_tag != tag:
        link_attuale = f"https://royaleapi.com/player/{tag}"
        link_precedente = f"https://royaleapi.com/player/{prev_tag}"
        doppio_tag_msg = f"\n\n⚠️ ATTENZIONE: Doppio tag rilevato:\n- Attuale: {link_attuale}\n- Precedente: {link_precedente}"
    else:
        doppio_tag_msg = ""
    link = f"https://royaleapi.com/player/{tag}"
    messaggio = f"""👤 {nome} ({username_display})

{lang_line}
{paese_line}
🔗 Profilo giocatore: {link}
📥 Presente nel gruppo Family: {"✅ Sì" if nel_benvenuto else "❌ No"}{doppio_tag_msg}"""
    old_msg_id = dati.get("gestione_message_id")
    if old_msg_id:
        try:
            await context.bot.delete_message(chat_id=gestione_group_id, message_id=old_msg_id)
        except Exception as e:
            logger.warning(f"Impossibile eliminare messaggio gestione: {e}")
    try:
        msg = await context.bot.send_message(
            chat_id=gestione_group_id,
            text=messaggio,
            message_thread_id=gestione_topic_id
        )
        dati["gestione_message_id"] = msg.message_id
        salva_su_google_sheet(user_id)
    except Exception as e:
        logger.error(f"Errore invio resoconto gestione: {e}")

async def ricevi_tag_privato(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    match = re.search(r"#([A-Z0-9]+)", text.upper())
    if match:
        tag = match.group(1)
        user_lang = update.effective_user.language_code or "sconosciuta"
        nome = None
        username = update.effective_user.username
        if user_id in utenti_in_attesa:
            nome = utenti_in_attesa[user_id]["nome"]
            username = utenti_in_attesa[user_id]["username"]
            del utenti_in_attesa[user_id]
        else:
            if user_id in dati_giocatori:
                nome = dati_giocatori[user_id].get("nome")
            else:
                nome = update.effective_user.full_name if hasattr(update.effective_user, 'full_name') else ""
        if user_id in dati_giocatori:
            dati_giocatori[user_id]["tag"] = tag
            dati_giocatori[user_id]["user_lang"] = user_lang
            dati_giocatori[user_id]["username"] = username
        else:
            dati_giocatori[user_id] = {
                "nome": nome,
                "username": username,
                "tag": tag,
                "user_lang": user_lang,
                "last_message_id": None,
                "gestione_message_id": None,
                "nel_benvenuto": False
            }
        try:
            await invia_resoconto(user_id, context)
            await invia_resoconto_gestione(user_id, context)
            sbloccato = await sblocca_utente_con_retry(context, user_id, max_tentativi=3)
            if not sbloccato:
                await update.message.reply_text("⚠️ Si è verificato un problema con lo sblocco. Contatta un admin.")
        except Exception as e:
            logger.error(f"Errore tag privato: {e}")
    else:
        await update.message.reply_text("❗Per favore, scrivimi il tuo tag in game (es: #VPJJPQCPG).\n\nPlease write me your player tag (like #VPJJPQCPG). ")

async def monitora_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != reclutamento_group_id:
        return
    user = update.effective_user
    if user.id in dati_giocatori:
        vecchio_username = dati_giocatori[user.id].get("username")
        nuovo_username = user.username
        if vecchio_username != nuovo_username:
            dati_giocatori[user.id]["username"] = nuovo_username
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
            messaggio = benv
            await context.bot.send_message(chat_id=benvenuto_group_id, text=messaggio, message_thread_id=benvenuto_topic_id)
        else:
            mention = f"[{member.full_name}](tg://user?id={user_id})"
            messaggio = f"❗ Ciao {mention}, unisciti prima al gruppo @reclutarozzi per iniziare il tuo reclutamento."
            await context.bot.send_message(chat_id=benvenuto_group_id, text=messaggio, parse_mode="Markdown", message_thread_id=benvenuto_topic_id)

# ─── LOG INGRESSI/USCITE GRUPPO WAR ───────────────────────────────────────────
async def log_war_member_change(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id if update.effective_chat else None
    logger.info(f"[WAR LOG] Evento ricevuto da chat {chat_id}")
    if chat_id != war_group_id:
        logger.info(f"[WAR LOG] Chat ID non corrisponde: {chat_id} != {war_group_id}")
        return

    member = None
    entrato = False

    if update.chat_member:
        cm = update.chat_member
        old_status = cm.old_chat_member.status
        new_status = cm.new_chat_member.status
        member = cm.new_chat_member.user
        logger.info(f"[WAR LOG] chat_member: {member.full_name} {old_status} -> {new_status}")
        if new_status in ("member", "administrator") and old_status not in ("member", "administrator", "creator"):
            entrato = True
        elif new_status in ("left", "kicked") and old_status in ("member", "administrator", "creator"):
            entrato = False
        else:
            return

    elif update.message:
        msg = update.message
        logger.info(f"[WAR LOG] message: new={msg.new_chat_members}, left={msg.left_chat_member}")
        if msg.new_chat_members:
            for m in msg.new_chat_members:
                username = f"@{m.username}" if m.username else "nessun username"
                testo = (
                    f"✅ <b>Entrato nel gruppo War:</b>\n"
                    f"{m.full_name} ({username})\n"
                    f"ID: <code>{m.id}</code>"
                )
                try:
                    await context.bot.send_message(chat_id=admin_log_chat_id, text=testo, parse_mode="HTML")
                    logger.info(f"[WAR LOG] Ingresso inviato per {m.full_name}")
                except Exception as e:
                    logger.error(f"Errore log ingresso war: {e}")
            return
        elif msg.left_chat_member:
            member = msg.left_chat_member
            entrato = False
        else:
            return
    else:
        return

    if member is None:
        return

    username = f"@{member.username}" if member.username else "nessun username"
    if entrato:
        testo = (
            f"✅ <b>Entrato nel gruppo War:</b>\n"
            f"{member.full_name} ({username})\n"
            f"ID: <code>{member.id}</code>"
        )
    else:
        testo = (
            f"❌ <b>Uscito dal gruppo War:</b>\n"
            f"{member.full_name} ({username})\n"
            f"ID: <code>{member.id}</code>"
        )
    try:
        await context.bot.send_message(chat_id=admin_log_chat_id, text=testo, parse_mode="HTML")
        logger.info(f"[WAR LOG] Messaggio {'ingresso' if entrato else 'uscita'} inviato per {member.full_name}")
    except Exception as e:
        logger.error(f"Errore log war: {e}")
# ──────────────────────────────────────────────────────────────────────────────

async def updatetag(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    if chat.id != reclutamento_group_id:
        await update.message.reply_text("Questo comando può essere usato solo nel gruppo reclutamento.")
        return
    try:
        member = await context.bot.get_chat_member(chat.id, user.id)
        if not (member.status in ['administrator', 'creator']):
            await update.message.reply_text("❌ Solo admin possono usare questo comando.")
            return
    except BadRequest:
        await update.message.reply_text("Errore nel verificare i permessi.")
        return
    target_user = None
    username_arg = None
    if update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
        if len(context.args) != 1:
            await update.message.reply_text("Uso corretto: rispondi con /updatetag #TAG")
            return
        tag_arg = context.args[0].upper()
    else:
        if len(context.args) != 2:
            await update.message.reply_text("Uso corretto: /updatetag @username #TAG")
            return
        username_arg = context.args[0]
        tag_arg = context.args[1].upper()
        if username_arg.startswith("@"):
            username_arg = username_arg[1:]
        if not username_arg:
            await update.message.reply_text("⚠️ Username non valido.")
            return
        for uid, dati in dati_giocatori.items():
            if dati.get("username", "").lower() == username_arg.lower():
                target_user = type('User', (object,), {
                    'id': uid,
                    'full_name': dati.get("nome", "Utente"),
                    'username': dati.get("username", ""),
                    'is_bot': False
                })
                break
        if not target_user:
            for uid, dati in utenti_in_attesa.items():
                if dati.get("username", "").lower() == username_arg.lower():
                    target_user = type('User', (object,), {
                        'id': uid,
                        'full_name': dati.get("nome", "Utente"),
                        'username': dati.get("username", ""),
                        'is_bot': False
                    })
                    break
        if not target_user:
            try:
                chat_target = await context.bot.get_chat(f"@{username_arg}")
                if chat_target:
                    target_user = chat_target
            except Exception:
                target_user = None
    if not re.match(r"^#?[A-Z0-9]+$", tag_arg):
        await update.message.reply_text("Tag non valido. Deve iniziare con # e contenere solo lettere/numeri.")
        return
    tag_arg = tag_arg.lstrip("#")
    user_id = getattr(target_user, 'id', None)
    if user_id is not None:
        if user_id not in dati_giocatori and username_arg:
            dati_giocatori[user_id] = {
                "nome": getattr(target_user, 'full_name', username_arg),
                "username": getattr(target_user, 'username', username_arg) or username_arg,
                "tag": tag_arg,
                "user_lang": None,
                "last_message_id": None,
                "gestione_message_id": None,
                "nel_benvenuto": False
            }
        dati_giocatori[user_id]["tag"] = tag_arg
        try:
            await invia_resoconto(user_id, context)
            await invia_resoconto_gestione(user_id, context)
            salva_su_google_sheet(user_id)
            username_display = getattr(target_user, 'username', username_arg) or username_arg or "utente"
            await update.message.reply_text(f"✅ Tag aggiornato per @{username_display} a #{tag_arg} e resoconti rigenerati.")
        except Exception as e:
            logger.error(f"Errore updatetag: {e}")
            await update.message.reply_text("⚠️ Tag salvato su database, ma errore nell'invio resoconti.")
        return
    for uid, dati in utenti_in_attesa.items():
        if username_arg and dati.get("username", "").lower() == username_arg.lower():
            user_id = uid
            dati_giocatori[user_id] = {
                "nome": dati.get("nome", username_arg),
                "username": dati.get("username", username_arg),
                "tag": tag_arg,
                "user_lang": "sconosciuta",
                "last_message_id": None,
                "gestione_message_id": None,
                "nel_benvenuto": False
            }
            del utenti_in_attesa[user_id]
            try:
                await invia_resoconto(user_id, context)
                await invia_resoconto_gestione(user_id, context)
                salva_su_google_sheet(user_id)
                await update.message.reply_text(f"✅ Tag aggiornato per @{username_arg} a #{tag_arg} e resoconti rigenerati.")
            except Exception as e:
                logger.error(f"Errore updatetag: {e}")
                await update.message.reply_text("⚠️ Tag salvato su database, ma errore nell'invio resoconti.")
            return
    fake_user_id = -int(time.time())
    dati_giocatori[fake_user_id] = {
        "nome": username_arg or "utente",
        "username": username_arg or "utente",
        "tag": tag_arg,
        "user_lang": None,
        "last_message_id": None,
        "gestione_message_id": None,
        "nel_benvenuto": False
    }
    try:
        await invia_resoconto(fake_user_id, context)
        await invia_resoconto_gestione(fake_user_id, context)
        salva_su_google_sheet(fake_user_id)
        await update.message.reply_text(f"✅ Nuovo profilo creato per @{username_arg} con tag #{tag_arg} e resoconti rigenerati.")
    except Exception as e:
        logger.error(f"Errore updatetag nuovo utente: {e}")
        await update.message.reply_text("⚠️ Profilo salvato su database, ma errore nell'invio resoconti.")

# ─── /infos DISPONIBILE IN TUTTI I GRUPPI ─────────────────────────────────────
async def infos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    try:
        member = await context.bot.get_chat_member(chat.id, user.id)
        if not (member.status in ['administrator', 'creator']):
            await update.message.reply_text("❌ Solo admin possono usare questo comando.")
            return
    except Exception:
        await update.message.reply_text("Errore nel verificare i permessi.")
        return

    target_user = None
    username_arg = None

    if update.message.reply_to_message:
        # Caso 1: risposta diretta a un messaggio
        target_user = update.message.reply_to_message.from_user
    else:
        # Caso 2: prova prima con context.args
        if context.args and len(context.args) >= 1:
            username_arg = context.args[0].lstrip("@")

        # Caso 3: fallback su entity del messaggio (mention e text_mention)
        # Gestisce i supergroup con topics dove context.args può essere vuoto
        if not username_arg and not target_user:
            for entity in (update.message.entities or []):
                if entity.type == "text_mention" and entity.user:
                    target_user = entity.user
                    break
                elif entity.type == "mention":
                    mention_text = update.message.text[entity.offset + 1:entity.offset + entity.length]
                    username_arg = mention_text
                    break

        # Caso 4: usa risolvi_target_da_username che gestisce tutti gli edge case
        if not target_user and username_arg:
            target_user = await risolvi_target_da_username(update, context, username_arg)

        if not target_user and not username_arg:
            await update.message.reply_text("Uso corretto: /infos @username oppure rispondi a un messaggio.")
            return

    # Ricerca nei dati
    user_id = getattr(target_user, 'id', None)
    dati = None

    if user_id is not None and user_id in dati_giocatori:
        dati = dati_giocatori[user_id]

    if not dati and username_arg:
        for uid, d in dati_giocatori.items():
            if d.get("username", "").lower() == username_arg.lower():
                user_id = uid
                dati = d
                break

    if not dati and username_arg:
        for uid, d in utenti_in_attesa.items():
            if d.get("username", "").lower() == username_arg.lower():
                user_id = uid
                dati = d
                break

    if not dati and username_arg:
        try:
            chat_target = await context.bot.get_chat(f"@{username_arg}")
            if chat_target and chat_target.id in dati_giocatori:
                user_id = chat_target.id
                dati = dati_giocatori[user_id]
        except Exception:
            pass

    if not dati:
        username_display = username_arg or getattr(target_user, 'username', None) or "utente"
        await update.message.reply_text(f"Utente @{username_display} non trovato nei dati.")
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
    family_status = "✅ Sì" if nel_benvenuto else "❌ No"
    messaggio = f"""👤 {nome} ({username_display})

{lang_line}
{paese_line}
📥 Nel gruppo Family: {family_status}

🔗 Profilo giocatore: {link}"""
    await update.message.reply_text(messaggio)
# ──────────────────────────────────────────────────────────────────────────────

async def risolvi_target_da_username(update: Update, context: ContextTypes.DEFAULT_TYPE, username_input: str):
    username_norm = (username_input or "").lstrip("@")
    if username_norm:
        for uid, dati in dati_giocatori.items():
            if str(dati.get("username", "")).lower() == username_norm.lower():
                return type('User', (object,), {
                    'id': uid,
                    'full_name': dati.get("nome", "Utente"),
                    'username': dati.get("username", ""),
                    'is_bot': False
                })
        for uid, dati in utenti_in_attesa.items():
            if str(dati.get("username", "")).lower() == username_norm.lower():
                return type('User', (object,), {
                    'id': uid,
                    'full_name': dati.get("nome", "Utente"),
                    'username': dati.get("username", ""),
                    'is_bot': False
                })
    for entity in update.message.entities or []:
        if entity.type == "text_mention" and entity.user:
            return entity.user
        if entity.type == "mention":
            mention_text = update.message.text[entity.offset + 1:entity.offset + entity.length]
            if not username_norm or mention_text.lower() == username_norm.lower():
                try:
                    chat_target = await context.bot.get_chat(f"@{mention_text}")
                    if chat_target:
                        return chat_target
                except Exception:
                    pass
    if username_norm:
        try:
            chat_target = await context.bot.get_chat(f"@{username_norm}")
            if chat_target:
                return chat_target
        except Exception:
            pass
    return None

async def warn_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    current_topic = update.message.message_thread_id
    is_correct_topic = (str(current_topic) == str(war_topic_id))
    if chat.id != war_group_id or not is_correct_topic:
        await update.message.reply_text("Questo comando è disponibile solo nel gruppo/argomento War.")
        return
    try:
        member = await context.bot.get_chat_member(chat.id, user.id)
        if member.status not in ['administrator', 'creator']:
            await update.message.reply_text("❌ Solo admin possono usare questo comando.")
            return
    except:
        await update.message.reply_text("Errore nel verificare i permessi.")
        return
    target_user = None
    if update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
    elif context.args:
        username_input = context.args[0].replace("@", "")
        target_user = await risolvi_target_da_username(update, context, username_input)
    if not target_user:
        await update.message.reply_text("⚠️ Rispondi a un utente o scrivi /warn @username")
        return
    try:
        is_bot_check = getattr(target_user, 'is_bot', False)
        if is_bot_check:
            await update.message.reply_text("🤖 Nota: Stai ammonendo un bot.")
        if str(target_user.id) == str(user.id):
            await update.message.reply_text("⚠️ Nota: Ti stai auto-ammonendo per test.")
        target_member = await context.bot.get_chat_member(chat.id, target_user.id)
        if target_member.status in ['administrator', 'creator']:
            await update.message.reply_text(f"👮‍♂️ Nota: Stai ammonendo un {target_member.status}.")
    except Exception:
        pass
    oggi = datetime.now()
    scadenza = oggi + timedelta(days=60)
    pulisci_warn_scaduti()
    try:
        warn_sheet.append_row([
            str(target_user.id),
            getattr(target_user, 'username', 'Nessuno') or getattr(target_user, 'full_name', 'Sconosciuto'),
            user.username or "Admin",
            oggi.strftime("%Y-%m-%d"),
            scadenza.strftime("%Y-%m-%d"),
            1
        ])
    except Exception as e:
        await update.message.reply_text("❌ Errore Google Sheets.")
        logger.error(f"GSheet error: {e}")
        return
    rows = warn_sheet.get_all_records()
    count = 0
    for row in rows:
        if str(row.get("user_id")) == str(target_user.id):
            count += 1
    t_name = getattr(target_user, 'full_name', 'Utente')
    t_user = getattr(target_user, 'username', 'nessuno')
    msg_text = f"🛡 <b>Utente Ammonito</b>\n\n👤 {t_name} (@{t_user})\n⚠️ Ammonizione: {count}° (scade tra 60gg)"
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➖", callback_data=f"warn_sub_{target_user.id}"),
            InlineKeyboardButton("➕", callback_data=f"warn_add_{target_user.id}")
        ],
        [InlineKeyboardButton("❌ Annulla", callback_data=f"warn_del_{target_user.id}")]
    ])
    await update.message.reply_text(msg_text, reply_markup=keyboard, parse_mode="HTML")

async def ammonisci_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    current_topic = update.message.message_thread_id
    is_correct_topic = (str(current_topic) == str(war_topic_id))
    if chat.id != war_group_id or not is_correct_topic:
        await update.message.reply_text("Questo comando è disponibile solo nel gruppo/argomento War.")
        return
    try:
        member = await context.bot.get_chat_member(chat.id, user.id)
        if member.status not in ['administrator', 'creator']:
            await update.message.reply_text("❌ Solo admin possono usare questo comando.")
            return
    except:
        await update.message.reply_text("Errore nel verificare i permessi.")
        return
    target_user = None
    ammonizioni_da_aggiungere = None
    if update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
        if context.args:
            try:
                ammonizioni_da_aggiungere = int(context.args[0])
            except ValueError:
                ammonizioni_da_aggiungere = None
    else:
        username_input = None
        if len(context.args) >= 2:
            username_input = context.args[0]
            try:
                ammonizioni_da_aggiungere = int(context.args[1])
            except ValueError:
                ammonizioni_da_aggiungere = None
        else:
            match = re.search(r"/ammonisci(?:@\w+)?\s+(@?\w+)\s+(\d+)", update.message.text or "", re.IGNORECASE)
            if match:
                username_input = match.group(1)
                try:
                    ammonizioni_da_aggiungere = int(match.group(2))
                except ValueError:
                    ammonizioni_da_aggiungere = None
        if username_input:
            target_user = await risolvi_target_da_username(update, context, username_input)
        elif update.message.entities:
            target_user = await risolvi_target_da_username(update, context, "")
    if not target_user or ammonizioni_da_aggiungere is None:
        await update.message.reply_text("⚠️ Usa /ammonisci @username 1-5 oppure rispondi al messaggio con /ammonisci 1-5.")
        return
    if ammonizioni_da_aggiungere < 1 or ammonizioni_da_aggiungere > 5:
        await update.message.reply_text("⚠️ Il numero di ammonizioni deve essere tra 1 e 5.")
        return
    oggi = datetime.now()
    scadenza = oggi + timedelta(days=60)
    pulisci_warn_scaduti()
    try:
        for _ in range(ammonizioni_da_aggiungere):
            warn_sheet.append_row([
                str(target_user.id),
                getattr(target_user, 'username', '') or getattr(target_user, 'full_name', 'Sconosciuto'),
                user.username or "Admin",
                oggi.strftime("%Y-%m-%d"),
                scadenza.strftime("%Y-%m-%d"),
                1
            ])
    except Exception as e:
        await update.message.reply_text("❌ Errore Google Sheets.")
        logger.error(f"GSheet error: {e}")
        return
    rows = warn_sheet.get_all_records()
    count = 0
    for row in rows:
        if str(row.get("user_id")) == str(target_user.id):
            count += 1
    t_name = getattr(target_user, 'full_name', 'Utente')
    t_user = getattr(target_user, 'username', 'nessuno')
    msg_text = (
        f"🛡 <b>Ammonizioni aggiunte</b>\n\n"
        f"👤 {t_name} (@{t_user})\n"
        f"➕ Aggiunte: {ammonizioni_da_aggiungere}\n"
        f"⚠️ Totale attive: {count}"
    )
    ban_message = ""
    if count >= 5:
        try:
            await context.bot.ban_chat_member(chat_id=chat.id, user_id=target_user.id)
            ban_message = "\n🚫 <b>Utente bannato</b> (raggiunte 5 ammonizioni)."
        except Exception as e:
            logger.error(f"Errore ban utente {target_user.id}: {e}")
            ban_message = "\n⚠️ Impossibile bannare l'utente."
    await update.message.reply_text(msg_text + ban_message, parse_mode="HTML")

async def gestione_warn_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    is_correct_topic = (str(query.message.message_thread_id) == str(war_topic_id))
    if query.message.chat.id != war_group_id or not is_correct_topic:
        return
    try:
        member = await context.bot.get_chat_member(query.message.chat.id, user.id)
        if member.status not in ['administrator', 'creator']:
            await query.answer("Non sei admin!", show_alert=True)
            return
    except:
        return
    data = query.data
    if data.startswith("warn_"):
        azione = data.split("_")[1]
        target_id = data.split("_")[2]
        target_name = "Utente"
        target_user_handle = "nessuno"
        try:
            if int(target_id) in dati_giocatori:
                target_name = dati_giocatori[int(target_id)].get("nome", "Utente")
                target_user_handle = dati_giocatori[int(target_id)].get("username", "")
            else:
                chat_member = await context.bot.get_chat_member(query.message.chat.id, target_id)
                target_name = chat_member.user.full_name
                target_user_handle = chat_member.user.username or "nessuno"
        except:
            pass
        pulisci_warn_scaduti()
        if azione == "del":
            rows = warn_sheet.get_all_values()
            riga_da_cancellare = None
            for i in range(len(rows) - 1, 0, -1):
                if str(rows[i][0]) == str(target_id):
                    riga_da_cancellare = i + 1
                    break
            if riga_da_cancellare:
                warn_sheet.delete_rows(riga_da_cancellare)
                await query.message.delete()
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=f"✅ Ammonizione rimossa da {user.first_name}.",
                    message_thread_id=query.message.message_thread_id
                )
            else:
                await query.edit_message_text("❌ Nessuna ammonizione attiva da annullare.")
            return
        elif azione == "add":
            oggi = datetime.now()
            scadenza = oggi + timedelta(days=60)
            warn_sheet.append_row([
                str(target_id),
                target_user_handle or target_name,
                user.username or "Admin",
                oggi.strftime("%Y-%m-%d"),
                scadenza.strftime("%Y-%m-%d"),
                1
            ])
        elif azione == "sub":
            rows = warn_sheet.get_all_values()
            riga_da_cancellare = None
            for i in range(len(rows) - 1, 0, -1):
                if str(rows[i][0]) == str(target_id):
                    riga_da_cancellare = i + 1
                    break
            if riga_da_cancellare:
                warn_sheet.delete_rows(riga_da_cancellare)
            else:
                await query.answer("Nessun warn da togliere!", show_alert=True)
                return
        rows = warn_sheet.get_all_records()
        count = 0
        for row in rows:
            if str(row.get("user_id")) == str(target_id):
                count += 1
        msg_text = f"🛡 <b>Utente Ammonito</b>\n\n👤 {target_name} (@{target_user_handle})\n⚠️ Ammonizione: {count}° (scade tra 60gg)"
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("➖", callback_data=f"warn_sub_{target_id}"),
                InlineKeyboardButton("➕", callback_data=f"warn_add_{target_id}")
            ],
            [InlineKeyboardButton("❌ Annulla", callback_data=f"warn_del_{target_id}")]
        ])
        try:
            await query.edit_message_text(text=msg_text, reply_markup=keyboard, parse_mode="HTML")
        except BadRequest:
            pass

async def elenco_warn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    current_topic = update.message.message_thread_id
    is_correct_topic = (str(current_topic) == str(war_topic_id))
    if update.effective_chat.id != war_group_id or not is_correct_topic:
        await update.message.reply_text("Questo comando è disponibile solo nel gruppo/argomento War.")
        return
    try:
        member = await context.bot.get_chat_member(update.effective_chat.id, update.effective_user.id)
        if member.status not in ['administrator', 'creator']:
            await update.message.reply_text("❌ Solo admin possono usare questo comando.")
            return
    except:
        await update.message.reply_text("Errore nel verificare i permessi.")
        return
    pulisci_warn_scaduti()
    rows = warn_sheet.get_all_records()
    if not rows:
        await update.message.reply_text("✅ Nessun utente ammonito al momento.")
        return
    oggi = datetime.now()
    utenti_warn = {}
    for row in rows:
        uid = str(row.get("user_id"))
        uname = row.get("username")
        data_warn_str = row.get("data_warn")
        try:
            data_warn = datetime.strptime(data_warn_str, "%Y-%m-%d")
            if uid not in utenti_warn:
                utenti_warn[uid] = {"name": uname, "tot": 0, "recent": 0}
            utenti_warn[uid]["tot"] += 1
            delta = oggi - data_warn
            if delta.days <= 30:
                utenti_warn[uid]["recent"] += 1
        except:
            continue
    msg = "🛡 <b>ELENCO AMMONITI</b> (Durata: 60gg)\n\n"
    msg += "📅 <b>Ultimi 30 giorni:</b>\n"
    found_recent = False
    for uid, dati in utenti_warn.items():
        if dati["recent"] > 0:
            msg += f"[{dati['recent']}] @{dati['name']}\n"
            found_recent = True
    if not found_recent:
        msg += "<i>Nessuno</i>\n"
    msg += "\n🗂 <b>Totale attivi:</b>\n"
    for uid, dati in utenti_warn.items():
        msg += f"[{dati['tot']}] @{dati['name']}\n"
    await update.message.reply_text(msg, parse_mode="HTML")

async def myammonizioni_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target_user = None
    if update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
    elif context.args:
        username_input = context.args[0].replace("@", "")
        for uid, dati in dati_giocatori.items():
            if str(dati.get("username", "")).lower() == username_input.lower():
                target_user = type('User', (object,), {
                    'id': uid,
                    'full_name': dati.get("nome", "Utente"),
                    'username': dati.get("username", ""),
                    'is_bot': False
                })
                break
        if not target_user:
            try:
                chat_target = await context.bot.get_chat(f"@{username_input}")
                if chat_target:
                    target_user = chat_target
            except Exception:
                target_user = None
    else:
        target_user = update.effective_user
    if not target_user:
        await update.message.reply_text("⚠️ Usa /myammonizioni @username oppure rispondi a un messaggio.")
        return
    pulisci_warn_scaduti()
    rows = warn_sheet.get_all_records()
    warn_list = []
    for row in rows:
        if str(row.get("user_id")) == str(target_user.id):
            scadenza = row.get("data_scadenza")
            data_warn = row.get("data_warn")
            warn_list.append((data_warn, scadenza))
    if not warn_list:
        await update.message.reply_text("✅ Nessuna ammonizione attiva per questo utente.")
        return
    warn_list_sorted = sorted(warn_list, key=lambda x: x[1])
    t_name = getattr(target_user, 'full_name', 'Utente')
    t_user = getattr(target_user, 'username', 'nessuno')
    msg = f"🛡 <b>Ammonizioni attive</b>\n\n👤 {t_name} (@{t_user})\n"
    for i, (_, scadenza) in enumerate(warn_list_sorted, start=1):
        msg += f"• Ammonizione {i}: scade il {scadenza}\n"
    await update.message.reply_text(msg, parse_mode="HTML")

async def resoconto_ammonizioni_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        member = await context.bot.get_chat_member(update.effective_chat.id, update.effective_user.id)
        if member.status not in ['administrator', 'creator']:
            await update.message.reply_text("❌ Solo admin possono usare questo comando.")
            return
    except:
        await update.message.reply_text("Errore nel verificare i permessi.")
        return
    pulisci_warn_scaduti()
    rows = warn_sheet.get_all_records()
    if not rows:
        await update.message.reply_text("✅ Nessuna ammonizione attiva al momento.")
        return
    utenti_warn = {}
    for row in rows:
        uid = str(row.get("user_id"))
        uname = row.get("username") or uid
        if uid not in utenti_warn:
            utenti_warn[uid] = {"name": uname, "tot": 0}
        utenti_warn[uid]["tot"] += 1
    msg = "🛡 <b>RESOCONTO AMMONIZIONI (attive)</b>\n\n"
    for uid, dati in utenti_warn.items():
        msg += f"[{dati['tot']}] @{dati['name']}\n"
    await update.message.reply_text(msg, parse_mode="HTML")

async def ammonizioni_mese_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pulisci_warn_scaduti()
    rows = warn_sheet.get_all_records()
    if not rows:
        await update.message.reply_text("✅ Nessuna ammonizione attiva al momento.")
        return
    oggi = datetime.now()
    utenti_warn = {}
    for row in rows:
        data_warn_str = row.get("data_warn")
        try:
            data_warn = datetime.strptime(data_warn_str, "%Y-%m-%d")
        except Exception:
            continue
        if data_warn.year == oggi.year and data_warn.month == oggi.month:
            uid = str(row.get("user_id"))
            uname = row.get("username") or uid
            if uid not in utenti_warn:
                utenti_warn[uid] = {"name": uname, "tot": 0}
            utenti_warn[uid]["tot"] += 1
    if not utenti_warn:
        await update.message.reply_text("✅ Nessuna ammonizione registrata nel mese corrente.")
        return
    msg = "🛡 <b>AMMONIZIONI DEL MESE CORRENTE</b>\n\n"
    for uid, dati in utenti_warn.items():
        msg += f"[{dati['tot']}] @{dati['name']}\n"
    await update.message.reply_text(msg, parse_mode="HTML")

async def armata_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("https://royaleapi.com/clan/P2UQP9CJ")

async def approdo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("https://royaleapi.com/clan/GURVCVCU")

async def tori_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("https://royaleapi.com/clan/YC89P002")

async def dog_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("https://royaleapi.com/clan/RP889JU")

async def baby_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("https://royaleapi.com/clan/QCQPJ90R")

async def brigata_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("https://royaleapi.com/clan/Q8G2QR2P")

async def clan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    messaggio = (
        "🪖 *Family Armata Rozza*\n\n"
        "• [Armata Rozza](https://royaleapi.com/clan/P2UQP9CJ)\n"
        "• [I Tori Feroci](https://royaleapi.com/clan/YC89P002)\n"
        "• [Dog Rider](https://royaleapi.com/clan/RP889JU)\n"
        "• [BabyRozza](https://royaleapi.com/clan/QCQPJ90R)\n"
        "• [BRIGATA ROZZA™️](https://royaleapi.com/clan/Q8G2QR2P)\n"
        "• [Approdo Rozzo™️](https://royaleapi.com/clan/GURVCVCU)\n"
    )
    await update.message.reply_text(messaggio, parse_mode="Markdown")

import random

async def bacgay_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    frasi = [
        "@BACWasTaken ti manca così tanto il cervello che potresti galleggiare sull’acqua.",
        "@BACWasTaken saresti perfetto come testimonial dei preservativi: faresti impennare le vendite.",
        "@BACWasTaken sei utile quanto il pastello bianco.",
        "@BACWasTaken stamattina ti sei specchiato in una pozzanghera di fango?",
        "@BACWasTaken avevi l’ombrello quando distribuivano la bellezza?",
        "@BACWasTaken spiegarti qualcosa è come insegnare il calcolo a un lemure.",
        "@BACWasTaken se corressi quanto parli, avresti già un oro olimpico.",
        "@BACWasTaken sei tagliente come una biglia.",
        "@BACWasTaken c’è della merda sui vestiti... ah no, sei solo tu.",
        "@BACWasTaken sei utile come un preservativo bucato.",
        "@BACWasTaken sembri avere più crateri della luna.",
        "@BACWasTaken sai la differenza tra te e le uova? Le uova vengono deposte.",
        "@BACWasTaken perché fai il difficile se sei difficile da volere?",
        "@BACWasTaken ti chiamerei fighetta, ma ti manca profondità.",
        "@BACWasTaken spero che tu incontri qualcuno bello, intelligente e simpatico... l’opposto tuo.",
        "@BACWasTaken dovresti portarti dietro una pianta per rimpiazzare l’ossigeno che sprechi.",
        "@BACWasTaken smettila di usare la testa solo per tenere fermi i denti.",
        "@BACWasTaken sei la prova vivente che anche i brutti scopano.",
        "@BACWasTaken sembri uno che non saprebbe fare lo spelling di DNA.",
        "@BACWasTaken alcuni bevono dalla fontana della conoscenza, tu ci hai fatto i gargarismi.",
        "@BACWasTaken usi la testa solo per tagliarti i capelli?",
        "@BACWasTaken se mangiassi spazzatura, sarebbe cannibalismo.",
        "@BACWasTaken tutti hanno bisogno d’amore, tu invece paghi per averlo.",
        "@BACWasTaken sembri un castello di sabbia già calpestato.",
        "@BACWasTaken vedo che oggi hai ritagliato del tempo per umiliarti in pubblico.",
        "@BACWasTaken sembri uno gnomo da giardino mal riuscito.",
        "@BACWasTaken sei uno strumento completo, ma nemmeno utile.",
        "@BACWasTaken come sono parenti i tuoi genitori?",
        "@BACWasTaken se fossi la luce alla fine del tunnel, tornerei indietro.",
        "@BACWasTaken se ti lancio un bastone, te ne vai?",
        "@BACWasTaken che contraccezione usi? La faccia?",
        "@BACWasTaken ti darei un +1, così forse trovi un amico.",
        "@BACWasTaken scommetto che i tuoi genitori cambiano discorso quando chiedono di te.",
        "@BACWasTaken direi che sei stupido come una roccia, ma almeno una roccia tiene aperta una porta.",
        "@BACWasTaken fai una lunga passeggiata su un pontile corto.",
        "@BACWasTaken sembri creato premendo 'casuale' nella schermata personaggio.",
        "@BACWasTaken se l’ignoranza è beatitudine, devi essere felicissimo.",
        "@BACWasTaken sei così indietro che pensi di essere avanti.",
        "@BACWasTaken quando piovevano cervelli avevi l’ombrello.",
        "@BACWasTaken potresti nascondere le uova di Pasqua e dimenticare dove.",
        "@BACWasTaken se avessi un altro cervello, ti sentiresti solo.",
        "@BACWasTaken continua a roteare gli occhi, magari trovi un cervello dietro.",
        "@BACWasTaken sembri uno che mangia i tasti del telecomando.",
        "@BACWasTaken hai il carisma di una multa sul parabrezza.",
        "@BACWasTaken sei il motivo per cui esiste il tasto ignora.",
        "@BACWasTaken hai il talento raro di sbagliare anche copiando.",
        "@BACWasTaken sei così inutile che in una rissa faresti da arbitro.",
        "@BACWasTaken hai meno spessore di un foglio bagnato.",
        "@BACWasTaken sei il classico che cade e dà la colpa al pavimento.",
        "@BACWasTaken se fossi una carta Clash Royale, costeresti 10 elisir e non faresti nulla."
    ]

    await update.message.reply_text(random.choice(frasi))

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Exception while handling an update: {context.error}", exc_info=True)

app = ApplicationBuilder().token(TOKEN).build()

# Handler ingressi/uscite gruppo War (log privato)
app.add_handler(ChatMemberHandler(log_war_member_change, chat_member_types=ChatMemberHandler.ANY_CHAT_MEMBER))
app.add_handler(MessageHandler(
    (filters.StatusUpdate.NEW_CHAT_MEMBERS | filters.StatusUpdate.LEFT_CHAT_MEMBER)
    & filters.Chat(war_group_id),
    log_war_member_change
))

app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS & filters.Chat(benvenuto_group_id), benvenuto_secondo_gruppo))
app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS & filters.Chat(reclutamento_group_id), nuovo_utente))
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("updatetag", updatetag))
app.add_handler(CommandHandler("infos", infos))
app.add_handler(CommandHandler("warn", warn_command))
app.add_handler(CommandHandler("elenco", elenco_warn))
app.add_handler(CommandHandler("ammonisci", ammonisci_command))
app.add_handler(CommandHandler("myammonizioni", myammonizioni_command))
app.add_handler(CommandHandler("resocontoammonizioni", resoconto_ammonizioni_command))
app.add_handler(CommandHandler("ammonizionimese", ammonizioni_mese_command))
app.add_handler(CallbackQueryHandler(gestione_warn_callback, pattern="^warn_"))
app.add_handler(CommandHandler("armata", armata_command))
app.add_handler(CommandHandler("approdo", approdo_command))
app.add_handler(CommandHandler("tori", tori_command))
app.add_handler(CommandHandler("dog", dog_command))
app.add_handler(CommandHandler("baby", baby_command))
app.add_handler(CommandHandler("brigata", brigata_command))
app.add_handler(CommandHandler("clan", clan_command))
app.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.TEXT & (~filters.COMMAND), ricevi_tag_privato))
app.add_handler(MessageHandler(filters.Chat(reclutamento_group_id) & filters.TEXT & (~filters.COMMAND), monitora_username))
app.add_error_handler(error_handler)
app.add_handler(CommandHandler("bacgay", bacgay_command))

logger.info("✅ Bot in esecuzione con polling...")
app.run_polling(allowed_updates=["message", "chat_member", "callback_query"])