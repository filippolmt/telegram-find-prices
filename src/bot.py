"""
Telegram Bot - Main entry point.
"""

import asyncio
import logging
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import FloodWaitError, AccessTokenExpiredError, AccessTokenInvalidError, ApiIdInvalidError, PhoneNumberInvalidError

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)
from bot_commands import BotCommands
from channel_listener import ChannelListener
from client_commands import ClientCommands
from config import Config
from scheduler import DailySummaryScheduler
from database import Base, engine, SessionLocal, run_migrations


def create_client(session_name: str, api_id: int, api_hash: str, session_string: str = "") -> TelegramClient:
    """Create a new Telegram client. Uses StringSession if session_string is provided."""
    session_string = session_string.strip()
    if session_string:
        return TelegramClient(StringSession(session_string), api_id, api_hash)
    return TelegramClient(session_name, api_id, api_hash)


async def main():
    """Main function to start the bot."""
    cf = Config()
    bot_token = cf.BOT_TOKEN
    api_id = cf.API_ID
    api_hash = cf.API_HASH
    bot_session_name = cf.BOT_SESSION_NAME
    client_session_name = cf.CLIENT_SESSION_NAME

    Base.metadata.create_all(bind=engine)
    run_migrations()

    bot_client = create_client(bot_session_name, api_id, api_hash)
    client = create_client(client_session_name, api_id, api_hash, session_string=cf.CLIENT_SESSION_STRING)
    client_commands = ClientCommands(client, SessionLocal, bot_client)
    bot_commands = BotCommands(bot_client, client_commands, SessionLocal)

    try:
        if await bot_client.start(bot_token=bot_token):
            log.info("Bot started!")
            bot_commands.register_commands()
        else:
            log.error("Failed to start the bot.")
            return
    except (AccessTokenExpiredError, AccessTokenInvalidError):
        log.error("BOT_TOKEN is expired or invalid. Generate a new one via @BotFather and update .env")
        return
    except ApiIdInvalidError:
        log.error("API_ID or API_HASH is invalid. Check your credentials at my.telegram.org and update .env")
        return

    try:
        if await client.start(phone=cf.PHONE_NUMBER):
            log.info("Client started!")
            listener = ChannelListener(client, bot_client, SessionLocal)
            listener.register()
            log.info("Channel listener active!")
        else:
            log.error("Failed to start the client.")
            return
    except PhoneNumberInvalidError:
        log.error("PHONE_NUMBER is invalid. Check your .env configuration.")
        return
    except FloodWaitError as e:
        log.warning("Telegram requires a wait of %d seconds. Retrying...", e.seconds)
        await asyncio.sleep(e.seconds)
        if await client.start(phone=cf.PHONE_NUMBER):
            log.info("Client started!")
            listener = ChannelListener(client, bot_client, SessionLocal)
            listener.register()
            log.info("Channel listener active!")
        else:
            log.error("Failed to start the client.")
            return

    # Start daily summary scheduler
    scheduler = DailySummaryScheduler(
        bot_client, SessionLocal,
        hour=cf.DAILY_SUMMARY_HOUR,
        tz_name=cf.TIMEZONE,
    )
    scheduler.start()

    await bot_client.run_until_disconnected()
    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
