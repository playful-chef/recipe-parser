from __future__ import annotations

import json

import pytest

from src.core.models import RecipeRecord
from src.core.writer import ResultWriter


def _record(url: str) -> RecipeRecord:
    return RecipeRecord(
        title=f"Recipe for {url}",
        instructions="Step 1\nStep 2",
        ingredients="Water, Flour",
        url=url,
    )


@pytest.mark.asyncio
async def test_writer_persists_every_buffered_record(tmp_path) -> None:
    tsv_path = tmp_path / "recipes.tsv"
    jsonl_path = tmp_path / "recipes.jsonl"
    writer = ResultWriter(tsv_path, flush_threshold=1, jsonl_path=jsonl_path)

    records = [_record("https://example.com/1"), _record("https://example.com/2")]
    for record in records:
        await writer.append(record)
    await writer.flush()

    tsv_lines = tsv_path.read_text(encoding="utf-8").strip().splitlines()
    # Header + 2 rows
    assert len(tsv_lines) == 3

    json_rows = [json.loads(line) for line in jsonl_path.read_text(encoding="utf-8").splitlines()]
    assert len(json_rows) == 2
    assert {row["url"] for row in json_rows} == {record.url for record in records}

