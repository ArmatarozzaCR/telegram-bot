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
from datetime import datetime
import logging
import time

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
        logger.info("🔄 Inizio caricamento Google Sheet...")
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
        logger.info(f"✅ Caricati {len(dati_giocatori)} giocatori da Google Sheet.")
    except Exception as e:
        logger.error(f"❌ Errore caricamento Google Sheet: {e}")


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
            sheet.update(f"A{riga_da_aggiornare}:G{riga_da_aggiornare}", [valori])
        else:
            sheet.append_row(valori)
        logger.info(f"Dati salvati su Google Sheet per user_id={user_id}")
    except Exception as e:
        logger.error(f"Errore salvataggio Google Sheet per user_id={user_id}: {e}")

def get_league_name(trophies):
    if trophies >= 5000:
        return "Lega Leggendaria 3"
    elif trophies >= 4000:
        return "Lega Leggendaria 2"
    elif trophies >= 3000:
        return "Lega Leggendaria 1"
    elif trophies >= 1500:
        return "Lega Oro"
    elif trophies >= 600:
        return "Lega Argento"
    else:
        return "Lega Bronzo"

def get_league_short(trophies):
    if trophies >= 5000:
        return "Leg 3"
    elif trophies >= 4000:
        return "Leg 2"
    elif trophies >= 3000:
        return "Leg 1"
    elif trophies >= 1500:
        return "Oro"
    elif trophies >= 600:
        return "Argento"
    else:
        return "Bronzo"

async def scrape_war_stats(tag):
    import aiohttp
    from bs4 import BeautifulSoup
    import asyncio
    url = f"https://royaleapi.com/player/{tag}/riverrace"
    
    try:
        async with aiohttp.ClientSession() as session:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            async with session.get(url, timeout=20, headers=headers) as response:
                if response.status != 200:
                    logger.error(f"HTTP {response.status} per tag {tag}")
                    return None
                
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                
                player_url = f"https://royaleapi.com/player/{tag}"
                clan_name = "Sconosciuto"
                clan_tag = None
                
                wars = []
                
                war_items = soup.find_all('div', class_='item')[:10]
                
                for war_item in war_items:
                    war_info = {}
                    
                    date_div = war_item.find('div', class_='date')
                    war_info['date'] = date_div.get_text(strip=True) if date_div else "N/A"
                    
                    position_div = war_item.find('div', class_='position')
                    if position_div:
                        pos_text = position_div.get_text(strip=True).replace('°', '').replace('st', '').replace('nd', '').replace('rd', '').replace('th', '').strip()
                        war_info['position'] = pos_text
                    else:
                        war_info['position'] = "N/A"
                    
                    clan_div = war_item.find('div', class_='clan_name')
                    if clan_div:
                        war_info['clan_name'] = clan_div.get_text(strip=True)
                        clan_link = clan_div.find('a')
                        if clan_link and clan_link.get('href'):
                            href = clan_link.get('href')
                            if '/clan/' in href:
                                war_info['clan_tag'] = href.split('/clan/')[-1].split('/')[0]
                            else:
                                war_info['clan_tag'] = None
                        else:
                            war_info['clan_tag'] = None
                    else:
                        war_info['clan_name'] = "Sconosciuto"
                        war_info['clan_tag'] = None
                    
                    trophies_div = war_item.find('div', class_='clan_score')
                    if trophies_div:
                        trophy_text = trophies_div.get_text(strip=True).replace(',', '').replace('.', '')
                        try:
                            war_info['clan_trophies'] = int(trophy_text)
                        except:
                            war_info['clan_trophies'] = 0
                    else:
                        war_info['clan_trophies'] = 0
                    
                    decks_div = war_item.find('div', class_='decks_used')
                    if decks_div:
                        decks_text = decks_div.get_text(strip=True)
                        try:
                            used = int(decks_text.split('/')[0])
                            war_info['decks_used'] = used
                        except:
                            war_info['decks_used'] = 0
                    else:
                        war_info['decks_used'] = 0
                    
                    fame_div = war_item.find('div', class_='fame')
                    if fame_div:
                        fame_text = fame_div.get_text(strip=True).replace(',', '').replace('.', '')
                        try:
                            war_info['medals'] = int(fame_text)
                        except:
                            war_info['medals'] = 0
                    else:
                        war_info['medals'] = 0
                    
                    boat_div = war_item.find('div', class_='boat_attacks')
                    if boat_div:
                        boat_text = boat_div.get_text(strip=True)
                        try:
                            war_info['boat_attacks'] = int(boat_text)
                        except:
                            war_info['boat_attacks'] = 0
                    else:
                        war_info['boat_attacks'] = 0
                    
                    if war_info['decks_used'] > 0:
                        war_info['avg_medals'] = round(war_info['medals'] / war_info['decks_used'])
                    else:
                        war_info['avg_medals'] = 0
                    
                    wars.append(war_info)
                
                return {
                    'player_url': player_url,
                    'wars': wars
                }
    
    except asyncio.TimeoutError:
        logger.error(f"Timeout scraping war stats per tag {tag}")
        return None
    except Exception as e:
        logger.error(f"Errore scraping war stats per tag {tag}: {e}")
        return None

