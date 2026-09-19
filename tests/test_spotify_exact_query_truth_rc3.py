from iras.device_bridge.ui_control import WindowsUIController


def test_spotify_query_match_uses_whole_tokens():
    assert WindowsUIController._spotify_query_matches_label("maa", "Maa") is True
    assert WindowsUIController._spotify_query_matches_label("maa", "Maa - Song") is True
    assert WindowsUIController._spotify_query_matches_label("maa", "Maanu") is False
    assert WindowsUIController._spotify_query_matches_label("maa", "Maand") is False
    assert WindowsUIController._spotify_query_matches_label("maa", "Maahi") is False


def test_spotify_multiword_query_requires_all_meaningful_tokens():
    assert WindowsUIController._spotify_query_matches_label("Shape of You", "Shape of You") is True
    assert WindowsUIController._spotify_query_matches_label("Shape of You", "Shape") is False
