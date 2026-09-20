from __future__ import annotations

from typing import Any
import re


INSTALLER_READ_TOOLS = {
    "web_search",
    "http_get",
    "device_software_manager_status",
    "device_software_search",
    "device_software_show",
    "device_software_list",
    "device_software_upgrades",
    "device_detect_apps",
    "device_list_processes",
    "device_computer_status",
    "device_computer_observe",
    "device_computer_verify",
    "device_verify_state",
}

INSTALLER_ACTION_TOOLS = INSTALLER_READ_TOOLS | {
    "device_software_install",
    "device_software_upgrade",
    "device_software_uninstall",
    "device_software_prepare_url",
    "device_software_install_prepared",
    "device_open_app",
    "device_app_control",
    "device_observe_ui",
    "device_computer_action",
    "device_ui_find_text",
    "device_ui_click_text",
    "device_ui_type_text",
    "device_ui_wait_text",
}

INSTALLER_COMMANDS = {"search", "updates", "update", "uninstall", "status", "pause", "resume", "cancel"}
_URL_RE = re.compile(r"^https://", re.IGNORECASE)


def parse_installer_command(text: str) -> tuple[str, str] | None:
    raw = str(text or "").strip()
    lower = raw.casefold()
    if lower == "/install":
        return ("status", "")
    if not lower.startswith("/install "):
        return None
    remainder = raw[len("/install "):].strip()
    if not remainder:
        return ("status", "")
    first, _, rest = remainder.partition(" ")
    command = first.casefold()
    if command in INSTALLER_COMMANDS:
        return (command, rest.strip())
    if command == "url":
        return ("url", rest.strip())
    return ("run", remainder)


def is_direct_installer_url(value: str) -> bool:
    return bool(_URL_RE.match(str(value or "").strip()))


