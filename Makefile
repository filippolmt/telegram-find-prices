.PHONY: build run run-d auth gen-session test test-v test-one lint hooks live-check dump-posts replay shell logs stop clean

# Build Docker image (only when dependencies change)
build:
	docker compose build

# Start the bot
run: build
	docker compose up

# Start the bot in background
run-d: build
	docker compose up -d

# First-time Telegram client authentication (interactive, one-time only)
auth:
	docker compose run --rm -it test python src/auth.py

# Generate StringSession for production (interactive, one-time only)
gen-session:
	docker compose run --rm -it test python src/generate_string_session.py

# Run all tests (src/ and tests/ mounted as volumes, no rebuild)
test:
	docker compose run --rm test

# Run tests with verbose output
test-v:
	docker compose run --rm test pytest tests/ -v

# Run a single test (e.g.: make test-one T=tests/test_models.py::test_create_user)
test-one:
	docker compose run --rm test pytest $(T) -v

# Lint with ruff (rebuild the image after dependency changes: make build)
lint:
	docker compose run --rm test ruff check src tests

# Enable the repo's git hooks (pre-commit: ruff), once per clone
hooks:
	git config core.hooksPath .githooks

# Run real channel messages through Backfill and Realtime (throwaway DB, notifications printed, nothing sent).
# The bot is paused meanwhile: one session must never run in two processes at once.
# e.g.: make live-check ARGS='--channel pallok --product "Ninja Blast" --product "NUTILIS CLEAR=20" --product "oral-b#B0CXYZ1234=30"'
live-check:
	docker compose stop bot
	docker compose run --rm -T test python src/live_check.py $(ARGS); status=$$?; docker compose up -d bot; exit $$status

# Save recent posts of the followed channels to data/posts.json for make replay (bot paused, like live-check).
# e.g.: make dump-posts ARGS='--limit 300 --channel pallok'
dump-posts:
	docker compose stop bot
	docker compose run --rm -T test python src/replay.py dump $(ARGS); status=$$?; docker compose up -d bot; exit $$status

# Prices that change between a git ref (default main) and the working tree, over data/posts.json (native: needs git and uv).
# e.g.: make replay BASE=v1.0.0 ARGS='--samples 20'
replay:
	uv run python src/replay.py diff --base $(or $(BASE),main) $(ARGS)

# Shell inside the container
shell:
	docker compose run --rm test bash

# View bot logs
logs:
	docker compose logs -f bot

# Stop containers
stop:
	docker compose down

# Clean up images and containers
clean:
	docker compose down --rmi local --volumes