def format_war_message(nome, username, war_data):
    player_url = war_data['player_url']
    wars = war_data['wars']
    
    username_display = f"@{username}" if username else ""
    
    if not wars:
        return f"""⚔️ WAR STATS - {nome} {username_display}
🔗 {player_url}

━━━━━━━━━━━━━━━━━━━━━━━
📊 ULTIME 10 WAR

❌ Nessuna partecipazione alle River Race registrata."""
    
    message = f"""⚔️ WAR STATS - {nome} {username_display}
🔗 {player_url}

━━━━━━━━━━━━━━━━━━━━━━━
📊 ULTIME 10 WAR

"""
    
    position_icons = {'1': '🥇', '2': '🥈', '3': '🥉'}
    
    total_decks = 0
    total_medals = 0
    total_boats = 0
    
    for idx, war in enumerate(wars, 1):
        pos = war['position']
        icon = position_icons.get(pos, '🏅')
        
        clan_link = f"https://royaleapi.com/clan/{war['clan_tag']}" if war['clan_tag'] else ""
        league = get_league_name(war['clan_trophies'])
        
        total_decks += war['decks_used']
        total_medals += war['medals']
        total_boats += war['boat_attacks']
        
        message += f"""{icon} War #{idx} - {war['date']}
🏰 Clan: {war['clan_name']}
🔗 {clan_link}
├ 🏆 Lega Clan: {league}
├ ⚔️ Deck Usati: {war['decks_used']} su 16
├ 🏅 Medaglie: {war['medals']:,}
├ 🚢 Attacchi Navali: {war['boat_attacks']}
└ 🎯 Media: {war['avg_medals']}

"""
    
    num_wars = len(wars)
    avg_medals_global = round(total_medals / total_decks) if total_decks > 0 else 0
    
    message += f"""━━━━━━━━━━━━━━━━━━━━━━━
📈 STATISTICHE TOTALI ({num_wars} War)

⚔️ Deck Usati: {total_decks}/160
🏅 🎯 Media: {avg_medals_global}
🚢 Attacchi Navali Totali: {total_boats}"""
    
    return message

def format_fastwar_message(nome, username, war_data):
    player_url = war_data['player_url']
    wars = war_data['wars']
    
    username_display = f"@{username}" if username else ""
    
    if not wars:
        return f"""⚔️ {nome} {username_display}
🔗 {player_url}

📊 MEDIE PER LEGA

❌ Nessuna partecipazione registrata."""
    
    message = f"""⚔️ {nome} {username_display}
🔗 {player_url}

📊 MEDIE PER LEGA

"""
    
    league_stats = {}
    
    for war in wars:
        league = get_league_name(war['clan_trophies'])
        
        if league not in league_stats:
            league_stats[league] = {
                'count': 0,
                'total_decks': 0,
                'total_medals': 0,
                'total_boats': 0,
                'total_avg': 0
            }
        
        league_stats[league]['count'] += 1
        league_stats[league]['total_decks'] += war['decks_used']
        league_stats[league]['total_medals'] += war['medals']
        league_stats[league]['total_boats'] += war['boat_attacks']
        league_stats[league]['total_avg'] += war['avg_medals']
    
    league_order = [
        "Lega Leggendaria 3",
        "Lega Leggendaria 2",
        "Lega Leggendaria 1",
        "Lega Oro",
        "Lega Argento",
        "Lega Bronzo"
    ]
    
    icons = {
        "Lega Leggendaria 3": "🏆",
        "Lega Leggendaria 2": "🥇",
        "Lega Leggendaria 1": "🥈",
        "Lega Oro": "🥉"
    }
    
    league_keys = [l for l in league_order if l in league_stats]
    
    for i, league in enumerate(league_keys):
        stats = league_stats[league]
        count = stats['count']
        avg_decks = round(stats['total_decks'] / count, 1)
        avg_medals = round(stats['total_medals'] / count)
        avg_boats = round(stats['total_boats'] / count, 1)
        avg_avg = round(stats['total_avg'] / count)
        
        icon = icons.get(league, "📊")
        connector = "└" if i == len(league_keys) - 1 else "├"
        
        message += f"""{icon} {league} ({count} war)
{connector} ⚔️ Deck: {avg_decks}/16 | 🏅 {avg_medals:,} | 🚢 {avg_boats} | ⭐ {avg_avg}

"""
    
    return message.rstrip()

