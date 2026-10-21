> **Merged build.** This is now the main IRAS screen. `python build.py` writes `clients/web/index.html`, served at `/app/`. It uses the same server address by default (Live). The sample-data demo is hidden. The old page is kept at `clients/web/classic/` for the remote screen, tasks and master control.

# IRAS Command Center

The new look of IRAS, working: a living orb, glass panels, an approval gate, and seven screens.
It is **one file** (`index.html`, about 530 KB). It works offline and makes no network requests.

It follows your plan: Cobalt and Neon skins, dark and light, glass, and an orb with six states.
It turns UI-1 (design system), UI-2 (shell, orb, live event stream) and UI-4 (light-mode check,
Performance mode, reduced motion) into running code.

## Open it

- **Fastest:** double-click `index.html`.
- **With IRAS:** put this folder at `clients/web/command-center/` and open
  `http://localhost:8000/app/command-center/`. The server already serves `clients/web/` at `/app`.

The classic client (`clients/web/index.html`) is not touched, so nothing that works today breaks.

## Try it in two minutes

1. Press **Play a guided demo**. You will see a voice request, an email summary, a red delete approval and the code agent.
2. Press **Space**, or click the orb. IRAS listens. Allow the microphone and the orb follows your real voice. Audio stays in the page.
3. Press **Install VS Code**. An amber approval opens. Press **Delete old build folders**. A red approval opens with a 9 second ring. **Esc** means no.
4. Press **Ctrl K** and type `neon`, `light` or `performance`.
5. Open **Activity** and click a row. Open **Memory** and drag the nodes, or search `music`. Open **Identity** and start Face ID or Voice ID.

## The screens

| Screen | What it shows |
|---|---|
| **Home** | The orb, the state name, the path Listen, Understand, Approval, Act, a picture of the screen area IRAS controls, a command bar, and Live activity. |
| **Chat** | Streaming replies with the tools used, small markdown, and code cards with Copy and Expand. |
| **Agents** | `/code`, `/research` and `/install` with a step timeline for each run, plus routines you can switch on and off. |
| **Activity** | The audit log as a timeline. Pick a row to see safety checks and the raw details. Export as JSON. |
| **Memory** | A map you can drag and search, a list version, and facts IRAS learned that wait for you to keep or forget. |
| **Identity** | Face ID and Voice ID enrollment (preview). |
| **Settings** | Theme, skin, Performance mode, reduce motion, voice, connection, the authority levels, keyboard keys. |

## Connect it to your server

Settings, then Connection, then **Live**. Type your server address and your access token
(the token is kept for this tab only), then press **Test connection**.
If you already use the classic web app, press **Import from classic web app**.

What works in Live mode today, using endpoints that already exist:

- Chat streaming (`POST /v1/chat/stream`)
- The provider chip and its backups (`GET /v1/providers/status`)
- Activity for the chats you send

Voice, approvals, agents and screen control need the server to push events during a turn.
`EVENTS.md` lists every event and proposes one small `GET /v1/events` stream. When it exists,
the live adapter is three lines and no screen changes.

If you open the file from your disk and point it at a server on another address, the server must
allow it (CORS). Served from `/app/` on the same server, it just works.

## Build it

```
python build.py            # makes index.html from src/. Python only, no Node.
python build.py --check    # also fails on a missing icon or an external link
```

```
src/index.template.html    the page
src/views/                 one file per screen
src/css/                   tokens, base, shell, components, then one file per screen
src/js/                    00-core (events, state machine) ... 90-app (start up), in order
src/assets/ src/fonts/     icons (Lucide) and fonts (Sora, Instrument Sans, JetBrains Mono)
tools/contrast.py          measures contrast for all four looks
qa/flows.py  qa/a11y.py    browser tests (need: pip install playwright, and for a11y: npm i axe-core)
```

## Checks that were run

- **Behaviour (qa/flows.py), 33 checks, all pass:** every scenario ends in the right states, the amber and red approvals, deny with Esc, the 9 second timeout, Stop, the code agent timeline, keyboard shortcuts, the palette, skins, Performance mode, at most 3 blurred layers, no impossible state moves, no network requests, no console errors.
- **Accessibility (qa/a11y.py):** axe-core, 7 screens, 4 looks, **0 violations**.
- **Contrast (tools/contrast.py):** every text pair is 4.5 or more and every interface part is 3 or more, in all four looks. See `DESIGN.md`.
- **Layout:** no sideways overflow at 390, 820, 1024, 1280, 1366 and 1440 pixels wide.
- **Motion:** with reduced motion no loop keeps running. In Performance mode there is no blur, no background drift and the orb runs at 20fps.
- **Project tests:** `pytest tests/test_command_center_ui.py`.

## Honest limits

- The **voice transcript is scripted**. The orb reacts to your real microphone, but this page cannot turn speech into text. The word-by-word text is a demo.
- The **Face ID mesh is an animated stand-in**. With the camera on, the mesh is hidden and only the progress ring shows. Nothing is matched, recorded or saved. The same is true for Voice ID.
- In **Live mode** only chat, provider status and activity are real. Memory, routines and Identity stay as samples.
- **Approvals by voice** are shown, but only the backend can check a voice. The preview approves with a tap.
- I tested in **Chromium** only. It needs a browser from 2024 or newer (container query units, `:has`, `color-mix`).
- The sample names, files and numbers in the demo are made up.
