# IRAS Cloud v5 RC3 architecture

```text
                       Cloud AI providers
                              ^
                              |
                        IRAS Cloud API
                        FastAPI / HTTPS
                              |
                     +--------+--------+
                     |                 |
             PostgreSQL state       Web/PWA
       memory + cloud workspace       client
                     ^                 |
                     |                 |
          +----------+----------+------+
          |                     |
 Windows IRAS cloud client     Android IRAS
 shared thread/history         shared thread/history
          |                     approvals/notifications
          |
 Windows IRAS device agent
 local policy / ToolRegistry / emergency stop
          |
 local apps/files/browser/OmniParser/Ollama
```

The public server intentionally does not register shell, filesystem, process, or unrestricted desktop-control tools. Those capabilities remain on authorized local IRAS nodes.

Cloud chat can request a local action only through the authenticated Remote/device job path. The paired Windows node remains the final enforcement point.

The unified cloud workspace (`src/iras/cloud_state.py`) stores only non-secret collaboration state: client presence, thread metadata, transcript and preferences. API/device/Remote/connector secrets are not stored in that workspace.

See `CLOUD_WORKSPACE_RC3.md` for the cross-client API and client behavior.
