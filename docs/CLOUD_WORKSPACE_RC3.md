# IRAS v5 RC3 Unified Cloud Workspace

IRAS Cloud now treats Windows, web/PWA, and Android as clients of one authenticated workspace rather than independent chat front ends.

## Shared state

The cloud workspace persists on the same `DATABASE_URL` backend used by v5 (PostgreSQL in deployment, SQLite locally):

- stable client identity/presence and capabilities;
- one shared active conversation thread;
- restart-safe user/assistant transcript;
- turn IDs so client retries do not duplicate user messages;
- non-secret cross-client preferences;
- thread-specific conversational context for direct cloud chat;
- existing v5 mobile events/approvals and Remote device state remain separate enforcement planes.

The state store never persists `IRAS_API_TOKEN`, device tokens, Remote session tokens, connector secrets, or vault material.

## API surface

Authenticated endpoints:

```text
POST /v1/cloud/clients/register
POST /v1/cloud/clients/{client_id}/heartbeat
GET  /v1/cloud/clients
GET  /v1/cloud/session
GET  /v1/cloud/threads
POST /v1/cloud/threads
POST /v1/cloud/threads/{thread_id}/activate
POST /v1/cloud/threads/{thread_id}/archive
GET  /v1/cloud/threads/{thread_id}/messages
GET  /v1/cloud/preferences
POST /v1/cloud/preferences/{key}
```

`/v1/chat` and `/v1/chat/stream` accept `client_id`, `thread_id`, and `turn_id`. Streaming `start`/`done` events return the resolved thread and persisted message IDs.

## Windows

The local `iras` command remains device-first and can use local Ollama/OmniParser/Windows tools. The cloud client joins the shared cloud transcript:

```powershell
.\run-iras-cloud-client.ps1
# or
iras-cloud-client
```

Configuration:

```env
IRAS_CLOUD_URL=https://your-iras-cloud.example
IRAS_CLOUD_TOKEN=your-long-cloud-token
```

If `IRAS_CLOUD_TOKEN` is empty, the client falls back to private `IRAS_API_TOKEN` configuration.

## Web/PWA

The web client creates a stable `web_*` client ID in browser local storage, registers with Cloud, resumes the active thread, and polls for cross-device message updates. The access token remains in `sessionStorage`, preserving the existing secret-handling boundary.

## Android

Android creates a stable `android_*` cloud client ID, resumes the active cloud thread, includes stable turn IDs in streamed chat, and polls the shared transcript alongside its existing approval/notification companion loop.

## Safety boundary

Cloud unification does **not** expose local shell/filesystem/process/desktop capabilities on the public server. State-changing Windows work still flows:

```text
cloud/web/mobile request
        ↓
short-lived authenticated Remote session
        ↓
paired Windows device bridge
        ↓
local Remote policy + ToolRegistry permissions + emergency stop
        ↓
Windows action
```

Remote protocol remains `1`.
