# IRAS v3.5.0 — Universal Computer Vision & Control

v3.5.0 introduces a general Windows computer-use layer so IRAS can solve GUI
workflows without an app-specific automation implementation for every program.

## Hybrid perception

IRAS now has a desktop observation tool that combines:

1. the current full-desktop screenshot;
2. the active/foreground Windows window;
3. Windows UI Automation (UIA) elements when accessibility metadata exists;
4. optional OmniParser visual grounding for custom-rendered controls that UIA
   cannot expose.

UIA remains the first choice because it is fast and native. OmniParser is only
called in `auto` mode when UIA yields no usable controls, or explicitly with
`vision="always"`.

OmniParser is opt-in. IRAS never sends a screenshot to an OmniParser endpoint
unless `IRAS_OMNIPARSER_URL` is configured.

## Grounded actions, not guessed coordinates

`device_computer_observe` returns an `observation_id` and actionable element
identifiers such as:

- `uia:12`
- `vision:4`

`device_computer_action` requires that fresh `observation_id`. Mouse actions use
one of the returned `element_id` values. The cloud model does not receive an
`x`/`y` action schema, so it cannot directly invent a raw click coordinate.
IRAS resolves an element's center locally at execution time.

Supported universal actions:

- move
- click
- double-click
- right-click
- type into a grounded element
- press a key
- hotkey
- scroll
- drag from one grounded element to another
- bounded wait

Fresh observations expire (30 seconds by default) so stale screen coordinates
cannot be replayed after the interface has changed.

## Closed-loop outcome verification

A successfully injected mouse/keyboard action is not treated as completion of
the user's goal.

The intended loop is:

`OBSERVE -> ACT -> OBSERVE -> VERIFY -> ADAPT/FINISH`

`device_computer_verify` returns one of:

- `PASS`
- `FAIL`
- `INCONCLUSIVE`

Available v3.5 predicates are:

- element exists
- element absent
- visible/accessible text contains a phrase
- foreground window title contains a phrase
- screen changed
- screen stayed stable
- foreground window changed

`INCONCLUSIVE` is never treated as success.

## Safety boundary

This is broad desktop control, not a permission bypass. It deliberately keeps
IRAS's existing permission/audit path. It also blocks visual targets that would
circumvent the project's existing restrictions on shells, registry/security
consoles, disk formatting, Defender/firewall disabling, PC reset, and account
removal.

Windows-key shortcuts, Ctrl+Alt+Delete, and Alt+F4 remain blocked in the visual
computer-use action layer.

## New tools

- `device_computer_status`
- `device_computer_observe`
- `device_computer_action`
- `device_computer_verify`

The older specialized tools remain available. The planner should prefer a
specialized deterministic tool when it is reliable, use UIA semantic control
for normal Windows controls, and use universal/visual computer control as the
fallback for unfamiliar/custom interfaces.