def build_software_install_graph(
    target: str, *, direct_url: bool = False, operation: str = "install"
) -> list[dict[str, Any]]:
    cleaned = " ".join(str(target or "").strip().split())
    operation = str(operation or "install").strip().casefold()
    if operation not in {"install", "update", "uninstall"}:
        raise ValueError("Software lifecycle operation must be install, update, or uninstall.")
    if not cleaned:
        raise ValueError("Software name, package ID, or HTTPS installer URL is required.")

    if direct_url:
        if operation != "install":
            raise ValueError("Direct HTTPS receipts are supported for installation only; update/uninstall use an installed package identity.")
        return [
            {
                "id": "install-research",
                "title": "Research installer source",
                "prompt": (
                    "Research the supplied installer URL and vendor identity using web_search/http_get. Confirm that the URL is HTTPS and appears to be "
                    "an official or vendor-controlled distribution location. Do not execute or download anything in this step. URL: " + cleaned
                ),
                "role": "researcher", "priority": 95, "depends_on": [], "max_retries": 1,
            },
            {
                "id": "install-prepare", "title": "Download and verify installer",
                "prompt": (
                    "Use device_software_prepare_url for this exact HTTPS URL. The device tool must download into the IRAS installer cache, compute SHA-256, "
                    "and validate Authenticode. Treat any invalid/unsigned signature, unsupported extension, redirect to a private address, or verification "
                    "failure as a hard blocker. Do not substitute another URL. URL: " + cleaned
                ),
                "role": "installer", "priority": 92, "depends_on": ["install-research"], "max_retries": 1,
            },
            {
                "id": "install-execute", "title": "Install verified package",
                "prompt": (
                    "Install only the receipt produced by device_software_prepare_url using device_software_install_prepared. Never execute an arbitrary path. "
                    "Do not bypass UAC, SmartScreen, signature checks, or IRAS authorization. If an interactive signed EXE installer opens, use bounded UI controls "
                    "only for the requested installation and stop on unexpected offers, publisher changes, or unrelated bundled software. Target: " + cleaned
                ),
                "role": "installer", "priority": 88, "depends_on": ["install-prepare"], "max_retries": 1,
            },
            {
                "id": "install-verify", "title": "Verify installation",
                "prompt": (
                    "Verify the requested software is installed using device_software_list, device_detect_apps, or other read-only verification. "
                    "Report concrete evidence and do not call the installation complete if verification is inconclusive. Target: " + cleaned
                ),
                "role": "reviewer", "priority": 80, "depends_on": ["install-execute"], "max_retries": 1,
                "continue_on_failure": True,
            },
        ]

    if operation == "update":
        update_all = cleaned.casefold() in {"all", "all packages", "everything"}
        return [
            {
                "id": "update-discover", "title": "Resolve installed package and update",
                "prompt": (
                    ("Use device_software_upgrades with no package ID and record the available updates. This request explicitly targets ALL upgradable packages. "
                     if update_all else
                     "Resolve the request to exactly one installed WinGet package ID using device_software_list/search/show, then use device_software_upgrades for that exact ID. "
                     "Never silently choose between multiple plausible installed packages. ")
                    + "Request: " + cleaned
                ),
                "role": "installer", "priority": 95, "depends_on": [], "max_retries": 1,
            },
            {
                "id": "update-execute", "title": "Apply software update",
                "prompt": (
                    ("The user explicitly requested update all. Use device_software_upgrade with all_packages=true. " if update_all else
                     "Use device_software_upgrade only for the exact installed package ID established upstream. ")
                    + "Do not use generic shell commands, do not bypass UAC/security controls, and preserve Remote/Master/local-policy authorization. Request: " + cleaned
                ),
                "role": "installer", "priority": 88, "depends_on": ["update-discover"], "max_retries": 1,
            },
            {
                "id": "update-verify", "title": "Verify updated state",
                "prompt": (
                    "Verify post-update state with device_software_list and device_software_upgrades. Record installed version evidence and any remaining update. "
                    "For update-all, report any packages still upgradeable instead of claiming blanket success. Request: " + cleaned
                ),
                "role": "reviewer", "priority": 80, "depends_on": ["update-execute"], "max_retries": 1,
                "continue_on_failure": True,
            },
        ]

    if operation == "uninstall":
        return [
            {
                "id": "uninstall-discover", "title": "Resolve installed package",
                "prompt": (
                    "Resolve the request to exactly one installed WinGet package ID using device_software_list/search/show. Confirm it is currently installed and "
                    "that package/publisher identity matches the request. Never silently choose on ambiguity. Request: " + cleaned
                ),
                "role": "installer", "priority": 95, "depends_on": [], "max_retries": 1,
            },
            {
                "id": "uninstall-execute", "title": "Uninstall exact package",
                "prompt": (
                    "Uninstall only the exact installed package ID established upstream using device_software_uninstall. Do not use generic shell commands, do not "
                    "remove unrelated dependencies, and do not bypass Windows/UAC or IRAS authorization. Request: " + cleaned
                ),
                "role": "installer", "priority": 88, "depends_on": ["uninstall-discover"], "max_retries": 1,
            },
            {
                "id": "uninstall-verify", "title": "Verify removal",
                "prompt": (
                    "Verify the exact package is absent using device_software_list and, where useful, app detection. If it remains installed, report the failure "
                    "and do not claim success. Request: " + cleaned
                ),
                "role": "reviewer", "priority": 80, "depends_on": ["uninstall-execute"], "max_retries": 1,
                "continue_on_failure": True,
            },
        ]

    return [
        {
            "id": "install-discover", "title": "Resolve software package",
            "prompt": (
                "Use device_software_manager_status and device_software_search to resolve the requested software to an exact WinGet package. "
                "Prefer the winget source, use publisher/package identity as evidence, and do not silently choose when multiple plausible packages remain. "
                "If ambiguous, report the candidates as a blocker instead of installing. Request: " + cleaned
            ),
            "role": "installer", "priority": 95, "depends_on": [], "max_retries": 1,
        },
        {
            "id": "install-inspect", "title": "Inspect exact package metadata",
            "prompt": (
                "For the single resolved package ID, use device_software_show and inspect publisher/source/version/installer metadata. If the package identity does "
                "not clearly match the user's request, stop and report the mismatch. Request: " + cleaned
            ),
            "role": "installer", "priority": 92, "depends_on": ["install-discover"], "max_retries": 1,
        },
        {
            "id": "install-execute", "title": "Install exact package",
            "prompt": (
                "Install only the exact verified package ID from the upstream result using device_software_install. Do not use generic shell commands, do not "
                "disable security controls, and do not bypass Windows/UAC. Preserve IRAS Remote/Master/local-policy authorization. Request: " + cleaned
            ),
            "role": "installer", "priority": 88, "depends_on": ["install-inspect"], "max_retries": 1,
        },
        {
            "id": "install-verify", "title": "Verify installed state",
            "prompt": (
                "Verify the exact package is installed using device_software_list and, where useful, app detection. Record the installed package/version as "
                "evidence. Do not claim success if the install process only launched or verification failed. Request: " + cleaned
            ),
            "role": "reviewer", "priority": 80, "depends_on": ["install-execute"], "max_retries": 1,
            "continue_on_failure": True,
        },
    ]


def installer_role_allowlist(role: str) -> set[str]:
    normalized = str(role or "").strip().casefold()
    if normalized == "installer":
        return set(INSTALLER_ACTION_TOOLS)
    if normalized in {"researcher", "reviewer"}:
        return set(INSTALLER_READ_TOOLS)
    if normalized == "coordinator":
        return set()
    return set(INSTALLER_READ_TOOLS)


def software_installer_status() -> dict[str, Any]:
    return {
        "enabled": True,
        "mode": "permissioned_software_lifecycle_agent",
        "package_manager": "winget",
        "direct_url": {
            "enabled": True,
            "https_only": True,
            "extensions": [".exe", ".msi"],
            "requires_valid_authenticode": True,
            "cache_receipt_required": True,
        },
        "authorization": (
            "Install/update/uninstall actions remain CRITICAL and pass through ToolRegistry, authenticated Remote session, local Remote policy, "
            "Master Control/approval, Emergency Stop, and Windows/UAC."
        ),
        "commands": [
            "/install search <software>",
            "/install <software-or-package-id>",
            "/install url <https-installer-url>",
            "/install updates [software-or-package-id]",
            "/install update <software-or-package-id>",
            "/install update all",
            "/install uninstall <software-or-package-id>",
            "/install status [run-id]",
            "/install pause [run-id]",
            "/install resume [run-id]",
            "/install cancel [run-id]",
        ],
    }
