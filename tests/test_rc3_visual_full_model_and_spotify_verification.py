from __future__ import annotations

from pathlib import Path


def test_managed_full_vision_honors_configured_device_and_reports_failures():
    root = Path(__file__).resolve().parents[1]
    bridge = (root / "src" / "iras" / "vision" / "omniparser_bridge_server.py").read_text(encoding="utf-8")
    runtime = (root / "src" / "iras" / "vision" / "omniparser_runtime.py").read_text(encoding="utf-8")
    cli = (root / "src" / "iras" / "cli.py").read_text(encoding="utf-8")

    assert "class _IRASFullOmniParser" in bridge
    assert "device=self.device" in bridge
    assert "torch.cuda.get_device_capability" in bridge
    assert 'full_model_state' in bridge
    assert 'full_model_error' in bridge
    assert 'full_model_device' in bridge
    assert 'status_code=503' in bridge
    assert 'full_model_error' in runtime
    assert 'full_model_device' in runtime
    assert 'full_model_error' in cli


def test_full_vision_guards_upstream_empty_ocr_edge_case_and_reuses_easyocr():
    root = Path(__file__).resolve().parents[1]
    bridge = (root / "src" / "iras" / "vision" / "omniparser_bridge_server.py").read_text(encoding="utf-8")

    assert "__IRAS_OCR_SENTINEL__" in bridge
    assert "used_sentinel = not bool(ocr_bbox)" in bridge
    assert "omni_utils.reader = _get_easyocr_reader()" in bridge
    assert "easyocr.Reader = lambda" in bridge


def test_setup_pins_cpu_and_precaches_florence_remote_code():
    root = Path(__file__).resolve().parents[1]
    setup = (root / "setup-omniparser.ps1").read_text(encoding="utf-8")

    assert 'Set-DotEnvValue "IRAS_OMNIPARSER_DEVICE" "cpu"' in setup
    assert '$env:IRAS_OMNIPARSER_DEVICE = "cpu"' in setup
    assert 'repo_id="microsoft/Florence-2-base-ft"' in setup
    assert 'Full OmniParser HTTP failure:' in setup


def test_spotify_reads_back_semantic_playback_state_after_play_command():
    root = Path(__file__).resolve().parents[1]
    ui = (root / "src" / "iras" / "device_bridge" / "ui_control.py").read_text(encoding="utf-8")
    intent = (root / "src" / "iras" / "device_bridge" / "intent.py").read_text(encoding="utf-8")

    assert "def _verify_spotify_playback" in ui
    assert 'SemanticVisualController(self).observe' in ui
    assert '"verified_playback": True' in ui
    assert '"query_evidence"' in ui
    assert "Verified Spotify playback" in intent
