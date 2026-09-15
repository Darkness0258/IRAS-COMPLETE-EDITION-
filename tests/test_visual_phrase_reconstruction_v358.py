from iras.device_bridge.computer_use import UniversalComputerController


def _observation(elements):
    return {
        "elements": elements,
        "screenshot": {"sha256": "screen"},
        "visual_sha256": "visual",
        "vision_available": True,
        "foreground": {"hwnd": 1, "title": "WhatsApp"},
    }


def test_text_contains_reconstructs_same_row_vision_fragments():
    observation = _observation(
        [
            {
                "element_id": "vision:1",
                "source": "vision",
                "label": "IRAS test message",
                "role": "text",
                "rect": {"left": 520, "top": 990, "width": 150, "height": 20},
            },
            {
                "element_id": "vision:2",
                "source": "vision",
                "label": "v3.5.8 123456",
                "role": "text",
                "rect": {"left": 680, "top": 991, "width": 120, "height": 19},
            },
        ]
    )

    status, evidence = UniversalComputerController._evaluate_condition(
        observation,
        condition="text_contains",
        target="IRAS test message v3.5.8 123456",
    )

    assert status == "PASS"
    assert any("iras test message v3.5.8 123456" in value for value in evidence["matches"])


def test_text_contains_does_not_join_unrelated_visual_rows():
    observation = _observation(
        [
            {
                "element_id": "vision:1",
                "source": "vision",
                "label": "IRAS test message",
                "role": "text",
                "rect": {"left": 520, "top": 800, "width": 150, "height": 20},
            },
            {
                "element_id": "vision:2",
                "source": "vision",
                "label": "v3.5.8 123456",
                "role": "text",
                "rect": {"left": 520, "top": 990, "width": 120, "height": 20},
            },
        ]
    )

    status, _ = UniversalComputerController._evaluate_condition(
        observation,
        condition="text_contains",
        target="IRAS test message v3.5.8 123456",
    )

    assert status == "FAIL"
