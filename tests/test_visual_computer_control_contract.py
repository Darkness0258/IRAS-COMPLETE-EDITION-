from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(rel):
    return (
        ROOT
        / rel
    ).read_text(
        encoding="utf-8"
    )


def test_executor_exposes_visual_observe_act():
    text = _read(
        Path(
            "src/iras/device_bridge/executor.py"
        )
    )

    assert '"observe_ui"' in text
    assert '"semantic_action"' in text
    assert "SemanticVisualController" in text
    assert "self.visual.observe(" in text
    assert "self.visual.act(" in text


def test_cloud_tools_expose_visual_observe_act():
    text = _read(
        Path(
            "src/iras/device_bridge/tools.py"
        )
    )

    assert '"device_observe_ui"' in text
    assert '"device_semantic_action"' in text
    assert "PermissionLevel.READ" in text
    assert "PermissionLevel.SAFE_ACTION" in text


def test_autonomous_planner_receives_visual_tools():
    text = _read(
        Path(
            "src/iras/device_bridge/planner.py"
        )
    )

    assert '"device_observe_ui"' in text
    assert '"device_semantic_action"' in text
    lowered = text.lower()
    assert "re-observe" in lowered
    assert "meaningful actions" in lowered


def test_agent_current_turn_scope_guards_visual_tools():
    text = _read(
        Path(
            "src/iras/core/agent.py"
        )
    )

    assert '"device_observe_ui"' in text
    assert '"device_semantic_action"' in text


def test_uia_script_uses_environment_not_user_code_interpolation():
    text = _read(
        Path(
            "src/iras/device_bridge/visual_control.py"
        )
    )

    assert "$env:IRAS_UI_HWND" in text
    assert "$env:IRAS_UI_LIMIT" in text
    assert "-EncodedCommand" in text
    assert "shell=False" in text
    assert "eval(" not in text
    assert "exec(" not in text


def test_visual_action_derives_coordinates_from_observed_rect():
    text = _read(
        Path(
            "src/iras/device_bridge/visual_control.py"
        )
    )

    assert "def _center(" in text
    assert "selected_element" in text
    assert "derived_click" in text
    assert "before_fingerprint" in text
    assert "after_fingerprint" in text
    assert "ui_changed" in text
