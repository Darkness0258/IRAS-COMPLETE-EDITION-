from tests.support.whatsapp_validation_helpers import (
    find_composer_target as _find_composer_target,
    find_contact_target as _find_contact_target,
)


def test_contact_grounding_rejects_search_box_with_same_query():
    search = {
        "element_id": "vision:1",
        "label": "Darkness",
        "role": "input",
        "rect": {"left": 80, "top": 100, "width": 340, "height": 40},
    }
    contact = {
        "element_id": "vision:8",
        "label": "Darkness",
        "role": "text",
        "rect": {"left": 90, "top": 190, "width": 120, "height": 28},
    }
    found = _find_contact_target(
        [search, contact], contact="Darkness", search_rect=search["rect"]
    )
    assert found is contact


def test_contact_grounding_requires_contact_semantics():
    found = _find_contact_target(
        [
            {
                "element_id": "vision:5",
                "label": "Search or start new chat",
                "role": "icon",
                "rect": {"left": 80, "top": 100, "width": 340, "height": 40},
            }
        ],
        contact="Darkness",
        search_rect={"left": 80, "top": 100, "width": 340, "height": 40},
    )
    assert found is None


def test_composer_grounding_prefers_type_a_message_control():
    target = {
        "element_id": "vision:31",
        "label": "Type a message",
        "role": "textbox",
        "rect": {"left": 500, "top": 900, "width": 800, "height": 45},
    }
    noise = {
        "element_id": "vision:4",
        "label": "Search messages",
        "role": "button",
        "rect": {"left": 1400, "top": 80, "width": 120, "height": 40},
    }
    assert _find_composer_target([noise, target]) is target
