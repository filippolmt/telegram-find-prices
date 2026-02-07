"""
First-time Telegram authentication script.
Creates session files and exits.
"""

import asyncio
from telethon import TelegramClient
from config import Config


async def main():
    cf = Config()

    # Bot authentication
    bot = TelegramClient(cf.BOT_SESSION_NAME, cf.API_ID, cf.API_HASH)
    await bot.start(bot_token=cf.BOT_TOKEN)
    print("Bot authenticated!")
    await bot.disconnect()

    # Client authentication (requires SMS code on first run)
    client = TelegramClient(cf.CLIENT_SESSION_NAME, cf.API_ID, cf.API_HASH)
    await client.start(phone=cf.PHONE_NUMBER)
    me = await client.get_me()
    print(f"Client authenticated as {me.first_name} (@{me.username})!")
    await client.disconnect()

    print("Sessions saved. Start the bot with: make run-d")


if __name__ == "__main__":
    asyncio.run(main())
