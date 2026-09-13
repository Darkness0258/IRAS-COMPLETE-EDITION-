from iras.device_bridge.visual_control import (
    SemanticVisualController,
)


def _element(
    name,
    role,
    *,
    automation_id="",
    enabled=True,
    index=0,
):
    return {
        "index": index,
        "name": name,
        "automation_id": automation_id,
        "role": role,
        "enabled": enabled,
        "focusable": True,
        "value": None,
        "rect": {
            "left": 10,
            "top": 20,
            "width": 120,
            "height": 30,
        },
    }


def test_exact_name_beats_partial_match():
    elements = [
        _element(
            "Settings and privacy",
            "Button",
            index=0,
        ),
        _element(
            "Settings",
            "Button",
            index=1,
        ),
    ]

    match = (
        SemanticVisualController
        .find_element(
            elements,
            "Settings",
        )
    )

    assert (
        match["name"]
        == "Settings"
    )


def test_role_can_disambiguate_same_name():
    elements = [
        _element(
            "Search",
            "Text",
            index=0,
        ),
        _element(
            "Search",
            "Edit",
            index=1,
        ),
    ]

    match = (
        SemanticVisualController
        .find_element(
            elements,
            "Search",
            role="Edit",
        )
    )

    assert (
        match["role"]
        == "Edit"
    )


def test_automation_id_can_be_target():
    elements = [
        _element(
            "",
            "Button",
            automation_id="sendButton",
            index=0,
        ),
    ]

    match = (
        SemanticVisualController
        .find_element(
            elements,
            "sendButton",
        )
    )

    assert (
        match[
            "automation_id"
        ]
        == "sendButton"
    )


def test_occurrence_selects_repeated_visible_item():
    elements = [
        _element(
            "Open",
            "Button",
            index=0,
        ),
        _element(
            "Open",
            "Button",
            index=1,
        ),
    ]

    match = (
        SemanticVisualController
        .find_element(
            elements,
            "Open",
            occurrence=2,
        )
    )

    assert (
        match["index"]
        == 1
    )


def test_disabled_control_is_penalized():
    elements = [
        _element(
            "Send",
            "Button",
            enabled=False,
            index=0,
        ),
        _element(
            "Send message",
            "Button",
            enabled=True,
            index=1,
        ),
    ]

    match = (
        SemanticVisualController
        .find_element(
            elements,
            "Send",
        )
    )

    assert (
        match["enabled"]
        is True
    )


def test_allowed_semantic_actions_are_bounded():
    assert (
        SemanticVisualController
        .ALLOWED_ACTIONS
        == {
            "click",
            "double_click",
            "focus",
            "type_into",
            "press",
        }
    )
