from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time


_UIA_OBSERVE_PS = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)

Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

$hwnd = [Int64]$env:IRAS_UI_HWND
$limit = [Int32]$env:IRAS_UI_LIMIT

if ($hwnd -le 0) {
    throw 'Invalid IRAS_UI_HWND.'
}

if ($limit -lt 1) {
    $limit = 1
}

if ($limit -gt 300) {
    $limit = 300
}

$root = [System.Windows.Automation.AutomationElement]::FromHandle(
    [IntPtr]$hwnd
)

if ($null -eq $root) {
    throw 'UI Automation could not attach to this window.'
}

$all = $root.FindAll(
    [System.Windows.Automation.TreeScope]::Descendants,
    [System.Windows.Automation.Condition]::TrueCondition
)

$items = New-Object System.Collections.Generic.List[Object]

for ($i = 0; $i -lt $all.Count; $i++) {
    if ($items.Count -ge $limit) {
        break
    }

    $el = $all.Item($i)

    try {
        $name = [string]$el.Current.Name
    } catch {
        $name = ''
    }

    try {
        $automationId = [string]$el.Current.AutomationId
    } catch {
        $automationId = ''
    }

    try {
        $control = [string]$el.Current.ControlType.ProgrammaticName
        $control = $control -replace '^ControlType\.', ''
    } catch {
        $control = ''
    }

    try {
        $enabled = [bool]$el.Current.IsEnabled
    } catch {
        $enabled = $false
    }

    try {
        $offscreen = [bool]$el.Current.IsOffscreen
    } catch {
        $offscreen = $true
    }

    try {
        $focusable = [bool]$el.Current.IsKeyboardFocusable
    } catch {
        $focusable = $false
    }

    try {
        $rect = $el.Current.BoundingRectangle
        $left = [int][Math]::Round($rect.Left)
        $top = [int][Math]::Round($rect.Top)
        $width = [int][Math]::Round($rect.Width)
        $height = [int][Math]::Round($rect.Height)
    } catch {
        $left = 0
        $top = 0
        $width = 0
        $height = 0
    }

    $value = $null

    try {
        $pattern = $el.GetCurrentPattern(
            [System.Windows.Automation.ValuePattern]::Pattern
        )

        if ($null -ne $pattern) {
            $value = [string]$pattern.Current.Value
        }
    } catch {
        $value = $null
    }

    # Ignore completely anonymous nodes and off-screen nodes. The agent acts
    # only on controls that are visible and semantically describable.
    if (
        -not $offscreen -and
        (
            -not [string]::IsNullOrWhiteSpace($name) -or
            -not [string]::IsNullOrWhiteSpace($automationId)
        ) -and
        $width -gt 0 -and
        $height -gt 0
    ) {
        $items.Add(
            [PSCustomObject]@{
                index = $items.Count
                name = $name
                automation_id = $automationId
                role = $control
                enabled = $enabled
                focusable = $focusable
                value = $value
                rect = [PSCustomObject]@{
                    left = $left
                    top = $top
                    width = $width
                    height = $height
                }
            }
        )
    }
}

$result = [PSCustomObject]@{
    window_name = [string]$root.Current.Name
    automation_id = [string]$root.Current.AutomationId
    element_count = $items.Count
    elements = $items
}

