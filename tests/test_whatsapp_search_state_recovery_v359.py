from tests.support.whatsapp_validation_helpers import (
    find_whatsapp_filled_search_target as _find_search_target,
)


def test_filled_whatsapp_search_box_can_be_grounded_by_query_plus_search_band():
    target = {
        "element_id": "vision:9",
        "source": "vision",
        "label": "Darkness",
        "role": "icon",
        "rect": {"left": 83, "top": 105, "width": 342, "height": 40},
    }

    assert _find_search_target([target], current_query="Darkness") is target


def test_contact_name_elsewhere_is_not_mistaken_for_filled_search_box():
    chat_header = {
        "element_id": "vision:2",
        "source": "vision",
        "label": "Darkness",
        "role": "text",
        "rect": {"left": 610, "top": 45, "width": 120, "height": 28},
    }
    search_result = {
        "element_id": "vision:5",
        "source": "vision",
        "label": "Darkness",
        "role": "text",
        "rect": {"left": 130, "top": 260, "width": 100, "height": 22},
    }

    assert _find_search_target(
        [chat_header, search_result], current_query="Darkness"
    ) is None


def test_semantic_placeholder_still_wins_normally():
    placeholder = {
        "element_id": "vision:19",
        "source": "vision",
        "label": "Search or start new chat",
        "role": "icon",
        "rect": {"left": 83, "top": 105, "width": 342, "height": 40},
    }

    assert _find_search_target([placeholder], current_query="Darkness") is placeholder
