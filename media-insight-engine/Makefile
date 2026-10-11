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

logs:
	docker compose logs -f server

down:
	docker compose down

.PHONY: up sync test golden logs down
