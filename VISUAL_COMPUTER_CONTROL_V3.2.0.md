# IRAS v3.2.0 — Visual Computer Control Engine

v3.2.0 adds an OBSERVE → ACT → OBSERVE → VERIFY loop for normal safe Windows
GUI applications.

## What "visual" means in this release

IRAS captures the active application window for local audit and, more
importantly, reads the visible Windows UI Automation accessibility tree:

- visible control names
- control roles (Button, Edit, MenuItem, ListItem, TabItem, Hyperlink, ...)
- Automation IDs
- values when exposed by the app
- enabled/focusable state
- real screen bounding rectangles

The planner receives this structured semantic snapshot. That is more reliable
than asking an LLM to invent coordinates and it works with IRAS's current
multi-provider cloud architecture without making every provider support image
inputs.

Screenshots are still saved under:

```text
~/.iras/ui_observations/
```

with dimensions and SHA-256 hashes for audit/debugging.

## New device tools

### `device_observe_ui`

Observe one app before acting.

Example conceptual result:

```json
{
  "app": "discord",
  "window_name": "Discord",
  "element_count": 83,
  "elements": [
    {
      "name": "Search",
      "role": "Edit",
      "rect": {
        "left": 501,
        "top": 113,
        "width": 302,
        "height": 34
      }
    },
    {
      "name": "User Settings",
      "role": "Button",
      "rect": {
        "left": 288,
        "top": 915,
        "width": 32,
        "height": 32
      }
    }
  ]
}
```

### `device_semantic_action`

Targets a real element from observation by name/role/Automation ID. Supported:

```text
click
double_click
focus
type_into
press
```

Coordinates are derived from the observed element bounds. The model does not
supply arbitrary coordinates.

After an action, IRAS observes again and returns:

```text
before_fingerprint
after_fingerprint
ui_changed
verification screenshot
updated visible UI elements
```

## Autonomous planner behavior

For unfamiliar GUI workflows the intended loop is:

```text
detect/open app
→ observe UI
→ choose a real visible semantic target
→ semantic action
→ observe updated UI
→ adapt
→ repeat until complete
```

The existing 8-step agent limit still bounds each turn.

## Safety

v3.2.0 does not add:

- arbitrary shell execution
- PowerShell commands chosen by the model
- arbitrary subprocess commands
- Windows-key shortcuts
- Ctrl+Alt+Delete
- unrestricted raw-coordinate clicking

The UI Automation PowerShell script is fixed application code. User text is not
inserted into it; only a validated window handle and element limit are passed
through environment variables.

Existing blocked command/admin applications remain blocked.
