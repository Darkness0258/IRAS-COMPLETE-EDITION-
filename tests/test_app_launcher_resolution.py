import pytest

from iras.device_bridge.app_catalog import (
    AppCatalog,
    AppEntry,
    ensure_safe_app_request,
)


def test_versioned_same_family_is_not_ambiguous():
    entries = [
        AppEntry(
            "Blender 5.2",
            "blender-aumid",
            "app_id",
            "start_apps",
        ),
        AppEntry(
            "Blender 5.2.1.0",
            "blender-new-aumid",
            "app_id",
            "start_apps",
        ),
    ]

    best = AppCatalog.best_match(
        "Blender",
        entries,
    )

    assert best.name.startswith(
        "Blender"
    )


def test_exact_executable_is_preferred_over_app_id_duplicate():
    entries = [
        AppEntry(
            "Acrobat",
            "acrobat-aumid",
            "app_id",
            "start_apps",
        ),
        AppEntry(
            "Acrobat",
            r"C:\Program Files\Adobe\Acrobat.exe",
            "exe",
            "app_paths",
            "Acrobat.exe",
        ),
    ]

    matches = AppCatalog.ranked_matches(
        "Acrobat",
        entries,
    )

    assert matches[0][1].kind == "exe"


def test_ranked_matches_keep_equivalent_fallbacks():
    entries = [
        AppEntry(
            "Example App 2.0",
            "example-aumid",
            "app_id",
            "start_apps",
        ),
        AppEntry(
            "Example App 2.1",
            r"C:\Apps\Example.exe",
            "exe",
            "app_paths",
            "Example.exe",
        ),
    ]

    matches = AppCatalog.ranked_matches(
        "Example App",
        entries,
    )

    assert len(matches) == 2
    assert {
        item[1].kind
        for item in matches
    } == {
        "app_id",
        "exe",
    }


@pytest.mark.parametrize(
    "name",
    [
        "PowerShell",
        "Windows Terminal",
        "Command Prompt",
        "Anaconda PowerShell Prompt",
        "regedit",
        "wsl",
    ],
)
def test_shell_admin_targets_remain_blocked(
    name,
):
    with pytest.raises(
        PermissionError
    ):
        ensure_safe_app_request(
            name
        )
