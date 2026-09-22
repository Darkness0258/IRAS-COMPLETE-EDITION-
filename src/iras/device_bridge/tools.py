from __future__ import annotations

from iras.models import (
    PermissionLevel,
)
from iras.tools.base import (
    Tool,
)
from iras.remote_access import action_permission
from iras.device_bridge.remote_context import current_remote_command_context
from pathlib import PureWindowsPath
import re


def _windows_path_within(path: PureWindowsPath, root: PureWindowsPath) -> bool:
    path_parts = [part.casefold() for part in path.parts]
    root_parts = [part.casefold() for part in root.parts]
    return len(path_parts) >= len(root_parts) and path_parts[:len(root_parts)] == root_parts


def _spotify_cloud_terms(query: str) -> list[str]:
    normalized = re.sub(r"[^a-z0-9]+", " ", str(query or "").casefold()).strip()
    stop = {
        "play", "spotify", "song", "songs", "music", "track", "tracks",
        "please", "open", "and", "the", "a", "an", "on", "my",
    }
    return [part for part in normalized.split() if len(part) >= 2 and part not in stop]




def _spotify_cloud_label_matches_query(query: str, label: str) -> bool:
    terms = _spotify_cloud_terms(query)
    if not terms:
        return False
    normalized = re.sub(r"[^a-z0-9]+", " ", str(label or "").casefold()).strip()
    tokens = set(normalized.split())
    return all(term in tokens for term in terms)

def _spotify_cloud_visual_verification(query: str, observation) -> dict:
    """Conservative second-opinion verification from computer_observe output.

    This is deliberately stricter than simply finding query text anywhere in
    Spotify.  It requires a visible Pause state plus query evidence in a likely
    now-playing region (bottom transport area or right-side detail panel).
    """
    data = observation if isinstance(observation, dict) else {}
    foreground = data.get("foreground") if isinstance(data.get("foreground"), dict) else {}
    title = str(foreground.get("title") or "")
    elements = list(data.get("elements") or [])
    rect = foreground.get("rect") if isinstance(foreground.get("rect"), dict) else {}
    left = float(rect.get("left") or 0)
    top = float(rect.get("top") or 0)
    width = max(1.0, float(rect.get("width") or 1))
    height = max(1.0, float(rect.get("height") or 1))
    terms = _spotify_cloud_terms(query)
    playing = False
    evidence = []

    for item in elements:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or item.get("name") or "").strip()
        norm = re.sub(r"[^a-z0-9]+", " ", label.casefold()).strip()
        if not norm:
            continue
        if norm == "pause" or norm.startswith("pause ") or " pause " in f" {norm} ":
            playing = True
        item_rect = item.get("rect") if isinstance(item.get("rect"), dict) else {}
        cx = float(item_rect.get("left") or 0) + float(item_rect.get("width") or 0) / 2
        cy = float(item_rect.get("top") or 0) + float(item_rect.get("height") or 0) / 2
        rx = (cx - left) / width
        ry = (cy - top) / height
        in_now_playing_region = ry >= 0.74 or rx >= 0.72
        if in_now_playing_region and terms and _spotify_cloud_label_matches_query(query, label):
            if label not in evidence:
                evidence.append(label)

    verified = bool("spotify" in title.casefold() and playing and evidence)
    return {
        "verified": verified,
        "playing": playing,
        "query_match": bool(evidence),
        "query_evidence": evidence[:8],
        "foreground_title": title,
        "source": "cloud_agent_computer_observe",
        "vision_status": data.get("vision_status"),
        "vision_available": bool(data.get("vision_available")),
        "vision_element_count": int(data.get("vision_element_count") or 0),
    }


def _bind_project_arguments(action: str, arguments: dict, project_root: str) -> dict:
    """Bind project-scoped device tools to the preflight-verified Windows root.

    Agents sometimes emit placeholders such as `.` or `IRAS` even after the
    project preflight resolved an absolute Windows path. Rewriting relative
    project arguments here makes the verified workspace an enforcement
    boundary instead of a prompt-only hint. Absolute paths outside the
    verified project are rejected before they reach the device queue.
    """
    root_text = str(project_root or "").strip()
    if not root_text:
        return dict(arguments or {})

    root = PureWindowsPath(root_text)
    bound = dict(arguments or {})
    key_by_action = {
        "git_status": "repo",
        "git_diff": "repo",
        "git_log": "repo",
        "run_tests": "project",
        "search_text": "root",
        "list_directory": "path",
        "read_text": "path",
        "read_text_range": "path",
        "file_info": "path",
        "write_text": "path",
        "replace_text": "path",
        "make_directory": "path",
        "open_project": "path",
    }
    key = key_by_action.get(str(action or ""))
    if not key:
        return bound

    raw = str(bound.get(key) or "").strip()
    aliases = {"", ".", "./", "iras", "project", "repo", "repository"}
    if raw.casefold() in aliases:
        candidate = root
    else:
        candidate = PureWindowsPath(raw)
        if not candidate.is_absolute():
            candidate = root / candidate

    if not _windows_path_within(candidate, root):
        raise PermissionError(
            "Project-scoped remote tool path is outside the preflight-verified project root."
        )

    bound[key] = str(candidate)
    return bound



