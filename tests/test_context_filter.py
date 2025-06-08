from vea.utils.context_filter import filter_top_n


def test_filter_top_n_returns_most_similar():
    items = [
        {"content": "apple banana"},
        {"content": "orange"},
        {"content": "banana pie"},
    ]
    result = filter_top_n(items, "apple", 1)
    assert result[0]["content"] == "apple banana"


def test_filter_top_n_handles_empty():
    assert filter_top_n([], "query", 5) == []
