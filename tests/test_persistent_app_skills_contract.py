from pathlib import Path


def text(path):
    return Path(path).read_text(encoding="utf-8")


def test_planner_exposes_learned_skill_tools_and_fallback_contract():
    source = text("src/iras/device_bridge/planner.py")
    assert '"device_skill_find"' in source
    assert '"device_skill_validate"' in source
    assert '"device_skill_list"' in source
    assert '"device_skill_inspect"' in source
    assert '"device_skill_delete"' in source
    lowered = source.lower()
    assert "device_skill_validate" in lowered
    assert "v3.2 fallback" in lowered
    assert "raw coordinates" in lowered


def test_skill_tools_keep_execution_in_existing_semantic_action_path():
    source = text("src/iras/device_bridge/skill_tools.py")
    lowered = source.lower()
    assert "permissionlevel.read" in lowered
    assert "permissionlevel.safe_action" in lowered
    assert "device_semantic_action" in source
    assert 'action="observe_ui"' in source
    assert '"ensure_open": false' in lowered
    assert "semantic_action" not in source.split("def device_skill_validate", 1)[1].split("def device_skill_list", 1)[0].replace("device_semantic_action", "")


def test_task_tracker_persists_only_verified_semantic_trace():
    source = text("src/iras/device_bridge/task_engine.py")
    assert "LearnedStep" in source
    assert 'name == "device_semantic_action"' in source
    assert 'output.get("verification_observation")' in source
    assert "learn_verified" in source
    assert "learnable_steps" in source


def test_version_is_345():
    assert "3.4.5" in text("src/iras/__init__.py")
    assert 'version = "3.4.5"' in text("pyproject.toml")