async def war_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or len(context.args) != 1:
        await update.message.reply_text("Uso corretto: /war @username oppure /war #TAG")
        return
    
    arg = context.args[0]
    tag = None
    nome = None
    username = None
    
    if arg.startswith("#"):
        tag = arg[1:].upper()
        nome = "Giocatore"
        username = None
    elif arg.startswith("@"):
        username_arg = arg[1:]
        user_id = None
        for uid, dati in dati_giocatori.items():
            if dati.get("username", "").lower() == username_arg.lower():
                user_id = uid
                break
        if user_id:
            tag = dati_giocatori[user_id].get("tag")
            nome = dati_giocatori[user_id].get("nome", "Giocatore")
            username = dati_giocatori[user_id].get("username")
        else:
            await update.message.reply_text(f"❌ Utente @{username_arg} non trovato nel database.")
            return
    else:
        await update.message.reply_text("Uso corretto: /war @username oppure /war #TAG")
        return
    
    if not tag:
        await update.message.reply_text("❌ Tag non trovato per questo utente.")
        return
    
    await update.message.reply_text("⏳ Recupero dati da RoyaleAPI...")
    
    try:
        war_data = await scrape_war_stats(tag)
        
        if not war_data or not war_data.get('wars'):
            await update.message.reply_text(f"⚠️ Impossibile recuperare i dati da RoyaleAPI.\n🔗 https://royaleapi.com/player/{tag}")
            return
        
        message = format_war_message(nome, username, war_data)
        await update.message.reply_text(message, disable_web_page_preview=True)
        
    except Exception as e:
        logger.error(f"Errore comando /war per tag {tag}: {e}")
        await update.message.reply_text(f"⚠️ Errore durante il recupero dei dati.\n🔗 https://royaleapi.com/player/{tag}")