$result | ConvertTo-Json -Depth 8 -Compress
"""


def _normalize(value: str) -> str:
    return " ".join(
        str(value or "")
        .strip()
        .lower()
        .replace("_", " ")
        .replace("-", " ")
        .split()
    )


class SemanticVisualController:
    """
    Bounded semantic UI observation + control for Windows.

    The model never invents raw coordinates. Windows UI Automation supplies
    the visible element bounds; IRAS selects an element by semantic text/role
    and derives the click point from that observed element.

    A screenshot is also captured for local audit/debugging, but the cloud
    planner reasons from the structured accessibility snapshot returned by
    Windows UI Automation. This keeps the v3.2 path provider-independent.
    """

    ALLOWED_ACTIONS = {
        "click",
        "double_click",
        "focus",
        "type_into",
        "press",
    }

    def __init__(self, ui):
        self.ui = ui

    @staticmethod
    def _powershell() -> str:
        executable = (
            shutil.which("powershell.exe")
            or shutil.which("powershell")
        )

        if not executable:
            raise FileNotFoundError(
                "Windows PowerShell is required for semantic UI observation."
            )

        return executable

    @staticmethod
    def _encoded_script(script: str) -> str:
        return base64.b64encode(
            script.encode("utf-16-le")
        ).decode("ascii")

    def _run_uia_observer(
        self,
        hwnd: int,
        max_elements: int,
    ) -> dict:
        env = dict(os.environ)
        env["IRAS_UI_HWND"] = str(
            int(hwnd)
        )
        env["IRAS_UI_LIMIT"] = str(
            max(
                1,
                min(
                    int(max_elements),
                    300,
                ),
            )
        )

        result = subprocess.run(
            [
                self._powershell(),
                "-NoProfile",
                "-NonInteractive",
                "-EncodedCommand",
                self._encoded_script(
                    _UIA_OBSERVE_PS
                ),
            ],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=15,
            shell=False,
            env=env,
        )

        if result.returncode != 0:
            error = (
                result.stderr.strip()
                or result.stdout.strip()
                or "Unknown UI Automation error."
            )

            raise RuntimeError(
                "Windows UI Automation observation failed: "
                + error[-2000:]
            )

        raw = result.stdout.strip()

        if not raw:
            raise RuntimeError(
                "Windows UI Automation returned no data."
            )

        try:
            payload = json.loads(
                raw
            )
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "Windows UI Automation returned invalid JSON: "
                + raw[-1500:]
            ) from exc

        if not isinstance(
            payload,
            dict,
        ):
            raise RuntimeError(
                "Windows UI Automation returned an unexpected payload."
            )

        payload.setdefault(
            "elements",
            [],
        )
        payload.setdefault(
            "element_count",
            len(
                payload["elements"]
            ),
        )

        return payload

    def _ensure_window(
        self,
        app: str,
        *,
        ensure_open: bool,
    ) -> tuple[str, int, bool]:
        canonical = (
            self.ui.canonical_app(
                app
            )
        )

        hwnd = self.ui._find_window(
            canonical
        )
        launched = False

        if (
            hwnd is None
            and ensure_open
        ):
            self.ui.catalog.launch(
                canonical
            )
            launched = True

            deadline = (
                time.monotonic()
                + 12.0
            )

            while (
                time.monotonic()
                < deadline
            ):
                time.sleep(
                    0.30
                )

                hwnd = (
                    self.ui._find_window(
                        canonical
                    )
                )

                if hwnd is not None:
                    break

        if hwnd is None:
            raise RuntimeError(
                f"Could not find a visible window for '{app}'."
            )

        if not self.ui._force_foreground(
            int(hwnd)
        ):
            raise RuntimeError(
                "Windows refused to focus the requested app. "
                "IRAS did not continue because input could reach the wrong window."
            )

        return (
            canonical,
            int(hwnd),
            launched,
        )

    def _capture_window(
        self,
        app: str,
        hwnd: int,
    ) -> dict:
        from PIL import ImageGrab

        rect = (
            self.ui._physical_window_rect(
                int(hwnd)
            )
        )

        bbox = (
            int(rect.left),
            int(rect.top),
            int(rect.right),
            int(rect.bottom),
        )

        try:
            image = ImageGrab.grab(
                bbox=bbox,
                all_screens=True,
            )
        except TypeError:
            image = ImageGrab.grab(
                bbox=bbox,
            )

        image.thumbnail(
            (
                1600,
                1100,
            )
        )

        target = (
            Path.home()
            / ".iras"
            / "ui_observations"
            / (
                _normalize(app)
                .replace(
                    " ",
                    "-",
                )
                + "-"
                + str(
                    int(
                        time.time()
                        * 1000
                    )
                )
                + ".jpg"
            )
        )

        target.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        image.convert(
            "RGB"
        ).save(
            target,
            "JPEG",
            quality=80,
            optimize=True,
        )

        digest = hashlib.sha256(
            target.read_bytes()
        ).hexdigest()

        return {
            "path": str(
                target
            ),
            "width": image.width,
            "height": image.height,
            "sha256": digest,
            "bytes": (
                target.stat().st_size
            ),
        }

    @staticmethod
    def _fingerprint(
        payload: dict,
    ) -> str:
        compact = {
            "window_name": payload.get(
                "window_name",
                "",
            ),
            "elements": [
                {
                    "name": item.get(
                        "name",
                        "",
                    ),
                    "automation_id": item.get(
                        "automation_id",
                        "",
                    ),
                    "role": item.get(
                        "role",
                        "",
                    ),
                    "value": item.get(
                        "value",
                        None,
                    ),
                    "rect": item.get(
                        "rect",
                        {},
                    ),
                }
                for item in payload.get(
                    "elements",
                    [],
                )
            ],
        }

        encoded = json.dumps(
            compact,
            sort_keys=True,
            ensure_ascii=False,
            default=str,
        ).encode(
            "utf-8"
        )

        return hashlib.sha256(
            encoded
        ).hexdigest()

    def observe(
        self,
        app: str,
        *,
        ensure_open: bool = True,
        max_elements: int = 180,
        screenshot: bool = True,
    ) -> dict:
        canonical, hwnd, launched = (
            self._ensure_window(
                app,
                ensure_open=bool(
                    ensure_open
                ),
            )
        )

        snapshot = (
            self._run_uia_observer(
                hwnd,
                max_elements,
            )
        )

        snapshot[
            "fingerprint"
        ] = self._fingerprint(
            snapshot
        )

        output = {
            "app": canonical,
            "window": hwnd,
            "launched": launched,
            "foreground_verified": True,
            "window_name": snapshot.get(
                "window_name",
                "",
            ),
            "element_count": (
                snapshot.get(
                    "element_count",
                    0,
                )
            ),
            "fingerprint": snapshot[
                "fingerprint"
            ],
            "elements": snapshot.get(
                "elements",
                [],
            ),
        }

        if screenshot:
            output[
                "screenshot"
            ] = self._capture_window(
                canonical,
                hwnd,
            )

        return output

    @staticmethod
    def _element_score(
        element: dict,
        target: str,
        role: str = "",
    ) -> float:
        wanted = _normalize(
            target
        )
        wanted_role = _normalize(
            role
        )

        name = _normalize(
            element.get(
                "name",
                "",
            )
        )
        automation_id = _normalize(
            element.get(
                "automation_id",
                "",
            )
        )
        element_role = _normalize(
            element.get(
                "role",
                "",
            )
        )

        if not wanted:
            return 0.0

        score = 0.0

        if name == wanted:
            score = max(
                score,
                1.00,
            )

        if (
            automation_id
            and automation_id == wanted
        ):
            score = max(
                score,
                0.98,
            )

        if (
            name.startswith(
                wanted
            )
            or wanted.startswith(
                name
            )
        ):
            score = max(
                score,
                0.90,
            )

        if (
            wanted in name
            or (
                automation_id
                and wanted
                in automation_id
            )
        ):
            score = max(
                score,
                0.84,
            )

        wanted_tokens = set(
            wanted.split()
        )
        name_tokens = set(
            name.split()
        )

        if (
            wanted_tokens
            and name_tokens
        ):
            overlap = (
                len(
                    wanted_tokens
                    & name_tokens
                )
                / len(
                    wanted_tokens
                    | name_tokens
                )
            )

            score = max(
                score,
                overlap * 0.82,
            )

        if wanted_role:
            if element_role == wanted_role:
                score += 0.15
            elif wanted_role in element_role:
                score += 0.08
            else:
                score -= 0.10

        if not element.get(
            "enabled",
            False,
        ):
            score -= 0.30

        rect = element.get(
            "rect",
            {},
        )

        if (
            int(
                rect.get(
                    "width",
                    0,
                )
            )
            <= 0
            or int(
                rect.get(
                    "height",
                    0,
                )
            )
            <= 0
        ):
            score -= 0.50

        return score

    @classmethod
    def find_element(
        cls,
        elements: list[dict],
        target: str,
        *,
        role: str = "",
        occurrence: int = 1,
    ) -> dict:
        occurrence = max(
            1,
            int(
                occurrence
            ),
        )

        scored = []

        for element in elements:
            score = cls._element_score(
                element,
                target,
                role,
            )

            if score >= 0.58:
                scored.append(
                    (
                        score,
                        element,
                    )
                )

        scored.sort(
            key=lambda item: (
                item[0],
                -int(
                    item[1].get(
                        "index",
                        0,
                    )
                ),
            ),
            reverse=True,
        )

        if len(
            scored
        ) < occurrence:
            names = [
                str(
                    item.get(
                        "name",
                        "",
                    )
                )
                for item in elements
                if item.get(
                    "name"
                )
            ][
                :40
            ]

            raise LookupError(
                "No visible UI element matched "
                f"target={target!r}"
                + (
                    f" role={role!r}"
                    if role
                    else ""
                )
                + ". Visible named elements include: "
                + ", ".join(
                    names
                )
            )

        score, element = (
            scored[
                occurrence - 1
            ]
        )

        return {
            **element,
            "match_score": round(
                score,
                4,
            ),
        }

    @staticmethod
    def _center(
        element: dict,
    ) -> tuple[int, int]:
        rect = element.get(
            "rect",
            {},
        )

        left = int(
            rect.get(
                "left",
                0,
            )
        )
        top = int(
            rect.get(
                "top",
                0,
            )
        )
        width = int(
            rect.get(
                "width",
                0,
            )
        )
        height = int(
            rect.get(
                "height",
                0,
            )
        )

        if (
            width <= 0
            or height <= 0
        ):
            raise RuntimeError(
                "The selected UI element has no clickable screen bounds."
            )

        return (
            left
            + width // 2,
            top
            + height // 2,
        )

    def _click(
        self,
        x: int,
        y: int,
        *,
        count: int = 1,
    ) -> dict:
        cursor = (
            self.ui._set_physical_cursor(
                int(x),
                int(y),
            )
        )

        user32 = (
            self.ui._user32()
        )

        for index in range(
            max(
                1,
                min(
                    int(count),
                    2,
                ),
            )
        ):
            user32.mouse_event(
                0x0002,
                0,
                0,
                0,
                0,
            )
            time.sleep(
                0.035
            )
            user32.mouse_event(
                0x0004,
                0,
                0,
                0,
                0,
            )

            if index == 0 and count > 1:
                time.sleep(
                    0.10
                )

        return cursor

    def act(
        self,
        app: str,
        action: str,
        target: str,
        *,
        text: str = "",
        key: str = "",
        role: str = "",
        occurrence: int = 1,
        replace: bool = False,
        ensure_open: bool = True,
        verify: bool = True,
    ) -> dict:
        action = _normalize(
            action
        ).replace(
            " ",
            "_",
        )

        if action not in (
            self.ALLOWED_ACTIONS
        ):
            raise PermissionError(
                f"Semantic UI action '{action}' is not allowed."
            )

        if (
            action == "type_into"
            and not str(
                text
            )
        ):
            raise ValueError(
                "type_into requires non-empty text."
            )

        if (
            action == "press"
            and not str(
                key
            )
        ):
            raise ValueError(
                "press requires a key."
            )

        before = self.observe(
            app,
            ensure_open=bool(
                ensure_open
            ),
            max_elements=220,
            screenshot=False,
        )

        element = self.find_element(
            before[
                "elements"
            ],
            target,
            role=role,
            occurrence=occurrence,
        )

        x, y = self._center(
            element
        )

        if not self.ui._force_foreground(
            int(
                before[
                    "window"
                ]
            )
        ):
            raise RuntimeError(
                "IRAS lost foreground verification before semantic action."
            )

        cursor = None

        if action in {
            "click",
            "focus",
        }:
            cursor = self._click(
                x,
                y,
                count=1,
            )

        elif action == "double_click":
            cursor = self._click(
                x,
                y,
                count=2,
            )

        elif action == "type_into":
            cursor = self._click(
                x,
                y,
                count=1,
            )

            time.sleep(
                0.12
            )

            if replace:
                self.ui.hotkey(
                    [
                        "ctrl",
                        "a",
                    ]
                )
                time.sleep(
                    0.05
                )

            self.ui.type_text(
                str(
                    text
                )
            )

        elif action == "press":
            cursor = self._click(
                x,
                y,
                count=1,
            )
            time.sleep(
                0.08
            )
            self.ui.press(
                str(
                    key
                )
            )

        time.sleep(
            0.55
        )

        after = None

        if verify:
            after = self.observe(
                app,
                ensure_open=False,
                max_elements=180,
                screenshot=True,
            )

        return {
            "app": before[
                "app"
            ],
            "action": action,
            "target": target,
            "selected_element": (
                element
            ),
            "derived_click": {
                "x": x,
                "y": y,
                "actual_x": (
                    cursor[
                        "actual_x"
                    ]
                    if cursor
                    else None
                ),
                "actual_y": (
                    cursor[
                        "actual_y"
                    ]
                    if cursor
                    else None
                ),
            },
            "command_sent": True,
            "before_fingerprint": (
                before[
                    "fingerprint"
                ]
            ),
            "after_fingerprint": (
                after[
                    "fingerprint"
                ]
                if after
                else None
            ),
            "ui_changed": (
                (
                    before[
                        "fingerprint"
                    ]
                    != after[
                        "fingerprint"
                    ]
                )
                if after
                else None
            ),
            "verification_observation": (
                {
                    "window_name": (
                        after[
                            "window_name"
                        ]
                    ),
                    "element_count": (
                        after[
                            "element_count"
                        ]
                    ),
                    "fingerprint": (
                        after[
                            "fingerprint"
                        ]
                    ),
                    "screenshot": (
                        after.get(
                            "screenshot"
                        )
                    ),
                    "elements": (
                        after[
                            "elements"
                        ][
                            :80
                        ]
                    ),
                }
                if after
                else None
            ),
        }
