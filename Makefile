.PHONY: setup demo-scan demo-down

setup:
	pre-commit install
	uv sync --locked

# ---------------------------------------------------------------------------
# Red team demo
# ---------------------------------------------------------------------------
# Usage:
#   make demo-scan API_KEY=<your-google-key> PROVIDER=google
#   make demo-scan API_KEY=<your-openai-key> PROVIDER=openai
#   make demo-scan API_KEY=<your-anthropic-key> PROVIDER=anthropic
#
# 1. Builds SmartPal in Docker
# 2. Starts the container
# 3. Discovers a JWT token from /demo/info
# 4. Injects the token into the redteam config
# 5. Runs snyk redteam against it
# 6. Tears down the container and temp files
CONTAINER_NAME := smartpal-demo
CONTAINER_PORT := 4000
CONFIG := redteaming/redteam.yaml
PROVIDER ?=
SNYK_CLI ?= snyk
ORG ?=
JSON_OUTPUT ?=
PROFILE ?=
SCAN_JSON := /tmp/redteam-results.json
SCAN_HTML := /tmp/redteam-report.html
EXTRA_CLI_FLAGS := $(if $(ORG),--org=$(ORG)) $(if $(PROFILE),--profile=$(PROFILE))

demo-scan:
	@test -n "$(API_KEY)" || { echo "Usage: make demo-scan API_KEY=your-api-key PROVIDER=google|openai|anthropic"; exit 1; }
	@test -n "$(PROVIDER)" || { echo "Usage: make demo-scan API_KEY=your-api-key PROVIDER=google|openai|anthropic"; exit 1; }
	@command -v $(SNYK_CLI) >/dev/null 2>&1 || { echo "ERROR: $(SNYK_CLI) not found. Install: https://docs.snyk.io/snyk-cli"; exit 1; }
	@echo "==> Building SmartPal..."
	@docker build -f Dockerfile -t $(CONTAINER_NAME) ./smartpal/backend
	@echo "==> Starting SmartPal (provider=$(PROVIDER))..."
	@docker rm -f $(CONTAINER_NAME) 2>/dev/null || true
	@SMARTPAL_API_KEY="$(API_KEY)" docker run -d --name $(CONTAINER_NAME) \
		-p $(CONTAINER_PORT):$(CONTAINER_PORT) \
		-e SMARTPAL_PROVIDER=$(PROVIDER) \
		-e SMARTPAL_API_KEY \
		$(CONTAINER_NAME)
	@echo "==> Waiting for healthy..."
	@for i in $$(seq 1 45); do \
		curl -sf http://localhost:$(CONTAINER_PORT)/health >/dev/null 2>&1 && break; \
		printf "."; sleep 1; \
	done; echo
	@curl -sf http://localhost:$(CONTAINER_PORT)/health >/dev/null 2>&1 || \
		{ echo "ERROR: SmartPal not healthy after 45s"; docker logs $(CONTAINER_NAME); \
		  docker stop $(CONTAINER_NAME) 2>/dev/null; docker rm $(CONTAINER_NAME) 2>/dev/null; exit 1; }
	@echo "==> Discovering JWT token..."
	@TOKEN=$$(curl -sf http://localhost:$(CONTAINER_PORT)/demo/info | \
		python3 -c "import sys,json; print(json.load(sys.stdin)['tokens'].get('Jane',''))") && \
		test -n "$$TOKEN" || { echo "ERROR: Could not discover JWT token"; \
		  docker stop $(CONTAINER_NAME) 2>/dev/null; docker rm $(CONTAINER_NAME) 2>/dev/null; exit 1; }; \
		sed "s|__TOKEN__|$$TOKEN|" $(CONFIG) > /tmp/redteam-run.yaml; \
		echo "==> Running $(SNYK_CLI) redteam..."; \
		$(SNYK_CLI) redteam --experimental \
			--config /tmp/redteam-run.yaml \
			--json-file-output=$(SCAN_JSON) \
			--html-file-output=$(SCAN_HTML) \
			$(EXTRA_CLI_FLAGS); \
		SCAN_EXIT=$$?; \
		rm -f /tmp/redteam-run.yaml; \
		echo ""; \
		echo "==> Tearing down..."; \
		docker stop $(CONTAINER_NAME) 2>/dev/null || true; \
		docker rm $(CONTAINER_NAME) 2>/dev/null || true; \
		echo ""; \
		if [ -f $(SCAN_JSON) ]; then \
			python3 redteaming/print-findings.py $(SCAN_JSON); \
		fi; \
		if [ -n "$(JSON_OUTPUT)" ] && [ -f $(SCAN_JSON) ]; then \
			cp $(SCAN_JSON) "$(JSON_OUTPUT)"; \
			echo "JSON results saved to $(JSON_OUTPUT)"; \
		fi; \
		if [ -f $(SCAN_HTML) ]; then \
			echo "==> Opening HTML report..."; \
			open $(SCAN_HTML) 2>/dev/null || xdg-open $(SCAN_HTML) 2>/dev/null || true; \
		fi; \
		rm -f $(SCAN_JSON); \
		exit $$SCAN_EXIT

demo-down:
	@docker stop $(CONTAINER_NAME) 2>/dev/null || true
	@docker rm $(CONTAINER_NAME) 2>/dev/null || true
	@rm -f /tmp/redteam-run.yaml
	@echo "Cleaned up."
