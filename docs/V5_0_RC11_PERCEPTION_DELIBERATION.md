# IRAS RC11 — Next-Level Perception, Process Awareness & Deliberate Repair

RC11 is an overlay on the cleaned RC10 baseline. It does not change Remote protocol `1` and does not weaken ToolRegistry, Remote/Master authorization, the emergency stop, filesystem roots, audit, or Windows/UAC.

## 1. Desktop world model

`device_desktop_context` is a READ-only diagnostic/perception tool. It combines:

- a fresh `device_computer_observe`-class UIA + OmniParser scene;
- foreground HWND, PID, process name, title and bounds;
- visible top-level windows and their owning process identities;
- stable scene element IDs and provenance;
- temporal screen changes from the immediately previous observation;
- a structured process inventory with responsiveness and resource summaries;
- correlation between the foreground window, visible windows and running processes.

Use it when the user asks what is happening on the PC, when a GUI behaves unexpectedly, or before choosing a repair route after a failed computer-use step.

## 2. Temporal screen perception

Every universal computer observation now carries `temporal` state:

- previous observation ID;
- bounded 0..1 visual change score from tiny grayscale frame comparisons;
- semantic change score from stable scene element IDs;
- appeared/disappeared controls;
- stable-element count;
- foreground window/process changes;
- `initial`, `stable`, `minor`, or `major` change level.

The image comparison is diagnostic only. IRAS still cannot act on guessed coordinates; state-changing GUI actions require a fresh grounded `element_id` from the existing computer-use controller.

## 3. Process awareness

`list_processes` / `device_list_processes` now return structured data rather than raw `tasklist` CSV. The inventory includes, where available:

- PID and parent PID;
- process name and category;
- cumulative CPU seconds;
- working/private memory;
- thread/handle counts;
- session ID;
- responsiveness;
- main-window title;
- start time;
- executable path only when explicitly requested;
- started/exited deltas since the prior snapshot.

Process command lines are intentionally **not collected**, because they can contain passwords, API tokens, signed URLs and other secrets.

## 4. Calm deliberate repair

RC11 adds `v5_deliberation_status` and `v5_deliberate_repair`.

The repair planner classifies failures into categories such as permission, UI grounding, process/app state, connectivity, verification, dependency, file/Git state and provider failures. It then ranks materially different bounded strategies.

The system prompt and Windows planner now enforce these behavioral rules:

1. gather fresh ground truth first;
2. classify the failure before changing state;
3. compare materially different routes;
4. prefer the smallest reversible route;
5. make one state change at a time;
6. do not repeat a failed route without new evidence;
7. verify the user's actual end state after repair;
8. stop at permission/human-input boundaries instead of forcing through them.

This is deliberate reasoning, not artificial sleeping or delay.

## 5. Coding Agent integration

The Coding Agent can use `device_desktop_context` and structured process inventory during inspect/test/repair/review work. The repair node explicitly asks for diagnosis, materially different routes, minimal changes and fresh GUI/process evidence when runtime behavior is involved.

## 6. Validation

RC11 adds `tests/test_rc11_perception_process_deliberation.py` covering process structure/deltas/privacy, temporal screen change detection, deliberate-repair route selection, planner permissions and prompt/tool contracts.

The Linux/container regression run after RC11 integration reports all tests passing. Final Windows acceptance should still run:

```powershell
cd D:\Projects\IRAS-complete
.\.venv\Scripts\Activate.ps1
.\run-v500-validation.ps1
```

For a live RC11 perception check after the updated bridge is running, ask IRAS to use `device_desktop_context` or query `device_list_processes`.
