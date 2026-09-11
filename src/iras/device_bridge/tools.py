from __future__ import annotations

from iras.models import (
    PermissionLevel,
)
from iras.tools.base import (
    Tool,
)


def make_tools(store):
    def request(
        action,
        arguments,
        device_id=None,
        timeout=35,
    ):
        return store.request_and_wait(
            action=action,
            arguments=arguments,
            device_id=device_id,
            timeout=timeout,
        )

    def device_list():
        return store.list_devices()

    def device_system_info(
        device_id=None,
    ):
        return request(
            "system_info",
            {},
            device_id,
        )

    def device_open_app(
        app,
        device_id=None,
    ):
        return request(
            "open_app",
            {
                "app": app,
            },
            device_id,
        )

    def device_open_url(
        url,
        device_id=None,
    ):
        return request(
            "open_url",
            {
                "url": url,
            },
            device_id,
        )

    def device_open_project(
        path,
        device_id=None,
    ):
        return request(
            "open_project",
            {
                "path": path,
            },
            device_id,
        )

    def device_list_files(
        path,
        include_hidden=False,
        device_id=None,
    ):
        return request(
            "list_directory",
            {
                "path": path,
                "include_hidden": (
                    include_hidden
                ),
            },
            device_id,
        )

    def device_read_text(
        path,
        max_chars=12000,
        device_id=None,
    ):
        return request(
            "read_text",
            {
                "path": path,
                "max_chars": (
                    max_chars
                ),
            },
            device_id,
        )

    def device_git_status(
        repo,
        device_id=None,
    ):
        return request(
            "git_status",
            {
                "repo": repo,
            },
            device_id,
        )

    def device_run_tests(
        project,
        device_id=None,
    ):
        return request(
            "run_tests",
            {
                "project": project,
            },
            device_id,
            timeout=90,
        )

    def device_capture_screen(
        device_id=None,
    ):
        return request(
            "capture_screen",
            {},
            device_id,
        )

    optional_device = {
        "device_id": {
            "type": "string",
            "description": (
                "Optional paired device ID. "
                "Omit to use the primary online Windows PC."
            ),
        }
    }

    return [
        Tool(
            "device_list",
            (
                "List paired IRAS computers and whether they are online. "
                "Use before device control when the target computer is ambiguous."
            ),
            {
                "type": "object",
                "properties": {},
            },
            device_list,
            PermissionLevel.READ,
        ),
        Tool(
            "device_system_info",
            "Get system information from the user's paired computer.",
            {
                "type": "object",
                "properties": {
                    **optional_device,
                },
            },
            device_system_info,
            PermissionLevel.READ,
        ),
        Tool(
            "device_open_app",
            (
                "Open an approved desktop application on the user's paired "
                "computer. Good for VS Code, Chrome, Spotify, Notepad, and Explorer."
            ),
            {
                "type": "object",
                "properties": {
                    "app": {
                        "type": "string",
                    },
                    **optional_device,
                },
                "required": [
                    "app",
                ],
            },
            device_open_app,
            PermissionLevel.SAFE_ACTION,
        ),
        Tool(
            "device_open_url",
            "Open an http/https URL in the paired computer's browser.",
            {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                    },
                    **optional_device,
                },
                "required": [
                    "url",
                ],
            },
            device_open_url,
            PermissionLevel.SAFE_ACTION,
        ),
        Tool(
            "device_open_project",
            (
                "Open an allowed local project directory in VS Code on the "
                "paired computer."
            ),
            {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                    },
                    **optional_device,
                },
                "required": [
                    "path",
                ],
            },
            device_open_project,
            PermissionLevel.SAFE_ACTION,
        ),
        Tool(
            "device_list_files",
            "List files in an allowed directory on the paired computer.",
            {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                    },
                    "include_hidden": {
                        "type": "boolean",
                    },
                    **optional_device,
                },
                "required": [
                    "path",
                ],
            },
            device_list_files,
            PermissionLevel.READ,
        ),
        Tool(
            "device_read_text",
            (
                "Read a text file from an allowed path on the user's paired "
                "computer. Use only when the user's request requires file content."
            ),
            {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                    },
                    "max_chars": {
                        "type": "integer",
                    },
                    **optional_device,
                },
                "required": [
                    "path",
                ],
            },
            device_read_text,
            PermissionLevel.READ,
        ),
        Tool(
            "device_git_status",
            "Run read-only git status in an allowed repository on the paired PC.",
            {
                "type": "object",
                "properties": {
                    "repo": {
                        "type": "string",
                    },
                    **optional_device,
                },
                "required": [
                    "repo",
                ],
            },
            device_git_status,
            PermissionLevel.READ,
        ),
        Tool(
            "device_run_tests",
            (
                "Run the detected project test suite on the paired computer. "
                "Only pytest or the package.json test script is allowed; no arbitrary shell."
            ),
            {
                "type": "object",
                "properties": {
                    "project": {
                        "type": "string",
                    },
                    **optional_device,
                },
                "required": [
                    "project",
                ],
            },
            device_run_tests,
            PermissionLevel.SAFE_ACTION,
        ),
        Tool(
            "device_capture_screen",
            (
                "Capture the paired computer's screen to a local IRAS screenshot "
                "file and return its path and dimensions."
            ),
            {
                "type": "object",
                "properties": {
                    **optional_device,
                },
            },
            device_capture_screen,
            PermissionLevel.READ,
        ),
    ]
