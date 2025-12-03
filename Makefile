PYTHON ?= python3.12
VENV ?= .venv
PIP := $(VENV)/bin/pip
PY := $(VENV)/bin/python
PLAYWRIGHT := $(VENV)/bin/playwright
UV := $(VENV)/bin/uv

.PHONY: setup install format lint test run collect fetch clean playwright

setup: $(VENV)/bin/activate
	@$(PIP) install --upgrade pip
	@$(PIP) install uv
	@$(UV) pip install .
	@$(PLAYWRIGHT) install --with-deps chromium

$(VENV)/bin/activate:
	$(PYTHON) -m venv $(VENV)

install:
	@$(PIP) install uv
	@$(UV) pip install .

format:
	@$(PY) -m ruff format src tests

lint:
	@$(PY) -m ruff check src tests

playwright:
	@$(PLAYWRIGHT) install --with-deps chromium

run: fetch

collect:
	@$(PY) -m src.main collect-links

fetch:
	@$(PY) -m src.main fetch-recipes

clean:
	rm -rf $(VENV) .pytest_cache __pycache__
	rm -rf data/output
	rm -rf state/*.json state/*.db
