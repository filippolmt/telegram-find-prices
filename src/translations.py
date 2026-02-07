"""
Internationalization: message translations and language helpers.
"""

SUPPORTED_LANGUAGES = {"en", "it"}
DEFAULT_LANGUAGE = "en"

MESSAGES = {
    "en": {
        # Auth / generic
        "not_authorized": "You are not authorized to use this bot.",
        "start_first": "Please start the bot first with /start in a private chat.",
        "operation_cancelled": "Operation cancelled.",
        "timed_out": "Timed out. Try again with {command}.",
        "invalid_choice": "Invalid choice. Try again with {command}.",
        "number_out_of_range": "Number out of range. Try again with {command}.",

        # /start
        "welcome": "Hi {username}, welcome! Use /add_channel to add a channel to monitor.",

        # /add_channel
        "add_channel_prompt": "Send the channel username or an invite link (t.me/+...). Type /cancel to abort.",
        "invalid_invite_link": "Invalid invite link.",
        "invalid_channel_id": "Invalid channel identifier. Use only letters, numbers and underscores (e.g. deals_tech).",
        "scanning_messages": "Scanning existing messages...",
        "backfill_matches": "Backfill complete: {count} matches found!",
        "backfill_no_matches": "Backfill complete: no matches found.",

        # /list_channels
        "no_channels": "You have no channels added.",
        "your_channels": "Your channels:\n{channels}",

        # /watch
        "watch_ask_product": "What product do you want to monitor? (type /cancel to abort)",
        "watch_ask_price": "At what price do you want to be notified?\nEnter a price (e.g. 799) or /skip to be notified at any price.",
        "watch_invalid_price": "Invalid price. Try again with /watch.",
        "watch_ask_category": "Category? (e.g. electronics, clothing, home)\nType /skip to skip.",
        "watch_already_monitoring": "You are already monitoring '{product}'.",
        "watch_suggest_price": "From history, the lowest price found for '{product}' is {price:.2f}.\nDo you want to use {price:.2f} as target price?\nReply 'yes' to accept, or enter a different price.",
        "watch_active": "Monitoring active: '{product}'{price_info}{cat_info}",

        # /list_products
        "no_products": "You are not monitoring any products. Use /watch to start.",
        "no_products_short": "You are not monitoring any products.",
        "your_products": "Your monitored products:\n{products}",

        # /unwatch
        "unwatch_prompt": "Which product do you want to remove? Enter the number:\n{products}\n\n/cancel to abort",
        "unwatched": "Removed: '{product}'",

        # /history
        "history_prompt": "Which product do you want to see history for?\n{products}\n\n/cancel to abort",
        "history_empty": "No matches found for '{product}'.",
        "history_header": "History for '{product}' (last {count} matches):",

        # /pause & /resume
        "paused": "Notifications paused. Use /resume to reactivate.",
        "resumed": "Notifications reactivated!",

        # /stats
        "stats_header": "Your stats:",
        "stats_products": "  Monitored products: {count}",
        "stats_channels": "  Channels: {count}",
        "stats_matches": "  Total matches: {count}",
        "stats_top_product": "  Top product: {name} ({count} matches)",
        "stats_top_channel": "  Top channel: {name} ({count} matches)",
        "stats_last_match": "  Last match: {date}",

        # /list_categories
        "categories_header": "Products by category:",
        "uncategorized": "Uncategorized",

        # Notifications (channel_listener / backfill)
        "notify_match": "'{product}' found in {channel}!\n{price_line}{text}{link_line}",
        "notify_price_line": "Price found: {price:.2f} (target: {target:.2f})\n\n",
        "notify_link_line": "\n\n Go to message: {link}",
        "notify_backfill_match": "[Backfill] '{product}' found in {channel}!\n{price_line}{text}{link_line}",
        "notify_backfill_price_line": "{price:.2f} (target: {target:.2f})\n\n",

        # join/leave channel
        "join_channel_success": "Joined channel: {channel}",
        "join_channel_failed": "Failed to join channel. Please check the link.",
        "leave_channel_success": "Left channel: {channel}",
        "leave_channel_failed": "Error leaving channel. Please try again later.",

        # Daily summary
        "summary_header": "Daily summary ({count} matches):",
        "summary_product": "\n {name} ({count} matches):",
        "summary_more": "  ... and {count} more",
    },

    "it": {
        # Auth / generic
        "not_authorized": "Non sei autorizzato ad usare questo bot.",
        "start_first": "Avvia prima il bot con /start in una chat privata.",
        "operation_cancelled": "Operazione annullata.",
        "timed_out": "Tempo scaduto. Riprova con {command}.",
        "invalid_choice": "Scelta non valida. Riprova con {command}.",
        "number_out_of_range": "Numero fuori intervallo. Riprova con {command}.",

        # /start
        "welcome": "Ciao {username}, benvenuto! Usa /add_channel per aggiungere un canale da monitorare.",

        # /add_channel
        "add_channel_prompt": "Invia il nome utente del canale o un link di invito (t.me/+...). Scrivi /annulla per annullare.",
        "invalid_invite_link": "Link di invito non valido.",
        "invalid_channel_id": "Identificativo canale non valido. Usa solo lettere, numeri e underscore (es. offerte_tech).",
        "scanning_messages": "Scansione messaggi esistenti...",
        "backfill_matches": "Scansione completata: {count} corrispondenze trovate!",
        "backfill_no_matches": "Scansione completata: nessuna corrispondenza trovata.",

        # /list_channels
        "no_channels": "Non hai canali aggiunti.",
        "your_channels": "I tuoi canali:\n{channels}",

        # /watch
        "watch_ask_product": "Quale prodotto vuoi monitorare? (scrivi /annulla per annullare)",
        "watch_ask_price": "A quale prezzo vuoi essere notificato?\nInserisci un prezzo (es. 799) o /salta per essere notificato a qualsiasi prezzo.",
        "watch_invalid_price": "Prezzo non valido. Riprova con /watch.",
        "watch_ask_category": "Categoria? (es. elettronica, abbigliamento, casa)\nScrivi /salta per saltare.",
        "watch_already_monitoring": "Stai gi\u00e0 monitorando '{product}'.",
        "watch_suggest_price": "Dallo storico, il prezzo pi\u00f9 basso trovato per '{product}' \u00e8 {price:.2f}.\nVuoi usare {price:.2f} come prezzo obiettivo?\nRispondi 's\u00ec' per accettare, o inserisci un prezzo diverso.",
        "watch_active": "Monitoraggio attivo: '{product}'{price_info}{cat_info}",

        # /list_products
        "no_products": "Non stai monitorando nessun prodotto. Usa /watch per iniziare.",
        "no_products_short": "Non stai monitorando nessun prodotto.",
        "your_products": "I tuoi prodotti monitorati:\n{products}",

        # /unwatch
        "unwatch_prompt": "Quale prodotto vuoi rimuovere? Inserisci il numero:\n{products}\n\n/annulla per annullare",
        "unwatched": "Rimosso: '{product}'",

        # /history
        "history_prompt": "Di quale prodotto vuoi vedere lo storico?\n{products}\n\n/annulla per annullare",
        "history_empty": "Nessuna corrispondenza trovata per '{product}'.",
        "history_header": "Storico per '{product}' (ultime {count} corrispondenze):",

        # /pause & /resume
        "paused": "Notifiche in pausa. Usa /resume per riattivare.",
        "resumed": "Notifiche riattivate!",

        # /stats
        "stats_header": "Le tue statistiche:",
        "stats_products": "  Prodotti monitorati: {count}",
        "stats_channels": "  Canali: {count}",
        "stats_matches": "  Corrispondenze totali: {count}",
        "stats_top_product": "  Prodotto top: {name} ({count} corrispondenze)",
        "stats_top_channel": "  Canale top: {name} ({count} corrispondenze)",
        "stats_last_match": "  Ultima corrispondenza: {date}",

        # /list_categories
        "categories_header": "Prodotti per categoria:",
        "uncategorized": "Senza categoria",

        # Notifications (channel_listener / backfill)
        "notify_match": "'{product}' trovato in {channel}!\n{price_line}{text}{link_line}",
        "notify_price_line": "Prezzo trovato: {price:.2f} (obiettivo: {target:.2f})\n\n",
        "notify_link_line": "\n\n Vai al messaggio: {link}",
        "notify_backfill_match": "[Scansione] '{product}' trovato in {channel}!\n{price_line}{text}{link_line}",
        "notify_backfill_price_line": "{price:.2f} (obiettivo: {target:.2f})\n\n",

        # join/leave channel
        "join_channel_success": "Canale aggiunto: {channel}",
        "join_channel_failed": "Impossibile unirsi al canale. Controlla il link.",
        "leave_channel_success": "Canale abbandonato: {channel}",
        "leave_channel_failed": "Errore nell'abbandonare il canale. Riprova pi\u00f9 tardi.",

        # Daily summary
        "summary_header": "Riepilogo giornaliero ({count} corrispondenze):",
        "summary_product": "\n {name} ({count} corrispondenze):",
        "summary_more": "  ... e altre {count}",
    },
}


def resolve_lang(lang_code: str | None) -> str:
    """Map a Telegram lang_code to a supported language.

    Truncates to 2 chars and falls back to DEFAULT_LANGUAGE.
    """
    if not lang_code:
        return DEFAULT_LANGUAGE
    short = lang_code[:2].lower()
    if short in SUPPORTED_LANGUAGES:
        return short
    return DEFAULT_LANGUAGE


def t(key: str, lang: str, **kwargs) -> str:
    """Return translated string with variable interpolation.

    Falls back to English if language unsupported or key missing.
    """
    messages = MESSAGES.get(lang, MESSAGES[DEFAULT_LANGUAGE])
    template = messages.get(key)
    if template is None:
        template = MESSAGES[DEFAULT_LANGUAGE].get(key, key)
    if kwargs:
        return template.format(**kwargs)
    return template
