# Windows without make: run the command after the colon by hand, e.g.
#   docker compose exec server python -m app.sync yale
COLLECTION ?= yale

up:      ## build and start db + server + client
	docker compose up --build -d

sync:    ## make sync COLLECTION=yale
	docker compose exec server python -m app.sync $(COLLECTION)

test:    ## server unit + integration tests
	docker compose exec server pytest -q

golden:  ## AC-11 golden test set
	docker compose exec server python -m app.golden $(COLLECTION)

up-gpu:  ## NVIDIA GPU transcription (needs NVIDIA Container Toolkit)
	docker compose -f docker-compose.yml -f docker-compose.gpu.yml up --build -d

# Apple Silicon: Docker can't reach the Mac GPU, so the server runs natively (db + client stay in Docker).
# One-time: cd server && python3.12 -m venv .venv && .venv/bin/pip install -r requirements-mac.txt
#           && .venv/bin/crawl4ai-setup && brew install ffmpeg
# Native server uses the non-TLS password fallback: DB_AUTH=password + sslmode=disable so it
# matches the `host … scram-sha-256` rule in pg_hba.conf rather than the cert-only `hostssl` rule.
MAC_ENV = set -a && . ./.env && DB_AUTH=password DATABASE_URL="postgresql://mie:$$POSTGRES_PASSWORD@localhost:5437/mie?sslmode=disable" CONFIG_DIR=$(CURDIR)/config PROMPTS_DIR=$(CURDIR)/prompts GOLDEN_DIR=$(CURDIR)/golden && set +a

dev-mac:  ## Apple GPU: db + client in Docker, server native on :8003
	docker compose up -d --no-deps db client
	$(MAC_ENV) && cd server && .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8003

sync-mac:  ## make sync-mac COLLECTION=yale (while dev-mac is running)
	$(MAC_ENV) && cd server && .venv/bin/python -m app.sync $(COLLECTION)

logs:
	docker compose logs -f server

down:
	docker compose down

# ---- Helm (local kind cluster + localhost:5000 registry) ----
REGISTRY ?= localhost:5000
CHART    = charts/mie
RELEASE  ?= mie

helm-images:  ## build mie-server + mie-client (prod) and push to $(REGISTRY)
	docker build -t $(REGISTRY)/mie-server:latest ./server
	docker build --target prod -t $(REGISTRY)/mie-client:latest ./client
	docker push $(REGISTRY)/mie-server:latest
	docker push $(REGISTRY)/mie-client:latest

helm-sync:  ## copy config/ prompts/ golden/ pg_hba.conf into the chart (Helm can only read files under the chart dir)
	rm -rf $(CHART)/files/config $(CHART)/files/prompts $(CHART)/files/golden
	mkdir -p $(CHART)/files/config/collections $(CHART)/files/config/lenses $(CHART)/files/prompts $(CHART)/files/golden
	cp config/collections/*.yaml $(CHART)/files/config/collections/
	cp config/lenses/*.yaml      $(CHART)/files/config/lenses/
	cp prompts/*.md              $(CHART)/files/prompts/
	cp golden/*.yaml             $(CHART)/files/golden/
	cp postgres/pg_hba.conf      $(CHART)/files/pg_hba.conf

helm-install: helm-sync  ## install/upgrade with secrets from values-local.yaml (gitignored)
	helm upgrade --install $(RELEASE) $(CHART) -f $(CHART)/values-local.yaml

helm-lint: helm-sync  ## lint + render the chart (no cluster needed)
	helm lint $(CHART)
	helm template $(RELEASE) $(CHART) -f $(CHART)/values-local.yaml >/dev/null

.PHONY: up up-gpu dev-mac sync-mac sync test golden logs down helm-images helm-sync helm-install helm-lint
