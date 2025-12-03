from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from src.core.config import AppPaths, CollectorMode, CollectorSettings
from src.storage.link_store import LinkStore
import src.workers.link_collector as link_collector_module

from src.workers.link_collector import (
    LinkCollector,
    build_ajax_url,
    extract_links_from_html,
    find_ajax_template,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_find_ajax_template_from_search_page() -> None:
    html = (FIXTURES / "search_page.html").read_text(encoding="utf-8")
    template = find_ajax_template(html)
    assert template is not None
    assert template.startswith("/ajax/free/search_page")
    assert "p=2" in template


def test_build_ajax_url_sets_page() -> None:
    template = "/ajax/free/search_page?ms=1&p=2"
    built = build_ajax_url(template, "https://1000.menu", 7)
    parsed = urlparse(built)
    assert parsed.netloc == "1000.menu"
    assert parse_qs(parsed.query)["p"] == ["7"]


def test_extract_links_from_html() -> None:
    html = (FIXTURES / "search_page.html").read_text(encoding="utf-8")
    links = extract_links_from_html(html, "https://1000.menu", {"1000.menu"})
    assert any(link.startswith("https://1000.menu/cooking/") for link in links)


def _make_ajax_payload(start: int, count: int) -> str:
    cards = "\n".join(
        f'<a class="recipe-card" href="/cooking/generated-recipe-{idx}">Recipe {idx}</a>'
        for idx in range(start, start + count)
    )
    return f"<div class='next_page_content'>{cards}</div>"


@pytest.mark.asyncio
async def test_http_collector_collects_over_100_links(monkeypatch, tmp_path) -> None:
    search_html = (FIXTURES / "search_page.html").read_text(encoding="utf-8")
    template = find_ajax_template(search_html)
    assert template

    base_paths = AppPaths()
    app_paths = AppPaths(
        base_url=base_paths.base_url,
        search_path=base_paths.search_path,
        data_dir=tmp_path / "data",
        state_dir=tmp_path / "state",
        output_file=tmp_path / "data/output.tsv",
        jsonl_file=None,
    )
    settings = CollectorSettings(app=app_paths, mode=CollectorMode.HTTP)
    store = LinkStore(tmp_path / "links.db")
    collector = LinkCollector(settings, store)

    ajax_page_two = _make_ajax_payload(10_000, 70)
    ajax_page_three = "<div class='next_page_content'></div>"
    ajax_url_two = build_ajax_url(template, app_paths.base_url, 2)
    ajax_url_three = build_ajax_url(template, app_paths.base_url, 3)
    responses = {
        app_paths.search_url(): search_html,
        ajax_url_two: ajax_page_two,
        ajax_url_three: ajax_page_three,
    }

    class DummyResponse:
        def __init__(self, text: str) -> None:
            self.text = text

        def raise_for_status(self) -> None:
            return None

    class DummyAsyncClient:
        def __init__(self, payloads: dict[str, str]) -> None:
            self._payloads = payloads

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url: str) -> DummyResponse:
            if url not in self._payloads:
                raise AssertionError(f"Unexpected URL requested: {url}")
            return DummyResponse(self._payloads[url])

    monkeypatch.setattr(
        link_collector_module.httpx, "AsyncClient", lambda *args, **kwargs: DummyAsyncClient(responses)
    )

    collector.settings.ensure_dirs()
    try:
        await collector._run_http_mode()
        stats = store.stats()
        total_urls = sum(stats.values())
        assert total_urls >= 100
    finally:
        store.close()

