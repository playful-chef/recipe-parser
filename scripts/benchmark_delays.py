from __future__ import annotations

import argparse
import asyncio
import tempfile
import time
from pathlib import Path

from src.core.config import AppPaths, CollectorMode, CollectorSettings
from src.core.logging import configure_logging
from src.storage.link_store import LinkStore
from src.workers.link_collector import LinkCollector


def _parse_floats(raw: str) -> list[float]:
    return [float(chunk.strip()) for chunk in raw.split(",") if chunk.strip()]


async def run_once(
    click_delay: float,
    scroll_pause: float,
    max_clicks: int,
    base_url: str,
    search_path: str,
    headless: bool,
) -> tuple[int, float]:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        data_dir = tmp_path / "data"
        state_dir = tmp_path / "state"
        data_dir.mkdir(parents=True, exist_ok=True)
        state_dir.mkdir(parents=True, exist_ok=True)

        paths = AppPaths(
            base_url=base_url,
            search_path=search_path,
            data_dir=data_dir,
            state_dir=state_dir,
            output_file=data_dir / "recipes.tsv",
        )
        settings = CollectorSettings(
            app=paths,
            click_delay=click_delay,
            scroll_pause=scroll_pause,
            max_clicks=max_clicks,
            progress_interval=0,
            headless=headless,
            mode=CollectorMode.BROWSER,
        )
        store = LinkStore(paths.queue_db)
        collector = LinkCollector(settings, store)

        started = time.perf_counter()
        try:
            await collector.run()
        finally:
            elapsed = time.perf_counter() - started
            stats = store.stats()
            total_links = sum(stats.values())
            store.close()

    return total_links, elapsed


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark collector click/scroll delays.")
    parser.add_argument("--click-delays", default="0.1,0.3,0.5", help="Comma-separated values (seconds)")
    parser.add_argument("--scroll-pauses", default="0.05,0.1", help="Comma-separated values (seconds)")
    parser.add_argument("--max-clicks", type=int, default=5, help="Clicks per benchmark run")
    parser.add_argument("--base-url", default="https://1000.menu")
    parser.add_argument(
        "--search-path",
        default="/cooking/search?ms=1&str=&es_tf=0&es_tt=14&es_cf=0&es_ct=2000",
    )
    parser.add_argument("--headed", action="store_true", help="Run Chromium with UI (default headless)")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    configure_logging(args.log_level)

    clicks = _parse_floats(args.click_delays)
    pauses = _parse_floats(args.scroll_pauses)
    if not clicks or not pauses:
        raise SystemExit("Provide at least one click delay and scroll pause.")

    print(f"Benchmarking {len(clicks) * len(pauses)} combinations (max_clicks={args.max_clicks})")
    for click_delay in clicks:
        for scroll_pause in pauses:
            total, elapsed = asyncio.run(
                run_once(
                    click_delay=click_delay,
                    scroll_pause=scroll_pause,
                    max_clicks=args.max_clicks,
                    base_url=args.base_url,
                    search_path=args.search_path,
                    headless=not args.headed,
                )
            )
            rate = total / elapsed if elapsed else 0.0
            print(
                f"click={click_delay:.2f}s scroll={scroll_pause:.2f}s -> "
                f"{total} links in {elapsed:.1f}s ({rate:.1f} links/s)"
            )


if __name__ == "__main__":
    main()

