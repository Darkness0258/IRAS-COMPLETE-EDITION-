from __future__ import annotations

from iras.models import (
    PermissionLevel,
)
from iras.tools.base import (
    Tool,
)
from iras.remote_access import action_permission
from iras.device_bridge.remote_context import current_remote_command_context


def make_tools(store):
    def request(
        action,
        arguments,
        device_id=None,
        timeout=35,
    ):
        context = current_remote_command_context()
        remote_session_id = context.session_id or None
        return store.request_and_wait(
            action=action,
            arguments=arguments,
            device_id=device_id,
            timeout=timeout,
            remote_session_id=remote_session_id,
            permission_level=(
                int(action_permission(action, arguments))
                if remote_session_id
                else None
            ),
            requester_device=context.requester_device,
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

    def device_detect_apps(
        query="",
        limit=100,
        device_id=None,
    ):
        return request(
            "detect_apps",
            {
                "query": query,
                "limit": limit,
            },
            device_id,
        )

    def device_app_control(
        app,
        action,
        device_id=None,
    ):
        return request(
            "app_control",
            {
                "app": app,
                "action": action,
            },
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

    def device_observe_ui(
        app,
        ensure_open=True,
        max_elements=180,
        screenshot=True,
        device_id=None,
    ):
        return request(
            "observe_ui",
            {
                "app": app,
                "ensure_open": ensure_open,
                "max_elements": max_elements,
                "screenshot": screenshot,
            },
            device_id,
            timeout=45,
        )

    def device_semantic_action(
        app,
        action,
        target,
        text="",
        key="",
        role="",
        occurrence=1,
        replace=False,
        ensure_open=True,
        verify=True,
        device_id=None,
    ):
        return request(
            "semantic_action",
            {
                "app": app,
                "action": action,
                "target": target,
                "text": text,
                "key": key,
                "role": role,
                "occurrence": occurrence,
                "replace": replace,
                "ensure_open": ensure_open,
                "verify": verify,
            },
            device_id,
            timeout=55,
        )

    def device_computer_status(
        device_id=None,
    ):
        return request(
            "computer_status",
            {},
            device_id,
            timeout=20,
        )

    def device_computer_observe(
        vision="auto",
        scope="auto",
        max_elements=180,
        device_id=None,
    ):
        return request(
            "computer_observe",
            {
                "vision": vision,
                "scope": scope,
                "max_elements": max_elements,
            },
            device_id,
            timeout=150,
        )

    def device_computer_action(
        observation_id,
        action,
        element_id="",
        target_element_id="",
        text="",
        key="",
        keys=None,
        amount=0,
        replace=False,
        seconds=0.5,
        verify=True,
        device_id=None,
    ):
        return request(
            "computer_action",
            {
                "observation_id": observation_id,
                "action": action,
                "element_id": element_id,
                "target_element_id": target_element_id,
                "text": text,
                "key": key,
                "keys": keys or [],
                "amount": amount,
                "replace": replace,
                "seconds": seconds,
                "verify": verify,
            },
            device_id,
            timeout=160,
        )

    def device_computer_verify(
        condition,
        target="",
        prior_observation_id="",
        vision="auto",
        scope="auto",
        device_id=None,
    ):
        return request(
            "computer_verify",
            {
                "condition": condition,
                "target": target,
                "prior_observation_id": prior_observation_id,
                "vision": vision,
                "scope": scope,
            },
            device_id,
            timeout=150,
        )

    def device_whatsapp_open_chat(
        contact,
        device_id=None,
    ):
        return request(
            "whatsapp_open_chat",
            {
                "contact": contact,
            },
            device_id,
            timeout=240,
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
        app=None,
        device_id=None,
    ):
        arguments = {
            "command": command,
        }

        if app:
            arguments["app"] = app

        return request(
            "media_control",
            arguments,
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


    def device_screen_preview(max_width=1100, quality=62, device_id=None):
        return request("screen_preview", {"max_width": max_width, "quality": quality}, device_id, timeout=45)

    def device_list_processes(limit=300, device_id=None):
        return request("list_processes", {"limit": limit}, device_id)

    def device_kill_process(pid, device_id=None):
        return request("kill_process", {"pid": pid}, device_id)

    def device_write_text(path, content, append=False, device_id=None):
        return request("write_text", {"path": path, "content": content, "append": append}, device_id)

    def device_make_directory(path, device_id=None):
        return request("make_directory", {"path": path}, device_id)

    def device_copy_path(source, destination, device_id=None):
        return request("copy_path", {"source": source, "destination": destination}, device_id)

    def device_move_path(source, destination, device_id=None):
        return request("move_path", {"source": source, "destination": destination}, device_id)

    def device_delete_path(path, device_id=None):
        return request("delete_path", {"path": path}, device_id)

    def device_clipboard_get(device_id=None):
        return request("clipboard_get", {}, device_id)

    def device_clipboard_set(text, device_id=None):
        return request("clipboard_set", {"text": text}, device_id)

    def device_ui_find_text(text, exact=False, role="", vision="auto", device_id=None):
        return request("ui_find_text", {"text": text, "exact": exact, "role": role, "vision": vision}, device_id, timeout=150)

    def device_ui_click_text(text, exact=False, role="", vision="auto", verify_text="", device_id=None):
        return request("ui_click_text", {"text": text, "exact": exact, "role": role, "vision": vision, "verify_text": verify_text}, device_id, timeout=170)

    def device_ui_type_text(target, text, replace=True, exact=False, role="", vision="auto", device_id=None):
        return request("ui_type_text", {"target": target, "text": text, "replace": replace, "exact": exact, "role": role, "vision": vision}, device_id, timeout=170)

    def device_ui_wait_text(text, timeout=8.0, exact=False, role="", vision="auto", device_id=None):
        return request("ui_wait_text", {"text": text, "timeout": timeout, "exact": exact, "role": role, "vision": vision}, device_id, timeout=max(20, int(timeout) + 15))

    def device_ui_scroll_until_text(text, amount=-620, max_steps=6, vision="auto", device_id=None):
        return request("ui_scroll_until_text", {"text": text, "amount": amount, "max_steps": max_steps, "vision": vision}, device_id, timeout=180)

    def device_verify_state(kind, target="", vision="auto", scope="foreground", device_id=None):
        return request("verify_state", {"kind": kind, "target": target, "vision": vision, "scope": scope}, device_id, timeout=150)

    def device_power_action(action, device_id=None):
        return request("power_action", {"action": action}, device_id, timeout=30)

    def device_run_command(executable, args=None, cwd="", timeout=60.0, device_id=None):
        return request(
            "run_command",
            {"executable": executable, "args": args or [], "cwd": cwd, "timeout": timeout},
            device_id,
            timeout=max(30, min(int(timeout) + 15, 180)),
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
            "device_detect_apps",
            (
                "Auto-detect installed and running GUI applications on the "
                "paired Windows PC. Use it to discover an app name before "
                "control when the user is unsure what is installed."
            ),
            {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                    },
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 250,
                    },
                    **optional_device,
                },
            },
            device_detect_apps,
            PermissionLevel.READ,
        ),
        Tool(
            "device_app_control",
            (
                "Control an auto-detected installed/running GUI app. Supports "
                "focus, minimize, maximize, restore and graceful close, and "
                "returns verified_state when Windows confirms the requested state. "
                "Shells and administrative consoles remain blocked."
            ),
            {
                "type": "object",
                "properties": {
                    "app": {
                        "type": "string",
                    },
                    "action": {
                        "type": "string",
                        "enum": [
                            "focus",
                            "minimize",
                            "maximize",
                            "restore",
                            "close",
                        ],
                    },
                    **optional_device,
                },
                "required": [
                    "app",
                    "action",
                ],
            },
            device_app_control,
            PermissionLevel.SAFE_ACTION,
        ),
        Tool(
            "device_open_app",
            (
                "Open a safe auto-detected installed GUI application on the user's paired "
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
                "Interact with one safe auto-detected desktop application on the paired "
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
                        "description": (
                            "Installed/running GUI app name. IRAS auto-detects "
                            "the closest safe application match on Windows."
                        ),
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
            "device_observe_ui",
            (
                "Observe one safe Windows GUI application semantically. Returns "
                "the visible Windows UI Automation element tree (names, roles, "
                "automation IDs, values and screen bounds), plus an optional "
                "local screenshot path/hash for audit. Use this before acting "
                "on an unfamiliar interface. Do not invent coordinates."
            ),
            {
                "type": "object",
                "properties": {
                    "app": {
                        "type": "string",
                    },
                    "ensure_open": {
                        "type": "boolean",
                    },
                    "max_elements": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 300,
                    },
                    "screenshot": {
                        "type": "boolean",
                    },
                    **optional_device,
                },
                "required": [
                    "app",
                ],
            },
            device_observe_ui,
            PermissionLevel.READ,
        ),
        Tool(
            "device_semantic_action",
            (
                "Perform one bounded semantic action on a visible UI element "
                "inside one safe Windows GUI app. The target must be matched "
                "against a real element returned by Windows UI Automation; "
                "IRAS derives the click point from that observed element instead "
                "of inventing coordinates. Actions: click, double_click, focus, "
                "type_into, or press. Re-observes after the action by default."
            ),
            {
                "type": "object",
                "properties": {
                    "app": {
                        "type": "string",
                    },
                    "action": {
                        "type": "string",
                        "enum": [
                            "click",
                            "double_click",
                            "focus",
                            "type_into",
                            "press",
                        ],
                    },
                    "target": {
                        "type": "string",
                        "description": (
                            "Visible UI element name or automation ID observed "
                            "from device_observe_ui."
                        ),
                    },
                    "text": {
                        "type": "string",
                    },
                    "key": {
                        "type": "string",
                    },
                    "role": {
                        "type": "string",
                        "description": (
                            "Optional UI Automation role such as Button, Edit, "
                            "ListItem, MenuItem, TabItem, or Hyperlink."
                        ),
                    },
                    "occurrence": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 20,
                    },
                    "replace": {
                        "type": "boolean",
                    },
                    "ensure_open": {
                        "type": "boolean",
                    },
                    "verify": {
                        "type": "boolean",
                    },
                    **optional_device,
                },
                "required": [
                    "app",
                    "action",
                    "target",
                ],
            },
            device_semantic_action,
            PermissionLevel.SAFE_ACTION,
        ),
        Tool(
            "device_computer_status",
            (
                "Report v3.7 universal Windows multimodal capabilities, including "
                "OmniParser readiness/autostart state, scene-graph grounding, and "
                "fresh-observation safety guards."
            ),
            {
                "type": "object",
                "properties": {
                    **optional_device,
                },
            },
            device_computer_status,
            PermissionLevel.READ,
        ),
        Tool(
            "device_computer_observe",
            (
                "Observe the current Windows desktop for universal computer use. "
                "Returns the foreground window, screenshot metadata, Windows UI "
                "Automation controls plus a fused multimodal scene graph. When visual "
                "grounding is needed, local OmniParser is started automatically if a "
                "configured/discovered installation is available. Every actionable "
                "element has a stable element_id, confidence, provenance and grounded "
                "screen bounds. Use scope='desktop' for taskbar, desktop, "
                "system-tray, or multi-window visual tasks; otherwise foreground "
                "scope is preferred. Use vision='always' for custom-rendered "
                "interfaces that UIA cannot describe. Never invent coordinates, and "
                "do not act on low-confidence visual targets."
            ),
            {
                "type": "object",
                "properties": {
                    "vision": {
                        "type": "string",
                        "enum": ["off", "auto", "always"],
                    },
                    "scope": {
                        "type": "string",
                        "enum": ["auto", "foreground", "desktop"],
                    },
                    "max_elements": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 300,
                    },
                    **optional_device,
                },
            },
            device_computer_observe,
            PermissionLevel.READ,
        ),
        Tool(
            "device_computer_action",
            (
                "Perform one universal keyboard/mouse action grounded in a fresh "
                "device_computer_observe result. Mouse actions use element_id, "
                "never model-invented x/y coordinates. Supports move, click, "
                "double_click, right_click, type_into, press, hotkey, scroll, "
                "drag and wait. The action re-observes by default, but that only "
                "verifies input delivery; use device_computer_verify for the "
                "user's actual requested outcome."
            ),
            {
                "type": "object",
                "properties": {
                    "observation_id": {"type": "string"},
                    "action": {
                        "type": "string",
                        "enum": [
                            "move", "click", "double_click", "right_click",
                            "type_into", "press", "hotkey", "scroll", "drag",
                            "wait"
                        ],
                    },
                    "element_id": {"type": "string"},
                    "target_element_id": {"type": "string"},
                    "text": {"type": "string"},
                    "key": {"type": "string"},
                    "keys": {
                        "type": "array",
                        "items": {"type": "string"},
                        "maxItems": 3,
                    },
                    "amount": {
                        "type": "integer",
                        "minimum": -10,
                        "maximum": 10,
                    },
                    "replace": {"type": "boolean"},
                    "seconds": {
                        "type": "number",
                        "minimum": 0.05,
                        "maximum": 5.0,
                    },
                    "verify": {"type": "boolean"},
                    **optional_device,
                },
                "required": ["observation_id", "action"],
            },
            device_computer_action,
            PermissionLevel.SAFE_ACTION,
        ),
        Tool(
            "device_computer_verify",
            (
                "Freshly re-observe the desktop and verify a semantic computer "
                "outcome. Returns PASS, FAIL or INCONCLUSIVE. Conditions include "
                "element_exists, element_absent, text_contains, "
                "window_title_contains, screen_changed, screen_stable, "
                "visual_changed, visual_stable and foreground_changed. In auto "
                "mode semantic checks can escalate to OmniParser when UIA alone "
                "cannot prove the result. v3.5.6 also returns an explicit outcome "
                "decision: ACCEPT, RETRY, ESCALATE_VISION or RECOVER, with a "
                "bounded retry budget and goal-sufficiency signal."
            ),
            {
                "type": "object",
                "properties": {
                    "condition": {
                        "type": "string",
                        "enum": [
                            "element_exists", "element_absent", "text_contains",
                            "window_title_contains", "screen_changed",
                            "screen_stable", "visual_changed", "visual_stable",
                            "foreground_changed"
                        ],
                    },
                    "target": {"type": "string"},
                    "prior_observation_id": {"type": "string"},
                    "vision": {
                        "type": "string",
                        "enum": ["off", "auto", "always"],
                    },
                    "scope": {
                        "type": "string",
                        "enum": ["auto", "foreground", "desktop"],
                    },
                    **optional_device,
                },
                "required": ["condition"],
            },
            device_computer_verify,
            PermissionLevel.READ,
        ),
        Tool(
            "device_whatsapp_open_chat",
            (
                "Open one WhatsApp chat by display name and visually verify the "
                "right-pane chat header. This bounded controller fast path never "
                "types into the message composer, never presses Enter, and never "
                "sends a message. Each click/type is bound to a fresh observation; "
                "failed state-changing actions are never replayed automatically."
            ),
            {
                "type": "object",
                "properties": {
                    "contact": {"type": "string"},
                    **optional_device,
                },
                "required": ["contact"],
            },
            device_whatsapp_open_chat,
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
                    "app": {
                        "type": "string",
                        "description": "Optional target media application. Omit for auto-detection.",
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

        Tool(
            "device_screen_preview",
            "Return a bounded JPEG preview of the paired Windows desktop for an authenticated remote session.",
            {"type": "object", "properties": {"max_width": {"type": "integer", "minimum": 480, "maximum": 1600}, "quality": {"type": "integer", "minimum": 40, "maximum": 82}, **optional_device}},
            device_screen_preview,
            PermissionLevel.READ,
        ),
        Tool(
            "device_list_processes",
            "List running processes on the paired Windows PC.",
            {"type": "object", "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 1000}, **optional_device}},
            device_list_processes,
            PermissionLevel.READ,
        ),
        Tool(
            "device_kill_process",
            "Terminate a process by PID on the paired PC. Requires an authenticated elevated remote session.",
            {"type": "object", "properties": {"pid": {"type": "integer", "minimum": 1}, **optional_device}, "required": ["pid"]},
            device_kill_process,
            PermissionLevel.SYSTEM_ACTION,
        ),
        Tool(
            "device_write_text",
            "Create, overwrite, or append a UTF-8 text file inside the laptop's explicitly allowed roots.",
            {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}, "append": {"type": "boolean"}, **optional_device}, "required": ["path", "content"]},
            device_write_text,
            PermissionLevel.SYSTEM_ACTION,
        ),
        Tool(
            "device_make_directory",
            "Create a directory inside the paired laptop's allowed roots.",
            {"type": "object", "properties": {"path": {"type": "string"}, **optional_device}, "required": ["path"]},
            device_make_directory,
            PermissionLevel.SYSTEM_ACTION,
        ),
        Tool(
            "device_copy_path",
            "Copy a file or directory between allowed roots on the paired laptop.",
            {"type": "object", "properties": {"source": {"type": "string"}, "destination": {"type": "string"}, **optional_device}, "required": ["source", "destination"]},
            device_copy_path,
            PermissionLevel.SYSTEM_ACTION,
        ),
        Tool(
            "device_move_path",
            "Move or rename a file/directory between allowed roots on the paired laptop.",
            {"type": "object", "properties": {"source": {"type": "string"}, "destination": {"type": "string"}, **optional_device}, "required": ["source", "destination"]},
            device_move_path,
            PermissionLevel.SYSTEM_ACTION,
        ),
        Tool(
            "device_delete_path",
            "Permanently delete a file or directory inside an allowed root. Critical and never available without a full remote session plus local full-mode policy.",
            {"type": "object", "properties": {"path": {"type": "string"}, **optional_device}, "required": ["path"]},
            device_delete_path,
            PermissionLevel.CRITICAL,
        ),
        Tool(
            "device_clipboard_get",
            "Read text from the Windows clipboard on the paired laptop.",
            {"type": "object", "properties": {**optional_device}},
            device_clipboard_get,
            PermissionLevel.READ,
        ),
        Tool(
            "device_clipboard_set",
            "Set text on the Windows clipboard on the paired laptop.",
            {"type": "object", "properties": {"text": {"type": "string"}, **optional_device}, "required": ["text"]},
            device_clipboard_set,
            PermissionLevel.SYSTEM_ACTION,
        ),
        Tool(
            "device_ui_find_text",
            "Find visible text using deterministic UIA/OCR/vision grounding without changing state.",
            {"type": "object", "properties": {"text": {"type": "string"}, "exact": {"type": "boolean"}, "role": {"type": "string"}, "vision": {"type": "string", "enum": ["off", "auto", "always"]}, **optional_device}, "required": ["text"]},
            device_ui_find_text,
            PermissionLevel.READ,
        ),
        Tool(
            "device_ui_click_text",
            "Click exactly one freshly grounded visible text target, then optionally verify fresh destination text. Never replays the click.",
            {"type": "object", "properties": {"text": {"type": "string"}, "exact": {"type": "boolean"}, "role": {"type": "string"}, "vision": {"type": "string", "enum": ["off", "auto", "always"]}, "verify_text": {"type": "string"}, **optional_device}, "required": ["text"]},
            device_ui_click_text,
            PermissionLevel.SYSTEM_ACTION,
        ),
        Tool(
            "device_ui_type_text",
            "Type into exactly one freshly grounded visible field. A new observation is required before any subsequent state-changing action.",
            {"type": "object", "properties": {"target": {"type": "string"}, "text": {"type": "string"}, "replace": {"type": "boolean"}, "exact": {"type": "boolean"}, "role": {"type": "string"}, "vision": {"type": "string", "enum": ["off", "auto", "always"]}, **optional_device}, "required": ["target", "text"]},
            device_ui_type_text,
            PermissionLevel.SYSTEM_ACTION,
        ),
        Tool(
            "device_ui_wait_text",
            "Wait using read-only fresh observations until text appears or a bounded timeout expires.",
            {"type": "object", "properties": {"text": {"type": "string"}, "timeout": {"type": "number", "minimum": 0.5, "maximum": 30}, "exact": {"type": "boolean"}, "role": {"type": "string"}, "vision": {"type": "string", "enum": ["off", "auto", "always"]}, **optional_device}, "required": ["text"]},
            device_ui_wait_text,
            PermissionLevel.READ,
        ),
        Tool(
            "device_ui_scroll_until_text",
            "Boundedly scroll with a fresh observation before each scroll until text is found. No scroll action is replayed from a consumed observation.",
            {"type": "object", "properties": {"text": {"type": "string"}, "amount": {"type": "integer"}, "max_steps": {"type": "integer", "minimum": 1, "maximum": 12}, "vision": {"type": "string", "enum": ["off", "auto", "always"]}, **optional_device}, "required": ["text"]},
            device_ui_scroll_until_text,
            PermissionLevel.SYSTEM_ACTION,
        ),
        Tool(
            "device_verify_state",
            "Semantically verify a terminal state such as visible text, foreground title, file existence, directory existence, or a running process.",
            {"type": "object", "properties": {"kind": {"type": "string", "enum": ["file_exists", "file_absent", "directory_exists", "foreground_title_contains", "screen_text", "process_running"]}, "target": {"type": "string"}, "vision": {"type": "string", "enum": ["off", "auto", "always"]}, "scope": {"type": "string", "enum": ["auto", "foreground", "desktop"]}, **optional_device}, "required": ["kind"]},
            device_verify_state,
            PermissionLevel.READ,
        ),
        Tool(
            "device_power_action",
            "Lock, restart, or shut down the paired Windows laptop. Restart/shutdown require a full remote session and local power opt-in.",
            {"type": "object", "properties": {"action": {"type": "string", "enum": ["lock", "restart", "shutdown"]}, **optional_device}, "required": ["action"]},
            device_power_action,
            PermissionLevel.CRITICAL,
        ),

        Tool(
            "device_run_command",
            "Run one explicitly named executable with an argv list and shell=False. Critical: requires a full remote session plus the laptop's local command-execution opt-in.",
            {"type": "object", "properties": {"executable": {"type": "string"}, "args": {"type": "array", "items": {"type": "string"}, "maxItems": 64}, "cwd": {"type": "string"}, "timeout": {"type": "number", "minimum": 1, "maximum": 300}, **optional_device}, "required": ["executable"]},
            device_run_command,
            PermissionLevel.CRITICAL,
        ),
    ]
