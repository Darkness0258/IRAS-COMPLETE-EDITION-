from iras.device_bridge.computer_use import UniversalComputerController


def _observation(
    *,
    elements=None,
    screenshot_hash="screen-a",
    visual_hash="visual-a",
    hwnd=100,
    title="Test App",
    vision_available=False,
):
    return {
        "elements": elements or [],
        "screenshot": {"sha256": screenshot_hash},
        "visual_sha256": visual_hash,
        "vision_available": vision_available,
        "foreground": {"hwnd": hwnd, "title": title},
    }


def test_semantic_pass_is_high_confidence_goal_verification():
    prior = _observation(
        screenshot_hash="screen-before",
        visual_hash="visual-before",
    )
    current = _observation(
        elements=[
            {
                "element_id": "vision:7",
                "label": "Metallica",
                "role": "text",
            }
        ],
        screenshot_hash="screen-after",
        visual_hash="visual-after",
        vision_available=True,
    )

    status, evidence = UniversalComputerController._evaluate_condition(
        current,
        condition="text_contains",
        target="Metallica",
        prior=prior,
    )
    assessment = UniversalComputerController._verification_assessment(
        condition="text_contains",
        status=status,
        evidence=evidence,
        observation=current,
        prior=prior,
        vision_escalated=True,
    )

    assert status == "PASS"
    assert assessment["semantic_goal_verified"] is True
    assert assessment["state_only_verified"] is False
    assert assessment["outcome_class"] == "semantic_goal"
    assert assessment["confidence_label"] == "high"
    assert assessment["confidence"] >= 0.95
    assert assessment["state_delta"]["screen_changed"] is True
    assert "vision" in assessment["evidence_sources"]


def test_screen_change_is_not_misreported_as_semantic_goal_success():
    prior = _observation(
        screenshot_hash="screen-before",
        visual_hash="visual-before",
    )
    current = _observation(
        elements=[
            {
                "element_id": "uia:1",
                "label": "Unrelated control",
                "role": "Button",
            }
        ],
        screenshot_hash="screen-after",
        visual_hash="visual-after",
    )

    status, evidence = UniversalComputerController._evaluate_condition(
        current,
        condition="text_contains",
        target="Wanted Result",
        prior=prior,
    )
    assessment = UniversalComputerController._verification_assessment(
        condition="text_contains",
        status=status,
        evidence=evidence,
        observation=current,
        prior=prior,
        vision_escalated=False,
    )

    assert status == "FAIL"
    assert assessment["semantic_goal_verified"] is False
    assert assessment["state_delta"]["screen_changed"] is True
    assert assessment["state_delta"]["visual_changed"] is True
    assert assessment["result"] == "not_verified"


def test_state_transition_pass_is_explicitly_state_only():
    prior = _observation(screenshot_hash="before")
    current = _observation(screenshot_hash="after")

    status, evidence = UniversalComputerController._evaluate_condition(
        current,
        condition="screen_changed",
        prior=prior,
    )
    assessment = UniversalComputerController._verification_assessment(
        condition="screen_changed",
        status=status,
        evidence=evidence,
        observation=current,
        prior=prior,
        vision_escalated=False,
    )

    assert status == "PASS"
    assert assessment["condition_verified"] is True
    assert assessment["semantic_goal_verified"] is False
    assert assessment["state_only_verified"] is True
    assert assessment["outcome_class"] == "state_transition"
    assert assessment["evidence_sources"] == ["screenshot_hash"]


def test_missing_prior_produces_inconclusive_low_confidence_assessment():
    current = _observation()

    status, evidence = UniversalComputerController._evaluate_condition(
        current,
        condition="visual_changed",
        prior=None,
    )
    assessment = UniversalComputerController._verification_assessment(
        condition="visual_changed",
        status=status,
        evidence=evidence,
        observation=current,
        prior=None,
        vision_escalated=False,
    )

    assert status == "INCONCLUSIVE"
    assert assessment["result"] == "inconclusive"
    assert assessment["confidence_label"] == "low"
    assert assessment["state_delta"]["available"] is False
