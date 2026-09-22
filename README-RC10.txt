IRAS RC10 — FULL AUTHORIZED WEB ACCESS

This cumulative package adds a persistent, permissioned public-web operator on top
of RC9.1. If RC9.1 is missing, apply-iras-rc10.ps1 installs the bundled cumulative
RC9.1 chain first.

Core additions:
- persistent IRAS-owned Playwright browser profile
- broad public HTTP/HTTPS access
- web search, tabs, page snapshots, semantic interaction, forms
- uploads/downloads/screenshots and SHA-256 download receipts
- vault-referenced login without raw credentials in tool arguments
- bounded multi-step web batches
- CAPTCHA/MFA/anti-bot detection (no bypass)
- owner domain allow/deny rules
- private-network SSRF boundary remains closed by default
- prompt-injection trust envelope expanded to v5_browser_* and v5_web_*

Apply:
  .\apply-iras-rc10.ps1 -Repo "D:\Projects\IRAS-complete" -Test

Then run:
  cd D:\Projects\IRAS-complete
  .\.venv\Scripts\Activate.ps1
  .\run-v500-validation.ps1

If Chromium is not installed for Playwright:
  python -m playwright install chromium
