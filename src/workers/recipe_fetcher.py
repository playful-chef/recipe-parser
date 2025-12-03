from __future__ import annotations

import asyncio
from typing import Sequence

import httpx

from ..core.config import FetcherSettings
from ..core.logging import get_logger
from ..core.writer import ResultWriter
from ..parsers.recipe_parser import parse_recipe
from ..storage.link_store import LinkStore

LOGGER = get_logger(__name__)


class RecipeFetcher:
    def __init__(self, settings: FetcherSettings, store: LinkStore) -> None:
        self.settings = settings
        self.store = store
        self.writer = ResultWriter(
            settings.app.output_file,
            jsonl_path=settings.app.jsonl_file,
            flush_threshold=settings.flush_threshold,
            link_store=store,
        )
        self._sem = asyncio.Semaphore(settings.http_concurrency)
        self._processed = 0
        self._progress_lock = asyncio.Lock()
        self._progress_interval = max(1, settings.progress_interval)

    async def run(self) -> None:
        self.settings.ensure_dirs()
        async with httpx.AsyncClient(timeout=self.settings.http_timeout, headers=self._headers()) as client:
            try:
                while True:
                    batch = await asyncio.to_thread(
                        self.store.lease_batch, self.settings.batch_size, self.settings.lease_seconds
                    )
                    if not batch:
                        await asyncio.sleep(2.0)
                        continue
                    await self._process_batch(client, batch)
            finally:
                await self.writer.finalize()

    async def _process_batch(self, client: httpx.AsyncClient, batch: Sequence[str]) -> None:
        tasks = [asyncio.create_task(self._process_url(client, url)) for url in batch]
        await asyncio.gather(*tasks)

    async def _process_url(self, client: httpx.AsyncClient, url: str) -> None:
        async with self._sem:
            try:
                html = await self._fetch_html(client, url)
                record = parse_recipe(html, url)
                if not record:
                    raise ValueError("Recipe payload missing required fields")
                await self.writer.append(record)
                await asyncio.to_thread(self.store.ack_success, url)
                await self._record_progress(url)
            except Exception as exc:
                LOGGER.warning("Failed to parse %s: %s", url, exc)
                await asyncio.to_thread(self.store.ack_fail, url, str(exc), self.settings.max_failures)

    async def _fetch_html(self, client: httpx.AsyncClient, url: str) -> str:
        backoff = 1.0
        for attempt in range(1, self.settings.max_failures + 1):
            try:
                response = await client.get(url)
                response.raise_for_status()
                return response.text
            except httpx.HTTPError as exc:
                LOGGER.debug("HTTP error (%s) on %s attempt %s", exc, url, attempt)
                if attempt >= self.settings.max_failures:
                    raise
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 10)
        raise RuntimeError("Unreachable retry loop")

    def _headers(self) -> dict[str, str]:
        return {
            "User-Agent": self.settings.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ru,en;q=0.9",
        }

    async def _record_progress(self, url: str) -> None:
        async with self._progress_lock:
            self._processed += 1
            if self._processed % self._progress_interval == 0:
                LOGGER.warning(
                    "Parsed %s recipes so far (latest: %s)",
                    self._processed,
                    url,
                )


