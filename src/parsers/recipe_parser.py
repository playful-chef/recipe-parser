from __future__ import annotations

import json
import re

from selectolax.parser import HTMLParser

from ..core.models import RecipeRecord
from ..core.normalization import collapse_ws

NUTRINFO_PATTERN = re.compile(r"nutrinfo\s*:\s*(\{.*?\})", re.DOTALL)
NOISE_PATTERNS = [
    re.compile(r"if\(general_glob_settings[\s\S]+?(?=ШАГ\s+\d+\.|$)", re.IGNORECASE),
    re.compile(
        r"\(adsbygoogle\s*=\s*window\.adsbygoogle[\s\S]+?(?=ШАГ\s+\d+\.|$)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\(function\(w,\s*d,\s*n,\s*s,\s*t\)[\s\S]+?(?=Шаг\s+\d+:|$)",
        re.IGNORECASE,
    ),
]


def parse_recipe(html: str, url: str) -> RecipeRecord | None:
    tree = HTMLParser(html)
    recipe_root = tree.css_first('section[itemtype="http://schema.org/Recipe"]') or tree.css_first(
        "#pt_info"
    )
    if recipe_root is None:
        return None

    title = (
        _first_meta(recipe_root, 'meta[itemprop="name"]')
        or _first_meta(recipe_root, '[itemprop="name"]')
        or _first_text(tree, "h1")
    )
    description = _first_meta(recipe_root, '[itemprop="description"]')
    author = _first_meta(recipe_root, '[itemprop="author"] [itemprop="name"]')
    total_time = _first_meta(recipe_root, '[itemprop="totalTime"]')
    servings = _first_meta(recipe_root, '[itemprop="recipeYield"]')
    rating_value = _first_meta(recipe_root, '[itemprop="ratingValue"]')
    rating_count = _first_meta(recipe_root, '[itemprop="reviewCount"]')
    calories = _first_text(tree, '[itemprop="calories"]')
    image = _first_meta(tree, 'meta[property="og:image"]')

    ingredients = _gather_meta_list(tree, 'meta[itemprop="recipeIngredient"]')
    instructions = _collect_instructions(tree)
    equipment = _gather_text_list(tree, ".recipe-equipment li")
    categories = _breadcrumb_list(tree)
    tags = _gather_text_list(
        tree,
        ".sims-tags-line a, .catalogs-list-grid a, .catalogs-list-grid .item a",
    )

    if not title or not ingredients or not instructions:
        return None

    nutrition = _extract_nutrition(html)

    return RecipeRecord(
        title=title,
        instructions="\n".join(instructions),
        ingredients=", ".join(ingredients),
        url=url,
        description=description,
        author=author,
        total_time=total_time,
        servings=servings,
        calories=calories,
        rating_value=rating_value,
        rating_count=rating_count,
        categories=", ".join(categories) if categories else None,
        equipment=", ".join(equipment) if equipment else None,
        tags=", ".join(tags) if tags else None,
        image=image,
        protein_percent=nutrition.get("protein_percent"),
        protein_grams=nutrition.get("protein_grams"),
        fat_percent=nutrition.get("fat_percent"),
        fat_grams=nutrition.get("fat_grams"),
        carb_percent=nutrition.get("carb_percent"),
        carb_grams=nutrition.get("carb_grams"),
        calories_per_100g=nutrition.get("calories_per_100g"),
        calories_total=nutrition.get("calories_total"),
        gi_min=nutrition.get("gi_min"),
        gi_avg=nutrition.get("gi_avg"),
        gi_max=nutrition.get("gi_max"),
        total_weight_grams=nutrition.get("total_weight_grams"),
    )


def _first_meta(root: HTMLParser, selector: str) -> str | None:
    node = root.css_first(selector)
    if not node:
        return None
    content = node.attributes.get("content")
    if content:
        return collapse_ws(content)
    return collapse_ws(node.text())


def _first_text(tree: HTMLParser, selector: str) -> str | None:
    node = tree.css_first(selector)
    if not node:
        return None
    return collapse_ws(node.text())


