from tests.support.whatsapp_validation_helpers import (
    find_whatsapp_search_target as _find_search_target,
)


def test_whatsapp_search_grounding_rejects_generic_input_sink_pane():
    elements = [
        {
            "element_id": "uia:0",
            "label": "Non Client Input Sink Window",
            "role": "Pane",
            "rect": {"left": 0, "top": 0, "width": 1920, "height": 32},
        }
    ]

    assert _find_search_target(elements) is None


def test_whatsapp_search_grounding_prefers_semantic_visual_search_target():
    elements = [
        {
            "element_id": "uia:0",
            "label": "Non Client Input Sink Window",
            "role": "Pane",
            "rect": {"left": 0, "top": 0, "width": 1920, "height": 32},
        },
        {
            "element_id": "vision:12",
            "label": "Search or start new chat",
            "role": "text",
            "rect": {"left": 110, "top": 85, "width": 320, "height": 36},
        },
    ]

    target = _find_search_target(elements)
    assert target is not None
    assert target["element_id"] == "vision:12"
