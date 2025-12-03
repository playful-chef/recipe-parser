from __future__ import annotations

from pathlib import Path

from src.parsers.recipe_parser import parse_recipe

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_recipe_extracts_nutrition_block() -> None:
    html = (FIXTURES / "bento_tort.html").read_text(encoding="utf-8")
    url = "https://1000.menu/cooking/65641-bento-tort-koreiskii"
    record = parse_recipe(html, url)
    assert record is not None
    assert record.title == "Бенто торт корейский"
    assert record.protein_percent == "15"
    assert record.protein_grams == "9"
    assert record.fat_percent == "39"
    assert record.fat_grams == "24"
    assert record.carb_percent == "46"
    assert record.carb_grams == "28"
    assert record.calories_per_100g == "306"
    assert record.total_weight_grams == "3526"
    assert record.calories_total == "10790"
    assert record.gi_min == "18"
    assert record.gi_avg == "0"
    assert record.gi_max == "82"
    assert record.url == url
    assert record.ingredients
    assert record.instructions


def test_instructions_are_stripped_from_html_tags() -> None:
    html = """
    <section itemtype="http://schema.org/Recipe">
        <h1>HTML Heavy Recipe</h1>
        <meta itemprop="recipeIngredient" content="Тестовое масло" />
        <div itemprop="recipeInstructions">
            <p>Смешайте <strong>ингредиенты</strong><br/>до однородности</p>
            <li><a href="https://example.com">Выпекайте 10 минут</a></li>
            <script>console.log('ads snippet');</script>
            <li class="as-ad-step noprint">
                <div id="adfox_123">
                    <script>(function(w, d, n, s, t) { window.example = 1; })(window, document, 'yaContextCb');</script>
                </div>
            </li>
        </div>
    </section>
    """
    record = parse_recipe(html, "https://example.com/html-heavy")
    assert record is not None
    assert "<" not in record.instructions
    assert ">" not in record.instructions
    assert "ингредиенты" in record.instructions
    assert "console.log" not in record.instructions
    assert "adfox" not in record.instructions.lower()
