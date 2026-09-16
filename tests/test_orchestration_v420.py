from __future__ import annotations

import threading
import time

import pytest

from iras.orchestration import (
    OrchestrationManager,
    GraphTaskSpec,
    parse_goal_command,
)


def test_goal_chat_syntax_is_explicit():
    assert parse_goal_command('/goal Build and test the feature') == 'Build and test the feature'
    assert parse_goal_command('/orchestrate\nreview this project') == 'review this project'
    assert parse_goal_command('build it with agents') == ''


def test_graph_runs_independent_nodes_in_parallel_then_dependency():
    times = {}
    lock = threading.Lock()

    def runner(prompt, context):
        with lock:
            times[prompt + '_start'] = time.perf_counter()
        if prompt in {'alpha', 'beta'}:
            time.sleep(0.15)
        with lock:
            times[prompt + '_end'] = time.perf_counter()
        return {'result': prompt.upper(), 'metrics': {}}

    manager = OrchestrationManager(runner, max_workers=3, max_tasks_per_run=8)
    try:
        run = manager.submit_graph(
            'parallel graph',
            [
                {'id': 'a', 'prompt': 'alpha', 'role': 'researcher', 'priority': 80},
                {'id': 'b', 'prompt': 'beta', 'role': 'reviewer', 'priority': 70},
                {'id': 'c', 'prompt': 'gamma', 'role': 'tester', 'depends_on': ['a', 'b']},
            ],
            add_coordinator=False,
        )
        final = manager.wait(run['run_id'], timeout=3)
        assert final['state'] == 'succeeded'
        assert abs(times['alpha_start'] - times['beta_start']) < 0.10
        assert times['gamma_start'] >= max(times['alpha_end'], times['beta_end'])
    finally:
        manager.close()


def test_role_and_dependency_outputs_reach_worker_context():
    seen = {}

    def runner(prompt, context):
        seen[prompt] = context
        return {'result': 'result-' + prompt}

    manager = OrchestrationManager(runner, max_workers=2, max_tasks_per_run=6)
    try:
        run = manager.submit_graph(
            'objective',
            [
                {'id': 'research', 'prompt': 'facts', 'role': 'researcher'},
                {'id': 'review', 'prompt': 'review', 'role': 'reviewer', 'depends_on': ['research']},
            ],
            add_coordinator=False,
        )
        manager.wait(run['run_id'], timeout=2)
        assert seen['review']['agent_role'] == 'reviewer'
        assert 'Reviewer Agent' in seen['review']['role_directive']
        assert seen['review']['dependency_results'][0]['result'] == 'result-facts'
        assert seen['review']['objective'] == 'objective'
    finally:
        manager.close()


def test_retry_requeues_bounded_failure_and_succeeds():
    attempts = {'work': 0}

    def runner(prompt, _context):
        attempts[prompt] += 1
        if attempts[prompt] == 1:
            raise RuntimeError('temporary')
        return {'result': 'ok'}

    manager = OrchestrationManager(runner, max_workers=1, max_tasks_per_run=4)
    try:
        run = manager.submit_graph(
            'retry',
            [{'id': 'work', 'prompt': 'work', 'max_retries': 1}],
            add_coordinator=False,
        )
        final = manager.wait(run['run_id'], timeout=4)
        task = final['tasks'][0]
        assert final['state'] == 'succeeded'
        assert task['attempts'] == 2
        assert attempts['work'] == 2
    finally:
        manager.close()


def test_pause_blocks_new_dependency_nodes_until_resume():
    first_started = threading.Event()
    release_first = threading.Event()

    def runner(prompt, _context):
        if prompt == 'first':
            first_started.set()
            release_first.wait(timeout=2)
        return {'result': prompt}

    manager = OrchestrationManager(runner, max_workers=2, max_tasks_per_run=5)
    try:
        run = manager.submit_graph(
            'pause',
            [
                {'id': 'one', 'prompt': 'first'},
                {'id': 'two', 'prompt': 'second', 'depends_on': ['one']},
            ],
            add_coordinator=False,
        )
        assert first_started.wait(timeout=1)
        manager.pause(run['run_id'])
        release_first.set()
        time.sleep(0.25)
        paused = manager.get(run['run_id'])
        states = {t['task_id']: t['state'] for t in paused['tasks']}
        assert paused['state'] == 'paused'
        assert states['two'] == 'queued'
        manager.resume(run['run_id'])
        final = manager.wait(run['run_id'], timeout=2)
        assert final['state'] == 'succeeded'
    finally:
        manager.close()