async def fastwar_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or len(context.args) != 1:
        await update.message.reply_text("Uso corretto: /fastwar @username oppure /fastwar #TAG")
        return
    
    arg = context.args[0]
    tag = None
    nome = None
    username = None
    
    if arg.startswith("#"):
        tag = arg[1:].upper()
        nome = "Giocatore"
        username = None
    elif arg.startswith("@"):
        username_arg = arg[1:]
        user_id = None
        for uid, dati in dati_giocatori.items():
            if dati.get("username", "").lower() == username_arg.lower():
                user_id = uid
                break
        if user_id:
            tag = dati_giocatori[user_id].get("tag")
            nome = dati_giocatori[user_id].get("nome", "Giocatore")
            username = dati_giocatori[user_id].get("username")
        else:
            await update.message.reply_text(f"❌ Utente @{username_arg} non trovato nel database.")
            return
    else:
        await update.message.reply_text("Uso corretto: /fastwar @username oppure /fastwar #TAG")
        return
    
    if not tag:
        await update.message.reply_text("❌ Tag non trovato per questo utente.")
        return
    
    await update.message.reply_text("⏳ Recupero dati da RoyaleAPI...")
    
    try:
        war_data = await scrape_war_stats(tag)
        
        if not war_data or not war_data.get('wars'):
            await update.message.reply_text(f"⚠️ Impossibile recuperare i dati da RoyaleAPI.\n🔗 https://royaleapi.com/player/{tag}")
            return
        
        message = format_fastwar_message(nome, username, war_data)
        await update.message.reply_text(message, disable_web_page_preview=True)
        
    except Exception as e:
        logger.error(f"Errore comando /fastwar per tag {tag}: {e}")
        await update.message.reply_text(f"⚠️ Errore durante il recupero dei dati.\n🔗 https://royaleapi.com/player/{tag}")

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
            logger.info(f"Utente {user_id} bloccato nel gruppo reclutamento")
        except Exception as e:
            logger.error(f"Errore restrict_chat_member per nuovo utente {user_id}: {e}")
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

    if "prev_tag" in dati and dati["prev_tag"] != tag:
        messaggio += f"\n\n⚠️ Attenzione: il tag in game è stato aggiornato da #{dati['prev_tag']} a #{tag}."

    dati["prev_tag"] = tag

    try:
        msg = await context.bot.send_message(chat_id=group_id, text=messaggio)
        dati["last_message_id"] = msg.message_id
        logger.info(f"Resoconto inviato per user_id={user_id}")
        if not username:
            if paese == "Italia":
                avviso = f"⚠️ {nome}, inserisci un username Telegram per facilitare il tuo reclutamento."
            else:
                avviso = f"⚠️ {nome}, please set a Telegram username to make your recruitment easier."
            await context.bot.send_message(chat_id=group_id, text=avviso, reply_to_message_id=msg.message_id)
        salva_su_google_sheet(user_id)
    except Exception as e:
        logger.error(f"Errore invio resoconto per user_id={user_id}: {e}")

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
            logger.warning(f"Impossibile eliminare messaggio gestione {old_msg_id}: {e}")
    try:
        msg = await context.bot.send_message(
            chat_id=gestione_group_id,
            text=messaggio,
            message_thread_id=gestione_topic_id
        )
        dati["gestione_message_id"] = msg.message_id
        logger.info(f"Resoconto gestione inviato per user_id={user_id}")
        salva_su_google_sheet(user_id)
    except Exception as e:
        logger.error(f"Errore invio resoconto gestione per user_id={user_id}: {e}")

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
            await context.bot.restrict_chat_member(
                chat_id=reclutamento_group_id,
                user_id=user_id,
                permissions=permessi_sbloccati
            )
            logger.info(f"Utente {user_id} sbloccato nel gruppo reclutamento")
        except Exception as e:
            logger.error(f"Errore durante ricezione tag privato per user_id={user_id}: {e}")
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
            msg_id = dati_giocatori[user.id].get("last_message_id")
            if msg_id:
                try:
                    await context.bot.delete_message(chat_id=reclutamento_group_id, message_id=msg_id)
                except Exception as e:
                    logger.warning(f"Impossibile eliminare messaggio {msg_id}: {e}")
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
    if not re.match(r"^#?[A-Z0-9]+$", tag_arg):
        await update.message.reply_text("Tag non valido. Deve iniziare con # e contenere solo lettere/numeri.")
        return
    tag_arg = tag_arg.lstrip("#")
    user_id = None
    for uid, dati in dati_giocatori.items():
        if dati.get("username", "").lower() == username_arg.lower():
            user_id = uid
            break
    if user_id is not None:
        dati_giocatori[user_id]["tag"] = tag_arg
        try:
            salva_su_google_sheet(user_id)
            await invia_resoconto(user_id, context)
            await invia_resoconto_gestione(user_id, context)
            await update.message.reply_text(f"✅ Tag aggiornato per @{username_arg} a #{tag_arg} e resoconti rigenerati.")
        except Exception as e:
            logger.error(f"Errore updatetag per user_id={user_id}: {e}")
            await update.message.reply_text(f"⚠️ Tag salvato su database, ma errore nell'invio resoconti.")
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
                "nel_benvenuto": False
            }
            del utenti_in_attesa[user_id]
            try:
                salva_su_google_sheet(user_id)
                await invia_resoconto(user_id, context)
                await invia_resoconto_gestione(user_id, context)
                await update.message.reply_text(f"✅ Tag aggiornato per @{username_arg} a #{tag_arg} e resoconti rigenerati.")
            except Exception as e:
                logger.error(f"Errore updatetag per user_id={user_id}: {e}")
                await update.message.reply_text(f"⚠️ Tag salvato su database, ma errore nell'invio resoconti.")
            return
    fake_user_id = -int(time.time())
    dati_giocatori[fake_user_id] = {
        "nome": username_arg,
        "username": username_arg,
        "tag": tag_arg,
        "user_lang": None,
        "last_message_id": None,
        "gestione_message_id": None,
        "nel_benvenuto": False
    }
    try:
        salva_su_google_sheet(fake_user_id)
        await invia_resoconto(fake_user_id, context)
        await invia_resoconto_gestione(fake_user_id, context)
        await update.message.reply_text(f"✅ Nuovo profilo creato per @{username_arg} con tag #{tag_arg} e resoconti rigenerati.")
    except Exception as e:
        logger.error(f"Errore updatetag per nuovo utente: {e}")
        await update.message.reply_text(f"⚠️ Profilo salvato su database, ma errore nell'invio resoconti.")

