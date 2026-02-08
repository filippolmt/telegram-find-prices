"""
Generate a Telethon StringSession for the user client.
Run once locally, then copy the output string to CLIENT_SESSION_STRING in .env.
"""

import sys
import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import ApiIdInvalidError, PhoneNumberInvalidError
from config import Config


async def main():
    cf = Config()

    if not cf.API_ID or not cf.API_HASH or not cf.PHONE_NUMBER:
        print("Error: API_ID, API_HASH, and PHONE_NUMBER must be set in .env")
        sys.exit(1)

    print("Generating StringSession for the user client...")
    print(f"Phone number: {cf.PHONE_NUMBER}")
    print()

    try:
        async with TelegramClient(StringSession(), cf.API_ID, cf.API_HASH) as client:
            await client.start(phone=cf.PHONE_NUMBER)

            me = await client.get_me()
            print(f"\nAuthenticated as {me.first_name} (@{me.username})")
            print()
            print("WARNING: The session string below grants full access to this Telegram account.")
            print("         Treat it like a password. Do not share it or commit it to version control.")
            print()
            print("Add this to your production .env:")
            print(f"CLIENT_SESSION_STRING={client.session.save()}")
    except ApiIdInvalidError:
        print("Error: API_ID or API_HASH is invalid. Check your .env configuration.")
        sys.exit(1)
    except PhoneNumberInvalidError:
        print("Error: PHONE_NUMBER is invalid. Check your .env configuration.")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
