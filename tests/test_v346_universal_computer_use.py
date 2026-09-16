from pathlib import Path

from iras.device_bridge.computer_use import UniversalComputerController


ROOT = Path(__file__).resolve().parents[1]


def source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_v346_or_newer_version_contract():
    import re
    init = source('src/iras/__init__.py')
    project = source('pyproject.toml')
    im = re.search(r'__version__\s*=\s*"(\d+)\.(\d+)\.(\d+)', init)
    pm = re.search(r'(?m)^version\s*=\s*"(\d+)\.(\d+)\.(\d+)', project)
    assert im is not None and pm is not None
    version = tuple(int(x) for x in im.groups())
    assert version >= (3, 4, 6)
    assert tuple(int(x) for x in pm.groups()) == version


def test_executor_registers_universal_computer_actions():
    text = source('src/iras/device_bridge/executor.py')
    for action in (
        'computer_status',
        'computer_observe',
        'computer_action',
        'computer_verify',
    ):
        assert f'"{action}"' in text
    assert 'UniversalComputerController' in text


def test_cloud_tools_expose_observe_act_verify_without_raw_xy_schema():
    text = source('src/iras/device_bridge/tools.py')
    assert '"device_computer_observe"' in text
    assert '"device_computer_action"' in text
    assert '"device_computer_verify"' in text

    start = text.index('            "device_computer_action",')
    end = text.index('        Tool(\n            "device_computer_verify",', start)
    block = text[start:end]

    assert '"observation_id"' in block
    assert '"element_id"' in block
    assert '"target_element_id"' in block
    assert '"x"' not in block
    assert '"y"' not in block


def test_planner_contains_closed_loop_computer_use_contract():
    text = source('src/iras/device_bridge/planner.py')
    for tool in (
        'device_computer_status',
        'device_computer_observe',
        'device_computer_action',
        'device_computer_verify',
    ):
        assert f'"{tool}"' in text
    lowered = text.lower()
    assert 'observation_id' in lowered
    assert 'element_id' in lowered
    assert 'never invent raw x/y coordinates' in lowered
    assert 'pass as success' in lowered
    assert 'inconclusive is not success' in lowered


def test_omniparser_adapter_uses_official_server_contract():
    controller = source('src/iras/device_bridge/computer_use.py')
    runtime = source('src/iras/vision/omniparser_runtime.py')
    text = controller + runtime
    assert 'IRAS_OMNIPARSER_URL' in text
    assert 'IRAS_OMNIPARSER_API_KEY' in text
    assert '/parse/' in text
    assert 'base64_image' in controller
    assert 'parsed_content_list' in controller
    assert 'som_image_base64' in controller
    assert 'IRAS_OMNIPARSER_AUTOSTART' in runtime


def test_vision_ratio_boxes_map_to_desktop_coordinates():
    parsed = [
        {
            'type': 'icon',
            'bbox': [0.25, 0.20, 0.50, 0.60],
            'interactivity': True,
            'content': 'Play',
            'source': 'box_yolo_content_yolo',
        }
    ]

    elements = UniversalComputerController._normalize_vision_elements(
        parsed,
        desktop_rect={
            'left': -100,
            'top': 50,
            'width': 2000,
            'height': 1000,
        },
        image_width=1000,
        image_height=500,
    )

    assert len(elements) == 1
    element = elements[0]
    assert element['element_id'] == 'vision:0'
    assert element['label'] == 'Play'
    assert element['rect'] == {
        'left': 400,
        'top': 250,
        'width': 500,
        'height': 400,
    }
    assert element['center'] == {'x': 650, 'y': 450}


def test_uia_elements_receive_stable_observation_local_ids():
    snapshot = {
        'elements': [
            {
                'name': 'Settings',
                'automation_id': 'settingsButton',
                'role': 'Button',
                'enabled': True,
                'value': None,
                'rect': {'left': 10, 'top': 20, 'width': 100, 'height': 40},
            }
        ]
    }

    elements = UniversalComputerController._uia_elements(snapshot)
    assert elements[0]['element_id'] == 'uia:0'
    assert elements[0]['label'] == 'Settings'
    assert elements[0]['center'] == {'x': 60, 'y': 40}


def test_outcome_verification_pass_fail_inconclusive():
    observation = {
        'foreground': {'title': 'Spotify'},
        'elements': [
            {
                'label': 'Majboor',
                'name': 'Majboor',
                'automation_id': '',
                'role': 'Text',
                'value': '',
            }
        ],
        'screenshot': {'sha256': 'after'},
    }
    prior = {
        'foreground': {'title': 'Chrome'},
        'screenshot': {'sha256': 'before'},
    }

    status, _ = UniversalComputerController._evaluate_condition(
        observation,
        condition='text_contains',
        target='Majboor',
    )
    assert status == 'PASS'

    status, _ = UniversalComputerController._evaluate_condition(
        observation,
        condition='element_absent',
        target='Majboor',
    )
    assert status == 'FAIL'

    status, _ = UniversalComputerController._evaluate_condition(
        observation,
        condition='screen_changed',
        prior=prior,
    )
    assert status == 'PASS'

    status, _ = UniversalComputerController._evaluate_condition(
        observation,
        condition='screen_changed',
        prior=None,
    )
    assert status == 'INCONCLUSIVE'


def test_task_engine_requires_goal_verification_after_computer_action():
    text = source('src/iras/device_bridge/task_engine.py')
    assert '"device_computer_action"' in text
    assert '"device_computer_verify"' in text
    assert 'self.needs_verification = True' in text
    assert 'status != "PASS"' in text


def test_computer_use_blocks_security_admin_visual_targets():
    assert UniversalComputerController._blocked_element(
        {
            'label': 'Open Windows Terminal',
            'name': '',
            'automation_id': '',
            'role': 'Button',
        }
    )
    assert not UniversalComputerController._blocked_element(
        {
            'label': 'Send message',
            'name': '',
            'automation_id': '',
            'role': 'Button',
        }
    )
