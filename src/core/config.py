from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin


def _default_search_path() -> str:
    return "/cooking/search?ms=1&str=&es_tf=0&es_tt=14&es_cf=0&es_ct=2000"


class CollectorMode(str, Enum):
    AUTO = "auto"
    BROWSER = "browser"
    HTTP = "http"


@dataclass(slots=True)
class AppPaths:
    base_url: str = "https://1000.menu"
    search_path: str = field(default_factory=_default_search_path)
    data_dir: Path = Path("data/output")
    state_dir: Path = Path("state")
    output_file: Path = Path("data/output/recipes.tsv")
    jsonl_file: Path | None = None

    def search_url(self) -> str:
        return urljoin(self.base_url, self.search_path)

    @property
    def queue_db(self) -> Path:
        return self.state_dir / "workqueue.db"

    @property
    def collector_state_file(self) -> Path:
        return self.state_dir / "collector_state.json"


@dataclass(slots=True)
class CollectorSettings:
    app: AppPaths = field(default_factory=AppPaths)
    click_delay: float = 0.3
    max_clicks: int | None = None
    scroll_pause: float = 0.1
    progress_interval: int = 200
    results_wait_timeout: float = 8.0
    results_poll_interval: float = 0.25
    headless: bool = True
    slow_mo_ms: int | None = None
    mode: CollectorMode = CollectorMode.AUTO
    http_timeout: float = 30.0

    def ensure_dirs(self) -> None:
        self.app.state_dir.mkdir(parents=True, exist_ok=True)


@dataclass(slots=True)
class FetcherSettings:
    app: AppPaths = field(default_factory=AppPaths)
    batch_size: int = 200
    http_concurrency: int = 16
    http_timeout: float = 25.0
    flush_threshold: int = 500
    progress_interval: int = 200
    max_failures: int = 5
    lease_seconds: float = 900.0
    user_agent: str = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    )

    def ensure_dirs(self) -> None:
        self.app.data_dir.mkdir(parents=True, exist_ok=True)
        self.app.state_dir.mkdir(parents=True, exist_ok=True)


