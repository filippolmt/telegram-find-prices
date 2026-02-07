.PHONY: build run auth test test-v stop logs clean shell

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
	docker compose run --rm -it test uv run python src/auth.py

# Run all tests (src/ and tests/ mounted as volumes, no rebuild)
test:
	docker compose run --rm test

# Run tests with verbose output
test-v:
	docker compose run --rm test uv run pytest tests/ -v

# Run a single test (e.g.: make test-one T=tests/test_models.py::test_create_user)
test-one:
	docker compose run --rm test uv run pytest $(T) -v

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
