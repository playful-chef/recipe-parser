from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
import re
from pathlib import Path
from typing import Iterable, Sequence
from urllib.parse import parse_qsl, urljoin, urlparse, urlunparse, urlencode

import httpx
from playwright.async_api import Error as PlaywrightError, async_playwright
from selectolax.parser import HTMLParser

from ..core.config import CollectorMode, CollectorSettings
from ..core.logging import get_logger
from ..core.normalization import normalize_url
from ..storage.link_store import LinkStore

LOGGER = get_logger(__name__)
NEXT_PAGE_RE = re.compile(r"cook_load_next_page_html\('([^']+)'")
CARD_SELECTORS = "#recipes a.h5[href], .cn-item a.h5[href], a.recipe-card[href]"


@dataclass(slots=True)
class CollectorState:
    path: Path
    clicks_completed: int = 0

    def load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self.clicks_completed = int(data.get("clicks_completed", 0))
        except (json.JSONDecodeError, ValueError):
            LOGGER.warning("Could not parse collector state, starting fresh")
            self.clicks_completed = 0

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"clicks_completed": self.clicks_completed}
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)


class LinkCollector:
    def __init__(self, settings: CollectorSettings, store: LinkStore) -> None:
        self.settings = settings
        self.store = store
        host = urlparse(self.settings.app.base_url).netloc
        self.allowed_hosts = {host, f"www.{host}"}
        self.state = CollectorState(self.settings.app.collector_state_file)
        self.state.load()
        self._collected_links = 0
        self._progress_interval = (
            self.settings.progress_interval if self.settings.progress_interval and self.settings.progress_interval > 0 else None
        )
        self._last_progress_bucket = 0

    async def run(self) -> None:
        self.settings.ensure_dirs()
        should_try_browser = self.settings.mode in (CollectorMode.AUTO, CollectorMode.BROWSER)
        if should_try_browser:
            try:
                await self._run_browser_mode()
                return
            except Exception as exc:
                if self.settings.mode == CollectorMode.BROWSER:
                    raise
                LOGGER.warning("Browser mode failed (%s). Falling back to HTTP fetching.", exc)
        await self._run_http_mode()

    async def _run_browser_mode(self) -> None:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(
                headless=self.settings.headless,
                slow_mo=self.settings.slow_mo_ms or 0,
            )
            page = await browser.new_page()
            try:
                await page.goto(self.settings.app.search_url(), wait_until="domcontentloaded")
                await self._collect_links_from_dom(page)
                if self.state.clicks_completed:
                    LOGGER.info("Replaying %s previous clicks to resume", self.state.clicks_completed)
                    await self._replay_clicks(page, self.state.clicks_completed)
                await self._consume_new_pages(page)
            finally:
                await browser.close()

    async def _replay_clicks(self, page, count: int) -> None:
        for _ in range(count):
            success = await self._load_more(page)
            if not success:
                LOGGER.warning("Unable to replay historical clicks; button missing")
                break
            await self._collect_links_from_dom(page)

    async def _consume_new_pages(self, page) -> None:
        performed = 0
        limit = self.settings.max_clicks
        while True:
            if limit is not None and performed >= limit:
                LOGGER.info("Reached configured click limit (%s)", limit)
                break
            success = await self._load_more(page)
            if not success:
                LOGGER.info("No further pages available")
                break
            performed += 1
            self.state.clicks_completed += 1
            self.state.save()
            await self._collect_links_from_dom(page)

    async def _load_more(self, page) -> bool:
        button = page.locator("button:has-text('Показать еще результаты')")
        if await button.count() == 0:
            return False
        before_length = await self._content_length(page)
        if self.settings.click_delay:
            await asyncio.sleep(self.settings.click_delay)
        try:
            await button.first.click()
        except PlaywrightError as exc:
            LOGGER.warning("Failed to click next page button: %s", exc)
            return False
        if self.settings.scroll_pause:
            await asyncio.sleep(self.settings.scroll_pause)
        if not await self._wait_for_results_growth(page, before_length):
            LOGGER.warning("Timeout waiting for additional search results")
            return False
        return True

    async def _content_length(self, page) -> int:
        try:
            return await page.eval_on_selector_all(
                CARD_SELECTORS,
                "nodes => nodes.length",
            )
        except PlaywrightError:
            return 0

    async def _wait_for_results_growth(self, page, previous_length: int) -> bool:
        loop = asyncio.get_running_loop()
        timeout = max(0.5, self.settings.results_wait_timeout)
        poll_interval = max(0.05, self.settings.results_poll_interval)
        deadline = loop.time() + timeout
        while True:
            current_length = await self._content_length(page)
            if current_length > previous_length:
                LOGGER.debug(
                    "Detected growth in search results (%s -> %s)",
                    previous_length,
                    current_length,
                )
                return True
            remaining = deadline - loop.time()
            if remaining <= 0:
                break
            await asyncio.sleep(min(poll_interval, remaining))
        return False

    async def _collect_links_from_dom(self, page) -> None:
        anchors = await page.eval_on_selector_all(
            CARD_SELECTORS,
            "nodes => nodes.map(node => node.getAttribute('href'))",
        )
        self._store_links(anchors)

    async def _run_http_mode(self) -> None:
        LOGGER.info("Using HTTP collector mode")
        async with httpx.AsyncClient(
            headers=self._default_headers(), timeout=self.settings.http_timeout
        ) as client:
            page_num = 1
            ajax_template: str | None = None
            iterations = 0
            while True:
                if page_num == 1:
                    target_url = self.settings.app.search_url()
                else:
                    if not ajax_template:
                        LOGGER.info("No AJAX template available; stopping HTTP pagination")
                        break
                    target_url = build_ajax_url(ajax_template, self.settings.app.base_url, page_num)
                LOGGER.debug("HTTP collector fetching %s", target_url)
                try:
                    response = await client.get(target_url)
                    response.raise_for_status()
                except httpx.HTTPError as exc:
                    LOGGER.warning("HTTP collector failed on %s: %s", target_url, exc)
                    break
                html = response.text
                added = self._collect_links_from_html(html)
                if page_num == 1:
                    ajax_template = ajax_template or find_ajax_template(html)
                if added == 0:
                    LOGGER.info("No recipe links found on HTTP page %s; stopping", page_num)
                    break
                iterations += 1
                if self.settings.max_clicks is not None and iterations >= self.settings.max_clicks:
                    LOGGER.info("Reached HTTP pagination limit (%s)", self.settings.max_clicks)
                    break
                page_num += 1

    def _collect_links_from_html(self, html: str) -> int:
        links = extract_links_from_html(html, self.settings.app.base_url, self.allowed_hosts)
        if not links:
            return 0
        return self._store_links(links)

    def _store_links(self, candidates: Sequence[str]) -> int:
        filtered = []
        for href in candidates:
            normalized = normalize_url(href, self.settings.app.base_url, self.allowed_hosts)
            if not normalized:
                continue
            path = urlparse(normalized).path
            if not path.startswith("/cooking/"):
                continue
            filtered.append(normalized)
        if not filtered:
            return 0
        added = self.store.add_links(filtered)
        if added:
            LOGGER.info("Queued %s new recipe URLs", added)
            self._record_progress(added)
        return added

    def _record_progress(self, added: int) -> None:
        if not self._progress_interval:
            return
        self._collected_links += added
        bucket = self._collected_links // self._progress_interval
        if bucket > self._last_progress_bucket:
            self._last_progress_bucket = bucket
            milestone = bucket * self._progress_interval
            LOGGER.warning("Discovered %s recipe links so far", milestone)

    def _default_headers(self) -> dict[str, str]:
        return {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ru,en;q=0.9",
        }


def extract_links_from_html(html: str, base_url: str, allowed_hosts: set[str]) -> list[str]:
    tree = HTMLParser(html)
    links: list[str] = []
    for selector in ("#recipes a.h5[href]", ".cn-item a.h5[href]", "a.recipe-card[href]"):
        for node in tree.css(selector) or []:
            href = node.attributes.get("href")
            normalized = normalize_url(href, base_url, allowed_hosts)
            if not normalized:
                continue
            if urlparse(normalized).path.startswith("/cooking/"):
                links.append(normalized)
    deduped: list[str] = []
    seen = set()
    for url in links:
        if url in seen:
            continue
        seen.add(url)
        deduped.append(url)
    return deduped


def find_ajax_template(html: str) -> str | None:
    match = NEXT_PAGE_RE.search(html)
    if not match:
        return None
    return match.group(1)


def build_ajax_url(template: str, base_url: str, page_num: int) -> str:
    parsed = urlparse(urljoin(base_url, template))
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["p"] = str(page_num)
    new_query = urlencode(query, doseq=True)
    return urlunparse(parsed._replace(query=new_query))


