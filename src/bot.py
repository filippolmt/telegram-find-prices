"""
Telegram Bot - Main entry point.
"""

import asyncio
import logging

from telethon import TelegramClient
from telethon.errors import (
    AccessTokenExpiredError,
    AccessTokenInvalidError,
    ApiIdInvalidError,
)
from telethon.sessions import StringSession

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)
from bot_commands import BotCommands
from channel_folder import ChannelFolder
from channel_listener import ChannelListener
from client_commands import ClientCommands
from config import Config
from database import (
    Base,
    SessionLocal,
    engine,
    migrate_to_shared_channels,
    run_migrations,
)
from scheduler import DailySummaryScheduler


def create_client(session_name: str, api_id: int, api_hash: str, session_string: str = "", lang_code: str = "en") -> TelegramClient:
    """Create a new Telegram client. Uses StringSession if session_string is provided.

    lang_code is the language the client presents to Telegram, which bots see as the sender's.
    """
    session_string = session_string.strip()
    session = StringSession(session_string) if session_string else session_name
    return TelegramClient(session, api_id, api_hash, lang_code=lang_code, system_lang_code=lang_code)


async def user_client_ready(client: TelegramClient) -> bool:
    """Connect the user client with its saved session. It never asks for a login code: a container has no
    terminal to type it in, and each restart would send a new code to the phone."""
    await client.connect()
    if await client.is_user_authorized():
        return True
    log.error("User session not authorized: set CLIENT_SESSION_STRING (src/generate_string_session.py, "
              "see README) or run make auth")
    return False


async def main():
    """Main function to start the bot."""
    cf = Config()
    bot_token = cf.BOT_TOKEN
    api_id = cf.API_ID
    api_hash = cf.API_HASH
    bot_session_name = cf.BOT_SESSION_NAME
    client_session_name = cf.CLIENT_SESSION_NAME

    if not cf.ALLOWED_USERS and not cf.ALLOW_ALL_USERS:
        log.warning("ALLOWED_USERS is empty: the bot will reject every user. "
                    "Set ALLOWED_USERS, or ALLOW_ALL_USERS=true to open it to everyone.")
    elif not cf.ALLOWED_USERS:
        log.warning("ALLOW_ALL_USERS=true: any Telegram user can drive this account.")

    Base.metadata.create_all(bind=engine)
    run_migrations()

    bot_client = create_client(bot_session_name, api_id, api_hash)
    client = create_client(client_session_name, api_id, api_hash, session_string=cf.CLIENT_SESSION_STRING)
    client_commands = ClientCommands(client, SessionLocal, bot_client)
    channel_folder = ChannelFolder(client, client_commands, cf.CHANNEL_FOLDER) if cf.CHANNEL_FOLDER else None
    bot_commands = BotCommands(bot_client, client_commands, SessionLocal, channel_folder)

    try:
        if await bot_client.start(bot_token=bot_token):
            log.info("Bot started!")
            bot_commands.register_commands((await bot_client.get_me()).username)
        else:
            log.error("Failed to start the bot.")
            return
    except (AccessTokenExpiredError, AccessTokenInvalidError):
        log.error("BOT_TOKEN is expired or invalid. Generate a new one via @BotFather and update .env")
        return
    except ApiIdInvalidError:
        log.error("API_ID or API_HASH is invalid. Check your credentials at my.telegram.org and update .env")
        return

    if not await user_client_ready(client):
        return
    log.info("Client started!")
    migrate_to_shared_channels(await client_commands.owner_id())
    ChannelListener(client, bot_client, SessionLocal).register()
    log.info("Channel listener active!")

    # Start daily summary scheduler
    scheduler = DailySummaryScheduler(
        bot_client, SessionLocal,
        hour=cf.DAILY_SUMMARY_HOUR,
        tz_name=cf.TIMEZONE,
    )
    scheduler.start()

    if channel_folder:
        channel_folder.register()
        await channel_folder.sync()

    await bot_client.run_until_disconnected()
    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
