# Events: how the screen is driven

The Command Center only draws what events tell it. It never guesses.
Everything that changes the screen is one event on one bus.

The demo (`src/js/30-sim.js`) emits these events from a script.
A real backend emits the same events, and no screen has to change.

```js
IRAS.ingest({ type: "state", state: "thinking" });   // what a live adapter calls
IRAS.bus.on("approval_result", (e) => { /* send your choice back */ });
```

## The events

| type | fields | what the screen does |
|---|---|---|
| `state` | `state`: idle, listening, thinking, speaking, acting, approval | Asks the state machine to move. Illegal moves are blocked and logged. |
| `wake` | `via` | Goes to **listening** at once, before the backend confirms. |
| `partial_transcript` | `text`, `final` | Shows what IRAS hears, live, in the card under the orb. |
| `speech_end` | `text` | Goes to **thinking**. Adds your spoken message to Chat. |
| `submit` | `text`, `via` | A typed request. Goes to **thinking**. Adds your message to Chat. |
| `token` | `text` | Streams into Chat and into the caption under the state name. |
| `tool_start` | `id`, `tool`, `title`, `detail`, `authority`, `screen?` | Adds a running row to Live activity and Activity. `authority` is `none`, `system` or `critical`. `screen` shows the screen peek (see below). |
| `tool_end` | `id`, `ok`, `ms`, `title?`, `detail?`, `result?` | Finishes that row. `ok:false` shows "Failed". |
| `peek_show`, `peek_step`, `peek_hide` | `spec`, `i` | Controls the screen peek card without adding a row. |
| `agent_step` | `run`, `agent`, `title`, `step:{id,label}`, `status`, `stepStatus`, `detail`, `index`, `total`, `final?`, `summary?` | Updates the run timeline in Agents and one row in Live activity. |
| `approval_request` | `id`, `authority`, `title`, `detail`, `effects[]`, `phrase?`, `expires_ms`, `approveLabel?` | Opens the approval overlay. `critical` is red and shows the voice phrase. |
| `approval_result` | `id`, `decision`, `via` | The screen emits this when you choose. `decision` is `approve`, `deny` or `expired`. |
| `tts_start`, `tts_end` | `text` | **Speaking**. The caption shows the sentence. |
| `audio_level` | `source`: mic or tts, `level`: 0 to 1 | Drives the orb rings and waveform. Send at 30 per second or less. |
| `provider` | `active`, `failover?`, `reason?` | Updates the provider chip. `failover:true` adds a log row and pulses the chip. |
| `sync` | `state`: syncing, synced, offline | Updates the sync chip. |
| `done` | `timing_ms` | Ends the reply and goes idle (unless an approval is open). |
| `cancel`, `error` | `message?` | Goes idle. |

`screen` and `peek_show` use a small spec:

```js
{ layout: "music" | "terminal" | "files",      // which picture of an app to draw
  app: "Spotify",
  steps: [{ label: "Pressing play", target: "play" }, ...] }
```

Targets are named boxes in each layout (`search`, `row1`, `play`, `line1`, `dir1`, `confirm`...).
It is a picture of the area IRAS controls, not a real screenshot.

## Allowed state moves

```
idle       -> listening, thinking, acting, speaking, approval
listening  -> thinking, idle, approval
thinking   -> acting, speaking, approval, idle, listening
acting     -> thinking, speaking, approval, idle
speaking   -> idle, listening, thinking, approval
approval   -> acting, thinking, speaking, idle
```

Listening and speaking can never be on at the same time. If you talk while IRAS is
speaking, it goes speaking, then listening. Any other move is blocked and an
`invalid_transition` event is emitted so you can see the bug.

## Reporting back

The screen reports only what you decide, never what it guessed.

```js
IRAS.bus.on("approval_result", (e) => send({ type: "approval_result", id: e.id, decision: e.decision, via: e.via }));
IRAS.bus.on("cancel",          ()  => send({ type: "cancel" }));      // Stop button, Esc
```

`via` is `button`, `escape` or `timeout`. A voice approval would arrive from the backend
as `approval_result` with `via: "voice"`, because only the backend can check the voice.

## What the current server already gives us

Live mode (Settings, Connection) uses endpoints that exist today:

| Endpoint | Used for |
|---|---|
| `GET /health` | The connection test |
| `GET /v1/providers/status` | The provider chip and its backups |
| `POST /v1/chat/stream` | Chat. Server-Sent Events |

The stream is translated like this (`src/js/35-live.js`):

| Server event | Becomes |
|---|---|
| `start` | caption "IRAS is working on it…", saves `thread_id` |
| `queued` | caption "Waiting in line…" |
| `token` | `token` |
| `done` | `done`. If `execution_mode` is `authorization_required`, shows a note |
| `error` | `error` and a message |

## Proposed next step: one live stream

Voice, approvals, agents and screen control need the server to push events while a
turn runs. A small `GET /v1/events` stream (Server-Sent Events or WebSocket) that sends
the events above would light up every screen with no UI change:

```js
const es = new EventSource(`${server}/v1/events?token=${token}`);
es.onmessage = (m) => IRAS.ingest(JSON.parse(m.data));
```

This endpoint does not exist yet. Everything else on this page does.
