# 1000.menu Dual-Worker Scraper

Headless scraper that exports high-quality recipe datasets from 1000.menu. The project focuses on dependable long‑running crawls: a Playwright collector keeps paginating the public search page, while an async HTTP fetcher parses each unique recipe only once and writes structured TSV/JSONL output.

See `docs/README.md` for the full architecture notes; this document concentrates on the why/how of running it.

## What You Get
- **Browser-grade discovery** – real Chromium session clicks “Показать ещё результаты…” so the dataset matches what a human sees.
- **HTTP-speed parsing** – recipes are fetched with `httpx` + `selectolax`, stripping ads/HTML leftovers and emitting nutrition data.
- **Exactly-once semantics** – SQLite queue (pending/leased/processed/failed) plus file writers keep outputs deduplicated even across crashes.
- **Operational milestones** – collectors log every 2 000 unique links; fetchers log every 200 parsed recipes so you can monitor with `LOG_LEVEL=WARNING`.

## Deploying the Scraper

### Local development (uv-powered)
```bash
git clone https://github.com/playful-chef/recipe-parser.git
cd recipe-parser
make setup          # creates .venv, installs deps via uv, installs Chromium

# Terminal 1 – discover links
.venv/bin/python -m src.main collect-links \
  --mode browser \
  --click-delay 0.05 \
  --scroll-pause 0.01

# Terminal 2 – fetch + parse
.venv/bin/python -m src.main fetch-recipes \
  --output-file data/output/recipes.tsv \
  --jsonl-file data/output/recipes.jsonl \
  --flush-size 500
```

Both workers can be restarted independently; state lives under `state/`.

### Docker Compose (recommended for production runs)
```bash
# build uv-based image
docker compose build

# start both workers in parallel
docker compose up -d collector fetcher

# follow progress at log level WARNING
docker compose logs -f collector fetcher

# clean stop + wipe state volume
docker compose down -v
```
`data/` is bind-mounted to the host so TSV/JSONL files update live; the SQLite queue sits in the named volume `state-data` and survives container restarts unless you pass `-v`.

### Clean restarts
If you need a fully fresh crawl:
```bash
docker compose down -v
rm -rf data/output state/collector_state.json
mkdir -p data/output state && touch data/.gitkeep state/.gitkeep
docker compose up -d collector fetcher
```

## Runtime Artifacts
- `data/output/recipes.tsv` – canonical dataset with headers; each row carries full text, nutrition, and metadata fields.
- `data/output/recipes.jsonl` – optional mirroring of every record for streaming ingestion.
- `state/workqueue.db` – queue plus per-link attempts.
- `state/collector_state.json` – remembers how many “load more” clicks already happened to resume pagination.

## Tips & Troubleshooting
- **Timeout warnings** – tune `--results-wait-timeout` (or `SCRAPER_RESULTS_WAIT_TIMEOUT`) so Playwright waits long enough after each click.
- **Collector stuck?** – run `collect-links --mode http` to fall back to the AJAX endpoint; the queue prevents duplicate processing.
- **Throttling** – reduce `--click-delay`, `--scroll-pause`, or `--http-concurrency` if the site pushes back; increase when you need throughput.
- **Milestones show duplicates?** – the collector only increments progress when `LinkStore.add_links` reports new unique URLs, so repeated warnings usually point to slow link growth rather than logging errors.
- **Need deeper internals?** – read `docs/README.md` for a component breakdown, diagrams, and extension ideas.

## Contributing & Testing
```bash
.venv/bin/python -m pytest
.venv/bin/python -m ruff format src tests
.venv/bin/python -m ruff check src tests
```

The repository is structured for long-lived scrapes; prefer incremental tuning (via config) over editing worker code unless you are changing site logic. Pull requests that improve parsing accuracy, monitoring, or deployment ergonomics are welcome.