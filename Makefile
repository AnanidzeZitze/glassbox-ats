.PHONY: help test build dev-backend dev-frontend docker-up docker-down clean

help:
	@echo "Glass-Box ATS Simulator & Optimization Studio — Developer Commands"
	@echo "  make test          Run all 24 backend unit, benchmark, and API integration tests"
	@echo "  make build         Build the Next.js frontend studio for production"
	@echo "  make dev-backend   Start the FastAPI backend server on http://localhost:8000"
	@echo "  make dev-frontend  Start the Next.js frontend studio on http://localhost:3000"
	@echo "  make docker-up     Build and start PostgreSQL 16 (pgvector), Backend, and Frontend"
	@echo "  make docker-down   Stop all Docker Compose containers"

test:
	.venv/bin/pytest backend/tests/ -v

build:
	cd frontend && npm run build

dev-backend:
	.venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload

dev-frontend:
	cd frontend && npm run dev -- -p 3000

docker-up:
	docker compose up --build -d

docker-down:
	docker compose down

clean:
	rm -rf .pytest_cache frontend/.next