def make_tools(store):
    def request(
        action,
        arguments,
        device_id=None,
        timeout=35,
    ):
        context = current_remote_command_context()
        remote_session_id = context.session_id or None
        effective_device_id = device_id or context.device_id or None
        arguments = _bind_project_arguments(action, arguments, context.project_root)
        return store.request_and_wait(
            action=action,
            arguments=arguments,
            device_id=effective_device_id,
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

    def device_desktop_context(
        vision="auto",
        scope="auto",
        max_elements=220,
        process_limit=160,
        include_process_paths=False,
        device_id=None,
    ):
        return request(
            "desktop_context",
            {
                "vision": vision,
                "scope": scope,
                "max_elements": max_elements,
                "process_limit": process_limit,
                "include_process_paths": include_process_paths,
            },
            device_id,
            timeout=180,
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
        primary_error = None
        try:
            output = request(
                "spotify_play",
                {
                    "query": query,
                },
                device_id,
                timeout=55,
            )
        except RuntimeError as exc:
            # A current bridge already fails closed when semantic playback
            # cannot be verified.  A stale bridge may still have performed the
            # action, so take one fresh OmniParser-backed observation before
            # deciding whether the operation really failed.
            primary_error = exc
            output = {}

        # The in-process LocalDeviceBridgeStore already runs the current
        # semantic Spotify controller directly. Cloud/remote stores always take
        # an independent fresh observation even when the bridge itself claims
        # verified playback; this prevents stale/legacy false positives.
        if store.__class__.__name__ == "LocalDeviceBridgeStore":
            if primary_error is not None:
                raise primary_error
            return output

        try:
            observation = request(
                "computer_observe",
                {
                    "vision": "always",
                    "scope": "foreground",
                    "max_elements": 260,
                },
                device_id,
                timeout=150,
            )
            fallback = _spotify_cloud_visual_verification(query, observation)
        except Exception as observe_exc:
            fallback = {
                "verified": False,
                "source": "cloud_agent_computer_observe",
                "error": f"{type(observe_exc).__name__}: {observe_exc}",
            }

        if fallback.get("verified"):
            merged = dict(output) if isinstance(output, dict) else {}
            merged.update({
                "app": "spotify",
                "query": query,
                "verified_playback": True,
                "playback_verification": fallback,
                "now_playing_candidates": list(fallback.get("query_evidence") or []),
                "query_evidence": list(fallback.get("query_evidence") or []),
                "verification_source": fallback.get("source"),
            })
            if primary_error is not None:
                merged["primary_bridge_error"] = str(primary_error)[:500]
            return merged

        if primary_error is not None:
            raise RuntimeError(
                f"{primary_error} Cloud visual verification also failed: "
                f"playing={fallback.get('playing')} query_match={fallback.get('query_match')} "
                f"evidence={fallback.get('query_evidence', [])}"
            ) from primary_error

        if isinstance(output, dict):
            output = dict(output)
            output["cloud_visual_verification"] = fallback
            if output.get("verified_playback"):
                output["bridge_verified_playback"] = True
                output["verified_playback"] = False
                output["now_playing_candidates"] = []
                output["query_evidence"] = []
        return output

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

    def device_read_text_range(path, start_line=1, end_line=200, device_id=None):
        return request(
            "read_text_range",
            {"path": path, "start_line": start_line, "end_line": end_line},
            device_id,
        )

    def device_search_text(root, query, pattern="*", regex=False, case_sensitive=False, max_matches=120, max_files=600, device_id=None):
        return request(
            "search_text",
            {
                "root": root, "query": query, "pattern": pattern, "regex": regex,
                "case_sensitive": case_sensitive, "max_matches": max_matches, "max_files": max_files,
            },
            device_id,
            timeout=60,
        )

    def device_file_info(path, sha256=True, device_id=None):
        return request("file_info", {"path": path, "sha256": sha256}, device_id)

    def device_find_projects(query="", max_depth=3, max_results=20, device_id=None):
        return request(
            "find_projects",
            {"query": query, "max_depth": max_depth, "max_results": max_results},
            device_id,
            timeout=45,
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

    def device_git_diff(repo, path="", staged=False, max_chars=30000, device_id=None):
        return request(
            "git_diff",
            {"repo": repo, "path": path, "staged": staged, "max_chars": max_chars},
            device_id,
        )

    def device_git_log(repo, limit=20, device_id=None):
        return request("git_log", {"repo": repo, "limit": limit}, device_id)

    def device_run_tests(
        project,
        target="",
        timeout=180.0,
        device_id=None,
    ):
        return request(
            "run_tests",
            {
                "project": project,
                "target": target,
                "timeout": timeout,
            },
            device_id,
            timeout=max(30, min(int(timeout) + 5, 180)),
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

    def device_list_processes(limit=300, query="", only_apps=False, sort_by="memory", include_path=False, track_changes=True, device_id=None):
        return request(
            "list_processes",
            {
                "limit": limit,
                "query": query,
                "only_apps": only_apps,
                "sort_by": sort_by,
                "include_path": include_path,
                "track_changes": track_changes,
            },
            device_id,
            timeout=60,
        )

    def device_kill_process(pid, device_id=None):
        return request("kill_process", {"pid": pid}, device_id)

    def device_write_text(path, content, append=False, device_id=None):
        return request("write_text", {"path": path, "content": content, "append": append}, device_id)

    def _quick_code_workspace(info):
        roots = [str(item).strip() for item in (info.get("allowed_roots") or []) if str(item).strip()]
        user = str(info.get("user") or "").strip()
        folded = [item.casefold() for item in roots]

        # Prefer a normal project location when the paired machine exposes it.
        for root, lower in zip(roots, folded):
            if lower.rstrip("\\") == "d:\\projects":
                return str(PureWindowsPath(root) / "IRAS-QuickCode")
        for root, lower in zip(roots, folded):
            if lower.rstrip("\\") == "d:":
                return str(PureWindowsPath(root) / "Projects" / "IRAS-QuickCode")
        for root, lower in zip(roots, folded):
            if "\\users\\" in lower:
                return str(PureWindowsPath(root) / "Documents" / "IRAS-QuickCode")
        for root, lower in zip(roots, folded):
            if lower.rstrip("\\") == "c:" and user:
                return str(PureWindowsPath(root) / "Users" / user / "Documents" / "IRAS-QuickCode")
        if roots:
            return str(PureWindowsPath(roots[0]) / "IRAS-QuickCode")
        raise RuntimeError("The paired PC did not report an allowed filesystem root.")

    def _quick_code_filename(filename, language):
        raw = PureWindowsPath(str(filename or "").strip()).name
        ext_by_language = {
            "python": ".py", "py": ".py",
            "javascript": ".js", "js": ".js",
            "typescript": ".ts", "ts": ".ts",
            "html": ".html", "css": ".css",
            "java": ".java", "c": ".c", "cpp": ".cpp", "c++": ".cpp",
            "csharp": ".cs", "c#": ".cs", "rust": ".rs", "go": ".go",
        }
        if not raw:
            raw = "main" + ext_by_language.get(str(language or "python").casefold(), ".txt")
        raw = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", raw).strip(" .")[:120]
        if not raw:
            raw = "main.py"
        if "." not in PureWindowsPath(raw).name:
            raw += ext_by_language.get(str(language or "python").casefold(), ".txt")
        return raw

    def device_quick_code(content, filename="", language="python", open_in_vscode=True, device_id=None):
        """Create one verified source file and open its workspace in VS Code.

        This deliberately composes existing bridge actions instead of adding a
        new privileged Windows executor command. Every filesystem operation is
        still checked against the configured bridge roots and every remote
        action keeps its existing permission classification.
        """
        text = str(content or "")
        if not text.strip():
            raise ValueError("Quick Code requires non-empty source content.")
        if len(text) > 20_000:
            raise ValueError("Quick Code source is limited to 20,000 characters.")

        info = request("system_info", {}, device_id)
        if not isinstance(info, dict):
            raise RuntimeError("The paired PC did not return system information.")
        workspace = _quick_code_workspace(info)
        name = _quick_code_filename(filename, language)
        path = str(PureWindowsPath(workspace) / name)

        request("make_directory", {"path": workspace}, device_id)
        write_result = request("write_text", {"path": path, "content": text, "append": False}, device_id)
        verify_result = request("read_text", {"path": path, "max_chars": 20_000}, device_id)
        verified_text = ""
        if isinstance(verify_result, dict):
            verified_text = str(verify_result.get("content") or verify_result.get("text") or "")
        elif isinstance(verify_result, str):
            verified_text = verify_result
        if verified_text != text:
            raise RuntimeError("Quick Code wrote the file but read-back verification did not match exactly.")

        opened = None
        focused_file = False
        if bool(open_in_vscode):
            opened = request("open_project", {"path": workspace}, device_id, timeout=45)
            # Open the freshly verified file through VS Code Quick Open. Failure
            # here does not invalidate the file creation itself; the result says
            # whether editor focusing also completed.
            try:
                focus = request(
                    "interact_app",
                    {
                        "app": "code",
                        "ensure_open": True,
                        "actions": [
                            {"action": "wait", "seconds": 0.5},
                            {"action": "hotkey", "keys": ["ctrl", "p"]},
                            {"action": "type", "text": name},
                            {"action": "press", "key": "enter"},
                        ],
                    },
                    device_id,
                    timeout=50,
                )
                focused_file = bool(focus)
            except Exception:
                focused_file = False

        return {
            "created": True,
            "verified": True,
            "path": path,
            "workspace": workspace,
            "filename": name,
            "language": str(language or ""),
            "bytes": len(text.encode("utf-8")),
            "vscode_opened": bool(opened),
            "file_focused": focused_file,
            "write_result": write_result,
        }

    def device_quick_code_run_in_vscode(path, language="", sample_input="5", device_id=None):
        """Run one previously created Quick Code file inside VS Code's integrated terminal.

        The file must already exist inside the paired device's allowed roots. This
        composes existing read/open/interact/observe bridge operations and does not
        add a new privileged Windows executor command.
        """
        raw_path = str(path or "").strip()
        if not raw_path:
            raise ValueError("Quick Code VS Code run requires a file path.")

        verified = request("read_text", {"path": raw_path, "max_chars": 20_000}, device_id)
        if isinstance(verified, dict):
            source = str(verified.get("content") or verified.get("text") or "")
        else:
            source = str(verified or "")
        if not source.strip():
            raise RuntimeError("Quick Code file is empty or could not be verified before execution.")

        win_path = PureWindowsPath(raw_path)
        workspace = str(win_path.parent)
        filename = win_path.name
        ext = win_path.suffix.casefold()
        lang = str(language or "").strip().casefold()
        if not lang:
            lang = {
                ".py": "python", ".js": "javascript", ".ts": "typescript",
                ".java": "java", ".c": "c", ".cpp": "cpp", ".cs": "csharp",
                ".rs": "rust", ".go": "go", ".html": "html",
            }.get(ext, "")

        request("open_project", {"path": workspace}, device_id, timeout=45)
        focus = request(
            "interact_app",
            {
                "app": "code",
                "ensure_open": True,
                "actions": [
                    {"action": "wait", "seconds": 0.4},
                    {"action": "hotkey", "keys": ["ctrl", "p"]},
                    {"action": "type", "text": filename},
                    {"action": "press", "key": "enter"},
                ],
            },
            device_id,
            timeout=50,
        )

        quoted = '"' + filename.replace('"', '') + '"'
        if lang in {"python", "py"} or ext == ".py":
            command = f"python {quoted}"
        elif lang in {"javascript", "js"} or ext == ".js":
            command = f"node {quoted}"
        elif lang in {"typescript", "ts"} or ext == ".ts":
            command = f"npx tsx {quoted}"
        else:
            raise ValueError(
                "Quick Code VS Code execution currently supports Python, JavaScript, and TypeScript files."
            )

        actions = [
            {"action": "hotkey", "keys": ["ctrl", "shift", "p"]},
            {"action": "type", "text": "Terminal: Create New Terminal"},
            {"action": "press", "key": "enter"},
            {"action": "wait", "seconds": 0.8},
            {"action": "type", "text": command},
            {"action": "press", "key": "enter"},
            {"action": "wait", "seconds": 0.8},
        ]

        input_sent = False
        if (lang in {"python", "py"} or ext == ".py") and "input(" in source:
            value = str(sample_input or "5").replace("\r", " ").replace("\n", " ")[:120]
            if value:
                actions.extend([
                    {"action": "type", "text": value},
                    {"action": "press", "key": "enter"},
                    {"action": "wait", "seconds": 0.8},
                ])
                input_sent = True

        run_result = request(
            "interact_app",
            {"app": "code", "ensure_open": True, "actions": actions},
            device_id,
            timeout=60,
        )

        observation = None
        try:
            observation = request(
                "observe_ui",
                {"app": "code", "ensure_open": True, "max_elements": 180, "screenshot": False},
                device_id,
                timeout=45,
            )
        except Exception:
            observation = None

        return {
            "executed": True,
            "path": raw_path,
            "workspace": workspace,
            "filename": filename,
            "language": lang,
            "command": command,
            "input_sent": input_sent,
            "file_focused": bool(focus),
            "terminal_action": run_result,
            "observation": observation,
        }

    def device_replace_text(path, old_text, new_text, count=1, device_id=None):
        return request(
            "replace_text",
            {"path": path, "old_text": old_text, "new_text": new_text, "count": count},
            device_id,
        )

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

    def device_software_manager_status(device_id=None):
        return request("software_manager_status", {}, device_id, timeout=30)

    def device_software_search(query, source="winget", count=20, device_id=None):
        return request(
            "software_search",
            {"query": query, "source": source, "count": count},
            device_id,
            timeout=75,
        )

    def device_software_show(package_id, source="winget", device_id=None):
        return request(
            "software_show",
            {"package_id": package_id, "source": source},
            device_id,
            timeout=75,
        )

    def device_software_list(query="", package_id="", device_id=None):
        return request(
            "software_list",
            {"query": query, "package_id": package_id},
            device_id,
            timeout=75,
        )

    def device_software_upgrades(package_id="", source="winget", device_id=None):
        return request(
            "software_upgrades",
            {"package_id": package_id, "source": source},
            device_id,
            timeout=105,
        )

    def device_software_install(package_id, source="winget", version="", scope="", device_id=None):
        return request(
            "software_install",
            {"package_id": package_id, "source": source, "version": version, "scope": scope},
            device_id,
            timeout=360,
        )

    def device_software_upgrade(package_id="", source="winget", all_packages=False, device_id=None):
        return request(
            "software_upgrade",
            {"package_id": package_id, "source": source, "all_packages": bool(all_packages)},
            device_id,
            timeout=660,
        )

    def device_software_uninstall(package_id, source="winget", device_id=None):
        return request(
            "software_uninstall",
            {"package_id": package_id, "source": source},
            device_id,
            timeout=660,
        )

    def device_software_prepare_url(url, device_id=None):
        return request(
            "software_prepare_url",
            {"url": url},
            device_id,
            timeout=240,
        )

    def device_software_install_prepared(receipt_id, device_id=None):
        return request(
            "software_install_prepared",
            {"receipt_id": receipt_id},
            device_id,
            timeout=360,
        )

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

    tools = [
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
                "Observe and understand the current Windows desktop for universal computer use. "
                "Use this instead of device_capture_screen when the user asks what is visible, "
                "what is open, or asks IRAS to describe/read a screenshot. Returns the foreground "
                "window, screenshot metadata, Windows UI Automation controls plus a fused "
                "multimodal scene graph. When visual "
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
            "device_desktop_context",
            (
                "Build the RC11 high-fidelity desktop world model: fresh UIA + OmniParser screen grounding, "
                "visible windows, foreground process identity, temporal screen changes, and a structured running-process snapshot. "
                "Use this when diagnosing what is happening on the PC, when a GUI is behaving unexpectedly, or before choosing a repair route."
            ),
            {
                "type": "object",
                "properties": {
                    "vision": {"type": "string", "enum": ["off", "auto", "always"]},
                    "scope": {"type": "string", "enum": ["auto", "foreground", "desktop"]},
                    "max_elements": {"type": "integer", "minimum": 1, "maximum": 300},
                    "process_limit": {"type": "integer", "minimum": 1, "maximum": 1000},
                    "include_process_paths": {"type": "boolean"},
                    **optional_device,
                },
            },
            device_desktop_context,
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
            "device_read_text_range",
            "Read a bounded line range from an allowed text/code file. Prefer this over reading a whole large source file.",
            {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "start_line": {"type": "integer", "minimum": 1},
                    "end_line": {"type": "integer", "minimum": 1},
                    **optional_device,
                },
                "required": ["path"],
            },
            device_read_text_range,
            PermissionLevel.READ,
        ),
        Tool(
            "device_search_text",
            "Search bounded text/code files recursively inside an allowed root and return matching lines with paths and line numbers. Symlinks and oversized files are skipped.",
            {
                "type": "object",
                "properties": {
                    "root": {"type": "string"},
                    "query": {"type": "string", "maxLength": 1000},
                    "pattern": {"type": "string", "maxLength": 200},
                    "regex": {"type": "boolean"},
                    "case_sensitive": {"type": "boolean"},
                    "max_matches": {"type": "integer", "minimum": 1, "maximum": 500},
                    "max_files": {"type": "integer", "minimum": 1, "maximum": 3000},
                    **optional_device,
                },
                "required": ["root", "query"],
            },
            device_search_text,
            PermissionLevel.READ,
        ),
        Tool(
            "device_file_info",
            "Inspect one allowed file/directory and optionally compute a SHA-256 hash for verification.",
            {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "sha256": {"type": "boolean"},
                    **optional_device,
                },
                "required": ["path"],
            },
            device_file_info,
            PermissionLevel.READ,
        ),
        Tool(
            "device_find_projects",
            "Discover likely development projects/repositories inside configured IRAS bridge roots. Use this before project Git/file tools when the Windows project path is unknown; never invent a cloud/container path.",
            {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "maxLength": 200},
                    "max_depth": {"type": "integer", "minimum": 0, "maximum": 5},
                    "max_results": {"type": "integer", "minimum": 1, "maximum": 50},
                    **optional_device,
                },
            },
            device_find_projects,
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
            "device_git_diff",
            "Read a bounded Git diff from an allowed repository, optionally for one path or staged changes.",
            {
                "type": "object",
                "properties": {
                    "repo": {"type": "string"},
                    "path": {"type": "string"},
                    "staged": {"type": "boolean"},
                    "max_chars": {"type": "integer", "minimum": 1000, "maximum": 100000},
                    **optional_device,
                },
                "required": ["repo"],
            },
            device_git_diff,
            PermissionLevel.READ,
        ),
        Tool(
            "device_git_log",
            "Read recent Git commit summaries from an allowed repository.",
            {
                "type": "object",
                "properties": {
                    "repo": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                    **optional_device,
                },
                "required": ["repo"],
            },
            device_git_log,
            PermissionLevel.READ,
        ),
        Tool(
            "device_run_tests",
            (
                "Run the detected project test suite, or one bounded pytest target, on the paired computer. "
                "Only pytest or the package.json test script is allowed; no arbitrary shell."
            ),
            {
                "type": "object",
                "properties": {
                    "project": {
                        "type": "string",
                    },
                    "target": {
                        "type": "string",
                        "description": "Optional pytest file or file::test node inside the project.",
                    },
                    "timeout": {
                        "type": "number",
                        "minimum": 10,
                        "maximum": 180,
                    },
                    **optional_device,
                },
                "required": [
                    "project",
                ],
            },
            device_run_tests,
            PermissionLevel.SYSTEM_ACTION,
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
            (
                "Return a structured read-only process inventory for the paired PC, including categories, visible app titles, "
                "memory/CPU-time summaries, responsiveness and started/exited deltas. Process command lines are never collected."
            ),
            {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "minimum": 1, "maximum": 1000},
                    "query": {"type": "string", "maxLength": 300},
                    "only_apps": {"type": "boolean"},
                    "sort_by": {"type": "string", "enum": ["memory", "cpu", "name", "pid"]},
                    "include_path": {"type": "boolean"},
                    "track_changes": {"type": "boolean"},
                    **optional_device,
                },
            },
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
            "device_quick_code",
            (
                "Create one source-code file directly on the paired PC, verify the exact file contents by reading them back, "
                "and open the containing workspace in VS Code. Use this for simple requests such as 'open VS Code and write "
                "a Python hello world/triangle program'. Generate the complete requested source in the content argument. "
                "Prefer this over typing code through GUI automation."
            ),
            {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "minLength": 1, "maxLength": 20000},
                    "filename": {"type": "string", "maxLength": 120},
                    "language": {"type": "string", "maxLength": 40},
                    "open_in_vscode": {"type": "boolean"},
                    **optional_device,
                },
                "required": ["content"],
            },
            device_quick_code,
            PermissionLevel.SYSTEM_ACTION,
        ),
        Tool(
            "device_quick_code_run_in_vscode",
            (
                "Run a previously created Quick Code source file inside VS Code's integrated terminal. "
                "Use this for follow-ups such as 'try this in VS Code' or 'run that code in VS Code'. "
                "The path must refer to an already-created file inside the paired PC's allowed roots."
            ),
            {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "language": {"type": "string", "maxLength": 40},
                    "sample_input": {"type": "string", "maxLength": 120},
                    **optional_device,
                },
                "required": ["path"],
            },
            device_quick_code_run_in_vscode,
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
            "device_replace_text",
            (
                "Replace an exact expected snippet in a UTF-8 text/code file on the paired PC. "
                "The file must be inside an allowed root; replacement count is bounded. "
                "Prefer this over rewriting an entire existing source file."
            ),
            {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "old_text": {"type": "string"},
                    "new_text": {"type": "string"},
                    "count": {"type": "integer", "minimum": 1, "maximum": 20},
                    **optional_device,
                },
                "required": ["path", "old_text", "new_text"],
            },
            device_replace_text,
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
            "device_software_manager_status",
            "Check whether the paired Windows PC has WinGet available and report its version.",
            {"type": "object", "properties": {**optional_device}},
            device_software_manager_status,
            PermissionLevel.READ,
        ),
        Tool(
            "device_software_search",
            "Search WinGet/MS Store package catalogs on the paired Windows PC. Read-only; use this before any install to resolve exact package identity.",
            {"type": "object", "properties": {"query": {"type": "string", "minLength": 1, "maxLength": 300}, "source": {"type": "string", "enum": ["winget", "msstore"]}, "count": {"type": "integer", "minimum": 1, "maximum": 50}, **optional_device}, "required": ["query"]},
            device_software_search,
            PermissionLevel.READ,
        ),
        Tool(
            "device_software_show",
            "Show metadata for one exact WinGet package ID before installation.",
            {"type": "object", "properties": {"package_id": {"type": "string", "minLength": 2, "maxLength": 200}, "source": {"type": "string", "enum": ["winget", "msstore"]}, **optional_device}, "required": ["package_id"]},
            device_software_show,
            PermissionLevel.READ,
        ),
        Tool(
            "device_software_list",
            "Read installed software state using WinGet, optionally by exact package ID or query.",
            {"type": "object", "properties": {"query": {"type": "string", "maxLength": 300}, "package_id": {"type": "string", "maxLength": 200}, **optional_device}},
            device_software_list,
            PermissionLevel.READ,
        ),
        Tool(
            "device_software_upgrades",
            "List available WinGet upgrades, optionally for one exact package ID. Read-only.",
            {"type": "object", "properties": {"package_id": {"type": "string", "maxLength": 200}, "source": {"type": "string", "enum": ["winget", "msstore"]}, **optional_device}},
            device_software_upgrades,
            PermissionLevel.READ,
        ),
        Tool(
            "device_software_install",
            "Install one exact verified WinGet package ID. CRITICAL: requires full Remote authorization and the laptop's local command-execution opt-in; Windows/UAC remain authoritative.",
            {"type": "object", "properties": {"package_id": {"type": "string", "minLength": 2, "maxLength": 200}, "source": {"type": "string", "enum": ["winget", "msstore"]}, "version": {"type": "string", "maxLength": 80}, "scope": {"type": "string", "enum": ["", "user", "machine"]}, **optional_device}, "required": ["package_id"]},
            device_software_install,
            PermissionLevel.CRITICAL,
        ),
        Tool(
            "device_software_upgrade",
            "Update one exact installed WinGet package, or all packages only when all_packages=true is explicitly requested. CRITICAL; Remote/UAC/local policy remain authoritative.",
            {"type": "object", "properties": {"package_id": {"type": "string", "maxLength": 200}, "source": {"type": "string", "enum": ["winget", "msstore"]}, "all_packages": {"type": "boolean"}, **optional_device}},
            device_software_upgrade,
            PermissionLevel.CRITICAL,
        ),
        Tool(
            "device_software_uninstall",
            "Uninstall one exact currently installed WinGet package ID and verify removal. CRITICAL; Remote/UAC/local policy remain authoritative.",
            {"type": "object", "properties": {"package_id": {"type": "string", "minLength": 2, "maxLength": 200}, "source": {"type": "string", "enum": ["winget", "msstore"]}, **optional_device}, "required": ["package_id"]},
            device_software_uninstall,
            PermissionLevel.CRITICAL,
        ),
        Tool(
            "device_software_prepare_url",
            "Download an explicitly selected HTTPS .exe/.msi installer into the IRAS cache, compute SHA-256, and inspect Authenticode. This does not execute the installer.",
            {"type": "object", "properties": {"url": {"type": "string", "minLength": 8, "maxLength": 4096}, **optional_device}, "required": ["url"]},
            device_software_prepare_url,
            PermissionLevel.SYSTEM_ACTION,
        ),
        Tool(
            "device_software_install_prepared",
            "Execute only an IRAS-cached installer receipt whose hash is unchanged and Authenticode status is Valid. CRITICAL; never accepts arbitrary file paths and never bypasses UAC/SmartScreen.",
            {"type": "object", "properties": {"receipt_id": {"type": "string", "minLength": 24, "maxLength": 24}, **optional_device}, "required": ["receipt_id"]},
            device_software_install_prepared,
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

    # Keep cloud-side approval classification aligned with the exact action the
    # Windows bridge will enforce. This prevents a dynamic SYSTEM/CRITICAL
    # action from being under-classified by a static tool permission.
    action_by_tool = {
        "device_list": None,
        "device_system_info": "system_info", "device_detect_apps": "detect_apps",
        "device_app_control": "app_control", "device_open_app": "open_app",
        "device_interact_app": "interact_app", "device_observe_ui": "observe_ui",
        "device_semantic_action": "semantic_action", "device_computer_status": "computer_status",
        "device_computer_observe": "computer_observe", "device_desktop_context": "desktop_context", "device_computer_action": "computer_action",
        "device_computer_verify": "computer_verify", "device_whatsapp_open_chat": "whatsapp_open_chat",
        "device_spotify_search": "spotify_search", "device_spotify_play": "spotify_play",
        "device_media_control": "media_control", "device_open_url": "open_url",
        "device_open_project": "open_project", "device_list_files": "list_directory",
        "device_quick_code_run_in_vscode": "interact_app",
        "device_read_text": "read_text", "device_read_text_range": "read_text_range",
        "device_search_text": "search_text", "device_file_info": "file_info",
        "device_find_projects": "find_projects", "device_git_status": "git_status", "device_git_diff": "git_diff", "device_git_log": "git_log",
        "device_run_tests": "run_tests", "device_capture_screen": "capture_screen",
        "device_screen_preview": "screen_preview", "device_list_processes": "list_processes",
        "device_kill_process": "kill_process", "device_write_text": "write_text",
        "device_replace_text": "replace_text", "device_make_directory": "make_directory",
        "device_copy_path": "copy_path", "device_move_path": "move_path",
        "device_delete_path": "delete_path", "device_clipboard_get": "clipboard_get",
        "device_clipboard_set": "clipboard_set", "device_ui_find_text": "ui_find_text",
        "device_ui_click_text": "ui_click_text", "device_ui_type_text": "ui_type_text",
        "device_ui_wait_text": "ui_wait_text", "device_ui_scroll_until_text": "ui_scroll_until_text",
        "device_verify_state": "verify_state", "device_power_action": "power_action",
        "device_software_manager_status": "software_manager_status",
        "device_software_search": "software_search", "device_software_show": "software_show",
        "device_software_list": "software_list", "device_software_upgrades": "software_upgrades",
        "device_software_install": "software_install", "device_software_upgrade": "software_upgrade",
        "device_software_uninstall": "software_uninstall",
        "device_software_prepare_url": "software_prepare_url",
        "device_software_install_prepared": "software_install_prepared",
        "device_run_command": "run_command",
    }

    # User-facing approval policy: bounded routine conveniences should not
    # interrupt the user merely because the request came through Cloud/Web/
    # Android instead of the local CLI.  This changes only ToolRegistry prompt
    # classification.  The device request still forwards the original
    # action_permission() value to the Remote/device authorization layer, so
    # local mode caps, Remote session scopes, emergency stop, and bridge-root
    # restrictions remain authoritative.
    #
    # Keep this allowlist intentionally narrow. Generic click/type, arbitrary
    # application interaction, file mutation, shell/process/power control,
    # sends/submits, installs, rollback and other consequential operations keep
    # their stronger approval requirements.
    routine_bounded_actions = {
        "whatsapp_open_chat",
        "spotify_search",
        "spotify_play",
        "media_control",
        "ui_scroll_until_text",
    }

    for tool in tools:
        action = action_by_tool.get(tool.name)
        if action:
            def _resolver(args, _action=action):
                forwarded = {k: v for k, v in dict(args or {}).items() if k != "device_id"}
                level = action_permission(_action, forwarded)
                if (
                    _action in routine_bounded_actions
                    and level == PermissionLevel.SYSTEM_ACTION
                ):
                    return PermissionLevel.SAFE_ACTION
                return level
            tool.permission_resolver = _resolver

    return tools
