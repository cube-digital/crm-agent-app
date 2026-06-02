.PHONY: help up down logs psql falkor-cli build reset

help:
	@echo "Targets:"
	@echo "  up         Start the compose stack (postgres + falkordb + your app)"
	@echo "  down       Stop everything"
	@echo "  logs       Follow logs from the app container"
	@echo "  psql       Open a psql shell on the (empty by default) postgres"
	@echo "  falkor-cli Open a redis-cli shell on FalkorDB (use GRAPH.QUERY ...)"
	@echo "  build      Rebuild the app image (you write the Dockerfile)"
	@echo "  reset      Stop and wipe all volumes — fresh start"

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f app

psql:
	docker compose exec postgres psql -U $${POSTGRES_USER:-crm} -d $${POSTGRES_DB:-crm}

falkor-cli:
	docker compose exec falkordb redis-cli

build:
	docker compose build

reset:
	docker compose down -v
