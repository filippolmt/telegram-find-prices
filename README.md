# Telegram Find Prices

Telegram bot that monitors channels and notifies you when a product you're looking for is mentioned, with optional price filtering.

## Features

- `/start` - Register your account
- `/add_channel` - Add a channel to monitor (public or invite link); `/add_channel @channel` skips the question. Only the owner adds channels; with `CHANNEL_FOLDER` other users file a request the owner approves or rejects
- `/remove_channel` - Stop monitoring a channel: the owner's account leaves it. Other users file a request, as for `/add_channel`
- `/list_channels` - Show the monitored channels, shared by every user, and your pending requests
- `/requests` - Owner only: pending channel requests, each with Approve/Reject buttons (a rejection asks for a reason, sent to the requesters)
- `/watch` - Add a product to monitor by name or Amazon product link (with optional target price and category); `/watch <name or link>` skips the first question. A product added by link also matches posts that link to it through Amazon short links (`link.amazon`, `amzn.to`, `amzn.eu`) or the `amzlink.to` shortener
- `/list_products` - Show your monitored products
- `/unwatch` - Remove a product from monitoring
- `/history` - View price history for a product
- `/pause` - Pause notifications
- `/resume` - Resume notifications
- `/stats` - View your statistics
- `/list_categories` - Show products grouped by category
- Auto-detects user language (English and Italian supported, English default)

## Prerequisites

