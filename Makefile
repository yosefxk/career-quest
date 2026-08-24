.PHONY: help install test dev docker-build docker-up docker-down clean

help:
	@echo "CareerQuest Developer CLI"
	@echo "-------------------------"
	@echo "make install      - Install Python dependencies & Playwright"
	@echo "make test         - Run test suite with pytest"
	@echo "make dev          - Start local development server with hot-reload"
	@echo "make docker-build - Build Docker container image"
	@echo "make docker-up    - Launch Docker stack in background"
	@echo "make docker-down  - Stop Docker stack"
	@echo "make clean        - Remove Python bytecode and temporary caches"

install:
	pip install -r backend/requirements.txt
	playwright install chromium --with-deps

test:
	pytest -v backend/tests

dev:
	uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8099 --reload

docker-build:
	docker compose build

docker-up:
	docker compose up -d

docker-down:
	docker compose down

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache
