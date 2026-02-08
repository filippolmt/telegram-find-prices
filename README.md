# Telegram Find Prices

Telegram bot that monitors channels and notifies you when a product you're looking for is mentioned, with optional price filtering.

## Features

- `/start` - Register your account
- `/add_channel` - Add a channel to monitor (public or invite link)
- `/remove_channel` - Remove a channel from monitoring (keeps the Telegram subscription)
- `/list_channels` - Show your monitored channels
- `/watch` - Add a product to monitor (with optional target price and category)
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
- A Telegram account with:
  - **API_ID** and **API_HASH** from [my.telegram.org](https://my.telegram.org)
  - **BOT_TOKEN** from [@BotFather](https://t.me/BotFather)
  - Your **phone number** associated with the account
  - Your **numeric user ID** (get it from [@userinfobot](https://t.me/userinfobot))

## Setup

### 1. Clone the repository

```bash
git clone <repo-url>
cd telegram-find-prices
```

### 2. Configure environment variables

```bash
cp .env.example .env
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

`ALLOWED_USERS` restricts who can use the bot (comma-separated numeric IDs). If empty, the bot is open to everyone.

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

**Option B: File-based session**

```bash
make auth
```

This creates session files in `data/` that are reused on subsequent runs. Simpler for local development.

### 4. Register bot commands with BotFather

Open [@BotFather](https://t.me/BotFather), select your bot with `/mybots`, then **Edit Bot** > **Edit Commands** and paste:

```
start - Register your account
add_channel - Add a channel to monitor
remove_channel - Remove a channel from monitoring
list_channels - Show your monitored channels
watch - Add a product to monitor
list_products - Show your monitored products
unwatch - Remove a product from monitoring
history - View price history for a product
pause - Pause notifications
resume - Resume notifications
stats - View your statistics
list_categories - Show products grouped by category
```

### 5. Start the bot

```bash
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
| `make shell` | Open a shell inside the container |
| `make build` | Rebuild the Docker image |
| `make clean` | Remove containers, images and volumes |

## How it works

1. Add channels to monitor with `/add_channel` (supports public usernames and invite links)
2. Add products with `/watch` (optionally with a target price and category)
3. When a message in a monitored channel mentions a product, you receive a notification via bot
4. If you set a target price, you only get notified when the price found is at or below the target
5. Fuzzy matching handles hyphens, underscores, and extra spaces in product names
6. Price history is tracked and a daily summary is sent at a configurable time

## Project structure

```
src/
  bot.py                      # Entry point
  auth.py                     # File-based authentication script
  generate_string_session.py  # StringSession generator for production
  config.py                   # Configuration from .env
  database.py                 # SQLAlchemy setup and migrations
  models.py                   # DB models (User, Channel, Product, PriceHistory)
  bot_commands.py             # Bot command handlers
  client_commands.py          # Telegram client operations
  channel_listener.py         # Channel message listener
  price_parser.py             # European price format parser
  scheduler.py                # Daily summary scheduler
  translations.py             # i18n: message translations (en/it)
tests/
  conftest.py                 # Pytest fixtures
  test_models.py              # DB model tests
  test_matching.py            # Product matching logic tests
  test_price_parser.py        # Price parser tests
  test_translations.py        # Translation tests
production/
  docker-compose.yml          # Production compose (pre-built ghcr.io image)
  .env.example                # Production environment template
data/                         # Runtime (sessions, database) - gitignored
```

## Production Deployment

The Docker image is automatically built and pushed to GitHub Container Registry when a version tag is pushed.

```bash
cd production
cp .env.example .env
# Fill in .env with your credentials and CLIENT_SESSION_STRING
docker compose up -d
```

To release a new version:

```bash
git tag v1.0.0
git push origin v1.0.0
```

The image is tagged with the version (e.g. `1.0.0`) and `latest`. The production compose uses the pre-built image from `ghcr.io/filippolmt/telegram-find-prices:latest`. The `data/` volume persists the SQLite database and session files on the host.

Variables are resolved via Docker Compose interpolation (`${VAR}`): host environment variables take precedence over the `.env` file in the `production/` directory, which takes precedence over defaults defined in the compose file.

## Tests

```bash
make test
```

Tests run in an isolated Docker container with an in-memory SQLite database.