- Docker and Docker Compose
- Optional: [uv](https://docs.astral.sh/uv/) to run tests and lint without Docker
- A Telegram account with:
  - **API_ID** and **API_HASH** from [my.telegram.org](https://my.telegram.org)
  - **BOT_TOKEN** from [@BotFather](https://t.me/BotFather)
  - Your **phone number** associated with the account
  - Your **numeric user ID** (get it from [@userinfobot](https://t.me/userinfobot))

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/filippolmt/telegram-find-prices.git
cd telegram-find-prices
```

### 2. Configure environment variables

```bash
cp example.env .env
```

Fill in `.env` with your credentials:

```
API_ID=123456
API_HASH=abc123def456
BOT_TOKEN=123456:ABC-DEF
USERNAME=your_username
PHONE_NUMBER=+39123456789
ALLOWED_USERS=12345678
```

`ALLOWED_USERS` restricts who can use the bot (comma-separated numeric IDs). If empty, the bot rejects everyone: set `ALLOW_ALL_USERS=true` only if you really want any Telegram user to drive your account (join channels, run backfills). Non-numeric entries are ignored with a warning in the logs.

Use a separate bot (its own `BOT_TOKEN`) for local development, so a local instance never runs alongside the production one on the same bot.

`CHANNEL_FOLDER` (optional) names a Telegram folder of the owner's account (the user client's): it holds exactly the monitored channels. The owner's `/add_channel` and `/remove_channel`, and approved requests, add the channel to it or take it out; a channel the owner moves in or out by hand in Telegram starts or stops being monitored (the account does not leave it). Only the channels listed in the folder count, not its rules (e.g. "all channels"). Without it, users cannot file channel requests and the monitored channels are those the owner adds with `/add_channel`. The owner must be listed in `ALLOWED_USERS`: while nobody is owner, the folder is not read and the monitored channels stay as they are. The folder is read at startup, when the owner sends `/start`, whenever the folder changes, and every 10 minutes. A folder holds at most 100 chats (200 with Premium): when it is full, adding a channel fails and the owner is told.

All available variables and their defaults are in [`src/config.py`](src/config.py).

### 3. First-time authentication

You have two options:

**Option A: StringSession (recommended for production)**

```bash
make gen-session
```

This generates a session string that you can store as an environment variable. Telegram sends a verification code to your phone — enter it when prompted. Copy the output and add it to `.env`:

```
CLIENT_SESSION_STRING=1BVtsO...
```

No session files needed. Ideal for containers and CI/CD.

Without the repo (e.g. on the server, or a self-hosting platform such as Runtipi), the published image generates it, for amd64 and arm64 alike:

```bash
docker run --rm -it -e API_ID=123456 -e API_HASH=abc -e PHONE_NUMBER=+39... \
  ghcr.io/filippolmt/telegram-find-prices:latest python src/generate_string_session.py
```

The bot itself never asks for a login code: with no authorized session it logs `User session not authorized` and exits, so a container restarting it does not send a new code to your phone each time.

**Option B: File-based session**

```bash
make auth
```

This creates session files in `data/` that are reused on subsequent runs. Simpler for local development.

### 4. Bot commands

The bot sets its command menu itself at startup, in English and Italian: nothing to paste in BotFather. In private chats it takes precedence over a list pasted there.

### 5. Start the bot

```bash
make build   # first run, and after every dependency change
make run-d
```

The bot starts in the background. Verify it's running with:

```bash
make logs
```

You should see:

```
[INFO] Bot started!
[INFO] Client started!
[INFO] Channel listener active!
```

## Make Commands

| Command | Description |
|---------|-------------|
| `make auth` | First-time file-based authentication (one-time only) |
| `make gen-session` | Generate a StringSession for production use |
| `make run` | Start the bot in foreground |
| `make run-d` | Start the bot in background |
| `make logs` | Show bot logs in real-time |
| `make stop` | Stop the bot |
| `make test` | Run tests |
| `make test-v` | Run tests with verbose output |
| `make test-one T=tests/test_models.py` | Run a single test file |
| `make lint` | Run ruff |
| `make shell` | Open a shell inside the container |
| `make build` | Rebuild the Docker image |
| `make clean` | Remove containers, images and volumes |

## How it works

1. The owner (the account of the user client) adds channels to monitor with `/add_channel` (supports public usernames and invite links), or puts them in the folder named by `CHANNEL_FOLDER`; other users ask with `/add_channel` and `/remove_channel` when there is a folder. Monitored channels are shared by every user
2. Add products with `/watch` (optionally with a target price and category)
3. When a message in a monitored channel mentions a product, every authorized user watching it receives a notification via bot
4. If you set a target price, you only get notified when the price found is at or below the target
5. Fuzzy matching handles hyphens, underscores, and extra spaces in product names
6. Price history is tracked and a daily summary is sent at a configurable time

## Project structure

```
src/
  bot.py                      # Entry point
  dev.py                      # Auto-reload runner for development (watchdog)
  auth.py                     # File-based authentication script
  generate_string_session.py  # StringSession generator for production
  config.py                   # Configuration from .env
  database.py                 # SQLAlchemy setup and migrations
  models.py                   # DB models (User, Channel, Product, PriceHistory)
  bot_commands.py             # Bot command handlers
  client_commands.py          # Telegram client operations
  channel_listener.py         # Channel message listener
  channel_folder.py           # Channel folder (CHANNEL_FOLDER): holds exactly the monitored channels
  channel_requests.py         # Channel requests waiting for the owner
  price_parser.py             # European price format parser
  scheduler.py                # Daily summary scheduler
  translations.py             # i18n: message translations (en/it)
tests/
  conftest.py                 # Pytest fixtures
  test_authorization.py       # ALLOWED_USERS parsing and fail-closed authorization
  test_bot.py                 # Client creation (file session vs StringSession)
  test_models.py              # DB model tests
  test_matching.py            # Product matching logic tests
  test_price_parser.py        # Price parser tests
  test_translations.py        # Translation tests
production/
  docker-compose.yml          # Production compose (pre-built ghcr.io image)
  example.env                 # Production environment template
data/                         # Runtime (sessions, database) - gitignored
```

## Production Deployment

The Docker image is automatically built and pushed to GitHub Container Registry when a version tag is pushed.

```bash
cd production
cp example.env .env
# Fill in .env with your credentials and CLIENT_SESSION_STRING
docker compose up -d
```

To release a new version:

```bash
git tag v1.0.0
git push origin v1.0.0
```

The image is built for `linux/amd64` and `linux/arm64`, tagged with the version (e.g. `1.0.0`) and `latest`. The production compose uses the pre-built image from `ghcr.io/filippolmt/telegram-find-prices:latest`. The `data/` volume persists the SQLite database and session files on the host.

Variables are resolved via Docker Compose interpolation (`${VAR}`): host environment variables take precedence over the `.env` file in the `production/` directory, which takes precedence over defaults defined in the compose file. A variable missing from `production/docker-compose.yml` never reaches the container.

### Upgrading from older versions

- **Authorization is fail-closed.** An empty `ALLOWED_USERS` used to open the bot to everyone; now it rejects everyone. Set `ALLOWED_USERS` (or `ALLOW_ALL_USERS=true`) before upgrading, or the bot stops answering. The startup log warns when nobody is authorized.
- **Runtime files are created owner-only (`600`).** Files created by older versions keep their permissions: run `chmod 600 data/*` once on the host.

## Tests and lint

```bash
make test        # in Docker
make lint

uv run pytest    # natively, faster (Python version from .python-version)
uv run ruff check src tests
```

Tests use an in-memory SQLite database and need no Telegram credentials. Any warning fails the suite (`filterwarnings = ["error"]` in `pyproject.toml`). CI runs ruff and pytest on every push and PR to `main`.
