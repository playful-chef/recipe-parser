from __future__ import annotations

import asyncio
import tempfile
import time
from pathlib import Path
from typing import Annotated, Optional

import typer

from .core.config import AppPaths, CollectorMode, CollectorSettings, FetcherSettings
from .core.logging import configure_logging
from .storage.link_store import LinkStore
from .workers.link_collector import LinkCollector
from .workers.recipe_fetcher import RecipeFetcher

app = typer.Typer(add_completion=False, help="1000.menu dual-worker scraper")


def _build_paths(
    base_url: str,
    search_path: str,
    output_file: Path,
    state_dir: Path,
    jsonl_file: Optional[Path],
) -> AppPaths:
    return AppPaths(
        base_url=base_url,
        search_path=search_path,
        data_dir=output_file.parent,
        state_dir=state_dir,
        output_file=output_file,
        jsonl_file=jsonl_file,
    )


@app.command("collect-links")
def collect_links(
    base_url: Annotated[str, typer.Option(envvar="SCRAPER_BASE_URL")] = "https://1000.menu",
    search_path: Annotated[
        str,
        typer.Option(envvar="SCRAPER_SEARCH_PATH", help="Search path with query params"),
    ] = "/cooking/search?ms=1&str=&es_tf=0&es_tt=14&es_cf=0&es_ct=2000",
    state_dir: Annotated[Path, typer.Option(envvar="SCRAPER_STATE_DIR")] = Path("state"),
    output_file: Annotated[Path, typer.Option(envvar="SCRAPER_OUTPUT_FILE")] = Path(
        "data/output/recipes.tsv"
    ),
    click_delay: Annotated[float, typer.Option(help="Sleep after clicking load-more")] = 1.0,
    scroll_pause: Annotated[float, typer.Option(help="Extra wait for DOM updates")] = 0.5,
    max_clicks: Annotated[
        Optional[int],
        typer.Option(help="Stop after N new load-more clicks (per run)"),
    ] = None,
    progress_interval: Annotated[
        int,
        typer.Option(
            envvar="SCRAPER_COLLECTOR_PROGRESS_INTERVAL",
            help="Log milestone after this many discovered links",
        ),
    ] = 200,
    headless: Annotated[bool, typer.Option("--headless/--headed")] = True,
    slow_mo: Annotated[
        Optional[int],
        typer.Option(envvar="SCRAPER_SLOW_MO", help="Optional Playwright slow-mo"),
    ] = None,
    mode: Annotated[
        CollectorMode,
        typer.Option(
            case_sensitive=False,
            help="collector strategy: auto (default), browser, or http",
        ),
    ] = CollectorMode.AUTO,
    results_wait_timeout: Annotated[
        float,
        typer.Option(
            envvar="SCRAPER_RESULTS_WAIT_TIMEOUT",
            help="Max seconds to wait for DOM growth after clicking load-more",
        ),
    ] = 8.0,
    http_timeout: Annotated[
        float,
        typer.Option(
            help="HTTP fallback timeout (seconds)",
            envvar="SCRAPER_COLLECTOR_HTTP_TIMEOUT",
        ),
    ] = 30.0,
    jsonl_file: Annotated[
        Optional[Path],
        typer.Option(envvar="SCRAPER_JSONL_FILE", help="JSONL mirror path (used by fetcher)"),
    ] = None,
    log_level: Annotated[str, typer.Option(envvar="LOG_LEVEL")] = "INFO",
) -> None:
    """Discover recipe URLs by clicking the search paginator."""

    configure_logging(log_level)
    paths = _build_paths(base_url, search_path, output_file, state_dir, jsonl_file)
    settings = CollectorSettings(
        app=paths,
        click_delay=click_delay,
        scroll_pause=scroll_pause,
        max_clicks=max_clicks,
        progress_interval=progress_interval,
        headless=headless,
        slow_mo_ms=slow_mo,
        mode=mode,
        results_wait_timeout=results_wait_timeout,
        http_timeout=http_timeout,
    )
    store = LinkStore(paths.queue_db)
    collector = LinkCollector(settings, store)
    try:
        asyncio.run(collector.run())
    finally:
        store.close()


@app.command("fetch-recipes")
def fetch_recipes(
    base_url: Annotated[str, typer.Option(envvar="SCRAPER_BASE_URL")] = "https://1000.menu",
    search_path: Annotated[
        str,
        typer.Option(envvar="SCRAPER_SEARCH_PATH", help="Used for documentation only"),
    ] = "/cooking/search?ms=1&str=&es_tf=0&es_tt=14&es_cf=0&es_ct=2000",
    state_dir: Annotated[Path, typer.Option(envvar="SCRAPER_STATE_DIR")] = Path("state"),
    output_file: Annotated[Path, typer.Option(envvar="SCRAPER_OUTPUT_FILE")] = Path(
        "data/output/recipes.tsv"
    ),
    jsonl_file: Annotated[
        Optional[Path],
        typer.Option(envvar="SCRAPER_JSONL_FILE", help="Optional JSONL mirror"),
    ] = None,
    batch_size: Annotated[int, typer.Option(envvar="SCRAPER_BATCH_SIZE")] = 200,
    http_concurrency: Annotated[int, typer.Option(envvar="SCRAPER_HTTP_CONCURRENCY")] = 16,
    http_timeout: Annotated[float, typer.Option(envvar="SCRAPER_HTTP_TIMEOUT")] = 25.0,
    flush_size: Annotated[int, typer.Option(envvar="SCRAPER_FLUSH_SIZE")] = 500,
    progress_interval: Annotated[
        int,
        typer.Option(
            envvar="SCRAPER_PROGRESS_INTERVAL",
            help="Log milestone after this many parsed recipes",
        ),
    ] = 200,
    max_failures: Annotated[int, typer.Option(envvar="SCRAPER_MAX_FAILURES")] = 5,
    lease_seconds: Annotated[float, typer.Option(envvar="SCRAPER_LEASE_SECONDS")] = 900.0,
    log_level: Annotated[str, typer.Option(envvar="LOG_LEVEL")] = "INFO",
) -> None:
    """Fetch recipe pages via HTTP requests and export them in batches."""

    configure_logging(log_level)
    paths = _build_paths(base_url, search_path, output_file, state_dir, jsonl_file)
    settings = FetcherSettings(
        app=paths,
        batch_size=batch_size,
        http_concurrency=http_concurrency,
        http_timeout=http_timeout,
        flush_threshold=flush_size,
        progress_interval=progress_interval,
        max_failures=max_failures,
        lease_seconds=lease_seconds,
    )
    store = LinkStore(paths.queue_db)
    fetcher = RecipeFetcher(settings, store)
    try:
        asyncio.run(fetcher.run())
    finally:
        store.close()


if __name__ == "__main__":
    app()

