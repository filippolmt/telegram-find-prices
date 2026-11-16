"""
Internationalization: message translations and language helpers.
"""

SUPPORTED_LANGUAGES = {"en", "it"}
DEFAULT_LANGUAGE = "en"

MESSAGES = {
    "en": {
        # Auth / generic
        "not_authorized": "You are not authorized to use this bot.",
        "users_only": "This bot works only for user accounts, in a private chat.",
        "operation_cancelled": "Operation cancelled.",
        "timed_out": "Timed out. Try again with {command}.",
        "invalid_choice": "Invalid choice. Try again with {command}.",
        "number_out_of_range": "Number out of range. Try again with {command}.",

        # /start
        "welcome": "Hi {name}, welcome! Use /watch to follow a product, also in one message: /watch <name or Amazon link>. /list_channels shows the channels monitored for everyone.",
        "folder_channels_monitored": "Channels monitored from your Telegram folder «{folder}»: {count}. Channels you add to it or remove from it follow within 10 minutes.",

        # /add_channel
        "add_channel_prompt": "Send the channel username or an invite link (t.me/+...). Type /cancel to abort.",
        "invalid_invite_link": "Invalid invite link.",
        "invalid_channel_id": "Invalid channel identifier. Use only letters, numbers and underscores (e.g. deals_tech).",
        "scanning_messages": "Scanning existing messages...",
        "backfill_matches": "Backfill complete: {count} matches found!",
        "backfill_no_matches": "Backfill complete: no matches found.",

        # /list_channels
        "no_channels": "No channels are monitored.",
        "monitored_channels": "Monitored channels:\n{channels}",
        "your_pending_requests": "\n\nYour requests waiting for the owner (+ add, − remove):\n{requests}",
        "no_requests": "No channel requests are pending.",

        # /watch
        "watch_ask_product": "What product do you want to monitor? Type its name or send an Amazon product link. (type /cancel to abort)",
        "watch_asin_keywords": "Amazon product {asin}: posts linking to it will match.\nSuggested keywords, to also match other variants and posts without the link: {keywords}\nReply 'ok' to accept, type your own keywords, or /skip to match by link only.",
        "watch_link_not_product": "I can't read an Amazon product from that link. Try again with /watch, sending the product name or a link like amazon.it/dp/… or amzn.eu/d/….",
        "watch_asin_no_keywords": "Amazon product {asin}: posts linking to it will match.\nType keywords to also match other variants and posts without the link, or /skip to match by link only.",
        "watch_ask_price": "At what price do you want to be notified?\nEnter a price (e.g. 799) or /skip to be notified at any price.",
        "watch_name_no_keywords": "The product name needs letters or digits. Try again with /watch.",
        "watch_invalid_price": "Invalid price. Try again with /watch.",
        "watch_ask_category": "Category? (e.g. electronics, clothing, home)\nType /skip to skip.",
        "watch_already_monitoring": "You are already monitoring '{product}'.",
        "watch_suggest_price": "From history, the lowest price found for '{product}' is {price:.2f}.\nDo you want to use {price:.2f} as target price?\nReply 'yes' to accept, or enter a different price.",
        "watch_active": "Monitoring active: '{product}'{price_info}{cat_info}",
        "watch_price_info": " at {price}",
        "any_price": "any price",
        "no_price": "N/A",

        # /list_products
        "no_products": "You are not monitoring any products. Use /watch to start.",
        "no_products_short": "You are not monitoring any products.",
        "your_products": "Your monitored products:\n{products}",

        # /unwatch
        "unwatch_prompt": "Which product do you want to remove? Enter the number:\n{items}\n\n/cancel to abort",
        "unwatched": "Removed: '{product}'",

        # /history
        "history_prompt": "Which product do you want to see history for?\n{items}\n\n/cancel to abort",
        "history_empty": "No matches found for '{product}'.",
        "history_header": "History for '{product}' (last {count} matches):",

        # /pause & /resume
        "paused": "Notifications paused. Use /resume to reactivate.",
        "resumed": "Notifications reactivated!",

        # /stats
        "stats_header": "Your stats:",
        "stats_products": "  Monitored products: {count}",
        "stats_channels": "  Monitored channels: {count}",
        "stats_matches": "  Total matches: {count}",
        "stats_top_product": "  Top product: {name} ({count} matches)",
        "stats_top_channel": "  Top channel: {name} ({count} matches)",
        "stats_last_match": "  Last match: {date}",

        # /list_categories
        "categories_header": "Products by category:",
        "uncategorized": "Uncategorized",

        # Notifications (channel_listener / backfill)
        "notify_match": "'{product}' found in {channel}!\n{price_line}{text}{offer_line}{link_line}",
        "notify_price_line": "Price found: {price:.2f} (target: {target:.2f})\n\n",
        "notify_offer_line": "\n\nOffer: {url}",
        "notify_link_line": "\n\nGo to message: {link}",
        "notify_backfill_match": "[Backfill] '{product}' found in {channel}!\n{price_line}{text}{offer_line}{link_line}",
        "notify_backfill_price_line": "{price:.2f} (target: {target:.2f})\n\n",

        # join/leave channel
        "channel_added": "Channel monitored: {channel}",
        "channel_already_monitored": "Already monitored: {channel}",
        "request_sent": "Request sent to the bot owner: {channel}. You will get their answer here.",
        "request_already_pending": "You already asked for {channel}: the request waits for the owner.",
        "request_other_pending": "A request about {channel} already waits for the owner.",
        "request_owner_add": "{requester} asks to monitor {channel}.",
        "request_owner_remove": "{requester} asks to stop monitoring {channel}. Approving makes your account leave the channel.",
        "owner_only_button": "Only the bot owner decides channel requests.",
        "request_already_decided": "This request was already decided.",
        "request_still_pending": "The request is still pending.",
        "request_approved_add": "Your request was approved: {channel} is now monitored.",
        "request_approved_remove": "Your request was approved: {channel} is no longer monitored.",
        "reject_reason_prompt": "Why do you reject the request for {channel}? The requesters will read it. /cancel to decide later.",
        "reject_reason_required": "A reason is required: the request is still pending.",
        "request_rejected": "Request rejected: {channel}",
        "request_rejected_requester": "Your request for {channel} was rejected: {reason}",
        "requester_username": "@{name}",
        "invite_label": "t.me/+{hash}…",
        "pending_line_add": "+ {channel}",
        "pending_line_remove": "− {channel}",
        "approve": "Approve",
        "reject": "Reject",
        "channels_owner_only": "Only the bot owner chooses the monitored channels.",
        "folder_add_failed": "Your account joined {channel} but could not add it to the folder «{folder}» (full, or missing?): the channel is not monitored.",
        "join_channel_failed": "Failed to join channel. Please check the link.",

        # /remove_channel
        "remove_channel_prompt": "Which channel do you want to remove? Enter the number:\n{items}\n\n/cancel to abort",
        "channel_removed": "Channel no longer monitored, your account left it: {channel}",
        "channel_removed_not_left": "Channel no longer monitored, but your account could not leave it: {channel}",
        "folder_remove_failed": "Could not take {channel} out of the folder «{folder}» (missing?): it is still monitored.",

        # Daily summary
        "summary_header": "Daily summary ({count} matches):",
        "summary_product": "\n {name} ({count} matches):",
        "summary_more": "  ... and {count} more",
    },

    "it": {
        # Auth / generic
        "not_authorized": "Non sei autorizzato ad usare questo bot.",
        "users_only": "Questo bot funziona solo con account utente, in una chat privata.",
        "operation_cancelled": "Operazione annullata.",
        "timed_out": "Tempo scaduto. Riprova con {command}.",
        "invalid_choice": "Scelta non valida. Riprova con {command}.",
        "number_out_of_range": "Numero fuori intervallo. Riprova con {command}.",

        # /start
        "welcome": "Ciao {name}, benvenuto! Usa /watch per seguire un prodotto, anche in un solo messaggio: /watch <nome o link Amazon>. /list_channels mostra i canali monitorati per tutti.",
        "folder_channels_monitored": "Canali monitorati dal tuo folder Telegram «{folder}»: {count}. I canali che aggiungi o togli dal folder vengono aggiornati entro 10 minuti.",

        # /add_channel
        "add_channel_prompt": "Invia il nome utente del canale o un link di invito (t.me/+...). Scrivi /annulla per annullare.",
        "invalid_invite_link": "Link di invito non valido.",
        "invalid_channel_id": "Identificativo canale non valido. Usa solo lettere, numeri e underscore (es. offerte_tech).",
        "scanning_messages": "Scansione messaggi esistenti...",
        "backfill_matches": "Scansione completata: {count} corrispondenze trovate!",
        "backfill_no_matches": "Scansione completata: nessuna corrispondenza trovata.",

        # /list_channels
        "no_channels": "Nessun canale è monitorato.",
        "monitored_channels": "Canali monitorati:\n{channels}",
        "your_pending_requests": "\n\nLe tue richieste in attesa del proprietario (+ aggiungi, − togli):\n{requests}",
        "no_requests": "Nessuna richiesta sui canali in attesa.",

        # /watch
        "watch_ask_product": "Quale prodotto vuoi monitorare? Scrivi il nome o invia il link di un prodotto Amazon. (scrivi /annulla per annullare)",
        "watch_asin_keywords": "Prodotto Amazon {asin}: i post con un link a questo prodotto verranno segnalati.\nParole chiave suggerite, per segnalare anche altre varianti e post senza link: {keywords}\nRispondi 'ok' per accettare, scrivi le tue parole chiave, o /salta per usare solo il link.",
        "watch_link_not_product": "Non riesco a leggere un prodotto Amazon da quel link. Riprova con /watch, inviando il nome del prodotto o un link come amazon.it/dp/… o amzn.eu/d/….",
        "watch_asin_no_keywords": "Prodotto Amazon {asin}: i post con un link a questo prodotto verranno segnalati.\nScrivi delle parole chiave per segnalare anche altre varianti e post senza link, o /salta per usare solo il link.",
        "watch_ask_price": "A quale prezzo vuoi essere notificato?\nInserisci un prezzo (es. 799) o /salta per essere notificato a qualsiasi prezzo.",
        "watch_name_no_keywords": "Il nome del prodotto deve contenere lettere o numeri. Riprova con /watch.",
        "watch_invalid_price": "Prezzo non valido. Riprova con /watch.",
        "watch_ask_category": "Categoria? (es. elettronica, abbigliamento, casa)\nScrivi /salta per saltare.",
        "watch_already_monitoring": "Stai gi\u00e0 monitorando '{product}'.",
        "watch_suggest_price": "Dallo storico, il prezzo pi\u00f9 basso trovato per '{product}' \u00e8 {price:.2f}.\nVuoi usare {price:.2f} come prezzo obiettivo?\nRispondi 's\u00ec' per accettare, o inserisci un prezzo diverso.",
        "watch_active": "Monitoraggio attivo: '{product}'{price_info}{cat_info}",
        "watch_price_info": " a {price}",
        "any_price": "qualsiasi prezzo",
        "no_price": "N/D",

        # /list_products
        "no_products": "Non stai monitorando nessun prodotto. Usa /watch per iniziare.",
        "no_products_short": "Non stai monitorando nessun prodotto.",
        "your_products": "I tuoi prodotti monitorati:\n{products}",

        # /unwatch
        "unwatch_prompt": "Quale prodotto vuoi rimuovere? Inserisci il numero:\n{items}\n\n/annulla per annullare",
        "unwatched": "Rimosso: '{product}'",

        # /history
        "history_prompt": "Di quale prodotto vuoi vedere lo storico?\n{items}\n\n/annulla per annullare",
        "history_empty": "Nessuna corrispondenza trovata per '{product}'.",
        "history_header": "Storico per '{product}' (ultime {count} corrispondenze):",

        # /pause & /resume
        "paused": "Notifiche in pausa. Usa /resume per riattivare.",
        "resumed": "Notifiche riattivate!",

        # /stats
        "stats_header": "Le tue statistiche:",
        "stats_products": "  Prodotti monitorati: {count}",
        "stats_channels": "  Canali monitorati: {count}",
        "stats_matches": "  Corrispondenze totali: {count}",
        "stats_top_product": "  Prodotto top: {name} ({count} corrispondenze)",
        "stats_top_channel": "  Canale top: {name} ({count} corrispondenze)",
        "stats_last_match": "  Ultima corrispondenza: {date}",

        # /list_categories
        "categories_header": "Prodotti per categoria:",
        "uncategorized": "Senza categoria",

        # Notifications (channel_listener / backfill)
        "notify_match": "'{product}' trovato in {channel}!\n{price_line}{text}{offer_line}{link_line}",
        "notify_price_line": "Prezzo trovato: {price:.2f} (obiettivo: {target:.2f})\n\n",
        "notify_offer_line": "\n\nOfferta: {url}",
        "notify_link_line": "\n\nVai al messaggio: {link}",
        "notify_backfill_match": "[Scansione] '{product}' trovato in {channel}!\n{price_line}{text}{offer_line}{link_line}",
        "notify_backfill_price_line": "{price:.2f} (obiettivo: {target:.2f})\n\n",

        # join/leave channel
        "channel_added": "Canale monitorato: {channel}",
        "channel_already_monitored": "Già monitorato: {channel}",
        "request_sent": "Richiesta inviata al proprietario del bot: {channel}. Riceverai qui la sua risposta.",
        "request_already_pending": "Hai già chiesto {channel}: la richiesta attende il proprietario.",
        "request_other_pending": "Una richiesta su {channel} attende già il proprietario.",
        "request_owner_add": "{requester} chiede di monitorare {channel}.",
        "request_owner_remove": "{requester} chiede di non monitorare più {channel}. Approvando, il tuo account uscirà dal canale.",
        "owner_only_button": "Solo il proprietario del bot decide le richieste sui canali.",
        "request_already_decided": "Questa richiesta è già stata decisa.",
        "request_still_pending": "La richiesta resta in attesa.",
        "request_approved_add": "La tua richiesta è stata approvata: {channel} ora è monitorato.",
        "request_approved_remove": "La tua richiesta è stata approvata: {channel} non è più monitorato.",
        "reject_reason_prompt": "Perché rifiuti la richiesta per {channel}? Chi l'ha fatta leggerà il motivo. /annulla per decidere più tardi.",
        "reject_reason_required": "Il motivo è obbligatorio: la richiesta resta in attesa.",
        "request_rejected": "Richiesta rifiutata: {channel}",
        "request_rejected_requester": "La tua richiesta per {channel} è stata rifiutata: {reason}",
        "requester_username": "@{name}",
        "invite_label": "t.me/+{hash}…",
        "pending_line_add": "+ {channel}",
        "pending_line_remove": "− {channel}",
        "approve": "Approva",
        "reject": "Rifiuta",
        "channels_owner_only": "Solo il proprietario del bot sceglie i canali monitorati.",
        "folder_add_failed": "Il tuo account è entrato in {channel} ma non è riuscito ad aggiungerlo al folder «{folder}» (pieno, o mancante?): il canale non è monitorato.",
        "join_channel_failed": "Impossibile unirsi al canale. Controlla il link.",

        # /remove_channel
        "remove_channel_prompt": "Quale canale vuoi rimuovere? Inserisci il numero:\n{items}\n\n/annulla per annullare",
        "channel_removed": "Canale non più monitorato, il tuo account ne è uscito: {channel}",
        "channel_removed_not_left": "Canale non più monitorato, ma il tuo account non è riuscito a uscirne: {channel}",
        "folder_remove_failed": "Impossibile togliere {channel} dal folder «{folder}» (mancante?): è ancora monitorato.",

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
