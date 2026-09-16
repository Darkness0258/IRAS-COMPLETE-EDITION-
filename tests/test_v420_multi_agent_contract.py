from pathlib import Path


def test_cloud_exposes_multi_agent_lifecycle_routes():
    text = Path('src/iras/cloud_api.py').read_text(encoding='utf-8')
    for route in (
        '/v1/orchestration/runs',
        '/v1/orchestration/runs/{run_id}/pause',
        '/v1/orchestration/runs/{run_id}/resume',
    ):
        assert route in text
    assert 'cancel_orchestration_run' in text


def test_planner_is_toolless_and_has_safe_fallback():
    text = Path('src/iras/cloud_api.py').read_text(encoding='utf-8')
    block = text[text.index('def _orchestration_planner'):text.index('orchestration_manager =')]
    assert 'worker.provider.complete' in block
    assert '[],\n        )' in block
    assert '_orchestration_fallback_plan' in block
    assert 'Planner did not return' in text


def test_web_tasks_panel_has_goal_lifecycle_controls():
    text = Path('clients/web/index.html').read_text(encoding='utf-8')
    for item in ('runGoal', 'latestGoal', 'pauseGoal', 'resumeGoal', 'cancelGoal'):
        assert f'id="{item}"' in text
    assert '/v1/orchestration/runs' in text
    assert 'FINAL COORDINATOR RESULT' in text


def test_doctor_reports_multi_agent_execution_separately():
    text = Path('src/iras/doctor.py').read_text(encoding='utf-8')
    assert '"Multi-agent execution"' in text
    assert 'IRAS_ORCHESTRATION_WORKERS' in text
    assert 'IRAS_ORCHESTRATION_MAX_TASKS' in text


def test_worker_role_directive_survives_adaptive_prompt_rebuild_contract():
    bootstrap = Path('src/iras/cloud_bootstrap.py').read_text(encoding='utf-8')
    agent = Path('src/iras/core/agent.py').read_text(encoding='utf-8')
    assert 'system_prompt_suffix' in bootstrap
    assert 'suffix = self.system_prompt[len(base_profile_prompt):]' in agent