def _gather_meta_list(tree: HTMLParser, selector: str) -> list[str]:
    values = []
    for node in tree.css(selector) or []:
        content = node.attributes.get("content") or node.text(deep=True)
        cleaned = collapse_ws(content)
        if cleaned:
            values.append(cleaned)
    deduped: list[str] = []
    seen = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def _gather_text_list(tree: HTMLParser, selector: str) -> list[str]:
    results = []
    for node in tree.css(selector) or []:
        if _is_ad_node(node):
            continue
        text = node.text(deep=True)
        if not text:
            continue
        cleaned = _strip_noise(text)
        if cleaned and not _looks_like_ad_text(cleaned):
            results.append(cleaned)
    return _dedupe(results)


def _collect_instructions(tree: HTMLParser) -> list[str]:
    instructions = _gather_text_list(tree, "ol.instructions li, .instructions li")
    extra_nodes = tree.css('[itemprop="recipeInstructions"] p, [itemprop="recipeInstructions"] li') or []
    for node in extra_nodes:
        if _is_ad_node(node):
            continue
        for chunk in _split_br_text(node):
            cleaned = _strip_noise(chunk)
            if cleaned and not _looks_like_ad_text(cleaned):
                instructions.append(cleaned)
    containers = tree.css('[itemprop="recipeInstructions"]') or []
    for node in containers:
        if _is_ad_node(node):
            continue
        for chunk in _split_br_text(node):
            cleaned = _strip_noise(chunk)
            if cleaned and not _looks_like_ad_text(cleaned):
                instructions.append(cleaned)
    return _dedupe(instructions)


def _split_br_text(node) -> list[str]:
    html = node.html
    if not html:
        return []
    html = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.IGNORECASE | re.DOTALL)
    replaced = re.sub(r"</?p[^>]*>", "\n", html, flags=re.IGNORECASE)
    replaced = re.sub(r"<br\s*/?>", "\n", replaced, flags=re.IGNORECASE)
    # Drop any remaining tags/attributes so we only keep readable text.
    replaced = re.sub(r"<[^>]+>", " ", replaced, flags=re.IGNORECASE)
    parts = [collapse_ws(part) for part in replaced.split("\n")]
    return [part for part in parts if part]


def _dedupe(values: list[str]) -> list[str]:
    deduped: list[str] = []
    seen = set()
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def _strip_noise(text: str) -> str:
    cleaned = text
    for pattern in NOISE_PATTERNS:
        cleaned = pattern.sub(" ", cleaned)
    cleaned = re.sub(r"\bРеклама\b", " ", cleaned, flags=re.IGNORECASE)
    return collapse_ws(cleaned)


def _looks_like_ad_text(text: str) -> bool:
    lower = text.lower()
    return any(
        marker in lower
        for marker in (
            "adfox",
            "adsbygoogle",
            "ya.adfox",
            "yaContextCb".lower(),
            "google-ya",
            "iface.jsappend",
            "(function(",
        )
    )


def _is_ad_node(node) -> bool:
    classes = node.attributes.get("class", "")
    return "as-ad-step" in classes


def _breadcrumb_list(tree: HTMLParser) -> list[str]:
    crumbs = [
        collapse_ws(node.text())
        for node in (tree.css("ol.breadcrumbs li span[itemprop='name']") or [])
    ]
    return [crumb for crumb in crumbs if crumb and crumb.lower() != "главная"]


def _extract_nutrition(html: str) -> dict[str, str | None]:
    match = NUTRINFO_PATTERN.search(html)
    if not match:
        return {}
    payload = match.group(1)
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return {}
    cals = _maybe_str(data.get("cals"))
    total_weight = data.get("total_weight") or 0
    total_cals = None
    if cals and total_weight:
        try:
            total_cals = str(int(round(float(cals) * float(total_weight) / 100)))
        except (ValueError, TypeError):
            total_cals = None
    return {
        "protein_percent": _maybe_str(data.get("ratio_p")),
        "protein_grams": _maybe_str(data.get("p")),
        "fat_percent": _maybe_str(data.get("ratio_f")),
        "fat_grams": _maybe_str(data.get("f")),
        "carb_percent": _maybe_str(data.get("ratio_c")),
        "carb_grams": _maybe_str(data.get("c")),
        "calories_per_100g": cals,
        "calories_total": total_cals,
        "gi_min": _maybe_str(data.get("ratio_cn")),
        "gi_avg": _maybe_str(data.get("ratio_cs")),
        "gi_max": _maybe_str(data.get("ratio_cv")),
        "total_weight_grams": _maybe_str(total_weight),
    }


def _maybe_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


