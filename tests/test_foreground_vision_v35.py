from iras.device_bridge.computer_use import UniversalComputerController


def test_numeric_panes_are_not_actionable_uia():
    elements = [
        {
            "role": "Pane",
            "label": "15",
            "automation_id": "15",
            "enabled": True,
        },
        {
            "role": "Pane",
            "label": "1025",
            "automation_id": "1025",
            "enabled": True,
        },
    ]

    assert (
        UniversalComputerController._uia_has_actionable_elements(
            elements
        )
        is False
    )


def test_button_is_actionable_uia():
    elements = [
        {
            "role": "Button",
            "label": "Save",
            "automation_id": "SaveButton",
            "enabled": True,
        }
    ]

    assert (
        UniversalComputerController._uia_has_actionable_elements(
            elements
        )
        is True
    )


def test_vision_coordinates_remap_from_foreground_crop():
    parsed = [
        {
            "bbox": [0.1, 0.1, 0.2, 0.2],
            "content": "File",
            "type": "text",
            "interactivity": True,
        }
    ]

    elements = (
        UniversalComputerController._normalize_vision_elements(
            parsed,
            desktop_rect={
                "left": 500,
                "top": 300,
                "width": 1000,
                "height": 600,
            },
            image_width=1000,
            image_height=600,
        )
    )

    element = elements[0]

    assert element["rect"]["left"] == 600
    assert element["rect"]["top"] == 360
    assert element["rect"]["width"] == 100
    assert element["rect"]["height"] == 60

    assert element["center"] == {
        "x": 650,
        "y": 390,
    }

def test_focusable_input_sink_pane_is_not_actionable_uia():
    elements = UniversalComputerController._uia_elements(
        {
            "elements": [
                {
                    "name": "Non Client Input Sink Window",
                    "automation_id": "",
                    "role": "Pane",
                    "enabled": True,
                    "focusable": True,
                    "rect": {
                        "left": 0,
                        "top": 0,
                        "width": 1920,
                        "height": 32,
                    },
                }
            ]
        }
    )

    # Framework plumbing must not be exposed as a user-operable target and
    # must not suppress foreground visual grounding.
    assert elements[0]["interactive"] is False
    assert (
        UniversalComputerController._uia_has_actionable_elements(elements)
        is False
    )


def test_focusable_custom_search_control_remains_actionable_uia():
    elements = UniversalComputerController._uia_elements(
        {
            "elements": [
                {
                    "name": "Search chats",
                    "automation_id": "SearchBox",
                    "role": "Custom",
                    "enabled": True,
                    "focusable": True,
                    "rect": {
                        "left": 100,
                        "top": 100,
                        "width": 320,
                        "height": 36,
                    },
                }
            ]
        }
    )

    assert (
        UniversalComputerController._uia_has_actionable_elements(elements)
        is True
    )