def test_cancel_prevents_downstream_and_discards_late_result():
    started = threading.Event()
    release = threading.Event()

    def runner(prompt, _context):
        if prompt == 'first':
            started.set()
            release.wait(timeout=2)
        return {'result': 'late-' + prompt}

    manager = OrchestrationManager(runner, max_workers=1, max_tasks_per_run=5)
    try:
        run = manager.submit_graph(
            'cancel',
            [
                {'id': 'one', 'prompt': 'first'},
                {'id': 'two', 'prompt': 'second', 'depends_on': ['one']},
            ],
            add_coordinator=False,
        )
        assert started.wait(timeout=1)
        manager.cancel(run['run_id'])
        release.set()
        final = manager.wait(run['run_id'], timeout=2)
        assert final['state'] == 'cancelled'
        by_id = {t['task_id']: t for t in final['tasks']}
        assert by_id['two']['state'] == 'cancelled'
        assert by_id['one']['state'] == 'cancelled'
        assert by_id['one']['result'] == ''
    finally:
        manager.close()


def test_failed_dependency_blocks_normal_task_but_final_coordinator_can_continue():
    def runner(prompt, _context):
        if prompt == 'boom':
            raise RuntimeError('nope')
        return {'result': 'ok-' + prompt}

    manager = OrchestrationManager(runner, max_workers=2, max_tasks_per_run=6)
    try:
        run = manager.submit_graph(
            'partial',
            [
                {'id': 'bad', 'prompt': 'boom', 'max_retries': 0},
                {'id': 'blocked', 'prompt': 'never', 'depends_on': ['bad']},
            ],
            add_coordinator=True,
        )
        final = manager.wait(run['run_id'], timeout=3)
        by_id = {t['task_id']: t for t in final['tasks']}
        assert final['state'] == 'failed'
        assert by_id['bad']['state'] == 'failed'
        assert by_id['blocked']['state'] == 'blocked'
        coordinator = [t for t in final['tasks'] if t['role'] == 'coordinator'][0]
        assert coordinator['state'] == 'succeeded'
        assert final['final_result'].startswith('ok-')
    finally:
        manager.close()


def test_async_planner_builds_graph_and_coordinator():
    def planner(objective, _context):
        return [
            {'id': 'r', 'title': 'Research', 'prompt': objective, 'role': 'researcher'},
            {'id': 't', 'title': 'Test', 'prompt': 'verify', 'role': 'tester', 'depends_on': ['r']},
        ]

    manager = OrchestrationManager(
        lambda prompt, context: {'result': f"{context['agent_role']}:{prompt}"},
        planner=planner,
        max_workers=2,
        max_tasks_per_run=8,
    )
    try:
        run = manager.submit_objective('build feature')
        final = manager.wait(run['run_id'], timeout=3)
        assert final['state'] == 'succeeded'
        assert any(t['role'] == 'researcher' for t in final['tasks'])
        assert any(t['role'] == 'tester' for t in final['tasks'])
        assert any(t['role'] == 'coordinator' for t in final['tasks'])
        assert final['final_result']
    finally:
        manager.close()


def test_graph_validation_rejects_cycles_and_unknown_dependencies():
    cycle = [
        GraphTaskSpec('a', 'a', 'a', depends_on=['b']),
        GraphTaskSpec('b', 'b', 'b', depends_on=['a']),
    ]
    with pytest.raises(ValueError, match='cycle'):
        OrchestrationManager.validate_specs(cycle, 5)

    missing = [GraphTaskSpec('a', 'a', 'a', depends_on=['missing'])]
    with pytest.raises(ValueError, match='unknown dependencies'):
        OrchestrationManager.validate_specs(missing, 5)


def test_worker_cap_is_global_across_multiple_runs():
    lock = threading.Lock()
    active = 0
    max_active = 0

    def runner(prompt, _context):
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.08)
        with lock:
            active -= 1
        return {'result': prompt}

    manager = OrchestrationManager(runner, max_workers=2, max_tasks_per_run=6)
    try:
        first = manager.submit_graph(
            'first',
            [{'id': f'a{i}', 'prompt': f'a{i}'} for i in range(3)],
            add_coordinator=False,
        )
        second = manager.submit_graph(
            'second',
            [{'id': f'b{i}', 'prompt': f'b{i}'} for i in range(3)],
            add_coordinator=False,
        )
        assert manager.wait(first['run_id'], timeout=3)['state'] == 'succeeded'
        assert manager.wait(second['run_id'], timeout=3)['state'] == 'succeeded'
        assert max_active <= 2
    finally:
        manager.close()
