# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**telegram-find-prices** — Telegram bot (Python 3.14) that monitors Telegram channels for product price offers and notifies users. Built with Telethon 1.42 (Telegram MTProto client) and SQLAlchemy (SQLite ORM). Runs in Docker.

## Commands

All operations go through the Makefile (Docker-based):

```bash
make auth       # First-time interactive Telegram authentication
make run-d      # Start bot in background
make run        # Start bot in foreground
make logs       # Tail bot logs
make stop       # Stop containers
make test       # Run all tests
make test-v     # Run tests verbose
make test-one T=tests/test_models.py  # Run single test file
make shell      # Shell into container
make build      # Rebuild Docker image
make clean      # Remove containers, images, volumes
```

Source code is mounted as Docker volumes (`src/`, `tests/`), so code changes are picked up without rebuilding. The Dockerfile uses a multi-stage build: uv is copied from the official `ghcr.io/astral-sh/uv` image, dependencies are compiled in a builder stage (with gcc for packages like aiohttp), and only the venv and source are copied to the final slim image.

## Architecture

### Dual-Client Design

The bot runs **two separate Telegram clients** concurrently:

- **Bot client** (`bot_session`): Receives user commands. Powered by a Telegram Bot Token.
- **User client** (`client_session`): Performs privileged actions (joining/leaving channels, reading channel messages) as a real Telegram user account. Requires phone number auth on first run via `make auth`.

`bot.py:main()` creates both clients, wires them together, starts the daily summary scheduler, and runs `bot_client.run_until_disconnected()`.

### Key Classes

- **`BotCommands`** (`bot_commands.py`) — Registers Telethon event handlers on the bot client. All commands check `ALLOWED_USERS` authorization. Validates channel identifiers with regex. Supports invite links (`t.me/+HASH`). Auto-detects user language from `sender.lang_code` and responds accordingly. Commands: `/start`, `/add_channel`, `/list_channels`, `/watch`, `/list_products`, `/unwatch`, `/history`, `/pause`, `/resume`, `/stats`, `/list_categories`.
- **`ClientCommands`** (`client_commands.py`) — Wraps Telethon channel operations (`JoinChannelRequest`, `ImportChatInviteRequest`, `LeaveChannelRequest`). Supports both public channels (username) and private channels (invite links). `list_channels()` is filtered per-user via DB join and shows channel title for private channels. `backfill_channel()` scans the last N messages of a channel for product matches. Error messages are sanitized (no RPC details leaked to users).
- **`ChannelListener`** (`channel_listener.py`) — Listens for new messages in channels. Filters products by user-channel subscription (joins Product -> UserChannel -> Channel). Matches by both username and numeric channel ID (for private channels). Uses `check_product_match()` for testable matching logic with fuzzy matching (hyphens, underscores, extra spaces). Saves matches to PriceHistory and includes direct message links in notifications.
- **`DailySummaryScheduler`** (`scheduler.py`) — Sends a daily summary of matches found to non-paused users at a configurable hour and timezone. Uses `zoneinfo.ZoneInfo` for timezone support.
- **`Config`** (`config.py`) — Loads settings from `.env` via `python-dotenv`. All paths resolved as absolute using `Path(__file__)`.
- **`PriceParser`** (`price_parser.py`) — Extracts European-format prices (EUR, euro symbol, dots for thousands, commas for decimals).
- **`translations`** (`translations.py`) — Dictionary-based i18n system. `MESSAGES` dict keyed by language code (`"en"`, `"it"`), `t(key, lang, **kwargs)` for translated string lookup with interpolation and English fallback, `resolve_lang(lang_code)` to map Telegram's `lang_code` to supported languages.

### Database

SQLite via SQLAlchemy (sync engine). Five tables:

| Table | Purpose |
|-------|---------|
| `users` | Telegram users who interacted with the bot. Has `paused` flag and `lang_code` for i18n. |
| `channels` | Monitored channels by identifier (username or numeric ID). Has `title` for private channels. |
| `user_channels` | Many-to-many join (user <-> channel) |
| `products` | Watched products per user with optional `target_price` and `category` |
| `price_history` | Price entries found in channels, with source (`realtime` or `backfill`) |

All classes accept a `sessionmaker` factory (not raw Session instances). SQLite configured with `check_same_thread=False` and `pool_pre_ping=True` for async compatibility.

Schema migrations are handled by `run_migrations()` in `database.py`, which adds missing columns to existing tables on startup (no Alembic dependency).

### Module Import Path

Source files in `src/` import each other as top-level modules (e.g., `from config import Config`). Tests add `src/` to `sys.path` in `conftest.py`.

### Runtime Files

All runtime data (SQLite DB, Telethon session files) stored in `data/` (gitignored). File permissions restricted to `600`.

## Environment Variables (.env at project root)

| Variable | Required | Description |
|----------|----------|-------------|
| `API_ID` | Yes | Telegram API ID (from my.telegram.org) |
| `API_HASH` | Yes | Telegram API Hash |
| `BOT_TOKEN` | Yes | Bot token from @BotFather |
| `PHONE_NUMBER` | Yes | Phone number for user client auth |
| `USERNAME` | No | Telegram username |
| `ALLOWED_USERS` | No | Comma-separated numeric user IDs (empty = open to all) |
| `TIMEZONE` | No | Timezone for daily summary (default: `UTC`) |
| `DAILY_SUMMARY_HOUR` | No | Hour for daily summary (default: `21`) |
| `BOT_SESSION_NAME` | No | Session file name (default: `bot_session`) |
| `CLIENT_SESSION_NAME` | No | Session file name (default: `client_session`) |
| `DATABASE_URL` | No | SQLAlchemy URL (default: `sqlite:///data/db.sqlite3`) |

## Security

- Docker container runs as non-root user (`appuser`)
- `.dockerignore` excludes `.env`, `.git/`, `data/`, session files
- Bot commands require `ALLOWED_USERS` authorization (if configured)
- Channel identifiers validated with regex before passing to Telegram API
- Invite hashes validated with alphanumeric regex
- RPC errors logged server-side, generic messages returned to users
- Channel listener queries filtered by user-channel subscription
- Paused users are excluded from notifications and daily summaries

## Testing

Tests use pytest with in-memory SQLite (no Telegram credentials needed). 75 tests across four files:

- `test_models.py` — DB models CRUD, constraints, pause/resume, categories, price history
- `test_matching.py` — `check_product_match()` logic including fuzzy matching (extracted from ChannelListener for testability)
- `test_price_parser.py` — European price format extraction
- `test_translations.py` — `t()` lookup, interpolation, fallback behavior, `resolve_lang()`, en/it key completeness

## Language & i18n

Code comments, docstrings, and log messages are in **English**. User-facing bot messages are **auto-translated** based on the user's Telegram language setting (`sender.lang_code`). Supported languages: **English** (default) and **Italian**. Unsupported languages fall back to English.

All translatable strings live in `src/translations.py` as a `MESSAGES` dict. To add a new language: add its 2-letter code to `SUPPORTED_LANGUAGES` and add a new key to `MESSAGES` with all string translations. The `test_translations.py` completeness checks will catch any missing keys.