async def info(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    except Exception as e:
        logger.error(f"Errore verifica permessi info: {e}")
        await update.message.reply_text("Errore nel verificare i permessi.")
        return
    if not context.args or len(context.args) != 1:
        await update.message.reply_text("Uso corretto: /info @username")
        return
    username_arg = context.args[0]
    if username_arg.startswith("@"):
        username_arg = username_arg[1:]
    user_id = None
    dati = None
    for uid, d in dati_giocatori.items():
        if d.get("username", "").lower() == username_arg.lower():
            user_id = uid
            dati = d
            break
    if not dati:
        for uid, d in utenti_in_attesa.items():
            if d.get("username", "").lower() == username_arg.lower():
                user_id = uid
                dati = d
                break
    if not dati:
        await update.message.reply_text(f"Utente @{username_arg} non trovato nei dati.")
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

async def armata_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("https://royaleapi.com/clan/P2UQP9CJ")

async def magnamm_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("https://royaleapi.com/clan/L08VGUJ9")

async def tori_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("https://royaleapi.com/clan/YC89P002")

async def dog_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("https://royaleapi.com/clan/RP889JU")

async def baby_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("https://royaleapi.com/clan/QCQPJ90R")

async def minibomba_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("https://royaleapi.com/clan/PJG0R00")

async def clan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    messaggio = (
        "🪖 *Family Armata Rozza*\n\n"
        "• [Armata Rozza](https://royaleapi.com/clan/P2UQP9CJ)\n"
        "• [Ce Magnamm](https://royaleapi.com/clan/L08VGUJ9)\n"
        "• [I Tori Feroci](https://royaleapi.com/clan/YC89P002)\n"
        "• [Dog Rider](https://royaleapi.com/clan/RP889JU)\n"
        "• [BabyRozza](https://royaleapi.com/clan/QCQPJ90R)\n"
        "• [Mini Bombarolo](https://royaleapi.com/clan/PJG0R00)\n"
    )
    await update.message.reply_text(messaggio, parse_mode="Markdown")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Exception while handling an update: {context.error}", exc_info=True)

import threading

def carica_sheets_background():
    import time
    time.sleep(1)
    carica_da_google_sheet()

thread = threading.Thread(target=carica_sheets_background, daemon=True)
thread.start()
logger.info("⚡ Bot si avvia mentre Google Sheets carica in background...")

app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS & filters.Chat(benvenuto_group_id), benvenuto_secondo_gruppo))
app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS & filters.Chat(reclutamento_group_id), nuovo_utente))
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("updatetag", updatetag, filters.Chat(reclutamento_group_id)))
app.add_handler(CommandHandler("info", info, filters.Chat(reclutamento_group_id)))
app.add_handler(CommandHandler("war", war_command))
app.add_handler(CommandHandler("fastwar", fastwar_command))
app.add_handler(CommandHandler("armata", armata_command))
app.add_handler(CommandHandler("magnamm", magnamm_command))
app.add_handler(CommandHandler("tori", tori_command))
app.add_handler(CommandHandler("dog", dog_command))
app.add_handler(CommandHandler("baby", baby_command))
app.add_handler(CommandHandler("minibomba", minibomba_command))
app.add_handler(CommandHandler("clan", clan_command))
app.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.TEXT & (~filters.COMMAND), ricevi_tag_privato))
app.add_handler(MessageHandler(filters.Chat(reclutamento_group_id) & filters.TEXT & (~filters.COMMAND), monitora_username))
app.add_error_handler(error_handler)

logger.info("✅ Bot in esecuzione con polling...")
app.run_polling()