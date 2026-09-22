# IRAS RC10 — Full Authorized Web Access

RC10 adds a persistent Playwright web-operator layer intended for end-to-end authorized web work while retaining the v4/v5 ToolRegistry, Remote/Master Control, audit and emergency-stop boundaries.

## Capability

- Broad public HTTP/HTTPS navigation with DNS/private-address SSRF checks.
- Persistent IRAS-owned browser profiles for cookies/session state without exposing cookie values to the model.
- Search through Bing, Google or DuckDuckGo.
- Multiple tabs, forward/back/reload, semantic page snapshots and bounded text extraction.
- Semantic interaction by visible text, ARIA role/name, form label, placeholder or selector.
- Select/check/keyboard/scroll/wait operations.
- Uploads, downloads with SHA-256 receipts, screenshots and persistent download history.
- Vault-referenced login: usernames/passwords are resolved inside IRAS and are never accepted as raw tool arguments or returned to the model.
- Bounded multi-step web batches (maximum 50 actions) with permission resolution based on the strongest action in the batch.
- CAPTCHA/MFA/anti-bot detection. IRAS pauses for user intervention rather than bypassing these controls.
- Owner domain allow/deny rules.

## Authority model

Reach is not authority. RC10 intentionally preserves:

- READ for observation/search/navigation.
- SYSTEM_ACTION for form filling, ordinary clicks, uploads/downloads and other stateful interaction.
- CRITICAL for consequential submit/login operations and high-impact click targets such as purchases, payments, publishing, account deletion or credential changes.
- Existing Remote/Master Control, approval, audit, UAC and emergency-stop enforcement.

Web content is untrusted external data. RC10 expands the prompt-injection wrapper to cover both `v5_browser_*` and `v5_web_*` tool output.

## Network policy defaults

```env
IRAS_WEB_HEADLESS=true
IRAS_WEB_PROFILE=owner
IRAS_WEB_DEFAULT_SEARCH=bing
IRAS_WEB_ALLOW_HTTP=true
IRAS_WEB_ALLOW_PRIVATE=false
IRAS_WEB_ALLOW_LOCALHOST=true
IRAS_WEB_ALLOW_SENSITIVE_UPLOADS=false
IRAS_WEB_MAX_DOWNLOAD_MB=1024
IRAS_WEB_NAV_TIMEOUT_MS=45000
IRAS_WEB_ACTION_TIMEOUT_MS=20000
```

Private/LAN browsing is intentionally off because IRAS already has explicit home/local-network adapters. Enable it only if the owner deliberately wants the browser to reach private address space.

## Authentication

The browser uses its own persistent profile under the IRAS state directory. It does not take over the user's normal Chrome profile. The owner can either log in manually in headed mode once or use the CRITICAL vault-referenced login tool. Cookie values are never returned by `session_status`.

## Installation acceptance

Run the targeted RC10 test, then the complete existing validation suite:

```powershell
.\apply-iras-rc10.ps1 -Repo "D:\Projects\IRAS-complete" -Test
cd D:\Projects\IRAS-complete
.\.venv\Scripts\Activate.ps1
.\run-v500-validation.ps1
```
