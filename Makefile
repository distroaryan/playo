# ──────────────────────────────────────────────────────────────
# Playto — Local Development Makefile
# ──────────────────────────────────────────────────────────────

# Default shell
SHELL := powershell.exe
.SHELLFLAGS := -NoProfile -Command

# ─── Database Services (PostgreSQL + Redis) ──────────────────
.PHONY: db-start db-stop db-logs

db-start: ## Start PostgreSQL and Redis containers (detached)
	docker compose -f docker-compose.dev.yml up -d

db-stop: ## Stop PostgreSQL and Redis containers
	docker compose -f docker-compose.dev.yml down

db-logs: ## Tail logs from database containers
	docker compose -f docker-compose.dev.yml logs -f

# ─── Django Backend ──────────────────────────────────────────
.PHONY: server migrate seed

server: ## Start the Django development server
	python manage.py runserver

migrate: ## Run Django database migrations
	python manage.py migrate

seed: ## Seed the database with test data
	python seed.py

# ─── Celery ──────────────────────────────────────────────────
.PHONY: celery-worker celery-beat flower

celery-worker: ## Start Celery worker (solo pool for Windows)
	celery -A playto worker --loglevel=info -P solo

celery-beat: ## Start Celery Beat scheduler
	celery -A playto beat --loglevel=info

flower: ## Start Celery Flower monitoring dashboard (port 5555)
	celery -A playto flower --port=5555

# ─── React Frontend ──────────────────────────────────────────
.PHONY: frontend frontend-install

frontend-install: ## Install frontend dependencies
	cd web && npm install

frontend: ## Start the React (Vite) dev server
	cd web && npm run dev

# ─── Full Docker Stack ───────────────────────────────────────
.PHONY: docker-up docker-down docker-build docker-logs

docker-up: ## Start all 7 containers (full stack)
	docker compose up -d

docker-down: ## Stop all containers
	docker compose down

docker-build: ## Rebuild all Docker images
	docker compose build --no-cache

docker-logs: ## Tail logs from all containers
	docker compose logs -f

# ─── Utilities ───────────────────────────────────────────────
.PHONY: test test-load clean help

test: ## Run Django test suite
	python manage.py test api

test-load: ## Run k6 load test for throughput and latency evaluation
	k6 run k6_load_test.js

clean: ## Remove Docker volumes and stopped containers
	docker compose down -v
	docker compose -f docker-compose.dev.yml down -v

help: ## Show this help message
	@echo ""
	@echo "  Playto Payout Engine — Available Commands"
	@echo "  =========================================="
	@echo ""
	@Select-String -Path Makefile -Pattern '^\w+:.*##' | ForEach-Object { $$match = $$_.Line -match '^(\S+):.*##\s*(.+)'; if ($$match) { "  make {0,-20} {1}" -f $$Matches[1], $$Matches[2] } }
	@echo ""
