# CLAUDE.md

**telegram-find-prices**: Telegram bot (Python 3.14, Telethon, SQLAlchemy on SQLite) that watches Telegram channels for product price offers and notifies users. Runs in Docker.

## Commands

The `Makefile` is the entry point (`make test`, `make lint`, `make run-d`, `make auth`, …); read it for the full list. Tests also run natively with `uv run pytest`, faster than the Docker path. After a dependency change, `make build` before any other `make` target. `src/` and `tests/` are mounted as volumes, so code changes need only a restart.

To inspect real channels, folders or posts read-only, run a Telethon script with the local user-client session: `make stop`, then `docker compose run --rm -T test python - < script.py`, then `make run-d`. One session must never run in two processes at once.

Configuration: every variable and its default is in `src/config.py`; user-facing setup is in `README.md`.

## Architecture

Two Telegram clients run in one process, wired in `bot.py:main()`:

- **Bot client** receives user commands (`bot_commands.py`), authenticated with `BOT_TOKEN`.
- **User client** acts as a real user account: joins and leaves channels and reads their messages (`client_commands.py`, `channel_listener.py`). Bots cannot read channels they are not admin of, which is why this second client exists. Session from `data/` (`make auth`) or from `CLIENT_SESSION_STRING` (`make gen-session`, preferred in production).

## Conventions

- Classes take a `sessionmaker` factory, never a `Session`.
- Modules in `src/` import each other as top-level modules (`from config import Config`); `tests/conftest.py` puts `src/` on `sys.path`.
- Foreign keys are enforced and every one is `ondelete="CASCADE"` (`test_every_foreign_key_cascades`). Models have no `relationship()`, so in tests `flush()` a parent row (`User`, `Channel`, `Product`) before adding its children.
- Schema changes go in `run_migrations()` in `database.py` (adds missing columns and removes orphaned rows at startup). There is no Alembic.
- Code, comments and logs are in English. User-facing strings live only in `src/translations.py`; to add a language, add its code to `SUPPORTED_LANGUAGES` and a full `MESSAGES` entry. `test_translations.py` fails on missing keys.
- Runtime files (`data/`: DB, sessions) are created `600`/`700` by `os.umask(0o077)` in `config.py`.
- `filterwarnings = ["error"]` in `pyproject.toml`: a new warning fails the suite.

## Security invariants

Keep these true in every change:

- Authorization is fail-closed: empty `ALLOWED_USERS` rejects everyone unless `ALLOW_ALL_USERS=true`.
- Unauthorized senders are never written to the DB.
- User-supplied channel identifiers and invite hashes are validated by regex before reaching the Telegram API; invite hashes are logged truncated.
- RPC errors are logged server-side; users get generic messages.
- Notifications go only to users subscribed to the channel and not paused.

## Production

`production/docker-compose.yml` runs the image that `.github/workflows/docker-publish.yml` pushes to GHCR on `v*` tags. Variables resolve by Compose interpolation: host environment, then `production/.env`, then compose defaults. A new env var goes in that compose file (or it never reaches the container) and in both `example.env` templates; `test_env_parity.py` fails otherwise. Templates are named `example.env`, not `.env.example`, because organisation policy blocks agents from reading `.env.*`.

## Agent skills

### Issue tracker

Issues and specs live in GitHub Issues (`filippolmt/telegram-find-prices`), managed with `gh`. See `docs/agents/issue-tracker.md`.

### Triage labels

Default vocabulary: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `GLOSSARY.md` and `docs/adr/` at the repo root, created lazily. See `docs/agents/domain.md`.
