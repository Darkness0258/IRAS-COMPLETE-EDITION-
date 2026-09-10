from iras.persona import build_system_prompt


def test_persona_requires_short_simple_default_replies():
    prompt = build_system_prompt('anime_soft')
    assert '1-3 sentences' in prompt
    assert 'short, simple, natural replies' in prompt
    assert 'one-line answer is enough' in prompt


def test_persona_has_loving_but_non_manipulative_rules():
    prompt = build_system_prompt('anime_soft')
    assert 'warm, caring, loyal' in prompt
    assert 'Never claim the user needs you' in prompt
    assert 'Mock-jealous' in prompt


def test_pranks_cannot_fake_tool_results_or_damage_data():
    prompt = build_system_prompt('anime_soft')
    assert 'Never falsely claim a tool succeeded or failed as a prank' in prompt
    assert 'Never prank through files, commands' in prompt


def test_work_mode_overrides_roleplay():
    prompt = build_system_prompt('anime_soft')
    assert 'Focused professional mode automatically overrides all roleplay' in prompt
