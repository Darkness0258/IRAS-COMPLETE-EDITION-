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

    def device_interact_app(
        app,
        actions,
        ensure_open=True,
        device_id=None,
    ):
        return request(
            "interact_app",
            {
                "app": app,
                "actions": actions,
                "ensure_open": (
                    ensure_open
                ),
            },
            device_id,
            timeout=50,
        )

    def device_spotify_search(
        query,
        device_id=None,
    ):
        return request(
            "spotify_search",
            {
                "query": query,
            },
            device_id,
            timeout=45,
        )

    def device_spotify_play(
        query,
        device_id=None,
    ):
        return request(
            "spotify_play",
            {
                "query": query,
            },
            device_id,
            timeout=45,
        )

    def device_media_control(
        command,
        device_id=None,
    ):
        return request(
            "media_control",
            {
                "command": command,
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
            "device_interact_app",
            (
                "Interact with one approved desktop application on the paired "
                "Windows PC. Use this for typing, searching, pressing keys, "
                "scrolling, or clicking known coordinates. It can launch and "
                "focus the app first. For Chrome search use Ctrl+L, type the "
                "query, then Enter."
            ),
            {
                "type": "object",
                "properties": {
                    "app": {
                        "type": "string",
                        "enum": [
                            "chrome",
                            "spotify",
                            "code",
                            "vscode",
                            "visual studio code",
                            "notepad",
                            "explorer",
                            "file explorer",
                        ],
                    },
                    "actions": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 15,
                        "items": {
                            "type": "object",
                            "properties": {
                                "action": {
                                    "type": "string",
                                    "enum": [
                                        "wait",
                                        "type",
                                        "press",
                                        "hotkey",
                                        "click",
                                        "double_click",
                                        "scroll",
                                    ],
                                },
                                "text": {
                                    "type": "string",
                                },
                                "key": {
                                    "type": "string",
                                },
                                "keys": {
                                    "type": "array",
                                    "items": {
                                        "type": "string",
                                    },
                                },
                                "x": {
                                    "type": "integer",
                                },
                                "y": {
                                    "type": "integer",
                                },
                                "amount": {
                                    "type": "integer",
                                },
                                "seconds": {
                                    "type": "number",
                                },
                            },
                            "required": [
                                "action",
                            ],
                        },
                    },
                    "ensure_open": {
                        "type": "boolean",
                    },
                    **optional_device,
                },
                "required": [
                    "app",
                    "actions",
                ],
            },
            device_interact_app,
            PermissionLevel.SAFE_ACTION,
        ),
        Tool(
            "device_spotify_search",
            (
                "Open Spotify search for any requested song, artist, album, "
                "playlist, podcast, or free-text query without starting "
                "playback."
            ),
            {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                    },
                    **optional_device,
                },
                "required": [
                    "query",
                ],
            },
            device_spotify_search,
            PermissionLevel.SAFE_ACTION,
        ),
        Tool(
            "device_spotify_play",
            (
                "Search for and start a requested song/artist/query in the "
                "Spotify Windows desktop app. Use this instead of generic UI "
                "actions when the user explicitly asks Spotify to play music. "
                "The result confirms that the command was sent, not that "
                "playback was independently verified."
            ),
            {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "Song title, artist, or Spotify search query."
                        ),
                    },
                    **optional_device,
                },
                "required": [
                    "query",
                ],
            },
            device_spotify_play,
            PermissionLevel.SAFE_ACTION,
        ),
        Tool(
            "device_media_control",
            (
                "Send a bounded Windows media key to the paired PC. Use for "
                "follow-ups such as play the song, pause, resume, next track, "
                "previous track, stop, mute, or volume changes. This sends a "
                "media command but cannot independently verify playback state."
            ),
            {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "enum": [
                            "play",
                            "pause",
                            "resume",
                            "play_pause",
                            "next",
                            "previous",
                            "stop",
                            "mute",
                            "unmute",
                            "volume_up",
                            "volume_down",
                            "shuffle_toggle",
                            "repeat_toggle",
                            "like_toggle",
                            "open_queue",
                            "open_liked_songs",
                            "open_now_playing",
                        ],
                    },
                    **optional_device,
                },
                "required": [
                    "command",
                ],
            },
            device_media_control,
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
