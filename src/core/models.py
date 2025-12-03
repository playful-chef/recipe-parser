from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import ClassVar

from .normalization import collapse_ws


def _clean(value: str | None) -> str:
    if value is None:
        return ""
    return collapse_ws(value)


@dataclass(slots=True)
class RecipeRecord:
    TSV_HEADERS: ClassVar[tuple[str, ...]] = (
        "title",
        "instructions",
        "ingredients",
        "url",
        "description",
        "author",
        "total_time",
        "servings",
        "calories",
        "rating_value",
        "rating_count",
        "categories",
        "equipment",
        "tags",
        "image",
        "captured_at",
        "protein_percent",
        "protein_grams",
        "fat_percent",
        "fat_grams",
        "carb_percent",
        "carb_grams",
        "calories_per_100g",
        "calories_total",
        "gi_min",
        "gi_avg",
        "gi_max",
        "total_weight_grams",
    )

    title: str
    instructions: str
    ingredients: str
    url: str
    description: str | None = None
    author: str | None = None
    total_time: str | None = None
    servings: str | None = None
    calories: str | None = None
    rating_value: str | None = None
    rating_count: str | None = None
    categories: str | None = None
    equipment: str | None = None
    tags: str | None = None
    image: str | None = None
    captured_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )
    protein_percent: str | None = None
    protein_grams: str | None = None
    fat_percent: str | None = None
    fat_grams: str | None = None
    carb_percent: str | None = None
    carb_grams: str | None = None
    calories_per_100g: str | None = None
    calories_total: str | None = None
    gi_min: str | None = None
    gi_avg: str | None = None
    gi_max: str | None = None
    total_weight_grams: str | None = None

    def to_row(self) -> list[str]:
        values = [
            self.title,
            self.instructions,
            self.ingredients,
            self.url,
            self.description,
            self.author,
            self.total_time,
            self.servings,
            self.calories,
            self.rating_value,
            self.rating_count,
            self.categories,
            self.equipment,
            self.tags,
            self.image,
            self.captured_at,
            self.protein_percent,
            self.protein_grams,
            self.fat_percent,
            self.fat_grams,
            self.carb_percent,
            self.carb_grams,
            self.calories_per_100g,
            self.calories_total,
            self.gi_min,
            self.gi_avg,
            self.gi_max,
            self.total_weight_grams,
        ]
        return [_clean(v) for v in values]

    def as_dict(self) -> dict[str, str]:
        keys = self.TSV_HEADERS
        values = self.to_row()
        return dict(zip(keys, values, strict=False))


