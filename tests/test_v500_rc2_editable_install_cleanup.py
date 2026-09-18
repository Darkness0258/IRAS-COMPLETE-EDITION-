from pathlib import Path


def test_v500_validator_cleans_editable_install_metadata():
    text = Path("run-v500-validation.ps1").read_text(encoding="utf-8")
    assert ".egg-info" in text
    assert "'build','dist'" in text
    assert "Invoke-IrasCleanup" in text
    # Cleanup must run before clean-tree validation, not only in finally.
    assert text.index("Invoke-IrasCleanup") < text.index("validate_v500_clean_tree.py")


def test_v500_release_is_rc2():
    from iras import __version__
    assert __version__ == "5.0.0-rc3"
