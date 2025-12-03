# 1000.menu Dual-Worker Scraper

High-volume 1000.menu scraper built around two cooperative workers:

1. **Link collector** – a lightweight Playwright session that sits on the public search page, keeps pressing “Показать еще результаты поиска…”, and sends every discovered recipe URL into a persistent queue.
2. **Recipe fetcher** – a fast `httpx` client that pops URLs from the queue, fetches them without spinning up a browser, parses the HTML with `selectolax`, and writes structured rows every 500 recipes.

The pipeline is fault tolerant (SQLite-backed queue, resumable collector state, duplicate suppression) and exports a nutrition-rich TSV/JSONL payload optimized for downstream analytics.

## Quick start
```bash
cd /Users/Bogodist/parsing_for_uni
make setup                       # venv, deps, Chromium for the collector

# Terminal 1 – keep discovering recipe links
.venv/bin/python -m src.main collect-links --max-clicks 50

# Terminal 2 – drain the queue and emit recipes every 500 rows
.venv/bin/python -m src.main fetch-recipes \
  --output-file data/output/recipes.tsv \
  --jsonl-file data/output/recipes.jsonl
```

Both commands can run indefinitely; stop/restart them at will. Progress lives in:

- `state/workqueue.db` – SQLite queue (`pending`, `leased`, `processed`, `failed`)
- `state/collector_state.json` – remembers how many “load more” clicks have already been replayed
- `data/output/recipes.tsv` (+ optional JSONL mirror)

## CLI overview

| Command | Description |
| --- | --- |
| `python -m src.main collect-links` | Launches Playwright (headless by default), opens the search page, keeps clicking “Показать еще результаты…” and pushes canonical recipe URLs into the queue. |
| `python -m src.main fetch-recipes` | Uses async `httpx` to fetch/parse recipe pages in parallel, exporting batched TSV/JSONL rows every `--flush-size` recipes while acknowledging URLs in the queue. |

### Common options
| Flag / env | Meaning | Default |
| --- | --- | --- |
| `--base-url`, `SCRAPER_BASE_URL` | Site root | `https://1000.menu` |
| `--search-path`, `SCRAPER_SEARCH_PATH` | Search endpoint used by the collector | `/cooking/search?ms=1&str=&es_tf=0&es_tt=14&es_cf=0&es_ct=2000` |
| `--state-dir`, `SCRAPER_STATE_DIR` | Persistent state directory | `state/` |
| `--output-file`, `SCRAPER_OUTPUT_FILE` | TSV target (parent directory becomes `data_dir`) | `data/output/recipes.tsv` |
| `--jsonl-file`, `SCRAPER_JSONL_FILE` | Optional JSONL mirror | unset |
| `--progress-interval`, `SCRAPER_PROGRESS_INTERVAL` | Log every N parsed recipes (fetcher) | `200` |

### Collector highlights
- `--max-clicks` caps how many **new** “load more” clicks happen per run (defaults to infinite).
- `--click-delay` and `--scroll-pause` keep things polite for the site.
- Resuming a stopped collector replays the previously completed click count so pagination state stays consistent; duplicates are ignored by the queue.
- `--mode auto|browser|http` lets you force a strategy. `auto` (default) tries Playwright first but automatically falls back to an HTTP paginator that scrapes the same AJAX endpoints the “Показать ещё результаты…” button uses—handy when the UI page gets stuck on a perpetual loader inside slower environments (Docker, CI, etc.).

### Fetcher highlights
- `--batch-size` controls how many URLs are leased from the queue at a time (default 20).
- `--http-concurrency` limits the number of simultaneous downloads (default 8).
- `--flush-size` controls how many parsed recipes are buffered before being written (default 500).
- `--progress-interval` (200 by default) prints a milestone log plus a flush summary every time that many recipes have been parsed—handy for long unattended runs even at higher log levels such as WARNING.
- `--max-failures` determines how many times a URL is retried before it’s moved to the `failed` bucket.

## Data schema (`data/output/recipes.tsv`)
The TSV writer adds headers once and appends batches of 500 rows:

1. `title`
2. `instructions` (newline-separated steps)
3. `ingredients` (comma-separated list)
4. `url`
5. `description`
6. `author`
7. `total_time`
8. `servings`
9. `calories`
10. `rating_value`
11. `rating_count`
12. `categories` (breadcrumb trail without “Главная”)
13. `equipment`
14. `tags`
15. `image`
16. `captured_at` (UTC ISO-8601)
17. `protein_percent`
18. `protein_grams`
19. `fat_percent`
20. `fat_grams`
21. `carb_percent`
22. `carb_grams`
23. `calories_per_100g`
24. `calories_total` (derived from total weight + per‑100g kcal)
25. `gi_min`
26. `gi_avg`
27. `gi_max`
28. `total_weight_grams`

Nutrition fields are parsed from the “Нутриенты и калорийность состава рецепта” widget (per 100 g by default) and mirrored in JSONL outputs. Already-exported URLs are checked via the queue before writing, guaranteeing idempotent reruns even if TSV files are deleted.

## Testing & linting
```bash
.venv/bin/python -m pytest          # unit tests + parser fixtures
.venv/bin/python -m ruff format src tests
.venv/bin/python -m ruff check src tests
```

## Docker / Compose
Launch both workers together with Docker Compose (the `data/` directory is bind-mounted so TSV/JSONL files stay on the host, while the SQLite queue lives inside a persistent named volume for durability). The default `LOG_LEVEL` inside the containers is `WARNING`, so you will mainly see milestone entries (flush + progress) instead of every HTTP call:
```bash
# build the image once
docker compose build

# run both workers in parallel (detached)
docker compose up -d collector fetcher

# follow logs if needed
docker compose logs -f collector fetcher

# stop everything
docker compose down
```
The state volume is called `parsing_for_uni_state-data`; inspect it with `docker compose exec collector ls /app/state` or `docker compose exec fetcher python -m sqlite3 /app/state/workqueue.db ...`.

## Operational notes
- Respect 1000.menu’s robots.txt; keep `--click-delay`, `--scroll-pause`, and `--http-concurrency` conservative for long crawls.
- The queue guarantees “exactly once” writing: processed URLs are never re-fetched, failed ones are retried with exponential backoff, and everything is crash-safe thanks to SQLite + JSON checkpoints.
- Clearing state for a clean run is as simple as deleting `state/workqueue.db` and `state/collector_state.json`.
- If the search page refuses to finish loading in a headless browser, rerun `collect-links` with `--mode http` to iterate directly over the `/ajax/free/search_page` endpoint until no more cards are returned.


