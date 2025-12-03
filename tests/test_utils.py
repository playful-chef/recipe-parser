from src.core.normalization import collapse_ws, normalize_url


def test_collapse_ws_trims_and_collapses():
    assert collapse_ws("  Привет\nмир  ") == "Привет мир"


def test_normalize_url_filters_external():
    assert (
        normalize_url("https://example.com/page", "https://1000.menu", ["1000.menu"]) is None
    )


def test_normalize_url_normalizes_path():
    result = normalize_url("/cooking/123#fragment", "https://1000.menu", ["1000.menu"])
    assert result == "https://1000.menu/cooking/123"
