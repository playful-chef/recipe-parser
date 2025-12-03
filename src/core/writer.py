from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Iterable

from ..storage.link_store import LinkStore
from .logging import get_logger
from .models import RecipeRecord

LOGGER = get_logger(__name__)


class ResultWriter:
    def __init__(
        self,
        tsv_path: Path,
        *,
        flush_threshold: int = 500,
        jsonl_path: Path | None = None,
        link_store: LinkStore | None = None,
    ) -> None:
        self.tsv_path = tsv_path
        self.jsonl_path = jsonl_path
        self.flush_threshold = flush_threshold
        self.link_store = link_store
        self._buffer: list[RecipeRecord] = []
        self._lock = asyncio.Lock()

    async def append(self, record: RecipeRecord) -> None:
        async with self._lock:
            self._buffer.append(record)
            if len(self._buffer) >= self.flush_threshold:
                await self._flush_locked()

    async def flush(self) -> None:
        async with self._lock:
            await self._flush_locked()

    async def finalize(self) -> None:
        await self.flush()

    async def _flush_locked(self) -> None:
        if not self._buffer:
            return
        rows = list(self._buffer)
        self._buffer.clear()
        await asyncio.to_thread(self._write_rows, rows)
        LOGGER.warning("Flushed %s recipes to %s", len(rows), self.tsv_path)

    def _write_rows(self, rows: Iterable[RecipeRecord]) -> None:
        # LinkStore already enforces uniqueness (url is PRIMARY KEY), so we write every record
        # provided by the fetcher batch. This avoids dropping whole flushes due to timing races.
        rows = list(rows)
        if not rows:
            return
        self._write_tsv(rows)
        if self.jsonl_path:
            self._write_jsonl(rows)

    def _write_tsv(self, rows: Iterable[RecipeRecord]) -> None:
        path = self.tsv_path
        path.parent.mkdir(parents=True, exist_ok=True)
        need_header = not path.exists()
        with path.open("a", encoding="utf-8") as fh:
            if need_header:
                header_line = "\t".join(RecipeRecord.TSV_HEADERS) + "\n"
                fh.write(header_line)
            for record in rows:
                line = "\t".join(record.to_row()) + "\n"
                fh.write(line)

    def _write_jsonl(self, rows: Iterable[RecipeRecord]) -> None:
        path = self.jsonl_path
        if not path:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            for record in rows:
                fh.write(json.dumps(record.as_dict(), ensure_ascii=False) + "\n")


